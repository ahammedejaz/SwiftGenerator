# Intelligent SWIFT Message Engineering and Testing Platform Expansion Report

Status: implementation and verification complete for the documented bounded scope  
Started: 2026-08-05  
Detailed plan: [SWIFT_PLATFORM_EXPANSION_PLAN.md](SWIFT_PLATFORM_EXPANSION_PLAN.md)

> Controlled demonstration subset only. No Swift network transmission, certification, or universal ISO 15022 conformance is claimed.

## Milestone progress

### Milestone 1 — Reconnaissance and plan: complete

Repository findings:

- Existing uncommitted application preserved; no Git commit baseline exists.
- FastAPI/Pydantic/SQLAlchemy/SQLite, Next.js/React, Alembic, Docker, Pytest, and Playwright conventions will be extended.
- Existing MT540–MT548 composers and OpenRouter authority/security boundaries remain unchanged.
- Official ISO 15022 catalogue and Swift Category 5 sources were reviewed for the bounded MT530, MT537, and MT564–MT568 scope.
- Rules requiring an institution or market implementation guide are explicitly disabled rather than inferred.

Files created:

- `SWIFT_PLATFORM_EXPANSION_PLAN.md`
- `SWIFT_PLATFORM_EXPANSION_REPORT.md`

Baseline checks:

- `make lint`: passed.
- `make typecheck`: passed; mypy checked 61 source files.
- `make test`: passed, 156 tests; one live test deselected; one Starlette TestClient deprecation warning.
- `docker compose config --quiet`: passed.
- `git diff --check`: passed.

Known issues:

- No authentication boundary exists for global cache administration, so cache clearing will be CLI-first and any HTTP control will be development-only and explicitly gated.
- The repository has no commit baseline, limiting diff attribution; all existing files are treated as user-owned.

Next milestone: Tag Intelligence foundation.

### Milestone 2 — Tag Intelligence foundation: complete

Implemented:

- Strict, versioned tag-knowledge models, loader, duplicate/signature/dependency/provenance checks, profile overlays, and startup coverage validation.
- 120 knowledge records covering every field signature emitted by MT540–MT548, with concise derived metadata and stable internal references to the reviewed authorised source set.
- Message-specific PSET explanations, profile-effective presence, BFS overlay, dependency display, synthetic examples, and explicit warning that PSET is not a generic counterparty account.
- Deterministic knowledge list, search, explain, tag-detail, and dependency APIs. Normal tag details make no LLM call.
- Knowledge Centre UI and clickable field details in Business, Tag, and Raw views.

Significant files created or modified:

- `backend/app/knowledge/models.py`
- `backend/app/knowledge/loader.py`
- `backend/config/knowledge/settlement_v1.yaml`
- `backend/config/knowledge/overlays/bfs_client_demo_v1.yaml`
- `backend/app/api/routes.py`
- `frontend/app/knowledge/page.tsx`
- `frontend/components/knowledge/KnowledgeCentre.tsx`
- `frontend/components/knowledge/TagDetailsDrawer.tsx`
- `frontend/components/messages/MessageViews.tsx`
- focused backend and Playwright knowledge tests

Verification:

- Focused Pytest: 18 passed; one upstream Starlette deprecation warning.
- Ruff: passed for application and focused tests.
- mypy: passed across 64 source files.
- Frontend ESLint and TypeScript: passed.
- Next.js production build: passed; `/knowledge` prerendered successfully.
- Guided/Expert Playwright after drawer integration: 3 passed.
- Knowledge Centre Playwright: 1 passed.

Known limitations:

- Knowledge records cover the currently emitted settlement subset only at this milestone. MT530, MT537, and MT564–MT568 coverage is added with each source-bounded module rather than pre-populated with guessed fields.
- Knowledge explanations are concise derived metadata, not reproduced handbook content and not a certification claim.

Next milestone: LLM call avoidance, privacy-safe exact caching, and usage telemetry.

### Milestone 3 — LLM efficiency and cache: complete

Implemented:

- Explicit call-decision policy: authoritative knowledge, resolution, validation, generation, lifecycle, reporting, and raw-subset parsing remain deterministic; only language interpretation/simplification/comparison/translation are model-eligible.
- Exact HMAC-SHA256 cache identifiers over canonicalised, tokenised input plus minimal context, workflow/profile/standards/prompt/schema/knowledge/taxonomy/model/settings/language/audience versions.
- Request-local placeholder-template canonicalisation and rehydration. Cached payloads never contain unmasked account/reference values and are revalidated against the current schema and current request’s placeholder map.
- Persistent SQLite cache plus bounded L1, namespace TTLs, strict version invalidation, corruption eviction, process-local single-flight stampede protection, and fail-open cache persistence behaviour.
- Content-free interaction telemetry for live, cache, deterministic, and unavailable outcomes, including current tokens/cost/latency and separately labelled avoided usage.
- Usage, cache-statistics, and safe diagnosis APIs; Guided compact usage panel and AI Efficiency dashboard.
- Additive Alembic migration preserving existing AI audit records.

