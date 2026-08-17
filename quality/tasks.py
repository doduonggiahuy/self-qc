from celery import shared_task
from django.utils import timezone

from .evaluation import evaluate_model_run
from .models import EvaluationModel, ModelEvaluationRun


@shared_task
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


@shared_task
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


@shared_task
def infer_annotation_frame(project_pk, frame_index, model_pk=None):
    from annotations.inference import predict
    from annotations.models import BoxAnnotation, Project
    from annotations.video import read_frame
    from .models import InferenceModel

    project = Project.objects.get(pk=project_pk)
    classes = list(project.classes.filter(enabled=True))
    model = InferenceModel.objects.filter(pk=model_pk, enabled=True).first() if model_pk else None
    proposals = predict(read_frame(project.video.path, frame_index), classes, model)
    project.boxes.filter(frame_index=frame_index, review_status="PREDICTED").delete()
    created = [BoxAnnotation.objects.create(
        project=project, frame_index=frame_index, label_class=item["label_class"],
        x1=item["bbox"][0], y1=item["bbox"][1], x2=item["bbox"][2], y2=item["bbox"][3],
        confidence=item["confidence"], source="YOLO_WORLD", review_status="PREDICTED", prompt=item["prompt"],
    ) for item in proposals]
    return {"boxes": [{"id": box.id, "class_id": box.label_class_id, "class_name": box.label_class.name, "color": box.label_class.color, "bbox": [box.x1, box.y1, box.x2, box.y2], "confidence": box.confidence, "source": box.source, "status": box.review_status, "prompt": box.prompt} for box in created]}


@shared_task(bind=True)
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
