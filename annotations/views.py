import hashlib
import io
import json
import logging

import cv2
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import AnnotationTaskForm, AutoAnnotationFunctionForm, ClientProjectForm, ProjectForm, ProjectLabelForm, RuleForm
from .application.project_schema import create_project_schema
from .models import AnnotationJob, AnnotationShape, AnnotationTask, AutoAnnotationFunction, AutoAnnotationRun, BoxAnnotation, ClientProject, LabelClass, Project, Rule
from .media import delete_project_media, ingest_task_uploads, read_project_frame

logger = logging.getLogger(__name__)


def _can_edit(user, project):
    return _can_view_annotation(user, project) and (user.is_superuser or project.owner_id == user.id or user.has_perm("annotations.change_boxannotation"))


def _can_view_annotation(user, project):
    if user.is_superuser or project.owner_id == user.id or _can_operate_annotation(user):
        return True
    task = project.annotation_task
    return bool(task and (task.assignees.filter(pk=user.pk).exists() or task.reviewers.filter(pk=user.pk).exists() or task.created_by_id == user.id))


def _is_root(user):
    return user.is_superuser


def _require_root(user):
    if not _is_root(user):
        raise PermissionDenied


def _can_create_annotation_task(user):
    return _is_root(user) or user.groups.filter(name="Data Annotator").exists()


def _can_operate_annotation(user):
    """Annotation team leads use the same Data Annotator role in the MVP.

    Project membership/team-lead scopes will be introduced with Annotation v2.
    Until then, this grants operational access only to the annotation domain,
    never to customer-project or AI-rule administration.
    """
    return _can_create_annotation_task(user)


def _can_use_task(user, task):
    return _can_operate_annotation(user) or task.created_by_id == user.id or task.assignees.filter(pk=user.pk).exists() or task.reviewers.filter(pk=user.pk).exists()


def _project(user, pk, edit=False):
    obj = get_object_or_404(Project, pk=pk)
    if not _can_view_annotation(user, obj) or (edit and not _can_edit(user, obj)):
        raise PermissionDenied
    return obj


def _client_project(user, pk):
    return get_object_or_404(ClientProject, pk=pk)


def _box_json(box):
    return {
        "id": box.id,
        "class_id": box.label_class_id,
        "class_name": box.label_class.name,
        "color": box.label_class.color,
        "bbox": [box.x1, box.y1, box.x2, box.y2],
        "confidence": box.confidence,
        "source": box.source,
        "status": box.review_status,
    }


@login_required
def project_list(request):
    projects = ClientProject.objects.prefetch_related("annotation_tasks__videos", "rules", "labels")
    return render(request, "annotations/project_list.html", {"projects": projects, "can_manage": _is_root(request.user)})


@login_required
def ground_truth_list(request):
    videos = Project.objects.select_related("client_project", "annotation_task", "owner").prefetch_related("classes")
    return render(request, "annotations/ground_truth_list.html", {"videos": videos, "can_manage": _is_root(request.user)})


@login_required
def client_project_create(request):
    _require_root(request.user)
    form = ClientProjectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            item = form.save(commit=False)
            item.owner = request.user
            item.save()
            create_project_schema(item, form.cleaned_data["labels_schema"], form.cleaned_data["rules_schema"])
        return redirect("client-project-detail", pk=item.pk)
    return render(request, "annotations/client_project_form.html", {"form": form})