Significant files created or modified:

- `backend/app/agents/cache.py`
- `backend/app/agents/decision.py`
- `backend/app/agents/usage.py`
- `backend/app/agents/service.py`
- `backend/app/persistence/ai_cache.py`
- `backend/app/persistence/ai_usage.py`
- `backend/alembic/versions/20260805_0003_ai_cache_and_usage.py`
- `frontend/components/ai/AiUsagePanel.tsx`
- `frontend/components/ai/AiEfficiencyDashboard.tsx`
- `frontend/app/ai-efficiency/page.tsx`
- `.env.example` and `docker-compose.yml`

Verification:

- Cache/config/service/API focused Pytest: 64 passed in the combined milestone run; one upstream Starlette deprecation warning.
- Cache-specific tests: 13 passed, covering HMAC keys, version invalidation, cross-request placeholder isolation, live-then-cache usage, stampede control, expiry, and bounded L1.
- Ruff and mypy: passed; mypy checked 68 application source files.
- Frontend ESLint and TypeScript: passed.
- Next.js production build: passed; `/ai-efficiency` generated successfully.
- Guided regression Playwright after usage integration: 3 passed.
- AI Efficiency Playwright: 1 passed.
- Clean Alembic migration: upgraded `0001 → 0002 → 0003`; head `20260805_0003`.

Measured cache contract in tests:

- First request: one provider call, 120 provider-reported tokens, source `LIVE_API`.
- Equivalent tokenised second request: zero provider calls, zero new tokens, 120 tokens avoided, source `CACHE`.
- Concurrent exact requests: one provider call maximum.
- Cross-request account leakage: zero; each current request rehydrated only its own account value.

Known limitations:

- The L1 cache and single-flight coordinator are process-local. SQLite is the shared persistence layer for this deployment; a distributed lock/cache adapter remains future work.
- Cache is securely disabled when the HMAC secret is absent. Production configuration refuses to enable caching without a minimum-length server-side secret.
- Avoided cost is labelled as an estimate and comes only from the original validated provider usage, never a fabricated price calculation.

Next milestone: deterministic settlement cancellation, amendment decisions, and the source-bounded MT530 subset.

### Milestone 4 — Settlement commands: complete

Implemented:

- Deterministic amendment-policy registry with an explicit result for processing changes, core-business changes, cancellation-only requests, unsupported changes, and mixed requests requiring clarification.
- Cancellation requests for persisted MT540–MT543 instructions, unique references, immutable originals, active-duplicate prevention, MT548 accepted/rejected outcomes, and recursive lifecycle reporting.
- Source-bounded MT530 Transaction Processing Command support for priority (`PRIR`) only. The service enforces original-reference and safekeeping-account correlation and the configured 0001–9999 range.
- Cancel-and-rebook orchestration for supported quantity, identifier, amount, settlement-date, and safekeeping-account changes. The original instruction remains immutable and the replacement receives a new sender reference.
- Deterministic MT530 composer, supported-subset raw parser, golden file, validation, profile rules, five verified tag-knowledge records, APIs, and Settlement Processing UI.
- Hold/release, proprietary non-matching information, settlement-party edits, and universal MT530 amendment claims are explicitly disabled pending an approved institution implementation guide.

Significant files created or modified:

- `backend/app/workflows/settlement_processing.py`
- `backend/config/workflows/settlement_amendment_v1.yaml`
- `backend/app/composers/settlement_command.py`
- `backend/config/knowledge/settlement_command_v1.yaml`
- `backend/app/raw/validator.py`
- `backend/app/persistence/repository.py`
- `frontend/app/settlement-processing/page.tsx`
- `frontend/components/settlement-processing/SettlementProcessingStudio.tsx`
- focused workflow, golden, knowledge, and Playwright tests

Verification:

- Focused settlement-processing, MT530 golden, and knowledge Pytest: 24 passed; one upstream Starlette deprecation warning.
- Ruff and mypy: passed; mypy checked 72 application source files.
- Frontend ESLint and TypeScript: passed.
- Next.js production build: passed; `/settlement-processing` prerendered successfully.

Known limitations:

- The verified MT530 subset only modifies priority. It is not a universal amendment implementation.
- Cancel-and-rebook settlement-party changes remain disabled because the existing canonical model stores those parties as a group and no approved per-party amendment policy is configured.
- Existing settlement Excel remains available; dedicated settlement-command workbook columns are deferred to the cross-workflow Excel expansion.

Next milestone: the source-bounded MT537 penalty statement subset.

### Milestone 5 — Penalties: complete for the bounded API/UI subset

Implemented:

