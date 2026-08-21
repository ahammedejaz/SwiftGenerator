# Repository context for AI agents

Orientation document for an AI tool working on this repository. Dense and factual by
design. Human-facing docs are [../README.md](../README.md), [ARCHITECTURE.md](ARCHITECTURE.md),
[CONTRIBUTING.md](CONTRIBUTING.md) and [the docs index](README.md).

---

## 1. What this repository is

**Financial Message Studio** — generates valid SWIFT MT (ISO 15022) and MX (ISO 20022)
financial messages for **testing**. Two audiences, one code path:

- A **manual tester** with no SWIFT knowledge uses a six-step browser wizard.
- An **automation tester** POSTs JSON or uploads a spreadsheet.

The browser UI calls exactly the same `/api/v1` endpoints automation calls. There is no
UI-only capability.

Not a production messaging gateway. Not a conformance authority. No SWIFT certification.

**Stack:** FastAPI + SQLAlchemy + Alembic (Python 3.13) · Next.js 16 + React 19 +
Tailwind 4 (Node 22) · SQLite locally, PostgreSQL in production.

**Repo:** `github.com/ahammedejaz/SwiftGenerator` (private) · default branch `main`.

---

## 2. Current state

23 message types generate end to end:

| Format | Types |
|---|---|
| MT | MT530, MT537, MT540–MT548, MT564–MT568 (16) |
| MX | sese.023.001.11, sese.024.001.13, sese.025.001.12 (3) |
| MX lifecycle | sese.020.001.08, sese.027.001.08, sese.030.001.10, sese.031.001.09 (4) |

**Both formats import.** `POST /api/v1/messages/import` reads an MT FIN message, an MT text
block or an ISO 20022 document back into canonical values and regenerates it through the
ordinary generation path. The format and the message are identified from the message itself
— the ISO 20022 namespace, or FIN Block 2 — never from a caller-supplied label.
`Compose(Parse(Compose(v))) == Compose(v)` is asserted for every sample of every configured
message in both formats, and for all 17 golden MT fixtures. The older
`/api/messages/validate-raw` still exists and still serves the Advanced screens.

The four lifecycle specifications are flagged **UNVERIFIED** in their own `limitations`:
version, root element name and element set were not reconciled against an authoritative ISO
20022 message-definition report. See §14.

After importing, **every difference between the message that went in and the one that came
out is attributed**: a value the caller edited, normalisation, content outside the configured
subset, or something interface- or network-generated that the studio deliberately never
writes. `POST /api/v1/messages/diff` returns it, and every `import` response carries the
same comparison. Deterministic — `difflib` and string comparison, no model.

`make coverage` reports **all 23 messages in both formats**, and every figure in it is
measured from the real component rather than read from a flag. `GET /api/v1/coverage` serves
the same data; `GET /api/v1/sources` reports which authoritative artifacts are present.

**The specification engine exists (Phases 0–1).** Message discovery is
specification-driven: the MT manifest — not a Python enum — decides which MT messages
exist, and `app/spec_engine` compiles an ISO 20022 XSD into an ordinary `config/mx` pack
(`make spec-compile`), gated by source-schema validation and a round trip. Every message
carries derived **capability dimensions** (structure / businessRules / marketPractice /
clientProfile / externalValidation) beside the legacy `PARTIAL`. No compiled pack ships
in the catalogue; the synthetic fixture lives in `tests/fixtures/xsd/`. See
[specification-engine.md](specification-engine.md) and
[specification-engine-plan.md](specification-engine-plan.md).

**The rule engine exists (Phase 2).** Business rules are versioned configuration in
`backend/config/rules/`, not Python: a closed declarative DSL, format-neutral field
references resolved through the existing registries, and three layers — base, market
practice, client — that may narrow one another but never widen or silently contradict.
An offline pipeline turns a source document into *candidates* (two isolated model passes,
deterministic diff, adversarial refuter, then the same compiler that guards an installed
pack); only a reviewed, source-controlled pack ever loads. Two clearly synthetic overlays
ship for `sese.023` under the `DEMO_MARKET_CLIENT_V1` profile; no base-business pack ships
for any real message. See [specification-rule-engine.md](specification-rule-engine.md),
[rule-pack-format.md](rule-pack-format.md) and
[rule-source-handling.md](rule-source-handling.md).

**The MT Prowide structure importer exists (Phase 4).** It is an offline
`app/spec_engine` tool that uses pinned Prowide Core artifacts as structural evidence for
all MT source models discovered in the artifact. The committed fixture records 274
Prowide source model classes across categories 0-9, 1,042 sequences, 990 fieldsets, 9,710
field groups and 620 global field classes for `SRU2025-10.3.18` (`SR2025`). Two hundred
fifty-eight source models are inert candidates and zero are activated. It is not a runtime
dependency, not Swift certification and not a conformance claim. See
[mt-structure-importer.md](mt-structure-importer.md),
[mt-source-versioning.md](mt-source-versioning.md) and
[generated/mt-importer-compatibility.md](generated/mt-importer-compatibility.md).

**The MT semantic-rule ingestion foundation exists (Phase 5A).** It is an offline
`app/rule_engine` path with MT source metadata, source privacy gating, canonical
Prowide-derived structural-reference validation, an MT synthetic extraction corpus and
readiness reports. It installs zero real MT Rule Packs, activates zero candidate messages
and leaves runtime MT structures untouched. See
[mt-semantic-rule-ingestion.md](mt-semantic-rule-ingestion.md),
[mt-semantic-source-handling.md](mt-semantic-source-handling.md),
[generated/mt-semantic-readiness.md](generated/mt-semantic-readiness.md) and
[generated/mt-semantic-source-readiness.md](generated/mt-semantic-source-readiness.md).

**Real SWIFT Message Reference Guides are read as evidence (Phase 5B).**
`app/rule_engine/mt_mrg/` reads an authorised SWIFT MyStandards MT Message Reference Guide
deterministically — identity, sections, Format Specifications, qualifier tables, Network
Validated Rules — and translates the rules it recognises into candidate expressions
compiled by the ordinary compiler. The two guides read are **SR2026**, which goes live on
14 November 2026 and is therefore a **future-test** lane, never current-live. MT540 states
18 Network Validated Rules and MT541 states 20. After Phase 5C, occurrence-scoped
candidate expressions are represented through the generic `rule-dsl/2`
`forEachOccurrence` primitive: 23 translate exactly, 15 more weakly than stated, and 0 are
unsupported. Every candidate is `REVIEW_REQUIRED`, none is written to
`config/rules/`, and runtime activations are **0**. The documents are licensed and live in
an ignored drop directory; what is committed is derived metadata
(`backend/tests/fixtures/mt_mrg/`), which is what lets `make check` verify the pipeline on
a machine that has never held one. See
[mt-real-semantic-phase-05b.md](mt-real-semantic-phase-05b.md),
[rule-occurrence-semantics.md](rule-occurrence-semantics.md),
[generated/mt-sr2026-semantic-readiness.md](generated/mt-sr2026-semantic-readiness.md) and
the reviewer packages in `docs/generated/mt54*-sr2026-rule-review.md`.

**The universal knowledge base, hybrid RAG and AI authoring exist (Phase 6 — branch
`feat/phase-6-universal-rag-ai-authoring`, not merged).** `app/knowledge_base/` discovers
authorised sources the operator drops into the ignored `swiftKnowledgeBase/` directory (and
`build/mx-real-sources`), identifies each from its content, segments it into a local SQLite
index with FTS5, embeds it only where policy allows, retrieves with lexical + semantic
reciprocal-rank fusion, and compiles **local Structure Packs** from deterministic evidence —
MT from the pinned Prowide fixture reconciled with SWIFT MRG Format Specifications, MX from
operator-supplied XSDs through the existing `spec_engine` compiler. Those packs serve a
separate, explicit **`KNOWLEDGE_PREVIEW` lane**; the configured lane is unchanged.
`app/ai_authoring/` lets a model identify a message, prepare canonical values, draft
MINIMAL / TYPICAL / FULL samples and test data, and phrase explanations with citations; the
deterministic validator and composer decide everything. Measured on the operator's folder on
2026-08-20: 23 sources, 4,663 segments, 293 message/release structures — **201 MT and 8 MX
`GENERATION_READY`** in the preview lane, 10 `STRUCTURE_VERIFIED`, 69 `STRUCTURE_AVAILABLE`,
5 `KNOWLEDGE_ONLY`; embeddings of every real source `BLOCKED` by policy, so retrieval on the
real corpus is lexical. See §10a, [universal-financial-message-rag.md](universal-financial-message-rag.md),
[knowledge-source-handling.md](knowledge-source-handling.md),
[ai-assisted-authoring.md](ai-assisted-authoring.md), [automation-api.md](automation-api.md)
and the generated [universal-message-readiness.md](generated/universal-message-readiness.md),
[knowledge-rag-coverage.md](generated/knowledge-rag-coverage.md) and
[ai-sample-readiness.md](generated/ai-sample-readiness.md).

**Verification status (measured 2026-08-21 on the Phase 6 branch final head):**

