# Overnight Implementation Report

**Date:** 2026-08-16
**Branch:** `feat/financial-message-studio`
**Brief:** [overnight-brief.md](overnight-brief.md) · **Plan:** [overnight-audit-and-plan.md](overnight-audit-and-plan.md)

---

## 1. Executive summary

The platform now generates **19 message types** — 16 MT and 3 MX — end to end, from the
browser, from JSON and from a spreadsheet, through one shared code path.

The four things that changed most:

1. **The MT output is a real FIN message.** The previous composer emitted
   `{1:DEMONSTRATION}` and `{2:MT541}`, neither of which is a valid header. Blocks 1, 2, 3
   and 5 are now built from configured interface values, and every value carries an origin
   label saying who is accountable for it.
2. **MX exists.** It did not before. Three ISO 20022 messages (`sese.023`, `sese.024`,
   `sese.025`) with namespace-correct XML, a `head.001.001.03` AppHdr, and real libxml2
   schema validation.
3. **Automation is a first-class path.** A stable `/api/v1` surface, tag-level MT and
   element-level MX Excel templates generated from the specification, and service
   authentication that does not require driving a login screen.
4. **The UI opens on the task.** Thirteen equal cards became six navigation items and a
   linear wizard. The app opens directly on Create Message.

**Verification:** 417 backend tests (from 257), 36 Playwright tests (from 11), ruff clean,
mypy strict clean, production build clean, migrations apply and reverse, both Docker images
build and the composed stack serves all four flows, no secret-shaped string in any tracked
file or in git history.

**Honest headline:** message coverage is a repository-configured subset that has never been
reconciled against a licensed specification. Everything says so — in the API, on screen and
in [../limitations.md](../limitations.md).

---

## 2. Audit findings

The full audit is in [overnight-audit-and-plan.md](overnight-audit-and-plan.md). What
mattered:

| # | Finding | Status |
|---|---|---|
| B1 | `POST /api/messages/generate` emitted a fabricated FIN envelope | **Fixed** — real envelope, and the old scenario API is untouched for the Advanced screens |
| B2 | Nine composers repeated the same fake header | **Superseded** — the studio path never uses them |
| B3 | The real FIN builder existed but needed login, CSRF, a draft and manually typed session numbers | **Fixed** — profile-driven, reachable from the open API |
| B4/B5 | 18 report ZIPs, mypy/ruff caches, `.DS_Store` in the tree | **Fixed** — removed, `.gitignore` extended |
| B6 | No git history at all | **Fixed** — baseline commit, then four reviewable commits |
| — | MX entirely absent | **Fixed** |
| — | Excel was scenario-shaped, not tag-level | **Fixed** |
| — | Thirteen top-level cards, seven ways to create a message | **Fixed** |
| — | No automation authentication model | **Fixed** |

**The strongest existing asset** was `app/authoring/composer.py` — a spec-driven Block 4
composer, already correct and already tested, reachable only through the authenticated
draft flow. The studio reuses it unchanged. That decision is why the MT work took hours
rather than days.

---

## 3. Plan versus actual

| Priority | Planned | Delivered |
|---|---|---|
| P1 | Audit and plan | Yes |
| P2 | Studio catalogue, models, `/api/v1`, service auth | Yes |
| P3 | MT FIN envelope, rock-solid MT541 | Yes — and all 16 MT types |
| P4 | `sese.023` vertical slice | Yes |
| P5 | Excel → API → FIN/XML | Yes, both formats |
| P6 | Message Intelligence for MT + MX | Yes |
| P7 | UI rebuild | Yes |
| P8 | Downloads and samples | Yes |
| P9 | Tests and regression | Yes |
| P10 | `sese.024`, `sese.025` *(if time)* | Yes |
| P11 | Report, git history, PR | Yes |

**Nothing planned was dropped.** Two things were deliberately not attempted, both recorded
in the plan's self-review as failing the "measurable user value" test: a WebSocket
validation channel, and an MT↔MX translation engine (impossible to do honestly without
authoritative mapping tables).

---

## 4. Architecture before

```
frontend (17 routes, 13 advertised on the home page)
    │
FastAPI
 ├── /api/*           public, unauthenticated, 60+ endpoints, scenario-shaped
 └── /api/…/drafts    session + CSRF + RBAC + tenant
    │
SettlementScenario ──► 9 hand-written composers ──► text with a fake envelope
```

Message creation was reachable seven ways. Field-level input existed only behind the
authenticated draft flow. No MX anywhere.

## 5. Architecture after

