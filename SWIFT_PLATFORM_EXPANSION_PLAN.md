# Intelligent SWIFT Message Engineering and Testing Platform Expansion Plan

Status: implementation plan, self-reviewed on 2026-08-05  
Repository: `SwiftGenerator`  
Execution mode: autonomous; this plan is not an approval gate

> This plan covers a controlled ISO 15022 demonstration subset. It does not claim full standards coverage, Swift network connectivity, institution approval, or Swift certification.

## 1. Repository findings

- Git is initialised on `main`, but there is no commit baseline. Every existing application file is uncommitted (`A`) and the OpenRouter integration files are untracked. All existing content is therefore treated as user-owned and must be preserved.
- A root `.env` exists and is ignored. Its presence was confirmed without reading or printing values. `.env.example` contains names and non-secret defaults only.
- The current FastAPI/Pydantic/SQLAlchemy/SQLite backend, Next.js 16/React 19 frontend, profile YAML, Alembic, Docker Compose, Pytest, and Playwright architecture is internally consistent and will be extended rather than replaced.
- The current domain supports MT540–MT548 through five deterministic composers. It persists generated scenarios/messages/findings and traverses a one-level settlement lifecycle.
- The existing tag representation is `RenderedField(sequence, tag, qualifier, value, businessPath, businessMeaning)`. It is suitable as the composer-to-knowledge coverage join point, but lacks a stable `knowledgeId`.
- The OpenRouter integration already has a provider-neutral async boundary, strict schema normalisation, privacy routing, request-local placeholders, bounded retries/escalation, circuit breaking, budgets, content-free telemetry, and an AI audit table.
- The deterministic phrase interpreter is explicitly identified as non-AI. It remains the resilience/form path.
- Excel uses `openpyxl`, validates OOXML, caps size/rows, escapes formula-leading values, continues valid rows, and emits a ZIP plus summary workbook and JSON reports.
- Baseline verification on 2026-08-05: Ruff and frontend ESLint passed; mypy passed 61 source files; TypeScript passed; 156 Pytest tests passed with one live test deselected; Docker Compose configuration passed; Git whitespace check passed.
- No authentication, RBAC, tenancy, PostgreSQL, distributed cache, or distributed telemetry exists. Operator-only cache mutation therefore cannot safely be exposed in the normal runtime; a CLI command and an explicitly development-enabled endpoint will be used.
- No existing tag knowledge pack, workflow registry, MT530 composer, MT537 composer, or corporate-action composer exists.

## 2. Current architecture

The current authoritative flow is:

```text
text or form
  -> optional OpenRouter intent interpretation
  -> strict model-output validation and local grounding
  -> canonical SettlementScenario
  -> deterministic resolver and missing-field engine
  -> versioned ClientProfile
  -> layered validation
  -> one of five deterministic composers
  -> persisted message, field map, lifecycle, report
```

Core seams to retain:

- `app/domain`: enums, canonical models, resolution, missing fields, validation.
- `app/composers`: deterministic sequence/tag rendering.
- `app/profiles`: versioned profile loading/defaults/requirements.
- `app/services`: orchestration outside API routes.
- `app/agents`: provider-neutral interpretation and safe telemetry.
- `app/persistence`: SQLAlchemy repositories and additive migrations.
- `app/bulk`: workbook mapping to the same services as REST.
- `frontend/lib/contracts.ts`: typed server contract mirror.

## 3. Proposed target architecture

Introduce three orthogonal registries without weakening existing message authority:

```text
WorkflowModuleRegistry
  -> settlement
  -> settlement-command
  -> penalties
  -> corporate-actions

TagKnowledgeRepository
  -> versioned YAML records
  -> profile overlays
  -> coverage validation against composer field maps

AiCallDecisionPipeline
  -> deterministic answer check
  -> verified knowledge lookup
  -> exact context-aware cache
  -> OpenRouter only when required
```

Each workflow module owns typed models, validation, composition, parsing for its own supported subset, lifecycle correlation, capabilities, and knowledge records. Existing settlement services will be adapted behind the registry without rewriting their proven composers.

## 4. Tag Intelligence Centre design

