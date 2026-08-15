# OpenRouter LLM Integration Plan

Plan date: 2026-08-04

Status: self-reviewed implementation baseline. This is an autonomous execution plan, not an approval gate.

## 1. Repository findings

- Git is initialised on `main` but has no commits. Every existing application file is intent-to-add/uncommitted user work and must be preserved. There are no unrelated deletions or conflicting tracked changes.
- The application is a verified FastAPI/Pydantic/SQLAlchemy/SQLite backend and Next.js 16/React 19/TypeScript frontend. Five deterministic composers, layered validation, profiles, lifecycle correlation, Excel/reporting, raw subset parsing, security middleware, Docker assets, and 70 backend plus 5 browser tests already exist.
- `httpx==0.28.1` exists in development requirements because FastAPI tests need it, but no runtime HTTP/LLM SDK exists. Promoting this single dependency to runtime is the smallest, most testable option. No OpenAI/OpenRouter SDK will be added.
- Initial integration ran without credentials. During the later live-remediation phase, an ignored root `.env` supplied an authorised runtime key. Presence was checked without printing the value; `.env` remains ignored and was never modified.
- `.env` files, runtime databases/reports, virtual environments, Node modules, builds, and test artifacts are ignored.
- No repository CI configuration exists. Quality commands are Make targets plus direct Ruff, mypy, Pytest, ESLint, TypeScript, Next build, Playwright, Alembic, npm audit, and Docker Compose checks.
- The frontend has repository-local Next.js instructions. Interactive Guided changes remain a serialisable Client Component; server-only secrets will never use a `NEXT_PUBLIC_` name.

## 2. Current agent architecture

`backend/app/agents/fallback.py` synchronously maps a small phrase vocabulary into the existing `ScenarioInterpretation`. `structured.py` is a provider-neutral synchronous callback wrapper that demonstrates strict Pydantic validation and one correction attempt but performs no network I/O. `prompts.py` contains unversioned intent/correction constants. `/api/agent/interpret` currently calls the deterministic interpreter directly and the Guided UI calls that endpoint while describing it as offline.

The current boundary is useful but not sufficient for production: it is synchronous, uses a generic dictionary transport, returns a full scenario rather than an auditable partial patch, has no privacy preprocessing, provider settings, lifecycle-managed client, circuit breaker, budgets, usage metadata, or honest provider status.

## 3. Current deterministic fallback behaviour

The fallback recognises Receive/Deliver, FOP/DVP, Buy/Sell, quantity, and ISIN. Buy/Sell may propose direction but marks it for confirmation. It uses the deterministic resolver and never composes raw MT. It will remain as an explicitly named non-AI endpoint and degraded-service/form aid. The production OpenRouter endpoint will never silently substitute it or label it as AI.

## 4. Proposed OpenRouter integration architecture

```text
POST /api/agent/interpret
  -> input length/control-character checks
  -> per-request sensitive placeholder tokenisation
  -> AiInterpretationService
       -> daily budget + circuit breaker
       -> OpenRouterClient (async pooled httpx)
       -> strict chat-completions JSON Schema response
       -> correction retry / bounded HTTP retries / optional escalation
       -> raw/tag/invention/grounding/placeholder validation
       -> safe partial canonical patch and conflict detection
  -> deterministic resolver
  -> deterministic missing-field engine (frontend continues existing call)
  -> safe AI metadata + content-free audit record
```

FastAPI lifespan creates and closes the pooled client/service on `app.state`. Routes retrieve the service from the request, keeping provider code out of domain/composer modules and enabling test injection. When required OpenRouter configuration has no key, startup remains diagnostic-capable, `/api/ai/health` reports degraded, `/api/agent/interpret` returns a controlled 503, and all structured message/profile/validation/form endpoints continue.

## 5. Model-selection strategy

- Pinned primary default: `openai/gpt-5.4-mini`.
- Pinned escalation default: `openai/gpt-5.4`.
- No router aliases, free router, arbitrary user slug, random selection, `order`, `only`, or `sort`.
- Operators may override both slugs only through server environment configuration.
- Escalation is at most one model transition per operation and occurs for exhausted primary transient/schema failures, low confidence when not merely caused by missing business data, contradiction, complex combined lifecycle intent, or conflict with high-confidence local parsing.
- Missing required financial information goes to the deterministic question engine rather than triggering escalation.

Both required model slugs were confirmed in the current OpenRouter model catalog. The primary is the lower-cost/high-throughput interpreter; the larger model is reserved for bounded ambiguity/recovery.

## 6. Structured-output schema

