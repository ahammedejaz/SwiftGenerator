# Client-Usable SWIFT Platform Plan

Date: 2026-08-05  
Status: self-reviewed; autonomous implementation authorised  
Scope: source-bounded ISO 15022 authoring platform; no certification or unconfigured network connectivity

## 1. Repository findings

- Git has no commits. Existing files are intent-to-add or untracked and are treated as user-owned; no unrelated file will be deleted or reset.
- Runtime is FastAPI/Pydantic/SQLAlchemy/Alembic with SQLite, Next.js 16/React 19, Docker Compose, Pytest, Playwright, Ruff, mypy, ESLint, and TypeScript.
- Sixteen message types are executable: MT530, MT537, MT540–MT548, and MT564–MT568. Five shared settlement composers and module-local MT530/MT537/corporate-action composers are deterministic.
- The Tag Intelligence repository has exactly 200 records. It validates coverage only against hard-coded emitted signatures, not against an authoritative message-format registry.
- There are zero versioned machine-readable specification rows. Consequently no official-row denominator, row-level validation traceability, or evidence-based completeness percentage exists.
- Existing forms are scenario demonstrations. Corporate actions and settlement processing have no editable business fields; MT537 exposes only status and amount direction; settlement guided mode exposes a narrow instruction subset and silently inserts synthetic parties/accounts.
- Penalty and corporate canonical models reject non-synthetic data. Existing composers emit `{1:DEMONSTRATION}` and proprietary `SYNTH` schemes.
- Raw parsing is an allowlisted validator, not a complete canonical round trip. Current files are block-like demonstration text, not configurable FIN/RJE envelopes.
- One golden file exists for every target type; it verifies current composer output, not full optional/repeatable format coverage.
- There is no authentication, session, CSRF, tenancy, RBAC, maker/checker, encryption, retention/purge, external validation, connector, submission, ACK/NAK, or production PostgreSQL driver.
- Existing OpenRouter structured interpretation, tokenisation, exact HMAC cache, privacy flags, and content-free usage telemetry are reusable and must not receive raw financial data.
- Current database migrations are additive through `20260805_0005`; Docker runs migrations before API startup.
- Runtime credentials exist only in ignored configuration. Their values were not inspected or printed.

### Current evidence-based coverage

`Configured rows` below means unique signatures in the existing emitted-subset allowlist, not official full-format rows. `Specification rows` is zero because no specification registry exists. UI is hard-coded rather than definition-driven, so no configured row is dynamically form-renderable today. Validator row coverage is also untraceable today because findings do not reference specification row IDs.

| Message | Specification rows | Configured rows | Knowledge | Canonical paths | Parser/composer signatures | Golden files |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| MT530 | 0 | 5 | 5 | 5 | 5 | 1 |
| MT537 | 0 | 23 | 23 | 23 | 23 | 1 |
| MT540 | 0 | 14 | 14 | 14 | 14 | 1 |
| MT541 | 0 | 15 | 15 | 15 | 15 | 1 |
| MT542 | 0 | 14 | 14 | 14 | 14 | 1 |
| MT543 | 0 | 15 | 15 | 15 | 15 | 1 |
| MT544 | 0 | 12 | 12 | 12 | 12 | 1 |
| MT545 | 0 | 13 | 13 | 13 | 13 | 1 |
| MT546 | 0 | 12 | 12 | 12 | 12 | 1 |
| MT547 | 0 | 13 | 13 | 13 | 13 | 1 |
| MT548 | 0 | 12 | 12 | 7 | 12 | 1 |
| MT564 | 0 | 14 | 14 | 14 | 14 | 1 |
| MT565 | 0 | 10 | 10 | 10 | 10 | 1 |
| MT566 | 0 | 13 | 13 | 13 | 13 | 1 |
| MT567 | 0 | 9 | 9 | 7 | 9 | 1 |
| MT568 | 0 | 6 | 6 | 6 | 6 | 1 |
| **Total** | **0** | **200** | **200** | **195** | **200** | **16** |

## 2. Current limitations

The 200 records prove documentation of emitted fields only. They do not prove full UHB coverage, current SR2026 validation rules, market practice, client acceptance, full option/qualifier catalogues, or complete conditional/repetition rules. `DEMO_SR2026` is not an authoritative standards label. Existing “VERIFIED” status means reviewed for the bounded implementation, not externally validated.

