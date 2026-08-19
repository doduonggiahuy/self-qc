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
    MEDIA_KIND_CHOICES = [("VIDEO", "Video"), ("IMAGE_SEQUENCE", "Image sequence")]

    name = models.CharField(max_length=160)
    client_project = models.ForeignKey(ClientProject, null=True, blank=True, on_delete=models.CASCADE, related_name="videos")
    # A media asset belongs to one annotation task. ClientProject is retained
    # temporarily for backwards-compatible data migration only.
    annotation_task = models.ForeignKey("AnnotationTask", null=True, blank=True, on_delete=models.CASCADE, related_name="videos")
    video = models.FileField(upload_to="videos/%Y/%m/", blank=True)
    media_kind = models.CharField(max_length=20, choices=MEDIA_KIND_CHOICES, default="VIDEO")
    frame_manifest = models.JSONField(default=list, blank=True)
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["client_project", "name"], name="unique_rule_per_client_project")]

    def __str__(self):
        return self.name


class AnnotationTask(models.Model):
    STATUS_CHOICES = [("DRAFT", "Draft"), ("ASSIGNED", "Assigned"), ("IN_PROGRESS", "In progress"), ("IN_REVIEW", "In review"), ("COMPLETED", "Completed")]

    client_project = models.ForeignKey(ClientProject, on_delete=models.CASCADE, related_name="annotation_tasks")
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    rules = models.ManyToManyField(Rule, blank=True, related_name="annotation_tasks")
    assignees = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="assigned_annotation_tasks")
    reviewers = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="review_annotation_tasks")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="DRAFT")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="created_annotation_tasks")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [models.UniqueConstraint(fields=["client_project", "name"], name="unique_annotation_task_per_project")]

    def __str__(self):
        return self.name


class LabelClass(models.Model):
    TYPE_CHOICES = [
        ("rectangle", "Detection / Bounding box"),
        ("skeleton", "Skeleton pose"),
        ("tag", "Tag"),
    ]
    # CVAT model: labels are owned by Project and inherited by its Tasks.
    client_project = models.ForeignKey(ClientProject, null=True, blank=True, on_delete=models.CASCADE, related_name="labels")
    # Legacy snapshot on an already-uploaded video; new labels are project-level.
    project = models.ForeignKey(Project, null=True, blank=True, on_delete=models.CASCADE, related_name="classes")
    name = models.CharField(max_length=80)
    label_type = models.CharField(max_length=16, choices=TYPE_CHOICES, default="rectangle")
    color = models.CharField(max_length=7, default="#00e676")
    enabled = models.BooleanField(default=True)
    confidence = models.FloatField(default=0.25)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["client_project", "name"], condition=models.Q(project__isnull=True), name="unique_label_per_client_project"),
            models.UniqueConstraint(fields=["project", "name"], condition=models.Q(client_project__isnull=True), name="unique_label_per_video_snapshot"),
        ]


class LabelAttribute(models.Model):
    INPUT_CHOICES = [(x, x.title()) for x in ("select", "radio", "checkbox", "text", "number")]
    label = models.ForeignKey(LabelClass, on_delete=models.CASCADE, related_name="attributes")
    name = models.CharField(max_length=80)
    input_type = models.CharField(max_length=16, choices=INPUT_CHOICES, default="select")
    values = models.JSONField(default=list, blank=True)
    default_value = models.CharField(max_length=160, blank=True)
    mutable = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        constraints = [models.UniqueConstraint(fields=["label", "name"], name="unique_attribute_per_label")]


class SkeletonPoint(models.Model):
    label = models.ForeignKey(LabelClass, on_delete=models.CASCADE, related_name="skeleton_points")
    name = models.CharField(max_length=80)
    color = models.CharField(max_length=7, default="#40c4ff")
    x = models.FloatField(default=50)
    y = models.FloatField(default=50)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        constraints = [models.UniqueConstraint(fields=["label", "name"], name="unique_point_per_skeleton")]


class SkeletonEdge(models.Model):
    label = models.ForeignKey(LabelClass, on_delete=models.CASCADE, related_name="skeleton_edges")
    from_point = models.ForeignKey(SkeletonPoint, on_delete=models.CASCADE, related_name="outgoing_edges")
    to_point = models.ForeignKey(SkeletonPoint, on_delete=models.CASCADE, related_name="incoming_edges")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        constraints = [models.UniqueConstraint(fields=["label", "from_point", "to_point"], name="unique_skeleton_edge")]


class AnnotationJob(models.Model):
    STAGE_CHOICES = [("annotation", "Annotation"), ("validation", "Validation"), ("acceptance", "Acceptance")]
    STATE_CHOICES = [("new", "New"), ("in_progress", "In progress"), ("completed", "Completed"), ("rejected", "Rejected")]
    task = models.ForeignKey(AnnotationTask, on_delete=models.CASCADE, related_name="jobs")
    video = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="job")
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="annotation_jobs")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="review_jobs")
    stage = models.CharField(max_length=16, choices=STAGE_CHOICES, default="annotation")
    state = models.CharField(max_length=16, choices=STATE_CHOICES, default="new")
    start_frame = models.PositiveIntegerField(default=0)
    stop_frame = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]


class AnnotationShape(models.Model):
    TYPE_CHOICES = [("rectangle", "Rectangle"), ("skeleton", "Skeleton")]
    job = models.ForeignKey(AnnotationJob, on_delete=models.CASCADE, related_name="shapes")
    label = models.ForeignKey(LabelClass, on_delete=models.PROTECT, related_name="shapes")
    frame_index = models.PositiveIntegerField(db_index=True)
    shape_type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    points = models.JSONField(default=list)
    attributes = models.JSONField(default=dict, blank=True)
    source = models.CharField(max_length=16, default="manual")
    confidence = models.FloatField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="created_annotation_shapes")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="updated_annotation_shapes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["job", "frame_index"], name="shape_job_frame_idx")]


class AutoAnnotationFunction(models.Model):
    """Remote inference function exposed to the Annotation execution plane."""
    KIND_CHOICES = [("detector", "Detection"), ("pose", "Pose / Skeleton")]

    name = models.CharField(max_length=160)
    key = models.SlugField(max_length=100, unique=True)
    endpoint_url = models.URLField(max_length=500)
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    spec = models.JSONField(default=list, help_text="CVAT-compatible model label specification")
    enabled = models.BooleanField(default=True)
    timeout_seconds = models.PositiveIntegerField(default=120)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class AutoAnnotationRun(models.Model):
    STATUS_CHOICES = [
        ("QUEUED", "Queued"), ("RUNNING", "Running"),
        ("COMPLETED", "Completed"), ("FAILED", "Failed"),
        ("CANCELLED", "Cancelled"),
    ]

    task = models.ForeignKey(AnnotationTask, on_delete=models.CASCADE, related_name="auto_annotation_runs")
    function = models.ForeignKey(AutoAnnotationFunction, on_delete=models.PROTECT, related_name="runs")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="QUEUED")
    threshold = models.FloatField(default=0.25)
    cleanup = models.BooleanField(default=False)
    mapping = models.JSONField(default=dict)
    progress_current = models.PositiveIntegerField(default=0)
    progress_total = models.PositiveIntegerField(default=0)
    shapes_created = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    celery_task_id = models.CharField(max_length=80, blank=True)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


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
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="created_qc_boxes")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="updated_qc_boxes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["project", "frame_index"], name="annotation_project_238bcb_idx")]
