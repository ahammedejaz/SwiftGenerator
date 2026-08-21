# Universal runtime, AI observability, conversion and startup plan

Written before implementation on `feat/universal-message-runtime-and-ai-hardening` from
Phase 6 head `c468cfbaf4ae4a3418087f6be8c4a87384c919eb`; repository base main is
`b0ad6dd3bbe7835bec00489f6018bdcf0c8c9c14`. Measurements are from 2026-08-21.

## 1. Executive objective

Finish the existing universal financial-message foundation as an operational product:
make Create Message fast and reliable at 400+ entries, make every explicit AI/RAG action
observable without exposing content, add deterministic MT-to-MX business conversion, and
make a clean deterministic installation one command. Structure Packs remain structure
authority, reviewed Rule Packs remain validation authority, Mapping Packs become conversion
authority, and `StudioService` remains the only final composer.

## 2. Repository baseline

- Base main: `b0ad6dd`; Phase 6 prerequisite head: `c468cfb` (PR 18, exact-head CI green).
- Configured lane: 16 MT and 7 MX messages.
- Local index: 163 active sources, 16,617 segments, 425 structures, 434 catalogue entries
  (23 configured, 411 preview), and 13 cached samples.
- Readiness: MT 234 generation-ready, 12 structure-verified, 95 structure-available,
  76 knowledge-only; MX 8 generation-ready.
- `make check`: 1,546 passed, 22 skipped, 6 deselected; ruff, mypy strict, ESLint,
  TypeScript, coverage and all offline generated-report/evaluation gates pass.
- Build, audit, secret scan, Compose config and both Docker image builds pass.
- Baseline E2E cannot be treated as isolated while the operator's dev servers occupy ports
  3000/8000: Playwright reuses them, while global setup writes a different synthetic DB.
  The first test times out waiting for Create Message. Final verification will run isolated.

## 3. Current message catalogue architecture

`build_catalogue()` projects configured MT/MX registries and then synchronously merges every
knowledge-preview structure. A `CatalogueEntry` is already a summary, but the implementation
constructs the complete `MessageSpec` (all fields) merely to derive that summary. The default
API returns all lanes in one response and the browser blocks its first useful controls on it.

## 4. Current configured lane

The configured lane is committed YAML, starts without knowledge or AI, and remains the
default for every existing call. It is small and fast enough to render immediately. No
change may make it depend on the knowledge DB, preview registry, embedding service or LLM.

## 5. Current knowledge-preview lane

The preview lane loads local YAML packs and structure rows into separate runtime registries.
It has honest readiness and release isolation. It currently loads 352 YAML packs on the
first catalogue request, then constructs complete projections for generation-ready entries.

## 6. Current RAG architecture

SQLite FTS5 and filtered vectors feed deterministic reciprocal-rank fusion. Known
message/release filters are applied before scoring; context and per-section limits are
bounded; citations carry evidence IDs. RAG is explicit and never invoked by a deterministic
message endpoint.

## 7. Current AI architecture

`app/ai_authoring` computes deterministic seeds, optionally calls a structured-output
provider, validates canonical values, repairs within a bound, and composes only through the
ordinary engine. It records aggregate AI metrics and returns per-result usage, but does not
yet expose a complete correlated operation record.

## 8. Current embedding architecture

The provider abstraction supports Azure/OpenAI-compatible, fake and disabled providers.
Vectors are keyed by segment hash/provider/deployment/dimensions/schema. Policy is stored per
source. Embeddings occur during sync or explicit probes, not catalogue GETs.

## 9. Current caching architecture

There are validated sample and presentation caches in the knowledge DB and a separate HMAC
AI cache for the legacy agent layer. Retrieval results are not cached. Catalogue projections
are not cached. The browser does not deduplicate identical requests.

## 10. Current Create Message loading path

React mounts Create Message, runs one effect, and calls the default full catalogue. In Next
development strict mode the component remount causes two identical requests. Only after a
full response is parsed does the format choice render. There is no stale request guard,
single-flight client promise, ETag or configured-first render.

## 11. Performance root causes