The public primary-source inventory confirms current SR2026 UHB publication timing and the roles of MT530/537/540–548/564–568, but the current Message Format Validation Rules are access-controlled and no institution MyStandards/SMPG/client pack is supplied. No message can truthfully be promoted to `PRODUCTION_CAPABLE` in this implementation.

## 3. Target architecture

```text
Authorised user + tenant + role
  -> versioned specification registry and effective client/event profile
  -> encrypted immutable draft versions
  -> specification-validated field/sequence instances with visible provenance
  -> deterministic generic composer / existing source-bounded workflow composer
  -> separated local validation levels
  -> block 4 + configured envelope/export adapters
  -> immutable review/approval version
  -> allowlisted server connector with idempotency and production gate
  -> submission attempts and externally supplied ACK/NAK/audit evidence
```

Existing deterministic message engines remain authoritative. New authoring services are isolated from OpenRouter and can be disabled without changing old APIs.

## 4. Authoritative-source strategy

- Add provenance statuses `VERIFIED`, `CLIENT_VERIFIED`, `EXTERNAL_VALIDATION_REQUIRED`, `UNVERIFIED`, and `DEPRECATED` with verification method/time/reviewer.
- Treat existing reviewed rows as the configured V1 subset and retain their stable internal references.
- Mark completeness against the missing current authorised format pack as unknown; capability remains `PARTIAL`.
- Provide a strict importer/schema for future SR/MyStandards/client packs. Unverified rows may be catalogued but cannot enter validated composition.
- Keep source-derived descriptions concise and never commit handbook pages.

## 5. Message-specification ingestion

Create typed message, sequence, field-row, code-list, rule-reference, and provenance models. A versioned YAML manifest will define message metadata and sequence order/cardinality; the compiler will join it with verified knowledge rows. Startup will fail on broken nesting, duplicates, invalid options/qualifiers, missing source, unknown rule targets, or a mandatory enabled row without knowledge.

The importer boundary will accept future approved JSON/YAML packs offline. Runtime web scraping is prohibited.

## 6. Coverage-accounting methodology

For each message compute configured rows, knowledge, dynamic-form, composer, parser, basic validator, sample, and golden coverage by stable row ID. Percentages use configured source-backed rows as denominator. A separate `authoritativeCompletenessKnown` flag prevents 100% configured-subset coverage from implying full UHB coverage. Generate `MESSAGE_COVERAGE_REPORT.md` and `/api/specifications/.../coverage`.

## 7. Real-data entry architecture

New drafts default to empty. No sample/default is inserted unless the user explicitly loads a sample or selects a visible profile default. Every field carries `USER_ENTERED`, `PROFILE_DEFAULT`, `SYSTEM_DERIVED`, `IMPORTED_EXCEL`, `IMPORTED_API`, or `SAMPLE_DATA`. Real-data authoring is available only through authenticated tenant-scoped endpoints with encryption configured.

## 8. Complete dynamic form architecture

The backend returns a form definition compiled from the effective specification and profile. The frontend renders business questions and expert sequence rows from that definition. It never embeds a message-specific field list. The first implementation renders all 200 configured rows, not unknown official rows.

## 9. Optional and conditional field handling

Presence, allowed options/codes, profile enablement, and deterministic condition results are returned per field. Optional rows can be added/removed; unavailable rows return a deterministic reason. Conditional rules without approved expressions are `EXTERNAL_VALIDATION_REQUIRED`, not guessed.

## 10. Repeatable-sequence handling

Sequence instances have stable IDs, parent IDs, occurrence indexes, min/max occurrence rules, and immutable version ownership. Reordering is limited to occurrence order within repeatable sequences; specification row order cannot be changed.

## 11. Corporate-action expansion

Remove the synthetic-only restriction from the configured DVOP models and expose all current MT564–MT568 rows through the generic builder. Preserve lifecycle correlation and cash-only MT566 limitations. Add an event-profile registry/import boundary. Cash dividend, interest, redemption, tender/exchange, rights, stock dividend, merger, mandatory-with-options, cancellation, and securities movement remain disabled until verified event packs are supplied.

## 12. MT537 expansion

