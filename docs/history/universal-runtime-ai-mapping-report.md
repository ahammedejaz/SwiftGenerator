# Universal runtime, AI observability and mapping report

Point-in-time implementation and release report for the 21 August 2026 engagement.

## Executive summary

The branch keeps the source-backed universal runtime delivered by Phase 6 and hardens the
remaining product gaps: Create Message now starts from a 23-entry configured projection and
enriches 411 preview entries in the background; AI/RAG/embedding/cache work has a privacy-safe
correlated ledger and operational page; MT-to-MX conversion uses exact deterministic Mapping
Packs and ordinary `StudioService`; and a clone starts without AI or licensed knowledge through
one Docker command.

Base main SHA: `b0ad6dd3bbe7835bec00489f6018bdcf0c8c9c14`.
Prerequisite Phase 6 head: `c468cfbaf4ae4a3418087f6be8c4a87384c919eb`.
Feature branch: `feat/universal-message-runtime-and-ai-hardening`.
Final commit, PR, merge and post-merge run are recorded in the release section after completion.

## Repository and source audit

The implementation reuses the format-neutral catalogue, Structure Packs, Rule Packs,
Presentation Packs, dynamic MT/MX registries, `StudioService`, parsers, composers, Excel path,
hybrid retriever, provider abstraction and validated sample cache. It does not introduce a
second serializer or message-specific conversion branch.

The operator knowledge root contained 164 files: 155 PDFs, eight XSDs and `.DS_Store`, about
36 MB. The active index reports 163 sources, 16,617 segments/embeddings, 156 message
identities, 425 structures and 13 cached samples. No explicit repository redistribution grant
was present. Raw SWIFT/MyStandards committed: **NO**. Restricted/unknown raw sources committed:
**0**. Git LFS: **not used**, because it does not resolve licensing. Distribution mode:
**SECURE_BOOTSTRAP**.

## Performance baseline and result

The original complete catalogue had 434 entries and a 717,865-byte response. Cold latency was
6.78 seconds; warm latency was about 2.76 seconds. Profiling identified repeated preview YAML
construction, O(n-squared) MX path lookup, 242 SQLite connections for sample status, duplicate
development remount requests and an all-or-nothing startup payload. No embedding or model call
occurred during catalogue load.

The fix adds O(1) MX path indexing, batched sample status, cached catalogue construction and
serialization, ETags with explicit sync invalidation, a configured-only API projection,
browser single-flight and a five-minute tab cache. Create Message renders configured messages
first and treats background preview failure separately from backend failure.

Measured after the fix in a fresh process:

| Path | First | p50 | p95/warm | Bytes |
|---|---:|---:|---:|---:|
| configured projection | 77.8 ms | 0.67 ms | 1.05 ms | 34,395 |
| complete catalogue | 4.07 s | 0.74 ms | about 1 ms warm | 717,865 |

The first browser interaction measured 539 ms locally. The isolated Playwright regression
delays background preview enrichment by two seconds and proves configured choices remain
interactive, refresh/remounts do not fan out requests, and repeat navigation reuses the cache.

## Universal MT and MX runtime

The local catalogue contains 434 honest entries: 419 MT and 15 MX. It reports 265
`GENERATION_READY`, 12 `STRUCTURE_VERIFIED`, 79 `STRUCTURE_AVAILABLE` and 78
`KNOWLEDGE_ONLY` entries. Configured: 16 MT and seven MX. Knowledge-preview: 403 MT and eight
MX. Generatable: 250 MT (16 configured plus 234 preview) and all 15 MX (seven configured plus
eight preview).

Dynamic MT remains generic from Prowide/MRG structural IR through runtime Structure Packs,
forms, canonical inputs, deterministic FIN, import/round trip, Excel, JSON API and AI samples.
Dynamic MX remains generic from operator XSD through the existing compiler, runtime registry,
forms, canonical inputs, deterministic XML, source-XSD validation, import/round trip, Excel and
JSON API. Unknown structure stays unknown; 76 MT knowledge-only entries and 95 structure-
available entries are not presented as supported generation.

## RAG, LLM, embeddings and cache

Retrieval remains deterministically planned by query class, then message/release filtered
before lexical/semantic ranking. Strict AI schemas return canonical values and evidence IDs;
the model never serializes FIN/XML or evaluates rules. Deterministic factories continue to own
references, dates and identifier-shaped data. Failed proposals receive bounded structured
repair and never return invalid output as success.

The indexed operator snapshot uses the configured Azure OpenAI LLM/embedding adapters without
exposing endpoints or secrets. Snapshot counters at verification time: 63 AI operations, 48
live calls, 164,245 input tokens, 13,235 output tokens, 12 cache hits, 13 calls and 73,154
tokens avoided; 61 retrievals (59 lexical, two hybrid), 10.9 average evidence segments and
122 ms average retrieval latency. The last incremental sync reused all 16,617 embeddings with
zero embedding requests. The offline synthetic evaluation passed 11/11 cases with Recall@5
1.0, MRR 0.8125, citation/message/release accuracy 1.0 and deterministic ordering.

