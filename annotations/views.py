import hashlib
import io
import json
import logging
import os

import cv2
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import ClientProjectForm, ProjectForm, RuleForm
from .inference import predict
from .models import BoxAnnotation, ClientProject, LabelClass, Project, Rule
from .video import probe, read_frame
from quality.models import InferenceModel, UserInferencePreference

logger = logging.getLogger(__name__)


def _can_edit(user, project):
    return user.is_superuser or project.owner_id == user.id or user.has_perm("annotations.edit_all_projects")


def _project(user, pk, edit=False):
    obj = get_object_or_404(Project, pk=pk)
    if edit and not _can_edit(user, obj):
        raise PermissionDenied
    return obj


def _client_project(user, pk):
    obj = get_object_or_404(ClientProject, pk=pk)
    if not (user.is_superuser or obj.owner_id == user.id or user.has_perm("annotations.edit_all_projects")):
        raise PermissionDenied
    return obj


def _box_json(box):
    return {
        "id": box.id,
        "class_id": box.label_class_id,
        "class_name": box.label_class.name,
        "color": box.label_class.color,
        "bbox": [box.x1, box.y1, box.x2, box.y2],
        "confidence": box.confidence,
        "source": box.source,
        "status": box.review_status,
        "prompt": box.prompt,
    }


@login_required
def project_list(request):
    projects = ClientProject.objects.prefetch_related("videos", "rules")
    if not (request.user.has_perm("annotations.edit_all_projects") or request.user.is_superuser):
        projects = projects.filter(owner=request.user)
    return render(request, "annotations/project_list.html", {"projects": projects})


@login_required
def ground_truth_list(request):
    videos = Project.objects.select_related("client_project", "owner").prefetch_related("classes", "rules")
    if not (request.user.has_perm("annotations.edit_all_projects") or request.user.is_superuser):
        videos = videos.filter(owner=request.user)
    return render(request, "annotations/ground_truth_list.html", {"videos": videos})


@login_required
def client_project_create(request):
    form = ClientProjectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        item.owner = request.user
        item.save()
        return redirect("client-project-detail", pk=item.pk)
    return render(request, "annotations/client_project_form.html", {"form": form})


@login_required
def client_project_detail(request, pk):
    item = _client_project(request.user, pk)
    rule_form = RuleForm(item, request.POST or None)
    if request.method == "POST" and rule_form.is_valid():
        rule = rule_form.save(commit=False)
        rule.client_project = item
        rule.save()
        rule_form.save_m2m()
        return redirect("client-project-detail", pk=item.pk)
    return render(request, "annotations/client_project_detail.html", {"client_project": item, "rule_form": rule_form})


@login_required
@require_POST
def client_project_delete(request, pk):
    item = _client_project(request.user, pk)
    item.delete()
    return redirect("project-list")


@login_required
@require_POST
def rule_delete(request, pk, rule_pk):
    item = _client_project(request.user, pk)
    get_object_or_404(item.rules, pk=rule_pk).delete()
    return redirect("client-project-detail", pk=item.pk)


@login_required
@require_POST
def video_delete(request, pk, video_pk):
    item = _client_project(request.user, pk)
    video = get_object_or_404(item.videos, pk=video_pk)
    video.video.delete(save=False)
    video.delete()
    return redirect("client-project-detail", pk=item.pk)


@login_required
def project_create(request):
    client_pk = request.GET.get("client") or request.POST.get("client_project")
    client = _client_project(request.user, client_pk) if client_pk else None
    form = ProjectForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            project = form.save(commit=False)
            project.owner = request.user
            project.client_project = client
            project.save()
            try:
                meta = probe(project.video.path)
            except Exception as exc:
                project.video.delete(save=False)
                project.delete()
                form.add_error("video", str(exc))
            else:
                Project.objects.filter(pk=project.pk).update(**meta)
                colors = ["#00e676", "#40c4ff", "#ffea00", "#ff5252", "#e040fb"]
                for index, line in enumerate(form.cleaned_data["classes"].splitlines()):
                    if not line.strip():
                        continue
                    parts = [part.strip() for part in line.split("|")]
                    name = parts[0]
                    prompt = parts[1] if len(parts) > 1 and parts[1] else name
                    try:
                        confidence = max(0.01, min(1.0, float(parts[2]))) if len(parts) > 2 else 0.25
                    except ValueError:
                        confidence = 0.25
                    LabelClass.objects.create(project=project, name=name, prompt=prompt, confidence=confidence, color=colors[index % len(colors)], order=index)
                return redirect("annotate", pk=project.pk)
    return render(request, "annotations/project_form.html", {"form": form, "client_project": client})


@login_required
def annotate(request, pk):
    project = _project(request.user, pk, edit=True)
    selectable_models = [model for model in InferenceModel.objects.filter(enabled=True) if model.is_selectable]
    preference = UserInferencePreference.objects.filter(user=request.user).select_related("model").first()
    return render(request, "annotations/annotate.html", {
        "project": project, "classes": project.classes.all(), "inference_models": selectable_models,
        "selected_inference_model_id": preference.model_id if preference else None,
    })


@login_required
def frame_image(request, pk, frame_index):
    project = _project(request.user, pk)
    if frame_index >= project.frame_count:
        raise Http404
    frame = read_frame(project.video.path, frame_index)
    ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise Http404
    return FileResponse(iter([encoded.tobytes()]), content_type="image/jpeg")


@login_required
def frame_data(request, pk, frame_index):
    project = _project(request.user, pk)
    boxes = project.boxes.filter(frame_index=frame_index).select_related("label_class")
    return JsonResponse({"boxes": [_box_json(box) for box in boxes]})


