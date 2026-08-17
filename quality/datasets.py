import json
import shutil
import uuid
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

import yaml
from django.conf import settings
from django.db import transaction

from .models import EvaluationDataset, EvaluationDatasetClass


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
MAX_ARCHIVE_FILES = settings.DATASET_MAX_ARCHIVE_FILES
MAX_EXTRACTED_BYTES = settings.DATASET_MAX_EXTRACTED_BYTES


def _safe_relative_path(raw):
    value = str(raw).replace("\\", "/").lstrip("/")
    path = PurePosixPath(value)
    if not value or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"Đường dẫn không an toàn: {raw}")
    return Path(*path.parts)


def save_uploaded_dataset(dataset, uploaded_files, relative_paths=None):
    root = Path(settings.DATASET_ROOT) / f"{dataset.pk}-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    if dataset.source_kind == "ZIP":
        uploaded = uploaded_files[0]
        archive_path = root / "source.zip"
        _write_upload(archive_path, uploaded)
        content_root = root / "content"
        _extract_zip_safely(archive_path, content_root)
    else:
        content_root = root / "content"
        content_root.mkdir()
        relative_paths = relative_paths or [item.name for item in uploaded_files]
        if len(relative_paths) != len(uploaded_files):
            raise ValueError("Danh sách relative path không khớp file upload.")
        for uploaded, raw_path in zip(uploaded_files, relative_paths):
            destination = content_root / _safe_relative_path(raw_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            _write_upload(destination, uploaded)
    dataset.source_path = str(content_root.relative_to(settings.DATASET_ROOT))
    dataset.save(update_fields=["source_path", "updated_at"])
    return inspect_dataset(dataset)


def initialize_chunked_upload(dataset):
    root = Path(settings.DATASET_ROOT) / f"{dataset.pk}-{uuid.uuid4().hex}"
    content_root = root / "content"
    content_root.mkdir(parents=True, exist_ok=False)
    dataset.source_path = str(content_root.relative_to(settings.DATASET_ROOT))
    dataset.manifest = {"upload": {"next_chunk": 0, "received_bytes": 0, "received_files": 0}}
    dataset.save(update_fields=["source_path", "manifest", "updated_at"])
    return dataset


def append_upload_chunk(dataset, uploaded_files, relative_paths, chunk_index):
    upload = dict(dataset.manifest.get("upload", {}))
    expected = int(upload.get("next_chunk", 0))
    if chunk_index < expected:
        return dataset  # Idempotent retry after a lost HTTP response.
    if chunk_index != expected:
        raise ValueError(f"Chunk sai thứ tự: cần {expected}, nhận {chunk_index}.")
    root = Path(settings.DATASET_ROOT) / dataset.source_path
    received_bytes = 0
    if dataset.source_kind == "ZIP":
        if len(uploaded_files) != 1:
            raise ValueError("Mỗi ZIP chunk phải chứa đúng một binary part.")
        archive_path = root.parent / "source.zip"
        expected_offset = int(upload.get("received_bytes", 0))
        mode = "r+b" if archive_path.exists() else "wb"
        with archive_path.open(mode) as target:
            # If a process died after writing but before committing the manifest,
            # retry starts exactly at the last committed byte boundary.
            target.truncate(expected_offset)
            target.seek(expected_offset)
            for part in uploaded_files[0].chunks():
                target.write(part)
                received_bytes += len(part)
        received_files = 0
    else:
        if len(relative_paths) != len(uploaded_files):
            raise ValueError("Danh sách relative path không khớp file upload.")
        for uploaded, raw_path in zip(uploaded_files, relative_paths):
            destination = root / _safe_relative_path(raw_path)
            if destination.exists():
                raise ValueError(f"File bị trùng trong dataset: {raw_path}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            _write_upload(destination, uploaded)
            received_bytes += uploaded.size
        received_files = len(uploaded_files)
    upload.update({
        "next_chunk": expected + 1,
        "received_bytes": int(upload.get("received_bytes", 0)) + received_bytes,
        "received_files": int(upload.get("received_files", 0)) + received_files,
    })
    dataset.manifest = {**dataset.manifest, "upload": upload}
    dataset.save(update_fields=["manifest", "updated_at"])
    return dataset


def finalize_chunked_upload(dataset):
    content_root = Path(settings.DATASET_ROOT) / dataset.source_path
    if dataset.source_kind == "ZIP":
        archive_path = content_root.parent / "source.zip"
        if not archive_path.is_file():
            raise ValueError("Chưa nhận được dữ liệu ZIP.")
        _extract_zip_safely(archive_path, content_root)
    elif not any(content_root.rglob("*")):
        raise ValueError("Folder upload chưa có file.")
    return inspect_dataset(dataset)


def _write_upload(destination, uploaded):
    with destination.open("wb") as target:
        for chunk in uploaded.chunks():
            target.write(chunk)


def _extract_zip_safely(archive_path, destination):
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if len(members) > MAX_ARCHIVE_FILES:
            raise ValueError(f"ZIP vượt quá {MAX_ARCHIVE_FILES} files.")
        if sum(item.file_size for item in members) > MAX_EXTRACTED_BYTES:
            raise ValueError(f"Dung lượng sau giải nén vượt giới hạn {MAX_EXTRACTED_BYTES} bytes.")
        destination.mkdir(exist_ok=True)
        for member in members:
            relative = _safe_relative_path(member.filename.rstrip("/"))
            target = destination / relative
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def inspect_dataset(dataset):
    root = Path(settings.DATASET_ROOT) / dataset.source_path
    files = [path for path in root.rglob("*") if path.is_file()]
    images = [path for path in files if path.suffix.lower() in IMAGE_SUFFIXES]
    json_files = [path for path in files if path.suffix.lower() == ".json"]
    yaml_files = [path for path in files if path.suffix.lower() in {".yaml", ".yml"}]
    label_files = [path for path in files if path.suffix.lower() == ".txt" and any(part.lower() in {"label", "labels"} for part in path.parts)]

    coco = _find_coco(json_files)
    if coco:
        result = _inspect_coco(coco, images)
    elif label_files or yaml_files:
        result = _inspect_yolo(root, images, label_files, yaml_files)
    else:
        result = _inspect_classification(root, images)

    ground_truth = result.pop("ground_truth")
    normalized_dir = root / ".qc"
    normalized_dir.mkdir(exist_ok=True)
    normalized_path = normalized_dir / "ground_truth.json"
    normalized_path.write_text(json.dumps(ground_truth, ensure_ascii=False), encoding="utf-8")
    result["manifest"]["normalized_gt"] = str(normalized_path.relative_to(root))
    with transaction.atomic():
        dataset.classes.all().delete()
        EvaluationDatasetClass.objects.bulk_create([
            EvaluationDatasetClass(dataset=dataset, external_id=str(item["id"]), name=item["name"], annotation_count=item["count"])
            for item in result["classes"]
        ])
        dataset.format = result["format"]
        dataset.task = result["task"]
        dataset.image_count = result["image_count"]
        dataset.annotation_count = result["annotation_count"]
        dataset.missing_label_count = result["missing_label_count"]
        dataset.manifest = result["manifest"]
        dataset.status = "READY"
        dataset.error = ""
        dataset.save()
    return dataset


def _find_coco(json_files):
    for path in json_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError, OSError):
            continue
        if isinstance(data, dict) and all(key in data for key in ("images", "annotations", "categories")):
            return path, data
    return None


def _inspect_coco(coco, disk_images):
    path, data = coco
    counts = Counter(str(item.get("category_id")) for item in data["annotations"])
    has_keypoints = any(item.get("keypoints") for item in data["annotations"])
    has_segments = any(item.get("segmentation") for item in data["annotations"])
    task = "POSE" if has_keypoints else "SEGMENTATION" if has_segments else "DETECTION"
    categories = [{"id": item["id"], "name": item["name"], "count": counts[str(item["id"])]} for item in data["categories"]]
    image_by_id = {item["id"]: item for item in data["images"]}
    grouped = {item["id"]: [] for item in data["images"]}
    for item in data["annotations"]:
        grouped.setdefault(item.get("image_id"), []).append({"class_id": str(item.get("category_id")), "bbox": item.get("bbox"), "bbox_format": "xywh_pixels", "keypoints": item.get("keypoints"), "segmentation": item.get("segmentation")})
    ground_truth = [{"image": image_by_id[key].get("file_name"), "width": image_by_id[key].get("width"), "height": image_by_id[key].get("height"), "annotations": value} for key, value in grouped.items()]
    return {"format": "COCO", "task": task, "image_count": len(data["images"]), "annotation_count": len(data["annotations"]), "missing_label_count": max(0, len(disk_images) - len({item.get("image_id") for item in data["annotations"]})), "classes": categories, "manifest": {"annotation_file": str(path), "disk_image_count": len(disk_images), "warnings": []}, "ground_truth": ground_truth}


def _inspect_yolo(root, images, label_files, yaml_files):
    names = {}
    for path in yaml_files:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            raw_names = data.get("names", {})
            names = {str(index): name for index, name in enumerate(raw_names)} if isinstance(raw_names, list) else {str(key): value for key, value in raw_names.items()}
            if names:
                break
        except (ValueError, UnicodeDecodeError, OSError, yaml.YAMLError):
            continue
    counts, max_columns = Counter(), 0
    parsed_labels = {}
    for path in label_files:
        parsed_labels[path.stem] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if not parts:
                    continue
                counts[parts[0]] += 1
                max_columns = max(max_columns, len(parts))
                if len(parts) >= 5:
                    parsed_labels[path.stem].append({"class_id": parts[0], "bbox": [float(value) for value in parts[1:5]], "bbox_format": "xywh_normalized", "extra": [float(value) for value in parts[5:]]})
        except (UnicodeDecodeError, OSError):
            continue
    task = "POSE" if max_columns > 6 else "SEGMENTATION" if max_columns == 6 else "DETECTION"
    class_ids = sorted(set(names) | set(counts), key=lambda value: int(value) if value.isdigit() else value)
    classes = [{"id": value, "name": str(names.get(value, f"class_{value}")), "count": counts[value]} for value in class_ids]
    image_stems = {path.stem for path in images}
    label_stems = {path.stem for path in label_files}
    ground_truth = [{"image": str(path.relative_to(root)), "annotations": parsed_labels.get(path.stem, [])} for path in images]
    return {"format": "YOLO", "task": task, "image_count": len(images), "annotation_count": sum(counts.values()), "missing_label_count": len(image_stems - label_stems), "classes": classes, "manifest": {"yaml": next((str(path.relative_to(root)) for path in yaml_files), None), "image_directories": _folder_roles(root, images), "label_directories": _folder_roles(root, label_files), "warnings": []}, "ground_truth": ground_truth}


def _inspect_classification(root, images):
    counts = Counter()
    for image in images:
        relative = image.relative_to(root)
        parent = relative.parent.name
        if parent.lower() not in {"images", "train", "val", "valid", "test", "content"}:
            counts[parent] += 1
    classes = [{"id": index, "name": name, "count": count} for index, (name, count) in enumerate(sorted(counts.items()))]
    if not images or not classes:
        raise ValueError("Không nhận diện được YOLO, COCO hoặc classification folder dataset.")
    ground_truth = [{"image": str(path.relative_to(root)), "class_name": path.parent.name} for path in images if path.parent.name in counts]
    return {"format": "CLASS_FOLDERS", "task": "CLASSIFICATION", "image_count": len(images), "annotation_count": len(images), "missing_label_count": len(images) - sum(counts.values()), "classes": classes, "manifest": {"image_directories": _folder_roles(root, images), "warnings": []}, "ground_truth": ground_truth}


def _folder_roles(root, paths):
    return sorted({str(path.parent.relative_to(root)) for path in paths})[:100]
