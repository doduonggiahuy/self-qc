# Roles and permissions

**Status:** Implemented baseline.

Hệ thống có hai persona UI:

## User

User đăng nhập bình thường và giữ đầy đủ chức năng nghiệp vụ hiện tại trên project
mà họ sở hữu:

- upload video và tạo project;
- cấu hình class/prompt/confidence;
- auto-label và review bbox;
- freeze GT;
- tạo/chạy test case và xem report.

## Admin

Admin là Django `is_staff` hoặc `is_superuser`. Ngoài quyền User, Admin có thể:

- mở khu vực `System`;
- đăng ký model inference và adapter;
- upload, sửa và xóa file model local do registry quản lý;
- bật/tắt model theo license/readiness;
- mở Django Admin để quản trị dữ liệu sâu hơn;
- superuser hoặc permission `edit_all_projects` có thể truy cập mọi project.

API kiểm tra quyền ở server; việc ẩn menu không được xem là biện pháp bảo mật.
Tài khoản production không được dùng mật khẩu mặc định `admin/admin`.

Admin Console nằm tại `/system/`, tách khỏi User workspace `/`. Django Admin chỉ
là công cụ dữ liệu cấp thấp được liên kết từ Admin Console.

Mỗi User có thể chọn một model inference đã được Admin bật và có adapter tương
thích. Preference này thuộc tài khoản User, không thay đổi lựa chọn của User khác.
