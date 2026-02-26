.PHONY: help install install-api install-frontend \
        dev-redis dev-api dev-worker dev-frontend \
        docker-build docker-up docker-down docker-logs \
        db-init test lint clean

# ── Default ──────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "Tennis Coach — available targets"
	@echo ""
	@echo "  Setup"
	@echo "    install            Install full Python deps (pipeline + API + worker)"
	@echo "    install-api        Install lightweight API-only Python deps"
	@echo "    install-frontend   Install Node.js deps for the Next.js frontend"
	@echo ""
	@echo "  Local dev (run each in its own terminal)"
	@echo "    dev-redis          Start a local Redis instance"
	@echo "    dev-api            Start FastAPI on :8000 (hot-reload)"
	@echo "    dev-worker         Start Celery worker (concurrency=2)"
	@echo "    dev-frontend       Start Next.js dev server on :3000"
	@echo ""
	@echo "  Docker"
	@echo "    docker-build       Build all Docker images"
	@echo "    docker-up          Start all services via Docker Compose"
	@echo "    docker-down        Stop and remove containers"
	@echo "    docker-logs        Tail logs for all services"
	@echo ""
	@echo "  Database"
	@echo "    db-init            Apply db_schema.sql to local Postgres"
	@echo ""
	@echo "  Quality"
	@echo "    test               Run pytest test suite"
	@echo "    lint               Run flake8 + frontend eslint"
	@echo "    clean              Remove build artefacts and caches"
	@echo ""

# ── Python env ───────────────────────────────────────────────────────────────
PYTHON     ?= python3
VENV_DIR   ?= .venv
PIP        := $(VENV_DIR)/bin/pip
PYTEST     := $(VENV_DIR)/bin/pytest
FLAKE8     := $(VENV_DIR)/bin/flake8

install:
	$(PYTHON) -m venv $(VENV_DIR)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(PIP) install pytest pytest-asyncio

install-api:
	$(PYTHON) -m venv $(VENV_DIR)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-api.txt
	$(PIP) install pytest pytest-asyncio

install-frontend:
	cd frontend && npm install

# ── Local dev ────────────────────────────────────────────────────────────────
dev-redis:
	redis-server

dev-api:
	$(VENV_DIR)/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

dev-worker:
	$(VENV_DIR)/bin/celery -A celery_app worker --loglevel=info --concurrency=2

dev-frontend:
	cd frontend && npm run dev

# ── Docker ───────────────────────────────────────────────────────────────────
docker-build:
	docker compose build

docker-up:
	docker compose up

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

# ── Database ─────────────────────────────────────────────────────────────────
DB_URL ?= postgresql://postgres:postgres@localhost:5432/tennis_coach

db-init:
	psql "$(DB_URL)" -f db_schema.sql

# ── Quality ──────────────────────────────────────────────────────────────────
test:
	PYTHONPATH=. $(PYTEST) tests/ -v --tb=short

lint:
	$(FLAKE8) api/ pipeline/ utils/ config.py celery_app.py \
	    --max-line-length=100 --ignore=E203,W503 || true
	cd frontend && npm run lint || true

clean:
	find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -not -path './.venv/*' -delete 2>/dev/null || true
	rm -rf frontend/.next frontend/out
