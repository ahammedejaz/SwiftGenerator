# Securities Settlement Message Studio Implementation Report

> OpenRouter integration addendum: the original deterministic MVP described here has since been extended through the provider-neutral agent boundary. See `OPENROUTER_LLM_INTEGRATION_REPORT.md` for the final AI architecture, exact current evidence, security controls, configuration, and live-provider status. Deterministic composers and lifecycle behavior described in this report remain authoritative.

Report date: 2026-08-04

Repository: `SwiftGenerator`

Status: hackathon demo ready through local Python/Node and verified Docker runtime. The original MVP evidence below is historical; `OPENROUTER_LLM_INTEGRATION_REPORT.md` is authoritative for current AI, dependency, test, and container evidence.

## 1. Executive Summary

The repository now contains a complete synthetic Securities Settlement Message Studio MVP. It guides a beginner from plain business language into a canonical settlement scenario, determines missing information, resolves MT540–MT548 types from deterministic tables, applies a versioned client profile, composes a controlled raw demonstration message, validates it, persists lifecycle relationships, and produces audit-oriented reports.

The minimum approved lifecycle works end to end through REST and the browser: MT541 Receive Against Payment instruction → MT548 status → MT545 full or partial confirmation. Shared engines also cover MT540–MT547 and all configured MT548 statuses. Excel bulk processing continues after row failures and exports raw messages, validation JSON, summary Excel, and an overall execution report.

The MVP is ready for the documented hackathon presentation using local Python/Node commands. It is not production ready, is not a complete ISO 15022 implementation, does not connect to the Swift network, and makes no certification claim.

## 2. Approved Scope

### Implemented

- Strongly typed canonical settlement model and controlled enums.
- Deterministic instruction/confirmation/status resolution.
- Versioned Base Demo and BFS Client Demo profiles with visible behavior differences.
- Deterministic missing-information engine and beginner questions.
- Five reusable deterministic composers spanning MT540–MT548.
- Five validation layers and audit findings.
- Valid and explicit controlled-negative generation modes with ten mutations.
- MT541 → MT548 → MT545 persistence, generation, and correlation; full/partial confirmation.
- Six controlled status categories and configured reason combinations.
- Guided, expert, lifecycle, bulk, report, business, tag, and raw-subset screens.
- Supported-subset raw editing and validation without AI invocation.
- Excel template, row continuation, ZIP artifacts, report metadata, and safe filenames/cells.
- OpenAPI REST endpoints, consistent error envelope, real-server sample scripts, reset mechanism.
- SQLite repositories and Alembic initial migration.
- Provider-neutral strict structured-intent adapter boundary plus deterministic offline interpreter.
- Request/upload limits, rate limiting, content/security headers, logging redaction, safe reset control, and non-root containers.
- Complete required documentation and synthetic fixtures.

### Deferred or deliberately excluded

- Any live Swift connectivity, official certification, complete standards validation, or institution rule pack.
- Institution-approved continuous model evaluation and production AI governance. The OpenRouter transport itself is now implemented and live-verified as documented in the integration report.
- Historical-message learning, RAG, similarity search, clustering, or production-message ingestion.
- Universal raw ISO 15022 parsing or complete canonical round trip from arbitrary raw text.
- Monaco Editor; the hackathon UI uses an accessible monospace textarea.
- Authentication, RBAC, SSO, PostgreSQL, immutable audit storage, managed object storage, microservices, Kafka, Kubernetes, and production observability.

No approved scope was removed. When a parallel browser run exposed a development-server first-compilation timing flake, Playwright was set to one worker so the shared demo database and development servers are exercised reliably. Product behavior was unchanged.

## 3. Architecture

### Frontend architecture

Next.js 16 App Router, React 19, TypeScript, Tailwind CSS, and client components for interactive flows. Screens call the documented FastAPI boundary through one typed API client. Domain rules do not live in UI components.

### Backend architecture

FastAPI exposes camelCase Pydantic contracts. Domain modules own enums/resolution/requirements/mutations/statuses/validation; services orchestrate preparation and lifecycle operations; composers render; repositories persist; bulk/report services reuse the same generation path. Global exceptions become safe envelopes without traces.

### Agent architecture