## Telemetry and usage UI

Every explicitly AI-assisted authoring operation stores content-free metadata keyed by request
ID: operation/message/release, model/calls/tokens/latency/cache, RAG mode/filter/candidates/
evidence/latency/corpus, embedding counters and outcome. Cleanup is bounded to 30 days and the
recent API response to 50 rows by default. The additive SQLite migration works against an old
index. Prompts, values, source text, excerpts, private endpoints, credentials and hidden
reasoning are excluded.

`/ai-efficiency` now renders **AI & Knowledge Usage** with Overview, RAG, Embeddings,
Knowledge, Cache and Recent Operations. Results distinguish live AI, validated cache reuse and
deterministic fallback, with expandable provider/model, evidence, token, latency and cache data.

## Mapping and conversion

The generic Mapping Pack contract has exact source/target identity, closed mapping kinds,
closed transforms, a deliberately small business-semantic vocabulary, evidence provenance,
review state, production eligibility and limitations. Runtime validation pins evidence plus
source/target Structure Pack checksums and refuses mismatch. `CANDIDATE` packs cannot execute;
only `REVIEWED` packs may be production eligible. There is no `eval` and no model serializer.

`GET /api/v1/messages/{source}/conversion-targets`, `POST /api/v1/messages/convert` and
`/convert` support canonical or raw MT input, exact target discovery, mapped/derived/user-
supplied/missing/not-represented reporting, missing-data questions and canonical preview. When
complete, conversion calls ordinary non-persisting MX generation and returns XML only after
deterministic validation. Create Message can transfer a generated MT to Convert.

No authorized real mapping evidence was present. The sole MT541 to `sese.023.001.11` proof is
`SYNTHETIC_TEST_ONLY`, disabled unless `allowSyntheticPreview` is explicit. It produces valid
deterministic XML while reporting eight mapped, seven derived, one lost and zero missing values
for the complete fixture. Real source-backed conversion remains
`BLOCKED_BY_MAPPING_EVIDENCE`; no business equivalence is claimed.

## Quickstart, health and security

`make quickstart` checks Docker Compose and OpenSSL, creates `.env` only when absent, generates
development session/cache/encryption secrets, builds images, runs Alembic, waits for readiness
and optionally fetches/syncs an approved bundle. AI, embeddings and knowledge default off while
the 23 configured messages remain available. Liveness is process-only; readiness requires the
database and configured registries and reports knowledge/AI/embeddings as optional states.

`make knowledge-fetch` requires one HTTPS or regular non-symlink local source and an approved
SHA-256. HTTPS downloads resume in an ignored checksum-keyed cache. Extraction rejects path
traversal, absolute/drive paths, links, devices, duplicate writes and oversized archives.
Focused tests cover checksum failure, missing configuration, cache reuse, HTTPS enforcement and
archive traversal. Dependency audits found zero known Python or npm production vulnerabilities;
the tracked-file secret scan found no secret-shaped values.

## Verification and UAT

- `make check`: 1,560 passed, 22 skipped, six live-provider tests deselected; ruff, mypy strict
  (231 files), ESLint, TypeScript, coverage, XSD, demo, Prowide, rule/MRG and RAG gates green.
- Playwright: 98/98 green against isolated fresh backend/frontend processes on 8011/3011.
- Build: Next production build green with 25 routes, including `/convert` and `/ai-efficiency`.
- Audit: pip-audit and `npm audit --omit=dev` report zero vulnerabilities.
- Docker: isolated project on 8021/3021 built both images, migrated an empty volume, reached
  healthy/ready, served Create and Convert, reported optional providers disabled, and tore down.
- Browser UAT: Create/search/configured+preview MT/configured+dynamic MX/AI sample/scenario/
  usage/knowledge/intelligence/conversion/Excel/API/import/download passed; desktop and phone
  widths had no horizontal overflow or console failures.

The clean-clone quickstart, exact feature-head CI, normal merge and post-merge CI evidence are
recorded below once those release gates complete.

## Known blockers

- Real MT-to-MX conversion needs an approved, versioned mapping authority and reviewer.
- Generation readiness remains limited by source structure: knowledge-only and partial MT
  structures cannot safely generate; configured MX subsets do not claim complete standard or
  market-practice validation.
- Licensed standards remain external to Git. A clone without approved bundle access starts in
  configured deterministic mode by design.

## Release record

- Final feature SHA: `PENDING`
- Pull request: `PENDING`
- Exact feature-head CI: `PENDING`
- Squash merge SHA: `PENDING`
- Post-merge main CI: `PENDING`
- Clean-clone quickstart: `PENDING`
