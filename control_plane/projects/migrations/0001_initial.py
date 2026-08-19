from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="PlatformProject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.SlugField(max_length=120, unique=True)),
                ("name", models.CharField(max_length=160)),
                ("manifest_version", models.PositiveIntegerField(default=1)),
                ("manifest", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(null=True, on_delete=models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="ServiceProvisioning",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("service", models.CharField(choices=[("ANNOTATION", "Annotation"), ("QUALITY", "Model Quality"), ("TRAINING", "Training"), ("AI_RULES", "AI Rules")], max_length=16)),
                ("external_id", models.CharField(blank=True, max_length=160)),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("PROVISIONING", "Provisioning"), ("READY", "Ready"), ("FAILED", "Failed")], default="PENDING", max_length=16)),
                ("last_event_id", models.CharField(blank=True, max_length=120)),
                ("error", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("project", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="provisioning", to="platform_control.platformproject")),
            ],
        ),
        migrations.AddConstraint(model_name="serviceprovisioning", constraint=models.UniqueConstraint(fields=("project", "service"), name="unique_project_service_provisioning")),
    ]
