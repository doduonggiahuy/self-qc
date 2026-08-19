from celery import shared_task
from django.utils import timezone

from .evaluation import evaluate_model_run
from .models import EvaluationModel, ModelEvaluationRun


@shared_task(queue="quality")
def analyze_evaluation_model(model_pk):
    from .model_inspection import inspect_model_artifact

    model = EvaluationModel.objects.get(pk=model_pk)
    try:
        result = inspect_model_artifact(model.model_file.path)
    except Exception as exc:
        model.status = "ERROR"
        model.error = str(exc)
        model.save(update_fields=["status", "error"])
        return {"status": "ERROR", "error": model.error}
    model.status = "READY"
    model.detected_task = result["task"]
    model.model_classes = result["classes"]
    model.metadata = result["metadata"]
    model.error = ""
    model.save(update_fields=["status", "detected_task", "model_classes", "metadata", "error"])
    return {"status": "READY", "classes": model.model_classes}


@shared_task(queue="quality")
def process_evaluation_dataset(dataset_pk):
    from .datasets import finalize_chunked_upload
    from .models import EvaluationDataset

    dataset = EvaluationDataset.objects.get(pk=dataset_pk)
    try:
        finalize_chunked_upload(dataset)
    except Exception as exc:
        dataset.status = "ERROR"
        dataset.error = str(exc)
        dataset.save(update_fields=["status", "error", "updated_at"])
        raise
    return dataset.pk


@shared_task(bind=True, queue="quality")
def execute_model_evaluation(self, run_pk):
    run = ModelEvaluationRun.objects.select_related("dataset", "model").get(pk=run_pk)
    run.status = "RUNNING"
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])
    try:
        metrics, per_class = evaluate_model_run(run)
    except Exception as exc:
        run.status = "ERROR"
        run.error = str(exc)
    else:
        run.status = "COMPLETED"
        run.metrics = metrics
        run.per_class_metrics = per_class
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "metrics", "per_class_metrics", "error", "finished_at"])