```
1546 backend tests passed, 22 skipped, 6 deselected (live marker)   ruff: clean   mypy --strict: clean (227 files)
  96 browser tests (Playwright)   eslint: clean   tsc --noEmit: clean   next build: clean
make check green (incl. knowledge-check: 11/11 synthetic retrieval cases, Recall@5 1.0, MRR 0.81)
live proofs, never in CI: probe-embeddings PASS (3072 dims) · test-live-rag Recall@5 1.0 / MRR 0.875
                          test-live-ai-sample 5 passed (second call: cache HIT, 0 model calls)
CI: six jobs on every PR and every push to main    see §11
docker: both images build, compose config valid
secret scan: clean; no raw source and no knowledge database is tracked
clean clone, no .env, no keys: install -> migrate -> check -> e2e, and docker, all green
```

Before Phase 6 (`main` at `b0ad6dd`): 1446 backend tests, 80 browser tests, mypy over 195 files.

---

## 3. The mental model — read this before changing anything

**A message is a specification plus values.**

```
SPECIFICATION (YAML, backend/config/)  +  VALUES (typed, uploaded, or POSTed)
                          │
                      COMPOSER
                          │
                    THE MESSAGE
```

Consequences that shape every decision in the codebase:

- **Most changes are YAML edits, not code.** Adding a field, a message, or a client profile
  touches `backend/config/` only. Check whether the change belongs there before writing code.
- **The UI, the JSON API and the Excel importer cannot disagree**, because all three read
  the same specification and call the same composer.
- **MT and MX never share a rendering path.** They meet only at the dispatching service and
  at the result object. MT code cannot emit XML; MX code cannot emit FIN blocks.

---

## 4. Request flow

```
Browser · JSON API · Excel upload
              │
        StudioService                       app/studio/service.py
              │
     ┌────────┴────────┐
  MT branch         MX branch
  resolve           resolve                 address → specification row
  validate          validate                6 layers (MT) / 9 layers (MX)
  compose           compose                 write in specification order
  FIN envelope      AppHdr + wrapper
                    XSD (libxml2)
     └────────┬────────┘
        GenerateResult                      message · validation · checksum · origins
              │                             + lane · provenance (Phase 6)
        studio_messages table
```

Phase 6 changes one thing in this picture: *resolve* reads the configured registries by
default and the `KNOWLEDGE_PREVIEW` registries only when the request names that lane (and,
for MT, a release). Nothing else in the flow knows which lane it is serving, and no step
in it calls a model or the knowledge base. The AI operations (`/api/v1/ai/*`) sit *before*
this flow — they produce values that then enter it like any other caller's.

---

## 5. File map

### Backend — the studio layer (new, ~5,800 LOC)

```
backend/app/studio/
  models.py         request/response contracts shared by every entry point
  catalogue.py      "what can I generate?" + format-neutral specification projection
  service.py        dispatch, layer assembly, output selection   ← the hub
  routes.py         /api/v1 (18 endpoints; Phase 6 added lane/release to catalogue, spec,
                    samples, validate, generate, import, Excel routes)
  security.py       X-API-Key service authentication
  samples.py        MINIMAL / TYPICAL / FULL sample generation
  excel.py          template generation + workbook parsing
  intelligence.py   deterministic search index over MT tags and MX elements
  store.py          recent-messages persistence
  coverage.py       unified MT + MX coverage, measured; renders docs/generated/
  demo_pack.py      builds demo/ from the production composer; gated by make check
  diff.py           original vs regenerated, with every difference attributed
  sources.py        authoritative-source readiness: drop points and what is present
  mt/fin.py         FIN envelope — the "nothing is invented" rules live here
  mt/generator.py   MT address resolution, validation, rendering
                    plan_sequences() is the whole MT occurrence model, shared with the parser
  mt/parser.py      MT import — the exact inverse of the composer and the envelope
  mx/models.py      declarative ISO 20022 structure model
  mx/registry.py    loads + flattens MX specifications
  mx/generator.py   MX composition, validation, AppHdr
  mx/parser.py      MX import — the exact inverse of the composer
  mx/xsd.py         schema derivation + libxml2 validation
```

### Backend — the knowledge base and AI authoring (Phase 6, ~10,000 LOC)

```
backend/app/knowledge_base/
  __init__.py       KNOWLEDGE_SCHEMA_VERSION, CHUNKER_VERSION, EMBEDDING_SCHEMA_VERSION,
                    PACK_COMPILER_VERSION — bump the last one whenever a compiler changes
  __main__.py       CLI: sync, status, reports, evaluate-rag, probe-embeddings, clean-cache
  discovery.py      walk the roots safely: no symlinks, ZIP limits, never writes a source
  identify.py       identity and classification from CONTENT, never from the filename
  chunking.py       stable segmentation with section classification and page markers
  db.py             the SQLite schema: source, path, segment, FTS5, embedding, run, structure
  index.py          incremental sync: checksum → parse → segment → FTS → embed → compile
  embeddings.py     provider-neutral embedding adapter (azure_openai / openai_compatible / fake)
  vector_store.py   NumPy cosine over float32 BLOBs; filtered by format/message/release
  retrieval.py      BM25 + cosine → reciprocal rank fusion (k=60), section diversity, budget
  policy.py         may this source's text leave the machine? two gates, default blocked
  service.py        the ONE runtime door: status, search, caches, telemetry; NOT_INDEXED-safe
  preview.py        the KNOWLEDGE_PREVIEW lane: packs loaded into separate registry instances
  reports.py        docs/generated/{universal-message-readiness,knowledge-rag-coverage,
                    ai-sample-readiness}.md
  evaluation.py     the offline retrieval evaluation behind make knowledge-check
  routes.py         /api/v1/knowledge (7 endpoints)
  structures/
    mt_pack.py      Prowide evidence + MRG Format Specifications → MT pack + gates + readiness
    mt_loader.py    MT pack → MessageSpecification (the runtime type the composer reads)
    mrg.py          Format Specification tables read from an MRG's page-marked text
    mx_pack.py      operator XSD → MX pack via spec_engine.compile_schema + validate_pack
    swift_format.py SWIFT field-format patterns → synthetic values for the sample gate
backend/app/ai_authoring/
  service.py        identify, prepare, samples, test data, presentation, ask, releases/compare
  provider.py       structured-completion provider (organisation endpoint / OpenRouter / scripted)
  prompts.py        prompt templates; the RAG context boundary and injection guards
  schemas.py        closed JSON schemas every model answer must satisfy
  routes.py         /api/v1/ai (7 endpoints)
```

### Backend — reused unchanged (predates the studio, already tested)

```
app/specifications/registry.py   MT specification registry (string-keyed; manifest-driven)
app/specifications/manifest.py   the manifest index — the single authority for which MT messages exist
app/spec_engine/                 XSD -> specification-pack compiler (offline CLI; never in the request path)
app/spec_engine/mt_prowide/      pinned Prowide MT extractor; build-time only
app/rule_engine/mt_semantics.py  MT semantic source readiness + canonical reference checks
app/rule_engine/mt_mrg/          reads a SWIFT Message Reference Guide as evidence; offline only
app/studio/capability.py         derived capability dimensions + plain-language summary
app/studio/registry.py           format-neutral message-definition projection (catalogue metadata only)
app/knowledge/loader.py          MT knowledge base
app/knowledge/code_lists.py      shared controlled code lists, with labels
app/knowledge/presentation.py    which control a field deserves, derived once from the tag
app/domain/identifiers.py        ISIN / BIC normalisation and verification, deterministic
app/authoring/composer.py        Block 4 composer          ← reused, do not fork
app/profiles/loader.py           client profiles
app/domain/ app/composers/ app/workflows/   original scenario API, serves Advanced screens
app/agents/                      AI layer (optional, off by default)
```

### Configuration — the actual source of truth

```
backend/config/README.md               what each directory is, and its override setting
backend/config/knowledge/*.yaml        MT: per-tag meaning, format, examples, mistakes
backend/config/knowledge/code_lists.yaml   controlled codes + labels, shared by MT and MX
backend/config/specifications/*.yaml   MT: sequences and row order per message
backend/config/mt_prowide_*.yaml       MT: pinned Prowide structural-evidence locks
backend/config/mx/*.yaml               MX: complete nested element tree, one per message
backend/config/mx/xsd/official/        drop licensed .xsd files here; see its README
backend/config/profiles/*.yaml         client profiles: currencies, rules, envelope values
backend/config/rule_sources/           business-rule sources; raw licensed drops ignored
swiftKnowledgeBase/                    operator's authorised PDFs/XSDs/ZIPs — ignored, never committed
build/knowledge/                       knowledge.sqlite3, packs/, source-cache/ — derived, ignored
```

Each of those four locations has a setting that redirects it — `MT_SPECIFICATION_MANIFEST`,
`MX_SPECIFICATION_DIRECTORY`, `MX_OFFICIAL_XSD_DIRECTORY`, `CLIENT_PROFILE_DIRECTORY` — so a
licensed artifact is a drop-in, not a code change. Unset means "the configuration committed
here", which is what keeps a clean clone working with no environment.
[authoritative-sources.md](authoritative-sources.md) is the procedure.

### Frontend (new, ~4,800 LOC)

