# Freeflow — session handoff (2026-08-13)

## 1. Mục tiêu đã thống nhất

Xây một repo QC độc lập hoàn toàn với `safety-rules`, có giao diện Django và phân quyền người dùng. Hệ thống có hai hướng chính:

1. **Tạo Ground Truth (module đang triển khai)**
   - Input là video RAW.
   - QC nhập các class/prompt cần tìm.
   - YOLO-World inference để đề xuất bbox theo từng frame.
   - Người dùng approve/reject hoặc chỉnh class, prompt và bbox.
   - Trình duyệt frame hỗ trợ dừng/chạy, frame trước/sau, seek, chỉnh tốc độ.
   - Khi save/export, giữ nguyên video RAW và sinh bộ label GT.

2. **Đánh giá output pipeline (chưa triển khai)**
   - Bắn video RAW GT vào MediaMTX để restream.
   - Lắng nghe bbox từ Kafka topic `emagic.par`.
   - So sánh bbox/class model trả về với label GT.
   - Cho phép cấu hình phạm vi cần kiểm tra vì không phải video nào cũng label đầy đủ: class/bbox cần check, FPS/sample rate, frame range, IoU threshold và các điều kiện QC khác.

Repo hiện đang tạm nằm tại:

```text
/home/ai/Documents/staging/safety-rules/freeflow
```

Đây là **nested Git repo độc lập**, branch `main`; chưa commit. Người dùng xác nhận sẽ tách hẳn `freeflow` ra khỏi `safety-rules`, vì vậy không được tạo dependency bằng relative path tới parent repo và không được đưa module này vào Git history của `safety-rules`.

Đường dẫn trên chỉ là vị trí tạm thời. Sau khi tách, mọi lệnh phải chạy từ root mới của `freeflow`; code ứng dụng hiện không phụ thuộc vào tên/path của parent repo.

## 2. Trạng thái hiện tại

MVP Django đã chạy được tại:

```text
http://localhost:8090
username: admin
password: admin
```

Chỉ service `freeflow_web` đang chạy. Các service backend/build/pipeline khác đã được giữ ở trạng thái dừng để tránh lag.

Kết quả xác minh trong container:

- Django system check: pass.
- Django tests: 5/5 pass.
- HTTP `/login/`: 200.
- PyTorch: `2.7.1+cu128`.
- CUDA runtime: 12.8.
- GPU detected: NVIDIA GeForce RTX 5060.

## 3. Những gì đã code

### Backend và dữ liệu

- Django 5.1, SQLite cho MVP, Django auth/group.
- `Project`: video, owner, trạng thái, FPS, kích thước, frame count, coverage và current frame.
- `LabelClass`: tên class, prompt YOLO-World, màu và trạng thái enable.
- `BoxAnnotation`: frame, class, tọa độ bbox, confidence, source và audit user.
- Trạng thái annotation: `PREDICTED`, `APPROVED`, `REJECTED`, `EDITED`.
- Source: `YOLO_WORLD` hoặc `MANUAL`.
- Hai role bootstrap: `QC Annotator`, `QC Reviewer`.
- Project chỉ được truy cập bởi owner hoặc superuser.

### API/UI hiện có

- Đăng nhập/đăng xuất bằng Django auth.
- Tạo project, upload và probe metadata video.
- Hiển thị frame JPEG theo frame index.
- Đọc/lưu bbox JSON theo frame.
- Lưu danh sách class/prompt.
- Lazy-load YOLO-World và inference frame hiện tại.
- Canvas editor:
  - play/pause;
  - previous/next frame;
  - seek bằng timeline hoặc nhập frame;
  - tốc độ 0.25x, 0.5x, 1x, 2x, 4x;
  - thêm, chọn, kéo, resize bằng bốn corner handles và xóa bbox;
  - đổi class/trạng thái bbox;
  - approve/reject/edit prediction.
- Export JSONL chỉ gồm bbox đã review (`APPROVED`/`EDITED`), kèm SHA-256 của video RAW.
- Video upload gốc không bị encode/chỉnh sửa.

Các file trọng tâm:

```text
annotations/models.py       Data model
annotations/views.py        Web/API/export
annotations/inference.py    YOLO-World lazy loader/inference
annotations/video.py        Probe/extract video frame
templates/annotations/      UI project và canvas annotator
annotations/tests.py        Test quyền, save prompt/bbox, export
docker-compose.yml          Service freeflow độc lập
Dockerfile                  Python + CUDA-compatible PyTorch build
README.md                   Hướng dẫn sử dụng ngắn
```

## 4. Quyết định kỹ thuật quan trọng