@login_required
def client_project_detail(request, pk):
    item = _client_project(request.user, pk)
    can_manage = _is_root(request.user)
    if request.method == "POST":
        _require_root(request.user)
    rule_form = RuleForm(request.POST or None) if can_manage else None
    label_form = ProjectLabelForm(request.POST or None) if can_manage else None
    if request.method == "POST" and request.POST.get("action") == "rule" and rule_form.is_valid():
        rule = rule_form.save(commit=False)
        rule.client_project = item
        rule.save()
        return redirect("client-project-detail", pk=item.pk)
    if request.method == "POST" and request.POST.get("action") == "label" and label_form.is_valid():
        label = label_form.save(commit=False)
        label.client_project = item
        label.order = item.labels.count()
        label.save()
        return redirect("client-project-detail", pk=item.pk)
    return render(request, "annotations/client_project_detail.html", {
        "client_project": item,
        "rule_form": rule_form,
        "label_form": label_form,
        "can_manage": can_manage,
        "can_create_task": _can_create_annotation_task(request.user),
        "can_operate_annotation": _can_operate_annotation(request.user),
    })


@login_required
def annotation_task_list(request):
    tasks = AnnotationTask.objects.select_related("client_project").prefetch_related("rules", "videos")
    if not _can_operate_annotation(request.user):
        tasks = tasks.filter(Q(assignees=request.user) | Q(reviewers=request.user) | Q(created_by=request.user)).distinct()
    return render(request, "annotations/task_list.html", {"tasks": tasks, "can_manage": _is_root(request.user)})


@login_required
def annotation_task_create(request, pk):
    if not _can_create_annotation_task(request.user):
        raise PermissionDenied
    client_project = _client_project(request.user, pk)
    # A Data Annotator may be the team lead for this project.  The role may
    # create and assign annotation work, while Root still owns projects/rules.
    can_assign = _can_operate_annotation(request.user)
    form = AnnotationTaskForm(client_project, request.POST or None, request.FILES or None, allow_assignment=can_assign)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                task = form.save(commit=False)
                task.client_project = client_project
                task.created_by = request.user
                task.save()
                form.save_m2m()
                ingest_task_uploads(task, request.user, form.cleaned_data.get("data_files", []))
        except Exception as exc:
            form.add_error("data_files", f"Không thể xử lý data: {exc}")
        else:
            return redirect("annotation-task-detail", pk=task.pk)
    return render(request, "annotations/task_form.html", {"form": form, "client_project": client_project, "editing": False})


@login_required
def annotation_task_edit(request, pk):
    task = get_object_or_404(AnnotationTask.objects.select_related("client_project"), pk=pk)
    if not _can_operate_annotation(request.user):
        raise PermissionDenied
    form = AnnotationTaskForm(
        task.client_project, request.POST or None, request.FILES or None,
        instance=task, allow_assignment=True,
    )
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                task = form.save()
                ingest_task_uploads(task, request.user, form.cleaned_data.get("data_files", []))
        except Exception as exc:
            form.add_error("data_files", f"Không thể xử lý data: {exc}")
        else:
            return redirect("annotation-task-detail", pk=task.pk)
    return render(request, "annotations/task_form.html", {
        "form": form, "client_project": task.client_project, "task": task, "editing": True,
    })


@login_required
@require_POST
def annotation_task_delete(request, pk):
    task = get_object_or_404(AnnotationTask.objects.prefetch_related("videos"), pk=pk)
    if not _can_operate_annotation(request.user):
        raise PermissionDenied
    project_pk = task.client_project_id
    for media in task.videos.all():
        delete_project_media(media)
    task.delete()
    return redirect("client-project-detail", pk=project_pk)


@login_required
def annotation_task_detail(request, pk):
    task = get_object_or_404(AnnotationTask.objects.select_related("client_project").prefetch_related("rules", "videos"), pk=pk)
    if not _can_use_task(request.user, task):
        raise PermissionDenied
    functions = AutoAnnotationFunction.objects.filter(enabled=True)
    function_specs = {str(item.pk): item.spec for item in functions}
    project_labels = [
        {"name": label.name, "type": label.label_type, "color": label.color,
         "points": [point.name for point in label.skeleton_points.all()]}
        for label in task.client_project.labels.prefetch_related("skeleton_points")
    ]
    return render(request, "annotations/task_detail.html", {
        "task": task, "can_upload": _can_create_annotation_task(request.user),
        "auto_functions": functions, "auto_runs": task.auto_annotation_runs.select_related("function")[:10],
        "auto_function_specs": function_specs, "auto_project_labels": project_labels,
        "can_manage_task": _can_operate_annotation(request.user),
    })


