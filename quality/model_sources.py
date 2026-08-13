import shutil
import urllib.error
import urllib.request
from pathlib import Path

from django.conf import settings

from .model_artifacts import REQUIRED


def provision_model(model):
    try:
        if model.provider == "LOCAL":
            from .model_artifacts import install_uploaded_artifact
            install_uploaded_artifact(model)
        elif model.provider == "HUGGING_FACE":
            _pull_hugging_face(model)
        elif model.provider == "OLLAMA":
            _pull_ollama(model.source)
        model.status, model.validation_error = "READY", ""
    except Exception as exc:
        model.status, model.validation_error, model.enabled = "ERROR", str(exc), False
    model.save(update_fields=["status", "validation_error", "enabled"])
    return model


def _pull_hugging_face(model):
    from huggingface_hub import snapshot_download
    destination_rel = Path("huggingface") / model.key
    destination = Path(settings.MODEL_ROOT) / destination_rel
    shutil.rmtree(destination, ignore_errors=True)
    snapshot_download(
        repo_id=model.source, local_dir=destination,
        ignore_patterns=["*.bin", "*.msgpack", "*.h5", ".git/*", ".cache/*"],
    )
    present = {item.name for item in destination.iterdir() if item.is_file()}
    required = REQUIRED.get(model.adapter)
    if not required or not any(item <= present for item in required):
        shutil.rmtree(destination, ignore_errors=True)
        raise ValueError("Repo không phải Florence-2/Grounding DINO bundle được hỗ trợ.")
    model.artifact_type, model.artifact_path = "MODEL_BUNDLE", str(destination_rel)
    model.save(update_fields=["artifact_type", "artifact_path"])


def _pull_ollama(tag):
    import json
    endpoint = settings.OLLAMA_URL.rstrip("/") + "/api/pull"
    request = urllib.request.Request(endpoint, data=json.dumps({"model": tag, "stream": False}).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=3600) as response:
            payload = json.load(response)
    except urllib.error.URLError as exc:
        raise ValueError(f"Không kết nối được Ollama: {exc}") from exc
    if payload.get("status") != "success":
        raise ValueError(f"Ollama pull thất bại: {payload}")
