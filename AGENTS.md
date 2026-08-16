# Repository context for AI agents

Orientation document for an AI tool working on this repository. Dense and factual by
design. Human-facing docs are [README.md](README.md), [ARCHITECTURE.md](ARCHITECTURE.md),
[CONTRIBUTING.md](CONTRIBUTING.md) and [docs/](docs/README.md).

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

**Verification status (all passing):**

```
757 backend tests (pytest)      ruff: clean      mypy --strict: clean (129 files)
 61 browser tests (Playwright)  eslint: clean    tsc --noEmit: clean
CI: five jobs on every PR and every push to main   see §11
production build: clean         migrations: up/down/up clean
docker: both images build, compose stack serves all flows
secret scan: clean in tree and in git history
clean clone, no .env, no keys: install -> migrate -> check -> e2e, and docker, all green
released as v0.1.0
```

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
              │
        studio_messages table
```

---

## 5. File map

### Backend — the studio layer (new, ~5,800 LOC)

```
backend/app/studio/
  models.py         request/response contracts shared by every entry point
  catalogue.py      "what can I generate?" + format-neutral specification projection
  service.py        dispatch, layer assembly, output selection   ← the hub
  routes.py         /api/v1 (18 endpoints)
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

### Backend — reused unchanged (predates the studio, already tested)

```
app/specifications/registry.py   MT specification registry
app/knowledge/loader.py          MT knowledge base
app/authoring/composer.py        Block 4 composer          ← reused, do not fork
app/profiles/loader.py           client profiles
app/domain/ app/composers/ app/workflows/   original scenario API, serves Advanced screens
app/agents/                      AI layer (optional, off by default)
```

### Configuration — the actual source of truth

```
backend/config/README.md               what each directory is, and its override setting
backend/config/knowledge/*.yaml        MT: per-tag meaning, format, examples, mistakes
backend/config/specifications/*.yaml   MT: sequences and row order per message
backend/config/mx/*.yaml               MX: complete nested element tree, one per message
backend/config/mx/xsd/official/        drop licensed .xsd files here; see its README
backend/config/profiles/*.yaml         client profiles: currencies, rules, envelope values
```

Each of those four locations has a setting that redirects it — `MT_SPECIFICATION_MANIFEST`,
`MX_SPECIFICATION_DIRECTORY`, `MX_OFFICIAL_XSD_DIRECTORY`, `CLIENT_PROFILE_DIRECTORY` — so a
licensed artifact is a drop-in, not a code change. Unset means "the configuration committed
here", which is what keeps a clean clone working with no environment.
[docs/authoritative-sources.md](docs/authoritative-sources.md) is the procedure.

### Frontend (new, ~4,800 LOC)

```
frontend/components/studio/
  Chrome.tsx           app shell, 6-item nav
  CreateMessage.tsx    the six-step wizard
  FieldEditor.tsx      progressive disclosure + inline field explanations
  ProofSheet.tsx       the generated message — dark, line-numbered, annotated
  MessageDiff.tsx      original vs regenerated, and why each line differs
  ValidationPanel.tsx  plain-English validation
  ExcelStudio.tsx  Intelligence.tsx  ValidateStudio.tsx  Automation.tsx  RecentMessages.tsx
  Icon.tsx  ui.tsx     authored SVG icons + the component vocabulary
frontend/lib/studio-types.ts   TypeScript mirror of the API contract
frontend/lib/studio-api.ts     typed client — the ONLY place fetch() is called
frontend/app/{,excel,intelligence,validate,automation,recent,advanced}/page.tsx
```

### Demonstration and release

```
demo/                                  synthetic pack, generated — never hand-written
CLIENT_DEMO_RUNBOOK.md                 the twenty-minute walkthrough
AUTHORITATIVE_ARTIFACT_CHECKLIST.md    what a client must supply, and what it unlocks
V0_1_0_RELEASE_READINESS_REPORT.md     what was verified for the v0.1.0 baseline
```

### Tests

