from django.contrib import admin
from .models import BoxAnnotation, ClientProject, LabelClass, Project, Rule

admin.site.register(ClientProject)
admin.site.register(Rule)
admin.site.register(Project)
admin.site.register(LabelClass)
admin.site.register(BoxAnnotation)