A new strict Pydantic `ModelInterpretationResult` generates the exact JSON Schema sent as `response_format.type=json_schema`, named `securities_settlement_interpretation`, with `strict=true` and `additionalProperties=false` throughout. It contains:

- controlled lifecycle/direction/payment/transaction/function/response-action intent;
- controlled extracted field paths only;
- string values with `EXPLICIT` or `PLACEHOLDER` source;
- sanitised evidence offsets and optional issued placeholder ID;
- ambiguity and missing-decision arrays;
- short beginner summary;
- confidence in `[0, 1]` and clarification boolean.

It has no `messageType`, validity, raw message, tag, qualifier, tool, prompt, or reasoning field. Parsed content receives Pydantic validation plus semantic validation for grounding, placeholders, field value types, forbidden tag/raw patterns, and inferred-value exclusion. The deterministic resolver alone calculates the MT type.

## 7. Data-minimisation strategy

- Send only the current user turn, a small controlled vocabulary/system instruction, and minimal confirmed non-sensitive intent context when supplied.
- Enforce the configured character limit without silent truncation.
- Reject null, bidirectional, and unsafe Unicode control characters; normal whitespace remains valid.
- Tokenise ISINs, account/reference/party/BIC-like values, and long account-like numbers into typed random request-local placeholders.
- Accept only placeholders issued in that request and mapped to a compatible allowed field.
- Rehydrate after strict schema/semantic validation; clear the mutable placeholder map in `finally`.
- Do not send raw MT, canonical objects, lifecycle histories, validation reports, profiles, accounts, or previous conversation transcripts.
- Do not persist input, response, prompt text, or mappings. Persist only safe metadata.

## 8. Prompt-injection controls

- Versioned prompt asset `settlement-intent-v2` is separate from business logic and covered by a hash/snapshot test.
- System instructions define a single interpretation task, explicit-only extraction, untrusted user text delimiters, no tools, no raw MT/tags, no hidden-prompt disclosure, no validity/compliance decision, and schema-only output.
- Request contains no tools or tool-choice capability.
- Local post-validation rejects raw-block/tag patterns, extra properties, unknown paths/enums/placeholders, invented/ungrounded values, commentary outside JSON, and output that attempts to alter authoritative fields.
- Adversarial fixtures cover role changes, prompt disclosure, direct generation, validity bypass, hidden defaults, raw MT, XML/JSON/Markdown/code fences, repetition, and Unicode controls.

## 9. Retry, escalation, timeout, and circuit-breaker behaviour

- `httpx.AsyncClient` uses explicit 5-second connect and 30-second operation read/write/pool timeouts, plus a bounded overall interpretation deadline.
- Retry only connection/timeout failures and HTTP 408/429/500/502/503/504. Honour numeric or HTTP-date `Retry-After`, capped by the overall deadline. Otherwise use exponential backoff with bounded jitter.
- Do not retry 400/401/402/403/404/412/413/422. Authentication, credits, invalid request, schema support, and privacy incompatibility map to stable errors.
- `OPENROUTER_MAX_RETRIES=2` means at most two additional HTTP attempts per model. One separate schema-correction request is allowed on the primary before escalation. Escalation is attempted once.
- Privacy settings are identical on every retry/escalation. No retry ever disables ZDR, enables data collection, removes parameter enforcement, or changes to an arbitrary model.
- A process-local circuit opens after a configurable consecutive-failure threshold, cools down, permits one half-open probe, and closes on success. Health is read-only and never calls the model.

## 10. Error-handling strategy

`AiServiceError` maps to safe error envelopes without provider content or traces. Stable codes include `AI_NOT_CONFIGURED`, `AI_AUTHENTICATION_FAILED`, `AI_PAYMENT_REQUIRED`, `AI_RATE_LIMITED`, `AI_TIMEOUT`, `AI_PROVIDER_UNAVAILABLE`, `AI_PRIVACY_REQUIREMENTS_UNAVAILABLE`, `AI_SCHEMA_VALIDATION_FAILED`, `AI_ESCALATION_FAILED`, `AI_BUDGET_EXCEEDED`, `AI_INPUT_TOO_LARGE`, `AI_CIRCUIT_OPEN`, and `AI_UNSAFE_RESPONSE`.

Required/no-key mode returns 503 from the interpretation endpoint while the API starts for diagnostics and deterministic forms. Provider 503 with ZDR filters is treated as privacy-requirements unavailable; it is never retried with weaker routing. The frontend shows AI unavailable plus an explicit non-AI option.

## 11. API changes

