FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY entrypoint.sh /usr/local/bin/model-qc-entrypoint
RUN chmod +x /usr/local/bin/model-qc-entrypoint
ENTRYPOINT ["/usr/local/bin/model-qc-entrypoint"]

FROM base AS web-deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-web.txt .
RUN pip install -r requirements-web.txt

FROM web-deps AS platform-web
COPY . .
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

FROM web-deps AS worker-base
RUN pip install \
      --index-url https://download.pytorch.org/whl/cu128 \
      torch==2.9.1 torchvision==0.24.1
COPY requirements-worker.txt .
RUN pip install -r requirements-worker.txt
COPY . .

FROM worker-base AS platform-worker
CMD ["celery", "-A", "control_plane.config.celery:app", "worker", "-Q", "platform", "--loglevel=INFO", "--concurrency=1"]

FROM worker-base AS annotation-worker
CMD ["celery", "-A", "control_plane.config.celery:app", "worker", "-Q", "annotation", "--loglevel=INFO", "--concurrency=1"]

FROM worker-base AS quality-worker
CMD ["celery", "-A", "control_plane.config.celery:app", "worker", "-Q", "quality", "--loglevel=INFO", "--concurrency=1"]

FROM worker-base AS training-worker
CMD ["celery", "-A", "control_plane.config.celery:app", "worker", "-Q", "training", "--loglevel=INFO", "--concurrency=1"]

FROM worker-base AS ai-rules-worker
CMD ["celery", "-A", "control_plane.config.celery:app", "worker", "-Q", "ai_rules", "--loglevel=INFO", "--concurrency=1"]