- Typed MT537 penalty statement and entry models for current, new-only, and updated-or-removed lists; new, updated, and removed actions; active, not-computed, and removed statuses; SEFP and LMFP types; payable and receivable amounts.
- Deterministic MT537 composer following the verified penalty-specific GENL/PENA/PENACUR/PENACOUNT/PENDET subset, including controlled list/type/status codes, supplied AMCO amounts, supplied day count, and optional settlement linkage.
- The service never calculates or guesses a penalty amount. It only reports explicit synthetic input and deterministically nets supplied values for the required counterparty-group total.
- Profile currency enforcement, duplicate/reference/action/status validation, settlement-reference correlation, dedicated persistence, lifecycle API, supported-subset raw parsing, golden file, 23 knowledge records, API endpoints, and Penalty Studio UI.
- Generic `workflow_messages` persistence and migration, designed for penalty and corporate-action modules without altering the existing settlement tables.

Significant files created or modified:

- `backend/app/workflows/penalties.py`
- `backend/app/composers/penalty_statement.py`
- `backend/config/knowledge/penalties_v1.yaml`
- `backend/app/persistence/workflow_messages.py`
- `backend/alembic/versions/20260805_0004_workflow_messages.py`
- `frontend/app/penalties/page.tsx`
- `frontend/components/penalties/PenaltyStudio.tsx`
- `frontend/components/messages/WorkflowMessageViews.tsx`
- MT537 workflow, golden, knowledge, raw-parser, and Playwright tests

Verification:

- Focused penalty/golden/knowledge Pytest: 23 passed; one upstream Starlette deprecation warning.
- Ruff: passed for application, migration, and focused tests.
- mypy: passed across 76 application source files.
- Frontend ESLint and TypeScript: passed.
- Next.js production build: passed; `/penalties` prerendered successfully.

Known limitations:

- This is a narrow penalty-reporting subset, not a complete MT537 pending-transaction statement implementation.
- It groups one currency and detection date per generated message and uses a source-backed synthetic proprietary party representation. Multi-currency grouping is deferred.
- Penalty calculation, rates, instrument calculation details, and market-specific netting are intentionally unsupported because no approved deterministic calculation rule pack is available.
- Cross-workflow Excel columns and ZIP reporting are completed in the shared bulk/reporting hardening milestone.

Next milestone: the source-bounded MT564–MT568 corporate-action lifecycle.

### Milestone 6 — Corporate Actions: complete for the verified DVOP lifecycle slice

Implemented:

- Typed corporate-action models and deterministic MT564, MT565, MT566, MT567, and MT568 composers behind a dedicated workflow service.
- Event coverage bounded to voluntary Dividend With Options (`DVOP`). Notification and election expose controlled cash and securities options; the currently verified confirmation movement is cash only.
- Strict event, message, option, security, account, quantity, deadline, profile, reference, and lifecycle correlation checks.
- Controlled instruction processing statuses, rejection reasons, and guarded cancellation-status modelling. Cancellation statuses cannot be emitted for a normal instruction.
- Narrative sanitisation rejects controls, role-changing code text, and raw MT fragments; MT568 supplementary text cannot replace structured event data.
- Persistent workflow lifecycle retrieval and an allowlisted raw parser that supports nested and repeated corporate-action sequences.
- 52 verified tag-knowledge records across MT564–MT568, taking repository knowledge coverage to 200 records.
- Corporate Actions UI and Playwright flow for notification → election → pending status → cash confirmation, with an associated MT568 narrative.
- One golden file per MT564–MT568 plus focused API, validation, correlation, raw-parser, and narrative-boundary tests.

Verification:

- Corporate-action/golden/knowledge/raw-parser focused Pytest: 28 passed.
- Ruff: passed; mypy: passed across 78 application source files.
- Frontend ESLint and TypeScript: passed.
- Next.js production build: passed; `/corporate-actions` generated successfully.

Known limitations:

- Only the reviewed `DVOP` event is enabled. Cash dividend, interest, redemption, and exchange-offer rule packs remain disabled rather than guessed.
- MT566 cash movement is implemented. Securities-movement confirmation is explicitly rejected pending a separately approved movement rule pack.
- MT565 cancellation construction is not enabled in this slice; cancellation-processing status types are reserved for a future verified cancellation-instruction path.
- Corporate-action Excel/report-specific extensions are completed in the cross-workflow hardening milestone.

Next milestone: workflow registry and capability discovery.

### Milestone 7 — Workflow registry: complete

Implemented:

- Added a typed `WorkflowModule` protocol and immutable registered module descriptors.
- Added one-owner validation for every implemented message type and deterministic module lookup.
- Registered Settlement, Settlement Command, Penalties, and Corporate Actions modules with explicit implemented or partially implemented status, bounded features, limitations, and knowledge coverage.
- Added profile-aware capability discovery at `GET /api/capabilities`.
- Capability responses distinguish implemented, partially implemented, disabled, planned, and unsupported claims. Future workflow names are discovery metadata only and do not imply implementation.
- The registry exposes module-owned knowledge records and prevents new message ownership from being silently duplicated.

