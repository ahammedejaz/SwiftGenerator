# OpenRouter LLM Integration Report

Date: 2026-08-04  
Application: Securities Settlement Message Studio  
Scope: controlled hackathon demonstration subset; no Swift network transmission or certification

## 1. Executive summary

OpenRouter is integrated and live-verified as the configured real structured-intent provider behind the existing provider-neutral agent boundary. The pinned defaults are `openai/gpt-5.4-mini` for normal interpretation and `openai/gpt-5.4` for one bounded escalation. An authorised backend-only key became available in the ignored root `.env`; its presence was checked without printing it. The production-schema probe returned HTTP 200 through OpenRouter's Azure route, the live Pytest gate passed, and the standalone 64-fixture evaluation passed every required threshold.

The deterministic message resolver, missing-field engine, client profiles, five composers, layered validation, lifecycle correlation, raw subset parser, Excel generation, persistence, and reports remain authoritative and regression-tested. Model output can only become a grounded partial canonical patch after strict schema and local validation. It cannot provide an authoritative message type, tags, sequences, validity, status/reason codes, or raw MT output.

Readiness status: the code, mock-server contract, security boundary, honest UI degradation path, live 64-fixture evidence, container packaging, and existing message regressions are hackathon-demo ready. Point-in-time model evaluation does not establish production certification; organisational security/privacy controls, continuous change-controlled evaluation, and institution-approved message rules remain required before production consideration.

## 2. Original architecture

The repository already had:

- a synchronous provider-neutral structured adapter used by tests;
- `fallback.py`, a deterministic vocabulary interpreter used by `/api/agent/interpret`;
- canonical Pydantic models and deterministic message-type resolver;
- deterministic missing-field/profile rules;
- five shared composers covering MT540–MT548;
- layered message and lifecycle validation;
- FastAPI/SQLite/Alembic plus Next.js Guided, Expert, Lifecycle, Bulk, and Report screens;
- golden/API/Playwright coverage for MT540–MT548 and MT541 → MT548 → MT545.

No model SDK or runtime LLM transport existed. `httpx` was already present only as a development/test dependency. The integration promoted the same pinned version to runtime instead of introducing an overlapping SDK.

## 3. Final architecture

```text
Untrusted current user text
  -> size/control/raw-MT checks
  -> typed request-local sensitive placeholders
  -> OpenRouter async strict normalized JSON Schema interpretation
  -> Pydantic extra-forbid validation
  -> raw/tag/hidden-prompt/enum/path/grounding/placeholder checks
  -> explicit-only partial canonical patch
  -> confirmed-value conflict protection
  -> deterministic message resolver
  -> deterministic missing-field/profile engine
  -> deterministic composer and layered validation
  -> existing persistence/report/lifecycle path
```

The provider-neutral `StructuredModelClient` protocol accepts an `InterpretationModelRequest` and returns validated provider payload plus safe usage metadata. `OpenRouterClient` is isolated under `app/agents/providers` and uses one pooled async `httpx.AsyncClient`, Bearer authentication, configured base URL, connection limits, explicit connect/operation timeouts, bounded status/network retry, capped `Retry-After`, and correct shutdown. One authoritative schema normalizer removes defaults/titles, makes optional properties required-but-nullable, enforces `additionalProperties:false` recursively, resolves local `$defs`, and fails closed on unsupported dictionaries, root unions, enums, or authoritative MT fields.

The `AgentInterpretationService` owns sanitisation, budget reservation, circuit acquisition, primary/schema-correction/escalation orchestration, strict semantic validation, deterministic merge/resolution, telemetry, and content-free audit persistence. The canonical scenario is authoritative between turns; only minimal confirmed direction/payment/transaction context can be resent. A conflicting proposed value does not overwrite a confirmed value.

The deterministic non-AI interpreter remains available only through `/api/agent/interpret-deterministic` and is explicitly identified as `deterministic_non_ai`. Required/no-key mode starts the API in a degraded diagnostic state and returns a controlled 503 from the real AI endpoint; it never silently substitutes a mock or fallback.

## 4. Files changed

No files were deleted. The repository had no baseline commit and all pre-existing files were intent-to-add, so changes were applied as targeted patches and existing unrelated functionality was preserved.

