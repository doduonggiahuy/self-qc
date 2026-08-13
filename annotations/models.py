from django.conf import settings
from django.db import models


class ClientProject(models.Model):
    """Customer-level workspace containing reusable videos and business rules."""
    STATUS_CHOICES = [("ACTIVE", "Active"), ("ARCHIVED", "Archived")]

    name = models.CharField(max_length=160)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="client_projects")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="ACTIVE")
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name


class Project(models.Model):
    STATUS_CHOICES = [("DRAFT", "Draft"), ("IN_REVIEW", "In review"), ("DONE", "Done")]

    name = models.CharField(max_length=160)
    client_project = models.ForeignKey(ClientProject, null=True, blank=True, on_delete=models.CASCADE, related_name="videos")
    video = models.FileField(upload_to="videos/%Y/%m/")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="qc_projects")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="DRAFT")
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    fps = models.FloatField(default=0)
    frame_count = models.PositiveIntegerField(default=0)
    coverage = models.CharField(max_length=16, choices=[("partial", "Partial"), ("exhaustive", "Exhaustive")], default="partial")
    current_frame = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        permissions = [
            ("edit_all_projects", "Can edit every QC project"),
            ("review_annotations", "Can approve or reject annotations"),
        ]
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name


class Rule(models.Model):
    client_project = models.ForeignKey(ClientProject, on_delete=models.CASCADE, related_name="rules")
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    enabled = models.BooleanField(default=True)
    videos = models.ManyToManyField(Project, blank=True, related_name="rules")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["client_project", "name"], name="unique_rule_per_client_project")]

    def __str__(self):
        return self.name


class LabelClass(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="classes")
    name = models.CharField(max_length=80)
    prompt = models.CharField(max_length=240)
    color = models.CharField(max_length=7, default="#00e676")
    enabled = models.BooleanField(default=True)
    confidence = models.FloatField(default=0.25)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [("project", "name")]
        ordering = ["order", "id"]


class BoxAnnotation(models.Model):
    REVIEW_CHOICES = [("PREDICTED", "Predicted"), ("APPROVED", "Approved"), ("REJECTED", "Rejected"), ("EDITED", "Edited")]
    SOURCE_CHOICES = [("YOLO_WORLD", "YOLO-World"), ("MANUAL", "Manual")]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="boxes")
    frame_index = models.PositiveIntegerField(db_index=True)
    label_class = models.ForeignKey(LabelClass, on_delete=models.PROTECT, related_name="boxes")
    x1 = models.FloatField()
    y1 = models.FloatField()
    x2 = models.FloatField()
    y2 = models.FloatField()
    confidence = models.FloatField(null=True, blank=True)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default="MANUAL")
    review_status = models.CharField(max_length=16, choices=REVIEW_CHOICES, default="PREDICTED")
    prompt = models.CharField(max_length=240, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="created_qc_boxes")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="updated_qc_boxes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["project", "frame_index"], name="annotation_project_238bcb_idx")]
