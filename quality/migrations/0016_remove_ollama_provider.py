from django.db import migrations, models


def remove_ollama_models(apps, schema_editor):
    InferenceModel = apps.get_model("quality", "InferenceModel")
    InferenceModel.objects.filter(provider="OLLAMA").delete()


class Migration(migrations.Migration):
    dependencies = [("quality", "0015_modelevaluationframe")]

    operations = [
        migrations.RunPython(remove_ollama_models, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="inferencemodel",
            name="provider",
            field=models.CharField(
                choices=[("LOCAL", "Upload local"), ("HUGGING_FACE", "Hugging Face")],
                default="LOCAL",
                max_length=20,
            ),
        ),
    ]
