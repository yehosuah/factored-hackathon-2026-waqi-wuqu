.PHONY: setup verify-sources check test etl-check backend-check frontend-check demo-up demo-down frontend-dev

DEMO_PROJECT ?= factored-submission
DEMO_PORT ?= 18040
FRONTEND_PORT ?= 5174

setup:
	cd etl && uv sync --locked --no-editable --reinstall-package factored-bank
	cd backend && uv sync --locked --no-editable --reinstall-package factored-bck
	cd frontend && npm ci

verify-sources:
	python3 scripts/verify_sources.py

etl-check:
	cd etl && UV_NO_EDITABLE=1 make check
	cd etl && UV_NO_EDITABLE=1 make test

backend-check:
	cd backend && PYTHONPATH=src UV_NO_EDITABLE=1 make check

frontend-check:
	cd frontend && npm test
	cd frontend && npm run check

check: verify-sources etl-check backend-check frontend-check

test: check

demo-up:
	cd etl && python3 scripts/demo.py up --backend-path ../backend --project $(DEMO_PROJECT) --port $(DEMO_PORT)

demo-down:
	cd etl && python3 scripts/demo.py down --backend-path ../backend --project $(DEMO_PROJECT) --port $(DEMO_PORT)

frontend-dev:
	cd frontend && FACTORED_API_TARGET=http://127.0.0.1:$(DEMO_PORT) npm run dev -- --port $(FRONTEND_PORT) --strictPort
