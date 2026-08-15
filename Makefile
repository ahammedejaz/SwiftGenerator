.PHONY: install migrate backend frontend test lint typecheck build e2e audit coverage benchmark reset-demo evaluate-ai evaluate-platform probe-live-ai test-live-ai

install:
	python3.13 -m venv backend/.venv
	backend/.venv/bin/pip install -r backend/requirements-dev.txt
	cd frontend && npm ci

migrate:
	cd backend && .venv/bin/alembic upgrade head

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

frontend:
	cd frontend && npm run dev

test:
	cd backend && .venv/bin/pytest

lint:
	cd backend && .venv/bin/ruff check app tests
	cd frontend && npm run lint

typecheck:
	cd backend && .venv/bin/mypy app
	cd frontend && npm run typecheck

build:
	cd frontend && npm run build

e2e:
	cd frontend && npm run test:e2e

audit:
	cd backend && .venv/bin/pip-audit -r requirements-dev.txt
	cd frontend && npm audit --omit=dev

coverage:
	cd backend && .venv/bin/python -m app.specifications.report --check

benchmark:
	cd backend && .venv/bin/python -m app.authoring.benchmark

evaluate-ai:
	cd backend && .venv/bin/python -m app.agents.evaluation

evaluate-platform:
	cd backend && .venv/bin/python -m app.agents.platform_evaluation

probe-live-ai:
	cd backend && .venv/bin/python -m app.agents.probe

test-live-ai:
	cd backend && .venv/bin/pytest -q -o addopts="" -m live

reset-demo:
	./scripts/reset-demo.sh
