from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("annotations", "0006_cvat_project_task_data_model")]
    operations = [
        migrations.AddField(model_name="labelclass", name="label_type", field=models.CharField(choices=[("rectangle", "Detection / Bounding box"), ("skeleton", "Skeleton pose"), ("tag", "Tag")], default="rectangle", max_length=16)),
        migrations.CreateModel(name="LabelAttribute", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("name", models.CharField(max_length=80)), ("input_type", models.CharField(choices=[("select", "Select"), ("radio", "Radio"), ("checkbox", "Checkbox"), ("text", "Text"), ("number", "Number")], default="select", max_length=16)),
            ("values", models.JSONField(blank=True, default=list)), ("default_value", models.CharField(blank=True, max_length=160)), ("mutable", models.BooleanField(default=False)), ("order", models.PositiveIntegerField(default=0)),
            ("label", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attributes", to="annotations.labelclass")),
        ], options={"ordering": ["order", "id"]}),
        migrations.CreateModel(name="SkeletonPoint", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("name", models.CharField(max_length=80)), ("color", models.CharField(default="#40c4ff", max_length=7)), ("x", models.FloatField(default=50)), ("y", models.FloatField(default=50)), ("order", models.PositiveIntegerField(default=0)),
            ("label", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="skeleton_points", to="annotations.labelclass")),
        ], options={"ordering": ["order", "id"]}),
        migrations.CreateModel(name="SkeletonEdge", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("order", models.PositiveIntegerField(default=0)),
            ("from_point", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="outgoing_edges", to="annotations.skeletonpoint")), ("label", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="skeleton_edges", to="annotations.labelclass")), ("to_point", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="incoming_edges", to="annotations.skeletonpoint")),
        ], options={"ordering": ["order", "id"]}),
        migrations.CreateModel(name="AnnotationJob", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("stage", models.CharField(choices=[("annotation", "Annotation"), ("validation", "Validation"), ("acceptance", "Acceptance")], default="annotation", max_length=16)), ("state", models.CharField(choices=[("new", "New"), ("in_progress", "In progress"), ("completed", "Completed"), ("rejected", "Rejected")], default="new", max_length=16)), ("start_frame", models.PositiveIntegerField(default=0)), ("stop_frame", models.PositiveIntegerField(default=0)), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("assignee", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="annotation_jobs", to=settings.AUTH_USER_MODEL)), ("reviewer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="review_jobs", to=settings.AUTH_USER_MODEL)), ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="jobs", to="annotations.annotationtask")), ("video", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="job", to="annotations.project")),
        ], options={"ordering": ["id"]}),
        migrations.CreateModel(name="AnnotationShape", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("frame_index", models.PositiveIntegerField(db_index=True)), ("shape_type", models.CharField(choices=[("rectangle", "Rectangle"), ("skeleton", "Skeleton")], max_length=16)), ("points", models.JSONField(default=list)), ("attributes", models.JSONField(blank=True, default=dict)), ("source", models.CharField(default="manual", max_length=16)), ("confidence", models.FloatField(blank=True, null=True)), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_annotation_shapes", to=settings.AUTH_USER_MODEL)), ("job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shapes", to="annotations.annotationjob")), ("label", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="shapes", to="annotations.labelclass")), ("updated_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_annotation_shapes", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["id"]}),
        migrations.AddConstraint(model_name="labelattribute", constraint=models.UniqueConstraint(fields=("label", "name"), name="unique_attribute_per_label")),
        migrations.AddConstraint(model_name="skeletonpoint", constraint=models.UniqueConstraint(fields=("label", "name"), name="unique_point_per_skeleton")),
        migrations.AddConstraint(model_name="skeletonedge", constraint=models.UniqueConstraint(fields=("label", "from_point", "to_point"), name="unique_skeleton_edge")),
        migrations.AddIndex(model_name="annotationshape", index=models.Index(fields=["job", "frame_index"], name="shape_job_frame_idx")),
    ]
