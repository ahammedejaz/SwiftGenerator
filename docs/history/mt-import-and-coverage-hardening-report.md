# MT Import and Coverage Hardening Report

**Date:** 2026-08-16 · **Base:** `21e5f4b` on `feat/mx-import-and-lifecycle` ·
**Scope:** the four priorities in the hardening brief, audited against `AGENTS.md` and
[autonomous-continuation-report.md](autonomous-continuation-report.md), verified in a
running browser.

No SWIFT, ISO 20022, MyStandards or client artifact was invented, expanded or "corrected".
The `sese.020/027/030/031` definitions remain `UNVERIFIED`; nothing in this work touched
them beyond reporting that status in more places.

---

## 1. Audit findings

The documented state was reproduced exactly before anything changed:

| Claim in `AGENTS.md` §2 | Result |
|---|---|
| 522 backend tests pass | ⚠️ **525** passed, 9 skipped, 1 deselected — the document was three behind |
| 46 browser tests pass | ✅ confirmed |
| ruff · eslint · `tsc --noEmit` clean | ✅ |
| mypy `--strict` clean, 125 files | ✅ |
| coverage gate current | ✅ |
| migrations up/down/up clean | ✅ |
| secret scan clean · docker builds | ✅ |

Three structural findings shaped the work:

1. **`AGENTS.md` §15 already listed this brief's items 5 and 6** — MT import and extending
   coverage to MX — as the recommended next work. The brief and the repository agreed.
2. **`app/specifications/report.py` was reachable only from `Makefile:coverage`.** The
   registry's own `report()`/`coverage()` methods are used separately by the older `/api/*`
   routes, so the generator could be replaced without disturbing them.
3. **All four configuration locations were hardcoded paths in Python.** The `xsd/official/`
   directory had a README describing a drop-in procedure that in practice required editing
   a module-level constant. That was the real authoritative-source readiness gap, and it is
   what priority 3 became.

### A generation defect that import made visible

While validating the first MT round trip, a message came back structurally different from
the one that went in. The cause was **not** in the new parser:

```python
# app/studio/mt/generator.py, before
for path, occurrence in list(needed):
    current = by_path.get(path)
    while current and current.parent_path:
        needed.add((current.parent_path, 1 if occurrence == 1 else occurrence))
```

A child sequence at occurrence *N* forced **every ancestor** to occurrence *N*. Asking for
two penalty-detail blocks therefore produced two whole `PENA` sequences — and `PENA` is
declared `1..1`, so the composer emitted a message that violated its own configured
cardinality:

```
:16R:PENA … :16R:PENDET :20C::PREF//P1 :16S:PENDET … :16S:PENA
:16R:PENA … :16R:PENDET :20C::PREF//P2 :16S:PENDET … :16S:PENA   ← should be one PENA
```

The composer *did* report `Sequence D occurrence count 2 is outside 1..1`, so it was not
silent, but there was no way for a tester to obtain the shape they had asked for. This is
reachable today from the wizard and from Excel's `SequenceOccurrence` column, so it predates
import entirely; import is only what made it visible. Fixed, with a regression test.

---

## 2. MT import architecture

`backend/app/studio/mt/parser.py` (~530 lines of code, the rest documentation).

It is the exact inverse of `SpecificationComposer.compose` and `build_fin_message`, and it
does nothing else. It produces `FieldInput` values — the same type the JSON API and the
Excel importer produce — and hands them to `StudioService.generate`. There is no
import-only composer, validator or renderer, so an imported message and a typed one cannot
disagree. That is what makes comparing them meaningful.

```
text → _scan_blocks   balanced {1:}{2:}{3:}{5:}, and {4: … -} by its terminator
     → _resolve_specification   Block 2, else caller, else the :16R: skeleton
     → _TextBlockReader
          _scan            :16R:/:16S: stack, tag lines, continuation lines
          _emit            resolve (sequence_path, tag, qualifier) → row + occurrence
          _check_structure run plan_sequences over what was read, compare the trees
     → _read_envelope   sender, receiver, session, sequence, priority, MUR
     → StudioService.generate
```

**Message-type resolution is layered, and refuses rather than guesses.** Block 2 always
wins, because that is where a FIN message names itself. A caller-supplied `messageType` is
consulted *only* when the text cannot name itself, and a Block 2 that disagrees with it is
`MT_IMPORT_TYPE_MISMATCH` — a refusal, not a reconciliation, because parsing a mislabelled
file against the caller's guess produces a confident wrong answer. Failing that, the `:16R:`
sequence skeleton narrows the candidates by deterministic set containment; one candidate is
used, more than one is `MT_IMPORT_TYPE_AMBIGUOUS` with the candidates listed.

