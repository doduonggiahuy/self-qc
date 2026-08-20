# Freeflow repository handoff

**Cập nhật:** 2026-08-20  
**Nhánh:** `main`  
**Mục đích:** tài liệu đầu vào duy nhất cho một phiên chat/agent mới tiếp tục phát triển repo.

## 1. Product và hướng kiến trúc đã chốt

Freeflow là Platform chung cho vòng đời Computer Vision theo customer project:

```text
Platform / Control Plane
  ├── Annotation: tạo Ground Truth và auto annotation
  ├── Model Quality: đánh giá model/rule bằng GT và output AI
  ├── Training: đánh giá dataset, train và phát hành model
  └── AI Rules: triển khai/chạy rule nghiệp vụ của từng project
```

Ví dụ `FuramaResort` là một Project. Project sở hữu label schema và các rule như
`standing_still` hay `use_phone`. Dataset đã label có thể được phát hành cho cả
Quality và Training. Model do Training tạo sẽ được Model Registry quản lý rồi đưa
vào AI Rules. Platform cung cấp UI, account, RBAC và project configuration chung.

Đích dài hạn là mỗi domain thành một repository/microservice riêng và trao đổi qua
Kafka. Hiện repo cố ý là **Django modular monolith** để phát triển workflow nhanh,
nhưng đã tạo seam theo bounded context. Metadata/event nhỏ đi qua contract/event;
video, dataset, model và report lớn chỉ truyền bằng versioned artifact reference,
không nhét binary vào Kafka.

Không tách repo ngay cho đến khi domain và contract ổn định.

## 2. Cấu trúc repository hiện tại

| Đường dẫn | Trách nhiệm |
| --- | --- |
| `annotations/` | Project label schema, Task, Job, Shape, media ingestion, canvas, auto annotation |
| `quality/` | GT release, model registry legacy, evaluation datasets/runs/metrics và Quality UI |
| `training/` | Base cho training dataset/run và worker queue |
| `ai_rules/` | Base cho versioned rule definition/run và worker queue |
| `model_registry/` | Seam/model registry dùng chung đang được tách khỏi Quality |
| `control_plane/projects/` | Platform project manifest, member UI và access context |
| `control_plane/contracts/` | Artifact contracts dùng chung trong giai đoạn monolith |
| `control_plane/events/` | Event envelope và topic constants; chưa gắn Kafka broker thật |
| `control_plane/templates/` | Django server-rendered MPA frontend/design system |
| `control_plane/config/` | Django settings, URL, WSGI và Celery config |
| `control_plane/docs/` | Tài liệu sống của hệ thống |
| `cvat/` | Source CVAT Community để nghiên cứu/tham khảo và chứa custom YOLO26 assets; không phải Django app Freeflow |

Tên ORM `ClientProject` hiện vẫn là Annotation Project thực tế. `Project` trong
`annotations` là media/data source legacy. Đây là khoản nợ naming cần xử lý cẩn
thận vì migration và code Quality cũ còn phụ thuộc.

## 3. Runtime và deployment local

Đường chạy chuẩn là Docker-first; không yêu cầu Python/PyTorch trên host.

```bash
make up local        # build và bật toàn stack
make apply           # recreate platform-web + annotation-worker để nhận code mới, không build
make rebuild         # build lại SERVICE, dùng khi đổi dependency/Dockerfile
make migrate         # chạy migration trong platform-web
make test            # toàn bộ Django tests trong container
make check           # system check + kiểm tra migration thiếu
make logs            # log service, mặc định platform-web
make logs-all        # log toàn stack
make admin           # createsuperuser
make createsuperuser # alias rõ nghĩa để tạo superuser
make sync-auto-annotation
```

UI: <http://localhost:8090>.

Compose project tên `freeflow`, gồm:

- `platform-web`: Django UI/API;
- `platform-worker`: Celery queue `platform`;
- `annotation-worker`: Celery queue `annotation`;
- `quality-worker`, `training-worker`, `ai-rules-worker`;
- `annotation-yolo26-detection`, `annotation-yolo26-pose`: GPU inference services;
- PostgreSQL 16 và Redis 7.

Source được bind mount vào `/app`. Runtime data nằm trong named volumes:

- `postgres_data`: PostgreSQL metadata/business state;
- `runtime_artifacts`: `/var/lib/freeflow/{media,models,datasets}`.

Reset toàn bộ dữ liệu Freeflow là thao tác destructive có xác nhận:

```bash
make reset-data CONFIRM=RESET
make up local
```

## 4. Account và RBAC

Role chuẩn:

- `Data Annotator`
- `AI Model Engineer`
- `AI Rule Engineer`
- `AI Ops Engineer`
- `QA/QC Engineer`
- `AI Admin`: Django superuser/root

Quy tắc Annotation hiện tại:

| Chức năng | AI Admin | Data Annotator |
| --- | --- | --- |
| Tạo/xóa Project | Có | Không |
| Tạo/sửa labels, attributes, skeleton, rules | Có | Không |
| Xem Project/rules/schema | Có | Có |
| Tạo/sửa/xóa Task trong Project | Có | Có |
| Upload/xóa Task data | Có | Có |
| Assign annotator/reviewer | Có | Có |
| Mở và lưu Job Canvas | Có | Có |
| Chạy Automatic Annotation | Có | Có |

