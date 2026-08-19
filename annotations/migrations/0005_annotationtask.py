from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("annotations", "0004_client_project_rules")]
    operations = [
        migrations.CreateModel(
            name="AnnotationTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160)),
                ("description", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("DRAFT", "Draft"), ("ASSIGNED", "Assigned"), ("IN_PROGRESS", "In progress"), ("IN_REVIEW", "In review"), ("COMPLETED", "Completed")], default="DRAFT", max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("assignees", models.ManyToManyField(blank=True, related_name="assigned_annotation_tasks", to=settings.AUTH_USER_MODEL)),
                ("client_project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="annotation_tasks", to="annotations.clientproject")),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_annotation_tasks", to=settings.AUTH_USER_MODEL)),
                ("reviewers", models.ManyToManyField(blank=True, related_name="review_annotation_tasks", to=settings.AUTH_USER_MODEL)),
                ("rules", models.ManyToManyField(blank=True, related_name="annotation_tasks", to="annotations.rule")),
                ("videos", models.ManyToManyField(related_name="annotation_tasks", to="annotations.project")),
            ],
            options={"ordering": ["-updated_at"]},
        ),
        migrations.AddConstraint(model_name="annotationtask", constraint=models.UniqueConstraint(fields=("client_project", "name"), name="unique_annotation_task_per_project")),
    ]