- Preserve `POST /api/agent/interpret` request fields and existing response fields where practical; make it async and OpenRouter-backed. Extend response with intent, extracted fields, ambiguities, missing decisions, conflicts, confidence, clarification, and `ai` metadata.
- Add `POST /api/agent/interpret-deterministic` for an explicitly labelled `deterministic_non_ai` result.
- Add `GET /api/ai/health` returning configured/mode/provider/models/escalation/circuit/last success/privacy and aggregate content-free telemetry only.
- API errors keep the existing envelope and request ID. No key, header, prompt, raw provider body, hidden prompt, reasoning, or placeholder mapping crosses the boundary.

## 12. Frontend changes

- Guided flow calls the real endpoint, shows interpreting/completed/clarification/unavailable states, safe retry, extracted business information, and provider/model metadata.
- It separates “AI interpretation” from “deterministic resolution,” “deterministic missing information,” and “deterministic composition/validation.”
- Required/no-key mode exposes **Use deterministic non-AI interpretation** and retains the editable normal form. It never calls that fallback silently.
- Add a safe diagnostics panel from `/api/ai/health`; no API key or arbitrary model control exists in the browser.
- Preserve existing subset/no-transmission/no-certification wording and all generation/lifecycle/bulk screens.

## 13. Configuration changes

Settings add validated environment-driven OpenRouter models/base URL/key, required/optional AI mode, provider privacy flags, timeouts/retries/deadline, input/output/confidence limits, optional daily budgets, circuit controls, and content-logging prohibition. Defaults follow the prompt exactly: provider `openrouter`, mode `required`, pinned models, parameter enforcement, fallbacks allowed, data collection denied, and ZDR required.

`mock` is accepted only when `APP_ENV=test`; deterministic behavior is selected only through the explicit non-AI endpoint or `AI_PROVIDER=disabled`. `.env.example` contains an empty key. Compose passes server settings and accepts the key from its environment without embedding it.

## 14. Observability and cost controls

- Process-local telemetry tracks requests, success/failure by safe code, primary/escalation, schema retries, input character counts, token counts, reported cost, latency average/p95, rate/budget events, and circuit state.
- Content-free structured log events include only internal request ID, provider/model, attempt, latency, counts, escalation reason, outcome, prompt/schema versions, and circuit state.
- SQLite stores the same safe audit metadata in a new nullable/backward-compatible table; no input/model content or mapping.
- Configurable daily interpretation-request/token budgets fail closed. Token reservations conservatively cover the maximum primary/correction/escalation calls and reconcile to returned usage; individual HTTP retry count is bounded separately. Output tokens, input characters, retries, escalation, and overall deadline are bounded.
- OpenRouter non-streaming responses already include token/cost usage; no extra usage request is made.

## 15. Testing and evaluation strategy

- Unit tests: configuration/key/header safety, request construction/schema/provider privacy, error classification/backoff, circuit, budgets, tokenisation/rehydration/disposal, prompt version, patch validation/conflicts, telemetry/redaction, raw/tag/invention rejection.
- `httpx.MockTransport` contract tests: success, malformed/invalid/extra/enum/raw responses; 401/402/408/429/500/timeout; retry; escalation; both unavailable; 503 ZDR incompatibility; usage and missing response fields.
- API tests: no-key 503, explicit deterministic metadata, safe health, no secret leakage, injected mock service success.
- Frontend/Playwright: unavailable/retry/non-AI path in credential-free test environment plus existing deterministic generation/profile/negative/lifecycle/bulk flows.
- Versioned JSON evaluation dataset with at least 60 synthetic scenarios across all requested intents, ambiguity, extraction, mistakes, adversarial and long inputs. Offline contract evaluation uses explicit test mock responses and reports pipeline safety separately from model quality.
- If a key is present, a separately marked live test/evaluator performs one isolated production-schema preflight before the 64-fixture dataset and records aggregate metadata only. A live key became available during remediation and both the preflight and full quality gates were executed.
- Full existing golden/API/UI/migration/security/Docker regression suite remains mandatory.

## 16. Expected files to create or modify

Create: `agents/schemas.py`, `preprocessing.py`, `errors.py`, `telemetry.py`, `circuit_breaker.py`, `budgets.py`, `service.py`, `providers/base.py`, `providers/openrouter.py`, versioned evaluation JSON/runner, OpenRouter unit/contract/API/security tests, Alembic AI-audit migration, this plan, and final integration report.