Represent the configured penalty structure as repeatable D1 currency, D1a counterparty, and D1a1 penalty instances. Support multiple user-entered groups and signed amount semantics without calculation. Pending-transaction B/C structures, calculation methods/details, account owner variants, and fields absent from the approved repository source remain catalogue gaps.

## 13. MT530 amendment boundaries

Keep priority modification as the only operational MT530 authoring row set. Add catalogue/import structures for other commands, but no core-trade change. Existing deterministic cancel/rebook policy remains authoritative.

## 14. Settlement lifecycle expansion

Expose all currently configured MT540–MT548 rows and functions in the dynamic builder, including explicit sample/default provenance. Existing cancellation, confirmation, status, and cancel/rebook correlation remain. Additional optional chains, pre-advice variants, pair-off, turnaround, and market-specific rules stay unsupported until imported.

## 15. Tag Intelligence expansion

Add specification row/cardinality/capability and expanded verification fields to effective knowledge responses. All builder, annotated sample, validation, raw, and report rows link to the message-specific knowledge ID. Do not invoke an LLM for details.

## 16. Sample-message architecture

Generate samples from deterministic composers and typed canonical sample factories. Store sample metadata/inputs, never separately authored raw output. Provide at least one current-subset sample for all 16 messages, annotations, download, comparison, and explicit `SAMPLE_DATA` loading. Additional lifecycle variants are added only where existing composers support them.

## 17. FIN envelope generation

Separate block 4 from envelope output. Add typed profile/request provenance for LT addresses, priority, MUR, and interface-generated session/sequence fields. Full FIN export requires explicit configured values; it never invents ACK/NAK, authentication, checksum trailers, session, or sequence. Existing demonstration blocks remain backward-compatible old API output.

## 18. Download formats

New version downloads will support block-4 `.txt`, canonical JSON, validation JSON, validation HTML, and evidence ZIP. Configured FIN `.fin` is enabled only when required envelope values exist. RJE adapters are configuration-driven and remain `EXTERNAL_VALIDATION_REQUIRED` until a client format contract is imported; no guessed production RJE is claimed.

## 19. Submission connector architecture

Create a provider-neutral connector protocol and registry. `DOWNLOAD_ONLY` is operational. A deterministic mock UAT connector exists only in explicit test/development configuration. HTTPS/SFTP/local-drop/MQ/Alliance/custom adapters expose configuration schemas and capability status but make no network/file submission without an approved client adapter.

## 20. Approval workflow

Implement DRAFT → VALIDATED → REVIEW_REQUESTED → APPROVED → QUEUED → SUBMITTED → ACKNOWLEDGED plus rejection/failure branches. Approval binds tenant, immutable version ID, checksum, profile/release, and approver. Authors cannot approve their own production version; edits create a new version and invalidate approval.

## 21. External validation integration

Add a provider-neutral evidence model and upload adapter. It records validator type, hash, reference, profile/release, status, timestamp, and findings. No MyStandards API claim is made. Production policy can require a matching passed result.

## 22. Client-profile architecture

Keep YAML profiles immutable and add envelope, validation-policy, event-profile, connector allowlist, and supported-output overlays. Existing demo profiles are renamed in UI as internal sample profiles; no client profile is labelled production-approved.

## 23. Authentication and authorisation

Implement server-side sessions, HttpOnly/SameSite cookies, CSRF double-submit enforcement, expiry/disable checks, role policies, and resource-level tenant checks. Add an explicit development-login adapter and OIDC/SAML provider protocols/configuration boundaries; do not invent IdP credentials or claim operational federation.

## 24. Tenant isolation

All new real-data tables include non-null tenant ID and repositories require an authenticated context. Cache contexts include an opaque tenant fingerprint. Tests cover cross-tenant IDOR attempts. Existing synthetic endpoints remain backward-compatible but are not the real-data path.

## 25. Data encryption

Add a KMS/key-provider protocol and AES-GCM envelope encryption using a server-side KEK for sensitive field values and canonical payloads. Production real-data mode fails closed without a configured key. SQLite remains development/test; SQLAlchemy/Alembic stay PostgreSQL-compatible and a PostgreSQL driver is added for deployment.

## 26. Audit architecture

Append-only application events capture actor/tenant/action/resource/version/outcome/checksum/time and masked metadata. No raw field values, messages, secrets, or connector responses are logged. Database immutability remains a production hardening gap.

