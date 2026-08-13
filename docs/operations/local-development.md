# Local development

## Makefile quick start

Chạy toàn bộ local stack giống cấu hình hiện tại:

```bash
make up local
```

Hoặc dùng alias tương đương:

```bash
make up-local
```

Make sẽ tạo `.env` từ `.env.example` nếu chưa có, build image và bật Docker
Compose. Entrypoint trong container tự migrate và bootstrap role.

Các command vận hành thường dùng:

```bash
make logs
make ps
make refresh    # apply thay đổi Python/template, không build image
make restart
make stop
make down       # giữ named volumes
make rebuild
make admin
```

Đóng gói một Hugging Face model directory để upload:

```bash
make pack-model SRC=/path/to/model OUT=/path/to/model.zip
```

Local Compose bind-mount source repo vào `/app`, còn `data`, `media` và `models`
vẫn dùng named volumes riêng. `make refresh` recreate riêng web container bằng
image hiện có để nhận code, thay đổi Compose và chạy migration qua entrypoint,
nhưng không build image. Dùng `make rebuild` nếu thay `requirements.txt`,
`Dockerfile`, system package hoặc CUDA/PyTorch stack.

Compose gọi entrypoint bằng `/bin/sh /app/entrypoint.sh` vì source local được bind
mount vào `/app`; cách này không phụ thuộc executable bit của script trên host.

Xem toàn bộ command:

```bash
make help
```

## Python virtual environment

Máy có NVIDIA/CUDA-compatible environment:

```bash
make install
make migrate
make bootstrap
make check
make test
make dev
```

Máy chỉ cần chạy check/test, không có GPU:

```bash
make install-cpu
make check
make test
```

`.venv` dùng cho phát triển Python trực tiếp. Docker Compose vẫn là đường chạy
được khuyến nghị để inference vì đã khóa CUDA stack và mount model volume.

## Chạy bằng Docker

```bash
docker compose up -d --build web
docker compose exec -T web python manage.py migrate
docker compose exec -T web python manage.py test
```

Mở `http://localhost:8090`.

## Chạy kiểm tra trực tiếp

```bash
python manage.py migrate
python manage.py check
python manage.py makemigrations --check
python manage.py test
```

Entrypoint tự migrate và bootstrap hai Django group. Không chạy
`docker compose down -v` nếu cần giữ database, video và model weights.