**Occurrence is checked against the real planner, not a restatement of it.** The MT
occurrence address is flat — `(sequence_path, occurrence)` — so not every nesting a real
message can carry is expressible. Rather than encode that rule twice, the occurrence model
was extracted into `plan_sequences()` in the generator, and the parser runs it over the
values it read and compares the resulting instance tree with the tree the message actually
had. A hand-derived rule was written first and was wrong in two cases; this cannot drift.

**No message-specific branches.** Resolution is by `(sequence_path, tag, qualifier)` against
the registry, so a message added as configuration imports with no code change — the same
property the lifecycle messages proved for generation.

---

## 3. Supported input formats

| Input | Recognised by | Notes |
|---|---|---|
| Complete FIN message | `{1:` / `{2:` | Blocks 1, 2, 3, 4 and 5 all parsed |
| FIN with a demonstration envelope | `{1:DEMONSTRATION}{2:MT541}` | What this repository's own sample exporter and golden fixtures write |
| Delivered (output) message | `{2:O541…}` | Message type read; **no receiver invented** from it |
| Text block | `{4: … -}` | Needs a message type only when the skeleton is ambiguous |
| Bare Block 4 body | `:16R:…` with no wrapper | Same |
| `.fin` / `.txt` upload | Browser reads the file as text | 1 MB client-side limit, 1 MB server-side |
| ISO 20022 wrapped payload, bare `Document`, or `AppHdr` + `Document` | `<` or the ISO namespace | Unchanged from the previous work |

`POST /api/v1/messages/import` now detects the format from the content. `text` is the
canonical field; `xml` still works, and a test asserts it, so callers written against the
MX-only version keep running.

---

## 4. Round-trip results

The property is `Compose(Parse(Compose(values))) == Compose(values)`, comparing the
recomposed **message** rather than the value list: two value lists can differ harmlessly
while denoting the same message, and the message is what a tester receives.

| Corpus | Count | Result |
|---|---|---|
| MT samples (every configured message × every available variant) | 30 | **all identical**, Block 4 and FIN |
| MT golden fixtures | 17 | **all import cleanly and recompose identically** |
| MX samples (unchanged from previous work) | 15 | all identical |
| Coverage report `Round trip` column | 23 messages | `IDENTICAL` for every one |

The golden fixtures matter here beyond regression: they use the demonstration envelope, so
they are exactly what a tester pastes after copying a message out of the samples screen.

---

## 5. Refusal and ambiguity cases

Nothing is silently dropped. Twenty named conditions, each with `expected` and `suggestion`,
each naming the business field rather than an internal identifier.

**Cannot be identified at all — the request is refused (422):**

`MT_IMPORT_EMPTY` · `MT_IMPORT_TOO_LARGE` · `MT_IMPORT_NO_TEXT_BLOCK` ·
`MT_IMPORT_TEXT_BLOCK_NOT_CLOSED` · `MT_IMPORT_BLOCK_NOT_CLOSED` · `MT_IMPORT_TYPE_UNKNOWN` ·
`MT_IMPORT_TYPE_AMBIGUOUS` · `MT_IMPORT_TYPE_NOT_CONFIGURED` · `MT_IMPORT_TYPE_MISMATCH`

**Identified, but part of it could not be imported — reported and folded into the
validation the UI shows:**

`MT_IMPORT_UNKNOWN_SEQUENCE` · `MT_IMPORT_SEQUENCE_NOT_OPENED` ·
`MT_IMPORT_SEQUENCE_NOT_CLOSED` · `MT_IMPORT_SEQUENCE_MISMATCHED_END` ·
`MT_IMPORT_FIELD_OUTSIDE_SEQUENCE` · `MT_IMPORT_UNKNOWN_FIELD` · `MT_IMPORT_UNPARSABLE_LINE` ·
`MT_IMPORT_DUPLICATE_FIELD` · `MT_IMPORT_EMPTY_VALUE` · `MT_IMPORT_VALUE_REJECTED` ·
`MT_IMPORT_NESTED_REPEAT_UNSUPPORTED`

**Read, and deliberately not reproduced — warnings:**