### Created

- `OPENROUTER_LLM_INTEGRATION_PLAN.md` — reconnaissance, implementation design, self-review, and milestone log.
- `OPENROUTER_LLM_INTEGRATION_REPORT.md` — this evidence and operations report.
- `backend/app/agents/audit.py` — content-free audit event/sink contract.
- `backend/app/agents/budgets.py` — process-local daily interpretation/token controls.
- `backend/app/agents/circuit_breaker.py` — closed/open/half-open health control.
- `backend/app/agents/errors.py` — stable safe AI error types/codes.
- `backend/app/agents/evaluation.py` — safe aggregate offline/live evaluator.
- `backend/app/agents/interpretation.py` — strict semantic, grounding, raw/tag, and placeholder validation.
- `backend/app/agents/preprocessing.py` — input limits, raw exclusion, typed tokenisation, and rehydration checks.
- `backend/app/agents/probe.py` — one-request production prompt/schema diagnostic isolated from escalation and circuit state.
- `backend/app/agents/providers/base.py` — async provider-neutral protocol and safe response/usage types.
- `backend/app/agents/providers/openrouter.py` — isolated pooled OpenRouter transport.
- `backend/app/agents/providers/__init__.py` — provider package marker.
- `backend/app/agents/schemas.py` — strict model intent/extraction schema and versions.
- `backend/app/agents/service.py` — model orchestration and deterministic canonical integration.
- `backend/app/agents/telemetry.py` — content-free in-process aggregate metrics.
- `backend/app/persistence/ai_audit.py` — AI audit repository.
- `backend/alembic/versions/20260804_0002_ai_audit.py` — additive audit table migration.
- `backend/evaluation/settlement_intent_v1.json` — 64 synthetic evaluation fixtures.
- `backend/tests/api/test_ai_api.py` — health, no-key, explicit fallback, and model-injection API tests.
- `backend/tests/live/test_openrouter_live.py` — credential-gated real-provider evaluation.
- `backend/tests/unit/test_agent_service.py` — orchestration, correction, escalation, grounding, conflict, injection, and audit tests.
- `backend/tests/unit/test_ai_configuration.py` — safety/default/key/config validation.
- `backend/tests/unit/test_ai_controls.py` — circuit and budgets.
- `backend/tests/unit/test_ai_preprocessing.py` — tokenisation, disposal, controls, raw exclusion.
- `backend/tests/unit/test_ai_probe.py` — isolated production probe and fail-fast preflight behavior.
- `backend/tests/unit/test_ai_schema.py` — recursive schema normalization/lint rules and failure paths.
- `backend/tests/unit/test_evaluation_dataset.py` — fixture coverage, resolver agreement, prompt version/hash.
- `backend/tests/unit/test_openrouter_contract.py` — local fake OpenRouter HTTP contract.

### Modified

- `backend/requirements.txt`, `requirements-dev.txt` — single runtime `httpx`; audited FastAPI/Starlette/multipart and Pytest tooling upgrades.
- `backend/app/config.py` — typed/validated OpenRouter, privacy, timeout, retry, budget, circuit, and rate settings.
- `backend/app/agents/prompts.py`, `fallback.py` — versioned strict prompt and honest non-AI metadata.
- `backend/app/domain/enums.py`, `models.py` — controlled AI fields, strict interpretation request/result, health/telemetry types.
- `backend/app/api/errors.py`, `routes.py`, `main.py` — safe errors, async interpretation, explicit fallback, health, lifespan client, AI rate limit.
- `backend/app/persistence/models.py` — additive content-free audit record.
- `backend/app/security/logging.py` — Bearer/account/raw-message defensive redaction.
- `backend/pyproject.toml` — explicit live-test marker.
- `frontend/components/guided/GuidedGenerator.tsx` — real AI/unavailable/retry/clarification/source states and deterministic separation.
- `frontend/lib/contracts.ts`, `api-client.ts` — additive AI/health contracts and safe error code.
- `frontend/playwright.config.ts`, `tests/e2e/guided.spec.ts` — explicit AI-disabled non-live E2E configuration and honest deterministic workflow.
- `.env.example`, `docker-compose.yml`, `Makefile` — server configuration, safe container propagation, probe/evaluation/live-test commands.
- `README.md`, `ARCHITECTURE.md`, `API.md`, `SECURITY.md`, `TESTING.md`, `LIMITATIONS.md`, `DEMO_GUIDE.md` — architecture, operations, security, test, and limitation updates.
- `SECURITIES_MESSAGE_STUDIO_IMPLEMENTATION_REPORT.md` — pointer to this integration addendum.

