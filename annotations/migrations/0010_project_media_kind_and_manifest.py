from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("annotations", "0009_remove_boxannotation_prompt_remove_labelclass_prompt")]
    operations = [
        migrations.AlterField(
            model_name="project", name="video",
            field=models.FileField(blank=True, upload_to="videos/%Y/%m/"),
        ),
        migrations.AddField(
            model_name="project", name="media_kind",
            field=models.CharField(choices=[("VIDEO", "Video"), ("IMAGE_SEQUENCE", "Image sequence")], default="VIDEO", max_length=20),
        ),
        migrations.AddField(
            model_name="project", name="frame_manifest",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