@login_required
@require_POST
def start_auto_annotation(request, pk):
    task = get_object_or_404(AnnotationTask.objects.select_related("client_project"), pk=pk)
    if not _can_use_task(request.user, task):
        raise PermissionDenied
    if task.auto_annotation_runs.filter(status__in=["QUEUED", "RUNNING"]).exists():
        return JsonResponse({"error": "Task đã có một Auto Annotation run đang xử lý."}, status=409)
    function = get_object_or_404(AutoAnnotationFunction, pk=request.POST.get("function"), enabled=True)
    from .auto_annotation import default_mapping, validate_mapping
    mapping = default_mapping(function, task.client_project)
    raw_mapping = request.POST.get("mapping", "").strip()
    if raw_mapping:
        try:
            mapping = json.loads(raw_mapping)
        except ValueError:
            return JsonResponse({"error": "Mapping JSON không hợp lệ."}, status=400)
    try:
        mapping = validate_mapping(function, task.client_project, mapping)
        threshold = float(request.POST.get("threshold", 0.25))
        if not 0 <= threshold <= 1:
            raise ValueError
    except (ValueError, ValidationError) as exc:
        return JsonResponse({"error": str(exc) or "Threshold phải nằm trong khoảng 0–1."}, status=400)
    total = sum(job.stop_frame - job.start_frame + 1 for job in task.jobs.all())
    if total <= 0:
        return JsonResponse({"error": "Task chưa có Job/Data để annotate."}, status=400)
    run = AutoAnnotationRun.objects.create(
        task=task, function=function, threshold=threshold,
        cleanup=request.POST.get("cleanup") == "on", mapping=mapping,
        progress_total=total, requested_by=request.user,
    )
    from .tasks import run_auto_annotation
    try:
        result = run_auto_annotation.delay(run.pk)
    except Exception as exc:
        run.status = "FAILED"
        run.error = f"Không thể đưa run vào annotation queue: {exc}"
        run.save(update_fields=["status", "error"])
        return redirect("annotation-task-detail", pk=task.pk)
    run.celery_task_id = result.id or ""
    run.save(update_fields=["celery_task_id"])
    return redirect("annotation-task-detail", pk=task.pk)


@login_required
def auto_annotation_status(request, pk, run_pk):
    task = get_object_or_404(AnnotationTask, pk=pk)
    if not _can_use_task(request.user, task):
        raise PermissionDenied
    run = get_object_or_404(task.auto_annotation_runs.select_related("function"), pk=run_pk)
    return JsonResponse({
        "id": run.pk, "status": run.status, "progress": run.progress_current,
        "total": run.progress_total, "shapes_created": run.shapes_created,
        "error": run.error, "function": run.function.name,
    })


@login_required
@require_POST
def cancel_auto_annotation(request, pk, run_pk):
    task = get_object_or_404(AnnotationTask, pk=pk)
    if not _can_use_task(request.user, task):
        raise PermissionDenied
    run = get_object_or_404(task.auto_annotation_runs, pk=run_pk, status__in=["QUEUED", "RUNNING"])
    run.status = "CANCELLED"
    run.save(update_fields=["status"])
    return redirect("annotation-task-detail", pk=task.pk)


@login_required
def auto_annotation_functions(request):
    _require_root(request.user)
    edit_id = request.GET.get("edit")
    instance = get_object_or_404(AutoAnnotationFunction, pk=edit_id) if edit_id else None
    form = AutoAnnotationFunctionForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        function = form.save(commit=False)
        function.spec = form.cleaned_data["spec_json"]
        if not function.pk:
            function.created_by = request.user
        function.save()
        return redirect("auto-annotation-functions")
    return render(request, "annotations/auto_annotation_functions.html", {
        "functions": AutoAnnotationFunction.objects.all(), "form": form, "editing": instance,
    })