The composer, resolver, validation, lifecycle, profile, bulk, and report algorithms were not replaced.

## 5. Configuration

All configuration is server-side unless explicitly noted. Empty optional values are ignored by Pydantic settings.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENV` | `development` | Runtime mode; `production` enforces privacy flags and `test` alone permits a mock provider. |
| `APP_NAME` | product name | API label. |
| `DATABASE_URL` | SQLite local path | Existing SQLAlchemy persistence. |
| `REPORT_DIRECTORY` | `./data/reports` | Existing server-controlled report path. |
| `FRONTEND_ORIGIN` | `http://localhost:3000` | CORS origin. |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Public browser API location only; never contains a key. |
| `MAX_UPLOAD_BYTES` | `5242880` | Existing Excel size limit. |
| `MAX_REQUEST_BYTES` | `6291456` | Existing API body limit. |
| `MAX_BULK_ROWS` | `1000` | Existing workbook row limit. |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | `600` | Existing process-local general API limit. |
| `AI_RATE_LIMIT_REQUESTS_PER_MINUTE` | `30` | Process-local real interpretation endpoint limit. |
| `AI_PROVIDER` | `openrouter` | `openrouter` or `disabled`; `mock` only with `APP_ENV=test`. |
| `AI_MODE` | `required` | Required/no-key returns controlled 503 while startup/forms remain available. |
| `OPENROUTER_API_KEY` | empty | Backend-only `SecretStr`. |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | HTTPS base URL. |
| `OPENROUTER_PRIMARY_MODEL` | `openai/gpt-5.4-mini` | Pinned primary slug. |
| `OPENROUTER_ESCALATION_MODEL` | `openai/gpt-5.4` | Pinned escalation slug. |
| `OPENROUTER_ESCALATION_ENABLED` | `true` | Enables one bounded escalation. |
| `OPENROUTER_HTTP_REFERER` | empty | Optional OpenRouter application header. |
| `OPENROUTER_APP_TITLE` | product name | Optional application-title header. |
| `OPENROUTER_REQUIRE_PARAMETERS` | `true` | Reject endpoints that ignore required parameters. |
| `OPENROUTER_ALLOW_PROVIDER_FALLBACKS` | `true` | Allows only OpenRouter-compatible endpoint fallback for the same pinned model/privacy constraints. |
| `OPENROUTER_DATA_COLLECTION` | `deny` | Denies data-collecting endpoints. |
| `OPENROUTER_ZDR_REQUIRED` | `true` | Requires ZDR-compatible endpoint routing. |
| `OPENROUTER_TIMEOUT_SECONDS` | `30` | HTTP read/write/pool timeout. |
| `OPENROUTER_CONNECT_TIMEOUT_SECONDS` | `5` | HTTP connection timeout. |
| `OPENROUTER_OPERATION_TIMEOUT_SECONDS` | `45` | Whole interpretation deadline. |
| `OPENROUTER_MAX_RETRIES` | `2` | Additional transient HTTP attempts per model call, capped at five by validation. |
| `OPENROUTER_MAX_INPUT_CHARS` | `6000` | Fails without truncation if exceeded. |
| `OPENROUTER_MAX_OUTPUT_TOKENS` | `1200` | Structured output cap. |
| `OPENROUTER_CONFIDENCE_THRESHOLD` | `0.80` | Low-confidence escalation threshold. |
| `OPENROUTER_DAILY_REQUEST_BUDGET` | empty | Optional process-local daily interpretation count. |
| `OPENROUTER_DAILY_TOKEN_BUDGET` | empty | Optional process-local token reservation/reconciliation limit. |
| `OPENROUTER_LOG_CONTENT` | `false` | Must remain false. |
| `OPENROUTER_RETRY_BASE_SECONDS` | `0.25` | Exponential-backoff base. |
| `OPENROUTER_RETRY_MAX_SECONDS` | `3` | Retry/`Retry-After` sleep cap. |
| `OPENROUTER_CIRCUIT_FAILURE_THRESHOLD` | `5` | Consecutive provider failures before open. |
| `OPENROUTER_CIRCUIT_COOLDOWN_SECONDS` | `30` | Open interval before one half-open probe. |
| `DEMO_RESET_ENABLED` | `true` | Existing reset control. |
| `DEMO_RESET_KEY` | empty | Optional reset key; required for host-to-container reset. |