The current runtime uses a provider-neutral async boundary with an isolated OpenRouter transport, strict normalized JSON Schema, sensitive-value placeholders, bounded retry/escalation, safe circuit/budget controls, and explicit deterministic non-AI degradation. Prompt instructions remain separate from business logic. See the integration report for the exact v2 prompt/schema, live evaluation, and privacy controls.

The AI boundary cannot select authoritative syntax, order sequences, bypass required fields, invent values, or transmit a message. All such decisions remain deterministic downstream.

### Canonical model

`SettlementScenario` owns business meaning independent of tags: profile/lifecycle/direction/payment/type/function/references, trade, security, account, settlement, confirmation, status, test configuration, and a synthetic-data marker. Dates and decimals are typed; controlled concepts are enums; extra properties are rejected.

### Composer architecture

| Composer | Coverage |
| --- | --- |
| `FopInstructionComposer` | MT540, MT542 |
| `DvpInstructionComposer` | MT541, MT543 |
| `FopConfirmationComposer` | MT544, MT546 |
| `DvpConfirmationComposer` | MT545, MT547 |
| `SettlementStatusComposer` | MT548 |

Each composer accepts prepared canonical data/profile, emits fields in fixed order, returns raw text plus a field map, and has no model-provider dependency.

### Validation architecture

Canonical/schema checks are followed by message/business checks, client-profile checks, raw structure checks, and lifecycle correlation. Positive errors block output. Negative mode first validates the positive baseline, applies exactly one enabled mutation, demands the expected rule, rejects unexpected errors, marks intentional findings, and displays the required notice.

### Client-profile architecture

Strict YAML files are loaded once by a typed repository. Base V1 allows optional client reference, GBP, and 16-character sender references with no PSET default. BFS Client Demo V1 requires client reference for MT540–MT547, defaults a synthetic PSET, allows USD/EUR, and limits references to 12. Generated reports record profile/version.

### Excel architecture

`openpyxl` creates the template, validates exact mandatory headers, parses each row into the canonical/service flow, and continues after errors. Response rows reference prior instruction rows. The ZIP contains `.txt`, `.validation.json`, `summary.xlsx`, and `execution-report.json`. Upload paths, types, size, OOXML structure, row count, output names, and formula-leading cells are controlled.

### Reporting architecture

Reports are stored under a configured server directory and retrieved only by repository-known UUID. Metadata drives the reports screen. SQLite stores canonical scenarios, messages, relationships, validation findings, and report payload/path metadata.

## 4. Message Coverage

| Message | Implemented | Supported scenarios and fields | Validation and limitations |
| --- | --- | --- | --- |
| MT540 | Yes | Receive Free instruction; reference/function, trade/settlement dates, ISIN, unit quantity, transaction, safe account, synthetic PSET/agents. | Resolver/business/profile/golden/raw checks; no cash leg; controlled subset only. |
| MT541 | Yes | Receive Against Payment instruction; MT540 fields plus currency/amount. | Complete guided golden path, missing amount negative, profile switching, API/UI/Excel coverage. |
| MT542 | Yes | Deliver Free instruction with the FOP shared engine. | Direction/type correlation and no-cash rule; controlled subset only. |
| MT543 | Yes | Deliver Against Payment instruction with the DVP shared engine. | Currency/amount required, resolver/golden/API coverage. |
| MT544 | Yes | MT540 full/partial Receive Free confirmation; original reference, actual date, identifier, settled units/result, safe/PSET/agents. | Type/security/direction/payment/quantity correlation; no cash leg. |
| MT545 | Yes | MT541 full/partial Receive Against Payment confirmation including settled cash. | Minimum lifecycle UI/API/golden coverage; over-quantity controlled negative. |
| MT546 | Yes | MT542 full/partial Deliver Free confirmation. | Same correlation layers through FOP confirmation engine. |
| MT547 | Yes | MT543 full/partial Deliver Against Payment confirmation. | Same correlation layers through DVP confirmation engine. |
| MT548 | Yes | References any supported instruction; Pending, Rejected, Matched, Unmatched, Cancellation Accepted/Rejected with controlled reasons/narrative. | Related type/reference and status/reason validation; not a complete processing-advice vocabulary. |

