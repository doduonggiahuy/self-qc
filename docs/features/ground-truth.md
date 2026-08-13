# Ground Truth workflow

**Status:** Bounding-box workflow implemented.

YOLO-World tạo `PREDICTED` proposal. Người dùng chỉnh hoặc duyệt thành
`APPROVED`, `REJECTED`, `EDITED`. Chỉ `APPROVED` và `EDITED` được export hoặc
freeze vào GT release.

Freeze sẽ:

1. hash video RAW bằng SHA-256;
2. tạo version kế tiếp trong project;
3. copy annotation đã review sang `GroundTruthItem`;
4. lưu metadata video và timestamp tương ứng frame;
5. đánh dấu release `FROZEN`.

Sửa bbox nguồn sau đó không thay đổi item trong release cũ. Temporal segment,
keypoint, mask và reviewer approval workflow vẫn là planned.

