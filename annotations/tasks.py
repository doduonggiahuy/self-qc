from celery import shared_task
from django.utils import timezone

from .auto_annotation import annotate_run
from .models import AutoAnnotationRun


@shared_task(queue="annotation", bind=True)
def run_auto_annotation(self, run_pk):
    run = AutoAnnotationRun.objects.select_related("task__client_project", "function", "requested_by").get(pk=run_pk)
    if run.status == "CANCELLED":
        return {"run_id": run.pk, "shapes_created": 0, "cancelled": True}
    run.status = "RUNNING"
    run.started_at = timezone.now()
    run.celery_task_id = self.request.id or ""
    run.save(update_fields=["status", "started_at", "celery_task_id"])
    try:
        annotate_run(run)
    except Exception as exc:
        run.status = "FAILED"
        run.error = str(exc)
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "finished_at"])
        raise
    run.refresh_from_db(fields=["status"])
    if run.status != "CANCELLED":
        run.status = "COMPLETED"
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "finished_at"])
    return {"run_id": run.pk, "shapes_created": run.shapes_created}
