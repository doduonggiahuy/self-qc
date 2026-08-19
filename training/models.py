from django.conf import settings
from django.db import models


class TrainingDataset(models.Model):
    """Immutable reference to an annotation/dataset artifact consumed by training."""
    key = models.SlugField(max_length=120, unique=True)
    source_release_id = models.CharField(max_length=120, blank=True)
    artifact_uri = models.CharField(max_length=500)
    manifest = models.JSONField(default=dict, blank=True)
    checksum = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class TrainingRun(models.Model):
    STATUS_CHOICES = [(value, value.title()) for value in ("PENDING", "RUNNING", "COMPLETED", "FAILED")]
    dataset = models.ForeignKey(TrainingDataset, on_delete=models.PROTECT, related_name="runs")
    name = models.CharField(max_length=160)
    config = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="PENDING")
    artifact_uri = models.CharField(max_length=500, blank=True)
    error = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