Golden files exist for every MT540–MT548 type and fail on unexpected text changes.

## 5. File Changes

The repository was empty at approved implementation start. Git was initialised, so all implementation files are created files; no pre-existing user file was modified and no file was deleted.

### Root and operations

- `.env.example`: non-secret environment contract.
- `.gitignore`: secrets, virtual environments, builds, databases, reports, and test artifacts.
- `Makefile`: install/migrate/run/lint/type/test/build/e2e/reset commands.
- `docker-compose.yml`: backend/frontend and named demo-data volume.
- `scripts/start-dev.sh`, `reset-demo.sh`, `api-demo.sh`: repeatable local/demo operations.
- `scripts/samples/mt541-generate.json`: synthetic automation sample.
- `README.md` and the ten focused design/operations documents: setup and reviewer guidance.
- This report: evidence, coverage, limitations, and final status.

### Backend application

- `backend/app/domain/*`: enums, canonical/API models, resolution tables, deterministic missing fields, status registry, negative mutations, five-layer validation.
- `backend/app/composers/*`: base contract/decimal formatter and five deterministic engines.
- `backend/app/services/generation.py`, `lifecycle.py`: positive/negative generation and response orchestration.
- `backend/app/agents/fallback.py`, `prompts.py`, `structured.py`: offline interpreter and safe optional-adapter boundary.
- `backend/app/raw/validator.py`: MT540–MT548 generated-subset parser/validator.
- `backend/app/profiles/loader.py` and `backend/config/profiles/*.yaml`: strict versioned profiles.
- `backend/config/statuses.yaml`: controlled demo statuses/reasons.
- `backend/app/api/routes.py`, `errors.py`, `main.py`: REST endpoints, error contracts, middleware, OpenAPI.
- `backend/app/persistence/*`: SQLAlchemy models/repositories/database/report storage.
- `backend/app/bulk/service.py`: template/import/row results/ZIP report.
- `backend/app/demo/service.py`: repeatable synthetic seed/reset.
- `backend/alembic*`: migration runtime and initial schema.
- `backend/requirements*.txt`, `pyproject.toml`: pinned runtime/dev dependencies and quality settings.
- `backend/Dockerfile`, `.dockerignore`: non-root backend image.

### Backend tests

- `backend/tests/unit/*`: resolver, profiles, requirements, validation, interpreter, structured adapter, raw parser, security.
- `backend/tests/api/*`: generation/errors, all families, lifecycle, negative mode, bulk/upload, raw, security, reset.
- `backend/tests/golden/*`: canonical scenarios and approved MT540–MT548 outputs.

### Frontend

- `frontend/app/*`: dashboard and Guided, Expert, Lifecycle, Bulk, and Report routes/layout/styles.
- `frontend/components/*`: guided form, expert builder, message views/raw editor, lifecycle timeline/actions, bulk results, report viewer.
- `frontend/lib/*`: typed contracts and safe API client.
- `frontend/tests/e2e/*`, `playwright.config.ts`: five critical smoke flows with isolated sequential execution.
- `frontend/package*.json`, TypeScript/ESLint/PostCSS/Next configuration: reproducible modern frontend toolchain.
- `frontend/Dockerfile`, `.dockerignore`: standalone non-root frontend image.
- `frontend/AGENTS.md`, `CLAUDE.md`: repository-local framework/agent guidance generated during setup.

## 6. API Summary

