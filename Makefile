# AIOps Makefile — 对齐 ongrid 的工程化纵深
# 支持: 多架构镜像构建/测试/lint/架构检查

IMAGE_NAME ?= aiops
IMAGE_TAG ?= latest
REGISTRY ?= docker.io/aiops
PLATFORMS ?= linux/amd64,linux/arm64

# ─── 构建 ───

.PHONY: build
build:
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .

.PHONY: build-multi
build-multi:
	docker buildx build \
		--platform $(PLATFORMS) \
		-t $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG) \
		--push \
		.

.PHONY: build-postgres
build-postgres:
	docker build \
		--build-arg WITH_POSTGRES=1 \
		-t $(IMAGE_NAME):$(IMAGE_TAG)-pg \
		.

# ─── 测试 ───

.PHONY: test
test:
	.venv/Scripts/python -m pytest tests/ -q --tb=short --cov=app --cov-fail-under=20

.PHONY: test-frontend
test-frontend:
	cd frontend && npx vitest run

.PHONY: test-e2e
test-e2e:
	.venv/Scripts/python tests/e2e_smoke.py 8012

.PHONY: test-all
test-all: test test-frontend

# ─── Lint ───

.PHONY: lint
lint:
	.venv/Scripts/python -m ruff check app tests tools deploy scripts

.PHONY: arch-check
arch-check:
	python tools/arch_check.py

.PHONY: check-all
check-all: lint arch-check

# ─── 部署 ───

.PHONY: compose-up
compose-up:
	docker compose --profile monitoring up -d --build

.PHONY: compose-up-pg
compose-up-pg:
	docker compose --profile postgres --profile monitoring up -d --build

.PHONY: compose-down
compose-down:
	docker compose down

# ─── 清理 ───

.PHONY: clean
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	rm -rf .pytest_cache frontend/dist .coverage coverage_html

# ─── 帮助 ───

.PHONY: help
help:
	@echo "AIOps Makefile"
	@echo "  build        - Build Docker image"
	@echo "  build-multi  - Build + push multi-arch image (requires docker buildx)"
	@echo "  test         - Run backend tests with coverage"
	@echo "  test-frontend- Run frontend vitest"
	@echo "  test-e2e     - Run E2E smoke test"
	@echo "  lint         - Run ruff check"
	@echo "  arch-check   - Run architecture boundary check"
	@echo "  compose-up   - Start monitoring stack"
	@echo "  clean        - Clean up cache files"