`MT_IMPORT_TRAILER_DROPPED` (MAC, CHK and authentication trailers are interface- and
network-generated; the studio refuses to write them, so it must say it dropped one) ·
`MT_IMPORT_USER_HEADER_FIELD_DROPPED` · `MT_IMPORT_OUTPUT_HEADER` (a delivered message's
header names the network, not a receiver — reusing any of it would be inventing an address) ·
`MT_IMPORT_DEMONSTRATION_HEADER` · `MT_IMPORT_FIELD_ORDER` · `MT_IMPORT_SEQUENCE_ORDER` ·
`MT_IMPORT_EMPTY_SEQUENCE_DROPPED` · `MT_IMPORT_BLOCK1_UNREADABLE` ·
`MT_IMPORT_BLOCK2_UNREADABLE` · `MT_IMPORT_NO_VALUES`

Two are worth explaining because they are the interesting cases:

**Ambiguity.** MT540 through MT543 share the `GENL/TRADDET/FIAC/SETDET` skeleton, and
MT548/MT567 share `GENL/LINK/STAT`. A text block from any of them fits several messages
equally well. Import refuses and lists the candidates. In the browser the message picker is
**revealed only after that refusal**, so a tester pasting a complete FIN message — which
names itself — is never asked a question they do not need to answer.

**Nested repeats.** The flat address carries one index, so a repeated block whose values
would be rebuilt inside a different block is refused rather than reshaped:

> `PENACOUNT block 2 carries no values of its own, so the studio cannot tell it apart from
> the PENACOUNT block before it and their contents would be merged.`

---

## 6. Unified MT and MX coverage

`backend/app/studio/coverage.py` replaces `app/specifications/report.py` as the generator of
`docs/generated/message-coverage.md`. `make coverage` still fails the build when the document
is stale; `make coverage-write` regenerates it. The registry's `report()`/`coverage()`
methods are untouched, because the older `/api/*` routes serve them.

**All 23 messages, both formats**, with format, version, capability, verification status,
configured rows or elements, form, composer, parser, validation, intelligence, Excel,
sample, golden, round trip, XSD source and authoritative-completeness status.

Two decisions define the report:

**Every denominator is the configured subset, and the document says so in its own body**
rather than in a footnote. No licensed specification is present, so no authoritative
format-row count exists to divide by. `12/12` means the twelve rows this repository holds
all work; it does not mean the message is complete.

**Every figure is measured, not declared.** Form comes from the catalogue projection, Excel
from reading back the generated reference sheet, Intelligence from the search index, parser
from address resolvability, sample from the fullest generated sample, round trip from
actually performing it. This is not academic: the Excel reference sheet was hardcoded to
three MX messages while the registry held seven, and a `composer_supported`-style flag would
have reported 100%.

Three bases are reported and never added together — `REPOSITORY_CONFIGURED`,
`AUTHORITATIVE_UNKNOWN`, `EXTERNALLY_VERIFIED`. Nothing is in the third today, and the
report says so. An MX message validated against an official schema that has been dropped in
moves to `EXTERNALLY_VERIFIED` automatically.

`GET /api/v1/coverage` serves the same data, so the document and the API cannot drift.

---

## 7. Authoritative-source readiness

Four classes of artifact would move the coverage boundary. None may be reproduced here. What
was prepared is the receiving end.

**The four hardcoded paths are now settings**, defaulting to the committed configuration so a
clean clone behaves identically:

| Artifact | Location | Setting |
|---|---|---|
| Official ISO 20022 schemas | `backend/config/mx/xsd/official/` | `MX_OFFICIAL_XSD_DIRECTORY` |
| ISO 20022 message definitions | `backend/config/mx/` | `MX_SPECIFICATION_DIRECTORY` |
| Licensed SWIFT MT specification | `backend/config/specifications/…` | `MT_SPECIFICATION_MANIFEST` |
| Client MyStandards guidelines | `backend/config/profiles/` | `CLIENT_PROFILE_DIRECTORY` |

`app/studio/sources.py` reports, per class: what it is, where it goes, the setting that
redirects it, what is being read right now, and what changes when a real artifact arrives.
Served by `GET /api/v1/sources`, rendered into the coverage document, and documented as a
procedure in [authoritative-sources.md](../authoritative-sources.md) — including what
to re-run and, for the lifecycle messages, which test asserts the `UNVERIFIED` caveat and
must be updated in the same commit.

The official-schema test was rewritten to **perform the drop-in procedure** — set the
setting, point it at a directory — rather than monkeypatching a module constant, so it tests
what a person would actually do. A companion test asserts the default still resolves to the
committed directory.

Nothing was scraped or copied. `.gitignore` already excludes `*.xsd` under the official
directory; every other location is documented as needing the same treatment before a
licensed file is copied in.

