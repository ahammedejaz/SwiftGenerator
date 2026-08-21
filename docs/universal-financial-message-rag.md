# Universal Financial Message Knowledge Engine (Phase 6)

Phase 6 turns the studio from a generator for 23 configured messages into a platform that
reads whatever authoritative material the operator drops into a local folder — SWIFT MT
Message Reference Guides, ISO 20022 XSDs, notes — indexes it for retrieval, compiles what
it can into message structures, and exposes every message it knows with a stated readiness.
Nothing configured changed. Everything new sits in a second, explicitly named lane.

This document is the architecture. The operator's guide to sources is
[knowledge-source-handling.md](knowledge-source-handling.md); the AI boundary is
[ai-assisted-authoring.md](ai-assisted-authoring.md); the measured state of every message
is in [generated/universal-message-readiness.md](generated/universal-message-readiness.md).

## 1. Two lanes, two release lanes

| Lane | What serves it | Rules | Where it shows |
|---|---|---|---|
| `CONFIGURED` | The reviewed `config/mt` manifest and `config/mx` packs — the 16 MT and 7 MX messages that existed before Phase 6 | Configured validation plus reviewed Rule Packs | Everywhere, unchanged |
| `KNOWLEDGE_PREVIEW` | Structure packs compiled from the local knowledge base (Prowide evidence, MRGs, XSDs) | None. `rulesStatus` is `NOT_ESTABLISHED`; candidate packs stay `REVIEW_REQUIRED`; activations are 0 | Only when a request names `lane=KNOWLEDGE_PREVIEW` |

The preview lane is never implicit. A request without a `lane` resolves in the configured
lane exactly as it did before. Every preview response carries a `provenance` block
(`LaneProvenance`: lane, release, releaseLane, structureSource, ruleStatus,
validationLevel, capabilityStatement, sourceProvenance) so a message can never be mistaken
for a configured one.

MT releases are a second axis. `RELEASE_LANES` records SR2024 and SR2025 as
`CURRENT_LIVE`, SR2026 and SR2027 as `FUTURE_TEST` (SR2026 goes live on 14 November
2026). The catalogue labels a future release "future release, test preview". A preview
request for an MT names its release; when it does not, the registry prefers a
generation-ready release, then the current-live one, and otherwise answers
`KNOWLEDGE_RELEASE_REQUIRED`.

**MT541 as the example.** The configured MT541 (public UHB review, current live) is the
authority for MT541 today. The knowledge base also holds MT541 SR2026, compiled from the
authorised SR2026 MRG corroborated by Prowide SR2025 evidence, which is `GENERATION_READY`
and listed as a separate future-release entry. The Prowide-only MT541 SR2025 structure also
exists (`STRUCTURE_AVAILABLE`, blocked by `QUALIFIER_EVIDENCE_MISSING`) but is *shadowed*:
a preview structure for the same message and current-live release as a configured pack is
not listed beside the configured entry, because the reviewed pack is the authority for
that release. The shadowed structure is still recorded in the readiness report and on
`GET /api/v1/knowledge/messages/MT541/status`. Sixteen such shadowed structures exist.

## 2. The pipeline

```
discover → identify → chunk → index (SQLite WAL + FTS5) → embed (policy-gated, cached)
        → compile structures (MT: Prowide + MRG; MX: XSD, six gates) → catalogue readiness
```

Everything runs from `python -m app.knowledge_base sync` (`make knowledge-sync`), is
incremental, and writes only under the ignored `build/knowledge/` tree.

### 2.1 Discover (`app/knowledge_base/discovery.py`)

`KNOWLEDGE_SOURCE_DIR` is a comma-separated list of roots, relative to the project root
(the operator's folder is `swiftKnowledgeBase`; the measured sync also used
`build/mx-real-sources`). Discovery is recursive, skips dot-files and never follows a
symlink. Supported suffixes: `.pdf .txt .md .markdown .html .htm .xsd .xml .zip`.
ZIPs are expanded into the source cache under safe rules (no `..` or absolute members,
no symlink members, nested ZIPs not expanded, `MAX_ZIP_RATIO = 100`, per-member and total
byte caps). Every file is hashed (SHA-256) before anything else happens.

