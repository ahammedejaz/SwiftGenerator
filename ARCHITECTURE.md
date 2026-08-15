# Architecture

## Design goals

The MVP prioritises a reliable MT541 → MT548 → MT545 vertical slice, deterministic financial-message behavior, resilient AI-assisted interpretation, synthetic data, and testability. It deliberately avoids microservices, message buses, live Swift connectivity, authentication, and production infrastructure.

## Runtime flow

```text
Guided text -> length/control checks -> request-local sensitive placeholders
                 |
                 v
OpenRouter strict structured interpretation (or explicit non-AI form)
                 |
                 v
Strict schema + grounding + partial canonical patch/conflict check
                 |
       +---------+----------+
       |                    |
Message resolver     Missing-field engine
       |                    |
       +---------+----------+
                 v
Versioned client profile
                 |
                 v
Layered validation -> controlled negative mutation when explicitly selected
                 |
                 v
One of five deterministic composers
                 |
                 v
Raw demonstration message + field map + validation report
                 |
                 v
SQLite lifecycle store / Excel and ZIP report
```

The composer receives typed, prepared canonical data. It renders fixed sequence order and has no dependency on an LLM.

## Frontend

The Next.js App Router application contains:

- `/`: dashboard and disclaimer.
- `/guided`: deterministic phrase interpretation, friendly next question, normal form, profiles, negative MT541, and all three views.
- `/expert`: business form and generated field inspection.
- `/lifecycle`: create an MT541, generate all supported statuses or a full/partial MT545, and inspect the correlated timeline.
- `/bulk`: download template, upload, view per-row outcomes, and download the ZIP/report.
- `/reports/[reportId]`: execution metadata and download link.

Business rules stay in the Python backend. Frontend contracts are typed but are not treated as the security boundary.

## Backend

`app/domain` owns enums, canonical Pydantic models, resolution, deterministic missing fields, mutations, statuses, and validation. `app/profiles` loads immutable versioned YAML configuration. `app/composers` contains the five shared engines. `app/services` coordinates preparation, validation, composition, persistence, and response generation. `app/api` exposes stable camelCase JSON contracts and safe error envelopes.

## Agent architecture

`app/agents/providers/base.py` defines the async provider-neutral protocol. `providers/openrouter.py` is the only runtime model transport and uses pooled `httpx`, explicit timeouts, a provider-normalized and locally linted Pydantic JSON Schema, pinned models, bounded retries, and required provider privacy settings. `service.py` owns correction, escalation, budget, circuit, grounding, deterministic merge, and safe metadata. Prompts and schemas are versioned as `settlement-intent-v2` and `settlement-interpretation-v2`.

`fallback.py` remains an explicitly labelled deterministic non-AI resilience path and test utility. It is never silently presented as OpenRouter. `structured.py` remains for backward-compatible adapter tests but is not the runtime transport. In required/no-key mode, the API starts degraded for diagnostics and AI calls return a controlled 503; the normal form and message engine remain usable.

The model receives only the current sanitised turn plus minimal confirmed non-sensitive state. Accounts, references, ISINs, and party identifiers/names are replaced with typed request-local placeholders, rehydrated only after strict validation, and cleared afterward. Existing raw messages, profiles, reports, full canonical objects, and conversation history are not sent.

The model cannot return a message type, tags, raw message, validity, status/reason code, or arbitrary field. Deterministic services still own message type selection, mandatory fields, sequence order, final syntax, validation, and lifecycle correlation.

## Five composers

| Engine | Message types | Responsibility |
| --- | --- | --- |
| FOP instruction | MT540, MT542 | Receive/Deliver without cash leg. |
| DVP instruction | MT541, MT543 | Receive/Deliver with currency and amount. |
| FOP confirmation | MT544, MT546 | Full/partial settlement without cash leg. |
| DVP confirmation | MT545, MT547 | Full/partial settlement with settled cash. |
| Settlement status | MT548 | Controlled status/reason response for any supported instruction. |

Each returns raw text and a field map. All sequence boundaries and field positions are source-controlled code.