```
frontend/components/studio/
  Chrome.tsx           app shell, 6-item nav
  CreateMessage.tsx    the six-step wizard
  FieldEditor.tsx      progressive disclosure + inline field explanations
  FieldControl.tsx     one control per inputKind — never inferred in the browser
  ProofSheet.tsx       the generated message — dark, line-numbered, annotated
  MessageDiff.tsx      original vs regenerated, and why each line differs
  ValidationPanel.tsx  plain-English validation
  ExcelStudio.tsx  Intelligence.tsx  ValidateStudio.tsx  Automation.tsx  RecentMessages.tsx
  KnowledgeBase.tsx    sources, readiness, search and sync for the local knowledge base
  Icon.tsx  ui.tsx     authored SVG icons + the component vocabulary
frontend/components/ai/KnowledgeTelemetryPanel.tsx   embedding / retrieval / sample-cache telemetry
frontend/lib/identifiers.ts    ISIN / BIC checks for live feedback; the server still decides
frontend/lib/studio-types.ts   TypeScript mirror of the API contract
frontend/lib/studio-api.ts     typed client — the ONLY place fetch() is called
frontend/app/{,excel,intelligence,validate,automation,recent,advanced}/page.tsx
frontend/app/knowledge-base/page.tsx   reached from the Advanced page, not the six-item nav
```

Phase 6 touched `CreateMessage.tsx` (catalogue entries are keyed by format, type, lane and
release; AI sample and business-request entry points), `Intelligence.tsx` (the "Ask" panel
over indexed sources), `ExcelStudio.tsx` and `Automation.tsx` (lane/release on templates and
examples) and `RecentMessages.tsx` (lane shown).

### Demonstration and release

```
demo/                                  synthetic pack, generated — never hand-written
CLIENT_DEMO_RUNBOOK.md                 the twenty-minute walkthrough
AUTHORITATIVE_ARTIFACT_CHECKLIST.md    what a client must supply, and what it unlocks
docs/history/                          point-in-time reports; v0-1-0-release-readiness-report.md is the v0.1.0 baseline
docs/generated/                        measured reports; make knowledge-reports-write renders the three Phase 6 ones
```

### Tests

```
backend/tests/studio/test_fin_envelope.py     envelope correctness + refusal rules
backend/tests/studio/test_mt_generation.py    addressing, validation, output modes
backend/tests/studio/test_settlement_domain_rules.py  SETR, party direction, party options
backend/tests/studio/test_financial_instrument_identifier.py  35B across every input path
backend/tests/studio/test_field_presentation.py  one presentation model for every client
backend/tests/unit/test_identifiers.py        ISO 6166 and BIC shape, both verdicts apart
backend/tests/studio/test_mx_generation.py    namespace, order, choice, XSD, AppHdr
backend/tests/studio/test_mt_import.py        the MT round trip, and every refusal
backend/tests/studio/test_mx_import.py        the MX round trip, and every refusal
backend/tests/studio/test_coverage_and_sources.py  coverage is measured, not declared
backend/tests/studio/test_message_diff.py     every difference is attributed correctly
backend/tests/studio/test_mx_lifecycle.py     the four cancellation/modification messages
backend/tests/rule_engine/test_mt_semantics.py Phase 5A MT source/reference/runtime boundaries
backend/tests/rule_engine/test_mt_mrg.py      Phase 5B/5C guide reading, release isolation, occurrence-aware candidate proofs
backend/tests/knowledge_base/test_discovery.py        roots, symlinks, ZIP limits, content identity
backend/tests/knowledge_base/test_chunking.py         stable segmentation and section classification
backend/tests/knowledge_base/test_embeddings.py       adapter, cache key, policy gate, fake provider
backend/tests/knowledge_base/test_retrieval_and_index.py  incremental sync, FTS, fusion, citations
backend/tests/knowledge_base/test_structures_and_lane.py  MT/MX pack compilation, gates, preview lane isolation
backend/tests/ai_authoring/test_authoring.py          identify/prepare/samples/test-data with the scripted provider
backend/tests/knowledge_fixtures.py                   the synthetic corpus every knowledge test indexes
backend/tests/live/test_ai_sample_live.py             real-provider proof; `-m live`, never in make check
backend/tests/studio/test_excel_api.py        templates, parsing, upload guards
backend/tests/studio/test_studio_api.py       the /api/v1 contract
backend/tests/security/test_cors_and_throttling.py  short-circuit responses stay readable
backend/tests/unit/test_database_concurrency.py    the in-memory engine under threads
backend/tests/unit/test_setup_from_a_clean_clone.py  make migrate works on a new machine
frontend/tests/e2e/studio-create.spec.ts      the manual journey
frontend/tests/e2e/mt-authoring.spec.ts       ISIN, SETR, parties, dropdowns, mode switch
frontend/tests/e2e/studio-import.spec.ts      import round trip + lifecycle in the browser
frontend/tests/e2e/message-diff.spec.ts       the comparison a tester actually reads
frontend/tests/e2e/studio-screens.spec.ts     other screens + responsive + a11y
frontend/tests/e2e/knowledge-base.spec.ts     sources, readiness, search, preview-lane catalogue
frontend/tests/e2e/ai-authoring.spec.ts       AI sample / business request with the scripted provider
frontend/tests/e2e/global-setup.ts            indexes the synthetic corpus into build/knowledge-e2e/ first
backend/tests/golden/expected/*.txt           byte-for-byte MT regression fixtures
```

---

## 6. Invariants — do not break these

### Nothing is invented

Every value carries a `FieldOrigin`:

| Origin | Platform produces it? |
|---|---|
| `USER_ENTERED`, `PROFILE_CONFIGURED`, `APPLICATION_GENERATED` | yes |
| `INTERFACE_GENERATED`, `NETWORK_GENERATED` | **never** |

Enforced in code:

- Missing Block 1 session/sequence numbers → `FinEnvelopeUnavailable`, **fail closed** with
  a named error. Never a plausible substitute.
- `FORBIDDEN_TRAILER_TAGS = {MAC, CHK, PDE, PDM, DLM, TNG, SYS}` — refused even if a profile
  configures them.
- MX `Sgntr` never written.
- The MX transport wrapper is profile-configured; absent config, no wrapper is invented.

### Coverage claims stay honest

Every specification ships `authoritativeCompletenessKnown: false` and every message reports
`capability: PARTIAL`. Only a reconciled licensed specification changes that. Do not raise a
capability claim without one.

Prowide Core evidence does not change that boundary. Treat it as
`PROWIDE_DERIVED_STRUCTURAL_EVIDENCE`: useful for message/sequence/field-group comparison,
never sufficient for qualifier legality, code-list legality, network validation, market
practice, client rules, Swift certification or ISO 15022 completeness.

MT semantic canonical references have the same boundary. `MT:SR2025:MT541:SETDET:22F:SETR`
is evidence metadata, not a runtime field definition. Runtime Rule Packs must still compile
through installed MT row ids or exact MT triples, and candidate-only MT messages remain
inactive.

### Prowide stays build-time only

The FastAPI runtime must not import `app.spec_engine.mt_prowide`, Java, Maven, Gradle or
Prowide. `make mt-prowide-check` reads committed reports only;
`make verify-prowide-mt-source` is the live pinned-source proof and writes only to ignored
`build/` paths.

### Errors name the business field

`"Settlement Amount is required."` — not `"MT541-E-19A-SETT missing"`. The `ruleId` goes in
the payload, never in the sentence. Every error needs `ruleId`, `field`, `message`,
`expected`, `suggestion`.

### The UI gains no capability the API lacks

New functionality means the endpoint first, then `lib/studio-types.ts`, then
`lib/studio-api.ts`, then the component. Those three frontend files are kept in step by
hand; there is no generator.

---

## 7. Validation layers

Reported individually, never collapsed into a boolean.

| Layer | MT | MX |
|---|---|---|
| `CANONICAL` | inputs address real fields | same |
| `STRUCTURE` | required present, cardinality | same |
| `FORMAT` | per-tag regex / per-datatype | ISO 20022 representation classes |
| `BUSINESS_RULES` | cross-field rules | same |
| `CLIENT_PROFILE` | currency, reference length | same |
| `FIN_ENVELOPE` | envelope buildable | n/a |
| `XML_WELL_FORMED` | n/a | parses |
| `XSD` | n/a | libxml2 |
| `APPHDR_CONSISTENCY` | n/a | `MsgDefIdr` matches namespace |

Client-profile rules also carry **identifier quality**: an ISIN's ISO 6166 check digit is
verified in `CLIENT_PROFILE`, not `FORMAT`, because the FIN network checks the field format
(`4!c//12!c`) and does not compute the check digit. Reporting both under one layer would
claim a SWIFT rule that does not exist. See `app/domain/identifiers.py`.

Business rules currently enforced: settlement date not before trade date · `APMT` requires
an amount, `FREE` forbids one · MX receipt must name the delivering chain · cancellation
requires a previous reference · status advice must report at least one status
(`requireOneOf`, expressed as **configuration** not code) · amount positive.

---

## 8. XSD: two schema sources

| Source | Origin | Proves |
|---|---|---|
| `OFFICIAL` | a `.xsd` the operator supplied in `backend/config/mx/xsd/official/` | conformance to that supplied schema — the platform cannot verify the file is the genuine ISO artifact |
| `SUBSET_DERIVED` | generated at runtime from the YAML | matches *this repo's* subset |

`SUBSET_DERIVED` is the default (official schemas are licensed, not included). It is a real
XSD compiled by libxml2 and independently catches element order, cardinality, datatypes,
enumerations and required attributes — tests prove each. It is **not** conformance and the
tool never claims it is. The response always reports which was used.

The same reading governs business-rule sources: `sourceType` on a source bundle is an
operator **declaration**, and the platform never converts it into a compliance claim.

---

## 8a. The rule engine: the invariants worth knowing before you touch it

- **AI candidates never enter runtime validation.** `RulePackRegistry` loads a pack only
  when the pack *and every rule in it* is `REVIEWED`, and it **refuses** rather than skips
  anything else — a silent skip is how that invariant would erode.