### 2.2 Identify (`identify.py`)

Identity comes from content, never from the file name:

- An MRG is recognised from its cover page through the Phase 5B reader
  (`rule_engine.mt_mrg.document.identify`) → `SWIFT-MT-SR2026-MT541-MRG`.
- An XSD is recognised from its `targetNamespace` → `ISO20022-XSD-pacs.008.001.14`.
  A `DOCTYPE` is refused.
- A note or usage guide binds to the dominant MT or ISO identifier in its body, and only
  when it dominates: the leader must occur at least twice and at least twice as often as the
  runner-up, and across families (MT vs MX) the same 2:1 rule applies. Otherwise the source is
  `UNIDENTIFIED-<hash>` and is indexed for search without a message.
- A body containing `KNOWLEDGE-SOURCE-CLASSIFICATION: SYNTHETIC_FIXTURE` is a synthetic
  fixture; everything else is `OFFICIAL_SWIFT_MT_STANDARDS_MATERIAL`,
  `OPERATOR_SUPPLIED_XSD`, `OPERATOR_SUPPLIED_DOCUMENT` or `LICENSED_UNKNOWN`.

### 2.3 Chunk (`chunking.py`)

Segments never cross two messages and never cross a page. MRG text is classified into
sections with the same classifier the rule reader uses (`SCOPE`, `FORMAT_SPECIFICATION`,
`NETWORK_VALIDATED_RULE`, `USAGE_RULE`, `FIELD_SPECIFICATION`, `EXAMPLE`, …); a rule
heading (`C1`, `C2`) or a field heading starts a new segment. An XSD is summarised one
type per segment (`MESSAGE_DEFINITION`, `ELEMENT_DEFINITION`). Segment ids are stable
(`<source-id>#S0001`) and each segment carries a content hash, its page, its section and
the identifiers found in it for lexical search.

### 2.4 Index (`db.py`)

One SQLite database (`KNOWLEDGE_DB_PATH`, default `build/knowledge/knowledge.sqlite3`)
in WAL mode, per-call connections, one process-wide write lock. Tables: sources (keyed by
checksum), paths, segments, an FTS5 table with bm25 column weights, embeddings as float32
BLOBs, index runs, structures, the validated-sample cache, the presentation cache,
artefacts, and retrieval/AI metrics. `KNOWLEDGE_SCHEMA_VERSION = 1`.

### 2.5 Embed (`embeddings.py`, `policy.py`, `vector_store.py`)

The embedding adapter is provider-neutral (`EmbeddingProvider` protocol): Azure OpenAI
(v1 surface, `api-key` header, legacy deployment route on 404), any OpenAI-compatible
server, `fake` for tests, `disabled`. Requests are batched (`EMBEDDING_BATCH_SIZE`),
retried with backoff and `Retry-After`, and fail with named codes (`EMBEDDING_RATE_LIMITED`,
`EMBEDDING_AUTHENTICATION_FAILED`, `EMBEDDING_TIMEOUT`, `EMBEDDING_REQUEST_INVALID`,
`EMBEDDING_PROVIDER_UNAVAILABLE`).

Whether a segment may leave the machine is a policy decision, not a capability one.
`policy_for` allows a synthetic fixture unconditionally; every other classification needs
`KNOWLEDGE_EXTERNAL_EMBEDDING_ALLOWED=true` *and* its name in
`KNOWLEDGE_EXTERNAL_PROCESSING_CLASSIFICATIONS`. A configured key is never permission.
On the operator's folder all 23 sources are `EMBEDDING_BLOCKED`; lexical search works for
all of them.

The cache is keyed by `(segment_hash, provider, deployment, dimensions,
EMBEDDING_SCHEMA_VERSION)`: an unchanged segment is never embedded twice, identical
segments in two documents share one vector, and a change of deployment or dimensions
re-embeds rather than mixing vectors.

### 2.6 Compile structures (`structures/`)

