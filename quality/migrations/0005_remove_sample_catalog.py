from django.db import migrations


SAMPLE_KEYS = ["yolo-world", "grounding-dino", "florence-2", "owlv2", "locate-anything-3b"]


def remove_sample_catalog(apps, schema_editor):
    model = apps.get_model("quality", "InferenceModel")
    model.objects.filter(key__in=SAMPLE_KEYS, model_file="").delete()


class Migration(migrations.Migration):
    dependencies = [("quality", "0004_inferencemodel_model_file_userinferencepreference")]
    operations = [migrations.RunPython(remove_sample_catalog, migrations.RunPython.noop)]
