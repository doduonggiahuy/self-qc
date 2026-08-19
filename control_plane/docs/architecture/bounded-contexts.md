# Bounded contexts

Repo hiện tại vẫn chạy như một Django modular monolith. Các module dưới đây
là ranh giới nghiệp vụ chuẩn bị cho việc tách thành service riêng:

| Context | Sở hữu | Không sở hữu |
| --- | --- | --- |
| `annotations` | video asset, label, annotation, annotation release | quality metrics, training execution |
| `quality` | dataset snapshot, evaluation, metrics, quality report | manual annotation workflow |
| `training` | training run, experiment, model output | annotation database |
| `ai_rules` | rule definition, rule run, rule result | model training and annotation UI |

Trong giai đoạn monolith, các context dùng chung PostgreSQL để phát triển
nhanh. Tuy nhiên code mới phải đi qua application service hoặc artifact/event
contract thay vì truy cập chéo các model tùy tiện.

## Data flow

```text
Annotation release
        ├── Model Quality evaluation snapshot
        ├── Training dataset reference
        └── AI Rule input artifact
```

File lớn được trao đổi qua `artifact_uri` và checksum. Kafka event chỉ mang
metadata và reference; event envelope nằm trong `control_plane/events`.
