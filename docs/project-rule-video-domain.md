# Project, Rule và Video domain

## Quan hệ dữ liệu

- `ClientProject` là workspace của một khách hàng.
- Một `ClientProject` có nhiều `Rule` và nhiều video annotation.
- `Project` cũ được giữ làm video annotation asset để tương thích với bbox, GT release và Quality Test hiện có.
- `Rule.videos` là quan hệ many-to-many. Một rule dùng nhiều video và một video được tái sử dụng ở nhiều rule.
- `LabelClass` và `BoxAnnotation` thuộc video asset vì nội dung annotation gắn với frame của video, không gắn trực tiếp với rule.

## Luồng giao diện

1. Tạo customer project ở Workspace.
2. Mở customer project và upload một hoặc nhiều video.
3. Annotation và quản lý class trên từng video.
4. Tạo rule, sau đó chọn các video dùng để kiểm thử rule.
5. Một video đã duyệt có thể được chọn lại trong các rule khác mà không cần annotation lại.

## Tương thích dữ liệu cũ

Migration `annotations.0004_client_project_rules` tạo một `ClientProject` cho mỗi video project cũ và gắn video vào project đó. Bbox, class, GT release và test run cũ không bị thay đổi.

## Quy tắc xóa

- Xóa rule không xóa video hoặc annotation.
- Xóa class trong annotator xóa cả bbox đang tham chiếu class đó sau khi người dùng xác nhận.
- Xóa video xóa dữ liệu annotation/GT/test liên quan theo cascade.
- Xóa customer project xóa toàn bộ rules và video thuộc project, do đó giao diện luôn yêu cầu xác nhận.