- **Rule packs cannot mutate structure packs.** There is no writer; the compiler only
  resolves references. Refusals are named: an overlay cannot invent a code, add an element
  or a tag, change a namespace, widen cardinality, or forbid a field the structure requires
  in every message.
- **Reviewed packs are source-controlled.** Local approval is not activation. The gate is
  `candidate → review → git diff → PR → CI → merge`; nothing writes to `config/rules/` at
  runtime and there is no review API.
- **Overlay widening is forbidden.** A higher layer's code set must be a subset of the
  effective set beneath it. A contradiction is reported with both rule identifiers and both
  evidence origins; the engine never picks a winner.
- **Source text is untrusted prompt data.** It is fenced, never followed, and the closed
  response schema means an injected instruction cannot change the answer's shape.
- **Non-synthetic source text needs two explicit approvals before model calls.**
  `sourceAllowsExternalModelProcessing` and
  `providerApprovedForSourceClassification` must both be true. Unknown is blocked.
- **No chain-of-thought is persisted.** It is never requested, and only the closed schema's
  fields are stored.
- **Live extraction is not part of normal CI.** `make check` must pass with no provider
  credential of any kind; a test asserts the offline evaluation cannot construct a live
  client.
- **Rule evaluation is pure.** No clock, no randomness, no I/O, no model — the platform
  validates identically with AI access switched off.
- **Occurrence scope is internal rule data, not a runtime structure writer.** `rule-dsl/2`
  can evaluate an assertion per repeating sequence occurrence when the caller supplies an
  `EvaluationContext`; legacy flat value bags keep the original global semantics. This
  closed MT540/MT541 SR2026 candidate gaps without installing those candidates.

---

## 9. Authentication: two separate models

| | Interactive | Automation |
|---|---|---|
| Mechanism | session cookie + CSRF + RBAC | `X-API-Key` |
| Scope | `/api/auth/*`, drafts, approvals | `/api/v1/*` |
| Config | `SESSION_HMAC_SECRET` | `AUTOMATION_API_KEYS` |

`/api/v1` is **open when `APP_ENV` is `development` or `test`** — that is what makes a clean
clone usable. Elsewhere it returns `503` until keys are configured. Keys come only from the
environment, are compared with `hmac.compare_digest` against every configured key, and never
appear in a response, log line or source.

---

## 10. AI boundary

Before Phase 6 the model did one thing: turn natural language into structured intent for
the settlement screen. Phase 6 adds `app/ai_authoring/`, and the boundary is the same shape,
wider:

- **The model proposes; deterministic code decides.** It may identify a message from a
  business request, choose canonical values for fields the Structure Pack declares, draft
  MINIMAL / TYPICAL / FULL samples and bulk test data, and phrase explanations with
  citations. It never renders FIN or XML, never decides validity, never parses, never reads
  a spreadsheet, never adds a field, code, sequence or element the structure lacks, and
  never changes the message type, lane or release it was given (`prepare` keeps MT541 when
  the request text says "use MT999"; every returned field id must exist in the structure).
- **Every AI answer goes through the ordinary validator and composer**, with a bounded
  repair loop (`KNOWLEDGE_AI_MAX_REPAIR_ATTEMPTS`, default 3) that feeds the validator's
  findings back. A sample is cached only once it validated, keyed as in §10a.
- **The deterministic endpoints make zero model calls.** `POST /api/v1/messages/generate`,
  `validate`, `import`, `diff`, the Excel routes and every `GET` never touch a provider or
  the knowledge base. RAG runs only on the explicit `/api/v1/ai/*` operations and
  `POST /api/v1/knowledge/search`.
- **Every operation computes a deterministic seed first.** That seed is what the `scripted`
  provider returns in CI and Playwright, what the platform falls back to with no provider,
  and the starting point a live model refines inside a closed JSON schema.
- **Retrieved text is data, not instruction.** Prompts fence source excerpts, the answer
  schema is closed, and a source whose `llm_policy` is `BLOCKED` is cited by identity and
  page but never quoted to an external model.

Message Intelligence lookup is still deterministic dictionary search — the Playwright test
still watches network traffic for it. The new "Ask" panel on that screen is an explicit AI
operation and is labelled as one.

`AI_PROVIDER=disabled` and `KNOWLEDGE_AI_PROVIDER=disabled` are fully supported: every
deterministic path and the preview lane keep working; the AI entry points answer with
their deterministic seed or a clear "not configured". Order when enabled:
**deterministic → cache → model**.

---

## 10a. The knowledge base — what an agent must know before touching it

**Roots and discovery.** `KNOWLEDGE_SOURCE_DIR` is a comma-separated list of roots relative
to the project root (the operator uses `swiftKnowledgeBase,build/mx-real-sources`).
`discovery.py` walks them without following symlinks, never leaves a root, extracts ZIP
members into the ignored source cache under byte and ratio limits, and never writes to an
original. Supported suffixes: `.pdf .txt .md .markdown .html .htm .xsd .xml .zip`.
`identify.py` decides what a file is **from its content** — an MRG's own cover page, an
XSD's target namespace — never from its name. Identity is
`(format, messageType, messageVersion, release)`; the checksum is the primary key, so the
same bytes under two paths are one source.

**The database** is one SQLite file (`KNOWLEDGE_DB_PATH`, default
`build/knowledge/knowledge.sqlite3`) with tables for sources, paths, segments, an FTS5
index (`unicode61 remove_diacritics 2`), embeddings, index runs and compiled structures.
Versions: `KNOWLEDGE_SCHEMA_VERSION 1`, `knowledge-chunker/1`, `embedding/1`,
`knowledge-pack-compiler/2`, `mt-structure-pack/1`. **Runtime reads the database only;
source files are opened by the sync command alone.**

**Incremental sync** (`make knowledge-sync`): unchanged checksums are skipped, chunks are
reused by hash, embeddings are reused by `(segment_hash, provider, deployment, dimensions,
schema_version)`, and compiled packs are reused when their compiler version and inputs are
unchanged. On the operator's folder a fresh compile takes ~20 s, an unchanged rescan 0.4 s,
`--reindex` ~27 s.

**Privacy policy is two gates, both default closed.** A source's text may go to an external
embedding or chat endpoint only when `KNOWLEDGE_EXTERNAL_EMBEDDING_ALLOWED` /
`KNOWLEDGE_EXTERNAL_LLM_ALLOWED` is true **and** its classification is listed in
`KNOWLEDGE_EXTERNAL_PROCESSING_CLASSIFICATIONS` (default: `SYNTHETIC_FIXTURE` only). The
decision is written on the source row and read by the embedder, the prompt builder and the
citation renderer alike. An API key is never permission. On the operator's machine all 23
real sources are `BLOCKED`, so retrieval over the real corpus is lexical, and the status
endpoint says so in `embeddingPolicyStatement`.

**Embeddings.** `EMBEDDING_PROVIDER` is `auto | azure_openai | openai_compatible | fake |
disabled`; `auto` picks Azure when the endpoint host is `*.openai.azure.com`, an
OpenAI-compatible server when an endpoint and key exist, and disabled otherwise. Vectors are
float32 BLOBs with their norm; the dimension is validated on read. `fake` exists for tests
and CI only.

**Retrieval** (`retrieval.py`): metadata narrowing by format / message / release / section
→ BM25 over FTS5 (k=20) → cosine over the filtered vectors (k=20) → reciprocal rank fusion
with `RRF_K = 60` → at most 4 hits per section → a context budget of
`KNOWLEDGE_CONTEXT_CHARS` (6,000). Semantic hits below 0.25 are dropped; semantic-only hits
need 0.35. Ties break on the segment id. Deterministic; no model ranks anything. Every hit
carries a citation — source id, checksum, page, section, release — and an excerpt only
where `snippets` is allowed by policy.

**Structure Packs and readiness.** `structures/mt_pack.py` builds one pack per MT message
and release from the pinned Prowide `SR2025` fixture, reconciled with the Format
Specification tables of any MRG the sync indexed for that message (the 14 `SR2026` guides
produce MRG+Prowide-corroborated packs; a conflict is recorded as
`STRUCTURE_SOURCE_CONFLICT`, never resolved by guessing). `structures/mx_pack.py` runs
every indexed XSD through `spec_engine.compile_schema` and `validate_pack` — the same six
gates a committed pack passes. Readiness is derived from gates, never declared:

| Readiness | Meaning |
|---|---|
| `KNOWLEDGE_ONLY` | text is indexed; no pack loads (MT035, MT043, MT048, MT049, MT096 — Prowide models with no block-4 fields) |
| `STRUCTURE_AVAILABLE` | pack loads but a gate failed or evidence is missing (`QUALIFIER_EVIDENCE_MISSING`, `FORMAT_FIDELITY_PARTIAL`, `MESSAGE_GENERATION_NOT_READY`) |
| `STRUCTURE_VERIFIED` | a deterministic sample validated and composed, but parse/round trip failed (`ROUND_TRIP_FAILED`) |
| `GENERATION_READY` | load → sample → validate → compose → parse → `Compose(Parse(Compose(v)))` identical (MX: and the source XSD accepted the output) |

Measured 2026-08-20: 293 structures; MT 201 `GENERATION_READY` (187 Prowide-only SR2025 +
14 MRG-corroborated), 10 `STRUCTURE_VERIFIED`, 69 `STRUCTURE_AVAILABLE`, 5
`KNOWLEDGE_ONLY`; MX 8 `GENERATION_READY` (every pacs XSD supplied). `GENERATION_READY`
means structure-backed test generation. It does not mean complete semantic rules, SWIFT
certification, conformance or User Handbook completeness — the pack's own `limitations`
say so.