- Không để `ultralytics` tự chọn PyTorch mới nhất. Lần build đầu đã resolve nhầm `torch 2.13 + CUDA 13`, rất lớn và không đồng bộ stack hiện tại; build đó đã được hủy.
- Dockerfile hiện khóa `torch==2.7.1`, `torchvision==0.22.1` từ PyTorch CUDA 12.8 index.
- Chỉ giữ `opencv-python==4.11.0.86`, tránh cài đồng thời OpenCV thường và headless.
- Runtime GPU khá lớn ở lần build đầu, nhưng đã nằm trong Docker cache. Không nên dùng `--no-cache` nếu chỉ sửa code/UI.
- Hiện dùng Django development server để QC MVP; chưa phải cấu hình production.
- Weight mặc định `yolov8s-worldv2.pt` được lazy-download ở lần inference đầu và lưu trong volume `qc_models`. Cần Internet cho lần tải đầu; chưa smoke-test inference bằng video thật.

## 5. Lệnh vận hành

```bash
cd /home/ai/Documents/staging/safety-rules/freeflow

# Bật module QC
docker compose up -d

# Xem log
docker compose logs -f web

# Chạy test
docker compose exec -T web python manage.py test

# Dừng riêng QC (không xóa data)
docker compose stop

# Rebuild sau khi đổi dependency/Dockerfile
docker compose up -d --build
```

Không chạy `docker compose down -v` nếu muốn giữ DB, video, label và model weight.

## 6. Test đã có

`annotations/tests.py` hiện kiểm tra:

1. Chưa đăng nhập bị redirect.
2. User khác không được mở project không thuộc sở hữu.
3. Owner lưu bbox được.
4. Owner lưu class/prompt được.
5. Export chỉ lấy annotation đã review và có hash video.

Chưa có browser/E2E test cho thao tác canvas và chưa test inference thực tế với video.

## 7. Việc nên làm tiếp theo

Ưu tiên ngay ở conversation mới:

1. Người dùng mở `http://localhost:8090`, upload một video ngắn và feedback UX thực tế.
2. Test lần inference YOLO-World đầu tiên, xác nhận weight được lưu đúng `/app/models` thay vì working directory; sửa nếu cần.
3. Kiểm tra mapping canvas ↔ độ phân giải gốc bằng video thật, đặc biệt khi resize trình duyệt.
4. Thêm autosave/dirty-state rõ ràng để đổi frame không làm mất chỉnh sửa.
5. Quyết định format GT cuối cùng (YOLO txt, COCO JSON, JSONL nội bộ, hoặc xuất đồng thời).
6. Thêm propagation/tracking bbox sang frame kế bên để giảm thao tác label thủ công.
7. Chuyển inference dài sang job queue và hiển thị progress; hiện inference chạy đồng bộ từng frame.
8. Thiết kế module MediaMTX + Kafka comparator độc lập với annotator:
   - test run/test case;
   - restream controller;
   - Kafka result collector/correlation;
   - GT sampler;
   - IoU/class matching;
   - metrics/report (precision, recall, missed/extra/wrong-class bbox);
   - cấu hình frame range/FPS/classes/expected bbox coverage.
9. Sau khi UX ổn mới chốt PostgreSQL, object storage, Celery/Redis và deployment production.

## 8. Lưu ý trước khi tiếp tục

- Tài khoản `admin/admin` chỉ dùng local; phải đổi khi đưa lên môi trường dùng chung.
- Nested repo đang có toàn bộ file ở trạng thái untracked. Kiểm tra rồi tạo initial commit trước khi phát triển tiếp.
- Volume hiện tại: `freeflow_qc_data`, `freeflow_qc_media`, `freeflow_qc_models`.
- Không bật lại toàn bộ safety pipeline chỉ để test annotator; module này có thể chạy độc lập.

## 9. Feedback và bugfix sau lần bàn giao đầu

### Bug inference không hiện bbox

Người dùng đã upload video thật và bấm infer nhưng không thấy bbox. Log xác nhận request inference trả HTTP 500, trong khi JavaScript cũ bỏ qua HTTP status rồi reload frame nên trông giống như model chạy xong nhưng không detect.

Nguyên nhân cụ thể:

```text
ModuleNotFoundError: No module named 'clip'
```

`YOLOWorld.set_classes()` cần CLIP text encoder. Ultralytics cố tự cài từ GitHub nhưng image không có `git`, nên thất bại.

Đã sửa:

