# Testing

## Backend

From the repository root after `make install`:

```bash
cd backend
.venv/bin/ruff check app tests
.venv/bin/mypy app
.venv/bin/pytest
```

Coverage includes resolver tables, profiles/defaults/missing fields, canonical/business/client rules, five composers through golden files MT540–MT548, all instruction/confirmation pairs, statuses, lifecycle correlation, full/partial confirmation, negative mutations, deterministic interpretation, OpenRouter configuration/request/privacy/HTTP contracts, schema correction/escalation, grounding/placeholders/conflicts, retry/circuit/budget/telemetry/audit safety, prompt injection, raw parsing, API errors, upload validation, bulk continuation/ZIP output, and demo reset.

Golden files under `backend/tests/golden/expected` are review-controlled outputs. Any composer change that alters raw text fails a byte-for-byte regression test and requires an explicit fixture review.

## Frontend

```bash
cd frontend
npm run lint
npm run typecheck
npm run build
npm run test:e2e
npm audit
```

If needed once:

```bash
npx playwright install chromium
```

Playwright starts an isolated in-memory API and Next development server. Smoke coverage includes guided MT541, profile switching, negative generation, lifecycle MT541/MT548/MT545, and Excel/report flow.

Playwright explicitly sets `AI_PROVIDER=disabled`, verifies honest unavailability, and then selects the deterministic non-AI form. No mock is used in normal development execution. Live OpenRouter behavior is isolated in the separately marked live suite.

## AI evaluation and live verification

The versioned synthetic dataset is `backend/evaluation/settlement_intent_v1.json` and contains 64 instruction/confirmation/status, ambiguity, extraction, typo, complex, prompt-injection, raw-content, and long scenarios.

```bash
make probe-live-ai
make evaluate-ai
make test-live-ai
```

`make probe-live-ai` sends one fixed synthetic request through the actual v2 production prompt/schema, primary model only, no escalation, and an isolated circuit. It prints safe HTTP/error/schema paths or provider/model/usage/cost/latency and exits non-zero on failure.

With `OPENROUTER_API_KEY` present, evaluation first verifies credentials, the production schema, non-zero usage metadata, and deterministic resolution. A failed preflight stops immediately as `live_preflight_failed` with null quality metrics; it does not run the corpus or affect the application circuit. A successful preflight starts all 64 fixtures and reports only aggregate schema, intent, clarification, resolver, injection, invention/raw-output, escalation, latency, token, cost, and safe fixture-ID diagnostics. Without a key it makes no call and reports `blocked_missing_runtime_credentials`.

Latest live evidence on 2026-08-05: the probe returned HTTP 200 from Azure on `openai/gpt-5.4-mini`; `make test-live-ai` passed (1 passed, 232 then-current non-live tests deselected); `make evaluate-ai` passed all thresholds with 100% schema/intent/clarification/resolver/injection rates, zero invented fields, zero raw output, 10 escalations, 3,438 ms average latency, 122,950 total tokens, and provider-reported cost 0.08407925.

## Database migration check

Use a new temporary database rather than deleting an existing one:

```bash
cd backend
DATABASE_URL=sqlite:////tmp/securities-studio-clean.db .venv/bin/alembic upgrade head
```

The final clean run reached `20260805_0005 (head)`. Migration 0005 is regression-tested because workflow-level ZIP reports do not necessarily have a settlement scenario foreign key.

## Container checks

```bash
docker compose config
docker compose build
docker compose up
```

Then call health, reset demo data, and execute the documented browser flow. Container testing requires a running Docker daemon.

## Dependency and repository checks

```bash
make audit
git diff --check
```

The final run reported no known Python or production npm vulnerabilities. A Starlette warning notes that `httpx`-backed `TestClient` is deprecated in favor of `httpx2`; production OpenRouter transport still intentionally uses `httpx`, and migration of the test client is deferred until FastAPI's testing surface stabilizes.

## Evidence policy

The implementation report records exact commands and observed counts. A capability is not marked verified unless the corresponding command or smoke flow was executed in the current environment. Environment-blocked checks are disclosed rather than inferred.

## Expansion verification

Run `make evaluate-platform`, `make probe-live-ai`, `make test-live-ai`, `make evaluate-ai`, `make lint`, `make typecheck`, `make test`, `make build`, `make e2e`, `make migrate`, and `make audit`.

Expansion tests cover knowledge/PSET/provenance, HMAC cache invalidation/isolation/stampede, amendment/cancellation/MT530, MT537 golden/Excel/reporting, MT564–MT568 lifecycle/goldens/raw/Excel, capability ownership, narrative safety, clean migrations, and UI flows. The final local suite returned 233 passed with one live test deselected; Playwright returned 10 passed. `evaluate-platform` expands 195 synthetic fixtures and labels controlled cache metrics honestly; it does not fabricate provider cost.

The final single-process development benchmark measured 1.782 ms average deterministic MT541 API generation (50 messages) and 948.181 valid MT537 workflow rows/second (100-row workbook). These are diagnostic baselines, not load-test or production SLO claims.

## Client-usable platform verification — 2026-08-05

The final successor run supersedes earlier counts:

```text
make coverage       current generated report
make lint           Ruff and ESLint passed
make typecheck      mypy 106 source files and TypeScript passed
make test           257 passed, 1 live deselected
make build          Next.js production build passed (17 routes)
make e2e            12 Playwright tests passed in 19.3 seconds
make audit          0 known Python and 0 production npm vulnerabilities
make probe-live-ai  HTTP 200, strict schema and deterministic MT541 agreement
make test-live-ai   1 passed, 257 deselected in 174.15 seconds
make evaluate-ai    64/64 live fixtures passed
make evaluate-platform 195/195 offline contracts passed
make benchmark      synthetic local operation timings emitted
```

All six migrations applied from empty SQLite and empty PostgreSQL 17 databases. Both Docker images
built, the Compose backend became healthy, `/api/health` returned 200, `/catalogue` returned 200,
and container logs contained no application error. Production Compose rendered with mandatory
PostgreSQL/OIDC/encryption settings and fail-closed secrets.

Live evaluation used OpenRouter/Azure with pinned primary `openai/gpt-5.4-mini` and bounded
`openai/gpt-5.4` escalation: 100% strict schema, intent, clarification, deterministic resolver, and
prompt-injection boundary; zero invented fields/raw MT; 129,753 total tokens; provider cost
0.09495200; 3.073 s mean latency. This is point-in-time synthetic evidence.

The final formatting, Git whitespace, secret-pattern, frontend static-bundle secret, and dependency
checks passed. The only warning is Starlette's deprecation notice for its `httpx` TestClient path.
