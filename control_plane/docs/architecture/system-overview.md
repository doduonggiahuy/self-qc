# System overview

**Status:** Implemented foundation, production execution plane planned.

Model QC là control plane để tạo Ground Truth và quản lý các bài kiểm thử cho
video AI. Repo hiện là Django modular monolith gồm hai bounded module:

```text
annotations  -> project, video, class/prompt, bbox editor, YOLO-World proposal
quality      -> GT release, target, inference registry, test case, test run
training     -> dataset artifact reference, training run, model artifact reference
ai_rules     -> versioned rule definition, rule execution and result artifact

The repository is currently a modular monolith. These four Django apps are
bounded-context seams for the future Annotation, Model Quality, Training and
AI Rule services. Large datasets and model outputs should be exchanged as
versioned artifact references; Kafka event envelopes are defined in
`control_plane.events` and can later be backed by a real broker without changing
the domain models.
```

## Luồng hiện chạy được

```text
Upload RAW video
 -> infer/draw/review bbox
 -> freeze reviewed bbox thành GT release
 -> tạo GT validation test case
 -> execute evaluator
 -> lưu metrics, assertions và correlation ID
```

Django view chỉ điều phối request ngắn. Nghiệp vụ freeze/run nằm trong service
boundary. Test run hiện chạy đồng bộ; worker/workflow durable là bước tiếp theo.

## Hạ tầng hiện tại

- Django 5.1 và Django auth.
- SQLite cho local MVP.
- Docker Compose và NVIDIA GPU.
- OpenCV đọc video/frame.
- Ultralytics YOLO-World + CLIP cho auto-label.
- Docker volumes lưu DB, media và weights.
- Model source tối giản: upload local hoặc Hugging Face pull.

Toàn bộ state persistent dùng volume `qc_storage`: Hugging Face snapshot nằm tại
`models/huggingface` và local artifacts cũng nằm trong `models`.

## Kiến trúc đích

PostgreSQL sẽ giữ metadata; S3/MinIO giữ video và artifact; worker/workflow chạy
inference; adapter gọi Triton hoặc thu Kafka; evaluator chuẩn hóa và chấm kết quả.
