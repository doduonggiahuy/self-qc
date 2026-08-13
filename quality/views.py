from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.http import JsonResponse
import json
from django.contrib.auth import get_user_model

from annotations.models import Project
from .forms import InferenceModelForm, TestCaseForm
from .models import InferenceModel, TestCase, TestRun, UserInferencePreference
from .services import create_run, execute_run, freeze_ground_truth
from .model_artifacts import remove_artifact
from .model_sources import provision_model


def _editable_project(user, pk):
    project = get_object_or_404(Project, pk=pk)
    if not (user.is_superuser or project.owner_id == user.id or user.has_perm("annotations.edit_all_projects")):
        raise PermissionDenied
    return project


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
def delete_system_model(request, model_pk):
    _require_admin(request.user)
    model = get_object_or_404(InferenceModel, pk=model_pk)
    model_name = model.name
    remove_artifact(model)
    model.delete()
    messages.success(request, f"Đã xóa model {model_name} và file weight do registry quản lý.")
    return redirect("quality-system-models")


@login_required
@require_POST
def select_inference_model(request):
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON không hợp lệ."}, status=400)
    model_id = payload.get("model_id")
    model = None
    if model_id:
        model = get_object_or_404(InferenceModel, pk=model_id, enabled=True)
        if not model.is_selectable:
            return JsonResponse({"error": "Model chưa có adapter inference tương thích."}, status=400)
    UserInferencePreference.objects.update_or_create(user=request.user, defaults={"model": model})
    return JsonResponse({"ok": True, "model_name": model.name if model else "System default"})


class _ArtifactReference:
    def __init__(self, reference):
        self.artifact_path = reference
        self.model_file = None
        self._reference = reference

    @property
    def runtime_reference(self):
        return self._reference