## 27. LLM privacy boundary

Deterministic forms, specifications, samples, composition, validation, export, approval, and submission never call OpenRouter. Existing tokenisation remains. The model is not given drafts, raw messages, full narratives, audit or lifecycle history.

## 28. LLM cache behaviour

Add opaque tenant fingerprint to cache-key context and tests for cross-tenant/profile/version isolation. Existing HMAC, placeholder, validation, TTL, and telemetry behavior remains unchanged.

## 29. API changes

Add specification/catalogue/coverage/sample endpoints; authenticated draft/field/sequence/version/validate/compose/import/download/audit endpoints; auth/session endpoints; review/approval; connector capability/health/test; submission/idempotency; and external-validation evidence. Preserve old APIs.

## 30. UI changes

Add Message Catalogue, authenticated Message Builder, Operations, and safe Security Context screens. Builder tabs are Business, Expert Sequence, Raw/Annotated, Validation, Downloads, and Review/Submission. Existing workflows remain available and are relabelled as configured subsets rather than demo-only platform identity.

## 31. Database migrations

Create additive tables for tenants, users/roles, sessions, drafts/versions, sequence/field instances, samples metadata, reviews/approvals, connectors, submissions/attempts, external validation, and audit. Values are encrypted; old rows are untouched. SQLite and PostgreSQL types use portable SQLAlchemy constructs.

## 32. Testing

- Specification schema/nesting/order/cardinality/provenance and row coverage for all 16 types.
- Dynamic form renderability and optional/repeatable/conditional behavior.
- Generic compose/parse round trip and line mappings.
- Sample/golden derivation and annotations.
- MT537 multi-group/signed amount without calculation.
- DVOP real-data lifecycle and explicit unsupported event refusal.
- Envelope/download integrity and deterministic filenames.
- Auth/session/CSRF/RBAC/tenant/maker-checker/encryption/audit/purge.
- Connector allowlist/idempotency/production gate/retry/ACK/NAK handling with mocks only.
- External evidence hash correlation.
- Existing 233-test and 10-Playwright suite.

## 33. Performance

Measure specification/form schema, knowledge search, sample load, compose, validate, download, bulk, cache, live model, and connector queue paths. No deterministic operation may call the LLM. Use development-machine results as baselines, not SLOs.

## 34. Deployment

Add PostgreSQL and security settings to `.env.example` and Compose without placing secrets in images. Development defaults keep real-data/submission disabled. Production validation requires PostgreSQL, encryption key, non-development auth, secure cookies/TLS proxy assumptions, cache HMAC, and production submission double gate.

## 35. Rollback

All new features are additive and behind `REAL_DATA_MODE_ENABLED`, `AUTH_MODE`, and submission gates. Old endpoints/composers remain. Migrations create new tables/nullable metadata only. Disabling new flags restores the current synthetic workflow without destructive downgrade.

## 36. Expected file changes

New backend packages: `specifications`, `authoring`, `auth`, `encryption`, `exports`, `connectors`, `external_validation`; configuration manifests; migration 0006; API models/routes; tests. New frontend pages/components: catalogue, builder, operations, session/security. New samples, coverage generator/report, and required guides. Existing settings, models, main/routes, cache context, layout/navigation, Compose, dependency manifests, tests, and documentation are extended.

## 37. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Full current SR/client rules absent | Remain `PARTIAL`; strict import boundary; no completeness claim. |
| Real data exposed | New path requires auth, tenant, encryption; content-free logs; LLM excluded. |
| Generic field permits invalid syntax | Validate row ID, option, qualifier, format and code before deterministic order/render. |
| Connector becomes SSRF primitive | Registry-owned destinations only; no URL/host in request. |
| Fake ACK/NAK | Store only connector-supplied evidence; mock is visibly test-only. |
| Self-approval/replay | Immutable version, role separation, checksum and unique idempotency key. |
| SQLite mistaken for production | Production settings reject SQLite; PostgreSQL driver/config documented. |
| RJE/FIN assumptions | Require explicit interface/client configuration; mark external validation required. |
| Large change regresses settlement | Keep old APIs/composers and run complete goldens/E2E continuously. |

## 38. Acceptance criteria