- Add typed `TagKnowledge`, `KnowledgeSource`, `TagExample`, `ProfileKnowledgeOverlay`, dependency, presence, rule-layer, and review-status models.
- Load version-controlled YAML from `backend/config/knowledge/` at application startup.
- Validate duplicates, message ownership, options, provenance, standards label, dependency references, and minimum explanation fields.
- Join generated fields by `(messageType, sequencePath, fieldTag, qualifier)` and return a stable `knowledgeId` in API views.
- Keep ordinary tag details fully deterministic. Optional LLM simplification will receive only selected verified records and will never create rule data.
- Add message/tag/search/dependency APIs and a Next.js `/knowledge` screen plus a reusable details drawer in Business, Tag, and Raw views.
- Display base rule, effective profile overlay, condition, source/review/version, common mistakes, related fields, and a small verified dependency tree.

## 5. Tag knowledge data model

The authoritative model will include:

- identity: knowledge ID, workflow module, message type, sequence path, tag, qualifier;
- explanation: display name, business meaning, technical meaning, why used, business question, missing impact, format explanation;
- rules: presence, condition expression/description, supported options, allowed codes, dependencies, required-with/conflicts/related fields, lifecycle impact, rule layer;
- examples: synthetic-only value and explanation;
- search terms;
- versioning: knowledge-base version, standards release/profile version;
- provenance: source type, stable source reference, review status, reviewed date, reviewed-by classification.

All models reject unknown properties and all enums are controlled. Conditions are descriptive identifiers interpreted by deterministic rules, never executable strings.

## 6. Source-provenance strategy

- Use concise derived metadata from the official ISO 15022 catalogue/User Handbook pages and public Swift Category 5 message-reference/usage guides reviewed during reconnaissance.
- Stable references will use official URLs such as `https://www.iso20022.org/15022/uhb/finmt530.htm`, `finmt537.htm`, and `finmt564.htm` through `finmt568.htm`, plus the reviewed official Swift volume references for settlement messages.
- Store no copied pages and no long handbook text.
- Label the current knowledge snapshot `KB_2026_08_05_V1`; preserve each source page's standards context separately from demo profile labels.
- Rules needing a market practice or institution implementation guide will be `UNVERIFIED` and disabled. They will not be accepted by composers.
- Coverage tests will require `VERIFIED` provenance for every emitted field.

## 7. Workflow-module architecture

Define a typed `WorkflowModule` protocol and registry with:

- module ID, display name, supported/partial/disabled/planned message types;
- resolve, missing fields, validate, compose, parse, correlate, knowledge, capabilities;
- profile enablement and supported operations;
- ownership collision detection;
- dispatch methods that return controlled unsupported results instead of central `if message_type` growth.

Initial modules:

- `SettlementWorkflowModule`: existing MT540–MT548.
- `SettlementCommandWorkflowModule`: cancellations and verified MT530 subset.
- `PenaltyWorkflowModule`: MT537 penalty statement subset.
- `CorporateActionWorkflowModule`: bounded MT564–MT568 lifecycle.

## 8. Settlement cancellation design

- Create cancellation requests only from persisted MT540–MT543 instructions.
- Deep-copy canonical data, allocate a caller-provided or synthetic unique sender reference, set `function=CANC`, set `relatedReference` to the original sender reference, and preserve direction/payment/security/cash/party fields unchanged.
- Compose through the existing instruction composer so tag/sequence authority remains deterministic.
- Reject absent originals, non-instructions, duplicate active cancellations, reused references, and any attempted core-value mutation.
- MT548 cancellation accepted/rejected statuses use controlled configured category/reason values and correlate to the cancellation while the lifecycle root remains the original instruction.
- Make lifecycle traversal recursive so instruction -> cancellation -> MT548 -> replacement is visible.

## 9. Settlement amendment decision model

Add deterministic `AmendmentPolicyRegistry` data with an effective policy per profile and lifecycle stage. Output classifications are exactly:

- `PROCESSING_DATA_MODIFICATION`
- `CORE_BUSINESS_DATA_CHANGE`
- `CANCELLATION_ONLY`
- `UNSUPPORTED_MODIFICATION`
- `CLARIFICATION_REQUIRED`