| Method and path | Purpose | Input | Output / validation behavior |
| --- | --- | --- | --- |
| GET `/api/health` | Liveness/scope | None | Status, application, environment, demo scope. |
| GET `/api/profiles` | Profile list | None | ID/version/release/status/types. |
| GET `/api/profiles/{profileId}` | Profile detail | Path ID | Defaults, currency/rule/requirement/mutation view; 404 if unknown. |
| GET `/api/statuses` | Controlled MT548 data | None | Categories, codes, reasons. |
| GET `/api/negative-tests` | Mutation allowlist | `profileId` query | Enabled enum list. |
| POST `/api/agent/interpret` | Offline intent | Text/profile | Partial canonical scenario, resolution/explanation/detected fields. |
| POST `/api/messages/resolve` | Message selection | Lifecycle and decision data | Type/confidence/explanation/missing decisions. |
| POST `/api/messages/missing-fields` | Next question | Scenario | Defaults, type, complete deterministic missing list, completion. |
| POST `/api/messages/validate-scenario` | Validate business object | Scenario | Structured report; does not compose. |
| POST `/api/messages/validate-raw` | Validate raw subset | Raw/profile | Type, parsed fields, structural/profile report; no AI call. |
| POST `/api/messages/generate` | Compose/persist | Scenario | Type, raw, field map, profile/version, validation; positive errors return 422. |
| POST `/api/messages/{instructionId}/responses` | Status/confirmation | Controlled action and applicable reason/date/partial/mutation values | Correlated MT548 or paired MT544–547. |
| GET `/api/messages/{messageId}` | Retrieve | Message UUID | Persisted generated object; 404 if absent. |
| GET `/api/messages/{messageId}/lifecycle` | Timeline | Any lifecycle message ID | Root, ordered entries, correlation report. |
| GET `/api/bulk/template` | Template | None | `.xlsx` attachment. |
| POST `/api/bulk/generate` | Workbook generation | Multipart `.xlsx` | Per-row results, report UUID/path; structure/type/size/path checks. |
| GET `/api/reports/{reportId}` | ZIP | Report UUID | Server-controlled ZIP attachment. |
| GET `/api/reports/{reportId}/metadata` | Report screen data | Report UUID | Execution summary/rows/download path. |
| POST `/api/demo/reset` | Repeatable seed | Optional reset header | Removed/seeded counts and lifecycle root; local/key controls. |

Schema errors return 422 without echoing full input. Domain errors include structured findings. All responses receive a request ID; no stack trace is exposed.

## 7. User Flows

### Beginner generation

The supplied purchase phrase resolves to MT541 with an explanation and a business-confirmation prompt for inferred Receive. The deterministic missing engine returns one friendly next question and all missing paths. Synthetic demo answers complete the form; generation displays validation plus business/tag/raw views.

### Expert generation

The expert screen exposes editable supported business values and generated fields by sequence. Business and tag views provide mappings; the raw textarea can be edited, restored, and revalidated against the emitted subset.

### Client-profile switching

Switching to BFS exposes required Client Reference. Backend missing-field/profile validation also applies the PSET default, 12-character sender limit, and USD/EUR currency set; it is not merely a visual change.

### Confirmation and MT548 generation

Lifecycle actions start from the persisted instruction. MT548 actions require configured reasons; full/partial confirmation automatically reuses instruction data and applies the paired type. The timeline shows IDs/types/references/business status/profile/version/validation/correlation.

### Negative testing

Valid baseline data is required, then one controlled mutation is selected. The guided demo removes MT541 amount and emits an intentionally invalid raw message only when the expected amount-required finding appears. Lifecycle mutations cover quantity/type/reference/status-reason failures.

### Excel generation

The UI downloads a synthetic template, uploads an `.xlsx`, shows row results, continues after the invalid example, opens report metadata, and downloads the complete ZIP. The tested template produces 3 generated and 1 failed row.

### Automation API

Swagger provides interactive contracts and `scripts/api-demo.sh` posts a complete synthetic MT541. Callers receive deterministic raw output, structured fields, profile/version, and findings suitable for assertions.

## 8. Validation Coverage

### Canonical rules

Strict schema/enums/extra rejection; required paths; date/decimal parsing; positive amount/quantity; ISIN subset format; sender length and uppercase/alphanumeric format.

### Message rules

Resolver/type consistency; FOP cash exclusion; DVP currency/amount requirements; trade/settlement chronology; function/previous reference; confirmation lifecycle; fixed deterministic message structures.

### Client rules

Supported types, required/client-required paths, defaults, allowed currencies, sender formatting, enabled mutations, and applied profile/version reporting.

### Correlation rules

Existing original instruction, related reference, paired confirmation type, security/direction/payment match, confirmation quantity bound, MT548 related instruction type, and status/reason combination.

### Raw structure rules

Demonstration/application blocks, supported MT header, non-nested matching sequence boundaries, type-specific sequence order, field position, repetition, tag/qualifier allowlist, control-character rejection, and profile message allowlist.

