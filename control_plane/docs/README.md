# Model QC documentation

Thư mục này là tài liệu sống của hệ thống. Mỗi thay đổi chức năng hoặc công
nghệ phải cập nhật file tương ứng trong cùng pull request.

## Bắt đầu đọc

1. [System overview](architecture/system-overview.md)
2. [Repository map](architecture/repository-map.md)
3. [Bounded contexts](architecture/bounded-contexts.md)
4. [Target platform architecture](architecture/target-platform.md)
5. [Domain model](architecture/domain-model.md)
6. [Roles and permissions](features/roles-and-permissions.md)
7. [Annotation Studio](features/annotation-studio.md)
8. [Annotation Tasks](features/annotation-tasks.md)
9. [Ground Truth workflow](features/ground-truth.md)
10. [Project, Rule và Video domain](project-rule-video-domain.md)
11. [Quality Lab](features/quality-lab.md)
12. [Model Quality workspace](features/model-quality-workspace.md)
13. [Inference model registry](features/inference-model-registry.md)
14. [Promptable model catalog](models/promptable-model-catalog.md)
15. [Local operations](operations/local-development.md)

## Quy ước tài liệu

- Một chức năng hoặc công nghệ lớn có một file Markdown riêng.
- Mô tả cả mục đích, luồng hoạt động, dữ liệu, cách chạy và giới hạn hiện tại.
- Gắn nhãn rõ `Implemented`, `Planned` hoặc `Research`.
- Không mô tả thiết kế dự kiến như thể nó đã chạy trong production.
- Link tới nguồn chính thức khi ghi nhận hành vi, license hoặc yêu cầu model.