**Lanes and releases — never conflate them.**

- `CONFIGURED`: the committed YAML, release `PUBLIC_UHB_REVIEW_2026_08_05`. Unchanged by
  Phase 6. It is what `GET /api/v1/catalogue` lists first and what every call means when
  it does not name a lane.
- `KNOWLEDGE_PREVIEW`: packs compiled by the sync, loaded by `preview.py` into **separate
  registry instances** of the same runtime types. A caller must name `lane` (and, for MT,
  `release`) on every request; nothing promotes a preview pack into the configured
  registries. Responses carry `lane` and `provenance` (structure source, release, release
  lane, gates, limitations).
- Releases: `SR2025` is `CURRENT_LIVE` Prowide evidence; `SR2026` is `FUTURE_TEST` (live
  14 November 2026); `RELEASE_LANES` is a recorded table, never computed from the clock. A
  preview of a configured message in a current-live release is **shadowed** — not listed
  beside the configured entry (16 such Prowide-only structures), recorded in the readiness
  report and visible at `GET /api/v1/knowledge/messages/{m}/status`. A future-release
  preview of the same message (MT541 SR2026) stays listed.

**Sample cache key**: format | message type | release or version | lane | sample type |
profile | structure checksum | sorted rule-pack ids | message-scoped corpus version |
`ai-authoring-prompt/1` | `ai-authoring-schema/1` | provider | model. Any of those changing
is a miss; a hit makes zero model calls and returns the same checksum.

**What is committed and what is not.** Committed: code, the synthetic fixture corpus
(`backend/tests/knowledge_fixtures.py`), the generated reports (counts, checksums, no
source text). Never committed: anything under `swiftKnowledgeBase/`, `build/knowledge*/`
(database, vectors, source cache, compiled packs), and no `.env` value. `make secret-scan`
and the `.gitignore` entries enforce it.

**Endpoints.** `/api/v1/knowledge`: `GET status`, `GET messages`,
`GET messages/{message}/status`, `POST search`, `GET telemetry`, `GET sources`,
`POST sync` (404 unless `KNOWLEDGE_MODE=local_uat`). `/api/v1/ai`: `POST messages/identify`,
`POST messages/prepare`, `POST samples`, `POST test-data/generate`, `POST presentation`,
`POST ask`, `POST releases/compare`. Existing routes gained `lane` / `release`: `GET
catalogue` (plus `readiness`, `blockers`, `configuredMessageCount`), `GET
messages/{m}/spec`, `samples`, `samples/{variant}`, `POST validate` / `generate` / `import`
(in the body), `generate-from-excel` and `templates/{format}.xlsx` (query). Contract detail:
[automation-api.md](automation-api.md).

---

## 11. Continuous integration

`.github/workflows/ci.yml`. Runs on every pull request to `main`, every push to `main`, and
on demand. **Python 3.13, Node 22** — the same versions this repository targets locally.

| Job | What it runs | On |
|---|---|---|
| **Required Checks** | `make install` → `make check` → `make secret-scan` → `git diff --check`. Since Phase 6 `make check` includes `knowledge-check`: the retrieval evaluation over the synthetic fixture corpus with `EMBEDDING_PROVIDER=fake` — no PDF, no XSD, no key, no network | PR, main |
| **Clean Clone** | `make install` → `make migrate` → `make check`, from git-tracked files only | PR, main |
| **MT Prowide Source** | backend deps + Java 21 → `make verify-prowide-mt-source` | PR, main |
| **Browser E2E** | `make e2e`; report, traces and screenshots uploaded **on failure only**. Its Playwright global setup first indexes the synthetic corpus into `build/knowledge-e2e/` (fake embeddings, `scripted` AI provider), so the Knowledge Base and AI authoring screens are exercised with no licensed document and no provider key | PR, main |
| **Docker** | `docker compose config --quiet` → `docker compose build`. Nothing is pushed | PR, main |
| **Security Audit** | `make audit` — `pip-audit` and `npm audit --omit=dev` | PR, main |

Phase 6 added no job and renamed none; it changed two step comments and what the existing
targets cover. The live provider proofs (`make probe-embeddings`, `make test-live-rag`,
`make test-live-ai-sample`) are deliberately outside CI: they need a key and cost money.

Branch protection is **configured** on `main`: the status check `Required Checks` is
required, `strict` is on so a branch must be up to date with `main` before it merges, and
force pushes and branch deletion are blocked. CI blocks rather than reports. Detail and
rationale: [history/ci-implementation-report.md](history/ci-implementation-report.md).

**Reproduce any job locally by running the same make target.** The workflow adds only what a
runner needs that a laptop does not: the browser's OS libraries (`--with-deps`, which needs
sudo and would be wrong on a developer machine), and a base ref so `git diff --check` has a
range — bare `git diff --check` compares the worktree to the index and is always clean in CI.

Things worth knowing before editing it:

- **Branch protection matches the check run's own name — `Required Checks` — not the
  `CI / Required Checks` display form the PR page shows.** Requiring the display form
  looks configured and gates nothing: every job green, `mergeable: MERGEABLE`, and the PR
  permanently `BLOCKED` with no visible reason. Renaming the job silently disables the
  gate; job name and protection setting must move together.
- **Clean Clone deliberately has no dependency cache.** A cached wheel would hide exactly the
  class of defect that motivated the job — `lxml-stubs==0.6.0`, a pin that does not exist
  upstream and broke `make install` for everyone who had never run it.
- **Security Audit is deliberately not part of Required Checks.** It asks the world whether a
  dependency has a newly published advisory, so it can turn red overnight for a reason
  nobody's change caused. A required gate should fail only for something in the diff.
- **`reuseExistingServer` is false whenever `CI` is set**, so a run can never adopt a server
  it did not start.
- Concurrency cancels superseded **pull request** runs only; a `main` run is never cancelled,
  because the default branch would be left with no verified result.

---

## 12. Commands

```bash
make install      # venv + npm ci                    (Python 3.13, Node 22)
make migrate      # alembic upgrade head
make backend      # uvicorn on :8000
make frontend     # next dev on :3000
make check        # lint + typecheck + tests + coverage gate   ← before every push
make e2e          # Playwright (starts both servers itself)
make secret-scan
make coverage     # fail if docs/generated/message-coverage.md is stale
make coverage-write   # regenerate it
make demo-pack        # rebuild demo/ from the production composer
make demo-pack-check  # fail if demo/ no longer matches what the composer produces
make spec-compile SOURCE=schema.xsd [OUT=dir]   # XSD -> specification pack + gates
make spec-validate PACK=pack.yaml SOURCE=schema.xsd
make spec-diff BEFORE=old.yaml AFTER=new.yaml
make mt-prowide-check          # generated Prowide reports are current; offline
make verify-prowide-mt-source  # pinned Prowide source reproduction + MT541 parser proof
make mt-rule-check             # MT semantic readiness docs + synthetic MT corpus
make evaluate-mt-rule-extraction
make mt-mrg-check              # SR2026 generated reports are current; needs no document
make mt-mrg-extract            # re-read the Message Reference Guides (local documents)
make mt-mrg-evaluate           # prove the SR2026 candidate rules behave
make verify-real-mt540-mt541-source   # the committed SR2026 evidence reproduces
docker compose up --build
```

Phase 6 — the knowledge base. `KNOWLEDGE_MODE` defaults to `local` for the CLI targets;
pass `KNOWLEDGE_SOURCE_DIR=swiftKnowledgeBase,build/mx-real-sources` to walk more than the
default root.

```bash
make knowledge-sync            # discover, identify, segment, index, embed (policy), compile packs — incremental
make knowledge-status          # counts, last run, embedding/LLM policy, load errors
make knowledge-reindex         # sync --reindex: re-parse every source, reuse nothing
make knowledge-clean-cache     # drop build/knowledge caches; never touches a source
make knowledge-reports-write   # docs/generated/{universal-message-readiness,knowledge-rag-coverage,ai-sample-readiness}.md
make knowledge-reports-check   # fail if those reports no longer match the database
make knowledge-check           # offline retrieval evaluation, synthetic fixtures, fake embeddings — in make check
make evaluate-rag              # the same evaluation, by its own name
make knowledge-dev             # sync, then uvicorn in KNOWLEDGE_MODE=local_uat (enables POST /knowledge/sync)
make probe-embeddings          # one synthetic call to the configured embedding deployment; prints dims and latency
make test-live-rag             # evaluate-rag --live: real embeddings over the SYNTHETIC corpus only
make test-live-ai-sample       # pytest -m live tests/live/test_ai_sample_live.py: real chat deployment
```

The last three are never part of `make check` or CI.

Targeted:

```bash
cd backend && .venv/bin/pytest tests/studio -q
cd backend && .venv/bin/pytest -k "fin_envelope" -q
cd frontend && npx playwright test studio-create --headed
```

---

## 13. Gotchas discovered the hard way

Defects found and fixed while building this. These are the ones likely to recur:

**Frontend**

1. **Unlayered CSS beats every Tailwind utility.** An unlayered `button { color: inherit }`
   reset silently killed every text-colour utility on every button. Layered rules always
   lose to unlayered ones regardless of specificity. → Base styles go in `@layer base`.