Modify: configuration, prompts, fallback naming/metadata adapter, API routes/errors, FastAPI lifespan, domain response/request models, persistence models/repository, runtime requirements, `.env.example`, Compose, Guided component/contracts/Playwright, README, ARCHITECTURE, API, SECURITY, TESTING, LIMITATIONS, and existing implementation report.

No composer, resolver, profile, validation, raw parser, lifecycle, bulk, or report algorithm will be replaced.

## 17. Backward-compatibility considerations

- Existing interpretation request (`text`, `profileId`) remains valid; optional current scenario/confirmed fields are additive.
- Existing response fields (`scenario`, `resolution`, `detectedFields`, `explanation`, `requiresBusinessConfirmation`) remain, with additive AI/audit fields.
- Message-generation, validation, profile, lifecycle, bulk, report, and raw APIs are unchanged.
- Old database rows remain valid; the new audit table has no foreign-key requirement that would invalidate existing messages.
- The intentional runtime behavior change is documented: `/api/agent/interpret` is real AI and returns 503 when required AI is unavailable rather than silently using deterministic interpretation.

## 18. Rollback strategy

- Set `AI_PROVIDER=disabled` and use the explicit deterministic endpoint/form; all deterministic generation remains functional.
- Provider modules are isolated and can be removed without composer/domain changes.
- The additive audit table can remain harmlessly on rollback; no destructive downgrade is required.
- Frontend retains the normal form and can hide only AI diagnostics/interpreter actions if rolled back.
- Because the repository has no baseline commit, no reset/checkout/rewrite will be used; changes remain reviewable in Git diff.

## 19. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Model invents financial data | Explicit-only schema, grounding, placeholders, local parsing/type validation, unsafe-response rejection. |
| Prompt injection | Versioned system boundary, no tools, untrusted delimiters, strict schema, raw/tag/prompt-output rejection, adversarial tests. |
| Privacy-incompatible endpoint | `require_parameters`, `data_collection=deny`, `zdr=true` on every request; controlled failure only. |
| Key/content leakage | Server-only secret, no content logs/storage, redaction tests, safe exceptions/telemetry. |
| Provider outage/latency | Bounded retry/escalation/deadline, circuit breaker, honest UI, explicit non-AI form. |
| Cost runaway | Input/output/rate/retry/escalation/daily request/token limits and usage telemetry. |
| LLM changes MT authority | Model schema excludes type/tags/validity; deterministic resolver/composer/validation unchanged. |
| Multi-turn overwrite | Current canonical scenario is authoritative; conflicts are surfaced and not merged. |
| Test mocks mistaken for production | `mock` provider restricted to `APP_ENV=test`; metadata always declares source. |
| Uncommitted baseline overwritten | Targeted patches only, no destructive Git operations, final full diff/status review. |

## 20. Exact acceptance criteria

1. OpenRouter client uses async pooled `httpx`, Bearer auth, configured base URL, pinned primary/escalation defaults, explicit timeouts, bounded retries, and lifecycle close.
2. Every request includes strict Pydantic-derived JSON Schema plus `require_parameters=true`, `allow_fallbacks=true`, `data_collection=deny`, and `zdr=true` by safe default.
3. Only controlled intent and grounded partial fields are accepted; no model-supplied message type, raw MT, tags, validity, invented value, unknown path/enum/placeholder, or commentary passes.
4. Sensitive values are tokenised per request, type checked, rehydrated after validation, and the map is cleared/not persisted.
5. Deterministic resolver, missing engine, client profile, composers, validators, lifecycle, bulk, and reports remain authoritative and regression-tested.
6. Primary and escalation attempts are bounded with documented triggers; missing ordinary business fields do not cause escalation.
7. No-key required mode starts degraded, reports safe health, returns controlled AI 503, and preserves explicit non-AI form generation.
8. Circuit breaker, budgets, content-free telemetry, safe persistent audit metadata, and error codes are tested.
9. Guided UI accurately labels AI/provider/non-AI sources and separates interpretation from deterministic selection/composition/validation.
10. At least 60 versioned synthetic evaluation fixtures run; preflight failure stops with `live_preflight_failed`, while successful live metrics are reported separately from offline contract checks.
11. All requested unit/contract/security/API tests and existing message/5 Playwright regression paths pass, plus lint/type/build/migration/audit/secret/diff/Docker checks.
12. Documentation and `OPENROUTER_LLM_INTEGRATION_REPORT.md` cover configuration, security/privacy, operations, key rotation/exposure, disablement, evidence, limitations, and production gaps without secrets or certification claims.

## Plan self-review

