import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "annotations",
    "quality",
    "training",
    "ai_rules",
    "control_plane.projects.apps.PlatformProjectsConfig",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "control_plane.config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "control_plane" / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "control_plane.projects.context_processors.platform_access",
    ]},
}]
WSGI_APPLICATION = "control_plane.config.wsgi.application"
if os.getenv("POSTGRES_HOST"):
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "freeflow"),
        "USER": os.getenv("POSTGRES_USER", "freeflow"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", "freeflow_local"),
        "HOST": os.getenv("POSTGRES_HOST", "db"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": os.getenv("SQLITE_DB_PATH", BASE_DIR / "data/db.sqlite3")}}
AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = "vi"
TIME_ZONE = "Asia/Ho_Chi_Minh"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "control_plane" / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.getenv("QC_MEDIA_ROOT", BASE_DIR / "media"))
MODEL_ROOT = Path(os.getenv("QC_MODEL_ROOT", BASE_DIR / "models"))
DATASET_ROOT = Path(os.getenv("QC_DATASET_ROOT", BASE_DIR / "datasets"))
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")
CELERY_TASK_DEFAULT_QUEUE = "platform"
CELERY_TASK_ROUTES = {
    "control_plane.projects.tasks.*": {"queue": "platform"},
    "annotations.tasks.*": {"queue": "annotation"},
    "quality.tasks.*": {"queue": "quality"},
    "training.tasks.*": {"queue": "training"},
    "ai_rules.tasks.*": {"queue": "ai_rules"},
}
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = int(os.getenv("CELERY_TASK_TIME_LIMIT", "86400"))
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "project-list"
LOGOUT_REDIRECT_URL = "login"
DATA_UPLOAD_MAX_MEMORY_SIZE = 200 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FILES = int(os.getenv("DATA_UPLOAD_MAX_NUMBER_FILES", "50000"))
DATA_UPLOAD_MAX_NUMBER_FIELDS = int(os.getenv("DATA_UPLOAD_MAX_NUMBER_FIELDS", "100000"))
DATASET_MAX_ARCHIVE_FILES = int(os.getenv("DATASET_MAX_ARCHIVE_FILES", "2000000"))
DATASET_MAX_EXTRACTED_BYTES = int(os.getenv("DATASET_MAX_EXTRACTED_BYTES", str(2 * 1024**4)))
