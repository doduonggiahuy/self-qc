import hashlib

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .evaluators import EVALUATORS
from .models import GroundTruthItem, GroundTruthRelease, TestRun


def _video_sha256(project):
    digest = hashlib.sha256()
    with open(project.video.path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@transaction.atomic
def freeze_ground_truth(project, user):
    reviewed = project.boxes.filter(review_status__in=["APPROVED", "EDITED"]).select_related("label_class")
    version = (project.gt_releases.aggregate(value=Max("version"))["value"] or 0) + 1
    release = GroundTruthRelease.objects.create(
        project=project,
        version=version,
        status="FROZEN",
        coverage=project.coverage,
        video_sha256=_video_sha256(project),
        annotation_count=reviewed.count(),
        manifest={
            "schema_version": "1.0",
            "video": project.video.name,
            "width": project.width,
            "height": project.height,
            "fps": project.fps,
            "frame_count": project.frame_count,
        },
        created_by=user,
        frozen_at=timezone.now(),
    )
    GroundTruthItem.objects.bulk_create([
        GroundTruthItem(
            release=release,
            frame_index=box.frame_index,
            timestamp_ms=round(box.frame_index * 1000 / project.fps) if project.fps else None,
            label=box.label_class.name,
            payload={"bbox": [box.x1, box.y1, box.x2, box.y2], "source": box.source},
            source_annotation_id=box.pk,
        )
        for box in reviewed
    ])
    return release


def create_run(test_case, user):
    release = test_case.ground_truth_release
    return TestRun.objects.create(
        test_case=test_case,
        created_by=user,
        input_snapshot={
            "test_case_id": test_case.pk,
            "test_case_version": test_case.version,
            "gt_release_id": release.pk if release else None,
            "gt_version": release.version if release else None,
            "target_id": test_case.target_id,
            "config": test_case.config,
        },
    )


def execute_run(run):
    run.status = "RUNNING"
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])
    evaluator_class = EVALUATORS.get(run.test_case.kind)
    if evaluator_class is None:
        run.status = "INCONCLUSIVE"
        run.error = f"Chưa có evaluator cho loại {run.test_case.kind}."
    else:
        try:
            result = evaluator_class().evaluate(run)
            run.metrics = result.metrics
            run.assertion_results = result.assertion_results
            run.status = result.status
        except Exception as exc:
            run.status = "ERROR"
            run.error = str(exc)
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "metrics", "assertion_results", "error", "finished_at"])
    return run