The first verified policy will permit MT530 priority (`processing.priority`) changes. Quantity, identifier, amount, date, settlement parties, and safekeeping account will require cancel/rebook or be unsupported according to explicit profile configuration. Unknown paths and ambiguous multiple changes fail closed. The LLM cannot alter policy decisions.

## 10. MT530 scope and limitations

- Implement a source-backed MT530 subset for priority-indicator modification using `GENL`, `SEME`, `23G`, account, `REQD`, related reference, and `22F::PRIR` in deterministic order.
- Validate reference syntax/length, account presence, original-message linkage, and priority range `0001`–`9999`.
- Add supported-subset parser, golden file, knowledge records, API, UI, Excel columns, lifecycle entry, and report metadata.
- Profile-gated proprietary `PROC`, approve/cancel/reject commands, buy-in details, and arbitrary non-matching modifications remain disabled because no approved institution/market implementation guide is present.
- The UI and capabilities endpoint will say “MT530 priority modification subset,” never “universal amendment.”

## 11. MT537 penalties design

- Implement the official penalties statement structure subset: GENL statement identity/date/account/activity/structure, `PENA`, `PENACUR`, `PENACOUNT`, repeated `PENDET`, penalty references, type, status/reason, computed amount, method, days, detection date, and optional related transaction reference.
- Support controlled penalty types `SEFP` and `LMFP`; statuses ACTIVE/NOT_COMPUTED/REMOVED; controlled new/update/remove reason semantics; payable/receivable represented deterministically through amount sign/direction.
- The platform reports supplied penalty amounts and never calculates them. Missing amount is blocking unless a verified not-computed rule explicitly allows the configured representation.
- Correlate by a supplied supported settlement reference where found, but allow standalone statements with an explicit “not correlated” result because MT537 is a statement message.
- Add builder, history/lifecycle view, raw/tag/validation views, APIs, workbook mode, ZIP/report metadata, parser, tests, and golden file.

## 12. MT564–MT568 corporate-action design

- Implement a deliberately small, source-backed canonical subset for event references, event code, mandatory/voluntary classification, ISIN, safekeeping account, dates, options, selected option, quantities, cash amount/currency, controlled status/reason, and narrative.
- Initial event codes: cash dividend (`DVCA`), dividend option (`DVOP`), interest payment (`INTR`), issuer-decided redemption (`REDM`), and exchange (`EXOF`). The UI uses friendly names but the configured code set is authoritative.
- MT564: GENL, event and sender references, function, CAEV, processing state, USECU/account/security, optional CADETL dates, repeated CAOPTN option number/code/default flag/currency.
- MT565: GENL/linkage, USECU/account/security, CAINST option number/code and instructed quantity/amount where relevant.
- MT567: GENL/linkage, controlled IPRC/CPRC/EPRC status and matching reason qualifier, optional CA option details.
- MT566: GENL/linkage, USECU/security/account, CACONF option, posting quantity, optional cash movement/payment date.
- MT568: GENL/linkage, optional USECU, mandatory ADDINFO with a controlled narrative category and sanitised/length-limited narrative.
- Do not implement tax, beneficial-owner, fractional entitlement, market claims, complex exchange ratios, or every event-specific conditional rule.

## 13. Future-workflow extension architecture

Document and test a registration path for future Category 5, statements/reconciliation, collateral, trade confirmation, treasury, payments, and ISO 20022 modules. Planned capabilities appear as metadata only. Adding a module must not require editing unrelated composers, validators, knowledge loaders, or UI navigation conditionals beyond registry-provided capability rendering.

## 14. Canonical-domain model changes

- Preserve `SettlementScenario` for backward compatibility.
- Add separate typed `SettlementCommandScenario`, `PenaltyStatement`, `PenaltyDetail`, `CorporateActionEvent`, `CorporateActionOption`, `CorporateActionInstruction`, `CorporateActionStatus`, `CorporateActionConfirmation`, and `CorporateActionNarrative` models.
- Add a generic persisted `WorkflowEnvelope`/metadata shape rather than forcing non-settlement fields into `SettlementScenario`.
- Extend `MessageType` and controlled enums to MT530, MT537, and MT564–MT568.
- Retain camelCase APIs, decimal strings, ISO dates, `extra=forbid`, synthetic-data marker, and Pydantic validation.

