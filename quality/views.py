from django.contrib import messages
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST
from django.http import FileResponse, JsonResponse, StreamingHttpResponse
import json
import shutil
from pathlib import Path
from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse

from annotations.models import ClientProject, Project
from .forms import EvaluationDatasetForm, InferenceModelForm, TestCaseForm
from .models import EvaluationDataset, EvaluationModel, InferenceModel, ModelEvaluationFrame, ModelEvaluationRun, TestCase, TestRun
from .datasets import (
    append_upload_chunk,
    finalize_chunked_upload,
    initialize_chunked_upload,
    save_uploaded_dataset,
)
from .services import create_run, execute_run, freeze_ground_truth
from .model_artifacts import remove_artifact
from .model_sources import provision_model


def _editable_project(user, pk):
    project = get_object_or_404(Project, pk=pk)
    if not (user.is_superuser or project.owner_id == user.id or user.has_perm("annotations.edit_all_projects")):
        raise PermissionDenied
    return project


def _editable_client_project(user, pk):
    project = get_object_or_404(ClientProject, pk=pk)
    if not (user.is_superuser or project.owner_id == user.id or user.has_perm("annotations.edit_all_projects")):
        raise PermissionDenied
    return project


@login_required
def model_quality_workspace(request):
    projects = ClientProject.objects.all() if request.user.is_superuser else ClientProject.objects.filter(owner=request.user)
    datasets = EvaluationDataset.objects.filter(owner=request.user).select_related("client_project")[:30]
    runs = ModelEvaluationRun.objects.filter(owner=request.user).select_related("dataset", "dataset__client_project", "model")[:30]
    return render(request, "quality/model_quality_dashboard.html", {
        "projects": projects, "datasets": datasets, "runs": runs,
        "project_count": projects.count(),
        "dataset_count": EvaluationDataset.objects.filter(owner=request.user).count(),
        "run_count": ModelEvaluationRun.objects.filter(owner=request.user).count(),
        "running_count": ModelEvaluationRun.objects.filter(owner=request.user, status="RUNNING").count(),
    })


@login_required
def create_model_quality_workspace(request):
    projects = ClientProject.objects.all()
    if not request.user.is_superuser:
        projects = projects.filter(owner=request.user)
    project_options = [{"id": item.pk, "name": item.name} for item in projects]
    return render(request, "quality/model_quality_workspace.html", {
        "project_options": project_options,
        "selected_project": request.GET.get("project", ""),
    })


@login_required
def edit_model_quality_task(request, dataset_pk):
    dataset = get_object_or_404(EvaluationDataset, pk=dataset_pk, owner=request.user)
    form = EvaluationDatasetForm(request.user, request.POST or None, instance=dataset)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Đã cập nhật evaluation task.")
        return redirect("model-quality-workspace")
    return render(request, "quality/model_quality_task_form.html", {"form": form, "dataset": dataset})


@login_required
@require_POST
def delete_model_quality_task(request, dataset_pk):
    dataset = get_object_or_404(EvaluationDataset, pk=dataset_pk, owner=request.user)
    if dataset.evaluation_runs.filter(status__in=["QUEUED", "RUNNING"]).exists():
        messages.error(request, "Không thể xóa task khi evaluation run đang chạy.")
        return redirect("model-quality-workspace")
    model_files = [model.model_file for model in dataset.candidate_models.all() if model.model_file]
    dataset_root = Path(settings.DATASET_ROOT).resolve()
    content_path = (dataset_root / dataset.source_path).resolve() if dataset.source_path else None
    artifact_root = content_path.parent if content_path and content_path.is_relative_to(dataset_root) else None
    with transaction.atomic():
        dataset.evaluation_runs.all().delete()
        dataset.candidate_models.all().delete()
        dataset.delete()
    for model_file in model_files:
        model_file.delete(save=False)
    if artifact_root and artifact_root != dataset_root:
        shutil.rmtree(artifact_root, ignore_errors=True)
    messages.success(request, "Đã xóa evaluation task và toàn bộ artifact liên quan.")
    return redirect("model-quality-workspace")


def _dataset_json(dataset):
    return {
        "id": dataset.pk, "name": dataset.name, "status": dataset.status,
        "client_project_id": dataset.client_project_id,
        "client_project_name": dataset.client_project.name if dataset.client_project_id else None,
        "format": dataset.format, "task": dataset.task,
        "image_count": dataset.image_count, "annotation_count": dataset.annotation_count,
        "missing_label_count": dataset.missing_label_count, "manifest": dataset.manifest,
        "error": dataset.error,
        "classes": [{"id": item.external_id, "name": item.name, "count": item.annotation_count} for item in dataset.classes.all()],
    }


