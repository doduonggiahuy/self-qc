import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "control_plane.config.settings")
app = Celery("freeflow")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
