from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from annotations.models import ClientProject
from .annotation_forms import AnnotationMemberCreateForm, AnnotationMemberRoleForm
from .roles import ROLE_GROUPS, platform_roles_for, set_platform_role


def _can_manage_annotation(user):
    return user.is_staff or user.is_superuser


def _annotation_manager_or_workspace(request):
    if _can_manage_annotation(request.user):
        return None
    messages.info(request, "Tài khoản của bạn đã đăng nhập. Annotation Workspace nằm ở đây; Platform Members chỉ dành cho AI Admin.")
    return redirect("ground-truth-list")


@login_required
def annotation_dashboard(request):
    response = _annotation_manager_or_workspace(request)
    if response:
        return response
    users = get_user_model().objects.filter(is_superuser=False).prefetch_related("groups").order_by("username")
    for user in users:
        user.platform_roles = platform_roles_for(user)
    projects = ClientProject.objects.prefetch_related("videos").order_by("name")
    return render(request, "platform_control/annotation_dashboard.html", {"members": users, "projects": projects})


@login_required
def annotation_member_create(request):
    response = _annotation_manager_or_workspace(request)
    if response:
        return response
    form = AnnotationMemberCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = get_user_model().objects.create_user(
            username=form.cleaned_data["username"], password=form.cleaned_data["password"],
        )
        set_platform_role(user, form.cleaned_data["role"])
        messages.success(request, f"Đã tạo account {user.username} với role {ROLE_GROUPS[form.cleaned_data['role']]}.")
        return redirect("platform-annotation-dashboard")
    return render(request, "platform_control/annotation_member_form.html", {"form": form, "member": None})


@login_required
def annotation_member_edit(request, user_pk):
    response = _annotation_manager_or_workspace(request)
    if response:
        return response
    member = get_object_or_404(get_user_model(), pk=user_pk, is_superuser=False)
    role = next((code for code, name in ROLE_GROUPS.items() if member.groups.filter(name=name).exists()), "DATA_ANNOTATOR")
    form = AnnotationMemberRoleForm(request.POST or None, initial={"role": role, "is_active": member.is_active})
    if request.method == "POST" and form.is_valid():
        set_platform_role(member, form.cleaned_data["role"])
        member.is_active = form.cleaned_data["is_active"]
        member.save(update_fields=["is_active"])
        messages.success(request, f"Đã cập nhật quyền annotation cho {member.username}.")
        return redirect("platform-annotation-dashboard")
    return render(request, "platform_control/annotation_member_form.html", {"form": form, "member": member})