**MT** (`mt_pack.py`): for every MT the Prowide evidence fixture knows (274 SR2025 models)
and every MRG in the knowledge base, the compiler builds an MT Structure Pack — sequences
(bracketed `16R/16S` or unbracketed with order-aware boundaries), field rows with
SWIFT-notation formats compiled to regular expressions (`swift_format.py`), qualifier
tables and codes from the MRG, choice groups as `parent/branch`, value-less markers such as
`:15A:`. Where both sources exist they are reconciled and the pack records
`SWIFT_MRG_<release>_PROWIDE_SR2025_CORROBORATED`. The pack then runs through the ordinary
engine: `LOAD → SAMPLE → VALIDATE → COMPOSE → PARSE → ROUND_TRIP`.

**MX** (`mx_pack.py`): each XSD goes through the existing `spec_engine.compile_schema` and
`validate_pack`, i.e. the six Phase 1 gates (registry load, sample, compose, source-XSD
validation, invalid variants rejected, round trip). The result is an ordinary `config/mx`
pack with a `KNOWLEDGE_PREVIEW` marker and the source XSD cached beside it, so runtime
validation uses the supplied schema.

Structure reuse is keyed by `PACK_COMPILER_VERSION` (`knowledge-pack-compiler/2`) and the
source checksums. A compiler change without a version bump reuses stale packs — which is
exactly what happened once during Phase 6 and why the version was bumped.

### 2.7 Readiness

| Readiness | Meaning | Catalogue |
|---|---|---|
| `KNOWLEDGE_ONLY` | Indexed for search; no loadable structure | Listed, not generatable, blockers shown |
| `STRUCTURE_AVAILABLE` | A pack loads but evidence is incomplete or a gate before COMPOSE failed | Listed, not generatable |
| `STRUCTURE_VERIFIED` | Sample, validate and compose pass; parse or round trip does not | Listed, not generatable |
| `GENERATION_READY` | All gates pass (MX: the source XSD accepted the sample) | Generatable in the preview lane |

Blocker codes are exact and travel with the entry: `QUALIFIER_EVIDENCE_MISSING` (a generic
field has no qualifier table — the guide is needed), `FORMAT_FIDELITY_PARTIAL` (a format
the notation compiler cannot render faithfully), `DUPLICATE_TAG_IN_SEQUENCE`,
`ROUND_TRIP_FAILED`, `STRUCTURE_SOURCE_MISSING`, `STRUCTURE_COMPILATION_FAILED`,
`STRUCTURE_SOURCE_CONFLICT`, `SEQUENCE_OMITTED_CODE_UNKNOWN:<path>` (an MRG sequence whose
block code could not be read), and the runtime refusal `MESSAGE_GENERATION_NOT_READY`.

Measured on the operator's folder plus the acquired pacs XSDs (293 structures): MT 201
`GENERATION_READY` (187 Prowide-only SR2025, 14 SR2026 MRG corroborated), 10
`STRUCTURE_VERIFIED`, 69 `STRUCTURE_AVAILABLE`, 5 `KNOWLEDGE_ONLY` (MT035, MT043, MT048,
MT049, MT096 — Prowide models with no block-4 fields); MX 8 `GENERATION_READY` (all eight
pacs schemas). A full compile takes about 20 s; an unchanged rescan reuses all 293 in 0.4 s.

## 3. Hybrid retrieval (`retrieval.py`)

`HybridRetriever.retrieve(query, query_type, filter, options)`:

1. **Filter first.** `RetrievalFilter` narrows by format, message type, one release (or an
   explicit list of releases for comparison — the only way to mix releases), sections and
   source ids. Filters are applied in SQL before ranking; a query for MT999 SR2026 cannot
   surface an SR2027 segment.
2. **Lexical.** The query is turned into a safe FTS5 expression (`fts_query`: every term
   quoted, identifiers such as `:22F::DBNM` split into searchable tokens, stop-word-only
   queries return nothing) and ranked by bm25 with column weights.