Measured HTTP: cold 6.781 s, warm p50 about 2.76 s, observed warm range 2.73-2.99 s,
717,865 bytes. Browser: direct 5.94-6.02 s, refresh 3.99 s, repeat navigation 5.96 s,
two catalogue requests each time. Cold profiling: 9.49 s under cProfile, including 6.14 s
preview load and 5.50 s YAML construction. Warm profiling: 2.88 s, of which 2.10 s is an
O(n-squared) MX `by_path()` scan repeated 18,770 times. Another 242 sample-cache lookups
open 242 SQLite connections. The page performs no LLM or embedding call; the defect is
synchronous preview projection, repeated work and duplicate transport.

## 12. Universal MT objective

Preserve Phase 6's generic Prowide/MRG-to-Structure-Pack path. Improvements target generic
pack/runtime behavior only. No new message-specific Python or React branch is acceptable.

## 13. Universal MX objective

Preserve XSD-to-pack-to-runtime generation for every safely representable family. Index MX
paths once so field projection is linear. Unsupported XSD constructs remain named blockers.

## 14. Source requirements

MT structural preview needs pinned Prowide evidence and, where qualifiers or semantics need
it, an authorized MRG. MX needs an operator-supplied XSD. Mapping needs a separately
authorized mapping specification. A PDF alone is not assumed to define deterministic
structure, and model memory is not mapping authority.

## 15. Knowledge ingestion

Keep one recursive root, content-derived identity, hash-based incremental sync, safe ZIP/XSD
handling and tombstoning scoped to the complete configured roots. Add distribution manifests
without copying source content. Regression-test root-list tombstoning.

## 16. Structure compilation

Keep MT and MX compilers offline. Add any catalogue-summary metadata at compilation/sync
time when practical. Compiler changes bump `PACK_COMPILER_VERSION`; unknown evidence remains
unknown and failed gates remain blockers.

## 17. Capability states

Keep `KNOWLEDGE_ONLY`, `STRUCTURE_AVAILABLE`, `STRUCTURE_VERIFIED`, and
`GENERATION_READY`; present them as Knowledge Only, Test Preview, and Ready where space is
limited. Mapping readiness is independent and must not promote structure readiness.

## 18. Runtime Structure Pack loading

Configured registries load normally. Preview registries remain separate and lazy. The first
configured render must not wait for preview YAML. A process-wide cache and explicit
invalidation after sync will prevent duplicate pack loading/projection.

## 19. Dynamic MT generation

Continue resolving preview MT by message and explicit release, then call the injected MT
generator through `StudioService`. Prove diverse categories by configuration-driven tests
and existing local packs; do not install message-specific fixtures as product code.

## 20. Dynamic MX generation

Continue resolving preview MX by full version, composing through the MX generator and
validating against the supplied source XSD. Make registry path lookup indexed rather than a
linear scan.

## 21. Guided forms

The ordinary first screen remains simple. It renders configured formats immediately and
merges preview summaries when ready. Selected details remain lazy-loaded from the existing
spec endpoint.

## 22. Expert forms

Expert form generation continues to consume the same `MessageSpec`. No form metadata will
move into TypeScript and no conversion-only field editor will duplicate `FieldEditor`.

## 23. AI sample generation

Keep AI output limited to canonical values and deterministic factories for random-shaped
data. The result should carry request ID, provider/model, live calls, tokens, latency, RAG
evidence count and cache status.

## 24. RAG retrieval

Retain metadata-first hybrid retrieval and bounded context. Add a privacy-safe retrieval
cache only if measurement justifies it; catalogue performance does not justify touching RAG.

## 25. Prompt design

Retain fenced untrusted evidence and operation-specific instructions. Add a deterministic
query planner mapping operation classes to filters, sections, top-K and context budget;
the model never chooses unrestricted corpus access.

## 26. AI response schemas

Keep closed structured output. User-visible claims distinguish known, inferred, missing and
unsupported. Evidence IDs must refer to supplied chunks. Never store hidden reasoning.

## 27. Sample repair

Keep bounded repair using allowed canonical fields, current values, deterministic findings
and selected evidence only. Invalid final output remains failure and is never cached.

