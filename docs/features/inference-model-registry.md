# Inference model registry

**Status:** Registry UI implemented; extra adapters planned.

## Giao diện tối giản

Admin chỉ chọn nguồn và nhập một giá trị:

- `Upload local`: chọn `.pt` hoặc ZIP bundle.
- `Hugging Face`: nhập repo ID, ví dụ `microsoft/Florence-2-base-ft`.

Mọi Hugging Face repo đều có thể tải vào `qc_storage/models/huggingface`; không lọc
theo tên model hoặc danh sách catalog. Sau khi tải, registry đọc `config.json` để tự
nhận diện adapter khi architecture đã được hỗ trợ. Repo chưa có adapter vẫn là
`READY` (đã lưu thành công) nhưng bị disable và không xuất hiện cho User inference.
Các trường kỹ thuật/license không hiển thị trong form. Chỉ model `READY`, enabled và
có adapter tương thích mới xuất hiện cho User.

Worker image cài `transformers`, `timm` và `einops` để chạy Florence-2 và Grounding
DINO. Sau khi thay worker dependency phải dùng `make rebuild SERVICE=worker`; chỉ
`make refresh` sẽ không cài package mới.

Về chất lượng: Grounding DINO là lựa chọn open-vocabulary detection ưu tiên cho
bbox. Florence-2 hữu ích để gợi ý/auto-label, nhưng bbox không ổn định bằng detector
chuyên dụng nên luôn cần review trong Annotation Studio.

Registry tại `/system/models/`, chỉ Django Admin truy cập được. Một record gồm:

- key/name và loại task;
- file weight local;
- adapter name;
- license và cờ commercial use;
- default JSON config và enabled state.

Admin có thể upload, sửa hoặc xóa `.pt`, `.pth`, `.onnx`, `.engine` và
`.torchscript`. File nằm dưới `MODEL_ROOT` (`/var/lib/model-qc/models` trong Docker), tức named
volume `qc_storage` (thư mục `models`). Khi thay file hoặc xóa record, registry cũng xóa file cũ mà nó
quản lý. Vì vậy UI luôn có bước xác nhận khi xóa.

Quản lý được file không đồng nghĩa file chạy được. Hiện runtime selectable chỉ là
file `.pt` dùng adapter `quality.adapters.YoloWorldAdapter`. ONNX/engine cần adapter
riêng trước khi Admin bật cho User.

## Lựa chọn theo User

Annotator hiển thị dropdown `Inference model của tôi`. Chỉ model `enabled` và có
adapter thực thi tương thích mới xuất hiện. Lựa chọn lưu trong
`UserInferencePreference`; khi không chọn, runtime dùng `YOLO_WORLD_MODEL` mặc
định. Cache model được giữ theo path nên nhiều User có thể chọn các weight khác
nhau trong cùng web process.

Upload model không chứng minh weight tương thích. Model chỉ nên bật sau license
review, resource benchmark và integration test. YOLO-World `.pt` đã được nối vào
runtime selection; các adapter khác vẫn là planned.

Không có catalog hoặc model remote được tạo sẵn. Model chỉ xuất hiện sau khi Admin
upload file weight. Các record catalog mẫu từ phiên bản trước được migration xóa.

## Admin upload YOLO-World M/L

Mở `System -> Local models`, upload `yolov8m-worldv2.pt` hoặc
`yolov8l-worldv2.pt`, rồi chọn:

```text
Task: Open-vocabulary detection
Adapter: YOLO-World (.pt) — inference enabled
Enabled: yes
Default config: {"confidence": 0.25, "device": "0"}
```

Model sau đó xuất hiện trong annotator cho mọi User. Mỗi User tự chọn và nhấn
`Chọn`; preference của các tài khoản khác không thay đổi.

File lớn được stream qua Django upload handler xuống model volume. Production cần
cấu hình giới hạn body-size và timeout của ingress/reverse proxy phù hợp.

## Hugging Face model bundle

Florence-2 và Grounding DINO cần cả weight, config, processor và tokenizer. Đóng
gói directory đã download bằng:

```bash
python manage.py pack_model_bundle /path/to/model-directory /path/to/model.zip
```

Command bỏ bản weight `pytorch_model.bin` trùng lặp khi đã có
`model.safetensors`. Khi upload, hệ thống giới hạn 500 file/20 GB, chặn absolute
path, `..` và symlink, giải nén qua thư mục tạm rồi move atomically vào
`qc_storage/models/bundles`. Bundle tối thiểu phải có:

```text
config.json
model.safetensors
preprocessor_config.json
```

Adapter hiện có:

- `Florence2Adapter`: caption-to-phrase grounding, chạy lần lượt từng class.
- `GroundingDinoAdapter`: zero-shot detection nhiều prompt trong một lượt.
- `YoloWorldAdapter`: weight `.pt` đơn file.