## Persistence and correlation

SQLAlchemy repositories isolate SQLite from service logic. `scenarios` store canonical JSON; `messages` store raw output and their parent message ID; `validation_results` store audit findings; `profiles` and `reports` support metadata. `ai_interpretation_audit` stores only request/model/prompt-schema version, attempts, latency, aggregate usage, escalation, and safe outcome—never prompt, output, key, reasoning, or placeholder maps. Lifecycle retrieval walks to the root instruction and lists responses in creation order. Alembic supplies additive migrations.

## OpenRouter control flow

Primary `openai/gpt-5.4-mini` handles normal requests. One schema-correction call is allowed. Low confidence, contradictory/complex intent, exhausted transient retries, or conflict with high-confidence local parsing can trigger one `openai/gpt-5.4` escalation. Authentication, credit, privacy-policy, budget, input, and open-circuit errors are not retried or escalated. Network retry uses bounded exponential backoff/jitter and honours capped `Retry-After`; the full operation has a deadline.

Every inference request sends `require_parameters=true`, `allow_fallbacks=true`, `data_collection=deny`, and `zdr=true` by safe default. It uses `max_completion_tokens` and intentionally omits endpoint-incompatible `temperature` and legacy `max_tokens`. Production settings validation rejects disabled parameter enforcement, data collection, or missing ZDR. Permanent request/schema/auth/credit/privacy failures do not affect the circuit; bounded transient infrastructure failures do. The process-local circuit breaker and daily counters reset with a process restart and are not distributed controls.

## Bulk and reporting

`openpyxl` validates the workbook and maps rows to the same canonical/service path used by REST. Valid rows continue if another row fails. A server-generated ZIP contains message text files, one JSON validation report per message, summary Excel, and an overall JSON execution report. Filenames are reduced to a safe allowlist and formula-like cells are escaped.

## Deployment

Two non-root containers are connected only through normal HTTP. The browser calls the published backend port. A named volume holds SQLite/report artifacts. Docker Compose performs the Alembic upgrade before API startup. This is development packaging, not a production topology.

## Expanded workflow architecture

The workflow registry enforces unique ownership and profile-aware capability discovery across Settlement, Settlement Command, Penalties, and Corporate Actions. Each module keeps typed canonical models, deterministic composers, validation/correlation, parser allowlists, profile enablement, and tag knowledge separate from provider code.

The Tag Intelligence loader validates YAML provenance, version, message signatures, field options, dependencies, overlays, and composer coverage at startup. Generic `workflow_messages` persistence stores MT537 and MT564–MT568 without changing settlement records.

Model-eligible flow remains local decision → sanitise/tokenise → exact HMAC cache → strict OpenRouter result → validate/rehydrate → deterministic engine. SQLite is persistent L2; bounded L1, circuit state, and single-flight are process-local.

## Secure source-bounded authoring architecture

`MessageSpecificationRegistry` compiles the 200 configured Tag Intelligence signatures into typed
sequence and field rows. It validates provenance, nesting, cardinality, tag options, conditions,
and ownership at startup, then supplies the Message Catalogue, dynamic form, generic composer,
parser allowlist, structural validator, annotated samples, and coverage report. Complex business
rules remain explicit code. Missing authorised rows cannot be inferred.

Encrypted drafts are tenant-scoped aggregates containing sequence instances and strongly typed
field instances. AES-GCM envelope encryption binds ciphertext to tenant/draft/field context.
Composition produces Block 4, line-level provenance, separated validation states, and a SHA-256
checksum. An immutable encrypted version is created before review. Approval is revision/checksum
specific and invalidated by any edit.

Development sessions, CSRF, tenant-aware repositories, RBAC, maker-checker, audit events, uploaded
external-validation evidence, and server-side connector policy form the operations boundary.
Production settings require PostgreSQL, OIDC/SAML mode, secure cookies, non-development connectors,
and managed secrets. Only the identity/connector interfaces are implemented until client contracts
exist; production submission remains disabled.