Data Annotator được quyền vận hành toàn bộ Task/Job trong Annotation domain để một
team lead annotator có thể upload và phân công cho cấp dưới. Việc ẩn menu chỉ là UX;
authorization phía backend mới là security boundary. Annotator tuyệt đối không
được POST Project, Project labels hoặc Project rules.

## 5. Annotation domain đã triển khai

### 5.1 Project → Task → Job

```text
ClientProject
  ├── LabelClass
  │    ├── LabelAttribute
  │    ├── SkeletonPoint
  │    └── SkeletonEdge
  ├── Rule
  └── AnnotationTask
       ├── assignees / reviewers / selected rules
       └── AnnotationJob
            └── AnnotationShape per frame
```

- Root tạo Project cùng label schema và rules.
- Constructor hỗ trợ rectangle/detection, tag, attributes và skeleton.
- Raw editor đọc JSON array cùng format CVAT (`type:any`, attributes, sublabels,
  skeleton SVG). ID CVAT bị bỏ khi persist local.
- Label và từng skeleton point có màu riêng. Point mới lấy palette tự động; Raw
  import giữ nguyên màu CVAT; canvas có palette fallback cho schema cũ đồng màu.
- Project detail hiển thị đúng swatch/mã màu đã lưu và có Edit/Delete cho từng
  label với root. Delete label xóa annotation tham chiếu sau confirm như CVAT;
  annotator không có quyền thay đổi schema.
- Annotator tạo Task trong Project, chọn rules, assignees/reviewers và upload data.
- Task kế thừa label schema từ Project và không được tự tạo label riêng.
- Task có edit/delete, đổi metadata/status/team/rules và upload bổ sung.

### 5.2 Media ingestion

Task nhận:

- nhiều image hoặc cả folder image;
- ZIP chứa image;
- video.

Folder/ZIP được natural-sort. ZIP có kiểm tra path traversal, encrypted entry, số
file và tổng dung lượng giải nén. Video được parse/materialize thành JPEG frame để
toàn bộ pipeline dùng chung `IMAGE_SEQUENCE` và frame manifest. File nguồn vẫn
được giữ để audit. Không trộn video/ZIP unique source với tập image trong cùng một
lần ingest.

### 5.3 Job Canvas hiện tại

Canvas full-screen có:

- Select, BBox và Skeleton tools;
- ảnh fit trong viewport cố định, giữ aspect ratio;
- wheel zoom neo theo vị trí con trỏ, nút zoom/fit;
- bbox label badge, kéo cả bbox và 8 resize handles;
- skeleton edges, point name, màu riêng từng point;
- click/kéo point để đổi tọa độ, nhập X/Y hoặc xóa riêng point;
- object list, Project labels, attribute editor;
- undo/redo, dirty-state guard, save frame, xóa object;
- frame slider, previous/next và keyboard shortcuts.

API chính:

- `GET /annotation/jobs/<job_id>/`
- `GET /api/annotation/jobs/<job_id>/frames/<frame>/`
- `POST /api/annotation/jobs/<job_id>/frames/<frame>/save/`

**Yêu cầu mới nhất chưa triển khai:** thêm Pan/Hand interaction để con trỏ có thể
kéo thả/pan frame đã zoom bên trong viewport. Nên làm theo kiểu CVAT: Hand tool
hoặc giữ Space + drag; không được xung đột drag bbox/skeleton point. Cursor cần đổi
`grab/grabbing`, pan bằng `viewport.scrollLeft/scrollTop`, và ghi vào docs/test.

Các bước Canvas tiếp theo hợp lý: autosave, visibility/lock, copy/paste shape,
polygon/mask, frame interpolation/tracking, configurable point visibility.

## 6. Automatic Annotation

Đã loại bỏ hoàn toàn inference model prompt/YOLO-World cũ khỏi Annotation. Auto
annotation mới theo mô hình CVAT function:

```text
AnnotationTask
  -> AutoAnnotationRun
  -> annotation Celery worker
  -> remote model /spec + /infer
  -> AnnotationShape trên từng Job/frame
```

Model function registry chứa endpoint, kind và dynamic spec. Detection/Pose là hai
function độc lập; class/keypoint không hardcode trong core Annotation. UI mapping
dùng các hàng hai dropdown `Project label ↔ Model class`, chỉ hiện Project label
tương thích shape type của model class. Skeleton mở mapping keypoint riêng.

Run có `QUEUED/RUNNING/COMPLETED/FAILED/CANCELLED`, progress polling, cooperative
cancel, threshold, cleanup existing shapes và chặn nhiều active run trên cùng Task.

Hai runtime hiện có:

- YOLO26s Detection: 80 classes;
- YOLO26s Pose: 17 COCO keypoints.

Khởi động/discover spec:

```bash
make sync-auto-annotation
```

