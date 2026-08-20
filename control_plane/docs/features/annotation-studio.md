# Annotation Studio

**Status:** Implemented — CVAT-inspired Project → Task → Job canvas MVP.

## Domain workflow

1. `AI Admin` tạo Annotation Project.
2. Project sở hữu labels, attributes, skeleton points/edges và AI rules.
3. `Data Annotator` tạo Task trong Project, chọn rules, assignees và reviewers.
4. Data có thể upload ngay trong form tạo Task hoặc bổ sung sau. Theo invariant
   của CVAT, mỗi lần ingest nhận một video, một ZIP ảnh, hoặc nhiều ảnh/folder;
   không trộn nguồn unique với tập ảnh.
5. Annotator mở Job Canvas. Canvas luôn đọc label schema của Project.

Data Annotator và root có thể chỉnh sửa Task sau khi tạo: tên, mô tả, rules,
assignees, reviewers, trạng thái và upload thêm data. Label schema trong form là
readonly vì Task kế thừa trực tiếp Project labels; chỉ root sửa schema tại Project
để không sinh hai nguồn label lệch nhau. Xóa Task yêu cầu confirm và cascade toàn
bộ Jobs, shapes, runs, media nguồn và frame manifest của Task.

## Data ingestion

Input local hiện hỗ trợ ảnh rời/folder, ZIP chứa ảnh và video. Ảnh trong folder
hoặc ZIP được natural-sort theo đường dẫn (`2.jpg` trước `10.jpg`). ZIP được kiểm
tra path traversal, encryption, số file và tổng dung lượng giải nén trước khi đọc.

Khác với CVAT giữ video làm nguồn interpolation, hệ thống này materialize video
thành từng JPEG frame ngay khi ingest. Mọi nguồn sau đó dùng chung
`IMAGE_SEQUENCE`, frame manifest, Canvas frame API và Automatic Annotation frame
reader. File video gốc vẫn được lưu để truy xuất nguồn/audit. Xóa data sẽ xóa cả
nguồn gốc và các frame đã materialize.

CVAT reference used: `engine.models.Project/Task/Job/Label/Skeleton/AttributeSpec`,
`Task.get_labels()`, project/task serializers, permission scopes, labels editor,
skeleton configurator and canvas skeleton draw/render handlers.

## Project Constructor

Root UI có `Constructor` và `Raw`. Mỗi label gồm `name`, `color`, `type` và
attributes; skeleton label có ordered points và edges. Raw tương thích JSON array
của CVAT, gồm `attributes`, `sublabels` và `svg`; các ID từ CVAT được bỏ qua khi
tạo Project mới. Trang `Chỉnh sửa project` nạp lại schema đã persist vào cả
Constructor và Raw, để Root có thể dán/chỉnh JSON CVAT hoặc thao tác trực quan.
Model prompt không thuộc Project schema và sẽ được xử lý ở feature model-label
mapping sau. Rule được tạo cùng Project.

Project detail hiển thị swatch, mã màu và loại của từng label từ dữ liệu đã persist,
không sinh lại màu ở frontend. AI Admin có thể sửa name/type/color hoặc xóa từng
label. Giống contract của CVAT, xóa label đã lưu yêu cầu confirm rằng toàn bộ
annotation tham chiếu label cũng bị xóa; backend thực hiện trong transaction. Đổi
type bị chặn với skeleton hoặc label đã có annotation để tránh làm sai shape schema.
Sửa name/color của skeleton không làm mất attributes, points hay edges. Khi lưu
toàn bộ schema, label giữ nguyên name/type sẽ giữ annotation; xóa, đổi tên hoặc
đổi type phải xác nhận vì annotation dùng label bị thay đổi sẽ bị xóa. Data
Annotator chỉ được xem schema và nhận 403 trên endpoint edit/delete.

## Job Canvas

Canvas có toolbar Select, BBox và Skeleton; panel phải hiển thị object list,
attribute editor và nút cấu hình shortcut cá nhân (không hiển thị danh sách Project
labels cố định). Shortcut được lưu theo User, gồm toàn bộ tool/action button:
Select `V`, Hand `H`, BBox `N`, Skeleton `S`, Save `Ctrl+S`, Undo/Redo
`Ctrl+Z/Y`, Zoom, Fit, previous/next frame, play/pause và Delete. Mặc định
`Space` play/pause chuỗi frame như video; Hand tool được dùng để pan bằng kéo
chuột, tránh xung đột với playback. BBox lưu bốn tọa độ. Skeleton lưu ordered named
points và render edges từ Project schema. API thay toàn bộ shapes của frame trong
một transaction.