## 15. Composer changes

- Retain all five existing settlement composers byte-for-byte unless knowledge IDs require a non-output field-map change.
- Add one deterministic composer per new structurally distinct message: MT530 command, MT537 penalty statement, and corporate-action notification/instruction/confirmation/status/narrative.
- Reuse a safe field collector to construct raw text and field maps, without dynamic/user templates.
- Add golden files and knowledge coverage assertions for every emitted field.

## 16. Parser changes

- Keep the existing settlement raw parser stable.
- Add a registry-dispatched supported-subset parser using deterministic sequence boundaries and per-message allowed field specifications.
- Reject fields/order/qualifiers outside each implemented subset and label all parser outputs as partial-subset validation.
- MT568 narrative remains inert data and is never treated as instructions to code or an LLM.

## 17. Validation changes

- Reuse `ValidationFinding` and layered reporting.
- Add module-local canonical, business, profile, structure, and lifecycle layers.
- Add stable rule IDs for MT530 range/linkage; MT537 structure/status/reason/amount/duplicate references; corporate-event option/deadline/linkage/movement/narrative rules.
- Cached AI output never bypasses validation and cannot set validity.
- Unsupported/unverified operations return explicit blocking findings, not guessed output.

## 18. Lifecycle-correlation changes

- Traverse message relations recursively and prevent cycles.
- Add workflow IDs and event kinds to persistence so non-settlement timelines remain typed.
- Validate settlement cancellation direction/payment immutability, replacement-reference uniqueness, penalty reference linkage, corporate event/option/instruction/status/confirmation references, quantities, and dates.
- Render module-specific timelines while retaining the existing `LifecycleTimeline` contract for existing API consumers.

## 19. Client-profile changes

- Add module enablement, message support, MT530 amendment policies, penalty allowed statuses/reasons/currencies, corporate event/status/option policies, narrative rules, and knowledge overlays.
- Profile overlays may narrow options or add requirements/explanations; they cannot broaden a base `UNVERIFIED` rule or contradict base standards metadata.
- Preserve Base/BFS settlement differences and add visible safe differences for new workflows only where supported.

## 20. LLM responsibility changes

- Extend the intent taxonomy with workflow module and bounded penalty/corporate-action classifications only after strict schema/version updates.
- Model output remains a partial patch; no message type/tag/qualifier/code invention and no amount calculation.
- Tag explanations use supplied verified records only and return “This tag is not yet covered by the verified knowledge profile.” when absent.
- Existing OpenRouter models, privacy settings, strict structured output, retry/escalation, and deterministic authority remain unchanged.

## 21. LLM call-avoidance strategy

Introduce an `AiCallDecisionService` that records a safe decision reason:

1. local request validation;
2. deterministic resolver/form check;
3. knowledge repository check;
4. workflow registry check;
5. exact cache lookup;
6. provider call only for unstructured interpretation, optional simplification/comparison/translation, or complex module intent;
7. deterministic post-processing and validation.

Normal tag clicks, resolver calls, validation, parsing, generation, profile display, lifecycle responses, and reports never invoke OpenRouter.

## 22. Cache architecture

- Define `AiResultCache` protocol, SQLite persistent adapter, and bounded process-local L1.
- Use namespace-specific TTLs: intent 30 days; tag simplification/comparison/translation 90 days; validation wording 30 days; lifecycle-dependent interpretation 1 day with state fingerprint.
- Apply a process-local keyed in-flight future map for stampede protection with a bounded wait.
- Store only validated structured templates with canonical typed placeholders and original aggregate usage.
- Fail cache reads/writes safely: a corrupt entry becomes a miss; provider success is not replaced by a cache persistence failure.

## 23. Cache-key design

- Build canonical JSON from namespace, canonicalised sanitised text, minimal context fingerprint, workflow/message/profile/version, standards release, prompt/schema/knowledge/taxonomy/model/settings/language/audience, and key version.
- Canonicalise request-random placeholders to ordered typed tokens before keying.
- Calculate opaque IDs with HMAC-SHA256 using server-only `AI_CACHE_HMAC_SECRET` and `AI_CACHE_KEY_VERSION`.
- Never expose the HMAC key or raw cache ID. Normal API diagnostics return counts and versions only.