@login_required
@require_POST
def client_project_delete(request, pk):
    _require_root(request.user)
    item = _client_project(request.user, pk)
    item.delete()
    return redirect("project-list")


@login_required
@require_POST
def rule_delete(request, pk, rule_pk):
    _require_root(request.user)
    item = _client_project(request.user, pk)
    get_object_or_404(item.rules, pk=rule_pk).delete()
    return redirect("client-project-detail", pk=item.pk)


@login_required
@require_POST
def video_delete(request, pk, video_pk):
    if not _can_create_annotation_task(request.user):
        raise PermissionDenied
    task = get_object_or_404(AnnotationTask, pk=pk)
    if not _can_use_task(request.user, task):
        raise PermissionDenied
    video = get_object_or_404(task.videos, pk=video_pk)
    delete_project_media(video)
    video.delete()
    return redirect("annotation-task-detail", pk=task.pk)


@login_required
def project_create(request):
    if not _can_create_annotation_task(request.user):
        raise PermissionDenied
    task_pk = request.GET.get("task") or request.POST.get("annotation_task")
    task = get_object_or_404(AnnotationTask.objects.select_related("client_project"), pk=task_pk) if task_pk else None
    if task is None:
        raise Http404("Video must be uploaded into an annotation task.")
    if not _can_use_task(request.user, task):
        raise PermissionDenied
    form = ProjectForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            jobs = ingest_task_uploads(
                task, request.user, form.cleaned_data["data_files"],
                name=form.cleaned_data.get("name"), coverage=form.cleaned_data["coverage"],
            )
        except Exception as exc:
            form.add_error("data_files", str(exc))
        else:
            return redirect("annotation-job", pk=jobs[0].pk)
    return render(request, "annotations/project_form.html", {"form": form, "task": task})


@login_required
def annotate(request, pk):
    project = _project(request.user, pk, edit=True)
    if project.annotation_task_id and hasattr(project, "job"):
        return redirect("annotation-job", pk=project.job.pk)
    raise Http404("Legacy prompt annotator has been removed. Open an Annotation Job instead.")


@login_required
def annotation_job(request, pk):
    job = get_object_or_404(
        AnnotationJob.objects.select_related("task__client_project", "video").prefetch_related(
            "task__client_project__labels__attributes",
            "task__client_project__labels__skeleton_points",
            "task__client_project__labels__skeleton_edges__from_point",
            "task__client_project__labels__skeleton_edges__to_point",
        ), pk=pk,
    )
    if not _can_use_task(request.user, job.task):
        raise PermissionDenied
    labels = job.task.client_project.labels.all()
    schema = [{
        "id": label.id, "name": label.name, "type": label.label_type, "color": label.color,
        "attributes": [{"id": attr.id, "name": attr.name, "input_type": attr.input_type, "values": attr.values, "default_value": attr.default_value} for attr in label.attributes.all()],
        "points": [{"id": point.id, "name": point.name, "x": point.x, "y": point.y, "color": point.color} for point in label.skeleton_points.all()],
        "edges": [{"from": edge.from_point.name, "to": edge.to_point.name} for edge in label.skeleton_edges.all()],
    } for label in labels]
    if job.state == "new":
        job.state = "in_progress"
        job.save(update_fields=["state", "updated_at"])
    return render(request, "annotations/job_annotate.html", {"job": job, "project": job.video, "label_schema": schema})


@login_required
def job_frame_data(request, pk, frame_index):
    job = get_object_or_404(AnnotationJob.objects.select_related("task"), pk=pk)
    if not _can_use_task(request.user, job.task):
        raise PermissionDenied
    shapes = job.shapes.filter(frame_index=frame_index).select_related("label")
    return JsonResponse({"shapes": [{"id": shape.id, "label_id": shape.label_id, "label_name": shape.label.name, "type": shape.shape_type, "points": shape.points, "attributes": shape.attributes, "source": shape.source, "confidence": shape.confidence} for shape in shapes]})


