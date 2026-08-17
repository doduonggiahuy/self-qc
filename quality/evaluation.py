import json
import time
from collections import Counter, defaultdict
from pathlib import Path

from django.conf import settings


def evaluate_model_run(run):
    if run.dataset.task not in {"DETECTION", "CLASSIFICATION"}:
        raise ValueError(f"Evaluator {run.dataset.get_task_display()} chưa được triển khai; dataset đã được lưu để nối adapter sau.")
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError("Ultralytics chưa được cài trong worker.") from exc
    model_path = Path(run.model.model_file.path)
    if model_path.suffix.lower() not in {".pt", ".onnx"}:
        raise ValueError("Weight .pth cần model adapter/architecture riêng; worker không thể load generic .pth.")
    model = YOLO(str(model_path))
    root = Path(settings.DATASET_ROOT) / run.dataset.source_path
    records = json.loads((root / run.dataset.manifest["normalized_gt"]).read_text(encoding="utf-8"))
    if run.dataset.task == "CLASSIFICATION":
        return _evaluate_classification(run, model, root, records)
    return _evaluate_detection(run, model, root, records)


def _resolve_image(root, relative):
    root = root.resolve()
    direct = (root / relative).resolve()
    if direct.is_relative_to(root) and direct.is_file():
        return direct
    matches = list(root.rglob(Path(relative).name))
    if len(matches) != 1:
        raise FileNotFoundError(f"Không xác định duy nhất image: {relative}")
    return matches[0]


def _evaluate_classification(run, model, root, records):
    correct, totals, hits = 0, Counter(), Counter()
    reverse_mapping = {model_name: gt_name for model_name, gt_name in run.model.class_mapping.items() if gt_name}
    for index, record in enumerate(records, 1):
        result = model.predict(str(_resolve_image(root, record["image"])), verbose=False)[0]
        predicted = result.names[int(result.probs.top1)]
        normalized = reverse_mapping.get(predicted)
        truth = record["class_name"]
        totals[truth] += 1
        if normalized == truth:
            correct += 1
            hits[truth] += 1
        _progress(run, index, {"image": record["image"], "kind": "classification", "truth": truth, "prediction": predicted, "mapped_prediction": normalized})
    per_class = [{"class": name, "accuracy": hits[name] / count if count else 0, "samples": count} for name, count in totals.items()]
    return {"accuracy": correct / len(records) if records else 0, "samples": len(records)}, per_class


def _evaluate_detection(run, model, root, records):
    class_by_id = {item.external_id: item.name for item in run.dataset.classes.all()}
    reverse_mapping = {model_name: gt_name for model_name, gt_name in run.model.class_mapping.items() if gt_name}
    mapped_gt = set(reverse_mapping.values())
    totals = defaultdict(lambda: Counter(tp=0, fp=0, fn=0))
    for index, record in enumerate(records, 1):
        image_path = _resolve_image(root, record["image"])
        result = model.predict(str(image_path), verbose=False)[0]
        height, width = result.orig_shape
        gt_by_class, pred_by_class = defaultdict(list), defaultdict(list)
        for annotation in record.get("annotations", []):
            gt_name = class_by_id.get(str(annotation["class_id"]))
            if not gt_name or gt_name not in mapped_gt:
                continue
            gt_by_class[gt_name].append(_bbox_xyxy(annotation, width, height))
        if result.boxes is not None:
            for box in result.boxes:
                model_name = result.names[int(box.cls.item())]
                gt_name = reverse_mapping.get(model_name)
                if gt_name:
                    xyxy = [float(value) for value in box.xyxy[0].tolist()]
                    pred_by_class[gt_name].append(xyxy)
        for name in set(gt_by_class) | set(pred_by_class):
            tp, fp, fn = _match_boxes(gt_by_class[name], pred_by_class[name])
            totals[name].update(tp=tp, fp=fp, fn=fn)
        preview_gt = []
        for annotation in record.get("annotations", []):
            gt_name = class_by_id.get(str(annotation["class_id"]), str(annotation["class_id"]))
            preview_gt.append({"label": gt_name, "bbox": _bbox_xyxy(annotation, width, height)})
        preview_predictions = []
        if result.boxes is not None:
            for box in result.boxes:
                model_name = result.names[int(box.cls.item())]
                preview_predictions.append({
                    "label": reverse_mapping.get(model_name) or model_name,
                    "model_label": model_name,
                    "confidence": float(box.conf.item()),
                    "bbox": [float(value) for value in box.xyxy[0].tolist()],
                })
        _progress(run, index, {"image": record["image"], "kind": "detection", "width": width, "height": height, "ground_truth": preview_gt, "predictions": preview_predictions})
    per_class = []
    aggregate = Counter(tp=0, fp=0, fn=0)
    for name, values in totals.items():
        aggregate.update(values)
        precision = values["tp"] / (values["tp"] + values["fp"]) if values["tp"] + values["fp"] else 0
        recall = values["tp"] / (values["tp"] + values["fn"]) if values["tp"] + values["fn"] else 0
        per_class.append({"class": name, "precision_iou50": precision, "recall_iou50": recall, **values})
    precision = aggregate["tp"] / (aggregate["tp"] + aggregate["fp"]) if aggregate["tp"] + aggregate["fp"] else 0
    recall = aggregate["tp"] / (aggregate["tp"] + aggregate["fn"]) if aggregate["tp"] + aggregate["fn"] else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
    return {"precision_iou50": precision, "recall_iou50": recall, "f1_iou50": f1, **aggregate, "images": len(records)}, per_class


def _bbox_xyxy(annotation, width, height):
    x, y, w, h = annotation["bbox"]
    if annotation["bbox_format"] == "xywh_normalized":
        x, y, w, h = x * width, y * height, w * width, h * height
        return [x - w / 2, y - h / 2, x + w / 2, y + h / 2]
    return [x, y, x + w, y + h]


def _match_boxes(gt_boxes, predicted_boxes, threshold=0.5):
    unmatched = set(range(len(predicted_boxes)))
    tp = 0
    for gt in gt_boxes:
        candidates = [(index, _iou(gt, predicted_boxes[index])) for index in unmatched]
        best = max(candidates, key=lambda item: item[1], default=(None, 0))
        if best[0] is not None and best[1] >= threshold:
            tp += 1
            unmatched.remove(best[0])
    return tp, len(unmatched), len(gt_boxes) - tp


def _iou(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = max(0, a[2] - a[0]) * max(0, a[3] - a[1]) + max(0, b[2] - b[0]) * max(0, b[3] - b[1]) - intersection
    return intersection / union if union else 0


def _progress(run, current, preview=None):
    run.progress_current = current
    if preview is not None:
        from .models import ModelEvaluationFrame
        ModelEvaluationFrame.objects.update_or_create(
            run=run, frame_index=current - 1,
            defaults={"image": preview.get("image", ""), "output": preview},
        )
    now = time.monotonic()
    should_preview = preview is not None and (current == 1 or current == run.progress_total or now - getattr(run, "_preview_saved_at", 0) >= 0.5)
    if should_preview:
        run.preview = preview
        run._preview_saved_at = now
        run.save(update_fields=["progress_current", "preview"])
    elif current == run.progress_total or current % 10 == 0:
        run.save(update_fields=["progress_current"])