Canvas dùng viewport cố định bằng đúng phần màn hình còn lại của Annotation
Studio. Ảnh/frame luôn được scale theo `contain`, giữ nguyên aspect ratio và nằm
giữa nền canvas; ảnh không làm layout nở theo kích thước gốc. Drawing buffer giữ
tọa độ pixel ảnh thật, còn CSS display size được tính lại bằng `ResizeObserver`,
vì vậy resize cửa sổ không làm lệch bbox/skeleton. Stroke, keypoint và hit radius
được bù theo display scale để luôn đủ rõ khi xem ảnh độ phân giải lớn.

Trong Select mode, annotator có thể kéo bên trong bbox để di chuyển, kéo tám handle
cạnh/góc để resize, và kéo trực tiếp skeleton point. Canvas UX áp dụng các
pattern cốt lõi tham khảo từ CVAT: bbox có 8 resize handles và label badge, mỗi
skeleton point hiển thị point name và màu riêng lấy từ Project schema. Constructor
tự cấp palette màu khác nhau cho point mới, cho phép đổi từng màu, đồng thời giữ
nguyên màu sublabel khi import Raw CVAT. Schema cũ có các point đồng màu được canvas
hiển thị bằng palette fallback. Object active có control points rõ ràng; click point
để chọn, kéo để đổi vị trí, nhập X/Y hoặc xóa riêng point đó. Zoom/fit độc lập với
tọa độ ảnh; cuộn chuột zoom neo tại đúng vị trí con trỏ. Canvas có undo/redo history,
unsaved-state guard và keyboard shortcuts gọn cho tool/save/delete/frame navigation. Chọn Project
label khác khi object đang selected sẽ đổi label nếu cùng shape type. Nút Delete
object hoặc phím Delete/Backspace xóa object đang chọn. Nếu một skeleton point đang
được chọn, Delete/Backspace (hoặc nút `Xóa point này`) chỉ xóa point đó khỏi
shape ở frame hiện tại, không xóa cả skeleton. Khi pose thiếu point, chọn skeleton,
chọn point còn thiếu ở panel phải rồi click lại vị trí trên ảnh để đặt point đó.
Tạo pose mới dùng thao tác kéo vùng như bbox; vùng chỉ làm layout tạm, không được
lưu hoặc hiển thị thành viền bbox, còn các keypoint được tạo theo layout schema bên
trong vùng. Canvas giữ snapshot draft
của nhiều frame trong bộ nhớ trang: annotator có thể chuyển qua hàng chục frame và
dùng `Ctrl+S`/`Save changes` để ghi batch từng frame. Chỉ lúc rời/reload Job khi
còn draft mới hiện browser unsaved-change guard. Object panel theo pattern CVAT
card: mỗi annotation có màu/label/type,
source/confidence, dropdown đổi label tương thích cùng shape type, lock/unlock,
hide/show, focus vào object và xóa trực tiếp. Lock chặn kéo/resize/sửa point và
attribute; hide chỉ ẩn object khỏi canvas, không xóa dữ liệu. Cả hai state được
lưu cùng shape attributes. Attributes chỉ mở khi bấm `Details` và bung ngay bên
dưới trong chính object card cùng màu, theo pattern CVAT. Toolbar có Hand tool (`H`) và giữ `Space` + kéo để pan ảnh đã
zoom, không xung đột Select/BBox/Skeleton. BBox là one-shot: bấm BBox hoặc `N`,
kéo hai góc chéo để tạo một shape, rồi tool tự về Select; blur/tab hoặc rời canvas
khi đang vẽ sẽ hủy draft dang dở. Chuột phải lên shape mở menu đổi label cùng type
hoặc xóa object.

Endpoints mới:

- `GET /annotation/jobs/<id>/`
- `GET /api/annotation/jobs/<id>/frames/<frame>/`
- `POST /api/annotation/jobs/<id>/frames/<frame>/save/`

Legacy manual bbox storage còn được giữ tạm cho các Ground Truth release cũ;
prompt inference endpoints đã bị xóa. Bước tiếp theo của canvas là polygon/mask,
autosave, undo/redo và job frame split.

## Automatic Annotation