Verification:

- Registry/capability and corporate-action regression subset: 12 passed.
- Ruff: passed.
- mypy: passed across 79 application source files.

Known limitations:

- Existing settlement composers retain their five shared implementation classes. The registry owns capability/message dispatch metadata; a future adapter can move each service invocation behind the same interface without rewriting proven composers.
- Planned workflow entries have no executable handler and are accurately labelled planned.

Next milestone: cross-workflow Excel/report expansion, evaluation, security hardening, and final verification.

### Milestone 8 — Evaluation and hardening: complete

Implemented:

- Shared workflow Excel template/import/ZIP export for settlement commands, penalties, and the implemented corporate-action lifecycle. Rows are isolated, valid rows continue when another row fails, and corporate rows can correlate by a prior valid row reference.
- Workflow report endpoint with module, message, profile/release, provenance, tag explanations, findings, relationships, and content-free AI usage metadata.
- Versioned 195-fixture expansion evaluation plus exact two-pass cache assessment.
- Twelve documentation guides/reviews covering the architecture, bounded rule packs, security, operations, testing, and unsupported areas.

Final verification evidence:

- `make lint`: passed Ruff and ESLint.
- `make typecheck`: passed mypy for 82 source files and TypeScript.
- `make test`: **233 passed, 1 live test deselected**, one upstream Starlette deprecation warning.
- `make build`: passed the Next.js production build with 12 routes.
- `make e2e`: **10 passed** in 16.3 seconds on the final rerun.
- `make probe-live-ai`: HTTP 200 through Azure using `openai/gpt-5.4-mini`, 1,545 prompt + 101 completion = 1,646 tokens, provider-reported cost 0.00074925, 4,157 ms, and deterministic MT541 agreement.
- `make test-live-ai`: **1 passed, 232 deselected** in 180.55 seconds.
- `make evaluate-ai`: 64/64 live fixtures evaluated; schema, intent, clarification, resolver, and prompt-injection authority rates all 100%; 0 invented protected values and 0 raw MT output; 122,950 tokens; provider-reported cost 0.08407925; 3,438 ms average latency; 10 escalations.
- `make evaluate-platform`: 195/195 offline expansion contracts passed; exact-cache pass two made 0 provider calls and used 0 new tokens.
- Clean Alembic upgrade reached `20260805_0005 (head)`.
- `make audit`: no known Python dependency vulnerabilities and 0 npm production vulnerabilities.
- Docker Compose config, backend/frontend image builds, runtime health/capability/front-end smoke, and clean shutdown passed.
- Formatter check covered 133 files; secret-pattern scan found no real secrets; `git diff --check` passed.

---

## 1. Executive summary

The repository now implements a modular **Intelligent SWIFT Message Engineering and Testing Platform** while retaining the proven MT540–MT548 settlement path. It adds deterministic tag intelligence, privacy-safe exact LLM caching and efficiency telemetry, settlement cancellation/amendment decisions with a bounded MT530 command, a bounded MT537 penalty-statement workflow, and a source-bounded MT564–MT568 Dividend With Options corporate-action lifecycle.

All message resolution, tag/qualifier choice, ordering, composition, validation, profile enforcement, and lifecycle correlation remain deterministic. OpenRouter interprets constrained language only; it is neither a standards source nor an authoritative message generator.

Readiness: the implemented demonstration slices are fully buildable and testable and the live settlement-intent evaluation passed. The platform is **not** SWIFT-certified, institution-approved, connected to the SWIFT network, or ready for real financial instructions.

## 2. Repository starting state

The starting repository already contained FastAPI/Pydantic/SQLAlchemy/SQLite/Alembic, Next.js/React/Tailwind, five shared settlement composers for MT540–MT548, layered validation, client profiles, raw-subset parsing, Excel/report flows, Docker, Pytest/Playwright, and a production-oriented OpenRouter boundary with strict structured output. Git had no commit baseline and all existing changes were treated as user-owned and preserved. No existing composer or validator was replaced.

## 3. Approved implementation scope

Implemented scope is intentionally bounded:

- Existing settlement: MT540–MT548 unchanged and regression-tested.
- Settlement processing: cancellation workflow, accepted/rejected MT548 outcomes, deterministic amendment policy, priority-only MT530, and configured cancel/rebook.
- Penalties: MT537 penalty reporting for explicit supplied data; no penalty calculation.
- Corporate actions: voluntary DVOP notification, election, processing status, cash confirmation, and related narrative.
- Platform services: Tag Intelligence, workflow registry/capabilities, exact LLM cache, usage dashboard, workflow Excel/ZIP, and workflow reports.

Deferred or disabled rules are listed in sections 30–32. No guessed event, tag, qualifier, code, calculation, or transition was enabled.

## 4. Final architecture

