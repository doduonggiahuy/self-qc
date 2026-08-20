"""CVAT-compatible automatic annotation boundary.

The registry and mapping live in Annotation; remote functions only receive an
image and return model-native labels. No project class or keypoint is hardcoded.
"""

import base64
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.core.exceptions import ValidationError

from .models import AnnotationShape
from .media import read_project_frame_bytes


def labels_compatible(model_label, project_label):
    model_type = model_label.get("type", "any")
    target_type = project_label.label_type
    if model_type == "any":
        return target_type != "skeleton"
    if target_type == "rectangle":
        return model_type in {"rectangle", "any"}
    return model_type == target_type


def default_mapping(function, project):
    """Match model labels and skeleton points by stable names and compatible types."""
    result = {}
    labels = list(project.labels.prefetch_related("skeleton_points"))
    for model_label in function.spec:
        target = next((item for item in labels if item.name == model_label.get("name") and labels_compatible(model_label, item)), None)
        if not target:
            continue
        entry = {"name": target.name, "attributes": {}}
        if target.label_type == "skeleton":
            target_points = {point.name for point in target.skeleton_points.all()}
            entry["sublabels"] = {
                point["name"]: {"name": point["name"], "attributes": {}}
                for point in model_label.get("sublabels", []) if point.get("name") in target_points
            }
        result[model_label["name"]] = entry
    return result


def validate_mapping(function, project, mapping):
    model_labels = {item.get("name"): item for item in function.spec}
    project_labels = {item.name: item for item in project.labels.prefetch_related("skeleton_points")}
    normalized = {}
    for model_name, entry in mapping.items():
        if model_name not in model_labels:
            raise ValidationError(f'Unknown model label "{model_name}".')
        target = project_labels.get(entry.get("name"))
        if not target:
            raise ValidationError(f'Unknown Project label "{entry.get("name")}".')
        if not labels_compatible(model_labels[model_name], target):
            raise ValidationError(f'Incompatible mapping: "{model_name}" → "{target.name}".')
        normalized_entry = {"name": target.name, "attributes": entry.get("attributes", {})}
        if target.label_type == "skeleton":
            model_points = {item.get("name") for item in model_labels[model_name].get("sublabels", [])}
            target_points = {item.name for item in target.skeleton_points.all()}
            point_mapping = entry.get("sublabels", {})
            for source_name, target_entry in point_mapping.items():
                target_name = target_entry.get("name") if isinstance(target_entry, dict) else target_entry
                if source_name not in model_points or target_name not in target_points:
                    raise ValidationError(f'Invalid skeleton point mapping "{source_name}" → "{target_name}".')
            normalized_entry["sublabels"] = point_mapping
        normalized[model_name] = normalized_entry
    if not normalized:
        raise ValidationError("Không có model label nào được map sang Project label.")
    return normalized


def invoke(function, image_bytes, threshold):
    """Call a CVAT-style function with canonical source bytes.

    Do not turn a stored JPEG/PNG into OpenCV pixels and back into JPEG here.
    The model service already owns image decoding, and forwarding the original
    bytes preserves details needed for small-object detection.
    """
    payload = json.dumps({
        "image": base64.b64encode(image_bytes).decode("ascii"),
        "threshold": threshold,
    }).encode("utf-8")
    request = Request(function.endpoint_url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=function.timeout_seconds) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"Function HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot connect to function: {exc.reason}") from exc
    if not isinstance(result, list):
        raise RuntimeError("Function output must be a JSON annotation array")
    return result


def convert_and_create(run, job, frame_index, annotations):
    labels = {item.name: item for item in run.task.client_project.labels.prefetch_related("skeleton_points")}
    created = []
    for annotation in annotations:
        mapping = run.mapping.get(annotation.get("label"))
        if not mapping:
            continue
        label = labels.get(mapping["name"])
        confidence = float(annotation.get("confidence", 0))
        shape_type = annotation.get("type")
        if label.label_type == "rectangle" and shape_type == "rectangle":
            points = [float(value) for value in annotation.get("points", [])]
            if len(points) != 4:
                continue
        elif label.label_type == "skeleton" and shape_type == "skeleton":
            output = {item.get("label"): item for item in annotation.get("elements", [])}
            point_mapping = mapping.get("sublabels", {})
            by_target = {}
            for source_name, target_entry in point_mapping.items():
                item = output.get(source_name)
                if not item or len(item.get("points", [])) < 2:
                    continue
                target_name = target_entry.get("name") if isinstance(target_entry, dict) else target_entry
                by_target[target_name] = {
                    "name": target_name, "x": float(item["points"][0]), "y": float(item["points"][1]),
                    "visible": not bool(item.get("outside", 0)),
                    "confidence": float(item.get("confidence", 0)),
                }
            points = [by_target[point.name] for point in label.skeleton_points.all() if point.name in by_target]
            if not points:
                continue
        else:
            continue
        created.append(AnnotationShape(
            job=job, label=label, frame_index=frame_index, shape_type=label.label_type,
            points=points, attributes={}, source="auto", confidence=confidence,
            created_by=run.requested_by, updated_by=run.requested_by,
        ))
    return AnnotationShape.objects.bulk_create(created)


def annotate_run(run):
    if run.cleanup:
        AnnotationShape.objects.filter(job__task=run.task).delete()
    count = 0
    for job in run.task.jobs.select_related("video"):
        for frame_index in range(job.start_frame, job.stop_frame + 1):
            run.refresh_from_db(fields=["status"])
            if run.status == "CANCELLED":
                return count
            annotations = invoke(run.function, read_project_frame_bytes(job.video, frame_index), run.threshold)
            count += len(convert_and_create(run, job, frame_index, annotations))
            run.progress_current += 1
            run.shapes_created = count
            run.save(update_fields=["progress_current", "shapes_created"])
    return count
