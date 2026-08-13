from django.urls import path
from . import views

urlpatterns = [
    path("system/", views.system_dashboard, name="quality-system-dashboard"),
    path("system/models/", views.system_models, name="quality-system-models"),
    path("system/models/<int:model_pk>/edit/", views.edit_system_model, name="quality-system-model-edit"),
    path("system/models/<int:model_pk>/delete/", views.delete_system_model, name="quality-system-model-delete"),
    path("account/inference-model/", views.select_inference_model, name="quality-select-inference-model"),
    path("projects/<int:project_pk>/quality/", views.dashboard, name="quality-dashboard"),
    path("projects/<int:project_pk>/quality/freeze-gt/", views.freeze_gt, name="quality-freeze-gt"),
    path("projects/<int:project_pk>/quality/test-cases/", views.create_test_case, name="quality-create-case"),
    path("projects/<int:project_pk>/quality/test-cases/<int:case_pk>/run/", views.run_test_case, name="quality-run-case"),
    path("projects/<int:project_pk>/quality/runs/<int:run_pk>/", views.run_detail, name="quality-run-detail"),
]
