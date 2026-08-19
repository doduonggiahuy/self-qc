from django.db import migrations, models
import django.db.models.deletion


def move_existing_videos_to_first_task(apps, schema_editor):
    Video = apps.get_model("annotations", "Project")
    # The new FK intentionally uses the same reverse name as the old M2M.
    # Read the historical implicit through model explicitly while both exist.
    through = apps.get_model("annotations", "AnnotationTask_videos")
    for row in through.objects.all():
        Video.objects.filter(pk=row.project_id, annotation_task__isnull=True).update(annotation_task_id=row.annotationtask_id)


class Migration(migrations.Migration):
    dependencies = [("annotations", "0005_annotationtask")]

    operations = [
        migrations.AddField(
            model_name="project",
            name="annotation_task",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="videos", to="annotations.annotationtask"),
        ),
        migrations.AddField(
            model_name="labelclass",
            name="client_project",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="labels", to="annotations.clientproject"),
        ),
        migrations.AlterField(model_name="labelclass", name="project", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="classes", to="annotations.project")),
        migrations.RunPython(move_existing_videos_to_first_task, migrations.RunPython.noop),
        migrations.RemoveField(model_name="annotationtask", name="videos"),
        migrations.RemoveField(model_name="rule", name="videos"),
        migrations.AlterUniqueTogether(name="labelclass", unique_together=set()),
        migrations.AddConstraint(model_name="labelclass", constraint=models.UniqueConstraint(condition=models.Q(("project__isnull", True)), fields=("client_project", "name"), name="unique_label_per_client_project")),
        migrations.AddConstraint(model_name="labelclass", constraint=models.UniqueConstraint(condition=models.Q(("client_project__isnull", True)), fields=("project", "name"), name="unique_label_per_video_snapshot")),
    ]
