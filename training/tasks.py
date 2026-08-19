from celery import shared_task

from .models import TrainingRun


@shared_task(queue="training")
def execute_training_run(run_pk):
    """Execution seam; GPU/training backend will be plugged in later."""
    run = TrainingRun.objects.get(pk=run_pk)
    run.status = "FAILED"
    run.error = "Training executor chưa được cấu hình."
    run.save(update_fields=["status", "error"])
    return {"status": run.status, "run_id": run.pk}
