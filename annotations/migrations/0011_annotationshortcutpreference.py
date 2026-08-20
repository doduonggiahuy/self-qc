from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("annotations", "0010_project_media_kind_and_manifest"),
    ]

    operations = [
        migrations.CreateModel(
            name="AnnotationShortcutPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shortcuts", models.JSONField(blank=True, default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=models.deletion.CASCADE, related_name="annotation_shortcut_preference", to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
