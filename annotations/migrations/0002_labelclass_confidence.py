from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("annotations", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="labelclass",
            name="confidence",
            field=models.FloatField(default=0.25),
        ),
    ]