```
backend/tests/studio/test_fin_envelope.py     envelope correctness + refusal rules
backend/tests/studio/test_mt_generation.py    addressing, validation, output modes
backend/tests/studio/test_mx_generation.py    namespace, order, choice, XSD, AppHdr
backend/tests/studio/test_mt_import.py        the MT round trip, and every refusal
backend/tests/studio/test_mx_import.py        the MX round trip, and every refusal
backend/tests/studio/test_coverage_and_sources.py  coverage is measured, not declared
backend/tests/studio/test_message_diff.py     every difference is attributed correctly
backend/tests/studio/test_mx_lifecycle.py     the four cancellation/modification messages
backend/tests/studio/test_excel_api.py        templates, parsing, upload guards
backend/tests/studio/test_studio_api.py       the /api/v1 contract
backend/tests/security/test_cors_and_throttling.py  short-circuit responses stay readable
backend/tests/unit/test_database_concurrency.py    the in-memory engine under threads
backend/tests/unit/test_setup_from_a_clean_clone.py  make migrate works on a new machine
frontend/tests/e2e/studio-create.spec.ts      the manual journey
frontend/tests/e2e/studio-import.spec.ts      import round trip + lifecycle in the browser
frontend/tests/e2e/message-diff.spec.ts       the comparison a tester actually reads
frontend/tests/e2e/studio-screens.spec.ts     other screens + responsive + a11y
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

Business rules currently enforced: settlement date not before trade date · `APMT` requires
an amount, `FREE` forbids one · MX receipt must name the delivering chain · cancellation
requires a previous reference · status advice must report at least one status
(`requireOneOf`, expressed as **configuration** not code) · amount positive.

---

## 8. XSD: two schema sources

| Source | Origin | Proves |
|---|---|---|
| `OFFICIAL` | a `.xsd` in `backend/config/mx/xsd/official/` | real conformance |
| `SUBSET_DERIVED` | generated at runtime from the YAML | matches *this repo's* subset |

`SUBSET_DERIVED` is the default (official schemas are licensed, not included). It is a real
XSD compiled by libxml2 and independently catches element order, cardinality, datatypes,
enumerations and required attributes — tests prove each. It is **not** conformance and the
tool never claims it is. The response always reports which was used.

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

The model does **one** thing: turn natural language into structured intent.

It never renders, validates, parses, reads a spreadsheet, builds XML, or looks up a tag.
Message Intelligence is deterministic dictionary lookup — a Playwright test watches network
traffic and asserts no model call is made.

`AI_PROVIDER=disabled` is fully supported and loses only the "describe a scenario in
English" screen. Order when enabled: **deterministic → cache → model**.

---

## 11. Continuous integration

`.github/workflows/ci.yml`. Runs on every pull request to `main`, every push to `main`, and
on demand. **Python 3.13, Node 22** — the same versions this repository targets locally.

| Job | What it runs | On |
|---|---|---|
| **Required Checks** | `make install` → `make check` → `make secret-scan` → `git diff --check` | PR, main |
| **Clean Clone** | `make install` → `make migrate` → `make check`, from git-tracked files only | PR, main |
| **Browser E2E** | `make e2e`; report, traces and screenshots uploaded **on failure only** | PR, main |
| **Docker** | `docker compose config --quiet` → `docker compose build`. Nothing is pushed | PR, main |
| **Security Audit** | `make audit` — `pip-audit` and `npm audit --omit=dev` | PR, main |

**Reproduce any job locally by running the same make target.** The workflow adds only what a
runner needs that a laptop does not: the browser's OS libraries (`--with-deps`, which needs
sudo and would be wrong on a developer machine), and a base ref so `git diff --check` has a
range — bare `git diff --check` compares the worktree to the index and is always clean in CI.

Things worth knowing before editing it:

- **`CI / Required Checks` is the name branch protection should require.** Renaming that job
  silently disables the gate.
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
docker compose up --build
```

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

**Middleware and HTTP**

16. **`app.add_middleware` prepends.** The last registration is the *outermost*. CORS was
    registered first and therefore ended up innermost, so every short-circuit response from
    the request-context middleware — 400, 413, 429 — reached the browser with no
    `Access-Control-Allow-Origin`. `fetch()` rejects such a response with a bare network
    error, so a throttled tester was told the backend was down. Keep the CORS registration
    last, and keep `tests/security/test_cors_and_throttling.py`.
17. **Do not rate-limit CORS preflight.** A preflight is browser overhead the caller never
    chose to send; throttling it fails the real request with an unexplainable CORS error and
    defends nothing, because a non-browser client never sends one.

**Environment**

18. **`next dev` writes its own `AGENTS.md`, and will write it here if `frontend/AGENTS.md`
    is missing.** `node_modules/next/dist/server/lib/generate-agent-files.js` walks up to the
    project root when it cannot find its file, and it **replaces** rather than merges — this
    document was reduced to nine lines of Next boilerplate once. Keep `frontend/AGENTS.md`
    committed; it is Next's target and it is what protects this file.
19. **Playwright's `reuseExistingServer` will reuse whatever is on port 8000**, including a
    backend you started by hand — which has a *different environment*. `playwright.config.ts`
    passes `DATA_ENCRYPTION_KEY` and `SESSION_HMAC_SECRET`; a hand-started server reads
    `.env` instead, and the encrypted-draft and guided specs then fail for reasons that have
    nothing to do with the change under test. It will also happily reuse a **stale** backend
    started before your change. Stop your own servers before `make e2e`.

20. **`localhost` is not an address, and on a dual-stack machine it resolves to `::1`
    first.** The backend binds `127.0.0.1`, so a browser `fetch()` to `http://localhost:8000`
    occasionally died with `ECONNREFUSED ::1:8000` — which reaches `fetch()` as a bare
    network error and reads as "the backend is down". It surfaced as an unrelated e2e test
    failing about one run in three. macOS binds `--host ::` as IPv6-*only*, so listening on
    both is not the fix; matching the address is. Everything the app and the tests call now
    uses `127.0.0.1`, and CORS accepts both spellings of the origin.

**Tests**

