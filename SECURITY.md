# Security review

## Implemented controls

- No live Swift/network transmission integration and no arbitrary outbound message action.
- Strict Pydantic request models with extra fields rejected and enum allowlists.
- Final syntax comes only from deterministic composers; no `eval`, dynamic templates, arbitrary code, or user-provided template execution.
- Raw content is parsed as inert data and rejected from the model boundary with `AI_RAW_CONTENT_NOT_ACCEPTED`. Prompt-injection-like narrative is untrusted delimited data with automated XML/JSON/Markdown/repetition/control-character regressions.
- OpenRouter credentials are backend-only `SecretStr` configuration. `.env` is ignored; `.env.example` is empty. No key is accepted by an API or exposed through `NEXT_PUBLIC_*`, health, error, audit, or telemetry contracts.
- Every provider call requires compatible structured-output parameters, denies data collection, and requires ZDR. Those controls are production-enforced and are never weakened during retry/escalation.
- The production schema is normalized and linted before transmission: no root union, every object property required, nullable optionals, recursive `additionalProperties:false`, no defaults/arbitrary maps, resolved local references, controlled enums, and no raw-message/tag/sequence fields.
- User content is length checked and sensitive ISIN/account/reference/party/BIC/name values are replaced with typed request-local placeholders. Only issued placeholders rehydrate after grounding/schema validation; mappings are cleared and never logged/stored.
- Payload logging is absent. Safe telemetry/audit contains only IDs, versions, models, attempt/latency/usage counts, escalation, and outcome. A defensive filter masks accounts, credentials/Bearer values, and whole raw-message-like log text.
- Spreadsheet upload enforces content type at the API, `.xlsx` extension, basename-only filename, byte limit, OOXML ZIP validity, and row limit.
- Generated ZIP names use an allowlist. Report retrieval uses repository-known UUIDs, preventing caller-selected filesystem paths.
- Spreadsheet output escapes formula-leading cells.
- API body size and per-client in-memory rate limits are configurable.
- Safe error envelopes include a request ID and omit stack traces/internal exception details from schema failures.
- CORS permits only the configured frontend; credentials are disabled. API responses set nosniff, deny framing, no-referrer, and a restrictive content security policy.
- Containers run as unprivileged users. Demo reset is local-development-only without a key and uses constant-time key comparison when configured.
- Only synthetic fixtures/values are committed.

## Secret handling

Never add a real key to `.env.example`, YAML profiles, tests, samples, Dockerfiles, frontend variables, logs, or Git history. `NEXT_PUBLIC_*` values are public by design. Set `OPENROUTER_API_KEY` only in an ignored local environment for development or a managed deployment secret store.

### Rotation and exposure response

1. Revoke/rotate the key in OpenRouter immediately; do not wait for an application deployment.
2. Replace the deployment secret and restart backend processes so pooled clients use the new credential.
3. Review content-free request counts/outcomes and provider usage without copying prompts/responses.
4. If a key entered Git or frontend assets, treat it as exposed even after deletion: revoke it, scan history/build artifacts/logs, and follow the organisation incident process.
5. Temporarily set `AI_PROVIDER=disabled` during containment; deterministic forms/messages remain available.

## Threat boundaries

The API treats browser input, Excel cells, raw MT-like text, filenames, request IDs, and model output as untrusted. Pydantic, workbook parsing, allowlists, strict model schema, grounding/placeholders, canonical merge conflict checks, deterministic resolution, and validation form separate boundaries. The model has no tools and the frontend is not a trusted validator.

## Known gaps before production

- Development session/RBAC/tenant/maker-checker foundations exist, but a contracted OIDC/SAML
  provider, enterprise group mapping, account lifecycle, and penetration test are not implemented.
- Sensitive draft fields and versions are envelope encrypted, but KMS/HSM integration, rotation
  automation, encrypted object storage, backup policy, and authorised retention purge remain open.
- SQLite/report files are development-only; production settings require PostgreSQL, but operational
  HA, backup/restore, row-level security, and database hardening require deployment engineering.
- In-memory rate limiting is per process and not suitable for distributed deployment.
- AI circuit breaker, telemetry percentiles, and daily usage budgets are process-local; a distributed deployment needs shared enforcement/observability.
- Provider privacy controls constrain routing but do not replace contractual, legal, DLP, or institutional data-governance review.
- Container images are not signed or accompanied by an SBOM/vulnerability-policy pipeline.
- The local Docker daemon used for verification reported a non-default seccomp profile; deployment must enforce an approved seccomp/container policy.
- No institution security assessment, penetration test, DLP, SIEM integration, or formal privacy
  impact assessment. A data-classification registry and retention setting are foundations, not a
  completed governance program.
- The raw parser and business rules are a supported test subset, not a compliance security control.

Production submission is fail-closed until these gaps and the institution's connector/rule-pack
requirements are resolved.

## Real-data controls

Real-data mode requires `DATA_ENCRYPTION_KEY` and `SESSION_HMAC_SECRET`. AES-256-GCM envelope
encryption uses authenticated tenant/draft/field context; field plaintext is absent from normal
logs and AI telemetry. Sessions are HTTP-only, same-site and CSRF-protected; production also
requires secure cookies. Tenant-scoped queries return indistinguishable not-found errors.

Submission destinations come only from the server-side connector registry. Dual production gates,
roles, immutable checksum approval, idempotency, external-validation policy, and an explicit UI
confirmation are required. No arbitrary browser URL can be submitted.

## Expansion controls

Cache IDs are server-keyed HMACs over tokenised/context-versioned inputs. Cached templates use current-request placeholders, are schema/domain revalidated, and are isolated by profile/model/prompt/schema/knowledge/standards/taxonomy versions. Failures and unvalidated output are not cached. L1 is bounded with TTL and process-local single-flight.

Knowledge fails closed on missing/unverified provenance, bad signatures/options/dependencies, or overlays that broaden/weaken rules. MT568 rejects controls, script/code-fence text, and raw MT fragments. Workflow Excel enforces path/type/container/size/row/header controls and formula escaping.

For cache-secret rotation, deploy a new `AI_CACHE_HMAC_SECRET`, increment `AI_CACHE_KEY_VERSION`, restart instances, and purge unreachable entries through approved offline maintenance. On exposure, disable AI/cache, rotate both secrets, and review content-free audit metadata only.