## 24. Cache privacy and isolation

- Sensitive tokenisation occurs before key creation.
- Cached templates can contain canonical placeholders only, never original values or request-random placeholder IDs.
- On hit, map canonical placeholders to the current request's issued placeholders, validate them, rehydrate current values, then dispose of the mapping.
- Include profile/version now and reserve a tenant fingerprint field for future tenancy. Cross-profile and cross-request leakage tests are mandatory.
- No raw prompt, model response, raw MT message, key, account, name, reference, or placeholder map is persisted.

## 25. Cache invalidation

Reject a hit on expiry, corruption, schema failure, prompt/schema/model/profile/standards/knowledge/taxonomy/key-version mismatch, or lifecycle fingerprint mismatch. Provide a protected CLI clear command. A development endpoint is available only when `AI_CACHE_ADMIN_ENDPOINT_ENABLED=true` and an operator reset key is configured.

## 26. Token and cost telemetry

- Add interaction source `LIVE_API`, `CACHE`, `DETERMINISTIC`, `AI_UNAVAILABLE`.
- Persist current-call counts/tokens/cost/latency separately from original cached usage and avoided estimates.
- Extend content-free audit storage with namespace, cache hit/age, calls/usage avoided, versions, and operation.
- Summary queries calculate real aggregates over selected periods; cost avoided uses only provider-reported original cached cost and is explicitly labelled estimated.

## 27. UI changes

- Add navigation and pages for Knowledge Centre, Workflow Studio, Penalties, Corporate Actions, and AI Efficiency.
- Add reusable tag drawer and make supported fields clickable in Business/Tag/Raw views.
- Add compact collapsible AI Usage panel to guided and assistant surfaces; show source, now-usage, cached original usage, avoided usage, provider/model/version, and last real call without content.
- Add deterministic amendment/cancellation form, MT530 builder, penalty builder, and corporate lifecycle view.
- Keep novice UI concise and preserve the hackathon/no-transmission disclaimer.

## 28. API changes

Add the required knowledge, capability, AI usage/cache diagnostics, settlement command/cancellation, penalties, corporate actions, and generic workflow lifecycle endpoints. Existing paths and response fields remain backward compatible. New routes delegate to services/registries; no business logic goes into route functions.

## 29. Database migrations

- Add `workflow_id`, `workflow_module`, `message_role`, and optional `parent_reference` metadata without changing existing records.
- Add `ai_cache_entries` with opaque ID, namespace/versions/model/profile, validated JSON payload, original usage, expiry/access/hits, and timestamps.
- Add `ai_interaction_metrics` for source/current/avoided usage and safe outcomes.
- Extend or leave `ai_interpretation_audit` intact; never rewrite historical records.
- Use one additive Alembic migration and verify upgrade from empty and from revision `0002`.

## 30. Excel changes

- Add a `Workflow Type` discriminator while preserving the existing settlement template and endpoint.
- Provide module-specific template endpoints and route rows to module services.
- Add required MT530, penalty, and corporate-action columns from the prompt.
- Continue valid rows after invalid rows; escape formulas; include module/message/report metadata in ZIP output.
- Do not put raw AI telemetry content or secrets in workbooks.

## 31. Reporting changes

Expand JSON/Excel report payloads with workflow/module/lifecycle, applicable standards/profile/knowledge source, amendment/cancellation/penalty/corporate linkage, and AI current/avoided usage. Include concise knowledge IDs/source statuses rather than copyrighted source text. Mask sensitive values in AI telemetry sections.

## 32. Security controls

- Add `SecretStr` cache HMAC configuration, fail-safe cache disablement when absent, rotation/key-version guidance, TTL/row/L1 bounds, corruption eviction, schema validation, and content-free logging.
- Add cross-profile/request isolation and cache-poisoning/stampede tests.
- Sanitize MT568 and other narratives for allowed characters/length and render them escaped in React.
- Retain file/type/size/path/formula protections, OpenRouter ZDR/data-deny/parameter enforcement, prompt-injection boundaries, rate limits, request limits, and non-root Docker users.
- A cache hit remains untrusted and passes the same Pydantic, grounding, resolver, profile, and lifecycle checks.

## 33. Testing strategy