2. **Grid/flex children default to `min-width: auto`.** A wide code block or table expands
   its track instead of scrolling, and the page scrolls sideways. → `min-w-0` on any
   grid/flex child that can hold wide content.
3. **React 19 lints synchronous `setState` in an effect body.** → Put the fetch inside the
   effect and use a reload token for retry, rather than calling a callback that sets state.
4. **`dir="rtl"` for left-truncating a path** reorders leading punctuation to the end.
   → Truncate in JS.

**Backend**

5. **`date.fromisoformat` accepts the compact `YYYYMMDD` form** on modern Python. An
   MT-style date passed the friendly ISODate check and only the XSD caught it. → Explicit
   `^\d{4}-\d{2}-\d{2}$` pattern first.
6. **Occurrence must thread through repeatable containers.** Without it, every repeat
   renders the first occurrence's values.
7. **Duplicate error reporting.** The composer restates in its own words what the structured
   validator already reported. Deduplicate by row id, not by message string — 12 missing
   fields otherwise produce 24 errors.
8. **A method named `list` on a class breaks `list[X]` annotations** under
   `from __future__ import annotations` (mypy resolves it to the method). → Renamed to
   `all_specs`.
9. **Comparing a resolved object to a code string** silently never matches and disables the
   rule. mypy `--strict` catches it via `comparison-overlap`; run it.

10. **An MX element name is not unique, and neither is an occurrence index.** The composer
    threads one occurrence integer down through each repeatable container, so the parser has
    to reassign the same integer walking back up. Two repeatable blocks nested inside each
    other cannot be represented at all — `parser.py` detects the collision and refuses
    rather than overwriting.

**The MT occurrence model**

11. **A child sequence at occurrence N did not imply an ancestor at occurrence N — but the
    composer assumed it did.** `_compose_inputs` carried the occurrence index up the whole
    parent chain, so asking for two `PENDET` blocks produced two whole `PENA` sequences and
    broke `PENA`'s own `1..1` cardinality. Reachable from the UI and from Excel's
    `SequenceOccurrence` column long before import existed; MT import is simply what made it
    visible. An ancestor repeats only where a field addresses that repeat directly. The rule
    now lives once, in `plan_sequences`.
12. **MT import must run the real planner, not a restatement of it.** The parser checks a
    structure is expressible by running `plan_sequences` over what it read and comparing the
    instance tree with the one the message had. A hand-derived rule looked right and was
    wrong in two cases; this cannot drift.
13. **This repository writes two different Block 2 conventions.** A real FIN envelope
    (`{2:I541DEMOUS33XXXXN}`) and a demonstration one (`{1:DEMONSTRATION}{2:MT541}`) that the
    golden fixtures and the samples screen use. An importer that only understands the first
    refuses the repository's own output.

**Configuration**

29. **A YAML merge key copies a code list onto every field that inherits it.** `<<: *anchor`
    copies *everything*, so a payment date ended up declaring the code list of a
    voluntary-event indicator, and an account number declared `VOLU` as its only allowed
    value. Harmless while nothing read them; the moment code lists became dropdowns they
    would have become wrong dropdowns. Blocked with an explicit `codeList: null` where the
    inheritance is accidental, asserted at load, and
    `test_a_code_list_never_leaks_onto_an_unrelated_field` fails if a list is ever shared by
    two fields with neither tag nor qualifier in common.
30. **A record that names a code list and restates different codes is a mistake, and load is
    the only useful moment to say so.** `_resolve_code_list` refuses rather than preferring
    one silently.

**Identifiers**

31. **This repository's own sample ISIN failed its check digit.** `XS0000000001` satisfies
    the ISO 15022 field format for 35B — twelve characters, two leading letters, a numeric
    final character — and the correct ISO 6166 digit for that body is `9`. It shipped in
    every golden fixture, the demo pack and both Excel templates because nothing computed
    the digit. `SAMPLE_ISIN` is now derived by `synthetic_isin()`, so it cannot recur.
32. **Field format and identifier quality are different claims and belong in different
    layers.** The FIN network validates `4!c//12!c`; it does not compute an ISO 6166 check
    digit. Reporting a bad check digit as a FORMAT failure would assert a SWIFT rule that
    does not exist, so it is a CLIENT_PROFILE finding with its own ruleId.

**Frontend**

33. **`maxLength` truncates the raw input before any normaliser sees it.** Pasting
    `ISIN XS0000000009` into a `maxLength={12}` box leaves `ISIN XS00000`, which normalises
    to `XS00000` — a silently mangled value from a paste that should have worked. Enforce
    the length *after* normalising instead. Found by Playwright, not by typing.
34. **Calling a parent's state setter during render can abort an in-flight fetch.** A select
    with exactly one allowed value preselected it inline, React re-rendered mid-commit, and
    the resulting churn cancelled the catalogue request — which surfaces as "the studio API
    could not be reached" against a backend that is running perfectly. Preselect in an
    effect.

**The specification engine**

35. **The MT registry was closed in both directions, and the loader duplicated
    configuration in code.** `MessageType` (a 16-member enum), `KNOWN_MESSAGE_OWNERS` and
    `KNOWN_FIELD_SIGNATURES` each had to be edited to add a message or even a field —
    despite §15 promising YAML-only extension. All three authorities now live in the
    manifest (`workflowModule`, `shortDescription`, sequences per message); the knowledge
    loader validates records against it, and `StrEnum` members being `str` is what let the
    registry switch to string keys without touching a legacy caller.
36. **A branch of an XSD choice must not compile to `presence: MANDATORY`.** The
    structural validator requires every mandatory leaf whose parent is present, so two
    mandatory branches of one choice can never both be satisfiable. The choice itself
    carries "exactly one"; branches compile with no presence, matching the hand-authored
    packs.
37. **The composer only writes an amount's `Ccy` attribute when the element declares
    `currencyAttribute: true`.** A compiled amount without that flag produces
    `<Amt>USD 1000.00</Amt>`, which the source schema rejects as a non-decimal — the
    source-XSD gate exists precisely to catch that class of compiler bug, and did.

**Persistence**

14. **`StaticPool` hands one SQLite connection to every thread at the same time.** With
    `check_same_thread=False` — which an in-memory database needs — nothing objects, and
    FastAPI runs sync endpoints in a threadpool, so requests really do overlap. Eight
    threads produced `InterfaceError: bad parameter or other API misuse` and, worse,
    `NoResultFound`/`MultipleResultsFound` from a query that can only return one row:
    threads reading each other's result sets. It surfaced as an e2e test failing about one
    run in three, a different test each time. `sqlite://` now uses `QueuePool` with
    `pool_size=1, max_overflow=0` — one connection, and the pool blocks the second caller
    until the first returns it. `tests/unit/test_database_concurrency.py` fails if that is
    ever reverted.

15. **Alembic builds its own engine and never imports `app.persistence.database`.** That
    module was the only place creating the folder a file-backed SQLite database lives in, so
    `make migrate` — the *second step of the documented setup* — failed on every clean clone
    with "unable to open database file", and worked on every machine that had already run
    the app. `ensure_database_directory` in `app/config.py` is now called from both.
    `tests/unit/test_setup_from_a_clean_clone.py` fails if `env.py` stops calling it.

16. **A cached `lxml` `XMLSchema` is shared mutable state.** `validate()` writes its
    findings onto the schema object — `error_log` is instance state, and libxml2 keeps a
    validation context there too — while `_compiled` hands one object to every caller and
    FastAPI runs sync endpoints in a threadpool. Two concurrent validations interleave, so a
    verdict or an error list can be attributed to the wrong document. Found by CI: a
    lifecycle test failed about one run in three with "No matching global declaration
    available for the validation root" against a document whose root the schema declares.
    Validation is now behind `_VALIDATION_LOCK`, held across the verdict *and* the error-log
    read, because releasing between them would let another thread overwrite the findings.
    Compilation stays cached; validating a settlement message takes microseconds.

**Middleware and HTTP**

17. **`app.add_middleware` prepends.** The last registration is the *outermost*. CORS was
    registered first and therefore ended up innermost, so every short-circuit response from
    the request-context middleware — 400, 413, 429 — reached the browser with no
    `Access-Control-Allow-Origin`. `fetch()` rejects such a response with a bare network
    error, so a throttled tester was told the backend was down. Keep the CORS registration
    last, and keep `tests/security/test_cors_and_throttling.py`.
18. **Do not rate-limit CORS preflight.** A preflight is browser overhead the caller never
    chose to send; throttling it fails the real request with an unexplainable CORS error and
    defends nothing, because a non-browser client never sends one.

**Environment**

19. **`next dev` writes its own `AGENTS.md`, and will write it here if `frontend/AGENTS.md`
    is missing.** `node_modules/next/dist/server/lib/generate-agent-files.js` walks up to the
    project root when it cannot find its file, and it **replaces** rather than merges — this
    document was reduced to nine lines of Next boilerplate once. Keep `frontend/AGENTS.md`
    committed; it is Next's target and it is what protects this file.
20. **Playwright's `reuseExistingServer` will reuse whatever is on port 8000**, including a
    backend you started by hand — which has a *different environment*. `playwright.config.ts`
    passes `DATA_ENCRYPTION_KEY` and `SESSION_HMAC_SECRET`; a hand-started server reads
    `.env` instead, and the encrypted-draft and guided specs then fail for reasons that have
    nothing to do with the change under test. It will also happily reuse a **stale** backend
    started before your change. Stop your own servers before `make e2e`.