## 28. Knowledge cache

If a retrieval cache is added, key it by corpus version, query class, message, release,
normalized query, retriever version and policy. Store only the same content already allowed
in the local index; never log retrieved text.

## 29. AI cache

The sample-cache identity continues to include model, prompt/schema versions, corpus,
Structure Pack checksum, active Rule Packs and profile. Cache hits report zero live calls
and the calls/tokens avoided.

## 30. Embedding cache

Keep the current exact vector key and expose reuse/avoided-call counts. Policy changes need
reindexing because policy is resolved at parse time; document that restart/reindex boundary.

## 31. Usage telemetry

Add a bounded privacy-safe operation ledger with request ID, timestamp, operation,
message/release, provider/model, calls, tokens, cache hit, calls/tokens avoided, latency,
RAG mode/evidence/latency and outcome. Do not store prompts, message values, source excerpts,
credentials or endpoints. Retain aggregate counters and delete old rows by configured age.

## 32. Usage UI

Turn the existing AI Efficiency screen into an operational `AI & Knowledge Usage` page in
the studio shell. Show overview, RAG, embeddings, knowledge, caches and bounded recent
operations. Use compact work-focused tables and facts; no nested card layout.

## 33. RAG observability

Report query type, message/release filtering, lexical/semantic candidates, final evidence
count, mode, context size and latency. Recent rows expose IDs and metadata, never snippets.

## 34. AI observability

Report whether a model was called, provider/model, tokens, latency and cache. Deterministic
fallback must say no live model call rather than presenting itself as AI usage.

## 35. Cache observability

Show sample cache hits/misses and live calls/tokens avoided; show embedding reuse from the
last sync; report unavailable figures as unavailable rather than zero-cost claims.

## 36. Create Message performance

Add catalogue scope (`configured`, `preview`, `all`) without breaking the default API.
Render configured results first, then merge a background preview response. Add server LRU
projection caches, explicit invalidation, ETag/If-None-Match, client single-flight request
deduplication and stale cancellation. Index MX paths and batch sample-cache status reads.
Regression gates will assert no knowledge/AI/embedding call for the configured summary and
reasonable payload/latency based on the measured baseline.

## 37. Frontend catalogue architecture

One shared catalogue store owns in-flight and cached responses. Create Message subscribes to
configured data, then background enrichment; repeated navigation reuses it. Errors distinguish
backend unavailable from optional preview unavailable. Search remains local over the compact
summary and handles 400+ entries without rendering every row at once.

## 38. Background enrichment

Preview enrichment must be interruptible and non-blocking. A failed knowledge read leaves the
configured catalogue usable with a clear optional-status notice. Sync invalidation causes a
fresh preview request without remounting the whole wizard.

## 39. MT-to-MX mapping architecture

Add `app/mapping/` with closed models, loader, compiler/validator, business-semantic bag and
conversion service. Mapping Packs are separate configuration and are never inferred at
runtime. Source parsing produces canonical MT values; target values enter `StudioService`.

## 40. Business semantic model

Start with the concepts exercised by an actual synthetic proof: transaction reference,
trade/settlement dates, instrument identifier, quantity, settlement amount/currency,
place of settlement, delivering agent and receiving agent. This is a small vocabulary, not
a financial ontology.

## 41. Mapping Pack model

Versioned YAML declares exact source/target format, message, release/version, structure
checksums where known, review state, provenance, production eligibility and mappings of
`DIRECT`, `TRANSFORM`, `CONDITIONAL`, `ONE_TO_MANY`, `MANY_TO_ONE`, `NOT_REPRESENTED`, and
`TARGET_REQUIRED_MISSING`. The transform vocabulary is closed; no `eval`.

## 42. Mapping provenance

Every pack records source type/reference/checksum, author/reviewer state and limitations.
No repository evidence establishes a real authoritative MT-to-MX mapping, so product code
ships no production-eligible real mapping. A clearly synthetic preview pack/test fixture may
exercise the workflow without claiming equivalence.

## 43. Missing-data handling