```text
UI / REST / Excel
  -> workflow registry and profile capability check
  -> typed canonical workflow model
  -> deterministic missing-field / amendment / correlation rules
  -> deterministic composer
  -> layered validation
  -> message + field map + provenance-aware report

Unstructured language only
  -> local deterministic decision
  -> exact HMAC cache lookup
  -> OpenRouter strict structured interpretation when necessary
  -> schema, placeholder, profile and authority validation
  -> deterministic workflow path above
```

Knowledge, cache, provider, persistence, workflow-domain, composition, and API/UI concerns are separated. Cached model output is still untrusted and passes the same current schemas and deterministic checks.

## 5. Workflow-module architecture

`backend/app/workflows/registry.py` defines the `WorkflowModule` contract and immutable module descriptors. It enforces exactly one owner for each executable message type and supplies profile-aware capability discovery. Registered modules are Settlement, Settlement Command, Penalties, and Corporate Actions. Planned Category 5, reconciliation, collateral, trade-confirmation, treasury, payment, and ISO 20022 entries are metadata only; they have no executable handlers.

`GET /api/capabilities` reports implemented, partially implemented, disabled, planned, and unsupported status with limitations. This avoids a growing global resolver branch while allowing proven settlement composers to remain stable.

## 6. Tag Intelligence architecture

The knowledge loader reads strongly validated, version-controlled YAML records. Startup validation detects duplicates, missing provenance/version/meaning, invalid message types/options, broken dependencies, and emitted-field coverage gaps. Effective records merge non-contradictory profile overlays.

Normal list, search, details, dependencies, and explanations are deterministic and make no LLM call. The Knowledge Centre and tag drawer expose business/technical meaning, purpose, question, presence and conditions, formats, related/dependent fields, client overlays, synthetic examples, lifecycle impact, and source/release/review status.

## 7. PSET implementation

PSET is clickable in Business, Tag, and Raw views. Its record explains that it is **Place of Settlement**, identifying the requested settlement location or venue—not a generic counterparty account. Depending on the specific message, option, market, and active profile it can represent a CSD, institution, country, or another approved representation. Each MT540–MT543 record has its own applicable presence rule and profile overlay; the UI does not generalise one message's rule. DEAG and REAG are shown only as verified related settlement-party fields.

## 8. Knowledge coverage by message

Startup and tests require every emitted signature to have knowledge. Current record counts are:

| Messages | Module | Records | Status |
| --- | --- | ---: | --- |
| MT540–MT548 | Settlement | 120 | Complete for emitted subset |
| MT530 | Settlement Command | 5 | Complete for priority-only subset |
| MT537 | Penalties | 23 | Complete for emitted subset |
| MT564–MT568 | Corporate Actions | 52 | Complete for emitted DVOP subset |
| **Total** |  | **200** | Startup-validated |

The records contain concise derived metadata and stable internal source references, not copyrighted handbook pages and not a certification claim.

## 9. MT530 coverage

MT530 supports only a source-backed processing priority command (`PRIR`) with values 0001–9999, original instruction linkage, account correlation, deterministic composition, raw-subset parsing, profiles, knowledge, golden tests, Excel, API, UI, persistence, and reporting. It is not described or implemented as a universal amendment message. Hold/release, proprietary non-matching details, arbitrary commands, and direct core-trade edits are rejected.

## 10. Cancellation and amendment behaviour

Cancellation requires an existing MT540–MT543 instruction, preserves direction/payment correlation and original immutability, prevents duplicate active cancellation requests, and can correlate controlled accepted/rejected MT548 status outcomes. Reports include original, cancellation, and status relationships.

The amendment registry returns `PROCESSING_DATA_MODIFICATION`, `CORE_BUSINESS_DATA_CHANGE`, `CANCELLATION_ONLY`, `UNSUPPORTED_MODIFICATION`, or `CLARIFICATION_REQUIRED`. Configured core changes use cancel-and-rebook, assign a new replacement reference, retain the original, and expose before/after values. The LLM cannot change this classification.

## 11. MT537 penalty coverage

The bounded MT537 module reports new, updated, or removed SEFP/LMFP penalties with active/not-computed/removed state, payable/receivable direction, explicit currency/amount, detection date, common/previous/related references, supplied day count, profile checks, duplicates, persistence, lifecycle, parser, knowledge, UI, Excel/ZIP, report, and golden tests.

No authorised penalty calculation rule pack exists in this repository. The application therefore requires explicit amounts and never derives rates, days, or penalty amounts. One generated message currently represents one detection date and currency grouping.

## 12. MT564–MT568 corporate-action coverage

The enabled event pack is voluntary Dividend With Options (`DVOP`):

- MT564: notification with event/security/account, deadlines/dates, controlled options/default, and entitlement context.
- MT565: cash or securities option election with correlated reference/account/security/quantity.
- MT567: controlled acknowledged/pending/rejected processing statuses for the implemented instruction path.
- MT566: cash confirmation with option/reference/quantity/currency/amount/payment-date correlation.
- MT568: sanitised supplementary narrative tied to the event.

