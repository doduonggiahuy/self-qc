# Target platform architecture

Platform là control plane: UI, IAM/RBAC, project manifest, provisioning và
trạng thái tổng hợp. Nó không chạy label, train, rule hay quality evaluation.

```text
Platform Control
  ├── Annotation: team labeling phát hành Ground Truth release
  ├── Training: profile dataset, train và phát hành model artifact
  ├── AI Rules: chạy rule package với model/data input chuẩn hóa
  └── Quality: so sánh GT với model/rule output, phát hành report
```

## Artifact lifecycle

```text
Annotation release -> Training dataset -> Model artifact -> Rule output
       \-------------------------------------------------> Quality report
```

Mọi cạnh trong sơ đồ là `ArtifactReference` có URI, checksum, schema version
và metadata. Khi tách service, event envelope ở `control_plane/events` sẽ được
publish qua Kafka; binary/video/dataset không đi qua Kafka.

## Transitional ownership

| Current code | Target owner | Migration approach |
| --- | --- | --- |
| `annotations.Project` | Annotation | đổi tên sau qua compatibility migration |
| `annotations.Rule` | AI Rules | giữ legacy binding; RulePackage là hướng mới |
| `quality.GroundTruthRelease` | Annotation | Quality chỉ giữ snapshot/reference sau khi tách DB |
| `quality.InferenceModel` | Training / model registry | dùng `training.model_registry` cho code mới |

## Project manifest

Platform lưu JSON/YAML đã parse dưới `PlatformProject.manifest`. Mỗi lần áp
dụng manifest, `control_plane.projects.services.apply_manifest()` tạo provisioning
event cho Annotation, Quality, Training và AI Rules. Mỗi service chỉ đọc phần
cấu hình của nó và tự lưu resource riêng.