def _evaluation_model_json(model):
    return {
        "id": model.pk, "name": model.name, "status": model.status,
        "task": model.detected_task, "classes": model.model_classes,
        "mapping": model.class_mapping, "metadata": model.metadata,
        "error": model.error, "file": Path(model.model_file.name).name,
    }


@login_required
@require_POST
def upload_evaluation_dataset(request):
    name = request.POST.get("name", "").strip()
    source_kind = request.POST.get("source_kind", "").upper()
    uploads = request.FILES.getlist("files")
    if not name or source_kind not in {"ZIP", "FOLDER"} or not uploads:
        return JsonResponse({"error": "Thiếu tên, nguồn hoặc file dataset."}, status=400)
    if source_kind == "ZIP" and (len(uploads) != 1 or Path(uploads[0].name).suffix.lower() != ".zip"):
        return JsonResponse({"error": "Nguồn ZIP chỉ chấp nhận đúng một file .zip."}, status=400)
    dataset = EvaluationDataset.objects.create(name=name, owner=request.user, source_kind=source_kind, source_path="")
    try:
        save_uploaded_dataset(dataset, uploads, request.POST.getlist("paths"))
    except Exception as exc:
        dataset.status, dataset.error = "ERROR", str(exc)
        dataset.save(update_fields=["status", "error", "updated_at"])
        return JsonResponse(_dataset_json(dataset), status=400)
    return JsonResponse(_dataset_json(dataset), status=201)


@login_required
@require_POST
def initialize_evaluation_dataset_upload(request):
    name = request.POST.get("name", "").strip()
    source_kind = request.POST.get("source_kind", "").upper()
    if not name or source_kind not in {"ZIP", "FOLDER"}:
        return JsonResponse({"error": "Thiếu tên hoặc loại nguồn dataset."}, status=400)
    client_project = _editable_client_project(request.user, request.POST.get("client_project_id"))
    dataset = EvaluationDataset.objects.create(name=name, client_project=client_project, owner=request.user, source_kind=source_kind, source_path="", status="PROCESSING")
    initialize_chunked_upload(dataset)
    return JsonResponse(_dataset_json(dataset), status=201)