The lifecycle view and Excel service support MT564 → MT565 → MT567 → MT566 with associated MT568. Securities-movement confirmation, MT565 cancellation construction, cash-dividend/interest/redemption/exchange event packs, and market-specific tax/entitlement calculations are disabled pending approved rule packs.

## 13. LLM call-decision pipeline

The service first checks local input constraints, deterministic handling, verified knowledge, workflow capabilities, and exact cache. Opening PSET, resolving Receive+DVP, validation, message generation, lifecycle responses, profile rules, dependencies, reports, and raw-subset parsing never require OpenRouter. Live calls are limited to eligible natural-language interpretation or controlled language assistance. Current production strict intent schema is the settlement schema; dedicated penalty/corporate conversational schemas remain a documented extension point rather than being simulated.

## 14. Cache architecture

The cache provides an async interface, bounded TTL L1, SQLite L2, and process-local single-flight. Namespaces distinguish intent interpretation, beginner explanation, comparison, validation simplification, translation, corporate-action intent, and penalty intent. Only validated structured payloads are cacheable; errors, approvals, generated references, raw messages, and final validation decisions are not.

The HMAC-SHA256 key includes operation, tokenised normalised input, minimal context fingerprint, workflow/message, profile ID/version, standards release, prompt/schema/knowledge/taxonomy/model/settings/language/audience, and cache-key version. It never includes secrets, raw MT, or unmasked identifiers.

## 15. Cache privacy

Sensitive accounts/references/parties are tokenised before keying. Cached templates may contain only request-scoped typed placeholders. Every hit revalidates the result and requires every placeholder to be issued by the current request before rehydrating from that request's temporary map. Cross-request and cross-profile tests prove isolation. Cache identifiers/payloads and the HMAC secret are never exposed to the browser or ordinary logs.

## 16. Cache invalidation

Prompt, schema, model, profile, standards-release, knowledge-base, taxonomy, or key-version changes cause a miss. TTL expiry, corruption, current-schema failure, unknown placeholders, or mismatched lifecycle fingerprints evict/reject the entry. Initial TTLs are 30 days for intent/validation explanations and 90 days for verified knowledge explanations/translations. Semantic similarity reuse is intentionally absent.

## 17. Token and cost telemetry

`ai_interactions` stores content-free source, namespace/hit/age, call counts, prompt/completion/total tokens, provider-reported cost, latency, avoided calls/tokens/cost, and prompt/schema/knowledge/profile versions. Original cached usage is kept separate from current zero-token cache-hit usage. Estimated avoided cost is emitted only when the source cache entry has a provider-reported cost; no price table or fabricated saving is used.

## 18. UI efficiency dashboard

Guided Generation includes a collapsible last-interaction panel. `/ai-efficiency` shows deterministic/live/cache interactions, hit rate, calls/tokens/cost used and avoided, primary/escalation counts, safe failures, and live/cached latency. It separately identifies the last real provider call. The UI never renders a key, raw key, prompt, provider body, cache payload, or sensitive identifier.

## 19. API changes

New deterministic knowledge APIs cover messages, tags, search, detail, explain, and dependencies. AI operations add last interaction, last provider call, summary, cache stats, and safe cache diagnosis. Workflow APIs add capabilities; settlement cancellation/amendment/MT530/cancel-rebook; penalty generate/validate; corporate notification/instruction/status/confirmation/narrative; generic workflow lifecycle/report; and workflow Excel template/generation. Existing settlement API contracts remain intact.

Administrative cache clearing is not exposed to normal HTTP users. Safe diagnosis returns configuration/counters only and never identifiers or payloads.

## 20. Database migrations

- `20260804_0002_ai_audit.py`: existing content-free OpenRouter audit.
- `20260805_0003_ai_cache_and_usage.py`: additive `ai_result_cache` and `ai_interactions` with backward-compatible defaults/indexes.
- `20260805_0004_workflow_messages.py`: additive generic workflow persistence with parent/related-message links.
- `20260805_0005_nullable_workflow_reports.py`: aligns the original report foreign key with workflow-level ZIP reports, which legitimately have no settlement scenario.

A clean SQLite database upgraded through 0001 → 0002 → 0003 → 0004 → 0005 and reported `20260805_0005 (head)`. A dedicated regression inserts a workflow report with a null settlement scenario after a real Alembic upgrade.

## 21. Significant file changes

Created domain groups include `backend/app/knowledge`, `backend/app/workflows`, the MT530/MT537/corporate composers, AI cache/usage repositories, workflow bulk/reporting services, three configuration rule packs and four knowledge YAML sets, migrations 0003/0004/0005, golden fixtures, and dedicated test packages. Frontend additions are `/knowledge`, `/ai-efficiency`, `/settlement-processing`, `/penalties`, and `/corporate-actions` with shared usage, knowledge, and workflow message components. Root documentation adds the six topic guides, this plan, and this report. No files were deleted.

