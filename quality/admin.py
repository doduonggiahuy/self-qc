from django.contrib import admin
from .models import EvaluationDataset, EvaluationDatasetClass, EvaluationModel, GroundTruthItem, GroundTruthRelease, InferenceModel, ModelEvaluationFrame, ModelEvaluationRun, Target, TestCase, TestRun, UserInferencePreference

admin.site.register(GroundTruthRelease)
admin.site.register(GroundTruthItem)
admin.site.register(Target)
admin.site.register(TestCase)
admin.site.register(TestRun)
admin.site.register(InferenceModel)
admin.site.register(UserInferencePreference)
admin.site.register(EvaluationDataset)
admin.site.register(EvaluationDatasetClass)
admin.site.register(EvaluationModel)
admin.site.register(ModelEvaluationRun)
admin.site.register(ModelEvaluationFrame)
