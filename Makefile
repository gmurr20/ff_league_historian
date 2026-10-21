VENV ?= .venv
PYTHON ?= $(shell if [ -f $(VENV)/bin/python3 ]; then echo $(VENV)/bin/python3; else which python3; fi)
RUFF ?= $(shell if [ -f $(VENV)/bin/ruff ]; then echo $(VENV)/bin/ruff; else which ruff; fi)
PYTEST ?= $(shell if [ -f $(VENV)/bin/pytest ]; then echo $(VENV)/bin/pytest; else which pytest; fi)

.PHONY: help install lint test seed backfill backfill-live sync-weekly build check run-api run-ui dev

help:
	@echo "Fantasy Football League Historian — Developer Commands"
	@echo ""
	@echo "  make install       - Create/update .venv and install backend + frontend deps"
	@echo "  make lint          - Run Ruff linter across Python code"
	@echo "  make test          - Run test suite via pytest"
	@echo "  make seed          - Seed local SQLite DB (ff_historian.db) with 3-season sample data"
	@echo "  make backfill      - Run historical ESPN backfill job from stored snapshots (--from-snapshots)"
	@echo "  make backfill-live - Pull live ESPN league data into local DB using .env credentials"
	@echo "  make sync-weekly   - Run active-season rolling weekly cron sync"
	@echo "  make run-api       - Start Flask REST API server on http://localhost:5001"
	@echo "  make run-ui        - Start Vite Vue 3 PWA dev server on http://localhost:5173"
	@echo "  make dev           - Start both Flask API (5001) and Vite UI (5173) together"
	@echo "  make build         - Build frontend production PWA bundle"
	@echo "  make check         - Run lint, test, and build"

install:
	@if [ ! -d "$(VENV)" ]; then \
		echo "Creating virtual environment in $(VENV)..."; \
		python3 -m venv $(VENV); \
	fi
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r backend/requirements.txt
	@if [ -f "frontend/package.json" ]; then \
		echo "Installing frontend dependencies..."; \
		(cd frontend && npm install); \
	fi

lint:
	$(RUFF) check .

test:
	$(PYTEST)

seed:
	$(PYTHON) -m db.seed_dev

backfill:
	$(PYTHON) -m backend.jobs.backfill_history --from-snapshots

backfill-live:
	$(PYTHON) -c "from backend.database import init_db; init_db()"
	$(PYTHON) -m backend.jobs.backfill_history

sync-weekly:
	$(PYTHON) -m backend.jobs.sync_weekly

run-api:
	$(PYTHON) -m backend.app

run-ui:
	cd frontend && npm run dev

dev:
	@echo "Starting Flask API on http://localhost:5001 and Vite PWA on http://localhost:5173..."
	@trap 'kill 0' INT TERM; \
	$(PYTHON) -m backend.app & \
	(cd frontend && npm run dev) & \
	wait

build:
	@if [ -f "frontend/package.json" ]; then \
		echo "Building frontend..."; \
		(cd frontend && npm run build); \
	else \
		echo "frontend/package.json does not exist yet (Phase 6 deliverable); skipping frontend build."; \
	fi

check: lint test build