---

## 8. Files changed

**New (7)**

```
backend/app/studio/mt/parser.py                       983   MT import
backend/app/studio/coverage.py                        565   unified MT + MX coverage
backend/app/studio/sources.py                         170   authoritative-source readiness
backend/tests/studio/test_mt_import.py                530   round trip, refusals, the API
backend/tests/studio/test_coverage_and_sources.py     178   coverage is measured, not declared
docs/authoritative-sources.md                         129   the import procedure, per artifact
backend/config/README.md                               22   what each directory is
```

**Removed (1)** — `backend/app/specifications/report.py`, superseded by `app/studio/coverage.py`.

**Modified (24)**

| File | Change |
|---|---|
| `backend/app/studio/mt/generator.py` | `plan_sequences()` extracted; the parallel-branch defect fixed |
| `backend/app/studio/models.py` | `ImportRequest`/`ImportResult` format-neutral |
| `backend/app/studio/routes.py` | import dispatches on content; `/coverage` and `/sources` |
| `backend/app/studio/excel.py` | `reference_rows()` exposed so coverage can measure the sheet |
| `backend/app/config.py` | four source-path settings and `source_path()` |
| `backend/app/specifications/registry.py` · `profiles/loader.py` · `mx/registry.py` · `mx/xsd.py` | read their location from settings |
| `backend/tests/studio/test_mx_generation.py` | official-schema test performs the real procedure |
| `Makefile` | `coverage` → `app.studio.coverage`; `coverage-write` added |
| `.env.example` · `backend/config/mx/xsd/official/README.md` | the new settings |
| `docs/limitations.md` | "MX has no import path" was stale; both formats now documented |
| `docs/README.md` · `docs/for-automation-testers.md` | import, coverage and sources |
| `docs/generated/message-coverage.md` | regenerated: 23 messages, both formats |
| `frontend/lib/studio-types.ts` · `studio-api.ts` | `text`, `messageType`, `fields`, `finBlocks` |
| `frontend/components/studio/CreateMessage.tsx` | both formats; progressive type picker; imported repeats made visible |
| `frontend/components/studio/ValidateStudio.tsx` | two paste modes collapsed into one |
| `frontend/components/studio/Automation.tsx` · `app/validate/page.tsx` | copy and endpoint list |
| `frontend/tests/e2e/studio-import.spec.ts` | four MT import journeys |
| `AGENTS.md` · `autonomous-continuation-report.md` | factual sections; superseded-in-part note |

`32 files changed, 3358 insertions(+), 448 deletions(-)`

---

## 9. Tests and exact results

```
make check
  ruff check app tests ......................... All checks passed
  eslint ....................................... clean
  mypy app ..................................... no issues in 127 source files
  tsc --noEmit ................................. clean
  pytest ....................................... 697 passed, 27 skipped, 1 deselected  (4.37s)
  coverage gate ................................ docs/generated/message-coverage.md is current

make e2e ....................................... 50 passed  (1.1m)
make secret-scan ............................... no secret-shaped strings in tracked files
docker compose config --quiet .................. ok
docker compose build ........................... backend Built, frontend Built
git diff --check ............................... clean
alembic upgrade / downgrade base / upgrade ..... clean, zero errors on a fresh database
```

**Backend tests: 525 → 697 (+172). Browser tests: 46 → 50 (+4).**

| Suite | Result |
|---|---|
| `test_mt_import.py` | 133 passed, 18 skipped |
| `test_mx_import.py` | 57 passed, 5 skipped |
| `test_coverage_and_sources.py` | 38 passed |
| `test_excel_api.py` | 39 passed |

Skips are message/variant combinations that do not exist — skipped by name, never silently
omitted.

Two tests are worth calling out because they encode the invariants most likely to erode:

- `test_no_message_claims_authoritative_completeness` asserts every message still reports
  `PARTIAL`, `authoritativeCompletenessKnown: false`, and a basis other than
  `EXTERNALLY_VERIFIED`.
- `test_a_repeated_sub_block_does_not_duplicate_its_parent` pins the generation defect above.

---

## 10. Browser verification

Walked the running application in Chromium at 1440×1000 and 390×844, capturing 20
screenshots. **Zero unexpected console errors, zero unexpected failed requests, 0px
horizontal overflow at 390px on every page.** The single 422 recorded is the deliberate
ambiguity refusal being exercised.