- Thêm `openai-clip==1.0.1` vào requirements.
- Frontend kiểm tra HTTP status và hiển thị lỗi inference rõ ràng.
- Hiển thị trạng thái đang xử lý và số bbox tìm được.
- Backend bắt exception, log stack trace và trả JSON error thay vì HTML 500.
- Model path tương đối được chuyển vào `/app/models`; volume `qc_models` giữ weight qua restart.
- Tách layer cài PyTorch/CUDA khỏi `requirements.txt` trong Dockerfile để các lần đổi package/UI sau dùng lại cache GPU.

Đã chạy inference thật trên project 1, frame 0:

- HTTP 200.
- YOLO-World tạo và lưu 6 bbox.
- Sau recreate container, 6 bbox vẫn còn.
- GPU vẫn nhận RTX 5060/CUDA 12.8.

CLIP có tải thêm text encoder khoảng 338 MB ở lần đầu. YOLO World weight `yolov8s-worldv2.pt` khoảng 24.7 MB. Hai weight này phải nằm trong `qc_models`.

### Cải tiến giao diện đã hoàn thành và chạy

- Theme/UI chung được làm lại dễ đọc hơn.
- Form tạo project chia rõ project metadata và class configuration.
- Một class/prompt là một card riêng.
- Có nút thêm/xóa class khi tạo project.
- Annotator sidebar được sắp xếp lại.
- Hiển thị notice thành công/lỗi sau inference.
- Hiển thị tổng bbox trên frame.

### Prompt YOLO-World đã thảo luận

Ngữ cảnh thật là camera góc cao trong nhà hàng, nhiều bàn bị chén đĩa, khăn ăn và hoa che mặt bàn. Prompt dài chứa nhiều phủ định làm embedding bị loãng; YOLO-World không hiểu các câu loại trừ giống LLM.

Class thống nhất:

```text
dining table
```

Prompt đang được khuyến nghị thử:

```text
visible restaurant tabletop, empty or prepared with tableware and flower decorations
```

Các prompt ngắn nên thử riêng nếu cần:

```text
dining table
restaurant table
set restaurant dining table
table with place settings
empty restaurant tabletop
restaurant table with tableware
restaurant table with plates and flower decorations
```

Không nên nhồi `exclude chairs, plates...` vào prompt. Nếu model luôn vẽ bbox không đúng ranh giới bàn thì sửa bằng QC bbox hoặc fine-tune, không kỳ vọng text prompt xử lý hoàn toàn.

## 10. Thay đổi mới nhất đã code nhưng CHƯA đưa vào container

Người dùng yêu cầu thêm:

1. Cho phép infer một frame hoặc toàn video.
2. Mỗi class có confidence riêng, gồm slider và ô nhập số đồng bộ.
3. Danh sách bbox có ID dễ đối chiếu.
4. Có nút xóa toàn bộ bbox trên frame thay vì xóa từng bbox.

Source local đã được chỉnh cho các chức năng trên, nhưng người dùng đã dừng command rebuild/migrate để chuyển conversation. Vì vậy cần hiểu chính xác:

- Source code local: đã có thay đổi.
- Kiểm tra local: `manage.py check` pass, 6/6 tests pass, `makemigrations --check` báo không thiếu migration, `git diff --check` pass.
- Container `freeflow_web` hiện tại: vẫn là image trước các thay đổi mới nhất.
- Database volume hiện tại: chưa apply migration `0002_labelclass_confidence`.
- Chưa browser-test UI mới và chưa test infer toàn video.

Các thay đổi source cụ thể:

### Confidence riêng từng class

- Thêm `LabelClass.confidence`, default `0.25`.
- Migration mới: `annotations/migrations/0002_labelclass_confidence.py`.
- Form tạo project lưu mỗi dòng nội bộ theo dạng:

```text
class name | YOLO prompt | confidence
```

- Card class lúc tạo project có slider `0.01..1.00` và ô number đồng bộ.
- Card class trong annotator cũng có slider và ô number.
- API `save_classes` validate/clamp confidence trong `[0.01, 1.00]`.
- Inference gọi model với threshold thấp nhất của các class đang bật, rồi lọc mỗi result bằng confidence riêng của class tương ứng. Đây là cần thiết vì Ultralytics nhận một `conf` chung cho lần predict.

### Infer một frame/toàn video

- Nút `Infer frame` giữ luồng hiện tại.
- Nút `Infer entire video` đã thêm vào frontend.
- Phiên bản MVP chạy tuần tự từng frame ở browser, mỗi frame là một HTTP request riêng.
- Có progress bar, số frame đã chạy, tổng bbox và nút `Dừng`.
- Khi xong/dừng/lỗi, quay lại frame người dùng đang xem.
- Prediction cũ trạng thái `PREDICTED` trên mỗi frame bị thay thế; bbox đã được human review được giữ nguyên theo logic backend hiện tại.

