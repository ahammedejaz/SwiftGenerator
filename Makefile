.PHONY: install migrate backend frontend dev test lint typecheck build e2e check audit coverage coverage-write benchmark reset-demo evaluate-ai evaluate-platform probe-live-ai test-live-ai secret-scan

install:
	python3.13 -m venv backend/.venv
	backend/.venv/bin/pip install -r backend/requirements-dev.txt
	cd frontend && npm ci
	# The browser Playwright drives is a separate download from the npm package, so a
	# machine that has never run Playwright cannot `make e2e` without this. Only chromium:
	# that is the one project the config declares.
	cd frontend && npx playwright install chromium

migrate:
	cd backend && .venv/bin/alembic upgrade head

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

frontend:
	cd frontend && npm run dev

dev:
	./scripts/start-dev.sh

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

# Everything that must pass before pushing.
check: lint typecheck test coverage

secret-scan:
	@git ls-files -z | xargs -0 grep -nIE \
		"sk-or-v1-[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{32,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----" \
		&& { echo "Secret-shaped string found in a tracked file"; exit 1; } || echo "No secret-shaped strings in tracked files"

audit:
	cd backend && .venv/bin/pip-audit -r requirements-dev.txt
	cd frontend && npm audit --omit=dev

coverage:
	cd backend && .venv/bin/python -m app.studio.coverage --check

coverage-write:
	cd backend && .venv/bin/python -m app.studio.coverage --write

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