21. **`localhost` is not an address, and on a dual-stack machine it resolves to `::1`
    first.** The backend binds `127.0.0.1`, so a browser `fetch()` to `http://localhost:8000`
    occasionally died with `ECONNREFUSED ::1:8000` — which reaches `fetch()` as a bare
    network error and reads as "the backend is down". It surfaced as an unrelated e2e test
    failing about one run in three. macOS binds `--host ::` as IPv6-*only*, so listening on
    both is not the fix; matching the address is. Everything the app and the tests call now
    uses `127.0.0.1`, and CORS accepts both spellings of the origin.

**Tests**

22. **The demonstration rate limit is per process, and each suite shares one.** Whether a
    run passed depended on how many requests it happened to make; growing either suite
    eventually tipped it over and produced 429s in files with nothing to do with throttling.
    `tests/conftest.py` and `playwright.config.ts` both raise the ambient limit. The
    throttle is still tested — `tests/security/test_cors_and_throttling.py` installs its own
    limiter, which is the only place the limit is the subject rather than the scenery.
23. **A loose `getByRole("heading", {name})` can pass on the page `<h1>`.** An assertion
    meant to check a generated message matches the page title instead, and only trips strict
    mode once the real heading also renders — so it passes or fails on timing. This has now
    happened twice: MT537 on `penalties`, then MT530 on `settlement-processing`, which passed
    on every laptop and failed on the **first CI run**, because a shared runner renders more
    slowly and both headings were present. Use `exact: true, level: 2` whenever a page and
    its result share a word — a generated message's code is always an `<h2>`.
24. **Hardcoded catalogue counts turn "someone added a YAML file" into a failure that says
    nothing.** Derive counts from the registries.

**Comparing two messages**

25. **An expected difference presented as a fault trains the tester to ignore all of them.**
    A regenerated message almost always differs from the pasted one, and almost always
    harmlessly. Every difference therefore carries a reason, and only `UNEXPLAINED` and
    `IMPORT_DROPPED` are counted as worth acting on. A Block 5 trailer or an MX `Sgntr` is
    `NOT_REPRODUCED` and is never an application error.
26. **Never label a difference you cannot account for as normalisation.** `UNEXPLAINED`
    exists for exactly the case the comparison is there to surface; a comfortable-sounding
    default would hide it.
27. **MX must be compared on a canonical serialisation, MT on raw lines.** Re-indenting an
    ISO 20022 document changes nothing about the message, but in FIN the line structure *is*
    the message. Normalising MT before comparing would hide a real defect.

**Coverage reporting**

28. **A declared coverage figure reports the flag, not the truth.** The Excel reference
    sheet was once hardcoded to three MX messages while the registry held seven, and a
    `composer_supported`-style flag would have said 100%. Every figure in
    `app/studio/coverage.py` is measured by asking the component what it produced.
29. **The coverage document is gated by `make check`, so it must be deterministic.** Render
    counts, never values: sample dates move with the clock and would fail the build on an
    unrelated commit. A test renders it twice and compares.

**Reading a standards document as evidence**

38. **A release is a lane, not a date comparison.** The SR2026 Message Reference Guides go
    live on 14 November 2026. Deriving the lane from the clock would make a validation rule
    change overnight without a commit, so the lane is a recorded constant and every report
    says the same thing whenever it is rendered. An SR2026 rule never becomes an SR2025 or
    a runtime fact by the calendar moving.
39. **A translation may say less than the source; it may never say more.** A weaker rule
    misses a violation a reviewer can still catch. A stronger rule rejects messages SWIFT
    accepts, which is the one outcome a testing platform must never produce. Phase 5B
    recorded occurrence-local MT540/541 rules as `UNSUPPORTED` rather than approximating
    them globally. Phase 5C added generic occurrence scope and recovered those candidates,
    while still leaving component, format-option, paired-code and distinct-occurrence
    clauses partial where the engine does not model them.
40. **A page number is not a row number.** The Format Specifications table numbers its rows
    in a right-hand column, and a wrapped row leaves that number alone on a line —
    indistinguishable from a page number at the foot of the page. Deleting "furniture" by
    shape silently deleted row 18. Furniture is now identified by *what it is*: the page's
    own number, and only at the bottom of that page.
41. **A lookahead window can eat the thing it is looking past.** The CODES blocks were
    matched over a three-line window to catch a wrapped introduction, and matching it
    *anywhere* in that window let the next list's introduction claim the previous list's
    final code — `DBNM` lost `VEND`, `SETR` lost `TURN`. Anchor a multi-line match at the
    start of its own line.
42. **Two sections share a page, so classification is per line.** The Usage Rules end and
    the Field Specifications begin on the same sheet. Page-level classification filed usage
    prose under the wrong authority.
43. **A document with no blank lines becomes one segment.** An extracted PDF can run a
    hundred pages without one, and every rule in the book would then share a single evidence
    identity. Segmentation now ends a block at a page break and at the segment ceiling too.
44. **The document refutes itself, for free.** Every qualifier table carries a `CR` column
    naming the rules that govern that qualifier. Comparing it against what a translation
    binds is a criticism with no way for two readings to agree by having made the same
    mistake — and it found a real over-reach in the linked-quantity rule.
45. **"Receive free" does not mean "no settlement amount".** MT540's own `C1` lists
    `:19A::SETT` among the amounts it constrains, and additionally lists `:19A::BOOK`, which
    MT541 does not. What MT540 lacks is MT541's `C2`, which makes the amount *mandatory*.
    Inferring the rule from the message name would have been wrong in both directions.
46. **`Cn` is a label, not an identity.** MT541 `C2` is the settlement-amount rule (`E92`);
    MT540 `C2` is a linked-count rule (`E90`). Matching rules by number across two books
    attributes one message's rules to another.
47. **A generated document that ends with a blank line fails CI and passes locally.**
    `git diff --check` refuses a *new* blank line at end of file, and it only sees one when
    a base ref is supplied — which the workflow does and a bare local run cannot, because
    it compares the worktree to the index. A renderer that joins a list ending in `""` and
    then appends `"\n"` produces exactly that. Normalise once, in a shared helper, so the
    next report cannot reintroduce it.
48. **An environment-dependent import needs an environment-independent annotation.**
    `# type: ignore[import-not-found]` on the optional `pypdf` import is correct on a runner
    without the package and an *unused-ignore error* on a laptop with it. A
    `[[tool.mypy.overrides]]` entry is the only spelling that is right on both machines.

**The knowledge base (Phase 6)**

49. **A compiler change without a version bump reuses stale packs.** Structure reuse is
    keyed on `PACK_COMPILER_VERSION` plus the inputs, so a fix to `mt_pack.py` that leaves
    the constant alone is silently never applied to an existing database. Bump
    `knowledge-pack-compiler/N` in `app/knowledge_base/__init__.py` in the same commit, or
    run `make knowledge-reindex` and wonder why nothing changed.
50. **`demo/` carries `lane: CONFIGURED` now.** Every request the demo pack records names
    its lane, so a lane added to the contract makes `make demo-pack-check` fail until
    `make demo-pack` regenerates it. That is the gate working; regenerate and commit.
51. **Silence is "blocked".** With the default settings every real source is
    `EMBEDDING_BLOCKED` and retrieval is lexical-only; telemetry shows `semantic: 0`. That is
    policy, not a failure. Allowing it takes both `KNOWLEDGE_EXTERNAL_EMBEDDING_ALLOWED=true`
    and the classification in `KNOWLEDGE_EXTERNAL_PROCESSING_CLASSIFICATIONS`. A key alone
    changes nothing.
52. **Sixteen preview structures exist that the catalogue does not list.** A Prowide-only
    `SR2025` pack for a message the configured lane already serves is *shadowed*: the
    configured pack is the authority for that message in the current-live release. They are
    in the readiness report and at `GET /knowledge/messages/{m}/status`; they are not
    missing.
53. **Option-R party fields take one slash after the qualifier.** `:95R::QUAL//...` was
    rendered for a `:4!c/8c/34x` format; the correct form is `:95R::QUAL/<scheme>/<code>`.
    Fixed in `qualifier_separator_for` (`app/knowledge/presentation.py`); golden fixtures
    and one Playwright expectation changed with it. A Prowide format string is the place to
    read the separator from, not the tag family.
54. **`STRUCTURE_VERIFIED` is the parser's verdict, not the composer's.** The ten MT
    structures in that state composed a valid message and then failed `ROUND_TRIP_FAILED`
    on the way back. Promote them only by fixing the generic parser path the gate names,
    never by relaxing the gate.
55. **`POST /api/v1/knowledge/sync` answers `404` unless `KNOWLEDGE_MODE=local_uat`.** Not
    403: outside UAT mode the endpoint does not exist as far as a caller can tell, so a
    production-style process cannot be asked to read workstation files, and a sync that
    "did nothing" is usually this. `make knowledge-dev` sets the mode for you.
56. **Runtime never opens a source file.** `preview.py` and `service.py` read the SQLite
    database and the YAML packs only; the compiler, the Prowide tooling, the MRG reader and
    the PDF library are imported by the sync command alone. A change that makes a request
    path import `structures/` or `identify.py` is wrong even if it works.
57. **Identity comes from content, never from the filename.** A file called `MT541.pdf`
    that is actually the MT540 guide is indexed as MT540. A renamed copy of an indexed file
    is the same source (same checksum, two paths), not a duplicate.