After mapping, compare target values with the real target `MessageSpec`. Missing required
target values yield `NEEDS_INPUT`, with field IDs, business labels and questions. Nothing
financially material is fabricated.

## 44. AI-assisted conversion

AI may later suggest target candidates or phrase questions through the existing explicit AI
boundary. It cannot activate a candidate Mapping Pack or supply unsupported required values.
The first implementation keeps conversion deterministic and reports the evidence blocker.

## 45. Conversion validation

When inputs are complete, build a normal `GenerateRequest` for target MX and call
`StudioService.generate(persist=false)`. Its canonical, structural, rule, XML, XSD and header
layers are returned unchanged. Invalid target output is never reported as converted.

## 46. Conversion evidence

Return pack ID/version/review state/provenance, applied transforms, mapped/derived/missing
target fields, and source fields not represented. Meaningful loss is never silent.

## 47. API conversion

Add `GET /api/v1/messages/{source}/conversion-targets` and
`POST /api/v1/messages/convert`. Accept raw source text or canonical source fields, exact
lane/release, target identity, profile and user-supplied target values. Return status,
canonical target values, report, validation and XML only when ready.

## 48. UI conversion

Add a Convert Message action after MT generation/import and a studio route for paste/import.
Show source/target, mapping provenance, mapped/derived/missing/not-represented counts, a
preview table, missing target controls, then deterministic generation. With no reviewed
mapping, show that honest state and never offer a fake target.

## 49. Excel conversion possibility

Keep the engine input/output canonical so an Excel facade can be added without new mapping
logic. This engagement documents the contract but does not claim an Excel conversion UI
unless a real reviewed mapping is available.

## 50. Release/version handling

Mapping resolution is exact on source/target release/version and lane. Mismatch refuses.
Structure checksum mismatch refuses. No calendar-based automatic promotion and no fallback
to another version.

## 51. Knowledge redistribution policy

Audit found 164 local files including `.DS_Store` and 163 active standards sources, about
36 MB. Repository documentation identifies SWIFT MRGs as licensed and records no explicit
redistribution authorization for the raw XSD/PDF set. `UNKNOWN` defaults to not committed.

## 52. Git LFS decision

Do not use Git LFS for these sources: LFS changes storage, not redistribution rights. No raw
SWIFT/MyStandards PDF or operator XSD will be staged. Git LFS can be reconsidered only with
explicit organization/repository redistribution metadata.

## 53. Secure knowledge bootstrap fallback

Add `make knowledge-fetch` backed by a script that requires `KNOWLEDGE_BUNDLE_URL` or a
local organization artifact path, downloads/copies to a temporary file, verifies a declared
SHA-256, validates archive paths/size, and installs only into the ignored knowledge root.
No credentials are embedded; absent configuration returns clear instructions.

## 54. Fresh-clone setup

Add `make quickstart`: create `.env` from the example if absent, default optional AI and
knowledge to disabled, build/start Compose, migrate automatically, and wait on readiness.
Configured deterministic messages must work without keys or source files.

## 55. Docker

Make Compose defaults deterministic (`AI_PROVIDER=disabled`, optional knowledge disabled),
run migrations before serving, add a persistent knowledge volume and optional read-only
source mount profile, and distinguish liveness/readiness. Keep secrets host-provided only.

## 56. Environment

Keep backward-compatible aliases. Document which settings are startup-cached and require a
backend restart. Tests pin `KNOWLEDGE_MODE=disabled` unless explicitly opting in so operator
`.env` cannot mutate the suite.

## 57. Secrets

Never print or return keys, cookies, endpoints with credentials, bundle credentials or cache
HMAC material. Bootstrap accepts credentials through normal environment/transport tooling.
Run tracked-file secret scan and inspect all new manifests.

## 58. Security

Review mapping-pack path traversal, closed transforms, source/target authorization, XSD/ZIP
limits, telemetry content, prompt injection, SSRF in knowledge fetch, auth on new APIs and
tenant/content leakage. Downloader redirects/protocols and archive extraction fail closed.

## 59. Performance