Lưu ý: đây chỉ là MVP. Video dài sẽ tạo rất nhiều request và không sống được nếu browser đóng. Bản đúng cho production cần background job Celery/RQ, job model, progress API, cancel flag và retry/resume.

### Bbox ID và xóa toàn bộ

- Danh sách hiển thị `BBox #<database-id>`.
- Bbox manual chưa save hiển thị `BBox new-<index>`.
- Có nút `Xóa toàn bộ` trên frame.
- Có hộp xác nhận số bbox trước khi xóa.
- Xóa list rồi gọi API save với `boxes: []`; backend hiện tại sẽ xóa toàn bộ DB bbox thuộc frame.
- Đã thêm test xác minh save frame rỗng xóa hết bbox frame đó.

## 11. Lệnh bắt buộc chạy đầu tiên ở conversation mới

Sau khi đọc file này, cần hoàn tất deployment source mới bằng:

```bash
cd /home/ai/Documents/staging/safety-rules/freeflow
docker compose up -d --build web
docker compose exec -T web python manage.py migrate
docker compose exec -T web python manage.py test
```

Sau đó xác minh:

```bash
docker compose exec -T web python manage.py shell -c "from annotations.models import Project; p=Project.objects.get(pk=1); print([(c.name, c.confidence) for c in p.classes.all()]); print('frame_0_boxes=', p.boxes.filter(frame_index=0).count())"
curl --retry 5 --retry-delay 1 -I http://127.0.0.1:8090/login/
```

Tiếp theo browser-test theo thứ tự:

1. Hard refresh `Ctrl+Shift+R`.
2. Mở project 1 và xác nhận 6 bbox frame 0 còn tồn tại.
3. Thay confidence từng class, lưu và reload để xác nhận persistence.
4. Infer một frame và đối chiếu bbox count/ID.
5. Xóa toàn bộ bbox trên một frame test rồi reload.
6. Chạy `Infer entire video` trên video ngắn hoặc dừng sớm để test progress/cancel.
7. Kiểm tra inference toàn video không xóa bbox `APPROVED`/`EDITED`.

## 12. Rủi ro/thiết kế cần xử lý tiếp

- Infer toàn video hiện inference mọi frame. Với video FPS cao đây là rất tốn thời gian và label gần như trùng nhau. Cần thêm `sample every N frames`, target FPS hoặc time interval.
- YOLO model dùng lock toàn process; requests inference chạy tuần tự trong một process. Không nên mở nhiều batch song song.
- Dev server không phù hợp batch dài.
- Cần thiết kế trạng thái project/job: queued, running, cancel requested, completed, failed.
- Cần quyết định nếu re-infer có giữ `REJECTED` hay chỉ giữ `APPROVED/EDITED`. Code hiện chỉ xóa `PREDICTED`, do đó `REJECTED` cũng được giữ lại.
- Class name đang unique trong project; chưa có alias/multiple prompts map về cùng class. Đây có thể cần thiết cho `dining table` vì nhiều biến thể hình ảnh.
- Confidence class mới chỉ tác động inference mới; không tự xóa prediction cũ dưới threshold khi thay config.
- Canvas/playback hiện tải từng JPEG frame qua Django/OpenCV, không phù hợp video 24 giờ. Cần proxy video/segment cache hoặc seek architecture tốt hơn.
- Export hiện chỉ JSONL nội bộ. Chưa có YOLO txt/COCO JSON.
- Chưa có autosave/job recovery hoàn chỉnh.
- Chưa có MediaMTX restream/Kafka `emagic.par` comparator; đó vẫn là phase 2.

## 13. Tóm tắt phase 2: QC output model/pipeline

Mục tiêu cuối của repo không chỉ là annotator. Sau khi có RAW GT + label GT, cần:

```text
RAW GT video
  -> MediaMTX restream
  -> DeepStream/model pipeline
  -> Kafka emagic.par bbox events
  -> correlate frame/timestamp/camera/test run
  -> compare prediction với GT
  -> QC report
```

Config test case dự kiến gồm:

- input video và camera/stream ID giả lập;
- FPS gốc, FPS restream và FPS/frame sampling cần đánh giá;
- coverage `partial`/`exhaustive`;
- frame/time ranges có label;
- classes/bbox cần check;
- IoU threshold theo class;
- confidence threshold;
- timestamp tolerance;
- ignore regions/ignored labels;
- expected count nếu applicable.

Ý nghĩa coverage:

