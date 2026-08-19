# Model QC Studio

Tài liệu hệ thống được duy trì tại [`control_plane/docs/`](control_plane/docs/README.md).

## Repository map

Đây là một Django modular monolith đang chuẩn bị tách thành các service riêng:

- `annotations/`: annotation workflow và Ground Truth source;
- `quality/`: model evaluation, metrics và quality reports;
- `training/`: training run orchestration;
- `ai_rules/`: versioned rule execution;
- `control_plane/`: Platform UI/config, project manifest, contracts, events và tài liệu;
- `cvat/`: CVAT Community annotation engine và custom auto-annotation models.

Đọc [repository map](control_plane/docs/architecture/repository-map.md) và [bounded
contexts](control_plane/docs/architecture/bounded-contexts.md) trước khi sửa code.

Quick start local:

```bash
make up local
make logs
make refresh
```

Mọi workflow development chạy bằng Docker; không cần cài Python/Django/PyTorch
trên host. Dùng `make help` để xem lệnh vận hành.

Xem các lệnh hỗ trợ bằng `make help`.

Django web application for creating human-reviewed ground truth with YOLO-World
assistance. Raw videos are never modified.

## Start

```bash
docker compose up -d --build
docker compose exec platform-web python manage.py createsuperuser
```

Open <http://localhost:8090>, sign in, create a project and upload a video.
The first YOLO-World inference downloads the configured model unless a matching
`.pt` file already exists in the `runtime_artifacts` volume under `models`.

## Current MVP

- Django users, groups and permissions;
- video upload/probe and frame-accurate JPEG access;
- configurable GT class and YOLO-World prompt mapping;
- YOLO-World proposals without overwriting reviewed boxes;
- canvas play/pause, speed, frame seek, draw/move/delete and class/status editing;
- project resume and approved/edited GT JSONL export.

Platform roles are created automatically. Use Platform Members to assign
`Data Annotator`, `AI Model Engineer`, `AI Rule Engineer`, `AI Ops Engineer`
or `QA/QC Engineer`; `AI Admin` is a Django superuser.

## Quality Lab foundation

Each project now has a **Quality Lab** entry point. The first runnable vertical
slice deliberately stays small:

1. review boxes in the annotator;
2. freeze reviewed boxes into an immutable Ground Truth release;
3. create a versioned GT validation test case;
4. run it and inspect its input snapshot, metrics, assertions and correlation ID.

The new `quality` Django app is the control-plane foundation:

```text
GroundTruthRelease -> GroundTruthItem
Target             -> future Triton/Kafka/offline adapter configuration
TestCase           -> immutable execution configuration/version
TestRun            -> state, input snapshot, metrics and assertion results
```

Execution logic lives behind `quality.services` and evaluator contracts rather
than in views. Runs are synchronous in this first slice. A durable workflow or
queue worker can later call the same `execute_run()` boundary without changing
the UI/domain model.

Only `GT_VALIDATION` has an evaluator today. Detection, classification, pose and
rule kinds are represented in the domain but intentionally return inconclusive
until their adapters/evaluators are implemented.

## Verify

```bash
python manage.py migrate
python manage.py check
python manage.py makemigrations --check
python manage.py test
```