Automatic Annotation đã chuyển sang luồng `Task → AutoAnnotationRun → Jobs →
AnnotationShape`. AI Admin đăng ký remote function tại `/system/auto-annotation/`
với endpoint, loại model và label `spec` tương thích CVAT. Data Annotator chạy
function trong trang chi tiết Task, chọn threshold, cleanup và mapping nâng cao.
Worker gửi bytes frame gốc/base64, theo dõi progress và ghi rectangle hoặc
skeleton trực tiếp vào canvas mới. Với `IMAGE_SEQUENCE`, bytes được đọc thẳng từ
frame manifest, không decode rồi JPEG-encode thêm lần nữa để tránh làm giảm độ
nhạy của small object như `cell phone`. Video legacy không có manifest mới dùng
fallback encode một lần.

Mapping mặc định dùng tên + loại label. Skeleton mapping tiếp tục map từng
model keypoint sang Project skeleton point; không có class hay keypoint nào được
hardcode trong Annotation service. Detection và Pose là hai function độc lập.
Run hỗ trợ trạng thái QUEUED/RUNNING/COMPLETED/FAILED/CANCELLED, progress polling,
cancel cooperative và giới hạn một active run trên mỗi Task.

Task UI không yêu cầu người vận hành viết mapping JSON. Khi đổi model function,
giao diện dựng card hai dropdown theo từng hàng `Project label ↔ Model class`, tự
chọn mapping cùng tên/tương thích loại và cho phép bỏ qua class. Khi đích là
skeleton, card mở thêm các hàng `Project skeleton point ← Model keypoint`. Form
serialize lựa chọn thành mapping contract cũ trong hidden field để validation và
worker không phụ thuộc frontend.

Data Annotator có quyền vận hành toàn bộ Task/Job trong Annotation domain, kể cả
Task do root hoặc annotator khác tạo và chưa assign, để hỗ trợ team lead phân công.
Quyền này không bao gồm tạo/sửa Project, label schema hay AI rule. QA/QC Engineer
vẫn chỉ truy cập Task được assign reviewer hoặc do chính họ tạo.

### Runtime YOLO26 local

Docker Compose có hai GPU services độc lập trên network `freeflow_default`:

- `annotation-yolo26-detection`: YOLO26s Detection, publish spec 80 classes;
- `annotation-yolo26-pose`: YOLO26s Pose, publish spec 17 COCO keypoints.

Image `freeflow/annotation-yolo26:dev` kế thừa CUDA/PyTorch từ Annotation worker
nhưng pin `ultralytics==8.4.121`, vì bản 8.3.94 không deserialize được layer
`Pose26`. Runtime endpoints nội bộ là `/health`, `/spec` và `/infer`; không expose
port ra host. Detection không lọc class. Pose point names nằm trong service config,
được registry discover qua `/spec` và mapping theo tên vào Project skeleton.

Khởi động và đồng bộ registry:

```bash
make sync-auto-annotation
```

Lệnh trên bật hai model services rồi chạy `sync_auto_annotation_functions` trong
Platform container. Có thể chạy lặp lại để cập nhật spec mà không tạo record trùng.

E2E smoke test ngày 2026-08-18 dùng `hp_14.jpg`: Detection trả person rectangle
confidence khoảng 0.958; Pose trả một `person_pose`. Celery run ghi một rectangle
và một skeleton 11 points vào Task `Auto Annotation E2E` của Project `Sample`;
17 model keypoints được thu gọn đúng theo 11 Project points qua mapping tên.

Prompt inference legacy đã bị loại bỏ: hai trường `LabelClass.prompt` và
`BoxAnnotation.prompt`, endpoint infer-frame, class/prompt editor và worker task
cũ không còn tồn tại. URL annotator legacy chỉ redirect video đã thuộc Job sang
Job Canvas; video legacy không thuộc Task/Job trả 404. Bảng model preference của
Quality được giữ lại để tránh migration mất dữ liệu ngoài bounded context, nhưng
Annotation không còn đọc hay ghi bảng này.

## Frontend shell

Giao diện dùng Django templates với design system SaaS nội bộ theo hướng Linear ×
Vercel × Roboflow. `control_plane/templates/base.html` là nguồn duy nhất cho color
tokens, application navigation, form controls, buttons, cards, tables, badges,
empty states và responsive breakpoints. Shell có active navigation và mobile menu;
theme guard giữ các trang legacy dùng chung palette trong lúc lần lượt loại bỏ CSS
hardcode. Project detail, Task list và Task detail dùng các component chung này;
màn Job Canvas giữ layout toàn màn hình nhưng dùng cùng tokens để không lệch phong
cách. Không thêm React/Vue runtime ở giai đoạn này để tránh tách state và validation
khỏi Django trong lúc annotation domain còn đổi.
