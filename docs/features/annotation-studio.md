# Annotation Studio

**Status:** Implemented — bounding-box annotation cho video.

Annotation Studio là giao diện tạo và review Ground Truth trên từng video asset.
Trong domain hiện tại, video asset vẫn dùng model Django `annotations.Project` để
tương thích với dữ liệu cũ; nó thuộc một customer workspace qua
`Project.client_project`.

## Phạm vi hiện tại

- Upload video RAW và đọc metadata bằng OpenCV: width, height, FPS, frame count.
- Khai báo class, prompt inference, confidence threshold và trạng thái enable.
- Chọn inference model riêng theo từng user.
- Infer frame hiện tại hoặc infer tuần tự toàn bộ video.
- Vẽ, chọn, di chuyển, resize, đổi class và xóa bounding box trên canvas.
- Review bbox bằng các trạng thái `PREDICTED`, `APPROVED`, `REJECTED`, `EDITED`.
- Lưu tiến độ theo frame và tiếp tục từ `current_frame`.
- Export annotation đã review thành JSONL.
- Freeze annotation đã review thành Ground Truth release bất biến trong Quality Lab.

Temporal segment, polygon/mask, keypoint/pose và workflow phân công reviewer chưa
được triển khai.

## Tạo video annotation

Video được thêm từ trang chi tiết customer project. Form yêu cầu:

- tên video dataset;
- file video RAW;
- coverage `Partial` hoặc `Exhaustive`;
- ít nhất một class;
- mỗi class có `name`, prompt tiếng Anh và confidence từ `0.01` đến `1.00`.

Sau upload, backend dùng `annotations.video.probe()` để đọc metadata và tạo
`LabelClass`. Video được gắn với `ClientProject` đã chọn rồi chuyển thẳng tới
annotator.

## Quản lý class trong annotator

Panel **Classes & YOLO prompts** hỗ trợ:

- thêm class mới;
- sửa name, prompt, confidence và trạng thái dùng khi infer;
- xóa class;
- đồng bộ slider confidence với numeric input;
- lưu tất cả thay đổi bằng một request.

Project phải còn ít nhất một class ở phía giao diện. Khi xóa class đã tồn tại,
giao diện yêu cầu xác nhận; backend xóa các `BoxAnnotation` tham chiếu class đó
trước khi xóa class để không tạo dữ liệu mồ côi.

Confidence được render bằng định dạng không-localize (`0.37`, không phải `0,37`)
để HTML `range` và `number` giữ đúng giá trị sau khi reload.

## Thao tác frame và bbox

Annotator hiển thị frame trên HTML canvas theo kích thước gốc của video:

- kéo trên vùng trống để tạo bbox với class đang chọn;
- click bbox để chọn;
- kéo bbox để di chuyển;
- kéo bốn góc để resize;
- dùng **Áp dụng** để đổi class của bbox đang chọn;
- nhấn `Delete` hoặc nút `×` để xóa bbox;
- **Xóa toàn bộ** xóa mọi bbox trên frame sau khi xác nhận;
- phím `←`/`→` chuyển frame, `Space` phát hoặc dừng;
- timeline, frame number và playback speed hỗ trợ điều hướng video.

Bbox tạo thủ công có source `MANUAL` và trạng thái `EDITED`. Bbox bị chỉnh sửa
được chuyển sang `EDITED`. Khi chuyển frame, thay đổi chưa lưu được gửi lên server
trước khi tải frame tiếp theo.

API lưu frame thay thế toàn bộ tập bbox của frame bằng payload hiện tại. Vì vậy
bbox không còn trong payload sẽ bị xóa khỏi database.

## Inference

User có thể chọn một `InferenceModel` đang enabled và ready. Lựa chọn được lưu ở
`UserInferencePreference`, độc lập giữa các tài khoản. `System default` để backend
dùng adapter mặc định.

Khi infer, chỉ các class có `enabled=True` được gửi vào adapter. Mỗi class cung cấp:

- label name;
- natural-language prompt;
- confidence threshold riêng.

### Infer một frame

Backend đọc frame bằng OpenCV, gọi adapter qua `annotations.inference.predict()`,
xóa proposal `PREDICTED` cũ trên frame và lưu proposal mới. Bbox đã được human
review (`APPROVED`, `REJECTED`, `EDITED`) được giữ nguyên.

### Infer toàn bộ video

Frontend gọi API infer lần lượt từ frame `0` đến frame cuối, hiển thị số frame và
bbox đã xử lý, đồng thời cho phép dừng. Đây hiện là tiến trình chạy trong browser:

- chưa có background worker hoặc queue;
- đóng/reload tab sẽ dừng vòng lặp;
- chưa có resume checkpoint tự động;
- thời gian xử lý tăng tuyến tính theo số frame.

Khi đưa vào production, luồng này cần chuyển sang job queue và lưu trạng thái job
ở server.

## Review status

| Status | Ý nghĩa | Được export/freeze |
| --- | --- | --- |
| `PREDICTED` | Proposal chưa được người kiểm tra xác nhận | Không |
| `APPROVED` | Bbox đã được duyệt | Có |
| `REJECTED` | Proposal bị từ chối | Không |
| `EDITED` | Bbox thủ công hoặc đã được người dùng chỉnh | Có |

## Export và Ground Truth release

**Export approved GT JSONL** chỉ lấy `APPROVED` và `EDITED`, group theo frame và
trả về mỗi dòng gồm video, frame index, timestamp và danh sách object. Response có
header `X-Video-SHA256` để truy vết đúng file video nguồn.

Freeze trong Quality Lab tạo `GroundTruthRelease` version kế tiếp và copy dữ liệu
sang `GroundTruthItem`. Release đã freeze không thay đổi khi bbox nguồn được sửa
sau đó.

## Quyền truy cập

- User phải đăng nhập.
- Owner video được annotation và chỉnh sửa.
- Superuser hoặc user có permission `annotations.edit_all_projects` có thể thao
  tác trên mọi video.
- User khác nhận HTTP `403` khi cố chỉnh sửa video không thuộc quyền.

## Endpoint chính

| Method | Endpoint | Chức năng |
| --- | --- | --- |
| `GET` | `/projects/<id>/annotate/` | Mở Annotation Studio |
| `GET` | `/projects/<id>/frames/<frame>.jpg` | Đọc ảnh của frame |
| `GET` | `/api/projects/<id>/frames/<frame>/` | Đọc bbox của frame |
| `POST` | `/api/projects/<id>/frames/<frame>/infer/` | Infer và lưu proposal |
| `POST` | `/api/projects/<id>/frames/<frame>/save/` | Lưu toàn bộ bbox của frame |
| `POST` | `/api/projects/<id>/classes/save/` | Thêm, sửa và xóa class |
| `GET` | `/projects/<id>/export/jsonl/` | Export reviewed GT |

## Giới hạn cần xử lý tiếp

- `annotations.Project` vẫn là tên model legacy cho video asset; nên rename trong
  một migration riêng khi API ổn định.
- CRUD class đang dùng một batch endpoint, chưa có optimistic locking/version để
  xử lý hai reviewer sửa đồng thời.
- Xóa class sẽ xóa bbox liên quan; chưa có soft-delete hoặc audit log.
- Autosave hiện xảy ra khi chuyển frame, nhưng chưa có debounce autosave trong lúc
  đang chỉnh bbox.
- Infer toàn video chưa chạy nền và chưa có retry theo frame.
- Chưa có video sampling policy, scene selection hoặc active-learning queue.
- Chưa có undo/redo và keyboard shortcut help đầy đủ.
