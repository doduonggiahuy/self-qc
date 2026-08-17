from django.urls import path
from . import views

urlpatterns = [
    path("", views.project_list, name="project-list"),
    path("ground-truth/", views.ground_truth_list, name="ground-truth-list"),
    path("clients/new/", views.client_project_create, name="client-project-create"),
    path("clients/<int:pk>/", views.client_project_detail, name="client-project-detail"),
    path("clients/<int:pk>/delete/", views.client_project_delete, name="client-project-delete"),
    path("clients/<int:pk>/rules/<int:rule_pk>/delete/", views.rule_delete, name="rule-delete"),
    path("clients/<int:pk>/videos/<int:video_pk>/delete/", views.video_delete, name="video-delete"),
    path("projects/new/", views.project_create, name="project-create"),
    path("projects/<int:pk>/annotate/", views.annotate, name="annotate"),
    path("projects/<int:pk>/frames/<int:frame_index>.jpg", views.frame_image, name="frame-image"),
    path("api/projects/<int:pk>/frames/<int:frame_index>/", views.frame_data, name="frame-data"),
    path("api/projects/<int:pk>/frames/<int:frame_index>/infer/", views.infer_frame, name="infer-frame"),
    path("api/projects/<int:pk>/frames/<int:frame_index>/save/", views.save_frame, name="save-frame"),
    path("api/projects/<int:pk>/classes/save/", views.save_classes, name="save-classes"),
    path("projects/<int:pk>/export/jsonl/", views.export_jsonl, name="export-jsonl"),
]