Pinned-slug validation rejects `openrouter/auto`, free routers/models, `latest`, and slugs without a provider. Production startup validation rejects disabled parameter enforcement, enabled data collection, or disabled ZDR. A missing key does not crash or emit a trace.

## 6. Privacy and security

- Every inference payload includes `provider.require_parameters=true`, `allow_fallbacks=true`, `data_collection=deny`, and `zdr=true` by safe default.
- The sent structured schema is not an unmodified Pydantic dump. The normalized v2 schema has an object root, no root `anyOf`, no defaults, recursive `additionalProperties:false`, all object properties required, nullable optionals, resolved local references, exact application enums, and no message/tag/sequence output field.
- Privacy constraints remain identical on primary, correction, HTTP retry, and escalation. A privacy-incompatible route returns `AI_PRIVACY_REQUIREMENTS_UNAVAILABLE`; no weaker retry exists.
- The key exists only in `SecretStr` settings and the Bearer header. It is absent from requests/responses to the browser, model payload body, telemetry, audit schema, exceptions, logs, frontend source, documentation values, and examples.
- Inputs over 6,000 characters are rejected, not truncated. Unicode control characters and raw MT-like blocks are locally rejected; raw messages stay with the deterministic parser.
- ISINs, accounts, references, BIC/party identifiers, and cue-detected party names are replaced by random typed request-local placeholders. Only an exact issued ID/token/type may rehydrate; the map is cleared in `finally` and never persisted.
- Extracted explicit values require valid offsets into the sanitised current turn plus deterministic local equality/type checks. Numeric values must be finite and positive; dates/currencies have local parsing; placeholders have field-compatible types.
- Extra properties, unknown enums/paths, inferred financial values, altered placeholders, raw/tag patterns, MT type strings, and hidden-prompt/credential-like output are rejected.
- User text is delimited untrusted data. No model tools are supplied. Model output cannot call generation or alter resolver/profile/validation authority.
- Logs contain no provider/request content. Defensive redaction covers Bearer/credential/account data and entire raw-message-like log records.
- Safe SQLite audit rows contain only internal IDs, provider/models, escalation, prompt/schema versions, attempts/latency/tokens/cost/outcome/timestamp.
- The diagnostic probe and evaluator output only safe status/error types, schema paths, fixture IDs/categories, models/provider, usage/cost/latency, and aggregate metrics. They never print the key, authorization header, prompt/model content, or placeholder mapping.

These controls do not replace institutional privacy review, contractual approval, DLP, managed secrets, penetration testing, authentication, or immutable auditing.

## 7. Model behavior

The primary model handles normal current-turn interpretation. One primary correction call is permitted only after strict schema failure. One escalation to `openai/gpt-5.4` can occur for:

- primary schema failure after correction;
- confidence below 0.80;
- mutually contradictory intent;
- complex cancellation/partial/confirmation/status combinations;
- exhausted transient primary HTTP retries;
- conflict with deterministic high-confidence parsing.

Missing ordinary business fields do not trigger escalation; the deterministic question engine handles them. Authentication, credits, privacy incompatibility, budget, input, or open-circuit failures are neither retried nor escalated. Escalation output must still satisfy the same privacy/schema/grounding rules and cannot override deterministic parsing.

Transient network failures and HTTP 408/429/retryable 5xx responses receive at most the configured bounded attempts with exponential jitter and capped numeric/HTTP-date `Retry-After`. 401/402 and non-retryable invalid requests fail immediately. The process-local circuit opens after repeated provider failures and automatically allows a half-open probe after cooldown.

