from django.contrib import admin
from .models import GroundTruthItem, GroundTruthRelease, InferenceModel, Target, TestCase, TestRun, UserInferencePreference

admin.site.register(GroundTruthRelease)
admin.site.register(GroundTruthItem)
admin.site.register(Target)
admin.site.register(TestCase)
admin.site.register(TestRun)
admin.site.register(InferenceModel)
admin.site.register(UserInferencePreference)