## 22. Test results

| Check | Result |
| --- | --- |
| Ruff + ESLint | Passed |
| Ruff formatter | 133 files compliant |
| mypy + TypeScript | Passed; mypy checked 82 files |
| Complete non-live Pytest | 233 passed, 1 deselected, 1 warning |
| Next.js production build | Passed; 12 routes |
| Playwright | 10 passed in 16.3s |
| Alembic clean upgrade | Passed to 0005 head; workflow report null-scenario insert verified |
| Python/npm audit | No known Python vulnerabilities; 0 npm production vulnerabilities |
| Docker config/build/runtime smoke | Passed |
| Secret scan | No real secrets found |
| Git whitespace | Passed |

The single warning is Starlette's upstream deprecation of its current `httpx` TestClient compatibility path; production uses async `httpx` directly.

## 23. Live OpenRouter results

The ignored runtime environment contained a key; its value was never printed. `make probe-live-ai` returned HTTP 200 through provider Azure with strict JSON Schema, `require_parameters=true`, `data_collection=deny`, and `zdr=true`, using `openai/gpt-5.4-mini`: 1,545 prompt tokens, 101 completion tokens, 1,646 total, provider-reported cost 0.00074925, latency 4,157 ms, deterministic MT541 agreement.

`make test-live-ai` passed 1 live test with 232 deselected in 180.55 seconds. `make evaluate-ai` passed all 64 fixtures: 100% strict schema, unambiguous intent, ambiguity clarification, resolver agreement, and prompt-injection authority; 0 invented accounts/BICs/ISINs/references and 0 raw MT; 10 escalations; 113,099 prompt + 9,851 completion = 122,950 tokens; provider-reported cost 0.08407925; 3,438 ms average latency.

These are point-in-time synthetic settlement-intent results, not certification or proof for the new penalty/corporate domains.

## 24. Cache two-pass evaluation

`make evaluate-platform` generated and evaluated 195 versioned fixtures: 40 tag, 30 amendment, 25 penalty, 40 corporate, 20 injection, 20 ambiguity, and 20 cache cases. Offline schema/authority/clarification contracts passed 100%, with 0 invented protected categories and average deterministic knowledge search of 0.115 ms.

For the controlled exact-cache two-pass test, pass one made 20 synthetic provider calls and recorded 2,400 test tokens. Pass two produced 20/20 valid hits, 0 provider calls, 0 new tokens, 0 cross-request leakage, and 100% deterministic resolver agreement. Average measured cache operation times were 0.176 ms for pass-one write path and 0.044 ms for hits. This is an instrumented test-provider evaluation, not live-provider cost evidence.

## 25. API calls avoided

The expansion cache evaluation avoided **20 of 20** second-pass calls. The focused concurrency test also limited simultaneous identical requests to one provider call. No production-wide hit rate is claimed because there is no representative production traffic.

## 26. Tokens avoided

The controlled expansion evaluation avoided **2,400 synthetic test tokens** on pass two, with 0 new tokens. A separate cache integration fixture avoided the original 120 test tokens on its repeat. Live-provider avoided-token totals were not manufactured from these fixtures.

## 27. Cost avoided

Cost avoided is **not available** for the controlled expansion cache evaluation because its test provider did not report cost. The UI/API correctly return null rather than inventing savings. For real cached calls, the service carries forward only the original provider-reported cost as an explicitly labelled estimate.

## 28. Performance results

Measured local results were 0.115 ms average knowledge search, 0.044 ms average exact L1 cache hit, 0.176 ms average controlled cache write path, 1.30 seconds for 233 local backend tests, and 3,438 ms average live OpenRouter latency over 64 fixtures. On an isolated migrated SQLite database, 50 deterministic MT541 API generations averaged 1.782 ms each; a 100-row valid MT537 workbook completed in 105.465 ms (948.181 rows/second). These are single-process development-machine measurements, not load-test or service-level guarantees. Deterministic tag details do not invoke caching or OpenRouter. Docker health/capability and frontend route smoke returned HTTP 200.

## 29. Security review

The expansion retains backend-only OpenRouter keys, ZDR/data denial/parameter enforcement, strict schema and authority checks, input/rate/size limits, upload controls, prompt-injection boundaries, content-free logs/audits, and deterministic validation. It adds a server-only minimum-32-character cache HMAC secret, versioned HMAC keys, placeholder isolation, TTL/size limits, schema revalidation, poisoning/corruption fail-closed handling, bounded stampede waiting, provenance validation, narrative control/raw-tag rejection, and spreadsheet formula-injection escaping.