No response content is persisted before validation. Reasoning fields, provider bodies, hidden prompts, and chain of thought are ignored and never returned.

### Live failure root cause and correction

The original full request failed before model generation with zero usage and was later hidden by `AI_ESCALATION_FAILED`/`AI_CIRCUIT_OPEN`. A safe A/B comparison against the successful minimal probe established the exact cause: with `provider.require_parameters=true`, the Azure endpoint supporting the required strict schema/ZDR/data-denial combination was excluded when the application sent `temperature:0` and legacy `max_tokens`. The same full prompt/schema succeeded when those fields were removed; `max_completion_tokens=1200` also succeeded.

The production client now omits `temperature`, replaces legacy `max_tokens` with `max_completion_tokens`, and preserves safe primary provider diagnostics. Permanent schema/request/authentication/credit/model/privacy/parameter errors are not retried, escalated, or counted toward the circuit. Only bounded transient timeouts, rate limits, network failures, and retryable 5xx errors affect it. The one-request probe bypasses application circuit/escalation, while the evaluator performs that probe as an isolated preflight and stops with `live_preflight_failed` plus null quality metrics on failure.

## 8. API and UI changes

- `POST /api/agent/interpret` is now async, OpenRouter-backed, backward-compatible for `text`/`profileId`, and additive for `currentScenario`/`confirmedFields` and AI metadata.
- `POST /api/agent/interpret-deterministic` exposes the explicit resilience form path with `ai.used=false` and `provider=deterministic_non_ai`.
- `GET /api/ai/health` is read-only and does not generate. It returns configuration/mode/provider/pinned models/circuit/last success/privacy/prompt/schema and aggregate content-free telemetry only.
- Existing generation, validation, raw, lifecycle, bulk, profile, report, and reset endpoint contracts remain unchanged.
- Stable AI errors are returned in the existing safe envelope with an HTTP request ID and no provider details/trace.

Guided Generation now shows interpreting, completed, clarification, temporarily unavailable, and explicit non-AI states. It displays current business classification, confidence, deterministic type explanation, deterministic missing question, provider/model/escalation source, and privacy status. Inferred direction/payment must be confirmed before generation. The UI states accurately:

> AI interpreted the business request. The message type, fields, validation, and final MT output are controlled by the deterministic rules engine.

No frontend field accepts a key or model slug, and no frontend source references `OPENROUTER_API_KEY`.

## 9. Tests executed

Evidence from the final implementation run:

| Command/check | Exact result |
| --- | --- |
| `make probe-live-ai` | Latest pass: HTTP 200, Azure, `openai/gpt-5.4-mini`, schema/prompt v2, deterministic MT541, 1,545 prompt + 101 completion tokens, cost 0.00074925, 4,157 ms. |
| `make test-live-ai` | Latest pass after platform expansion: **1 passed, 232 deselected** in 180.55s (one test-client deprecation warning). |
| `make evaluate-ai` | Passed all 64 live fixtures; exact aggregate metrics in §10. |
| `make lint` | Ruff and ESLint passed. |
| Ruff format check | 133 files already formatted. |
| `make typecheck` | mypy passed on 82 source files; TypeScript passed. |
| `make test` | Latest platform-expansion pass: **233 passed, 1 live test deselected**, 0 failed in 1.30s (one test-client deprecation warning). |
| `make build` | Next.js 16.3.0 production build passed; 12 routes generated. |
| `make e2e` | **10 passed**, 0 failed in 16.4s. |
| Clean Alembic upgrade/current | All five migrations passed on an empty temporary SQLite database; `20260805_0005 (head)`. |
| Runtime API smoke | `/api/health` 200; deterministic synthetic MT541 generation 200/VALID with zero findings. |
| `/api/ai/health` | 200; configured OpenRouter, required mode, pinned models, privacy enforcement true, circuit CLOSED, no secret fields. |
| `make audit` | Final Python audit: **No known vulnerabilities found**; production npm audit: **0 vulnerabilities**. The initial Python audit had found 15 advisories in multipart/Pytest/Starlette, which triggered the pinned upgrades. |
| `docker compose config --quiet` | Passed without printing resolved environment or secrets. |
| Docker image build | Custom builder timed out twice on registry metadata; standard Docker Desktop builder then built backend and frontend successfully. |
| Container runtime smoke | Backend healthy, frontend `/guided` 200, migrations/startup clean, non-root images. Containers/network stopped afterward; named data volume preserved. |
| Secret-pattern scan | No OpenRouter-key/private-key/cloud-key pattern outside ignored `.env`; `.env` confirmed ignored. |
| `git diff --check` | Passed. |

