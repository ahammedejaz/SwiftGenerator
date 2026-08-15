# Intelligent SWIFT Message Engineering Platform

This repository provides source-bounded authoring, deterministic composition, validation,
download, review, approval, and controlled submission foundations for configured ISO 15022
Category 5 subsets. It supports MT530, MT537, MT540–MT548, and MT564–MT568 as `PARTIAL`
capabilities. Users can enter actual business values through the secure dynamic builder; the
system never silently inserts synthetic defaults. Synthetic data is loaded only through an
explicit sample action.

The platform does **not** claim SWIFT certification, complete ISO 15022 conformance, acceptance
by every market or custodian, or live SWIFT connectivity. Authoritative release specifications,
institution-approved profiles, external validation, production identity, and a contracted
connector are required before production use. See [MESSAGE_COVERAGE_REPORT.md](MESSAGE_COVERAGE_REPORT.md).

## Authoritative architecture

```text
User-entered or imported data
→ tenant-isolated encrypted draft
→ machine-readable configured specification
→ effective client/event profile
→ deterministic composer
→ separated validation levels
→ immutable revision and checksum
→ maker-checker approval
→ allowlisted server-side connector
```

The LLM is optional and limited to tokenised intent interpretation or explanation. It never
selects sequence/tag order, qualifies fields, validates a transaction, composes FIN, approves,
or submits a message. Normal forms, Tag Intelligence, samples, composition, validation, and
submission do not call the LLM.

## Configured capabilities

- Settlement: MT540–MT543 instructions, MT544–MT547 confirmations, MT548 statuses and the
  verified configured MT541 → MT548 → MT545 lifecycle.
- Processing: a source-bounded MT530 processing-command subset; core business changes remain
  cancel-and-rebook decisions.
- Statements/penalties: an MT537 nested penalty-reporting subset. Amounts are entered by users;
  no unapproved penalty calculation is performed.
- Corporate actions: MT564–MT568 with the configured DVOP event profile. Other listed event
  types are catalogue-only until authorised profiles are imported.
- Knowledge: 200 Tag Intelligence records, exact configured-row search, provenance, dependencies,
  and composer-driven annotated samples for all 16 target messages.
- Authoring: optional configured fields, repeatable configured sequences, explicit field source,
  round-trip import, Block 4/FIN/JSON/HTML/ZIP downloads, and profile-aware validation.
- Operations: development authentication, tenant isolation, RBAC, CSRF, encryption, immutable
  revisions, review/approval, uploaded external evidence, and mock-UAT submission testing.

All 16 generation capabilities remain `PARTIAL`; MT535, MT536, MT538, and MT578 are
`CATALOGUE_ONLY` and cannot be generated.

## Local setup

Prerequisites: Python 3.13, Node.js 22, npm, and optionally Docker Desktop.

```bash
cp .env.example .env
make install
```

Secure authoring is disabled by default. For local development, generate server-side test secrets
without committing them, then set `REAL_DATA_MODE_ENABLED=true`, `AUTH_MODE=development`,
`SESSION_HMAC_SECRET`, and a base64-encoded 32-byte `DATA_ENCRYPTION_KEY` in the ignored `.env`.
Run migrations and start both processes:

```bash
make migrate
make backend
```

```bash
make frontend
```

Open `http://localhost:3000`; API documentation is at `http://localhost:8000/docs`.
Development identities are explicitly labelled and are never permitted when `APP_ENV=production`.

## Docker

Development:

```bash
docker compose up --build
```

Production configuration uses PostgreSQL and fail-closed settings:

```bash
docker compose -f docker-compose.yml -f docker-compose.production.yml config
docker compose -f docker-compose.yml -f docker-compose.production.yml up --build
```

Supply production secrets from a secret manager. The production overlay deliberately fails when
required secret variables are absent. It does not provide an OIDC/SAML implementation or a live
message connector.

## AI configuration

OpenRouter defaults are pinned to `openai/gpt-5.4-mini` with bounded escalation to
`openai/gpt-5.4`. Structured JSON Schema, parameter enforcement, data-collection denial, ZDR,
sensitive placeholder tokenisation, exact HMAC caching, circuit breaking, and content-free
telemetry remain enabled. Put `OPENROUTER_API_KEY` only in server-side secret configuration.
Set `AI_PROVIDER=disabled` to retain all deterministic features without AI.

## Verification

```bash
make coverage
make lint
make typecheck
make test
make build
make e2e
make audit
make probe-live-ai
make evaluate-ai
make evaluate-platform
make test-live-ai
git diff --check
```

Live AI commands execute only when a runtime key is present and never print prompts or secrets.
See [TESTING.md](TESTING.md) for evidence and [CLIENT_USABLE_SWIFT_PLATFORM_REPORT.md](CLIENT_USABLE_SWIFT_PLATFORM_REPORT.md)
for the final status.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [DOMAIN_MODEL.md](DOMAIN_MODEL.md)
- [API.md](API.md)
- [MESSAGE_BUILDER_GUIDE.md](MESSAGE_BUILDER_GUIDE.md)
- [TAG_INTELLIGENCE_GUIDE.md](TAG_INTELLIGENCE_GUIDE.md)
- [SAMPLE_MESSAGES_GUIDE.md](SAMPLE_MESSAGES_GUIDE.md)
- [FIN_EXPORT_GUIDE.md](FIN_EXPORT_GUIDE.md)
- [AUTH_AND_RBAC_GUIDE.md](AUTH_AND_RBAC_GUIDE.md)
- [DATA_PROTECTION_GUIDE.md](DATA_PROTECTION_GUIDE.md)
- [CONNECTOR_INTEGRATION_GUIDE.md](CONNECTOR_INTEGRATION_GUIDE.md)
- [SUBMISSION_OPERATIONS_GUIDE.md](SUBMISSION_OPERATIONS_GUIDE.md)
- [PENALTIES_GUIDE.md](PENALTIES_GUIDE.md)
- [CORPORATE_ACTIONS_GUIDE.md](CORPORATE_ACTIONS_GUIDE.md)
- [MT530_GUIDE.md](MT530_GUIDE.md)
- [LIMITATIONS.md](LIMITATIONS.md)
