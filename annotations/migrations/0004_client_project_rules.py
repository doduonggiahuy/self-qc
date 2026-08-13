from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def wrap_existing_videos(apps, schema_editor):
    ClientProject = apps.get_model("annotations", "ClientProject")
    Project = apps.get_model("annotations", "Project")
    for video in Project.objects.filter(client_project__isnull=True).iterator():
        client = ClientProject.objects.create(name=video.name, owner_id=video.owner_id)
        video.client_project_id = client.pk
        video.save(update_fields=["client_project"])


class Migration(migrations.Migration):
    dependencies = [("annotations", "0002_labelclass_confidence")]
    operations = [
        migrations.CreateModel(
            name="ClientProject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160)),
                ("status", models.CharField(choices=[("ACTIVE", "Active"), ("ARCHIVED", "Archived")], default="ACTIVE", max_length=16)),
                ("description", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="client_projects", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-updated_at"]},
        ),
        migrations.AddField(
            model_name="project", name="client_project",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="videos", to="annotations.clientproject"),
        ),
        migrations.CreateModel(
            name="Rule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160)),
                ("description", models.TextField(blank=True)),
                ("enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("client_project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rules", to="annotations.clientproject")),
                ("videos", models.ManyToManyField(blank=True, related_name="rules", to="annotations.project")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.AddConstraint(model_name="rule", constraint=models.UniqueConstraint(fields=("client_project", "name"), name="unique_rule_per_client_project")),
        migrations.RunPython(wrap_existing_videos, migrations.RunPython.noop),
    ]