3. **Semantic.** When the provider is available and the segments were embedded, the query
   vector is compared by NumPy cosine over the stored float32 blobs. Hits below
   `min_semantic_score = 0.25` are dropped; a hit that is semantic-only needs
   `semantic_only_floor = 0.35`.
4. **Fuse.** Reciprocal rank fusion with k = 60, ties broken deterministically by segment
   id, then section diversity (`max_per_section`) and a context budget
   (`KNOWLEDGE_CONTEXT_CHARS`, default 6,000).
5. **Cite.** Every hit is a `Citation` — source id, document title, section, page, segment
   id, checksum prefix, method (`LEXICAL`, `SEMANTIC`, `HYBRID`). Snippet text is returned
   only when the source's policy allows it; otherwise the location alone is given.

When no embedding provider is configured, or the sources are blocked, retrieval states
`semanticAvailable: false` with a reason (`EMBEDDING_PROVIDER_UNAVAILABLE`,
`KNOWLEDGE_NOT_INDEXED`) and is lexical. Every query records a metric row.

The offline evaluation (`make knowledge-check`, part of `make check`) runs 11 synthetic
cases with fake embeddings: Recall@5 1.0, MRR 0.81, deterministic across runs. The live
evaluation (`make test-live-rag`) embeds the *synthetic* fixture corpus with the configured
deployment: Recall@5 1.0, MRR 0.875, message and release accuracy 1.0; 80 segments, 53
embedded in 5 batched requests, 27 cache hits, 3,832 tokens.

## 4. Incremental sync

`KnowledgeIndexer.sync` is hash-first: an unchanged file is never re-read. A changed file
replaces its segments and tombstones the previous checksum; a deleted file is tombstoned
and its segments and vectors removed; an unreadable file is recorded as `FAILED` with a
code and does not stop the run; an interrupted run is marked `INTERRUPTED` and the next run
continues. Readers are safe during a write (WAL, per-call connections). Each run updates
`corpus_version` — a hash that changes only when sources change, and which the sample cache
keys on per message — and writes `source-manifest.json` beside the database. `--reindex`
re-parses everything; `clean-cache` drops the source cache and packs, never a source.

## 5. Catalogue, UI and API

`GET /api/v1/catalogue` lists configured entries first, then every preview entry the
knowledge base knows, each with `lane`, `release`, `releaseLane`, `readiness`,
`readinessLabel`, `blockers`, `structureSource`, `rulesStatus`, `knowledgeSources`,
`aiSampleReady` and `automationReady`. Each format reports `messageCount` (both lanes)
and `configuredMessageCount`. Configured entries are exactly the 23 that existed before.

The existing endpoints accept `lane` and `release` — `spec`, `samples`, `validate`,
`generate`, `import`, `generate-from-excel`, `templates/{format}.xlsx` — and refuse a
preview message that is not generation-ready with `MESSAGE_GENERATION_NOT_READY`. New
endpoints live under `/api/v1/knowledge` (status, messages, per-message status, search,
telemetry, sources, sync) and `/api/v1/ai` (see
[ai-assisted-authoring.md](ai-assisted-authoring.md)).

In the UI the Create Message flow searches across both lanes, shows a readiness badge and
a release chip, and lists non-generatable entries with their blockers instead of hiding
them; the Excel page offers a template per generation-ready preview message; the
Knowledge Base page (`/knowledge-base`) shows status, sources, messages and search; Message
Intelligence gains "Ask"; Automation lists every new endpoint.

## 6. First run and startup

