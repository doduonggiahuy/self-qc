from django.conf import settings
from django.db import models


class PlatformProject(models.Model):
    """Platform-owned project manifest, independent from service-local IDs."""
    key = models.SlugField(max_length=120, unique=True)
    name = models.CharField(max_length=160)
    manifest_version = models.PositiveIntegerField(default=1)
    manifest = models.JSONField(default=dict)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]


class ServiceProvisioning(models.Model):
    SERVICE_CHOICES = [
        ("ANNOTATION", "Annotation"),
        ("QUALITY", "Model Quality"),
        ("TRAINING", "Training"),
        ("AI_RULES", "AI Rules"),
    ]
    STATUS_CHOICES = [(value, value.title()) for value in ("PENDING", "PROVISIONING", "READY", "FAILED")]

    project = models.ForeignKey(PlatformProject, on_delete=models.CASCADE, related_name="provisioning")
    service = models.CharField(max_length=16, choices=SERVICE_CHOICES)
    external_id = models.CharField(max_length=160, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="PENDING")
    last_event_id = models.CharField(max_length=120, blank=True)
    error = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["project", "service"], name="unique_project_service_provisioning")]