58. **`bis_skin_checked` hydration warnings are not ours.** They come from a browser
    extension that rewrites the DOM before React hydrates. Reproduce in a clean profile
    before chasing them.
59. **The synthetic fixture corpus is the only thing a live embedding test may send.**
    `make test-live-rag` embeds `tests/knowledge_fixtures.py`, never the operator's folder,
    whatever the policy settings say — so it can be run on a machine that holds licensed
    PDFs without sending one.

---

## 14. Known limitations

Full list: [limitations.md](limitations.md).

- **Coverage is a repository-configured subset**, never reconciled against a licensed spec.
- **XSD is `SUBSET_DERIVED` by default.**
- **The four lifecycle specifications are doubly unverified.** `sese.020`, `sese.027`,
  `sese.030` and `sese.031` carry the usual subset caveat *and* an explicit `UNVERIFIED`
  limitation: their version numbers, message root element names and element sets were
  modelled on the ISO 20022 idioms already in this repository, not reconciled against an
  authoritative message-definition report. Reconcile before any use beyond internal testing.
- **A message over 3,000 lines, or with over 200 import problems, is not compared line by
  line.** The comparison still answers whether the two messages are the same, and says why
  it did not list the differences. Both bounds sit far above anything the studio itself can
  produce.
- **Import cannot represent a repeatable block nested inside another repeatable block.**
  The flat `(path, occurrence)` address has one index. Detected and refused
  (`MT_IMPORT_NESTED_REPEAT_UNSUPPORTED`, `MX_IMPORT_NESTED_REPEAT_UNSUPPORTED`), never
  silently collapsed. No configured message currently has such a structure in its samples.
- **An MT text block does not say which message it is.** Where the `:16R:` skeleton fits
  more than one configured message — MT540–MT543 share `GENL/TRADDET/FIAC/SETDET` — import
  refuses and lists the candidates rather than picking one. A complete FIN message names
  itself in Block 2 and needs no help. The browser reveals a message picker only after the
  refusal, so the question is never asked of someone who does not need it.
- **"Any message" means: any message for which an authorised source and deterministic
  structure evidence exist, and only as far as the gates prove.** The configured lane is
  still 23 messages. The preview lane is as wide as the Prowide fixture plus whatever XSDs
  and guides the operator dropped in — 209 `GENERATION_READY` structures on 2026-08-20 —
  and a message without structural evidence (`KNOWLEDGE_ONLY`) can be searched but never
  generated. Preview packs carry structure only; Network Validated Rules, usage rules,
  market practice and client rules are not evaluated unless a reviewed Rule Pack is
  installed.
- **Retrieval over the real corpus is lexical.** Every real source is embedding-blocked by
  policy in the default configuration; the hybrid path is proven on the synthetic corpus
  and with a live probe, not on the licensed documents.
- **AI output is bounded, not deterministic.** The validator and composer decide what is
  accepted; a live model may propose different valid values on different days. The sample
  cache pins a validated answer; `KNOWLEDGE_AI_PROVIDER=scripted` pins the seed.
- **Not in the configured lane:** payments (`pacs.*`), cash management (`camt.*`),
  reconciliation (`semt.*`). Eight `pacs` XSDs compile to `GENERATION_READY` preview
  structures from the operator's XSDs; nothing `camt.*` or `semt.*` has been supplied.
- **The `22F::SETR` domain-rule gap is closed.** It used to render `//BUY` in Sequence B
  and `//RECE` in Sequence E; neither is a settlement transaction type, and the field
  belongs in Sequence E alone. Reconciled against `config/mx/sese.023.001.11.yaml` — this
  repository's own ISO 20022 definition of the same business message, which separates
  direction (`SctiesMvmntTp`), payment (`Pmt`) and transaction type (`SctiesTxTp`) and both
  formats now share one code list. What is still *not* established is whether that list is
  complete; the subset caveat applies to it unchanged.
- **RJE fails closed** — no authorised interchange contract exists here.
- Rate limits, AI circuit breaker and L1 cache are **per process**.
- No production identity-provider adapter; no KMS/HSM; no penetration test.

---

## 15. How to extend

| Task | What to do |
|---|---|
| Add a field to an MT message | One record in `backend/config/knowledge/*.yaml`. No code. |
| Add or change a code list | One entry in `backend/config/knowledge/code_lists.yaml`, referenced by `codeList:`. Labels reach the UI, the API, Excel and both formats at once. No code. |
| Change which control a field gets | It is derived in `app/knowledge/presentation.py` from the tag and field option. Override per record with `inputKind:` only where derivation genuinely cannot know. |
| Add an MT message | One manifest entry (`config/specifications/supported_subset_v1.yaml`: sequences, `workflowModule`, `shortDescription`) plus its field records in `config/knowledge/`. No code — `tests/specifications/test_dynamic_registry.py` proves it. |
| Compile an MX message from its schema | `make spec-compile SOURCE=schema.xsd` emits an ordinary `config/mx` pack, gated against the source schema. [specification-engine.md](specification-engine.md). |
| Add an MX message | One file in `backend/config/mx/`. Namespace must be `urn:iso:std:iso:20022:tech:xsd:<version>`. A node has `dataType` **or** `children`, never both. Document order = element order. **No code** — the four lifecycle messages were added this way and gained samples, Excel columns, search, import and XSD validation with no Python change. |
| Add a client profile | One file in `backend/config/profiles/`. No code. |
| Add a validation rule | `MtGenerator._business_rules` / `._profile_rules`, or `MxGenerator._business_rules`. Prefer configuration (`requireOneOf`) where possible. |
| Add an output format | `OutputMode` enum → produce in `StudioService` → extension in `routes.OUTPUT_FILE_TYPES`. |
| Add an endpoint | `app/studio/routes.py` → `lib/studio-types.ts` → `lib/studio-api.ts`. |
| Import a licensed spec, schema or client guideline | Drop the file in and point the matching setting at it. No code. [authoritative-sources.md](authoritative-sources.md) is the procedure; `GET /api/v1/sources` reports what is present. |
| Make another MT message testable from its Message Reference Guide | Put the PDF under `swiftKnowledgeBase/`, run `make knowledge-sync`, read its row in `GET /api/v1/knowledge/messages/{m}/status` or the readiness report. No code: identity comes from the PDF, structure from Prowide evidence reconciled with the guide, the lane is `KNOWLEDGE_PREVIEW`. If the row is not `GENERATION_READY` the blocker names the generic gate to fix. [knowledge-source-handling.md](knowledge-source-handling.md). |
| Make another MX message testable from its XSD | Put the `.xsd` (or a ZIP of them) under `swiftKnowledgeBase/`, run `make knowledge-sync`. The existing compiler and its six gates run; the pack lands in the preview lane. No code — the eight `pacs` messages were added this way. |
| Promote a preview structure into the configured lane | Not automatic, by design. Review the pack, commit it as ordinary `config/` YAML with its provenance, add the manifest entry; then the configured gates and golden files apply. |
| Add an AI operation | `app/ai_authoring/service.py` (compute the seed first) → a closed schema in `schemas.py` → the route → `lib/studio-types.ts` → `lib/studio-api.ts`. It must survive `KNOWLEDGE_AI_PROVIDER=scripted` and `disabled`. |

**Golden files** (`backend/tests/golden/expected/*.txt`) fail on any byte change to MT
output. That friction is deliberate: update the fixture in the same commit and say why.

---

## 16. Recommended next work

In value order on the current architecture:

1. **Close the ten `ROUND_TRIP_FAILED` MT structures** by fixing the generic parser path
   each gate names, and reduce the 69 `STRUCTURE_AVAILABLE` blockers
   (`QUALIFIER_EVIDENCE_MISSING` needs a guide for the message; `FORMAT_FIDELITY_PARTIAL`
   needs another pattern in `swift_format.py`). Every fix is generic and moves many rows.
2. **Phase 7 of the specification engine** ([plan](specification-engine-plan.md)): client
   MyStandards usage-guideline ingestion on top of the knowledge base, and the remaining
   MT542–MT548 guides already in the operator's drop directory as semantic-rule sources.
3. **Reconcile the four lifecycle specifications** against an authoritative ISO 20022
   message-definition report. They are shipped, generating and round-tripping, but flagged
   `UNVERIFIED`; this is the cheapest way to remove a caveat that applies to four of seven
   MX messages. The procedure and what to re-run are in
   [authoritative-sources.md](authoritative-sources.md).
4. **Import a licensed MT specification.** Still the only thing that changes what the
   platform may *claim*. The drop point and the setting exist; the YAML structure already
   fits.
5. **Drop official ISO 20022 XSDs into `backend/config/mx/xsd/official/`.** One folder, no
   code, MX validation becomes authoritative.
6. **Shared state for rate limiter and circuit breaker** before running more than one
   instance. Needs Redis or equivalent.
7. **Production OIDC/SAML adapter.** The boundary exists; the adapter does not.

## 17. Writing style expected in this repo

- Comments explain **why**, not what. A comment restating code is noise; one recording a
  decision, a constraint, or a fixed bug is why nobody reintroduces it.
- Tests are named after behaviour, assert on `ruleId` not prose, and parametrise over sets
  rather than picking a member. The whole backend suite runs in ~3s, so prefer real
  end-to-end assertions to mocks.
- Commit messages explain why. If a test caught the bug, say so. If a golden file changed,
  say why the output changed.
- User-facing copy uses the product's own language, never the standard's jargon. No "Oops",
  no exclamation marks.