### Negative-test rules

All ten approved mutations are implemented. Expected findings become intentional; absence of the expected rule or any unrelated error blocks output.

### Unsupported validation

Complete ISO 15022 syntax/semantic/network validation, FIN header authentication, standards-release delta packs, market/client practices beyond demo YAML, external reference validation, checksum/signature, and institution conformance are not implemented.

## 9. Testing Results

### Original MVP commands and evidence

This table records the pre-OpenRouter baseline. It is retained for traceability, not presented as current final evidence. The integration report records the final 156-test, live-provider, dependency-audit, Playwright, migration, Docker-build, and runtime results.

| Check | Command | Result |
| --- | --- | --- |
| Backend lint | `cd backend && .venv/bin/ruff check app tests` | Passed, no findings. |
| Backend type check | `cd backend && .venv/bin/mypy app` | Passed, 46 source files, no issues. |
| Backend unit/API/golden/security | `cd backend && .venv/bin/pytest` | 70 passed, 0 failed, 0.29s. |
| Frontend lint | `cd frontend && npm run lint` | Passed. |
| Frontend type check | `cd frontend && npm run typecheck` | Passed. |
| Production build | `cd frontend && npm run build` | Passed; 7 routes generated/compiled. |
| UI smoke | `cd frontend && npm run test:e2e` | 5 passed, 0 failed, 10.2s, Chromium. |
| Dependency audit | `cd frontend && npm audit` | 0 vulnerabilities reported. |
| Clean migration | `DATABASE_URL=sqlite:////tmp/securities-studio-clean-20260804-final.db .venv/bin/alembic upgrade head` | Initial revision applied successfully. |
| Compose syntax | `docker compose config` | Passed. |
| Container image build | `docker compose build` | Not executed to completion: local Docker daemon unavailable at its Unix socket. |
| Diff whitespace | `git diff --check` | Passed after EOF formatting cleanup. |
| Secret pattern scan | repository `rg -l` scan for common private key/AWS/OpenAI-key forms | No matches. |

An initial parallel Playwright run recorded 4 passed/1 timeout while Next compiled the report route under three workers. The bulk test passed immediately in isolation. Worker count was then fixed at one to isolate the shared demo server/database; the final complete run passed 5/5. This resolved a harness timing issue, not a skipped product assertion.

### API and demo smoke evidence

A real Uvicorn process was started and logged only successful requests for the smoke path:

- Health returned `status: ok` and demonstration scope.
- `./scripts/reset-demo.sh` returned 15 removed, 15 seeded on repeat, and a root lifecycle ID.
- `./scripts/api-demo.sh` returned a valid MT541, profile `BASE_DEMO_V1` version `1.0.0`, zero errors, fixed field map, and demonstration disclaimer.
- Rejected response returned valid MT548 with `REJT`/`INVALID_REFERENCE` and the original MT541 link.
- Full response returned valid MT545 with matching reference/security/payment/direction and settled quantity/amount.
- Lifecycle retrieval returned `correlationValid: true`.
- Observed backend smoke logs contained HTTP 200 responses and no errors/tracebacks. Uvicorn shut down cleanly.

### Browser smoke coverage

Guided resolution/questions/MT541/all views/raw validation; BFS profile/negative notice; expert three views; MT541 → MT548 → MT545 correlated lifecycle; Excel template/upload/3-valid-1-failed/report/ZIP download.

## 10. Security Review

- Secrets: `.env` ignored; deterministic mode requires no key; the live key is backend-only and was never printed; the final credential/private-key scan had no match outside ignored `.env`.
- Logging: full payloads are not logged; defensive account/credential redaction is tested.
- Uploads: content type, extension, basename, size, OOXML ZIP, row count, safe output naming, and spreadsheet formula escaping.
- Prompt injection: user text is sanitized untrusted model data; raw MT remains local to deterministic parsing; strict schema/no-tools/local reconciliation tests preserve the authority boundary.
- Input validation: strict schemas/enums, request size, controlled configuration, no arbitrary code/template execution.
- Network: no Swift or outbound message integration.
- HTTP: safe error envelope, request ID, CORS allowlist, credentials disabled, security headers, configurable in-memory rate limit.
- Containers: non-root users and minimal runtime stages.

