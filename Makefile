.PHONY: install migrate backend frontend dev test lint typecheck build e2e check audit coverage coverage-write xsd-compatibility xsd-compatibility-write demo-pack demo-pack-check mt-prowide-extract mt-prowide-reports-write mt-prowide-check verify-prowide-mt-source benchmark reset-demo evaluate-ai evaluate-platform probe-live-ai test-live-ai secret-scan mx-source-discover mx-source-fetch mx-source-acquire mx-source-inspect mx-message-set-discover mx-message-set-fetch mx-message-set-inspect verify-real-iso-sources mx-scaleout rule-source-ingest rule-extract rule-review rule-validate rule-inspect rule-diff evaluate-rule-extraction test-live-rule-extraction

# The interpreter used to build the virtualenv. Overridable so a runner or a machine that
# spells it differently needs no change to the recipe: `make install PYTHON=python3`.
PYTHON ?= python3.13

install:
	$(PYTHON) -m venv backend/.venv
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
check: lint typecheck test coverage xsd-compatibility demo-pack-check mt-prowide-check

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

xsd-compatibility:
	cd backend && .venv/bin/python -m app.spec_engine.compatibility --check

xsd-compatibility-write:
	cd backend && .venv/bin/python -m app.spec_engine.compatibility --write

demo-pack:
	cd backend && .venv/bin/python -m app.studio.demo_pack --write

demo-pack-check:
	cd backend && .venv/bin/python -m app.studio.demo_pack --check

MT_PROWIDE_LOCK ?= backend/config/mt_prowide_sru2025_10_3_18.lock.yaml
MT_PROWIDE_FIXTURE ?= backend/tests/fixtures/mt_prowide/all-categories-sru2025-10.3.18.json
MT_PROWIDE_CACHE ?= build/mt-prowide-cache
MT_PROWIDE_FRESH ?= build/mt-prowide-candidates/all-categories-sru2025-10.3.18.json

mt-prowide-extract:
	cd backend && .venv/bin/python -m app.spec_engine mt-prowide-extract \
		--lock $(abspath $(MT_PROWIDE_LOCK)) --cache $(abspath $(MT_PROWIDE_CACHE)) \
		--out $(abspath $(MT_PROWIDE_FIXTURE))

mt-prowide-reports-write:
	cd backend && .venv/bin/python -m app.spec_engine mt-prowide-reports \
		--fixture $(abspath $(MT_PROWIDE_FIXTURE)) --write

mt-prowide-check:
	cd backend && .venv/bin/python -m app.spec_engine mt-prowide-reports \
		--fixture $(abspath $(MT_PROWIDE_FIXTURE)) --check

verify-prowide-mt-source:
	cd backend && .venv/bin/python -m app.spec_engine mt-prowide-verify \
		--lock $(abspath $(MT_PROWIDE_LOCK)) --cache $(abspath $(MT_PROWIDE_CACHE)) \
		--fixture $(abspath $(MT_PROWIDE_FIXTURE)) --out $(abspath $(MT_PROWIDE_FRESH))

# Specification engine: compile a source schema into a pack, prove a pack against its
# source. Usage: make spec-compile SOURCE=path/to/schema.xsd [OUT=backend/config/mx]
#                make spec-validate PACK=path/to/pack.yaml SOURCE=path/to/schema.xsd
spec-compile:
	cd backend && .venv/bin/python -m app.spec_engine compile $(abspath $(SOURCE)) $(if $(OUT),--out $(abspath $(OUT)),) --validate

spec-validate:
	cd backend && .venv/bin/python -m app.spec_engine validate $(abspath $(PACK)) --source $(abspath $(SOURCE))

spec-diff:
	cd backend && .venv/bin/python -m app.spec_engine diff $(abspath $(BEFORE)) $(abspath $(AFTER))

# MX real-schema scale-out tooling. Discovery and fetch are developer/operator commands;
# runtime generation never performs either.
#   make mx-source-discover LOGICAL="pacs.008 pain.001" OUT=backend/config/mx/xsd/sources/snapshot.yaml
#   make mx-source-fetch URL=https://www.iso20022.org/... OUT=backend/config/mx/xsd/sources
#   make mx-source-acquire MANIFEST=... SOURCES=... OUT=...
#   make mx-source-inspect MANIFEST=backend/config/mx/xsd/sources/snapshot.yaml
#   make mx-message-set-discover FAMILY=pacs
#   make mx-message-set-fetch URL=https://www.iso20022.org/... OUT=backend/config/mx/xsd/sources MESSAGE_SET_NAME="Payments Clearing and Settlement"
#   make mx-message-set-inspect BUNDLE=... SOURCES=backend/config/mx/xsd/sources MESSAGE_SET_NAME="Payments Clearing and Settlement"
#   make verify-real-iso-sources MANIFEST=... SOURCES=... OUT=...
#   make mx-scaleout MANIFEST=... SOURCES=... OUT=build/mx-candidates REPORT=build/mx-scaleout.md
mx-source-discover:
	cd backend && .venv/bin/python -m app.spec_engine source-discover $(LOGICAL) \
		$(if $(OUT),--out $(abspath $(OUT)),)