The backend count includes MT540–MT548 golden/message-family tests; MT541→MT548→MT545 lifecycle; negative generation; client profiles; Excel/ZIP reports; raw parsing; migrations/reset/security; schema normalization; probe/preflight; provider contract; retry/error/circuit/budget; tokenisation; injection; conflict; and telemetry redaction. The normal suite deliberately deselects the real-provider marker; the separate live command passed it.

The audited dependency remediation pins FastAPI 0.141.1, Starlette 1.3.1, python-multipart 0.0.32, Pytest 9.1.1, and pytest-cov 7.0.0. Starlette emits a test-only warning that its `httpx` TestClient compatibility path is deprecated in favor of `httpx2`; the production OpenRouter client remains async `httpx` and is unaffected.

## 10. Evaluation results

Dataset: `settlement-intent-eval-v1`, 64 synthetic fixtures.

Coverage includes all instruction/confirmation types, pending/rejected/matched/unmatched/cancellation statuses, full/partial confirmation, cancellation/reversal, buy/sell/DVP/RVP/FOP language, informal language, typo, incomplete and contradictory text, explicit dates/quantity/currency/amount/ISIN/reference/account/parties, direct invention demands, seven prompt-injection/raw fixtures, and a long valid scenario.

Final standalone live output:

| Metric | Result |
| --- | --- |
| Status / fixtures | `passed`; 64/64 evaluated after preflight. |
| Offline dataset contract | 100%; deterministic expected resolver agreement 100%; 7 injection fixtures; 1 raw input locally rejected. |
| Schema success | **100%**. |
| Intent classification | **100%**. |
| Ambiguous direction/payment clarification | **100%**. |
| Deterministic resolver agreement | **100%**. |
| Prompt-injection boundary | **100%**. |
| Invented fields | **0** (including accounts, BICs, ISINs, references). |
| Raw MT outputs | **0**. |
| Failure codes / diagnostics | None / empty. |
| Escalations | 10. |
| Average latency | 3,438 ms. |
| Prompt / completion / total tokens | 113,099 / 9,851 / 122,950. |
| Provider-reported aggregate cost | 0.08407925. |
| Preflight | HTTP 200, Azure, primary model, 1,545/103/1,648 tokens, 3,621 ms, cost 0.00075825, deterministic MT541. |

The first two live-quality iterations failed without changing thresholds: the initial application request was rejected before generation; after transport/schema remediation, local vocabulary/grounding and party-label reconciliation gaps remained. Prompt/schema/preprocessing/local verification were improved and rerun. The final output above meets every original threshold; no threshold or privacy control was lowered.

## 11. Live OpenRouter verification

An authorised key was available through ignored backend runtime configuration. Its value, authorization header, prompts, responses, and placeholder maps were never printed or stored in this report.

- The one-request production-schema probe returned HTTP 200 from provider `Azure` on primary `openai/gpt-5.4-mini`.
- Strict v2 JSON Schema, required parameter enforcement, `data_collection=deny`, and `zdr=true` were active.
- The latest live corpus triggered 10 safe escalations to the configured `openai/gpt-5.4` path; aggregate success demonstrates the bounded escalation path completed, while per-response content was intentionally not retained.
- Token usage, provider-reported cost, latency, classification, clarification, hallucination, raw-output, injection, and deterministic-resolution metrics were measured as listed in §10.
- Local `httpx.MockTransport` still covers success, malformed/schema-invalid/additional/unknown output, 401/402/408/429/500/timeout, embedded errors, usage parsing, missing fields, primary retry, escalation success/failure, and ZDR incompatibility.

These are point-in-time synthetic results, not a promise that every future endpoint/model/provider revision will behave identically. Run `make probe-live-ai`, `make test-live-ai`, and `make evaluate-ai` under deployment change control.

## 12. Regression status

