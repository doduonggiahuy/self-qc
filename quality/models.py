import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible
from django.db import models

from annotations.models import Project


@deconstructible
class ModelStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=settings.MODEL_ROOT)


model_storage = ModelStorage()


def validate_model_file(value):
    allowed = {".pt", ".pth", ".onnx", ".engine", ".torchscript", ".zip"}
    if Path(value.name).suffix.lower() not in allowed:
        raise ValidationError(f"File model phải có định dạng: {', '.join(sorted(allowed))}.")


class GroundTruthRelease(models.Model):
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("FROZEN", "Frozen"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="gt_releases")
    version = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="DRAFT")
    coverage = models.CharField(
        max_length=16,
        choices=[("partial", "Partial"), ("exhaustive", "Exhaustive")],
    )
    video_sha256 = models.CharField(max_length=64)
    annotation_count = models.PositiveIntegerField(default=0)
    manifest = models.JSONField(default=dict)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    frozen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "version"], name="unique_gt_release_version"),
        ]
        ordering = ["-version"]

    def __str__(self):
        return f"{self.project} GT v{self.version}"


class GroundTruthItem(models.Model):
    release = models.ForeignKey(GroundTruthRelease, on_delete=models.CASCADE, related_name="items")
    annotation_type = models.CharField(max_length=32, default="bounding_box")
    frame_index = models.PositiveIntegerField(db_index=True)
    timestamp_ms = models.PositiveBigIntegerField(null=True, blank=True)
    label = models.CharField(max_length=80)
    payload = models.JSONField()
    source_annotation_id = models.PositiveBigIntegerField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["release", "frame_index"])]
        ordering = ["frame_index", "id"]


class Target(models.Model):
    KIND_CHOICES = [
        ("TRITON", "Triton"),
        ("KAFKA", "Kafka"),
        ("OFFLINE", "Offline"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="quality_targets")
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    config = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "name"], name="unique_project_target_name"),
        ]

    def __str__(self):
        return self.name


class InferenceModel(models.Model):
    PROVIDER_CHOICES = [("LOCAL", "Upload local"), ("HUGGING_FACE", "Hugging Face"), ("OLLAMA", "Ollama")]
    STATUS_CHOICES = [("PENDING", "Pending"), ("READY", "Ready"), ("ERROR", "Error")]
    ARTIFACT_CHOICES = [("SINGLE_FILE", "Single weight file"), ("MODEL_BUNDLE", "Model bundle")]
    TASK_CHOICES = [
        ("OPEN_VOCAB_DETECTION", "Open-vocabulary detection"),
        ("VISUAL_GROUNDING", "Visual grounding"),
        ("SEGMENTATION", "Segmentation"),
        ("VIDEO_REASONING", "Video reasoning"),
    ]
    key = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=160)
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default="LOCAL")
    source = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="PENDING")
    task = models.CharField(max_length=32, choices=TASK_CHOICES)
    model_file = models.FileField(storage=model_storage, upload_to="registry/", validators=[validate_model_file])
    artifact_type = models.CharField(max_length=20, choices=ARTIFACT_CHOICES, default="SINGLE_FILE")
    artifact_path = models.CharField(max_length=500, blank=True)
    validation_error = models.TextField(blank=True)
    adapter = models.CharField(max_length=120, help_text="Tên adapter trong execution plane")
    description = models.TextField(blank=True)
    license_name = models.CharField(max_length=120, blank=True)
    commercial_use = models.BooleanField(default=False)
    config_schema = models.JSONField(default=dict, blank=True)
    default_config = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def runtime_reference(self):
        if self.provider == "OLLAMA":
            return self.source
        if self.artifact_path:
            return str(Path(settings.MODEL_ROOT) / self.artifact_path)
        return self.model_file.path

    @property
    def file_size(self):
        try:
            reference = Path(self.runtime_reference)
            if reference.is_dir():
                return sum(item.stat().st_size for item in reference.rglob("*") if item.is_file())
            return reference.stat().st_size
        except (FileNotFoundError, OSError, ValueError):
            return None

    @property
    def artifact_name(self):
        return self.artifact_path or (self.model_file.name if self.model_file else "")

    @property
    def is_selectable(self):
        supported = {
            "quality.adapters.YoloWorldAdapter",
            "quality.adapters.Florence2Adapter",
            "quality.adapters.GroundingDinoAdapter",
            "quality.adapters.OllamaVisionAdapter",
        }
        if self.provider == "OLLAMA":
            return self.enabled and self.status == "READY" and self.adapter == "quality.adapters.OllamaVisionAdapter" and bool(self.source)
        if not self.artifact_path and not self.model_file:
            return False
        reference = Path(self.runtime_reference)
        compatible = (
            self.adapter == "quality.adapters.YoloWorldAdapter" and reference.is_file() and reference.suffix.lower() == ".pt"
        ) or (
            self.adapter in {"quality.adapters.Florence2Adapter", "quality.adapters.GroundingDinoAdapter"}
            and self.artifact_type == "MODEL_BUNDLE" and reference.is_dir()
        )
        return (
            self.enabled
            and self.status == "READY"
            and self.adapter in supported
            and not self.validation_error
            and compatible
        )


class UserInferencePreference(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="inference_preference")
    model = models.ForeignKey(InferenceModel, null=True, blank=True, on_delete=models.SET_NULL, related_name="selected_by")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user}: {self.model or 'system default'}"


class TestCase(models.Model):
    KIND_CHOICES = [
        ("GT_VALIDATION", "GT validation"),
        ("DETECTION", "Detection model"),
        ("CLASSIFICATION", "Classification model"),
        ("POSE", "Pose model"),
        ("RULE", "Logic rule"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="test_cases")
    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=24, choices=KIND_CHOICES, default="GT_VALIDATION")
    version = models.PositiveIntegerField(default=1)
    ground_truth_release = models.ForeignKey(
        GroundTruthRelease, null=True, blank=True, on_delete=models.PROTECT, related_name="test_cases"
    )
    target = models.ForeignKey(Target, null=True, blank=True, on_delete=models.PROTECT, related_name="test_cases")
    config = models.JSONField(default=dict, blank=True)
    assertions = models.JSONField(default=list, blank=True)
    enabled = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "name", "version"], name="unique_test_case_version"),
        ]
        ordering = ["name", "-version"]

    def __str__(self):
        return f"{self.name} v{self.version}"


class TestRun(models.Model):
    STATUS_CHOICES = [
        ("QUEUED", "Queued"),
        ("RUNNING", "Running"),
        ("PASSED", "Passed"),
        ("FAILED", "Failed"),
        ("ERROR", "Error"),
        ("CANCELLED", "Cancelled"),
        ("INCONCLUSIVE", "Inconclusive"),
    ]

    test_case = models.ForeignKey(TestCase, on_delete=models.PROTECT, related_name="runs")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="QUEUED", db_index=True)
    correlation_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    input_snapshot = models.JSONField(default=dict)
    metrics = models.JSONField(default=dict)
    assertion_results = models.JSONField(default=list)
    error = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
