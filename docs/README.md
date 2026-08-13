# Model QC documentation

Thư mục này là tài liệu sống của hệ thống. Mỗi thay đổi chức năng hoặc công
nghệ phải cập nhật file tương ứng trong cùng pull request.

## Bắt đầu đọc

1. [System overview](architecture/system-overview.md)
2. [Domain model](architecture/domain-model.md)
3. [Roles and permissions](features/roles-and-permissions.md)
4. [Ground Truth workflow](features/ground-truth.md)
5. [Quality Lab](features/quality-lab.md)
6. [Inference model registry](features/inference-model-registry.md)
7. [Promptable model catalog](models/promptable-model-catalog.md)
8. [Local operations](operations/local-development.md)

## Quy ước tài liệu

- Một chức năng hoặc công nghệ lớn có một file Markdown riêng.
- Mô tả cả mục đích, luồng hoạt động, dữ liệu, cách chạy và giới hạn hiện tại.
- Gắn nhãn rõ `Implemented`, `Planned` hoặc `Research`.
- Không mô tả thiết kế dự kiến như thể nó đã chạy trong production.
- Link tới nguồn chính thức khi ghi nhận hành vi, license hoặc yêu cầu model.

