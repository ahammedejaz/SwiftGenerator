# REST API

The FastAPI OpenAPI UI is available at `http://localhost:8000/docs`. JSON uses camelCase, unknown properties are rejected, and errors never contain stack traces.

## Error contract

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "The scenario contains blocking validation errors.",
    "details": [],
    "requestId": "generated-or-X-Request-ID"
  }
}
```

Typical status codes are 400 for invalid operations/resources supplied by name, 404 for missing stored resources/profiles, 413 for an oversized body, 422 for schema/domain validation, 429 for rate/budget limits, and 503 for controlled AI unavailability. Provider bodies and stack traces are never forwarded.

## Endpoints

| Method | Path | Purpose | Input/output and validation |
| --- | --- | --- | --- |
| GET | `/api/health` | Liveness and scope label. | No input; safe runtime metadata. |
| GET | `/api/profiles` | List profile summaries. | Includes versions and supported message types. |
| GET | `/api/profiles/{profileId}` | Get one profile rule view. | Defaults, requirements, currencies, mutations, validation limits; unknown ID returns 404. |
| GET | `/api/statuses` | List controlled status/reason combinations. | Safe configuration used by MT548. |
| GET | `/api/negative-tests?profileId=...` | List enabled mutations. | Profile allowlist. |
| GET | `/api/ai/health` | Read-only AI status without a model call. | Configured/mode/provider/pinned models/circuit/privacy/prompt/schema and aggregate content-free telemetry. Never returns a key. |
| POST | `/api/agent/interpret` | Real OpenRouter structured intent interpretation. | Text/profile plus optional current scenario/confirmed field paths → grounded partial patch, deterministic resolution, conflicts, clarification and safe AI metadata. Required/no-key returns 503. |
| POST | `/api/agent/interpret-deterministic` | Explicit non-AI resilience interpreter. | Existing text/profile request → partial scenario with `ai.used=false` and `provider=deterministic_non_ai`. Never silently selected. |
| POST | `/api/messages/resolve` | Resolve lifecycle/type. | Lifecycle, direction/payment or original instruction type → type/explanation/missing decisions. |
| POST | `/api/messages/missing-fields` | Calculate deterministic requirements. | Canonical scenario → missing list, friendly next question, completion, defaults. |
| POST | `/api/messages/validate-scenario` | Run canonical/business/profile validation. | Scenario → structured findings. |
| POST | `/api/messages/validate-raw` | Validate generated raw subset. | Raw text/profile → parsed supported fields and structural report. Never invokes AI. |
| POST | `/api/messages/generate` | Resolve, validate, compose, persist. | Scenario → type, raw, field map, profile version, report. Invalid valid-mode requests are blocked. |
| POST | `/api/messages/{instructionId}/responses` | Generate MT548 or paired confirmation. | Controlled action, reason/date/partial values, optional controlled mutation. |
| GET | `/api/messages/{messageId}` | Retrieve a persisted output. | Full generated message or 404. |
| GET | `/api/messages/{messageId}/lifecycle` | Retrieve root and correlated responses. | Timeline with validation/correlation. |
| GET | `/api/bulk/template` | Download `.xlsx` template. | Synthetic examples included. |
| POST | `/api/bulk/generate` | Generate workbook rows. | Multipart `.xlsx`; row continuation and ZIP report metadata. |
| GET | `/api/reports/{reportId}` | Download report ZIP. | Server-resolved path only. |
| GET | `/api/reports/{reportId}/metadata` | View bulk execution metadata. | Row summaries plus download path. |
| POST | `/api/demo/reset` | Clear and reseed demo messages. | Local development only without key; otherwise requires `X-Demo-Reset-Key`. |

## AI interpretation contract

The request accepts `text`, `profileId`, optional `currentScenario`, and optional `confirmedFields`. It deliberately has no model or API-key field. Unknown properties are rejected.

The response preserves the original scenario/resolution fields and adds `intent`, grounded `extractedFields`, `ambiguities`, `missingDecisions`, `conflicts`, `confidence`, `requiresClarification`, and safe `ai` metadata. The deterministic resolver—not the model—sets `resolution.resolvedMessageType` and `scenario.messageType`.

```json
{
  "ai": {
    "used": true,
    "provider": "openrouter",
    "model": "openai/gpt-5.4-mini",
    "primaryModel": "openai/gpt-5.4-mini",
    "escalated": false,
    "promptVersion": "settlement-intent-v2",
    "schemaVersion": "settlement-interpretation-v2",
    "requestId": "safe-internal-uuid",
    "latencyMs": 842,
    "attemptCount": 1,
    "outcomeCode": "SUCCESS"
  }
}
```

Stable safe AI errors include `AI_NOT_CONFIGURED`, `AI_AUTHENTICATION_FAILED`, `AI_PAYMENT_REQUIRED`, `AI_RATE_LIMITED`, `AI_TIMEOUT`, `AI_PROVIDER_UNAVAILABLE`, `AI_INVALID_REQUEST`, `AI_SCHEMA_REQUEST_INVALID`, `AI_UNSUPPORTED_MODEL_OR_PARAMETERS`, `AI_PRIVACY_REQUIREMENTS_UNAVAILABLE`, `AI_SCHEMA_VALIDATION_FAILED`, `AI_ESCALATION_FAILED`, `AI_BUDGET_EXCEEDED`, `AI_INPUT_TOO_LARGE`, `AI_CIRCUIT_OPEN`, `AI_RAW_CONTENT_NOT_ACCEPTED`, and `AI_UNSAFE_RESPONSE`.

Safe internal diagnostics retain the primary code, provider HTTP status/error type, permanent/transient classification, escalation occurrence and escalation code. Public errors never contain request content, provider bodies, keys, headers, prompts, responses, or placeholder mappings.

## Lifecycle request examples

Pending MT548:

```json
{
  "action": "PENDING_STATUS",
  "reasonCode": "AWAITING_CASH",
  "reasonNarrative": "SYNTHETIC PENDING STATUS"
}
```

Full MT545 from MT541:

```json
{
  "action": "FULL_CONFIRMATION",
  "actualSettlementDate": "2026-08-06"
}
```

Partial MT545:

```json
{
  "action": "PARTIAL_CONFIRMATION",
  "actualSettlementDate": "2026-08-06",
  "settledQuantity": "400",
  "settledAmount": "10000.00"
}
```

## Automation example

`scripts/samples/mt541-generate.json` is a complete synthetic generation request:

```bash
./scripts/api-demo.sh
```

The response supplies `resolvedMessageType`, `rawMessage`, `fieldMap`, `profileId`, `profileVersion`, and `validation` for test assertions.

## Expansion endpoints

- `GET /api/capabilities`
- `GET /api/knowledge/messages|tags|search|dependencies/*` and `POST /api/knowledge/explain`
- `POST /api/settlement/cancellations|amendment-decision|commands|cancel-rebook`
- `POST /api/penalties/generate|validate`
- `POST /api/corporate-actions/notifications|instructions|statuses|confirmations|narratives`
- `GET /api/workflows/{workflowId}/lifecycle`
- `GET /api/workflows/messages/{messageId}/report`
- `GET /api/bulk/workflow-template` and `POST /api/bulk/workflow-generate`
- `GET /api/ai/usage/last-interaction|last-provider-call|summary`
- `GET /api/ai/cache/stats` and `POST /api/ai/cache/diagnose`

Safe contracts never expose keys, cache IDs, prompts, cached payloads, provider bodies, or placeholder maps.

## Secure authoring and operations APIs

All mutations below require a server-side session, tenant context, role check, and CSRF token.

- Authentication: `POST /api/auth/development-login`, `GET /api/auth/session`, `POST /api/auth/logout`.
  Development login is disabled outside explicit development mode.
- Specifications: `GET /api/specifications/messages`, `/{messageType}`, `/{messageType}/coverage`,
  `/api/specifications/coverage`, and `/api/specifications/event-profiles`.
- Samples: `GET /api/knowledge/samples`, `/{sampleId}`, and
  `POST /api/knowledge/samples/{sampleId}/load`.
- Drafts: `POST /api/messages/drafts`, `GET|PATCH /api/messages/drafts/{draftId}`,
  add/delete `/fields`, and add/delete `/sequences`.
- Authoring: `POST /api/messages/{draftId}/compose|validate|review|approve|submit`.
- Downloads: `GET /api/messages/{draftId}/downloads` and `/{format}` for artifacts that require no
  sensitive envelope input. FIN/RJE values use CSRF-protected
  `POST /api/messages/{draftId}/exports/{format}` JSON bodies so sender/receiver identifiers never
  enter URL/access logs. Supported formats are Block 4, FIN, text, canonical JSON, validation
  JSON/HTML, and evidence ZIP. RJE fails closed without an approved contract.
- Import: `POST /api/messages/import` parses the supported subset, returns unknown lines separately,
  and reports round-trip equivalence.
- Operations: `GET /api/messages/{draftId}/audit|submissions`, `GET /api/connectors`, connector
  health/test, and uploaded validation evidence at `/api/external-validation/results/{draftId}`.

Errors use the existing safe error envelope and never return stack traces, ciphertext, connector
configuration, or tenant existence. Catalogue-only messages are visible but rejected for drafts.