- All 200 configured rows compile into typed definitions, dynamic forms, knowledge, generic parser/composer maps, and coverage metrics.
- Every target type has a deterministic annotated sample and can create an encrypted tenant-scoped draft with user-entered values and visible provenance.
- Optional fields and configured repeatable sequences can be managed without changing standard order.
- New generic output round-trips for configured rows; validation levels are separate.
- Block 4/JSON/validation HTML/ZIP work; configured FIN requires explicit interface data; unsupported RJE configurations fail safely.
- Development authentication, RBAC, tenant isolation, CSRF, session expiry, maker/checker, edit invalidation, encryption, audit, and purge tests pass.
- Download-only and mock-UAT connector lifecycles enforce validation, approval, idempotency, allowlist, and production gates; no real connector is contacted.
- External-validation evidence is hash-correlated and clearly separate.
- Old and new tests, lint/type/build/E2E/migrations/audits/Docker/scans pass.
- Coverage and final reports state configured-subset percentages separately from unknown authoritative completeness.

## 39. Supported versus unsupported scope

Supported after implementation: secure authoring and operational controls for the 200 existing source-bounded rows across all 16 target messages, real user input without synthetic insertion, annotated composer-generated samples, deterministic composition/validation/export, and mock/download connector operations.

Explicitly unsupported: full current SR2026 format/validation coverage, MyStandards API, institution/client/market rule conformance, unconfigured RJE/Alliance/MQ/SFTP/HTTPS connectivity, production IdP federation, production ACK/NAK, additional CA event packs, complete pending-transaction MT537, complete MT530, universal FIN parsing, SWIFT network transmission, and certification.

## Implementation sequence

1. Specification registry, coverage accounting, and source-status model.
2. Samples, generic fields/sequences, composer/parser/export core.
3. Encrypted drafts, auth/tenant/RBAC/session/CSRF/audit migration.
4. Review/approval/external-validation/connector/submission lifecycle.
5. Dynamic catalogue/builder/operations UI and Excel/sample flows.
6. Full verification, performance, Docker/PostgreSQL configuration review, documentation, and report.

## Plan Self-Review

### Requirements covered

The plan covers reconnaissance, source restrictions, all target messages, specifications, coverage accounting, real data and provenance, dynamic/repeatable forms, Tag Intelligence, samples, MT537/corporate/settlement/MT530 boundaries, generic composition, FIN/export/RJE constraints, validation levels/external evidence, authentication/tenancy/encryption/audit, LLM/cache safety, connectors/submission, Excel/raw round trip, APIs/UI, migrations, performance, deployment, rollback, testing, documentation, and transparent capability states.

### Requirements initially missed and corrected

- Added an explicit distinction between configured-subset coverage and unknown authoritative completeness.
- Added fail-closed full-FIN behavior for missing interface-generated session/sequence values.
- Added tenant fingerprinting to AI cache context without raw tenant IDs in keys.
- Added edit-after-approval invalidation and immutable checksum/version binding.
- Added external validation evidence without claiming a MyStandards API.
- Added explicit test-only ACK/NAK semantics and no automatic bulk submission.
- Added a production-settings gate requiring PostgreSQL and non-development auth.

### Remaining assumptions

- The existing 200 reviewed records may be used as the only enabled V1 field subset; they do not establish full current-standard coverage.
- The public SWIFT source inventory establishes message purpose/release timing, but current locked validation rules require an authorised future import.
- Development session auth and mock UAT are acceptable test adapters, never production identities/connectivity.
- AES-GCM with an injected KEK is an acceptable local envelope-encryption adapter; production KMS integration remains required.

### Supported scope

All 16 target message types can use the secure generic authoring framework for their currently configured rows. Existing deterministic domain flows remain intact. Download-only and mock-UAT operations are testable.

### Explicitly unsupported scope

Any row, event, qualifier, code, market/client rule, connector, identity provider, or external validator absent from the approved repository source set is not enabled. No message will be labelled `PRODUCTION_CAPABLE` in this change.

Self-review result: **PASS WITH SOURCE-BOUND SCOPE**. Implementation can continue autonomously without an approval pause.

## Execution outcome

Implementation completed for the source-bounded foundation described above. The full result,
verification evidence, unmet acceptance criteria, and production gaps are recorded in
`CLIENT_USABLE_SWIFT_PLATFORM_REPORT.md`. No capability was promoted beyond `PARTIAL`.
