import shutil
import json
from pathlib import Path

from django.conf import settings

def provision_model(model):
    try:
        if model.provider == "LOCAL":
            from .model_artifacts import install_uploaded_artifact
            install_uploaded_artifact(model)
        elif model.provider == "HUGGING_FACE":
            _pull_hugging_face(model)
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
        ignore_patterns=[".git/*", ".cache/*"],
    )
    model.adapter, model.task = _adapter_from_huggingface_metadata(destination)
    if model.adapter == "quality.adapters.UnavailableAdapter":
        # The artifact is valid storage even when this deployment has no
        # execution adapter for its architecture yet.
        model.enabled = False
    model.artifact_type, model.artifact_path = "MODEL_BUNDLE", str(destination_rel)
    model.save(update_fields=["artifact_type", "artifact_path", "adapter", "task", "enabled"])


def _adapter_from_huggingface_metadata(directory):
    config_path = Path(directory) / "config.json"
    try:
        config = json.loads(config_path.read_text())
    except (OSError, json.JSONDecodeError):
        return "quality.adapters.UnavailableAdapter", "VISUAL_GROUNDING"
    if not isinstance(config, dict):
        return "quality.adapters.UnavailableAdapter", "VISUAL_GROUNDING"

    architectures = config.get("architectures") or []
    if not isinstance(architectures, (list, tuple)):
        architectures = [architectures]
    signals = [str(config.get("model_type", "")), *[str(value) for value in architectures]]
    normalized = " ".join(signals).lower().replace("_", "-")
    if "florence" in normalized:
        return "quality.adapters.Florence2Adapter", "VISUAL_GROUNDING"
    if "grounding-dino" in normalized or "groundingdino" in normalized:
        return "quality.adapters.GroundingDinoAdapter", "OPEN_VOCAB_DETECTION"
    return "quality.adapters.UnavailableAdapter", "VISUAL_GROUNDING"