```
 Browser (6 nav items)        Automation (JSON · Excel · curl · REST Assured)
        └──────────────┬──────────────┘
                       │  /api/v1 — the same endpoints for both
                  StudioService
                       │
         ┌─────────────┴─────────────┐
      MT branch                   MX branch
      resolve · validate          resolve · validate
      compose (reused)            compose (new)
      FIN envelope                AppHdr + wrapper
                                  XSD (libxml2)
         └─────────────┬─────────────┘
                  GenerateResult
        message · validation · checksum · origins
```

Three doors in, one room behind them. MT and MX never share a rendering path. The original
scenario API and all thirteen specialist screens still work, unchanged, under **Advanced**.

Full detail: [../../ARCHITECTURE.md](../../ARCHITECTURE.md).

---

## 6. UI simplifications

| Before | After |
|---|---|
| 13 cards on the home page | 6 navigation items; the app opens on Create Message |
| 7 entry points for creating a message | 1 linear wizard |
| Opens with a free-text box and a model call | Opens with "MT or MX?" — no model involved |
| Format never surfaced | Format is step 1 |
| All fields or nothing | Required shown, optional behind "Add optional field", repeats behind "Add another" |
| Tag knowledge on a separate page | ℹ on every field, inline, no modal, no model call |
| `ruleId` and `technicalExplanation` first | "Ready to generate" or "3 issues need attention", each naming field, problem, expectation and fix |
| Downloads required a session | Copy and Download on the result |
| Teal, Arial, generic dashboard | Warm paper around a dark proof sheet ([../../DESIGN.md](../../DESIGN.md)) |

---

## 7. MT functionality

**All 16 types generatable field-by-field:** MT530, MT537, MT540–MT548, MT564–MT568.

- Fields address by row id (`MT541-A-20C-SEME`) or by sequence/tag/qualifier. Sequence
  accepts a code (`GENL`) or a path (`A`), and may be omitted when unambiguous.
- Ambiguous, unknown, duplicate and wrong-option addresses each produce their own named
  error rather than a silent omission.
- Validation across canonical, structure, format, business-rule, client-profile and
  FIN-envelope layers, each reported separately.
- Business rules: settlement date not before trade date, cancellation requires a previous
  reference, amount positive, currency and reference length per profile.
- Repeated sequences via `SequenceOccurrence`.

## 8. MX functionality

**Three types, complete lifecycle:** `sese.023.001.11` (instruction) →
`sese.024.001.13` (status advice) → `sese.025.001.12` (confirmation).

- Declarative nested specification per message; document order in the YAML **is** element
  order in the XML.
- Namespace derived from and validated against the version.
- Choice elements, repeatable blocks with per-occurrence values, currency as an attribute,
  XML escaping.
- Format checking per ISO 20022 representation class, with corrective suggestions —
  an MT-style date returns *"MX uses YYYY-MM-DD, not the MT format YYYYMMDD. Try
  2026-08-18."*
- Business rules: date chronology, `APMT` requires an amount and `FREE` forbids one, a
  receipt must name the delivering chain, and a status advice must report at least one
  status (expressed as `requireOneOf` **configuration**, not code).

## 9. FIN output

```
{1:F01DEMOGB2LAXXX0001000001}
{2:I541DEMOUS33XXXXN}
{4:
:16R:GENL
:20C::SEME//TESTREF001
…
-}
```

Block 1 is a correctly structured 25-character basic header. Block 2 is a correctly
structured output application header. Block 3 appears only with a message user reference.
Block 5 appears only when the profile configures a permitted trailer.

**Nothing is invented.** Every value carries an origin:

| Origin | Produced? |
|---|---|
| `USER_ENTERED`, `PROFILE_CONFIGURED`, `APPLICATION_GENERATED` | yes |
| `INTERFACE_GENERATED`, `NETWORK_GENERATED` | **never** |

Missing session or sequence numbers **fail closed** with a named error. MAC, CHK, PDE, PDM,
DLM, TNG and SYS trailers are refused even if a profile lists them — each covered by a
parametrised test.

Output modes: `BLOCK4`, `FIN`, `TXT`, `CANONICAL_JSON`.

## 10. MX AppHdr and Document output

```xml
<?xml version="1.0" encoding="UTF-8"?>
<BusinessMessage>                                   <!-- profile-configured wrapper -->
  <AppHdr xmlns="urn:iso:std:iso:20022:tech:xsd:head.001.001.03">
    <Fr><FIId><FinInstnId><BICFI>DEMOGB2LXXX</BICFI></FinInstnId></FIId></Fr>
    <To><FIId><FinInstnId><BICFI>DEMOUS33XXX</BICFI></FinInstnId></FIId></To>
    <BizMsgIdr>SESE023202608161520</BizMsgIdr>
    <MsgDefIdr>sese.023.001.11</MsgDefIdr>
    <CreDt>2026-08-16T15:20:41Z</CreDt>
  </AppHdr>
  <Document xmlns="urn:iso:std:iso:20022:tech:xsd:sese.023.001.11">
    <SctiesSttlmTxInstr>…</SctiesSttlmTxInstr>
  </Document>
</BusinessMessage>
```