Measure cold/warm and practical p50/p95 for configured, preview and all catalogue scopes;
payload sizes; first/refresh/repeat browser interaction. Target is evidence-relative: the
configured first screen should be subsecond locally and never wait for preview; warm merged
catalogue should remove the current multi-second O(n-squared) path.

## 60. Testing

Add unit/integration tests for catalogue scopes/cache/invalidation/ETag, duplicate-client
fetches, no AI on deterministic paths, telemetry privacy/retention, mapping types and refusal
conditions, bootstrap checksums/failures, health distinctions and quickstart defaults.
Extend Playwright for direct/refresh/repeat/large catalogue, optional-service states, usage
page and conversion preview.

## 61. UAT

Run real Chromium desktop and mobile. Exercise configured and preview MT/MX, AI sample and
cache indicator, usage page, intelligence RAG, conversion UI/API, Excel/import/download and
network/console/overflow checks. Capture timing evidence, not screenshots alone.

## 62. CI

Keep paid providers and private sources out. Synthetic knowledge, fake embeddings, scripted
AI and synthetic mapping fixtures prove all generic paths. Preserve every existing job and
run exact-head checks before merge.

## 63. Migration

Knowledge telemetry schema changes use idempotent SQLite initialization/migration and do not
invalidate source/index rows. Mapping configuration is additive. Existing `/catalogue`
default behavior and generation payloads stay compatible.

## 64. Rollback

Catalogue scope and caches are additive and can fall back to the current full call. The new
mapping router/config can be removed without changing composers. Telemetry rows are optional
metadata. Quickstart changes retain the existing `make dev` path.

## 65. Acceptance criteria

Configured Create Message is interactive without refresh and independent of optional
services; preview enrichment is reliable; no page GET calls AI/embeddings; AI results and a
dedicated usage page show accurate calls/RAG/tokens/cache/latency; deterministic conversion
reports loss/missing data and uses the target Structure Pack/composer; clean AI-less and
knowledge-less Docker startup works; all repository and clean-clone gates pass.

## 66. Honest limitations

Generation coverage is only what deterministic evidence proves. Preview structures do not
gain semantic completeness. Real-source embeddings reflect operator policy, not repository
permission. No authoritative MT-to-MX mapping evidence is present, so real conversion is
`BLOCKED_BY_MAPPING_EVIDENCE`; the engine and synthetic preview prove mechanics only. This
tool remains a testing platform, not SWIFT certification or a production gateway.

## Self-review and revised decisions

The plan was challenged against the engagement questions before implementation:

- A PDF is not treated as sufficient structure. MT still needs Prowide/MRG reconciliation;
  MX still needs XSD; mappings need their own authority.
- The LLM never serializes FIN/XML, validates XSD, evaluates rules or activates mappings.
- RAG explains and supplies evidence; it never becomes runtime validation authority.
- Conversion feeds the same parsers, canonical inputs and `StudioService`, not a second
  message engine.
- Prowide gaps remain blockers; an MRG may reconcile only what it explicitly establishes.
- The performance fix does not preload RAG, embed on GET, or hide latency with a spinner.
  It separates configured-first rendering from optional preview enrichment, then removes
  the measured repeated/O(n-squared) work.
- One MT may have multiple target mappings and every target may require absent values; the
  API therefore returns candidates and `NEEDS_INPUT`, not a single guessed XML document.
- Source/target releases and structure checksums are exact. No automated equivalence claim
  is made.
- Git LFS was rejected because permission is absent. A verified internal bundle bootstrap
  is the only lawful clone-and-run option for raw knowledge.
- Clean start is explicitly AI-less and knowledge-less; optional capability is visible but
  cannot make the configured studio unhealthy.
- The initial idea of a persistent catalogue projection generated only by knowledge sync
  was revised: existing databases would still make the first post-upgrade request slow.
  Configured-first render plus lazy preview works immediately, while server caching and
  indexed lookup make enrichment fast thereafter.
- The initial idea of shipping a real-looking MT541-to-sese.023 mapping was rejected. Only
  a conspicuously synthetic, non-production fixture may demonstrate conversion until an
  approved mapping source is supplied.

Implementation proceeds with these corrected decisions.
