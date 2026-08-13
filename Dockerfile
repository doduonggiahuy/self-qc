FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libglib2.0-0 libgl1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Keep the CUDA runtime deterministic.  Without an explicit PyTorch wheel,
# ultralytics may resolve to a much newer CUDA toolkit and add several GB.
RUN pip install \
      --index-url https://download.pytorch.org/whl/cu128 \
      torch==2.7.1 torchvision==0.22.1
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
