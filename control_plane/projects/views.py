import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ProjectManifestForm
from .models import PlatformProject
from .services import apply_manifest


def _can_manage_platform(user):
    return user.is_staff or user.is_superuser


def _platform_manager_or_workspace(request):
    if _can_manage_platform(request.user):
        return None
    messages.info(request, "Tài khoản của bạn đã đăng nhập. Project manifest chỉ dành cho AI Admin.")
    return redirect("project-list")


@login_required
def project_list(request):
    response = _platform_manager_or_workspace(request)
    if response:
        return response
    return render(request, "platform_control/project_list.html", {
        "projects": PlatformProject.objects.prefetch_related("provisioning"),
    })


@login_required
def project_manifest_edit(request, key=None):
    response = _platform_manager_or_workspace(request)
    if response:
        return response
    project = get_object_or_404(PlatformProject, key=key) if key else None
    initial = {}
    if project:
        initial = {"key": project.key, "name": project.name, "manifest": json.dumps(project.manifest, indent=2, ensure_ascii=False)}
    form = ProjectManifestForm(request.POST or None, initial=initial)
    if project:
        form.fields["key"].disabled = True
    if request.method == "POST" and form.is_valid():
        try:
            item, events = apply_manifest(
                key=form.cleaned_data["key"],
                name=form.cleaned_data["name"],
                manifest=form.cleaned_data["manifest"],
                user=request.user,
            )
        except ValueError as exc:
            form.add_error("manifest", str(exc))
        else:
            messages.success(request, f"Đã lưu manifest v{item.manifest_version} và tạo {len(events)} provisioning event.")
            return redirect("platform-project-edit", key=item.key)
    return render(request, "platform_control/project_manifest_form.html", {"form": form, "project": project})
