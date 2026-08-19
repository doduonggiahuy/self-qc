FROM model-qc/annotation-worker:dev

RUN python -m pip install --no-cache-dir --upgrade ultralytics==8.4.121

CMD ["python", "/app/annotations/runtime/server.py"]