Docker intentionally reported cache disabled when no HMAC secret was supplied; this is secure degradation. Production configuration refuses enabled caching without that secret. Performance verification also found and corrected an original-migration mismatch (`reports.scenario_id` was non-null although the ORM and workflow report repository allow no settlement scenario); additive migration 0005 and a clean-migration regression now enforce the intended contract. A distributed lock, tenant ID dimension, managed secret store, authentication/RBAC, immutable audit, and formal penetration/privacy review remain deployment requirements.

## 30. Known limitations

- Controlled ISO 15022 demonstration subsets only; no network connectivity or certification.
- MT530 is priority-only; MT537 is penalty reporting only; corporate actions are voluntary DVOP with cash confirmation only.
- No penalty/entitlement/tax/rate calculation, securities-movement confirmation, or universal corporate event coverage.
- Corporate/penalty conversational interpretation uses deterministic forms today; the production LLM schema remains settlement-intent-specific.
- Expanded 195-fixture assessment is an offline contract/cache evaluation; only the 64 settlement corpus was live-evaluated.
- SQLite persistence, process-local L1/single-flight/circuit/rate/budget state, mutable audit, and no multi-tenant/RBAC boundary.
- Workflow Excel is a bounded shared template, not every optional ISO field or arbitrary message parser.
- No representative production load test or live cache hit-rate baseline.

## 31. Unsupported workflows

Additional Category 5 statements, reconciliation, collateral, trade confirmation, treasury, payments, ISO 20022 equivalents, cash-dividend/interest/redemption/exchange packs, MT565 cancellation construction, securities-movement confirmation, complete MT530 commands, penalty calculation/netting, and arbitrary raw parsing are planned or unsupported. Capability discovery labels them accurately and provides no executable route.

## 32. Production-readiness gaps

Before production consideration: obtain licensed/authorised institution rule packs and reviews; add authentication, RBAC, maker/checker, tenancy, managed secrets and rotation, PostgreSQL/shared cache/distributed locking, immutable audit/SIEM, retention/DLP, model/vendor/legal approval, continuous live evaluation and cost monitoring, load/resilience/penetration testing, signed SBOM and CI/CD controls, network egress policy, operational SLOs, and external-message signing/transmission controls. The current application must continue using synthetic data only.

## 33. Exact run commands

```bash
make install
make migrate
make backend
make frontend
```

Then open `http://localhost:3000`; API/OpenAPI are at `http://localhost:8000/api/health` and `http://localhost:8000/docs`. Configure a backend-only `OPENROUTER_API_KEY` and a random server-side `AI_CACHE_HMAC_SECRET` of at least 32 characters in the ignored local environment to enable live AI and caching. Neither belongs in frontend variables.

Docker alternative:

```bash
docker compose up --build
```

## 34. Exact verification commands

```bash
make probe-live-ai
make test-live-ai
make evaluate-ai
make evaluate-platform
make lint
backend/.venv/bin/ruff format --check backend/app backend/tests backend/alembic
make typecheck
make test
make build
make e2e
make audit
make migrate
docker compose config --quiet
docker compose build
docker compose up -d
curl -fsS http://localhost:8000/api/health
curl -fsS http://localhost:8000/api/capabilities
docker compose down
git diff --check
```

The three live commands require runtime credentials and incur provider usage. They never print the key or prompt content.

## 35. Future roadmap

Priorities are approved event/market/client rule packs; dedicated strict penalty/corporate language schemas and live corpora; distributed Redis-compatible cache/lock adapter; PostgreSQL and tenant-aware keys; authentication/maker-checker/immutable audit; full licensed conformance tooling; expanded parser/Excel schemas; continuous model and cache-efficiency evaluation; additional Category 5 modules; then separately governed ISO 20022 equivalents.

## 36. Final status

Fully working and verified: existing MT540–MT548, 200-record Tag Intelligence and PSET drawer, exact privacy-safe cache and telemetry UI, settlement cancellation/amendment decisions, priority-only MT530, penalty-reporting MT537, voluntary-DVOP MT564–MT568 cash lifecycle, workflow registry/capabilities, workflow Excel/ZIP/reporting, local/live/security/migration/Docker tests, and documentation.

Partially working by explicit design: MT530, MT537, and MT564–MT568 are source-bounded subsets; the workflow registry reports them `PARTIALLY_IMPLEMENTED`. Expanded domain LLM interpretation and cost-savings baselines are not claimed. No destructive changes or secrets were introduced.

The platform is hackathon/demo ready for the documented synthetic flows. It is not ready or certified for production financial messaging.
# Successor status — client-usable source-bounded authoring

This expansion now has a secure encrypted draft, dynamic configured-row builder, sample catalogue,
maker-checker, external-evidence, and controlled connector foundation. All target capabilities
remain `PARTIAL`; see `CLIENT_USABLE_SWIFT_PLATFORM_REPORT.md` and
`MESSAGE_COVERAGE_REPORT.md` for current scope and evidence.