@login_required
@require_POST
def upload_evaluation_dataset_chunk(request, dataset_pk):
    try:
        chunk_index = int(request.POST.get("chunk_index", ""))
    except ValueError:
        return JsonResponse({"error": "chunk_index không hợp lệ."}, status=400)
    uploads = request.FILES.getlist("files")
    if chunk_index < 0 or not uploads:
        return JsonResponse({"error": "Chunk không có dữ liệu."}, status=400)
    try:
        with transaction.atomic():
            dataset = EvaluationDataset.objects.select_for_update().get(
                pk=dataset_pk, owner=request.user, status="PROCESSING"
            )
            append_upload_chunk(dataset, uploads, request.POST.getlist("paths"), chunk_index)
    except EvaluationDataset.DoesNotExist:
        return JsonResponse({"error": "Upload session không tồn tại hoặc đã kết thúc."}, status=404)
    except (OSError, ValueError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    upload = dataset.manifest.get("upload", {})
    return JsonResponse({"id": dataset.pk, **upload})


@login_required
@require_POST
def finalize_evaluation_dataset_upload(request, dataset_pk):
    from .tasks import process_evaluation_dataset

    with transaction.atomic():
        dataset = get_object_or_404(
            EvaluationDataset.objects.select_for_update(), pk=dataset_pk,
            owner=request.user, status="PROCESSING"
        )
        upload = dict(dataset.manifest.get("upload", {}))
        if not upload.get("next_chunk"):
            return JsonResponse({"error": "Upload chưa có chunk dữ liệu."}, status=400)
        if not upload.get("finalize_requested"):
            upload["finalize_requested"] = True
            dataset.manifest = {**dataset.manifest, "upload": upload}
            dataset.save(update_fields=["manifest", "updated_at"])
            transaction.on_commit(lambda: process_evaluation_dataset.delay(dataset.pk))
    return JsonResponse(_dataset_json(dataset), status=202)


@login_required
@require_GET
def evaluation_dataset_upload_status(request, dataset_pk):
    dataset = get_object_or_404(EvaluationDataset, pk=dataset_pk, owner=request.user)
    return JsonResponse(_dataset_json(dataset))


@login_required
@require_POST
def upload_evaluation_model(request, dataset_pk):
    dataset = get_object_or_404(EvaluationDataset, pk=dataset_pk, owner=request.user, status="READY")
    uploaded = request.FILES.get("model_file")
    if not uploaded or Path(uploaded.name).suffix.lower() not in {".pt", ".pth", ".onnx"}:
        return JsonResponse({"error": "Model phải là file .pt, .pth hoặc .onnx."}, status=400)
    model = EvaluationModel.objects.create(
        dataset=dataset, owner=request.user, name=Path(uploaded.name).stem,
        model_file=uploaded, status="ANALYZING",
    )
    from .tasks import analyze_evaluation_model
    transaction.on_commit(lambda: analyze_evaluation_model.delay(model.pk))
    return JsonResponse(_evaluation_model_json(model), status=202)


@login_required
@require_GET
def evaluation_model_status(request, model_pk):
    model = get_object_or_404(EvaluationModel, pk=model_pk, owner=request.user)
    return JsonResponse(_evaluation_model_json(model))


@login_required
@require_POST
def delete_evaluation_model(request, model_pk):
    model = get_object_or_404(EvaluationModel, pk=model_pk, owner=request.user)
    if model.runs.exists():
        return JsonResponse({"error": "Model đã có evaluation run nên không thể xóa."}, status=409)
    model_file = model.model_file
    model.delete()
    if model_file:
        model_file.delete(save=False)
    return JsonResponse({"deleted": True})


@login_required
@require_POST
def confirm_evaluation_model_mapping(request, model_pk):
    model = get_object_or_404(EvaluationModel, pk=model_pk, owner=request.user, status="READY")
    try:
        mapping = json.loads(request.POST.get("class_mapping", "{}"))
        confirmed_gt = json.loads(request.POST.get("gt_classes", "[]"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Class mapping JSON không hợp lệ."}, status=400)
    for item in confirmed_gt:
        name = str(item.get("name", "")).strip()
        if name:
            model.dataset.classes.filter(external_id=str(item.get("id"))).update(name=name)
    gt_names = set(model.dataset.classes.values_list("name", flat=True))
    model_classes = set(model.model_classes)
    if not isinstance(mapping, dict) or not mapping or not set(mapping).issubset(model_classes):
        return JsonResponse({"error": "Mapping phải bắt đầu từ class của model."}, status=400)
    invalid_targets = {value for value in mapping.values() if value is not None and value not in gt_names}
    if invalid_targets:
        return JsonResponse({"error": f"Mapping chứa GT class không tồn tại: {', '.join(sorted(invalid_targets))}."}, status=400)
    if not any(mapping.values()):
        return JsonResponse({"error": "Cần map ít nhất một model class với GT class."}, status=400)
    model.class_mapping = mapping
    model.save(update_fields=["class_mapping"])
    return JsonResponse(_evaluation_model_json(model))


@login_required
@require_POST
def create_model_evaluation_run(request, dataset_pk):
    dataset = get_object_or_404(EvaluationDataset, pk=dataset_pk, owner=request.user, status="READY")
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON không hợp lệ."}, status=400)
    model = get_object_or_404(EvaluationModel, pk=payload.get("model_id"), dataset=dataset, owner=request.user, status="READY")
    if not model.class_mapping:
        return JsonResponse({"error": "Model chưa được xác nhận class mapping."}, status=400)
    run = ModelEvaluationRun.objects.create(dataset=dataset, model=model, owner=request.user, progress_total=dataset.image_count, input_snapshot={"dataset_id": dataset.pk, "dataset_manifest": dataset.manifest, "model_id": model.pk, "model_file": model.model_file.name, "class_mapping": model.class_mapping})
    from .tasks import execute_model_evaluation
    execute_model_evaluation.delay(run.pk)
    return JsonResponse({"id": run.pk, "status": run.status}, status=202)


@login_required
def model_evaluation_run_status(request, run_pk):
    run = get_object_or_404(ModelEvaluationRun, pk=run_pk, owner=request.user)
    preview = run.preview or {}
    return JsonResponse({"id": run.pk, "status": run.status, "current": run.progress_current, "total": run.progress_total, "metrics": run.metrics, "per_class_metrics": run.per_class_metrics, "preview": preview, "preview_image_url": reverse("model-quality-run-preview-image", args=[run.pk]) if preview.get("image") else None, "viewer_url": reverse("model-quality-run-viewer", args=[run.pk]), "error": run.error})


@login_required
@require_GET
def model_evaluation_run_viewer(request, run_pk):
    run = get_object_or_404(
        ModelEvaluationRun.objects.select_related("dataset", "dataset__client_project", "model"),
        pk=run_pk, owner=request.user,
    )
    return render(request, "quality/model_evaluation_viewer.html", {"run": run})


@login_required
@require_GET
def model_evaluation_frame_data(request, run_pk, frame_index):
    run = get_object_or_404(ModelEvaluationRun, pk=run_pk, owner=request.user)
    frame = get_object_or_404(ModelEvaluationFrame, run=run, frame_index=frame_index)
    return JsonResponse({
        "frame_index": frame.frame_index, "image": frame.image, "output": frame.output,
        "image_url": reverse("model-quality-run-frame-image", args=[run.pk, frame.frame_index]),
    })


@login_required
@require_GET
def model_evaluation_frame_image(request, run_pk, frame_index):
    run = get_object_or_404(ModelEvaluationRun.objects.select_related("dataset"), pk=run_pk, owner=request.user)
    frame = get_object_or_404(ModelEvaluationFrame, run=run, frame_index=frame_index)
    from .evaluation import _resolve_image
    try:
        image_path = _resolve_image(Path(settings.DATASET_ROOT) / run.dataset.source_path, frame.image)
    except FileNotFoundError as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    return FileResponse(image_path.open("rb"))


@login_required
@require_GET
def export_model_evaluation_run(request, run_pk):
    run = get_object_or_404(ModelEvaluationRun, pk=run_pk, owner=request.user)
    def rows():
        header = {"run_id": run.pk, "dataset": run.dataset.name, "model": run.model.name, "status": run.status, "metrics": run.metrics, "per_class_metrics": run.per_class_metrics}
        yield json.dumps({"type": "summary", **header}, ensure_ascii=False) + "\n"
        for frame in run.frames.iterator(chunk_size=1000):
            yield json.dumps({"type": "frame", "frame_index": frame.frame_index, "image": frame.image, **frame.output}, ensure_ascii=False) + "\n"
    response = StreamingHttpResponse(rows(), content_type="application/x-ndjson")
    response["Content-Disposition"] = f'attachment; filename="model-evaluation-run-{run.pk}.jsonl"'
    return response


@login_required
@require_GET
def export_model_evaluation_frame(request, run_pk, frame_index):
    run = get_object_or_404(ModelEvaluationRun, pk=run_pk, owner=request.user)
    frame = get_object_or_404(ModelEvaluationFrame, run=run, frame_index=frame_index)
    response = JsonResponse({"run_id": run.pk, "frame_index": frame.frame_index, "image": frame.image, **frame.output}, json_dumps_params={"ensure_ascii": False, "indent": 2})
    response["Content-Disposition"] = f'attachment; filename="run-{run.pk}-frame-{frame.frame_index}.json"'
    return response


@login_required
@require_GET
def model_evaluation_preview_image(request, run_pk):
    run = get_object_or_404(ModelEvaluationRun.objects.select_related("dataset"), pk=run_pk, owner=request.user)
    relative = (run.preview or {}).get("image")
    if not relative:
        return JsonResponse({"error": "Run chưa có preview frame."}, status=404)
    from .evaluation import _resolve_image
    try:
        image_path = _resolve_image(Path(settings.DATASET_ROOT) / run.dataset.source_path, relative)
    except FileNotFoundError as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    return FileResponse(image_path.open("rb"))


def _context(project, form=None):
    return {
        "project": project,
        "releases": project.gt_releases.all(),
        "test_cases": project.test_cases.select_related("ground_truth_release", "target"),
        "runs": TestRun.objects.filter(test_case__project=project).select_related("test_case")[:30],
        "form": form or TestCaseForm(project),
    }


@login_required
def dashboard(request, project_pk):
    project = _editable_project(request.user, project_pk)
    return render(request, "quality/dashboard.html", _context(project))


@login_required
@require_POST
def freeze_gt(request, project_pk):
    project = _editable_project(request.user, project_pk)
    release = freeze_ground_truth(project, request.user)
    messages.success(request, f"Đã freeze Ground Truth v{release.version} với {release.annotation_count} annotation.")
    return redirect("quality-dashboard", project_pk=project.pk)


@login_required
@require_POST
def create_test_case(request, project_pk):
    project = _editable_project(request.user, project_pk)
    form = TestCaseForm(project, request.POST)
    if form.is_valid():
        TestCase.objects.create(
            project=project, name=form.cleaned_data["name"], kind="GT_VALIDATION",
            ground_truth_release=form.cleaned_data["ground_truth_release"],
            assertions=[{"metric": "annotation_count", "operator": ">=", "value": form.cleaned_data["minimum_annotations"]}],
            created_by=request.user,
        )
        messages.success(request, "Đã tạo GT validation test case.")
        return redirect("quality-dashboard", project_pk=project.pk)
    return render(request, "quality/dashboard.html", _context(project, form), status=400)


@login_required
@require_POST
def run_test_case(request, project_pk, case_pk):
    project = _editable_project(request.user, project_pk)
    test_case = get_object_or_404(TestCase, pk=case_pk, project=project, enabled=True)
    run = create_run(test_case, request.user)
    # Synchronous only for this first vertical slice; the runner boundary can move to a worker unchanged.
    execute_run(run)
    messages.success(request, f"Test run #{run.pk}: {run.get_status_display()}.")
    return redirect("quality-run-detail", project_pk=project.pk, run_pk=run.pk)


@login_required
def run_detail(request, project_pk, run_pk):
    project = _editable_project(request.user, project_pk)
    run = get_object_or_404(TestRun.objects.select_related("test_case"), pk=run_pk, test_case__project=project)
    return render(request, "quality/run_detail.html", {"project": project, "run": run})


def _require_admin(user):
    if not (user.is_superuser or user.is_staff):
        raise PermissionDenied


@login_required
def system_dashboard(request):
    _require_admin(request.user)
    models = InferenceModel.objects.all()
    return render(request, "quality/system_dashboard.html", {
        "project_count": Project.objects.count(), "user_count": get_user_model().objects.count(),
        "model_count": models.count(), "ready_model_count": models.filter(status="READY").count(),
        "error_model_count": models.filter(status="ERROR").count(), "run_count": TestRun.objects.count(),
        "recent_models": models.order_by("-updated_at")[:5], "recent_runs": TestRun.objects.select_related("test_case")[:5],
    })


@login_required
def system_models(request):
    _require_admin(request.user)
    form = InferenceModelForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        model = provision_model(form.create_model(request.user))
        if model.status == "ERROR":
            messages.error(request, f"Không thể chuẩn bị model: {model.validation_error}")
        else:
            messages.success(request, f"Model {model.name} đã sẵn sàng.")
        return redirect("quality-system-models")
    return render(request, "quality/system_models.html", {"models": InferenceModel.objects.all(), "form": form})


@login_required
def edit_system_model(request, model_pk):
    _require_admin(request.user)
    model = get_object_or_404(InferenceModel, pk=model_pk)
    if request.method == "POST":
        model.enabled = request.POST.get("enabled") == "on" and model.status == "READY"
        model.save(update_fields=["enabled"])
        messages.success(request, f"Đã cập nhật {model.name}.")
        return redirect("quality-system-models")
    return render(request, "quality/system_model_edit.html", {"model": model})


@login_required
@require_POST
def retry_system_model(request, model_pk):
    _require_admin(request.user)
    model = get_object_or_404(InferenceModel, pk=model_pk)
    if model.status == "READY":
        messages.info(request, f"Model {model.name} đã sẵn sàng.")
        return redirect("quality-system-models")
    model.status, model.validation_error = "PENDING", ""
    model.save(update_fields=["status", "validation_error", "updated_at"])
    model = provision_model(model)
    if model.status == "READY":
        messages.success(request, f"Đã chuẩn bị lại model {model.name}.")
    else:
        messages.error(request, f"Không thể chuẩn bị {model.name}: {model.validation_error}")
    return redirect("quality-system-models")


@login_required
@require_POST
def delete_system_model(request, model_pk):
    _require_admin(request.user)
    model = get_object_or_404(InferenceModel, pk=model_pk)
    model_name = model.name
    remove_artifact(model)
    model.delete()
    messages.success(request, f"Đã xóa model {model_name} và file weight do registry quản lý.")
    return redirect("quality-system-models")


class _ArtifactReference:
    def __init__(self, reference):
        self.artifact_path = reference
        self.model_file = None
        self._reference = reference

    @property
    def runtime_reference(self):
        return self._reference
