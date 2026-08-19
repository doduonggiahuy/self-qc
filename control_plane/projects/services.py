from django.db import transaction

from control_plane.events import envelope

from .models import PlatformProject, ServiceProvisioning


SERVICES = ("ANNOTATION", "QUALITY", "TRAINING", "AI_RULES")


def validate_manifest(manifest):
    """Small, stable validation seam for JSON/YAML manifests submitted by Platform UI."""
    if not isinstance(manifest, dict):
        raise ValueError("Project manifest phải là object JSON/YAML.")
    for key in ("annotation", "quality", "training", "ai_rules"):
        if key in manifest and not isinstance(manifest[key], dict):
            raise ValueError(f"'{key}' phải là object cấu hình.")


@transaction.atomic
def apply_manifest(*, key, name, manifest, user):
    """Persist the Platform source of truth and queue all service provisioning."""
    validate_manifest(manifest)
    project, created = PlatformProject.objects.get_or_create(
        key=key,
        defaults={"name": name, "manifest": manifest, "created_by": user},
    )
    if not created:
        project.name = name
        project.manifest = manifest
        project.manifest_version += 1
        project.save(update_fields=["name", "manifest", "manifest_version", "updated_at"])

    events = []
    for service in SERVICES:
        state, _ = ServiceProvisioning.objects.update_or_create(
            project=project,
            service=service,
            defaults={"status": "PENDING", "error": ""},
        )
        event = envelope(
            "platform.project.provision.requested",
            project.key,
            {"project_key": project.key, "manifest_version": project.manifest_version, "service": service},
            producer="platform-control",
        )
        state.last_event_id = event["event_id"]
        state.save(update_fields=["last_event_id", "updated_at"])
        events.append(event)
    return project, events