- Unit: knowledge loader/coverage/overlays/dependencies/search/PSET, registries/capabilities, amendment decisions, every new composer/parser/validator, cache key/privacy/TTL/invalidation/stampede/corruption, telemetry calculations.
- Golden: MT530, MT537, MT564–MT568 plus unchanged MT540–MT548.
- API: every required new endpoint and safe error contract.
- Integration: cancellation -> MT548, cancel/rebook immutability, penalty correlation, MT564 -> MT565 -> MT567 -> MT566 plus MT568.
- Excel/report: every workflow, invalid row continuation, formula injection.
- UI/Playwright: knowledge/PSET drawer, usage/cache panels, MT530, MT537, corporate lifecycle, existing flows.
- Security: HMAC/key/log/cache isolation, narrative sanitisation, arbitrary slug, secret scan.
- Full existing regression suite remains mandatory.

## 34. Evaluation strategy

- Add versioned synthetic fixtures for 40 knowledge questions, 30 amendments/cancellations, 25 penalties, 40 corporate actions, 20 injection, 20 ambiguity, and 20 cache equivalence cases.
- Use deterministic/offline contract evaluation for knowledge/rule authority and strict provider evaluation only for supported interpretation schemas.
- Add a two-pass exact-cache evaluation with an injected counting model client: pass one populates; pass two makes zero provider calls/tokens; concurrent requests make at most one call.
- Run live OpenRouter probe/current settlement evaluation when the ignored runtime key is present. New workflow live evaluation runs only after its strict schema is implemented; no thresholds will be fabricated.

## 35. Rollback strategy

- Keep new modules behind profile/capability enablement.
- `AI_CACHE_ENABLED=false` bypasses L1/persistent cache without affecting OpenRouter or deterministic forms.
- No existing composer output or endpoint is removed.
- Additive migration columns/tables leave old rows readable.
- Registry adapters wrap existing settlement behavior, allowing new dispatch to be disabled independently.
- Avoid destructive migrations and no source file deletion.

## 36. Expected files to create or modify

Expected new areas:

- `backend/app/knowledge/`, `backend/config/knowledge/`, knowledge tests.
- `backend/app/workflows/settlement_commands/`, `penalties/`, `corporate_actions/`, registry tests.
- `backend/app/agents/cache/`, call-decision/usage services and cache tests.
- Alembic revision `0003` for cache/workflow/interaction metadata.
- Golden outputs and synthetic evaluation data.
- Frontend components/pages for knowledge, workflow studio, penalties, corporate actions, and AI efficiency.
- New module-specific Excel and report helpers.
- Required guides and expansion report.

Expected modifications:

- domain enums/models, profiles, API router/contracts, generation/raw/lifecycle dispatch, agent service/config/telemetry/audit, persistence models/repositories, bulk/reporting, `.env.example`, Docker Compose, Makefile, navigation/styles, tests, and core documentation.

## 37. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Domain scope exceeds verified sources | Implement only field/rule subsets proven by official ISO/Swift sources; disable market/client-specific behaviors. |
| New central branching | Registry ownership and module-local dispatch. |
| Existing settlement regression | Preserve composer output; run old goldens continuously. |
| Cache leaks sensitive data | Tokenise/canonicalise before HMAC; template placeholders only; validate/rehydrate current mapping. |
| Cache poisoning/staleness | Strict result schema, version-rich key, expiry, corruption-as-miss, no failed-output caching. |
| Stampede or unbounded memory | Bounded L1, TTL, async in-flight coalescing and wait timeout. |
| Misleading cost savings | Use original provider-reported usage only; separate current and avoided; label estimates. |
| SQLite concurrency limits | Short transactions, unique cache ID, duplicate-insert handling; document distributed cache as future work. |
| No authentication for cache admin | CLI by default; dev endpoint disabled unless explicit key/config. |
| Corporate-action rule complexity | Small event/field subset and transparent exclusions; no generic event engine claim. |
| Large UI scope | Reuse field-table, form, timeline, report, and panel components; preserve working core. |

## 38. Acceptance criteria