21. **The demonstration rate limit is per process, and each suite shares one.** Whether a
    run passed depended on how many requests it happened to make; growing either suite
    eventually tipped it over and produced 429s in files with nothing to do with throttling.
    `tests/conftest.py` and `playwright.config.ts` both raise the ambient limit. The
    throttle is still tested — `tests/security/test_cors_and_throttling.py` installs its own
    limiter, which is the only place the limit is the subject rather than the scenery.
22. **A loose `getByRole("heading", {name})` can pass on the page `<h1>`.** One e2e
    assertion meant to check a generated MT537 was matching the page title instead, and only
    failed strict mode once the real heading also rendered — so it passed or failed on
    timing. Use `exact` and `level` when a page and its result share a word.
23. **Hardcoded catalogue counts turn "someone added a YAML file" into a failure that says
    nothing.** Derive counts from the registries.

**Comparing two messages**

24. **An expected difference presented as a fault trains the tester to ignore all of them.**
    A regenerated message almost always differs from the pasted one, and almost always
    harmlessly. Every difference therefore carries a reason, and only `UNEXPLAINED` and
    `IMPORT_DROPPED` are counted as worth acting on. A Block 5 trailer or an MX `Sgntr` is
    `NOT_REPRODUCED` and is never an application error.
25. **Never label a difference you cannot account for as normalisation.** `UNEXPLAINED`
    exists for exactly the case the comparison is there to surface; a comfortable-sounding
    default would hide it.
26. **MX must be compared on a canonical serialisation, MT on raw lines.** Re-indenting an
    ISO 20022 document changes nothing about the message, but in FIN the line structure *is*
    the message. Normalising MT before comparing would hide a real defect.

**Coverage reporting**

27. **A declared coverage figure reports the flag, not the truth.** The Excel reference
    sheet was once hardcoded to three MX messages while the registry held seven, and a
    `composer_supported`-style flag would have said 100%. Every figure in
    `app/studio/coverage.py` is measured by asking the component what it produced.
28. **The coverage document is gated by `make check`, so it must be deterministic.** Render
    counts, never values: sample dates move with the clock and would fail the build on an
    unrelated commit. A test renders it twice and compares.

---

## 14. Known limitations

Full list: [docs/limitations.md](docs/limitations.md).

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
- **Not implemented:** payments (`pacs.*`), cash management (`camt.*`), reconciliation
  (`semt.*`).
- **Documented domain-rule gap:** the configured MT subset renders `:22F::SETR//BUY` in
  Sequence B and `:22F::SETR//RECE` in Sequence E. Authoritatively `22F::SETR` belongs in
  Sequence E only and direction is implied by the message type. Recorded rather than
  silently corrected — fixing it needs an authoritative source, not a guess.
- **RJE fails closed** — no authorised interchange contract exists here.
- Rate limits, AI circuit breaker and L1 cache are **per process**.
- No production identity-provider adapter; no KMS/HSM; no penetration test.

---

## 15. How to extend

| Task | What to do |
|---|---|
| Add a field to an MT message | One record in `backend/config/knowledge/*.yaml`. No code. |
| Add an MX message | One file in `backend/config/mx/`. Namespace must be `urn:iso:std:iso:20022:tech:xsd:<version>`. A node has `dataType` **or** `children`, never both. Document order = element order. **No code** — the four lifecycle messages were added this way and gained samples, Excel columns, search, import and XSD validation with no Python change. |
| Add a client profile | One file in `backend/config/profiles/`. No code. |
| Add a validation rule | `MtGenerator._business_rules` / `._profile_rules`, or `MxGenerator._business_rules`. Prefer configuration (`requireOneOf`) where possible. |
| Add an output format | `OutputMode` enum → produce in `StudioService` → extension in `routes.OUTPUT_FILE_TYPES`. |
| Add an endpoint | `app/studio/routes.py` → `lib/studio-types.ts` → `lib/studio-api.ts`. |
| Import a licensed spec, schema or client guideline | Drop the file in and point the matching setting at it. No code. [docs/authoritative-sources.md](docs/authoritative-sources.md) is the procedure; `GET /api/v1/sources` reports what is present. |

**Golden files** (`backend/tests/golden/expected/*.txt`) fail on any byte change to MT
output. That friction is deliberate: update the fixture in the same commit and say why.

---

## 16. Recommended next work

In value order on the current architecture:

1. **Reconcile the four lifecycle specifications** against an authoritative ISO 20022
   message-definition report. They are shipped, generating and round-tripping, but flagged
   `UNVERIFIED`; this is the cheapest way to remove a caveat that applies to four of seven
   MX messages. The procedure and what to re-run are in
   [docs/authoritative-sources.md](docs/authoritative-sources.md).
2. **Import a licensed MT specification.** Still the only thing that changes what the
   platform may *claim*. The drop point and the setting exist; the YAML structure already
   fits.
3. **Drop official ISO 20022 XSDs into `backend/config/mx/xsd/official/`.** One folder, no
   code, MX validation becomes authoritative.
4. **Fix `22F::SETR` placement** once §14's authoritative source exists.
5. **Shared state for rate limiter and circuit breaker** before running more than one
   instance. Needs Redis or equivalent.
6. **Production OIDC/SAML adapter.** The boundary exists; the adapter does not.

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