@login_required
@require_POST
def save_job_frame(request, pk, frame_index):
    job = get_object_or_404(AnnotationJob.objects.select_related("task__client_project"), pk=pk)
    if not _can_use_task(request.user, job.task):
        raise PermissionDenied
    payload = json.loads(request.body)
    allowed_labels = {label.id: label for label in job.task.client_project.labels.all()}
    with transaction.atomic():
        job.shapes.filter(frame_index=frame_index).delete()
        created = []
        for item in payload.get("shapes", []):
            label = allowed_labels.get(int(item.get("label_id", 0)))
            if not label or item.get("type") not in {"rectangle", "skeleton"} or item.get("type") != label.label_type:
                continue
            shape = AnnotationShape.objects.create(job=job, frame_index=frame_index, label=label, shape_type=item["type"], points=item.get("points", []), attributes=item.get("attributes", {}), source=item.get("source", "manual"), confidence=item.get("confidence"), created_by=request.user, updated_by=request.user)
            created.append(shape.id)
    return JsonResponse({"ok": True, "ids": created})


@login_required
def frame_image(request, pk, frame_index):
    project = _project(request.user, pk)
    if frame_index >= project.frame_count:
        raise Http404
    frame = read_project_frame(project, frame_index)
    ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise Http404
    return FileResponse(iter([encoded.tobytes()]), content_type="image/jpeg")


@login_required
def frame_data(request, pk, frame_index):
    project = _project(request.user, pk)
    boxes = project.boxes.filter(frame_index=frame_index).select_related("label_class")
    return JsonResponse({"boxes": [_box_json(box) for box in boxes]})


@login_required
@require_POST
def save_frame(request, pk, frame_index):
    project = _project(request.user, pk, edit=True)
    payload = json.loads(request.body)
    with transaction.atomic():
        keep = []
        for raw in payload.get("boxes", []):
            box_id = raw.get("id")
            box = project.boxes.filter(pk=box_id, frame_index=frame_index).first() if box_id else None
            if box is None:
                box = BoxAnnotation(project=project, frame_index=frame_index, created_by=request.user, source="MANUAL")
            box.label_class = get_object_or_404(project.classes, pk=raw["class_id"])
            box.x1, box.y1, box.x2, box.y2 = raw["bbox"]
            box.review_status = raw.get("status", "EDITED")
            box.updated_by = request.user
            if box.source == "YOLO_WORLD" and box.review_status == "PREDICTED":
                box.review_status = "EDITED"
            box.save()
            keep.append(box.pk)
        project.boxes.filter(frame_index=frame_index).exclude(pk__in=keep).delete()
        project.current_frame = frame_index
        project.save(update_fields=["current_frame", "updated_at"])
    return JsonResponse({"ok": True})


@login_required
def export_jsonl(request, pk):
    project = _project(request.user, pk)
    approved = project.boxes.filter(review_status__in=["APPROVED", "EDITED"]).select_related("label_class").order_by("frame_index", "id")
    grouped = {}
    for box in approved:
        grouped.setdefault(box.frame_index, []).append({
            "id": str(box.id), "class": box.label_class.name,
            "bbox": [box.x1, box.y1, box.x2, box.y2],
        })
    records = [json.dumps({
        "video": project.video.name, "frame_index": frame,
        "timestamp": frame / project.fps if project.fps else None,
        "objects": objects,
    }, ensure_ascii=False) for frame, objects in grouped.items()]
    content = ("\n".join(records) + "\n").encode()
    digest = hashlib.sha256()
    with open(project.video.path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    response = FileResponse(io.BytesIO(content), content_type="application/x-ndjson")
    response["Content-Disposition"] = f'attachment; filename="project-{project.pk}-gt.jsonl"'
    response["X-Video-SHA256"] = digest.hexdigest()
    return response