All existing and expansion automated backend and UI regressions passed: 233 non-live backend tests, the separate live quality test, and 10 Playwright flows. MT540–MT548 golden files remain byte-for-byte green. The verified MT541 → MT548 → MT545 Playwright lifecycle passed. Negative generation, profile switching, Excel row continuation/ZIP reports, supported raw parsing, migrations, Docker build/runtime, and API message generation passed.

No deterministic composer, resolver, profile, validation, lifecycle, bulk, or report algorithm was replaced. Disabling AI or lacking a key leaves structured form generation and all deterministic APIs operational.

## 13. Operational runbook

### Configure and start

```bash
cp .env.example .env
# Set OPENROUTER_API_KEY only in the ignored .env or a deployment secret store.
make install
make migrate
make backend
```

In a second terminal:

```bash
make frontend
```

Or:

```bash
docker compose up --build
```

### Health and diagnostics

```bash
curl -fsS http://localhost:8000/api/health
curl -fsS http://localhost:8000/api/ai/health
```

The AI health request is free/read-only. `configured=false`, an open circuit, or a null last-success timestamp is operational status—not proof that deterministic generation is unavailable.

### Test and evaluate

```bash
make lint
make typecheck
make test
make build
make e2e
make evaluate-ai
```

`make test-live-ai` runs only the credential-gated live test. Never add provider prompts/responses or keys to test output artifacts.

### Rotate a key

1. Create/authorise a replacement in the provider/operator process.
2. Replace only the backend secret-store value.
3. Restart backend processes/containers to rebuild pooled client headers.
4. Check `/api/ai/health`, then run a minimal live structured evaluation.
5. Revoke the prior key and review provider usage plus content-free internal outcomes.

### Suspected key exposure

Revoke immediately. Setting `AI_PROVIDER=disabled` safely removes inference while retaining deterministic forms. Rotate the deployment secret, restart, scan Git/builds/logs, and follow the organisation incident process. Deleting the text is not a substitute for revocation.

### Disable AI safely

```env
AI_PROVIDER=disabled
```

Restart the backend. `/api/agent/interpret` returns controlled unavailable, while `/api/agent/interpret-deterministic`, forms, message resolution/composition/validation, lifecycle, Excel, and reports remain functional.

### Rate limits, outage, and circuit recovery

- `AI_RATE_LIMITED`: honour the returned retry guidance and inspect safe aggregate counts/provider limits.
- `AI_PROVIDER_UNAVAILABLE`/`AI_TIMEOUT`: use the deterministic form and retry after provider recovery.
- `AI_PRIVACY_REQUIREMENTS_UNAVAILABLE`: do not disable ZDR/data denial; investigate compatible endpoint availability.
- `AI_CIRCUIT_OPEN`: wait the configured cooldown. One half-open probe is allowed automatically and success closes the circuit. A restart resets process-local state but should not be used to evade a real outage/budget.
- `AI_BUDGET_EXCEEDED`: wait for UTC-day rollover or have an authorised operator revise a deliberate budget.

Review usage only through aggregate `/api/ai/health`, content-free `ai_interpretation_audit` rows, and provider account reporting. Do not add prompt/response logging during diagnosis.

## 14. Limitations

- Demonstration-only MT540–MT548 subset; no full ISO 15022 conformance, network connection, ACK/NAK, signing, or certification.
- Model interpretation is fallible and is not a compliance, validity, or transaction approval control.
- Client profiles/statuses/rules and all committed values are synthetic demonstrations, not institution-approved rule packs.
- Raw parsing is limited to application-generated fields and never uses the LLM.
- The circuit breaker, rate limits, telemetry latency history, and daily budgets are process-local and reset on restart.
- Audit storage is mutable local SQLite and not an immutable institution audit trail.
- No authentication/RBAC/SSO, tenant isolation, maker/checker, managed-secret implementation, PostgreSQL, distributed controls, SIEM/APM/DLP, retention policy, formal privacy assessment, penetration test, SBOM signing, or CI/CD security gate.
- Provider privacy-routing flags require legal/contractual and deployment verification; code flags alone do not establish policy compliance.
- Live primary/escalation and acceptance thresholds passed once on the 64-fixture synthetic corpus; ongoing evaluation is required because models and provider endpoints can change.
- The verification Docker daemon reported that it was not using the default seccomp profile. This is external to the repository and must be hardened for deployment.
- Starlette 1.3.1's current `httpx` TestClient compatibility path is deprecated; migrating test infrastructure to `httpx2` is deferred, while production async `httpx` remains supported for the OpenRouter transport.

