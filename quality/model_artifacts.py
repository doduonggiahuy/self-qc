import shutil
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.exceptions import ValidationError


MAX_FILES = 500
MAX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024 * 1024

REQUIRED = {
    "quality.adapters.Florence2Adapter": [{"config.json", "model.safetensors", "preprocessor_config.json"}],
    "quality.adapters.GroundingDinoAdapter": [{"config.json", "model.safetensors", "preprocessor_config.json"}],
}


def install_uploaded_artifact(model):
    """Validate and install an uploaded single file or ZIP bundle into MODEL_ROOT."""
    if not model.model_file:
        raise ValidationError("Phải upload file model.")
    uploaded_path = Path(model.model_file.path)
    if uploaded_path.suffix.lower() != ".zip":
        if model.adapter != "quality.adapters.YoloWorldAdapter" or uploaded_path.suffix.lower() != ".pt":
            model.artifact_type = "SINGLE_FILE"
        model.artifact_path = str(uploaded_path.relative_to(settings.MODEL_ROOT))
        model.validation_error = ""
        model.save(update_fields=["artifact_type", "artifact_path", "validation_error"])
        return

    destination_rel = Path("bundles") / f"{model.key}-{uuid.uuid4().hex[:12]}"
    destination = Path(settings.MODEL_ROOT) / destination_rel
    temporary = Path(settings.MODEL_ROOT) / ".extracting" / uuid.uuid4().hex
    temporary.mkdir(parents=True, exist_ok=False)
    try:
        with zipfile.ZipFile(uploaded_path) as archive:
            members = archive.infolist()
            if len(members) > MAX_FILES:
                raise ValidationError(f"Bundle có quá nhiều file (tối đa {MAX_FILES}).")
            total = sum(item.file_size for item in members)
            if total > MAX_UNCOMPRESSED_BYTES:
                raise ValidationError("Bundle sau giải nén vượt quá 20 GB.")
            for item in members:
                path = PurePosixPath(item.filename)
                is_symlink = (item.external_attr >> 16) & 0o170000 == 0o120000
                if path.is_absolute() or ".." in path.parts or is_symlink:
                    raise ValidationError(f"ZIP chứa đường dẫn không an toàn: {item.filename}")
            archive.extractall(temporary)

        root = _bundle_root(temporary)
        present = {item.name for item in root.iterdir() if item.is_file()}
        requirements = REQUIRED.get(model.adapter)
        if not requirements or not any(required <= present for required in requirements):
            raise ValidationError(
                "Bundle thiếu config.json, model.safetensors hoặc preprocessor_config.json, "
                "hoặc adapter không hỗ trợ bundle."
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(root), destination)
        model.artifact_type = "MODEL_BUNDLE"
        model.artifact_path = str(destination_rel)
        model.validation_error = ""
        model.save(update_fields=["artifact_type", "artifact_path", "validation_error"])
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
        model.model_file.storage.delete(model.model_file.name)
        model.model_file = ""
        model.save(update_fields=["model_file"])


def remove_artifact(model, keep_path=None):
    reference = Path(model.runtime_reference) if (model.artifact_path or model.model_file) else None
    if not reference or (keep_path and reference == Path(keep_path)):
        return
    root = Path(settings.MODEL_ROOT).resolve()
    resolved = reference.resolve()
    if root not in resolved.parents:
        return
    if resolved.is_dir():
        shutil.rmtree(resolved)
    elif resolved.exists():
        resolved.unlink()


def _bundle_root(temporary):
    visible = [item for item in temporary.iterdir() if item.name != "__MACOSX"]
    if len(visible) == 1 and visible[0].is_dir():
        return visible[0]
    return temporary
