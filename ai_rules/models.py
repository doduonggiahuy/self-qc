from django.conf import settings
from django.db import models


class RuleDefinition(models.Model):
    key = models.SlugField(max_length=120, unique=True)
    name = models.CharField(max_length=160)
    version = models.PositiveIntegerField(default=1)
    rule_type = models.CharField(max_length=64)
    config = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)


class RuleRun(models.Model):
    STATUS_CHOICES = [(value, value.title()) for value in ("PENDING", "RUNNING", "COMPLETED", "FAILED")]
    rule = models.ForeignKey(RuleDefinition, on_delete=models.PROTECT, related_name="runs")
    input_artifact_uri = models.CharField(max_length=500)
    input_event_id = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="PENDING")
    result_artifact_uri = models.CharField(max_length=500, blank=True)
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