Without a database the API answers `GET /api/v1/knowledge/status` with
`indexed: false` and the message "Knowledge Base has not been indexed yet. Run `make
knowledge-sync`."; the catalogue shows the 23 configured messages and nothing else; no
screen fails. With `KNOWLEDGE_MODE=disabled` (the default) the knowledge endpoints say so
and the preview lane is empty.

```
Terminal 1:  make backend            Terminal 2:  make frontend
Index:       make knowledge-sync     (KNOWLEDGE_SOURCE_DIR=a,b make knowledge-sync)
One command: make knowledge-dev     # incremental sync, then the backend in local UAT mode
```

`KNOWLEDGE_MODE=local` serves the lane; `local_uat` additionally enables
`POST /api/v1/knowledge/sync` and the Sync button. The Playwright suite indexes the
synthetic fixtures into `build/knowledge-e2e/` in its global setup, so CI exercises every
screen without a licensed document or a key.

## 7. What "any message" means

A message is *generation-ready* when a structure compiled from evidence loaded, a
deterministic sample validated, composed, parsed back and re-composed identically — and,
for MX, the source XSD accepted the sample. That is structure-backed test generation. It
is not a claim that Network Validated Rules, usage rules, market practice or client rules
are evaluated (they are not, unless a reviewed Rule Pack is installed), not SWIFT
certification, and not proof of User Handbook completeness. A message without a loadable
structure is still *known*: searchable, citable, listed with the exact reason it cannot
generate. Adding a new MT guide or MX schema requires no code — see
[knowledge-source-handling.md](knowledge-source-handling.md) §6.

## 8. Generated reports (`make knowledge-reports-write`)

| Report | Contents |
|---|---|
| `generated/universal-message-readiness.md` | One row per message and release: source docs, structure source, readiness, gates passed, exact blockers; configured lane first; shadowed rows marked |
| `generated/knowledge-rag-coverage.md` | Sources, pages, segments, FTS and embedding counts, policy state per source, checksums — no source text |
| `generated/ai-sample-readiness.md` | For every generation-ready message: which sample types are offered and whether a validated AI sample is cached (`CACHE_READY`, `AI_READY`, `DETERMINISTIC_FALLBACK`, `N/A`) |

`make knowledge-reports-check` fails when the committed reports no longer match the
database. The reports contain counts, identifiers and checksum prefixes only.

## 9. Security and privacy rules

- Raw sources never enter Git: `swiftKnowledgeBase/`, `build/knowledge/`,
  `build/knowledge-*/` (database, vectors, source cache, packs) are ignored.
- Licensed text leaves the machine only under the double gate in §2.5; the default is
  blocked. "Embedding provider configured: Yes" is the most the UI ever says about the
  deployment — no key, no endpoint.
- Retrieval is evidence for a person or a prompt; it is never validation authority. The
  deterministic engine validates; a citation cannot make a message valid.
- The preview lane applies no rules and says so in every response.
- `make secret-scan` and `git diff --check` run in CI; normal CI spends no money and passes
  on a clean clone with no PDF, no XSD and no key.

## Where this lives

```
backend/app/knowledge_base/
  discovery.py  identify.py  chunking.py  db.py  embeddings.py  vector_store.py
  retrieval.py  index.py  policy.py  paths.py  preview.py  service.py  routes.py
  background.py  evaluation.py  reports.py  __main__.py
  structures/  swift_format.py  mrg.py  mt_loader.py  mt_pack.py  mx_pack.py
backend/app/studio/catalogue.py        universal catalogue, shadowing rule
backend/tests/knowledge_base/          71 tests; fixtures in backend/tests/fixtures/knowledge/
frontend/components/studio/KnowledgeBase.tsx, CreateMessage.tsx, ExcelStudio.tsx
docs/generated/universal-message-readiness.md, knowledge-rag-coverage.md, ai-sample-readiness.md
```

## Limitations

- Generation-ready means structure-backed; semantic rules are not established for any
  preview message and candidate rules are never activated.
- 69 MT structures stay `STRUCTURE_AVAILABLE` (mostly qualifier evidence missing without a
  guide, or a format the notation compiler renders only partially) and 10 stay
  `STRUCTURE_VERIFIED` (round trip fails); the readiness report names each blocker.
- Embedding is blocked by policy for every licensed source, so retrieval over the
  operator's folder is lexical. Semantic retrieval is proven on the synthetic corpus only.
- Release lanes are a recorded constant (`RELEASE_LANES`), not derived from a calendar.
- The preview MT parser uses the compiled structure; parsing a message that uses content
  outside that structure reports it as unconfigured, as it does in the configured lane.
- Identity for notes relies on identifier dominance; an ambiguous note is indexed
  unidentified rather than guessed.
