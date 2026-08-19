SHELL := /bin/bash
.DEFAULT_GOAL := help
.NOTPARALLEL:

COMPOSE ?= docker compose
SERVICE ?= platform-web
PROJECT_NAME ?= model-qc
APP_SERVICES := platform-web platform-worker annotation-worker quality-worker training-worker ai-rules-worker
INFERENCE_SERVICES := annotation-yolo26-detection annotation-yolo26-pose

.PHONY: help install install-cpu env check test migrate migrations bootstrap docker-migrate docker-test \
	dev up local up-local down stop restart apply refresh refresh-all rebuild logs logs-all ps shell admin pack-model clean \
	data-volumes reset-data reset-all-data sync-auto-annotation

help: ## Hiển thị các command có sẵn
	@awk 'BEGIN {FS = ":.*## "; printf "Model QC commands:\n\n"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: up ## Build Docker images và bật toàn bộ local stack

install-cpu: up ## Alias Docker-first; worker mặc định chạy CPU

env: ## Tạo .env từ .env.example nếu chưa tồn tại
	@test -f .env || cp .env.example .env

check: ## Chạy Django system check và kiểm tra migration thiếu trong Docker
	$(COMPOSE) up -d platform-web
	$(COMPOSE) exec platform-web python manage.py check
	$(COMPOSE) exec platform-web python manage.py makemigrations --check

test: ## Chạy toàn bộ test trong Docker
	$(COMPOSE) up -d platform-web
	$(COMPOSE) exec platform-web python manage.py test

migrate: ## Apply migration trong Docker
	$(COMPOSE) up -d platform-web
	$(COMPOSE) exec platform-web python manage.py migrate

docker-migrate: migrate ## Alias tương thích của migrate

docker-test: test ## Alias tương thích của test

migrations: ## Sinh migration mới trong Docker
	$(COMPOSE) up -d platform-web
	$(COMPOSE) exec platform-web python manage.py makemigrations

bootstrap: ## Bootstrap role Django trong Docker
	$(COMPOSE) up -d platform-web
	$(COMPOSE) exec platform-web python manage.py bootstrap_roles

dev: up ## Alias Docker-first của up

up: env ## Build và bật toàn bộ local stack bằng Docker Compose
	$(COMPOSE) up -d --build

# Cho phép cú pháp thân thiện `make up local`. Target `up` thực hiện công việc;
# `local` là marker không-op để Make không báo "No rule to make target".
local: ## Marker dùng cùng `make up local`
	@:

up-local: up ## Alias rõ nghĩa cho `make up local`

down: ## Dừng và remove container/network, giữ nguyên named volumes
	$(COMPOSE) down

data-volumes: ## Liệt kê named volumes dữ liệu thuộc riêng Model QC
	docker volume ls --filter "label=com.docker.compose.project=$(PROJECT_NAME)" --format "table {{.Name}}\t{{.Labels}}"

reset-data: ## Xóa PostgreSQL và artifact runtime Model QC (CONFIRM=RESET)
	@if [ "$(CONFIRM)" != "RESET" ]; then \
		echo "Từ chối xóa: dùng 'make reset-data CONFIRM=RESET'. Lệnh xóa database, media, models và datasets."; \
		exit 2; \
	fi
	$(COMPOSE) down --remove-orphans
	@docker volume ls -q --filter "label=com.docker.compose.project=$(PROJECT_NAME)" --filter "label=com.model-qc.reset-group=all-data" | xargs -r docker volume rm
	@echo "Đã xóa PostgreSQL và artifact runtime. Chạy 'make up local' để tạo stack mới."

reset-all-data: ## Alias reset toàn bộ runtime data (CONFIRM=RESET_ALL)
	@if [ "$(CONFIRM)" != "RESET_ALL" ]; then \
		echo "Từ chối xóa: dùng 'make reset-all-data CONFIRM=RESET_ALL'. Lệnh này xóa PostgreSQL và artifact runtime."; \
		exit 2; \
	fi
	$(COMPOSE) down --remove-orphans
	@docker volume ls -q --filter "label=com.docker.compose.project=$(PROJECT_NAME)" --filter "label=com.model-qc.reset-group=all-data" | xargs -r docker volume rm
	@echo "Đã xóa PostgreSQL và artifact runtime."

stop: ## Dừng service nhưng giữ container và volumes
	$(COMPOSE) stop

restart: ## Restart service đã chọn (mặc định platform-web)
	$(COMPOSE) restart $(SERVICE)

apply: ## Apply code mới: recreate Platform và toàn bộ worker, không rebuild image
	$(COMPOSE) up -d --no-build --force-recreate $(APP_SERVICES)

refresh: env ## Recreate Platform web và toàn bộ domain workers, không rebuild image
	$(COMPOSE) up -d --no-build --force-recreate $(APP_SERVICES)

refresh-all: env ## Alias của refresh
	$(COMPOSE) up -d --no-build --force-recreate $(APP_SERVICES)

rebuild: env ## Rebuild và recreate service đã chọn
	$(COMPOSE) up -d --build $(SERVICE)

logs: ## Theo dõi log Platform web
	$(COMPOSE) logs -f $(SERVICE)

logs-all: ## Theo dõi log Platform, workers, model inference, db và redis
	$(COMPOSE) logs -f $(APP_SERVICES) $(INFERENCE_SERVICES) db redis

ps: ## Xem trạng thái service
	$(COMPOSE) ps

sync-auto-annotation: ## Bật YOLO26 Detection/Pose và đồng bộ function specs vào registry
	$(COMPOSE) up -d annotation-yolo26-detection annotation-yolo26-pose
	$(COMPOSE) exec -T platform-web python manage.py sync_auto_annotation_functions

shell: ## Mở Django shell trong Platform web container
	$(COMPOSE) exec $(SERVICE) python manage.py shell

admin: ## Tạo Django superuser tương tác trong Platform web container
	$(COMPOSE) exec $(SERVICE) python manage.py createsuperuser

pack-model: ## Đóng gói model đã nằm trong workspace: make pack-model SRC=/app/... OUT=/app/...
	@test -n "$(SRC)" || (echo "Thiếu SRC=/app/model-directory" && exit 2)
	@test -n "$(OUT)" || (echo "Thiếu OUT=/app/model.zip" && exit 2)
	$(COMPOSE) exec platform-web python manage.py pack_model_bundle "$(SRC)" "$(OUT)"

clean: ## Xóa cache Python trong workspace; không xóa Docker data/volumes
	find . -type d -name __pycache__ -prune -exec rm -r {} +
	find . -type f -name '*.py[co]' -delete