- `Partial`: GT chỉ label chọn lọc; prediction không match GT chưa chắc là false positive. Chủ yếu đo model có tìm thấy các GT đã khai báo không.
- `Exhaustive`: GT đã đầy đủ trong phạm vi QC; có thể kết luận bbox dư là false positive và tính precision/recall đầy đủ.

Metrics/report nên có:

- true positive, false negative, false positive;
- wrong class;
- IoU distribution;
- precision/recall/F1 theo class và tổng;
- missed/extra bbox gallery theo frame;
- latency/timestamp mismatch;
- traceability tới test run, video hash, model/config version.

## 14. Tách `freeflow` khỏi `safety-rules`

### Ranh giới repository

`freeflow` phải là một sản phẩm/repo độc lập:

- Git repository riêng.
- Docker Compose project riêng: `freeflow`.
- Database/media/model volumes riêng.
- Dependency/README/env/migrations/tests riêng.
- Không import Python module từ `safety-rules`.
- Không mount source/config từ `safety-rules`.
- Tích hợp MediaMTX/Kafka về sau chỉ qua protocol/config, không copy logic nội bộ bằng relative import.

### Trạng thái Git trước khi tách

Nested repo đã có `.git` riêng nhưng chưa có initial commit; toàn bộ file đang untracked. Conversation mới nên kiểm tra:

```bash
cd /home/ai/Documents/staging/safety-rules/freeflow
git status
git rev-parse --show-toplevel
```

Sau khi review source, nên tạo initial commit **bên trong nested repo trước khi di chuyển** để có mốc khôi phục:

```bash
git add .
git commit -m "feat: bootstrap standalone Freeflow studio"
```

Không chạy `git add freeflow` từ root `safety-rules`.

### Di chuyển source

Nên dừng riêng service QC trước khi di chuyển, không xóa volume:

```bash
cd /home/ai/Documents/staging/safety-rules/freeflow
docker compose stop
```

Sau đó move cả thư mục `freeflow`, bao gồm `.git`, sang vị trí repo mới. Không dùng `docker compose down -v`.

Ví dụ đích (chỉ là gợi ý, cần người dùng xác nhận path thực tế):

```text
/home/ai/Documents/staging/freeflow
```

Sau khi move:

```bash
cd /path/to/new/freeflow
git rev-parse --show-toplevel
docker compose up -d --build web
```

### Docker volume khi đổi vị trí repo

Compose đã khai báo cố định:

```yaml
name: freeflow
```

Do đó đổi đường dẫn thư mục không làm đổi Compose project name. Các volume cũ vẫn là:

```text
freeflow_qc_data
freeflow_qc_media
freeflow_qc_models
```

Nếu giữ nguyên `name: freeflow`, compose tại path mới sẽ dùng lại các volume trên, nên DB, video RAW, bbox và model weights không bị mất.

Trước và sau khi move nên xác minh:

```bash
docker volume ls | grep freeflow
docker compose config --volumes
docker compose up -d
docker compose exec -T web python manage.py migrate
```

Không đổi Compose project name trong lúc move. Nếu muốn đổi tên volumes/repo về sau, phải backup/restore riêng.

### Dữ liệu cần backup trước khi tách

Tối thiểu cần giữ:

- `qc_data`: SQLite DB.
- `qc_media`: video RAW upload.
- `qc_models`: YOLO-World và CLIP weights.
- source repo bao gồm `.git` sau initial commit.

Docker volumes không nằm trong thư mục source, nên thao tác move source không tự mang data sang máy khác. Nếu chỉ đổi folder trên cùng máy thì chúng vẫn còn. Nếu chuyển sang máy/server khác thì phải export/import volumes hoặc chuyển sang bind mounts/object storage trước.

### File cấu hình cần bổ sung sau khi tách

Repo độc lập nên có thêm:

- `.env.example` cho `QC_PORT`, Django secret/debug, model/device/confidence.
- `Makefile` hoặc scripts riêng: `up`, `down`, `test`, `migrate`, `logs`, `create-admin`.
- Production compose tách khỏi development compose.
- License/ownership và remote Git riêng.
- CI chạy Django check, migrations check và tests mà không cần GPU; inference GPU integration test chạy riêng.

### Những thứ không được mang từ `safety-rules`

- Database, Redis, Celery hoặc Kafka consumer của safety backend nếu module QC chưa thực sự cần.
- Reset scripts có khả năng xóa recordings/evidence của safety pipeline.
- Docker networks dùng chung không cần thiết.
- Hardcoded paths trỏ về `/home/ai/Documents/staging/safety-rules`.

Phase MediaMTX/Kafka sau này có thể dùng compose profile/integration compose riêng, nhưng core annotator vẫn phải chạy độc lập chỉ với Django + GPU.
