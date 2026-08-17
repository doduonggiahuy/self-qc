import ast
import json
from pathlib import Path


def inspect_model_artifact(path):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".onnx":
        classes, task, metadata = _inspect_onnx(path)
    elif suffix == ".pt":
        classes, task, metadata = _inspect_ultralytics(path)
    elif suffix == ".pth":
        classes, task, metadata = _inspect_pytorch_checkpoint(path)
    else:
        raise ValueError("Chỉ hỗ trợ metadata của .pt, .pth và .onnx.")
    classes = _normalize_classes(classes)
    if not classes:
        raise ValueError("Weight không chứa metadata class có thể nhận diện tự động.")
    return {"classes": classes, "task": str(task or "").upper(), "metadata": metadata}


def _normalize_classes(value):
    if isinstance(value, dict):
        def key(item):
            return int(item[0]) if str(item[0]).isdigit() else str(item[0])
        value = [name for _, name in sorted(value.items(), key=key)]
    if not isinstance(value, (list, tuple)):
        return []
    return [str(name).strip() for name in value if str(name).strip()]


def _decode_metadata_value(value):
    if not isinstance(value, str):
        return value
    for parser in (json.loads, ast.literal_eval):
        try:
            return parser(value)
        except (ValueError, SyntaxError, json.JSONDecodeError):
            pass
    return value


def _inspect_onnx(path):
    try:
        import onnx
    except ImportError as exc:
        raise RuntimeError("Worker chưa cài thư viện onnx để đọc metadata.") from exc
    model = onnx.load(str(path), load_external_data=False)
    properties = {item.key: _decode_metadata_value(item.value) for item in model.metadata_props}
    classes = properties.get("names") or properties.get("class_names") or properties.get("classes")
    metadata = {key: value for key, value in properties.items() if key not in {"names", "class_names", "classes"}}
    metadata.update({"format": "ONNX", "ir_version": model.ir_version})
    return classes, properties.get("task"), metadata


def _inspect_ultralytics(path):
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError("Worker chưa cài Ultralytics.") from exc
    model = YOLO(str(path))
    task = getattr(model, "task", "")
    return getattr(model, "names", None), task, {"format": "PyTorch", "framework": "Ultralytics"}


def _inspect_pytorch_checkpoint(path):
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("Worker chưa cài PyTorch.") from exc
    checkpoint = torch.load(str(path), map_location="cpu", weights_only=True)
    if not isinstance(checkpoint, dict):
        raise ValueError("Checkpoint .pth không phải dictionary có metadata.")
    containers = [checkpoint]
    for key in ("meta", "metadata", "config"):
        if isinstance(checkpoint.get(key), dict):
            containers.append(checkpoint[key])
    classes = next((item.get(key) for item in containers for key in ("names", "class_names", "classes") if item.get(key)), None)
    task = next((item.get("task") for item in containers if item.get("task")), "")
    return classes, task, {"format": "PyTorch checkpoint"}