Runtime dùng GPU mặc định (`YOLO_DEVICE`, Compose `gpus: all`). Khi máy không có
GPU phải điều chỉnh Compose/env thay vì giả định service sẽ tự chạy CPU.

## 7. Quality, Training, AI Rules và contracts

### Quality

Quality đã có domain/model/UI đáng kể: immutable GT release/items, target,
inference model legacy, test case/run, evaluation dataset/class/model/run/frame.
Mục tiêu là so output AI + rule config với GT Annotation để chấm model/rule.
Một số evaluator/workflow còn là MVP và cần audit theo từng function trước khi gọi
là production-ready.

### Training

Hiện là base: `TrainingDataset`, `TrainingRun`, application service và Celery queue.
Luồng đích: nhận dataset artifact từ Annotation, phân tích FG/BG/brightness và chất
lượng dataset, train, rồi publish model artifact/version sang Model Registry.

### AI Rules

Hiện là base: `RuleDefinition`, `RuleRun`, application service và Celery queue.
Rule code sau này phải tuân thủ input/output message contract chung để Platform,
Quality và runtime có thể gọi/chấm thống nhất.

### Contracts/events

`control_plane/contracts/artifacts.py` và `control_plane/events/` là contract seam
trong monolith. Kafka broker thật chưa được triển khai. Khi tách repo cần version
schema, idempotency key, correlation/causation IDs, outbox/inbox và artifact URI +
checksum; không để các service import ORM của nhau.

## 8. Frontend

Frontend hiện là Django templates/MPA, không dùng React/Vue runtime. Design system
chung ở `control_plane/templates/base.html`; stylesheet canonical nằm tại
`control_plane/static/control_plane/ui.css`. Application shell và component skin
được refactor ngày 2026-08-20 theo hướng SaaS Linear × Vercel × Roboflow: một bộ
dark tokens duy nhất, compact navigation có active state, responsive mobile menu,
surface phẳng, form focus rõ, table/card/status/button thống nhất và theme guard
cho các template cũ còn style cục bộ. Component anatomy và responsive behavior
tham khảo Ant Design/Bootstrap 5 (1440 canvas, 8px rhythm, responsive containers,
vertical form item, table wrapper, button variants); visual skin theo Linear ×
Vercel × Roboflow. Job Canvas có layout riêng nhưng dùng chung
tokens để giữ mật độ của annotation tool. Tiếp tục ưu tiên workflow và interaction
đúng trước khi cân nhắc SPA; không thêm framework chỉ để đổi giao diện.

## 9. Testing và trạng thái working tree

Test Annotation gần nhất sau thay đổi skeleton/zoom:

```text
25 tests passed
Django system check: 0 issues
makemigrations --check: no changes detected
```

Luôn chạy trước khi bàn giao:

```bash
git diff --check
docker compose exec -T platform-web python manage.py makemigrations --check --dry-run
docker compose exec -T platform-web python manage.py test annotations.tests --noinput
docker compose exec -T platform-web python manage.py check
```

Working tree hiện có nhiều thay đổi chưa commit thuộc công việc người dùng đang
làm. Không reset, checkout hoặc ghi đè thay đổi ngoài phạm vi. Trước khi sửa file,
đọc `git status` và diff phần liên quan. Commit gần nhất khi lập handoff là
`4499ba9 update annotation tool`.

## 10. Khoản nợ và tài liệu có thể đã stale

- Một số docs cũ còn nhắc SQLite, YOLO-World, `qc_storage`, hai group hoặc đường
  dẫn `config/`/`templates/` ở root. Code/Compose hiện tại dùng PostgreSQL,
  YOLO26 auto annotation, `postgres_data` + `runtime_artifacts`, sáu role và
  `control_plane/config` + `control_plane/templates`.
- `README.md` vẫn chứa phần legacy YOLO-World và lệnh Python host; Docker-first
  trong file handoff này và Makefile là nguồn vận hành đúng hơn.
- Naming `ClientProject`/legacy `Project`, registry còn nằm một phần trong Quality,
  và boundary giữa Platform manifest với Annotation Project cần refactor tiếp.
- Kafka, object storage S3/MinIO, durable workflow/outbox và service repo split vẫn
  là kiến trúc đích, chưa phải chức năng đang chạy.

## 11. Cách bắt đầu ở chat mới

Prompt ngắn đề xuất:

```text
Đọc toàn bộ control_plane/docs/SESSION_HANDOFF.md và các file nó trỏ tới.
Kiểm tra git status, không làm mất thay đổi đang có. Tiếp tục yêu cầu gần nhất:
thêm Hand/Space-drag để pan frame đã zoom trong Annotation Job Canvas, cập nhật
docs, chạy Annotation tests và deploy/test bằng Docker.
```

Tài liệu chi tiết hơn nằm tại:

- `control_plane/docs/features/annotation-studio.md`
- `control_plane/docs/features/roles-and-permissions.md`
- `control_plane/docs/architecture/bounded-contexts.md`
- `control_plane/docs/architecture/target-platform.md`
- `control_plane/docs/operations/local-development.md`