@login_required
@require_POST
def infer_frame(request, pk, frame_index):
    project = _project(request.user, pk, edit=True)
    classes = list(project.classes.filter(enabled=True))
    if not classes:
        return JsonResponse({"error": "Không có class nào được bật để inference."}, status=400)
    if os.getenv("INFERENCE_EXECUTION") == "worker":
        try:
            preference = UserInferencePreference.objects.filter(user=request.user).first()
            from quality.tasks import infer_annotation_frame
            payload = infer_annotation_frame.delay(project.pk, frame_index, preference.model_id if preference else None).get(timeout=3600)
            return JsonResponse(payload)
        except Exception as exc:
            logger.exception("Worker inference failed for project=%s frame=%s", project.pk, frame_index)
            return JsonResponse({"error": f"Inference worker thất bại: {exc}"}, status=500)
    try:
        frame = read_frame(project.video.path, frame_index)
        preference = UserInferencePreference.objects.filter(user=request.user).select_related("model").first()
        selected_model = preference.model if preference and preference.model and preference.model.is_selectable else None
        proposals = predict(frame, classes, selected_model)
    except Exception as exc:
        logger.exception("Inference failed for project=%s frame=%s", project.pk, frame_index)
        return JsonResponse({"error": f"Inference thất bại: {exc}"}, status=500)
    # Preserve all human-reviewed GT; only replace unreviewed proposals.
    project.boxes.filter(frame_index=frame_index, review_status="PREDICTED").delete()
    created = [BoxAnnotation.objects.create(
        project=project, frame_index=frame_index,
        label_class=item["label_class"], x1=item["bbox"][0], y1=item["bbox"][1],
        x2=item["bbox"][2], y2=item["bbox"][3], confidence=item["confidence"],
        source="YOLO_WORLD", review_status="PREDICTED", prompt=item["prompt"],
        created_by=request.user, updated_by=request.user,
    ) for item in proposals]
    return JsonResponse({"boxes": [_box_json(box) for box in created]})


@login_required
@require_POST
def save_frame(request, pk, frame_index):
    project = _project(request.user, pk, edit=True)
    payload = json.loads(request.body)
    with transaction.atomic():
        keep = []
        for raw in payload.get("boxes", []):
            box_id = raw.get("id")
            box = project.boxes.filter(pk=box_id, frame_index=frame_index).first() if box_id else None
            if box is None:
                box = BoxAnnotation(project=project, frame_index=frame_index, created_by=request.user, source="MANUAL")
            box.label_class = get_object_or_404(project.classes, pk=raw["class_id"])
            box.x1, box.y1, box.x2, box.y2 = raw["bbox"]
            box.review_status = raw.get("status", "EDITED")
            box.updated_by = request.user
            if box.source == "YOLO_WORLD" and box.review_status == "PREDICTED":
                box.review_status = "EDITED"
            box.save()
            keep.append(box.pk)
        project.boxes.filter(frame_index=frame_index).exclude(pk__in=keep).delete()
        project.current_frame = frame_index
        project.save(update_fields=["current_frame", "updated_at"])
    return JsonResponse({"ok": True})


@login_required
@require_POST
def save_classes(request, pk):
    project = _project(request.user, pk, edit=True)
    payload = json.loads(request.body)
    with transaction.atomic():
        deleted_ids = [int(value) for value in payload.get("deleted_ids", []) if str(value).isdigit()]
        if deleted_ids:
            deleting = project.classes.filter(pk__in=deleted_ids)
            project.boxes.filter(label_class__in=deleting).delete()
            deleting.delete()
        for raw in payload.get("classes", []):
            item_id = raw.get("id")
            item = get_object_or_404(project.classes, pk=item_id) if item_id else LabelClass(project=project, order=project.classes.count())
            name = str(raw.get("name", "")).strip()
            prompt = str(raw.get("prompt", "")).strip()
            if not name or not prompt:
                return JsonResponse({"error": "Class và prompt không được để trống"}, status=400)
            item.name = name
            item.prompt = prompt
            item.enabled = bool(raw.get("enabled", True))
            try:
                item.confidence = max(0.01, min(1.0, float(raw.get("confidence", 0.25))))
            except (TypeError, ValueError):
                return JsonResponse({"error": "Confidence phải là số từ 0.01 đến 1.00"}, status=400)
            if not item.color:
                colors = ["#00e676", "#40c4ff", "#ffea00", "#ff5252", "#e040fb"]
                item.color = colors[project.classes.count() % len(colors)]
            item.save()
    return JsonResponse({"ok": True})


@login_required
def export_jsonl(request, pk):
    project = _project(request.user, pk)
    approved = project.boxes.filter(review_status__in=["APPROVED", "EDITED"]).select_related("label_class").order_by("frame_index", "id")
    grouped = {}
    for box in approved:
        grouped.setdefault(box.frame_index, []).append({
            "id": str(box.id), "class": box.label_class.name,
            "bbox": [box.x1, box.y1, box.x2, box.y2],
        })
    records = [json.dumps({
        "video": project.video.name, "frame_index": frame,
        "timestamp": frame / project.fps if project.fps else None,
        "objects": objects,
    }, ensure_ascii=False) for frame, objects in grouped.items()]
    content = ("\n".join(records) + "\n").encode()
    digest = hashlib.sha256()
    with open(project.video.path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    response = FileResponse(io.BytesIO(content), content_type="application/x-ndjson")
    response["Content-Disposition"] = f'attachment; filename="project-{project.pk}-gt.jsonl"'
    response["X-Video-SHA256"] = digest.hexdigest()
    return response