Reviewed against every section of the integration request. The plan explicitly covers reconnaissance, exact model slugs, provider-neutral async client, strict schema, ZDR/data denial/parameter enforcement, data minimisation, prompt injection, retries/escalation/deadline/circuit breaker, safe errors, API/UI, mock isolation, telemetry/cost budgets, multi-turn conflict handling, audit persistence, 60+ evaluation, live-key branching, complete regression verification, documentation, rollback, and honest limitations. It preserves all deterministic authority boundaries and adds no destructive operation. No omission requiring a plan correction remains.

## Autonomous progress log

- Milestone 1: reconnaissance complete; current official OpenRouter structured-output, routing/privacy, authentication/header, error/retry, usage, and model catalog documentation reviewed; plan self-review passed.
- Milestone 2: OpenRouter core complete. Added validated pinned configuration, async pooled `httpx` provider, strict Pydantic JSON Schema, versioned prompts, privacy routing, bounded HTTP retry/`Retry-After`, safe error classification, unit and mock-transport contract coverage.
- Milestone 3: agent integration complete. Added per-request tokenisation/rehydration/disposal, grounding and unsafe-output rejection, deterministic resolver merge, multi-turn conflict protection, bounded correction/escalation, circuit breaker, daily budgets, content-free telemetry, and additive AI audit migration. Backend regression suite is green at this checkpoint.
- Milestone 4: API/frontend integration complete. `/api/agent/interpret` now uses real provider configuration, `/api/agent/interpret-deterministic` is explicit non-AI, `/api/ai/health` is read-only/safe, and Guided Generation shows AI, clarification, unavailable, retry, and deterministic-authority states. Frontend lint, typecheck, and production build pass at this checkpoint.
- Milestone 5: security and operations complete. Added content-free/redacted logging compatible with Uvicorn access records, safe aggregate telemetry and audit persistence, process-local circuit/rate/budget controls, Docker/environment propagation, protected demo reset behavior, and dependency/secret/security checks. Docker images built and the degraded no-key runtime smoke passed.
- Milestone 6: live remediation and final verification complete. The production request initially failed before token usage because Azure was excluded by `temperature` and legacy `max_tokens` under `require_parameters=true`; the direct minimal probe succeeded because it omitted those endpoint-incompatible fields. The client now omits `temperature`, uses `max_completion_tokens`, normalises/lints the Pydantic schema, preserves primary provider diagnostics, isolates preflight/circuit state, and counts only transient infrastructure failures toward the circuit.
- Milestone 6 live evidence: `make probe-live-ai` returned HTTP 200 from Azure using `openai/gpt-5.4-mini`, strict schema v2, 1,545 prompt/103 completion tokens, reported cost 0.00075825, and deterministic MT541 resolution. The final standalone 64-fixture evaluation passed with 100% schema, intent, clarification, resolver, and injection-boundary rates; zero invented fields; zero raw MT outputs; 11 escalations; 114,675 prompt and 10,299 completion tokens; 3,700 ms average latency; and provider-reported total cost 0.09088350.
- Final regression evidence after dependency remediation: 156 non-live backend tests passed (1 live test deselected by default), the separate live test passed, all 5 Playwright flows passed, lint/type/build/migration/API smoke/secret/diff checks passed, Python and npm audits reported no known vulnerabilities, both Docker images built, and the container health/frontend smoke passed. The local Docker daemon's non-default seccomp warning remains an environment hardening gap.

## Live-request diagnostic addendum and self-review

The one-request probe uses the real prompt and authoritative normalized schema, only the primary model, no escalation, and a separate client with no application circuit state. It prints only HTTP status, safe OpenRouter error type/message, schema paths, model/provider, usage, cost, latency, prompt/schema versions, and deterministic resolution.

Schema normalization is a single fail-closed function. It removes `default`/`title`, makes every object property required, represents optional values through a required nullable branch, sets `additionalProperties:false` recursively, preserves and resolves local `$defs`, rejects arbitrary mappings/root unions/unknown enums/authoritative MT output fields, and is exercised by dedicated lint tests.

Permanent provider/configuration/schema/privacy/authentication/credit failures are not retried, escalated, or counted by the circuit. Only bounded transient network, timeout, rate-limit, and retryable 5xx failures affect it. Evaluation preflight stops the corpus with `live_preflight_failed` and null quality metrics if any production-schema, usage, or deterministic-resolution check fails.

Final self-review: every diagnostic/remediation requirement is implemented without reducing ZDR, data-collection denial, parameter enforcement, pinned models, prompt-injection controls, or deterministic message authority. The plan and final report contain no key, prompt body, model response body, or placeholder map.