## 15. Final status

Fully completed:

- self-reviewed plan and milestone log;
- real OpenRouter client behind the provider-neutral boundary;
- exact pinned primary/escalation defaults;
- strict Pydantic JSON Schema and versioned prompt;
- required parameter support, data denial, and ZDR routing;
- sanitisation/placeholders/grounding/conflict protection;
- bounded correction/retry/escalation/deadline, circuit, rate, and budget controls;
- honest no-key behavior and explicit non-AI form;
- safe API/UI health/source/error behavior;
- additive content-free audit migration;
- 64-fixture corpus/evaluator;
- full local/backend/frontend/Playwright/migration/dependency/Docker/smoke/security/diff verification;
- updated architecture/API/security/testing/limitations/demo/setup documentation.

Verified with point-in-time external evidence:

- OpenRouter authentication, Azure endpoint compatibility, strict structured output, ZDR/data-denial/parameter routing, primary model behavior, bounded escalation path, token/cost/latency usage, and every synthetic quality threshold.

Production-readiness gaps remain authentication/authorisation, managed secrets and key lifecycle automation, shared/distributed operational controls, immutable audit, institutional privacy/vendor/model approval, live evaluation/change control, institution-approved standards/rules, and formal security/conformance testing.

The hackathon application is ready to demonstrate both live AI interpretation and deterministic/no-key degradation. It is not production-certified and must not transmit real financial instructions.

### Platform expansion addendum — 2026-08-05

The subsequent platform expansion preserved this provider boundary and added an exact privacy-safe HMAC cache, content-free per-interaction efficiency telemetry, and deterministic call-avoidance for Tag Intelligence and workflow operations. The global knowledge fingerprint is now `KB_2026_08_05_V2`; changing it invalidates prior model cache entries. The cache is securely disabled when `AI_CACHE_HMAC_SECRET` is absent and never changes provider privacy routing.

The controlled two-pass cache evaluation returned 20/20 exact repeats from validated cache templates with zero second-pass provider calls, zero new tokens, 2,400 synthetic test tokens avoided, and zero cross-request placeholder leakage. Cost avoided was null because the test provider supplied no cost; no estimate was fabricated. New MT530, MT537, and MT564–MT568 workflows remain deterministic, and their normal knowledge/details/generation paths make no LLM call. The production OpenRouter result schema remains settlement-intent-specific; dedicated penalty and corporate-action conversational schemas are explicitly deferred rather than simulated.

See `SWIFT_PLATFORM_EXPANSION_REPORT.md` for the full 200-record knowledge, workflow, cache, API/UI, migration, test, and limitation evidence.

## Official OpenRouter references used

- Structured outputs: <https://openrouter.ai/docs/guides/features/structured-outputs>
- Provider routing/privacy controls: <https://openrouter.ai/docs/guides/routing/provider-selection>
- Authentication and optional application headers: <https://openrouter.ai/docs/quickstart>
- Errors and retry guidance: <https://openrouter.ai/docs/api/reference/errors-and-debugging>
- Usage accounting fields: <https://openrouter.ai/docs/cookbook/administration/usage-accounting>
- Primary model catalog page: <https://openrouter.ai/openai/gpt-5.4-mini/apps>
- Escalation model catalog page: <https://openrouter.ai/openai/gpt-5.4>
# Successor verification note — 2026-08-05

The client-usable expansion re-ran the production-schema probe and 64-fixture live evaluation.
OpenRouter/Azure returned HTTP 200 for `openai/gpt-5.4-mini`; all thresholds passed with strict
schema/resolver/injection agreement and no invented fields or raw MT output. Tenant partitioning
was added to cache-key context. Exact aggregate evidence is in
`CLIENT_USABLE_SWIFT_PLATFORM_REPORT.md`; no prompts, responses, or secrets were recorded.
