import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="Project", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("name", models.CharField(max_length=160)),
            ("video", models.FileField(upload_to="videos/%Y/%m/")),
            ("status", models.CharField(choices=[("DRAFT", "Draft"), ("IN_REVIEW", "In review"), ("DONE", "Done")], default="DRAFT", max_length=16)),
            ("width", models.PositiveIntegerField(default=0)), ("height", models.PositiveIntegerField(default=0)),
            ("fps", models.FloatField(default=0)), ("frame_count", models.PositiveIntegerField(default=0)),
            ("coverage", models.CharField(choices=[("partial", "Partial"), ("exhaustive", "Exhaustive")], default="partial", max_length=16)),
            ("current_frame", models.PositiveIntegerField(default=0)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("owner", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="qc_projects", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["-updated_at"], "permissions": [("edit_all_projects", "Can edit every QC project"), ("review_annotations", "Can approve or reject annotations")]}),
        migrations.CreateModel(name="LabelClass", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("name", models.CharField(max_length=80)), ("prompt", models.CharField(max_length=240)),
            ("color", models.CharField(default="#00e676", max_length=7)), ("enabled", models.BooleanField(default=True)),
            ("order", models.PositiveIntegerField(default=0)),
            ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="classes", to="annotations.project")),
        ], options={"ordering": ["order", "id"], "unique_together": {("project", "name")}}),
        migrations.CreateModel(name="BoxAnnotation", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("frame_index", models.PositiveIntegerField(db_index=True)),
            ("x1", models.FloatField()), ("y1", models.FloatField()), ("x2", models.FloatField()), ("y2", models.FloatField()),
            ("confidence", models.FloatField(blank=True, null=True)),
            ("source", models.CharField(choices=[("YOLO_WORLD", "YOLO-World"), ("MANUAL", "Manual")], default="MANUAL", max_length=16)),
            ("review_status", models.CharField(choices=[("PREDICTED", "Predicted"), ("APPROVED", "Approved"), ("REJECTED", "Rejected"), ("EDITED", "Edited")], default="PREDICTED", max_length=16)),
            ("prompt", models.CharField(blank=True, max_length=240)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_qc_boxes", to=settings.AUTH_USER_MODEL)),
            ("updated_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_qc_boxes", to=settings.AUTH_USER_MODEL)),
            ("label_class", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="boxes", to="annotations.labelclass")),
            ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="boxes", to="annotations.project")),
        ]),
        migrations.AddIndex(model_name="boxannotation", index=models.Index(fields=["project", "frame_index"], name="annotation_project_238bcb_idx")),
    ]

