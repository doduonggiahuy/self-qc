from django.contrib import admin
from .models import (
    AnnotationJob, AnnotationShape, AnnotationTask, AutoAnnotationFunction, AutoAnnotationRun, BoxAnnotation, ClientProject,
    LabelAttribute, LabelClass, Project, Rule, SkeletonEdge, SkeletonPoint,
)

admin.site.register(ClientProject)
admin.site.register(Rule)
admin.site.register(Project)
admin.site.register(LabelClass)
admin.site.register(BoxAnnotation)
admin.site.register(AnnotationTask)
admin.site.register(AnnotationJob)
admin.site.register(AnnotationShape)
admin.site.register(AutoAnnotationFunction)
admin.site.register(AutoAnnotationRun)
admin.site.register(LabelAttribute)
admin.site.register(SkeletonPoint)
admin.site.register(SkeletonEdge)
