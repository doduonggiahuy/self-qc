# Annotation Tasks

**Status:** Implemented — CVAT-inspired Project → Task → Data workflow.

`AI Admin` tạo Annotation Project, project-level label schema và AI Rule.
`Data Annotator` tạo Annotation Task bên trong Project, chọn rule có sẵn,
gán annotator/reviewer và upload/xóa data (video) **trong Task**. Đây là mô
hình rút gọn từ CVAT: Project sở hữu labels, Task sở hữu data.

## Luồng hiện tại

1. AI Admin tạo Annotation Project, labels và rules.
2. Data Annotator tạo task trong project, chọn rules, gán đội ngũ/reviewer.
3. Data Annotator có thể kéo/thả nhiều video ngay trên màn tạo Task; mỗi video
   tạo một Job. Sau đó vẫn có thể upload thêm tại `/annotation/tasks/<id>/`.
4. Video nhận snapshot label schema của Project để annotation/inference ổn định.
4. Từ task, annotator mở video để label; truy cập trực tiếp video không được giao
   trả về `403`.

## Giới hạn hiện tại

- Task chưa chia frame range/job; mỗi task hiện giao toàn bộ video được chọn.
- Chưa có màn hình cập nhật status từ annotator sang reviewer.
- Project-level labels, attributes và skeleton schema đã được triển khai. Task
  không sở hữu label riêng và Job Canvas đọc schema từ Project.
