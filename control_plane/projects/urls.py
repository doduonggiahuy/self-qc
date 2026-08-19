from django.urls import path

from . import annotation_views, views


urlpatterns = [
    path("platform/annotation/", annotation_views.annotation_dashboard, name="platform-annotation-dashboard"),
    path("platform/annotation/members/new/", annotation_views.annotation_member_create, name="platform-annotation-member-create"),
    path("platform/annotation/members/<int:user_pk>/", annotation_views.annotation_member_edit, name="platform-annotation-member-edit"),
    path("platform/projects/", views.project_list, name="platform-project-list"),
    path("platform/projects/new/", views.project_manifest_edit, name="platform-project-create"),
    path("platform/projects/<slug:key>/", views.project_manifest_edit, name="platform-project-edit"),
]
