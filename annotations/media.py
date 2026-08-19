import re
import stat
import uuid
import zipfile
from pathlib import Path, PurePosixPath

import cv2
from django.conf import settings
from django.core.files.base import ContentFile, File
from django.core.files.storage import default_storage

from .models import AnnotationJob, LabelClass, Project
from .video import probe, read_frame


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


def _natural_key(value):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]


def _image_meta(storage_name):
    frame = cv2.imread(default_storage.path(storage_name), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError(f"Không đọc được ảnh {Path(storage_name).name}")
    height, width = frame.shape[:2]
    return {"width": width, "height": height, "fps": 1.0}


def _copy_images(task, sources, dataset_id):
    manifest = []
    for index, (display_name, source) in enumerate(sorted(sources, key=lambda item: _natural_key(item[0]))):
        suffix = Path(display_name).suffix.lower()
        storage_name = f"annotation-data/task-{task.pk}/{dataset_id}/frames/{index:08d}{suffix}"
        manifest.append(default_storage.save(storage_name, File(source)))
    if not manifest:
        raise ValueError("Không tìm thấy ảnh hợp lệ trong data đã chọn.")
    return manifest


def _zip_images(task, uploaded, dataset_id):
    uploaded.seek(0)
    with zipfile.ZipFile(uploaded) as archive:
        candidates = []
        total_bytes = 0
        for member in archive.infolist():
            path = PurePosixPath(member.filename)
            if member.is_dir() or path.name.startswith(".") or "__MACOSX" in path.parts:
                continue
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("ZIP chứa đường dẫn không an toàn.")
            if stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError("ZIP chứa symbolic link, hiện chưa được hỗ trợ.")
            if member.flag_bits & 0x1:
                raise ValueError("ZIP có file mã hóa, hiện chưa được hỗ trợ.")
            if Path(path.name).suffix.lower() in IMAGE_EXTENSIONS:
                candidates.append(member)
                total_bytes += member.file_size
        if len(candidates) > settings.DATASET_MAX_ARCHIVE_FILES or total_bytes > settings.DATASET_MAX_EXTRACTED_BYTES:
            raise ValueError("ZIP vượt giới hạn số file hoặc dung lượng giải nén.")
        manifest = []
        for index, member in enumerate(sorted(candidates, key=lambda item: _natural_key(item.filename))):
            suffix = Path(member.filename).suffix.lower()
            storage_name = f"annotation-data/task-{task.pk}/{dataset_id}/frames/{index:08d}{suffix}"
            with archive.open(member) as source:
                manifest.append(default_storage.save(storage_name, File(source)))
        if not manifest:
            raise ValueError("Không tìm thấy ảnh hợp lệ trong ZIP.")
        return manifest


def _snapshot_labels(project, task):
    for label in task.client_project.labels.all():
        LabelClass.objects.create(
            project=project, name=label.name, label_type=label.label_type,
            confidence=label.confidence, color=label.color,
            enabled=label.enabled, order=label.order,
        )


def _create_sequence(task, user, name, manifest, coverage):
    meta = _image_meta(manifest[0])
    project = Project.objects.create(
        name=name, owner=user, client_project=task.client_project,
        annotation_task=task, coverage=coverage, media_kind="IMAGE_SEQUENCE",
        frame_manifest=manifest, frame_count=len(manifest), **meta,
    )
    _snapshot_labels(project, task)
    return AnnotationJob.objects.create(
        task=task, video=project, assignee=task.assignees.first(), reviewer=task.reviewers.first(),
        start_frame=0, stop_frame=len(manifest) - 1,
    )


def ingest_task_uploads(task, user, uploads, *, name=None, coverage="partial"):
    uploads = list(uploads)
    if not uploads:
        return []
    images = [(item.name, item) for item in uploads if Path(item.name).suffix.lower() in IMAGE_EXTENSIONS]
    videos = [item for item in uploads if Path(item.name).suffix.lower() in VIDEO_EXTENSIONS]
    archives = [item for item in uploads if Path(item.name).suffix.lower() == ".zip"]
    unsupported = [item.name for item in uploads if Path(item.name).suffix.lower() not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | {".zip"}]
    if unsupported:
        raise ValueError(f"Định dạng không hỗ trợ: {', '.join(unsupported)}")
    # Same invariant as CVAT: one unique source (video/archive), or many images.
    if len(videos) + len(archives) > 1 or ((videos or archives) and images):
        raise ValueError("Một Task chỉ nhận một video, một ZIP ảnh, hoặc nhiều ảnh/folder; không trộn các loại data.")
    if images:
        dataset_id = uuid.uuid4().hex
        manifest = _copy_images(task, images, dataset_id)
        return [_create_sequence(task, user, name or "Image sequence", manifest, coverage)]
    if archives:
        uploaded = archives[0]
        manifest = _zip_images(task, uploaded, uuid.uuid4().hex)
        return [_create_sequence(task, user, name or Path(uploaded.name).stem, manifest, coverage)]

    uploaded = videos[0]
    project = Project.objects.create(
        name=name or Path(uploaded.name).stem, video=uploaded, owner=user,
        client_project=task.client_project, annotation_task=task, coverage=coverage,
        media_kind="IMAGE_SEQUENCE",
    )
    dataset_id = uuid.uuid4().hex
    manifest = []
    try:
        meta = probe(project.video.path)
        capture = cv2.VideoCapture(project.video.path)
        try:
            index = 0
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                encoded, payload = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                if not encoded:
                    raise ValueError(f"Không encode được frame {index}")
                storage_name = f"annotation-data/task-{task.pk}/{dataset_id}/frames/{index:08d}.jpg"
                manifest.append(default_storage.save(storage_name, ContentFile(payload.tobytes())))
                index += 1
        finally:
            capture.release()
        if not manifest:
            raise ValueError("Video không có frame hợp lệ.")
        project.width = meta["width"]
        project.height = meta["height"]
        project.fps = meta["fps"]
        project.frame_count = len(manifest)
        project.frame_manifest = manifest
        project.save(update_fields=["width", "height", "fps", "frame_count", "frame_manifest", "updated_at"])
        _snapshot_labels(project, task)
        return [AnnotationJob.objects.create(
            task=task, video=project, assignee=task.assignees.first(), reviewer=task.reviewers.first(),
            start_frame=0, stop_frame=len(manifest) - 1,
        )]
    except Exception:
        for storage_name in manifest:
            default_storage.delete(storage_name)
        project.video.delete(save=False)
        project.delete()
        raise


def read_project_frame(project, frame_index):
    if project.media_kind == "IMAGE_SEQUENCE":
        try:
            storage_name = project.frame_manifest[int(frame_index)]
        except (IndexError, TypeError, ValueError):
            raise ValueError(f"Không đọc được frame {frame_index}")
        frame = cv2.imread(default_storage.path(storage_name), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError(f"Không đọc được frame {frame_index}")
        return frame
    return read_frame(project.video.path, frame_index)


def delete_project_media(project):
    if project.video:
        project.video.delete(save=False)
    for storage_name in project.frame_manifest or []:
        default_storage.delete(storage_name)