`MsgDefIdr` is derived from the selected message, so header and document cannot disagree.
`Sgntr` is never written. The wrapper is profile-configured — with none configured, the
output is the Document alone plus a warning.

Output modes: `XML`, `APPHDR`, `DOCUMENT`, `CANONICAL_JSON`.

**XSD validation:** real libxml2 validation, against an official schema when one is present
in `backend/config/mx/xsd/official/`, otherwise against a schema derived from the configured
specification. The response always reports which (`OFFICIAL` or `SUBSET_DERIVED`). Tests
prove the derived schema independently catches out-of-order elements, missing required
attributes, bad patterns and bad enumerations.

## 11. Excel API

`POST /api/v1/messages/generate-from-excel` — multipart `.xlsx`, one message per
`ScenarioID`.

Templates are generated **from the specification**, so nobody invents a tag or an XPath.
Each carries three sheets: Scenarios (pre-filled and working), Reference (every supported
field with format and example, required rows shaded) and Read me.

| MT columns | MX columns |
|---|---|
| ScenarioID · MessageType · ProfileID · Sequence · SequenceOccurrence · Tag · Qualifier · Option · Value | ScenarioID · MessageType · ProfileID · XPath · Occurrence · Value |

Format is detected from the columns. Headers match case- and space-insensitively. Excel
date cells convert back to ISO text; numeric cells do not gain a decimal point. A failing
scenario does not stop the others — every scenario is reported with its own validation.

## 12. JSON API

`POST /api/v1/messages/generate` and `/validate`. Response carries the message in several
output forms, the layered validation report, a SHA-256 checksum, a correlation id, the
profile and version, and the envelope origin table.

Discovery endpoints mean automation never hand-writes a payload: `/catalogue`,
`/messages/{type}/spec`, `/messages/{type}/samples/{variant}`.

Full surface: [../for-automation-testers.md](../for-automation-testers.md).

## 13. Message Intelligence

One deterministic search across MT tags and MX elements. Query by tag (`95R`), qualifier
(`PSET`), element (`SttlmDt`), XPath fragment, business phrase (`settlement amount`) or
message type (`sese.023`).

Returns business meaning, technical meaning, why used, format, allowed codes, examples,
common mistakes, dependencies, cardinality, parent, source reference — **and the field shown
inside a real generated message**.

No model call. A Playwright test watches network traffic and asserts none is made.

## 14. Downloads

Per-output downloads preserve the exact generated bytes with no added formatting. An
evidence ZIP bundles every output plus the validation report and the inputs used.

## 15–16. AI usage and cache

Unchanged and untouched. The model interprets intent only. It never renders, validates,
parses, reads a spreadsheet or builds XML. Order remains deterministic → cache → model.
Telemetry still reports live calls, cache hits, tokens, cost, latency, and what was avoided.

**The AI path is off by default and nothing in the studio depends on it.**

---

## 17. Files changed

**114 files, +17,483 / −4,109** since the baseline commit.

**New — backend (18 modules)**

```
app/studio/{__init__,models,catalogue,service,routes,security,samples,excel,
            intelligence,store}.py
app/studio/mt/{__init__,fin,generator}.py
app/studio/mx/{__init__,models,registry,generator,xsd}.py
config/mx/{sese.023.001.11,sese.024.001.13,sese.025.001.12}.yaml
alembic/versions/20260816_0007_studio_messages.py
tests/studio/{test_fin_envelope,test_mt_generation,test_mx_generation,
              test_excel_api,test_studio_api}.py
```

**New — frontend (12 components, 7 routes, 2 specs)**

```
components/studio/{Chrome,CreateMessage,FieldEditor,ProofSheet,ValidationPanel,
                   ExcelStudio,Intelligence,ValidateStudio,Automation,
                   RecentMessages,Icon,ui}.tsx
app/{excel,intelligence,validate,automation,recent,advanced}/page.tsx
lib/{studio-api,studio-types}.ts
tests/e2e/{studio-create,studio-screens}.spec.ts
```

**Modified**