mx-source-fetch:
	cd backend && .venv/bin/python -m app.spec_engine source-fetch "$(URL)" --out $(abspath $(OUT)) \
		$(if $(EXPECTED_MESSAGE_DEFINITION),--expected-message-definition $(EXPECTED_MESSAGE_DEFINITION),) \
		$(if $(EXPECTED_CHECKSUM),--expected-checksum $(EXPECTED_CHECKSUM),)

mx-source-acquire:
	cd backend && .venv/bin/python -m app.spec_engine source-acquire --manifest $(abspath $(MANIFEST)) \
		--sources $(abspath $(SOURCES)) $(if $(OUT),--out $(abspath $(OUT)),)

mx-source-inspect:
	cd backend && .venv/bin/python -m app.spec_engine source-inspect $(abspath $(MANIFEST))

mx-message-set-discover:
	cd backend && .venv/bin/python -m app.spec_engine message-set-discover $(FAMILY)

mx-message-set-fetch:
	cd backend && .venv/bin/python -m app.spec_engine message-set-fetch "$(URL)" \
		--out $(abspath $(OUT)) $(if $(FAMILY),--family $(FAMILY),) \
		$(if $(MESSAGE_SET_NAME),--message-set-name "$(MESSAGE_SET_NAME)",)

mx-message-set-inspect:
	cd backend && .venv/bin/python -m app.spec_engine message-set-inspect $(abspath $(BUNDLE)) \
		--sources $(abspath $(SOURCES)) $(if $(FAMILY),--family $(FAMILY),) \
		$(if $(MESSAGE_SET_NAME),--message-set-name "$(MESSAGE_SET_NAME)",)

verify-real-iso-sources:
	cd backend && .venv/bin/python -m app.spec_engine source-acquire \
		--manifest $(abspath $(or $(MANIFEST),backend/config/mx/xsd/sources/catalogue-snapshot-2026-08-20.yaml)) \
		--sources $(abspath $(or $(SOURCES),build/mx-real-sources)) \
		$(if $(OUT),--out $(abspath $(OUT)),) --bundle-only

mx-scaleout:
	cd backend && .venv/bin/python -m app.spec_engine scaleout --manifest $(abspath $(MANIFEST)) \
		--sources $(abspath $(SOURCES)) --out $(abspath $(OUT)) \
		$(if $(REPORT),--report $(abspath $(REPORT)),)

# Rule engine: business rules as reviewed configuration. Extraction is offline and never
# runs inside the application. Usage:
#   make rule-source-ingest SOURCE_ID=SYNTH-DEMO-MARKET-V1
#   make rule-extract SOURCE_ID=... MESSAGE=sese.023 [LAYER=MARKET_PRACTICE PROFILE=...]
#   make rule-review CANDIDATE=path/to.yaml REVIEWER="Your Name" [OUT=backend/config/rules]
#   make rule-validate PACK=backend/config/rules/....yaml
#   make rule-inspect [MESSAGE=sese.023 PROFILE=DEMO_MARKET_CLIENT_V1]
#   make rule-diff BEFORE=... AFTER=...
rule-source-ingest:
	cd backend && .venv/bin/python -m app.rule_engine ingest $(SOURCE_ID) --stamp

rule-extract:
	cd backend && .venv/bin/python -m app.rule_engine extract --source-id $(SOURCE_ID) \
		--message $(MESSAGE) $(if $(FORMAT),--format $(FORMAT),) $(if $(LAYER),--layer $(LAYER),) \
		$(if $(PROFILE),--profile $(PROFILE),) $(if $(OUT),--out $(abspath $(OUT)),)

rule-review:
	cd backend && .venv/bin/python -m app.rule_engine review $(abspath $(CANDIDATE)) --approve \
		--reviewer "$(REVIEWER)" $(if $(OUT),--out $(abspath $(OUT)),)

rule-validate:
	cd backend && .venv/bin/python -m app.rule_engine validate $(abspath $(PACK)) --require-reviewed

rule-inspect:
	cd backend && .venv/bin/python -m app.rule_engine inspect \
		$(if $(MESSAGE),--message $(MESSAGE),) $(if $(PROFILE),--profile $(PROFILE),)

rule-diff:
	cd backend && .venv/bin/python -m app.rule_engine diff $(abspath $(BEFORE)) $(abspath $(AFTER))

# The offline run stages scripted answers and measures the deterministic half of the
# pipeline. It costs nothing and calls nothing.
evaluate-rule-extraction:
	cd backend && .venv/bin/python -m app.rule_engine evaluate

# The live run calls the configured models and is the only thing that measures extraction
# quality. It costs money and is never part of `make check`.
test-live-rule-extraction:
	cd backend && .venv/bin/python -m app.rule_engine evaluate --live

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
