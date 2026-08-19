# Model Quality workspace

**Status:** Dataset ingestion, class mapping và detection/classification runner đã
được nối backend. Pose/segmentation được nhận diện nhưng evaluator chuyên biệt chưa
triển khai.

## Luồng chức năng

1. **Dataset**: upload ZIP hoặc folder theo cơ chế chunk.
2. **Inspect GT**: backend nhận diện YOLO, COCO hoặc classification folders; thống
   kê image, annotation, missing label và class rồi tạo `.qc/ground_truth.json`.
3. **Model & Mapping**: upload `.pt`, `.pth`, `.onnx`; GPU worker tự đọc class
   metadata rồi UI tạo card `model class → GT class` với dropdown.
4. **Evaluate**: Celery GPU worker inference toàn bộ ảnh và lưu metrics theo run.

`GET /model-quality/` là dashboard liệt kê customer projects, evaluation datasets,
recent runs, status và progress. Nút **Tạo evaluation task** mở wizard tại
`GET /model-quality/new/`; có thể truyền `?project=<id>` từ customer project.
Dataset, model và run đều gắn với owner trong cùng PostgreSQL của hệ thống.
`EvaluationDataset.client_project` liên kết bắt buộc trong luồng UI tới đúng
`ClientProject`. Model Evaluation không phụ thuộc `Rule`; rule thuộc module Rule
Automation. Không dùng model legacy `Project` (video annotation) làm customer project.

Mỗi row Evaluation Task có menu `⋯`. User owner có thể đổi tên task hoặc chuyển
task sang một Customer Project khác mà họ sở hữu. Xóa task sẽ xóa toàn bộ model,
run, output frame và thư mục dataset tương ứng trong volume. Hệ thống không cho
xóa khi còn run `QUEUED` hoặc `RUNNING` để tránh làm worker mất artifact giữa job.

## Chunked dataset upload

Không gửi toàn bộ dataset trong một HTTP request:

- Frontend tạo upload session tại `POST /api/model-quality/dataset-uploads/`.
- ZIP được cắt thành binary chunk 16 MiB.
- Folder được chia theo batch tối đa 250 file hoặc khoảng 64 MiB; từng file vẫn gửi
  `webkitRelativePath` để giữ cấu trúc.
- Chunk có index tuần tự. Gửi lại một index đã hoàn tất là idempotent, giúp retry khi
  client mất response.
- Mỗi chunk được retry tối đa ba lần với exponential backoff.
- `POST .../finalize/` chỉ enqueue parser. Celery worker giải nén, nhận diện format
  và normalize GT; UI poll `GET .../dataset-uploads/<id>/` tới `READY` hoặc `ERROR`.

Upload progress (`bytes`, chunk hiện tại) nằm trong `EvaluationDataset.manifest`.
File nằm tại `datasets` trong shared `qc_storage` volume; metadata nằm trong PostgreSQL. Mặc định
cho phép 2 triệu ZIP members và tối đa 2 TiB sau giải nén, có thể chỉnh bằng env.

Với production nhiều triệu file nên thay filesystem upload bằng S3/MinIO multipart
và manifest object storage. API session/chunk/finalize hiện tại là boundary để thay
storage backend mà không đổi wizard.

## Format và chuẩn hóa

- YOLO: `data.yaml`, `images/`, `labels/`.
- COCO: image files và annotation JSON có `images`, `annotations`, `categories`.
- Classification folders: mỗi folder class chứa image.

ZIP được kiểm tra path traversal, số member và tổng kích thước giải nén. Dataset
được chuẩn hóa về manifest GT chung trước evaluation.

## Class mapping

Mapping không sửa taxonomy gốc. Ví dụ model class `table → dining_table`, `mobile
phone → phone`; một model class có thể map `Ignore`. Mapping được lưu cùng
`EvaluationModel` và được snapshot vào evaluation run.

Sau khi nhận weight, web lưu artifact vào model volume với trạng thái `ANALYZING`
và enqueue `analyze_evaluation_model`. Worker đọc:

- `.pt`: metadata `names` và `task` qua Ultralytics.
- `.onnx`: `metadata_props` (`names`, `class_names` hoặc `classes`) qua ONNX.
- `.pth`: dictionary checkpoint an toàn (`weights_only=True`) và các key metadata
  phổ biến. Checkpoint kiến trúc tùy chỉnh không chứa class metadata sẽ trả `ERROR`.

UI poll model tới `READY`, hiển thị mỗi detected class thành card và tự chọn GT
class khi tên giống nhau sau khi bỏ space, `_` và `-`. Các tên khác để user chọn
trong dropdown; hệ thống không tự đoán mapping mơ hồ.

Upload model dùng progress theo byte từ `XMLHttpRequest`. Nút `×` abort request
đang gửi; nếu server đã tạo record thì endpoint delete xóa cả record và weight khi
model chưa có run. Trạng thái lỗi vẫn giữ nút `×` để dọn sạch và chọn lại cùng file.
Polling metadata retry lỗi kết nối tạm thời tối đa 10 lần để web reload ngắn không
làm một model đã upload thành lỗi giả trên giao diện.

## Execution

- `web`: nhận chunk, ghi shared dataset volume và quản lý API/UI; không dùng GPU.
- `worker`: Celery đọc cùng PostgreSQL/volume, parse dataset và chạy inference GPU.
- `redis`: broker/result backend.
- `db`: PostgreSQL dùng chung cho Annotation, Model Quality và các module sau.

Detection hiện tính precision, recall, F1 và TP/FP/FN theo class tại IoU 0.5.
Classification tính accuracy và per-class accuracy. `.pth` cần adapter kiến trúc cụ
thể; pose/segmentation hiện trả lỗi rõ ràng thay vì tạo metric giả.

Trong khi evaluation chạy, worker lưu live preview vào run khoảng mỗi 0,5 giây:
ảnh hiện tại, prediction bbox/class/confidence và Ground Truth bbox. Endpoint ảnh
preview kiểm tra owner của run; UI poll status và vẽ prediction màu xanh dương,
Ground Truth nét đứt màu xanh lá trên canvas. Preview chỉ phục vụ quan sát, không
tham gia tính metric và không làm thay đổi Ground Truth.

Sau khi tạo run, UI chuyển tới inference viewer toàn màn hình tại
`/model-quality/runs/<id>/`. Viewer dùng layout tương tự Annotation Studio: ảnh và
canvas lớn bên trái; progress, metadata, output frame và metrics bên phải. Chế độ
Live tự bám frame mới nhất, user có thể tắt Live để tua timeline các frame đã xử lý.

Mỗi output được lưu thành `ModelEvaluationFrame` gồm index, image path và JSON
prediction/GT. Vì vậy reload trang vẫn xem lại được từng frame. Có hai export:

- toàn bộ run dưới dạng JSONL, gồm summary và từng frame;
- riêng frame đang xem dưới dạng JSON.

Các endpoint viewer, ảnh và export đều lọc theo owner của run. Run cũ tạo trước
migration lưu frame chỉ có metrics/preview cuối; output từng frame áp dụng cho run
mới.
