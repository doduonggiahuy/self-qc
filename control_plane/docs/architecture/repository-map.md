# Repository map

## Product code

```text
annotations/     Annotation Studio và annotation application services
quality/         Model Quality và evaluation services
training/        Training run orchestration (base)
ai_rules/        AI Rule definition/execution (base)
control_plane/events/ Event envelope dùng chung trong giai đoạn monolith
```

## Runtime và deployment

```text
config/          Django settings, URLs, Celery
templates/       Server-rendered MPA templates
Dockerfile       Web/worker image
docker-compose.yml  Local runtime: web, worker, PostgreSQL, Redis
```

## External platform

`cvat/` là source tree của CVAT Community và custom YOLO26 Nuclio functions.
Nó là annotation engine được tích hợp/khám phá, không phải Django app của
Freeflow. Khi tách repo, thư mục này sẽ trở thành `annotation-service`.

## Rule of thumb

- Domain logic nằm trong context tương ứng.
- Celery task chỉ điều phối, không chứa workflow dài.
- Artifact lớn không đi qua Kafka.
- Không import model ORM của context khác trong code mới nếu có thể dùng ID,
  service hoặc artifact contract.