```
backend: app/main.py · app/config.py · app/api/errors.py · app/profiles/loader.py
         app/persistence/models.py · app/specifications/report.py
         config/profiles/*.yaml · requirements*.txt
frontend: app/layout.tsx · app/page.tsx · app/globals.css
root: Makefile · .gitignore · .env.example
```

**Documentation:** 30 files removed, 12 written. See §24.

## 18. Database changes

One additive migration, `20260816_0007`, creating `studio_messages` with three indexes. No
existing table is altered or dropped. Verified: applies to a clean database, downgrades and
re-applies cleanly.

## 19. APIs added

14 endpoints under `/api/v1`, listed in [../for-automation-testers.md](../for-automation-testers.md#every-endpoint).
Nothing existing was removed or renamed.

`HTTPException` now returns the platform error envelope with a stable code, so automation
can branch on `error.code` rather than parsing prose.

## 20–21. Tests added and exact results

| Suite | Before | After |
|---|---|---|
| Backend | 257 | **417** |
| — of which studio | 0 | **160** |
| Playwright | 11 | **36** |

```
$ make test
417 passed, 1 deselected, 1 warning in 3.07s

$ make lint
All checks passed!                                    (ruff)
✔ No ESLint warnings or errors

$ make typecheck
Success: no issues found in 124 source files          (mypy --strict)
                                                      (tsc --noEmit: clean)
$ make build
✓ Compiled successfully in 1505ms
✓ Generating static pages (23/23)

$ make e2e
36 passed (52.1s)

$ make coverage
docs/generated/message-coverage.md is current

$ alembic upgrade head && alembic downgrade -1 && alembic upgrade head
OK

$ docker compose up --build
backend    Up (healthy)
frontend   Up

$ make secret-scan
No secret-shaped strings in tracked files
```

**Design detector:** zero findings in the new frontend code. Seven `gray-on-color` warnings
remain in the pre-existing Advanced screens, which were preserved rather than redesigned.

## 22. Browser and manual verification

Verified with Playwright driving a real Chromium against the real backend, plus screenshot
inspection of every screen at 1440 px and 390 px.

| Flow | Result |
|---|---|
| Manual MT: MT541 → enter values → validate → generate → real FIN → download | pass |
| Manual MX: sese.023 → validate → AppHdr + Document → download | pass |
| Automation MT: Excel → API → FIN | pass, 3/3 scenarios |
| Automation MX: Excel → API → XML | pass, 3/3 scenarios |
| Intelligence: `PSET` → meaning, format, dependencies, sample | pass |
| Intelligence: `SttlmDt` → XPath, cardinality, sample XML | pass |
| Field explanation inline, no modal, no model call | pass |
| Envelope origins including what was deliberately not produced | pass |
| Recent Messages → reopen → evidence ZIP | pass |
| Advanced screens still reachable | pass |
| No sideways scroll at 10 widths from 360 px to 1600 px | pass |
| Skip link, single `h1` per page, keyboard focus | pass |

**Eight defects were found by this verification and fixed**, seven of which no unit test
would have caught:

1. An unlayered `button { color: inherit }` reset beat every Tailwind text-colour utility —
   layered rules always lose to unlayered ones. It made the proof toolbar invisible and
   would have broken button text across the product. Base styles moved to `@layer base`.
2. Grid and flex items default to `min-width: auto`, so a wide code block expanded its track
   instead of scrolling; `/automation` scrolled sideways at 390 px.
3. The nav was `overflow-visible` at `lg`, pushing the page wider at exactly 1024 px.
4. The required-field counter compared *all* filled values against *required* count,
   reporting "14 of 12".
5. Fields whose codes are a value prefix (`36B`, `UNIT/1000`) rendered as a dropdown that
   silently discarded the value.
6. A floating copy button sat on top of code that scrolled underneath it.
7. Twelve missing MT fields produced twenty-four errors — the composer restated in its own
   words what the structured validator had already reported.
8. MX rendered-line annotations matched by element name, which is ambiguous in ISO 20022
   (`Dt`, `Cd` recur). The composer now emits the element path directly.

Two further defects were caught by the new tests before any browser run:

- **MX repeated blocks rendered the first occurrence's values for every repeat**, because
  the occurrence was not threaded through the container.
- **`date.fromisoformat` accepts the compact `YYYYMMDD` form** on modern Python, so an
  MT-style date passed the friendly ISODate check and only the XSD rejected it.

## 23–25. Known limitations, unsupported types, domain-rule gaps

Recorded in full in [../limitations.md](../limitations.md). The essentials:

- **Coverage is a configured subset**, never reconciled against a licensed specification.
  Every message reports `PARTIAL` and `authoritativeCompletenessKnown: false`.
- **XSD is `SUBSET_DERIVED` by default.** Real libxml2 validation, but of this repository's
  subset. Drop an official schema in `config/mx/xsd/official/` and it is preferred
  automatically.
- **Not implemented:** payments (`pacs.*`), cash management (`camt.*`), reconciliation
  (`semt.*`), the MX cancellation and modification lifecycle (`sese.020/027/030/031`), and
  MX *import* (generation only).
- **Documented domain-rule gap:** the configured MT subset renders `:22F::SETR//BUY` in
  Sequence B and `:22F::SETR//RECE` in Sequence E. Authoritatively, `22F::SETR` belongs in
  Sequence E only and direction is implied by the message type. Recorded rather than
  silently corrected, because correcting it requires an authoritative source.
- **RJE fails closed** — no authorised interchange contract exists here, and guessing the
  structure would be worse than not offering it.
- Rate limits, the AI circuit breaker and the L1 cache are **per process**.

## 26. Security review

Full detail in [../security.md](../security.md). What changed:

**Added**

- Service authentication for `/api/v1` via `X-API-Key`, kept separate from interactive
  sessions. Keys come only from `AUTOMATION_API_KEYS`, are compared with
  `hmac.compare_digest` against every configured key so timing reveals nothing, and never
  appear in a response, a log line or the source. Open in development; `503` with an
  explanation elsewhere until configured.
- `HTTPException` routed through the safe error envelope, so no bare `detail` string with
  internal text can escape.
- Field values are rejected if they contain FIN block fragments, so a value cannot smuggle
  structure into an envelope.
- `make secret-scan`.

**Preserved:** every existing control — strict request models, upload guards, formula
escaping, placeholder tokenisation at the model boundary, safe logging, CORS, security
headers, tenant isolation, unprivileged containers.

**Verified:** `.env` gitignored and never committed; no secret-shaped string in any tracked
file or anywhere in git history; no hardcoded credential in source.

## 27. Exact commands

```bash
# Setup
make install
make migrate

# Run
make backend      # → http://localhost:8000
make frontend     # → http://localhost:3000
# or
docker compose up --build

# Verify
make check        # lint + typecheck + tests + coverage gate
make e2e
make secret-scan
```

## 28. Demo walkthrough

**Roughly eight minutes.**

1. **Open <http://localhost:3000>.** You are on Create Message. Six steps across the top.
2. **MT → Securities Settlement → MT541 → Typical.** A complete valid scenario is loaded.
3. **Click the ℹ on Intended Settlement Date.** Meaning, why, format, example, common
   mistakes — inline, and no model was called.
4. **Clear the Settlement Amount and press Validate.** *"1 issue needs attention"*, naming
   the business field, what was expected and what to do. Restore it.
5. **Press Generate message.** The proof sheet wipes in: real `{1:F01…}`, real `{2:I541…}`,
   line numbers, and a margin naming the field each line came from.
6. **Expand Envelope values.** Some values are yours, some the profile's, some derived —
   and the trailer row says *not written, the network adds this*. That is the honesty story.
7. **Start over → MX → sese.023 → Typical → Generate.** AppHdr plus Document, correct
   namespace, schema-validated. No FIN blocks anywhere.
8. **Bulk / Excel → Download MT template → drop it straight back.** Three scenarios, three
   FIN messages, each expandable.
9. **Message Intelligence → type `PSET`.** MT and MX results together, full explanation, and
   the field shown inside a real message. Marked *Deterministic*.
10. **API & Automation.** The same call in curl, Java, Python and JavaScript, plus the whole
    endpoint list.
11. **Recent Messages.** Everything generated in the demo, ready to download again.

## 29. Recommended next phase

In the order I would actually do them:

1. **Import a licensed specification.** Everything else is gated on this. It is what turns
   `PARTIAL` into a real capability claim, and the YAML structure is already the right shape
   to receive it.
2. **Drop in official ISO 20022 XSDs.** One folder, no code change, and MX validation
   becomes authoritative.
3. **MX import and round trip.** Generation exists; parsing someone else's XML back into
   fields does not. It is the most-requested missing half.
4. **The MX cancellation lifecycle** — `sese.020`, `sese.027`, `sese.030`, `sese.031`. Pure
   YAML on the current architecture.
5. **Fix the `22F::SETR` placement** once §25's authoritative source is available.
6. **Shared state for the rate limiter and circuit breaker** before running more than one
   instance.
7. **A production identity-provider adapter.** The OIDC/SAML boundary is there; the adapter
   is not.

Items 3 and 4 are the highest user value per hour on the current architecture. Item 1 is the
only one that changes what the platform is allowed to claim.