Covered: MT import → builder → edit → regenerate · MT text block → refusal → picker →
import · MX import → builder → regenerate · MT generation from scratch · MX lifecycle
generation · Validate for both formats · Excel → API → MT FIN (3 generated, 0 failed) ·
Excel → API → MX XML (3 generated, 0 failed) · Message Intelligence · Recent Messages ·
single-output download · evidence ZIP · Automation · three pages at phone width.

### Three findings, all fixed

1. **Imported repeats above occurrence 1 were invisible.** The wizard reset the
   repeat counters on import, so a value at occurrence 2 sat in state, was submitted on
   generate, and was never rendered — data the tester could neither see nor correct. The
   builder now opens each repeated block to the number of repeats that arrived. This
   affected MX import too, so it was a live defect before this work.
2. **The Validate page still said "an existing MT message"** in its subtitle after the mode
   had been generalised. Caught by reading the screenshot, not by any test.
3. **The Validate screen asked a question with no purpose.** It had separate "An existing MT
   message" and "An existing MX message" modes, but the import endpoint identifies a message
   from its own content. Collapsed into one "An existing message" mode — three modes to two,
   and one fewer way to pick wrong.

One non-finding, investigated and dismissed: `download/TXT` returned 404 for a stored MX
message. That is correct — `TXT` is an MT-only output — and the response says so by name:
*"sese.025 was not generated with TXT output."* The fault was in the smoke script's
fallback.

---

## 11. Remaining external blockers

Unchanged, and none worked around.

1. **Licensed ISO 20022 message-definition reports.** `sese.020.001.08`, `sese.027.001.08`,
   `sese.030.001.10` and `sese.031.001.09` still carry `UNVERIFIED` as their first
   limitation: version numbers, root element names and element sets were modelled on the ISO
   20022 idioms already present in this repository and reconciled against nothing. **This
   remains the single largest outstanding risk and should be settled before any external
   use.** It is now surfaced in three more places — the coverage report names them, the
   readiness report names them, and `docs/authoritative-sources.md` gives the procedure —
   which makes it harder to overlook but no less true.
2. **Official ISO 20022 XSDs.** Absent, so MX validation remains `SUBSET_DERIVED`. The drop
   point, the setting, the README and the procedure now all exist.
3. **Licensed SWIFT MT specification.** Coverage remains a repository-configured subset;
   every message still reports `PARTIAL`.
4. **`22F::SETR` placement** is unchanged and still needs an authoritative source.
5. **Client MyStandards profiles** and **production connector contracts** — absent,
   untouched.
6. **Shared rate-limiter and circuit-breaker state** needs Redis or equivalent.

---

## 12. Updated recommended next work

1. **Reconcile the four lifecycle specifications** against an authoritative message-definition
   report. Cheapest removal of a caveat that applies to four of seven MX messages.
2. **Import a licensed MT specification.** Still the only thing that changes what the
   platform may claim. The drop point and the setting now exist.
3. **Drop official ISO 20022 XSDs in.** One folder, no code.
4. **Fix `22F::SETR` placement** once an authoritative source exists.
5. **An original-versus-recomposed diff in the browser.** Both formats round-trip and the
   proof sheet shows the result, but nothing highlights what changed between the message that
   went in and the one that came out — the first thing a tester looks for, and the last
   remaining gap in the import experience.
6. **Shared rate-limiter and circuit-breaker state** before running more than one instance.
7. **Production OIDC/SAML adapter.** The boundary exists; the adapter does not.

---

## 13. Invariants checked

| Invariant | How it was kept |
|---|---|
| A message = specification + values | MT import resolves against the registry; a message added as configuration imports with no code |
| Prefer configuration over code | Four source locations became settings rather than new loaders |
| UI, JSON API and Excel share one path | Import produces `FieldInput`/`ElementInput` and calls `StudioService.generate`; no second composer exists |
| MT and MX rendering stay separate | Two parsers, two packages; the only shared code is the dispatch in `routes.import_message` |
| Never invent interface/network values | Block 5 trailers and MX `Sgntr` are read, reported and **not** reproduced; an output header yields no receiver address |
| AI does intent interpretation only | Untouched; both parsers are deterministic and call no model |
| Honest `PARTIAL` reporting | Not weakened. A test asserts every message still reports `PARTIAL` and `authoritativeCompletenessKnown: false`; the coverage report states its denominator in its own body |
| No UI capability without an API equivalent | Endpoint first, then types, then client, then component. `/coverage` and `/sources` are API-only and listed on the Automation page |
| No message-specific branches | Import resolves by `(sequence_path, tag, qualifier)` and by namespace; no message name appears in either parser |