- Every field emitted by all enabled composers has valid verified knowledge; PSET is clickable and displays message/profile-specific meaning, condition, related fields, source, and version without an AI call.
- Registry capability discovery accurately labels implemented/partial/disabled/planned/unsupported modules.
- Identical cacheable requests use one live/mock call first and zero calls/tokens second, with correct current placeholder rehydration and no cross-request/profile leakage.
- UI/API separate current usage from original cached and avoided usage.
- Cancellation preserves original data, prevents duplicates, and correlates MT548 accepted/rejected status.
- MT530 priority subset composes/parses/validates and core changes deterministically require cancel/rebook or return unsupported.
- MT537 source-backed penalty subset composes/parses/validates/correlates and never calculates/invents an amount.
- MT564/565/567/566/568 source-backed lifecycle composes/parses/validates/correlates for the controlled event subset.
- Module-specific Excel and report flows work with row continuation.
- Existing MT540–MT548/OpenRouter/raw/Excel/report/profile/lifecycle tests remain green.
- Ruff, formatting, mypy, frontend lint/typecheck/build, Playwright, clean migration, Docker, audits, secret scan, and whitespace checks are executed and honestly reported.

## 39. Implementation sequence

1. Create the initial expansion report/progress log.
2. Implement tag models/loader/config, current settlement coverage, APIs/UI, and tests.
3. Add cache configuration/models/migration/repository/L1/stampede/key/usage integration, APIs/UI, and tests.
4. Add workflow registry and adapt settlement dispatch/capabilities.
5. Add cancellation/amendment/MT530 subset, lifecycle/report/Excel/UI, and tests.
6. Add MT537 subset with knowledge/parser/Excel/report/UI/tests.
7. Add MT564–MT568 subset with lifecycle/knowledge/parser/Excel/report/UI/tests.
8. Expand evaluation datasets and two-pass cache evaluation.
9. Run full live/non-live verification, Docker/migrations/audits/scans/performance measurements.
10. Complete all guides and the final expansion report.

## Plan Self-Review

### Requirements covered

The plan covers all requested architecture, knowledge, provenance, PSET, settlement cancellation/amendment, MT530, penalties, corporate actions, future registry, LLM call avoidance, exact privacy-safe caching, HMAC keys, invalidation, stampede protection, current/avoided usage telemetry, UI/API, migrations, Excel/reporting, security, evaluation, performance measurement, rollback, documentation, and verification requirements.

### Requirements initially missed and corrected

- Added recursive lifecycle traversal so cancellation statuses and replacements can be grandchildren without disappearing from the original timeline.
- Added explicit separation of original cached usage from current zero-token cache-hit usage.
- Added a CLI-first cache-clear design because the repository has no authentication boundary.
- Added profile overlays that may only narrow verified base rules.
- Added a requirement that cached model output repeat all grounding, resolver, profile, and lifecycle validation.
- Added event code source constraints and excluded complex tax/fraction/market-claim rules.

### Remaining assumptions

- Official ISO 15022 public catalogue pages are the authoritative public source snapshot available to this repository; institution-specific behavior is absent.
- `DEMO_SR2026` remains an internal demo profile label. Knowledge records retain their reviewed official source reference and do not imply an official SR2026 certification.
- SQLite is acceptable for this prototype cache/audit layer; a shared store is a future production hardening item.
- No tenant identifier exists. The cache key reserves isolation metadata, and profile isolation is enforced now.

### Supported scope

- Existing MT540–MT548 subset unchanged.
- Tag knowledge for every field actually emitted by enabled deterministic composers.
- MT530 priority modification subset, settlement cancellation, and configured cancel/rebook decisions.
- MT537 penalties-sequence reporting subset for SEFP/LMFP.
- MT564–MT568 corporate-action lifecycle subset for controlled event types and fields.
- Exact context-aware AI cache and usage-efficiency reporting.

### Explicitly unsupported scope

- Universal MT530 amendment or unconfigured approve/cancel/reject market commands.
- Penalty calculation.
- All MT537 pending-transaction statement variants.
- Full corporate-action event, tax, beneficial-owner, fractions, market-claim, proxy, or movement coverage.
- All Category 5, all banking workflows, all ISO 15022 parsing, ISO 20022 messages, live Swift transmission, or certification.
- Approximate/vector semantic caching.

Self-review result: **PASS**. The implementation may proceed without an approval pause.