Known limitations are no authentication/authorization/tenant isolation, no encryption or immutable audit policy, local SQLite/files, process-local rate/circuit/budget controls, no production secret manager, no SBOM/image-signing pipeline, no penetration test, and a verification Docker daemon that reported a non-default seccomp profile.

## 11. Performance and Reliability

Bulk generation is synchronous and bounded at 1,000 rows/5 MiB by default. Rows are isolated logically so one validation error does not abort valid rows. Errors use stable contracts. SQLite and local reports are adequate for one hackathon process, not concurrent production throughput.

The deterministic path has no external retry/failure dependency. The optional structured adapter retries malformed schema output once and then fails closed; it has no configured provider. UI forms and APIs remain fully usable when AI is disabled or unavailable.

Repositories keep a future PostgreSQL migration possible, but distributed locking/rate limiting/background jobs were correctly deferred. Golden outputs make composer regressions visible.

## 12. Setup and Demonstration

### Install and configure

```bash
cp .env.example .env
make install
make migrate
```

### Start

Terminal 1:

```bash
make backend
```

Terminal 2:

```bash
make frontend
```

Or:

```bash
./scripts/start-dev.sh
```

### Run tests

```bash
make lint
make typecheck
make test
make build
make e2e
cd frontend && npm audit
```

### Load/reset and present

```bash
make reset-demo
```

Open `http://localhost:3000/guided` and follow `DEMO_GUIDE.md`. Open Swagger at `http://localhost:8000/docs`; `./scripts/api-demo.sh` verifies the curl workflow.

### Docker alternative

After starting Docker Desktop:

```bash
docker compose up --build
```

This is the only setup path not executed in the current verification environment because its daemon was not running.

## 13. Known Limitations

- Supported ISO 15022-style field subset only; raw parser is generated-subset only.
- No live Swift connection, network certification, ACK/NAK, signing, or official rule validation.
- Demonstration profiles/statuses and synthetic data only.
- No authentication, maker/checker, RBAC, SSO, tenant isolation, or production audit controls.
- SQLite/local synchronous processing and report files.
- No configured external AI transport; deterministic interpreter vocabulary is finite.
- No Monaco; accessible textarea instead.
- Partial and basic function coverage, not every optional/repeating field/sequence or lifecycle variation.
- Container definitions validate syntactically, but images were not built/run in this environment.

## 14. Recommended Next Phases

1. Obtain authorised standards documentation and institution-approved rule packs; expand fields and formal conformance fixtures.
2. Add authentication, RBAC/maker-checker, SSO, tenant boundaries, immutable audit, data classification/retention, and managed secrets.
3. Move to PostgreSQL and encrypted object storage; add background bulk jobs, distributed rate limiting, operational telemetry, backup/restore, and disaster-recovery tests.
4. Add signed/SBOM-scanned CI images, SAST/dependency/container policies, penetration testing, and deployment hardening.
5. Connect an approved structured-output provider only after model risk/privacy review; keep deterministic authority and offline fallback.
6. Expand raw round-trip parsing, Category 5 coverage, institution/market rule packs, and ISO 20022 securities-message support.
7. Add broader accessibility, cross-browser, performance, visual regression, and high-volume reliability suites.

## 15. Final Status

Fully working and executed locally: deterministic MT540–MT548 generation, MT541 → MT548 → MT545 lifecycle, full/partial confirmations, profile switching, missing questions, valid/negative modes, business/tag/raw views, raw subset validation, REST persistence/correlation, Excel/ZIP/reporting, reset, migration, and all automated local checks listed above.

Partially working by deliberate design: AI integration has a strict provider-neutral adapter boundary but no external transport; raw parsing validates only generated fields; standards coverage is a documented subset.

Not completed: production controls/infrastructure, official or institution validation, network connectivity, universal parser, and container runtime execution in this environment.

Hackathon demo readiness: **ready through the verified local Python/Node setup**. Before presenting with Docker, start Docker Desktop and execute `docker compose up --build`. Before any production consideration, every security, governance, standards, infrastructure, and operational gap in this report must be addressed; the generated messages must be validated against authorised documentation and institution-approved implementation rules.
