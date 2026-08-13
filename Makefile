SHELL := /bin/bash
.DEFAULT_GOAL := help
.NOTPARALLEL:

PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python
VENV_PIP := $(VENV)/bin/pip
COMPOSE ?= docker compose
SERVICE ?= web

.PHONY: help install install-cpu env check test migrate migrations bootstrap \
	dev up local up-local down stop restart refresh rebuild logs ps shell admin pack-model clean

help: ## Hiển thị các command có sẵn
	@awk 'BEGIN {FS = ":.*## "; printf "Model QC commands:\n\n"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Tạo .venv và cài dependency local với PyTorch CUDA 12.8
	@test -d "$(VENV)" || "$(PYTHON)" -m venv "$(VENV)"
	"$(VENV_PYTHON)" -m pip install --upgrade pip setuptools wheel
	"$(VENV_PIP)" install --index-url https://download.pytorch.org/whl/cu128 torch==2.7.1 torchvision==0.22.1
	"$(VENV_PIP)" install -r requirements.txt

install-cpu: ## Tạo .venv CPU-only để develop/check/test khi không có NVIDIA GPU
	@test -d "$(VENV)" || "$(PYTHON)" -m venv "$(VENV)"
	"$(VENV_PYTHON)" -m pip install --upgrade pip setuptools wheel
	"$(VENV_PIP)" install --index-url https://download.pytorch.org/whl/cpu torch==2.7.1 torchvision==0.22.1
	"$(VENV_PIP)" install -r requirements.txt

env: ## Tạo .env từ .env.example nếu chưa tồn tại
	@test -f .env || cp .env.example .env

check: ## Chạy Django system check và kiểm tra migration thiếu
	"$(VENV_PYTHON)" manage.py check
	"$(VENV_PYTHON)" manage.py makemigrations --check

test: ## Chạy toàn bộ test bằng .venv
	"$(VENV_PYTHON)" manage.py test

migrate: ## Apply migration bằng .venv
	"$(VENV_PYTHON)" manage.py migrate

migrations: ## Sinh migration mới bằng .venv
	"$(VENV_PYTHON)" manage.py makemigrations

bootstrap: ## Bootstrap role Django bằng .venv
	"$(VENV_PYTHON)" manage.py bootstrap_roles

dev: migrate bootstrap ## Chạy Django trực tiếp từ .venv tại port 8090
	"$(VENV_PYTHON)" manage.py runserver 0.0.0.0:8090

up: env ## Build và bật toàn bộ local stack bằng Docker Compose
	$(COMPOSE) up -d --build

# Cho phép cú pháp thân thiện `make up local`. Target `up` thực hiện công việc;
# `local` là marker không-op để Make không báo "No rule to make target".
local: ## Marker dùng cùng `make up local`
	@:

up-local: up ## Alias rõ nghĩa cho `make up local`

down: ## Dừng và remove container/network, giữ nguyên named volumes
	$(COMPOSE) down

stop: ## Dừng service nhưng giữ container và volumes
	$(COMPOSE) stop

restart: ## Restart service web
	$(COMPOSE) restart $(SERVICE)

refresh: env ## Recreate web bằng image hiện có để apply code/compose/migration, không rebuild
	$(COMPOSE) up -d --no-build --force-recreate $(SERVICE)

rebuild: env ## Rebuild và recreate service web
	$(COMPOSE) up -d --build $(SERVICE)

logs: ## Theo dõi log service web
	$(COMPOSE) logs -f $(SERVICE)

ps: ## Xem trạng thái service
	$(COMPOSE) ps

shell: ## Mở Django shell trong container web
	$(COMPOSE) exec $(SERVICE) python manage.py shell

admin: ## Tạo Django superuser tương tác trong container web
	$(COMPOSE) exec $(SERVICE) python manage.py createsuperuser

pack-model: ## Đóng gói HF model directory: make pack-model SRC=/path/model OUT=/path/model.zip
	@test -n "$(SRC)" || (echo "Thiếu SRC=/path/to/model-directory" && exit 2)
	@test -n "$(OUT)" || (echo "Thiếu OUT=/path/to/model.zip" && exit 2)
	"$(VENV_PYTHON)" manage.py pack_model_bundle "$(SRC)" "$(OUT)"

clean: ## Xóa cache Python local; không xóa DB/media/model/volumes
	find . -type d -name __pycache__ -not -path './.venv/*' -prune -exec rm -r {} +
	find . -type f -name '*.py[co]' -not -path './.venv/*' -delete
