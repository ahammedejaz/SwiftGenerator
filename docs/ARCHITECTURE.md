# Architecture

How this thing is put together, and why.

If you read only one section, read **[The one big idea](#the-one-big-idea)**. Everything
else follows from it.

---

## The one big idea

A message is built from a **specification** plus **values**.

The specification says what fields exist, in what order, what each is called, what shape
its value must be, and whether it is required. It lives in YAML, not in code. The values
come from a person typing, a spreadsheet, or an HTTP request.

```
   SPECIFICATION                 VALUES
   (what a message looks like)   (what goes in it)
            │                         │
            └───────────┬─────────────┘
                        ▼
                    COMPOSER
                        │
                        ▼
                   THE MESSAGE
```

That is why adding a new field is a YAML edit, not a code change, and why the UI, the JSON
API and the Excel importer cannot disagree about what a message needs — they all read the
same specification and call the same composer.

---

## The shape of the whole thing

```
┌─────────────────────────────────────────────────────────────────────┐
│  BROWSER                    Next.js 16 · React 19 · Tailwind 4      │
│  Create · Excel · Intelligence · Validate · Automation · Convert    │
└───────────────────────────────┬─────────────────────────────────────┘
                                │  HTTP, always /api/v1
┌───────────────────────────────▼─────────────────────────────────────┐
│  FastAPI                                                            │
│                                                                     │
│   THREE DOORS IN, ONE ROOM BEHIND THEM                              │
│   ┌──────────┐  ┌───────────┐  ┌─────────────┐                      │
│   │ Browser  │  │ JSON API  │  │ Excel upload│                      │
│   └────┬─────┘  └─────┬─────┘  └──────┬──────┘                      │
│        └──────────────┼───────────────┘                             │
│                       ▼                                             │
│              StudioService                    ← everything meets    │
│                       │                          here               │
│         ┌─────────────┴─────────────┐                               │
│         ▼                           ▼                               │
│   ┌───────────┐               ┌───────────┐                         │
│   │ MT branch │               │ MX branch │                         │
│   ├───────────┤               ├───────────┤                         │
│   │ resolve   │               │ resolve   │  find the field         │
│   │ validate  │               │ validate  │  is the value legal?    │
│   │ compose   │               │ compose   │  write it out           │
│   │ FIN wrap  │               │ AppHdr    │  wrap it up             │
│   └─────┬─────┘               └─────┬─────┘                         │
│         │                           │                               │
│         │                           ▼                               │
│         │                      XSD check (libxml2)                  │
│         └─────────────┬─────────────┘                               │
│                       ▼                                             │
│                  GenerateResult                                     │
│         message · validation · checksum · origins                   │
│                       │                                             │
│                       ▼                                             │
│                 studio_messages (SQLite / PostgreSQL)               │
└─────────────────────────────────────────────────────────────────────┘
```

**MT and MX never share a rendering path.** MT code cannot produce XML; MX code cannot
produce FIN blocks. They meet only at the service that dispatches to them and at the result
they both return. That separation is deliberate: the two standards are genuinely different,
and blending them would produce plausible nonsense.

Since Phase 6 there is a second thing beside that room, not inside it:

```
   swiftKnowledgeBase/  (operator's PDFs, XSDs, ZIPs — ignored by Git)
            │  make knowledge-sync            ← offline; the only thing that opens a source
            ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  KNOWLEDGE BASE            build/knowledge/ (ignored)         │
   │  identify → segment → SQLite + FTS5 → embed (policy) →        │
   │  compile local Structure Packs (MT from Prowide + MRG,        │
   │  MX from XSD) and gate each one                               │
   └──────────┬──────────────────────────────┬────────────────────┘
              │ read at runtime              │ read at runtime
              ▼                              ▼
      /api/v1/knowledge              KNOWLEDGE_PREVIEW lane
      /api/v1/ai  (RAG, AI authoring)        │ only when a caller names it
              │ proposes values              ▼
              └──────────────────►  the same StudioService, composer,
                                    validator, XSD check and result
```

The knowledge base is retrieval, index and cache state. It is never validation authority.
Structure Packs define structure, reviewed Rule Packs define semantic validation, the
composer builds FIN and XML, and the deterministic endpoints never call into it.

Conversion sits beside authoring, not inside either renderer:

```
raw/canonical MT -> ordinary MT parser -> exact Mapping Pack
                                      -> business semantic values
                                      -> target canonical MX values
                                      -> ordinary StudioService -> XML/XSD result
```

Mapping Packs are a fourth configuration type beside Structure, Rule and Presentation
Packs. They own only semantic transformation. Every pack has evidence/review provenance;
missing target facts return `NEEDS_INPUT`, and source loss is part of the response. A model
cannot activate a Mapping Pack or make the deterministic target valid.

Catalogue startup is split deliberately: the browser first requests the configured
projection, which does not touch knowledge, then enriches it with the cached preview
projection. See [universal-message-runtime.md](universal-message-runtime.md).

---

## Following one request all the way through

Say a tester presses **Generate** on an MT541.

**1. The browser sends what it has.**

```json
POST /api/v1/messages/generate
{
  "format": "MT",
  "messageType": "MT541",
  "profileId": "BASE_DEMO_V1",
  "fields": [
    { "sequence": "GENL", "tag": "20C", "qualifier": "SEME", "value": "TESTREF001" },
    { "sequence": "TRADDET", "tag": "98A", "qualifier": "SETT", "value": "20260818" }
  ]
}
```

**2. `StudioService` picks the branch** — `format: "MT"` → the MT generator.

**3. Resolve: which field is this?**
`MtGenerator.resolve()` turns `GENL / 20C / SEME` into the specification row
`MT541-A-20C-SEME`. You can address a field either way — by that row id, or by the
sequence/tag/qualifier triple an automation tester keeps in a spreadsheet. An address that
matches nothing becomes a named error, never a silent omission.

**4. Validate, in layers.** Each layer is reported separately, so you can see exactly
where a message went wrong:

| Layer | Question it answers |
|---|---|
| `CANONICAL` | Do these inputs even address real fields? |
| `STRUCTURE` | Is everything required present? |
| `FORMAT` | Does each value match its expected shape? |
| `BUSINESS_RULES` | Do the values make sense *together*? (settlement date after trade date) |
| `CLIENT_PROFILE` | Does this client allow this currency, this reference length? |
| `FIN_ENVELOPE` | Can we build a real envelope, or are we missing interface values? |

MX adds three more: `XML_WELL_FORMED`, `XSD`, `APPHDR_CONSISTENCY`.

**5. Compose Block 4.** `SpecificationComposer` writes the tags in specification order,
opening and closing each sequence with `:16R:` / `:16S:`. This class predates the studio
and is reused unchanged — it was already correct and already tested.

**6. Wrap it in a FIN envelope.** Blocks 1, 2, optional 3 and optional 5, built from
values configured on the client profile. See [Nothing is invented](#nothing-is-invented).

**7. Return everything.** The message in several output formats, the validation report,
a SHA-256 checksum, and an origin label for every envelope value.

---

## The parts, and what each one owns

### Specifications — what a message looks like

```
backend/config/knowledge/*.yaml     MT: what each tag means, in business language
backend/config/specifications/      MT: which sequences and rows each message has
backend/config/mt_prowide_*.yaml    MT: pinned Prowide structural-evidence locks
backend/config/mx/*.yaml            MX: the full element tree
backend/config/profiles/*.yaml      Per-client settings and envelope values
backend/config/rules/*.yaml         Reviewed business rules: base, market practice, client
backend/config/rule_sources/        The documents rules were derived from (synthetic only here)
swiftKnowledgeBase/                 Operator's authorised sources for the knowledge base (ignored)
build/knowledge/packs/              Local Structure Packs the sync compiled (ignored, preview lane only)
```

**MT** is defined in two halves. The *knowledge base* describes each tag once — meaning,
why it is used, format, examples, common mistakes — and lists which messages use it. The
*specification registry* says which sequences a message has and in what order. Joining them
gives the ordered list of rows for a message.

The Prowide MT structure importer lives beside the specification engine, not in the
runtime path. It downloads pinned Prowide Core artifacts into ignored `build/` directories,
extracts structural evidence for every MT source model discovered in the pinned artifact,
writes a deterministic fixture, and renders reports comparing that evidence with the
configured MT subset. It does not install candidate messages or rewrite the manifest. See
[mt-structure-importer.md](mt-structure-importer.md).

**MX** is one nested tree per message. Document order in the YAML *is* element order in the
XML, so there is exactly one place where order is defined:

```yaml
- name: SttlmDt
  displayName: Settlement Date
  presence: MANDATORY
  children:
    - name: Dt
      presence: MANDATORY
      children:
        - name: Dt
          displayName: Intended Settlement Date
          presence: MANDATORY
          dataType: ISODate
          businessPath: trade.settlementDate
          businessMeaning: The calendar date on which settlement is intended to occur.
          examples:
            - value: "2026-08-18"
              explanation: A synthetic intended settlement date.
```

Everything the UI shows about that element — the label, the help text, the example, the
format hint — comes from those lines. Nothing about it is written in TypeScript.

### The studio layer — `backend/app/studio/`

| File | Owns |
|---|---|
| `models.py` | The request and response shapes shared by every entry point |
| `catalogue.py` | "What can I generate?" and the format-neutral view of a specification |
| `service.py` | Dispatch, layer assembly, output selection — the room behind the three doors |
| `routes.py` | The `/api/v1` HTTP surface |
| `security.py` | `X-API-Key` service authentication |
| `samples.py` | Sample data in three depths |
| `excel.py` | Template generation and workbook parsing |
| `intelligence.py` | The search index over MT tags and MX elements |
| `store.py` | Recent messages |
| `mt/generator.py` | MT address resolution, validation, rendering |
| `mt/fin.py` | The FIN envelope |
| `mx/registry.py` | Loads and flattens MX specifications |
| `mx/generator.py` | MX composition, validation, AppHdr |
| `mx/xsd.py` | Schema validation |

### The knowledge base — `backend/app/knowledge_base/`

| File | Owns |
|---|---|
| `discovery.py` | Which files exist under the roots and whether they are safe to read: no symlinks, ZIP limits, never writes a source |
| `identify.py` | What a file *is*, from its content — an MRG's cover page, an XSD's namespace — never from its name |
| `chunking.py` | Stable segments with a section label and a page number |
| `db.py` | The SQLite schema: sources, paths, segments, FTS5, embeddings, runs, structures |
| `index.py` | The incremental sync; checksums decide what is re-read |
| `embeddings.py` · `vector_store.py` | Provider-neutral embedding adapter and NumPy cosine over stored vectors |
| `policy.py` | Whether a source's text may leave the machine. Two gates, default closed |
| `retrieval.py` | Lexical + semantic → reciprocal rank fusion. Deterministic |
| `structures/` | Local Structure Packs: MT from Prowide evidence reconciled with MRG tables, MX from XSD through the existing compiler; gates and readiness |
| `preview.py` | Loads those packs into the `KNOWLEDGE_PREVIEW` lane — separate registry instances of the runtime types |
| `service.py` | The one runtime door: status, search, caches, telemetry |
| `reports.py` | The three generated readiness reports |

### AI authoring — `backend/app/ai_authoring/`

| File | Owns |
|---|---|
| `service.py` | identify · prepare · samples · test data · presentation · ask · releases/compare — each computes a deterministic seed first |
| `provider.py` | The structured-completion provider: organisation endpoint, OpenRouter, or the `scripted` stand-in |
| `prompts.py` | Prompt templates; retrieved text is fenced as untrusted evidence |
| `schemas.py` | The closed JSON schema every model answer must satisfy |

### The layers underneath — reused, not rewritten

The studio sits on top of code that already existed and already had tests:

- `app/specifications/registry.py` — the MT specification registry
- `app/knowledge/loader.py` — the MT knowledge base
- `app/authoring/composer.py` — the Block 4 composer
- `app/profiles/loader.py` — client profiles
- `app/domain/`, `app/composers/`, `app/workflows/` — the original scenario-shaped API,
  still serving the Advanced screens

None of that was modified to make the studio work. The studio adds a second, field-level
door into the same specifications.

### The frontend — `frontend/`

```
app/                    one folder per route
components/studio/      the studio components (incl. KnowledgeBase.tsx, reached from Advanced)
components/ai/          AI Efficiency panels, incl. knowledge telemetry
components/<other>/     the pre-existing Advanced screens
lib/studio-types.ts     TypeScript mirror of the API contract
lib/studio-api.ts       the typed client — the only place fetch() is called
```

`ProofSheet.tsx` is the component that matters most: it renders the generated message on a
dark surface with line numbers and margin annotations naming the business field each line
came from. See [DESIGN.md](DESIGN.md) for why it looks the way it does.

---

## Nothing is invented

This is a rule, not a preference, and it is enforced in code.

Every value in a generated message carries an **origin**:

| Origin | Meaning | Does the platform produce it? |
|---|---|---|
| `USER_ENTERED` | You typed it | yes |
| `PROFILE_CONFIGURED` | Someone configured it on the client profile | yes |
| `APPLICATION_GENERATED` | Derived from your choices (the `541` in Block 2) | yes |
| `INTERFACE_GENERATED` | A real SWIFT interface assigns it | **never** |
| `NETWORK_GENERATED` | The SWIFT network adds it in transit | **never** |

So:

- **Session and sequence numbers** in Block 1 must be configured on the profile or supplied
  on the request. If they are neither, FIN output **fails closed** with an error naming
  exactly what is missing. It does not pick a plausible number.
- **Block 5 trailers** (MAC, CHK, PDE, …) are refused outright, even if a profile asks for
  them. They are authentication and checksums the network computes.
- **The MX transport wrapper** — the element that carries an `AppHdr` and a `Document`
  together — is a market convention, not part of ISO 20022. It comes from the profile. No
  profile, no wrapper.
- **`Sgntr`** (digital signature) is never written.

The Create Message screen shows this table, including the rows where the value is blank
and the reason it is blank.

---

## Rules are configuration too — `backend/app/rule_engine/`

Structure is one authority; business rules are another. A **rule pack** says what a valid
*use* of an already-valid structure looks like — and reads structure without ever writing
it, which is a property of the architecture rather than a promise: there is no writer in
the package at all.

```
Structure          elements, order, cardinality, datatype, code set
   ↓
BASE_STANDARD  →  MARKET_PRACTICE  →  CLIENT_PROFILE      each may narrow, never widen
   ↓
Effective rules → deterministic evaluator → ValidationIssue[], each naming its layer
```

Every layer runs; none suppresses another. A contradiction between layers is reported with
both rule identifiers at *installation*, not when a tester eventually trips over it.

Rules become active the way any configuration does. An offline pipeline reads a source
document, segments it deterministically, asks two isolated model passes for candidates from
a closed vocabulary, compares them without picking a side, attacks them with a refuter, and
runs them through the same compiler that guards an installed pack. What comes out is a
*candidate* — and the registry loads only reviewed, source-controlled packs, refusing
rather than skipping anything else. Runtime evaluation calls no model at all.

MT semantic-rule ingestion uses that same path with MT source metadata, canonical
Prowide-derived structural references and runtime row-id compilation. The canonical
`MT:SR2025:...` reference is provenance only; installed rules still point at existing MT
row ids such as `MT541-E-22F-SETR`. Phase 5A ships no real MT semantic source and no
runtime MT Rule Pack. See
[mt-semantic-rule-ingestion.md](mt-semantic-rule-ingestion.md).

Phase 5C adds occurrence-aware evaluation to the same engine. `rule-dsl/2` can scope an
assertion to each occurrence of a repeating sequence or subsequence, carrying parent
lineage when repeats are nested. The feature is internal rule-evaluation state: it does not
write MT structures, does not load SR2026 candidate packs, and does not make Java, Prowide,
Maven or Gradle part of the FastAPI runtime. The SR2026 MT540/MT541 candidate evaluator
uses it offline to prove same-occurrence behaviour while all candidates remain
`REVIEW_REQUIRED`.

See [specification-rule-engine.md](specification-rule-engine.md).

---

## Two ways to validate MX, and why

XSD validation runs against one of two schemas, and the response always says which:

| Source | Where it comes from | What it proves |
|---|---|---|
| `OFFICIAL` | An `.xsd` you drop into `backend/config/mx/xsd/official/` as the official artifact | Conformance to that supplied schema. Whether the file is the genuine ISO artifact is your responsibility under your licence — the platform cannot verify it |
| `SUBSET_DERIVED` | Generated at runtime from the YAML specification | The document matches *this repository's* subset |

`SUBSET_DERIVED` is the default because the official schemas are licensed and not in this
repository. It is a real XSD compiled by libxml2 — it independently catches element order,
cardinality, datatypes, enumerations and required attributes. It is **not** authoritative
conformance, and the tool never claims it is.

Drop an official schema in and the validator prefers it automatically. Nothing else changes.

---

## Authentication: two separate models

An automation framework should not have to drive a login screen. A human should not have to
hold a long-lived key. So there are two models and they do not overlap:

| | Interactive | Automation |
|---|---|---|
| Who | A person in a browser | A test suite or pipeline |
| How | Session cookie + CSRF + roles | `X-API-Key` header |
| Where | `/api/messages/drafts`, `/api/auth/*` | `/api/v1/*` |
| Config | `SESSION_HMAC_SECRET` | `AUTOMATION_API_KEYS` |

In development, `/api/v1` is **open** — that is what makes a fresh clone usable with no
setup. Set `APP_ENV` to anything else and it closes until `AUTOMATION_API_KEYS` is set.
Keys come only from the environment and never appear in a response, a log line or the
source.

---

## Where AI fits (and where it does not)

The AI layer interprets **intent**. That is all.

```
"I bought 1000 shares, settling Tuesday against payment"
                    │
                    ▼
              AI interpretation      ← the only thing a model does
                    │
                    ▼
    { direction: RECEIVE, paymentType: AGAINST_PAYMENT, ... }
                    │
                    ▼
        deterministic code from here on
```

A model never renders a message, never validates one, never parses one, never reads a
spreadsheet and never builds XML. If the AI layer is switched off entirely — which it is by
default — you lose the convenience features and nothing else.

Phase 6 widened what the model may *propose* without moving that line:

```
"Set up a receive-against-payment for 1,000 XS0000000009 settling Tuesday"
                    │
                    ▼
   identify the message ─── from the discovered catalogue only; never a type it was not given
                    │
                    ▼
   prepare values ───────── for fields the Structure Pack declares; nothing else may appear
   (MINIMAL / TYPICAL / FULL samples, bulk test data)
                    │          ▲
                    ▼          │  validator findings, at most KNOWLEDGE_AI_MAX_REPAIR_ATTEMPTS times
   deterministic validator ────┘
                    │
                    ▼
   deterministic composer → FIN / XML → the same GenerateResult as any other caller
                    │
                    ▼
   validated-sample cache    (a second identical request makes zero model calls)
```

Where a model needs to know what a standard says, it is shown **retrieved excerpts with
citations** from the local knowledge base — fenced as untrusted evidence, inside a closed
answer schema — and only excerpts whose source policy allows the text to leave the machine.
A blocked source is cited by document, page and section without being quoted.

Every AI operation first computes a deterministic seed. With `KNOWLEDGE_AI_PROVIDER=scripted`
(development and test only) the seed *is* the answer, which is how CI and Playwright
exercise these screens with no key. With no provider configured the operations fall back to
the seed. The deterministic endpoints — generate, validate, import, diff, Excel — never call
a model or the knowledge base, whatever is configured.

When AI is used, the order is **deterministic → cache → model**, so a repeated question
costs nothing. The AI Efficiency screen shows live calls, cache hits, tokens, cost where the
provider reports it, latency, how much was avoided, and — since Phase 6 — embedding and
retrieval telemetry.

---

## Data

One additive table, `studio_messages`, holds recently generated messages so a tester can
download one again without rebuilding the scenario. It trims itself: 500 rows or 30 days,
whichever comes first. It is a working surface, not a system of record.

SQLite by default. PostgreSQL is required when `APP_ENV=production`, enforced in
`app/config.py`.

Everything else in the database belongs to the pre-existing authoring stack (drafts,
approvals, audit, AI telemetry) and is untouched by the studio.

The knowledge base has its **own** SQLite file, `build/knowledge/knowledge.sqlite3` by
default (`KNOWLEDGE_DB_PATH`), beside the compiled packs and the extracted source cache. It
is derived entirely from the operator's sources and is rebuilt by `make knowledge-sync`; it
is ignored by Git, as are the sources. What *is* committed is code, the synthetic fixture
corpus the tests index, and three generated reports that record counts and checksums but no
source text. There is no migration for it: the schema is created on first use and carries
`KNOWLEDGE_SCHEMA_VERSION`.

---

## Adding things

**A new field on an existing MT message**
Add a record to the right file in `backend/config/knowledge/`. It appears in the API, the
UI, the Excel template and Message Intelligence with no code change.

**A new MX message**
Add one YAML file to `backend/config/mx/`. The registry picks it up, the catalogue lists
it, samples generate themselves, the Excel template gains a sheet, and the derived XSD is
built from it. Still no code change.

Or let the specification engine write that file for you: `make spec-compile
SOURCE=schema.xsd` compiles an ISO 20022 schema into the same format, proves a generated
sample against the source schema, and records the schema's checksum in the pack. The
running application never compiles anything — packs arrive like any other configuration,
through review and commit. See [specification-engine.md](specification-engine.md).

**A new MT message**
One entry in `backend/config/specifications/supported_subset_v1.yaml` (sequences, owner
module, description) plus its field records in `backend/config/knowledge/`. The manifest
is the single authority for which MT messages exist — there is no message list in code.

Prowide-derived candidates can inform that review, but they do not replace it. Run
`make verify-prowide-mt-source`, inspect
[generated/mt-prowide-structure-diff.md](generated/mt-prowide-structure-diff.md), then
make a separate source-backed runtime change if a candidate should be promoted.

**A new validation rule**
Prefer configuration. A reviewed rule pack in `backend/config/rules/` expresses a
conditional requirement, a prohibition, a code restriction, a date relation or a
cross-field dependency declaratively, carries the source location that established it, and
applies to the browser, the JSON API and the Excel path through one call site. See
[rule-pack-format.md](rule-pack-format.md).

For MT semantic rules, first declare and ingest an authorised source in
`backend/config/rule_sources/` or an override directory, then use `make mt-rule-check` to
verify readiness and the synthetic MT corpus. Without a real source, the MT path stays
foundation-only.

The older hand-written rules still live in `MtGenerator._business_rules` /
`._profile_rules` and `MxGenerator._business_rules`, and `requireOneOf` in the MX YAML is
a third, narrower form of the same idea. Nothing was migrated: those rules are working,
tested and unaffected by the engine.

**A new output format**
Add it to `OutputMode`, produce it in `StudioService`, and give it a file extension in
`routes.OUTPUT_FILE_TYPES`.

**Another MT message, from its Message Reference Guide, without code**
Put the PDF under `swiftKnowledgeBase/` and run `make knowledge-sync`. The sync identifies
it from its own cover page, indexes it for search, and compiles a Structure Pack from the
pinned Prowide evidence reconciled with the guide's Format Specifications. The pack is
gated — load, sample, validate, compose, parse, round trip — and lands in the
`KNOWLEDGE_PREVIEW` lane with a readiness the gates decided. `GET
/api/v1/knowledge/messages/{m}/status` and
[generated/universal-message-readiness.md](generated/universal-message-readiness.md) show
the row and, where it is not `GENERATION_READY`, the exact blocker. Nothing is promoted into
the configured lane; that stays a reviewed commit. See
[knowledge-source-handling.md](knowledge-source-handling.md).

**Another MX message, from its XSD, without code**
Put the `.xsd` (or a ZIP of schemas) under `swiftKnowledgeBase/` and run
`make knowledge-sync`. The same compiler and six gates that produce a committed pack run
against it, and the result is served in the preview lane. The eight `pacs` messages were
added exactly this way.

---

## Deliberate non-goals

No microservices. No message broker. No Kubernetes. No service mesh.

Two processes and a database. A developer who has never seen this repository should be able
to follow a request from the browser to the generated message in one sitting — which is
what this document is for.
