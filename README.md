# Model QC Studio

Tài liệu hệ thống được duy trì tại [`docs/`](docs/README.md).

Quick start local:

```bash
make up local
make logs
make refresh
```

Xem các lệnh hỗ trợ bằng `make help`.

Django web application for creating human-reviewed ground truth with YOLO-World
assistance. Raw videos are never modified.

## Start

```bash
docker compose up -d --build
docker compose exec web python manage.py createsuperuser
```

Open <http://localhost:8090>, sign in, create a project and upload a video.
The first YOLO-World inference downloads the configured model unless a matching
`.pt` file already exists in the `qc_models` volume.

## Current MVP

- Django users, groups and permissions;
- video upload/probe and frame-accurate JPEG access;
- configurable GT class and YOLO-World prompt mapping;
- YOLO-World proposals without overwriting reviewed boxes;
- canvas play/pause, speed, frame seek, draw/move/delete and class/status editing;
- project resume and approved/edited GT JSONL export.

Reviewer groups are created automatically. Add users to `QC Annotator` or
`QC Reviewer` from Django admin.

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
