# Final MVP / POC release report

The last implementation engagement on this repository. Everything here was measured on
2026-08-22 from the branch it describes, not carried over from an earlier report.

---

## 1. Executive summary

The Financial Message Studio was already a capable product. An audit against a **real
browser** — rather than against its own test suite — found that three of its headline
journeys did not work for a user following the documentation, and that none of the three
could be seen by any existing test:

1. **Create Message was dead on `127.0.0.1`**, the address this repository standardises on
   and the address its documentation gives. `next dev` blocks its own `/_next/hmr`
   resources for any host it was not started on, so the client never hydrated and the
   screen sat on *"Loading configured messages…"* having made **no API request at all**.
   The same build on `localhost:3000` was perfect, which is why 1,611 backend tests and 96
   browser tests never saw it.
2. **Convert Message had a dead button.** It listed the Mapping Pack, took the user's
   preview opt-in, and then refused: *"No exact Mapping Pack matches this source and
   target."* The request carried no `targetLane`, so it resolved against `CONFIGURED`
   while both candidate packs address `KNOWLEDGE_PREVIEW`. No API test could see it,
   because an API test names the lane itself.
3. **MT103 → pacs.008 could never complete**, even through the API with every declared
   missing value supplied. The recorded proof claimed READY because it only ever sent the
   MINIMAL sample, which omits the two fields that break it.

All three are fixed and regression-tested, along with three quality defects and one
cosmetic one. Coverage is unchanged where it should be; the semantic corpus improved
by ten rules through two sound vocabulary additions.

**MVP status: READY. Blocking software defects: 0.**

## 2. Base SHA

`e8a77f8a5d90be8d5690b54711cdc4174d515df6` — verified equal to `origin/main` before
branching.

## 3. Branch

`feat/final-mvp-release-hardening`

## 4. Baseline, re-measured rather than trusted

The engagement brief quoted figures from the previous report. Re-measuring found two of
them stale:

| Measure | Brief said | Actually was |
|---|---:|---:|
| Rules EXACT | 330 | **335** |
| Rules UNSUPPORTED | 466 | **461** |
| MT catalogue entries | 481 | 481 ✓ |
| Generation-ready entries | 424 | 424 ✓ |
| Distinct types ready | 258 / 271 | 258 / 271 ✓ |
| SR2026 / SR2025 ready | 210 / 198 | 210 / 198 ✓ |
| Backend tests | — | 1,611 passed, 23 skipped |

## 5. Final architecture

Unchanged, and deliberately so. Knowledge base → (RAG / LLM) and (Structure Engine) →
canonical values → deterministic rules → Mapping Pack → deterministic composer → MT FIN or
MX XML. No model writes FIN or XML. The deterministic endpoints make zero model calls.

## 6. Structural MT coverage

| Measure | Value |
|---|---:|
| MT catalogue entries | 481 (16 configured, 465 knowledge-preview) |
| Generation-ready entries | 424 |
| Blocked entries | 57 |
| Distinct MT message types | 271 |
| …with at least one generation-ready structure | 258 |
| SR2026 ready | 210 / 210 |
| SR2025 ready | 198 / 255 |
| Universal generation matrix | 408 / 408 |
| MX generation-ready | 15 / 15 (7 configured + 8 `pacs` preview) |

## 7. The remaining blocked MT types

Thirteen distinct types have no generation-ready structure in any release. All thirteen are
category-0 FIN **system** messages exchanged with the network itself, not business
messages.

| Root cause | Types |
|---|---|
| `PROWIDE_NO_BLOCK4_FIELDS` — the model states no Block 4 field groups and no guide exists | MT035, MT043, MT048, MT049, MT096 |
| `FORMAT_NOTATION_NOT_IN_SOURCE` — the only notation is a Prowide-internal macro with no SWIFT spelling | MT021, MT023 (`<HHMM><MIR>1!a<?>`), MT056 (`<YYMMDDHHMM><?>`), MT063 (`<CC>[14<DATE1>]`), MT074, MT090, MT092, MT094 (`{65x}n`) |

`<?>` is an explicit *unknown* in the only source that describes these messages. Choosing a
width for it would be an invention, which the brief forbids and which the platform's own
invariants forbid. **These stay blocked, and each has a deterministic reason, a visible
catalogue state (`generatable: false`), no crash and no dead end.**

The 35 `QUALIFIER_EVIDENCE_MISSING` and 17 `FORMAT_NOTATION_NOT_IN_SOURCE` *entries* are
release-bound, not additional blocked types: the same message is generation-ready in the
SR2026 lane where its guide is read.

## 8. Semantic coverage

| Disposition | Before | After |
|---|---:|---:|
| Rules discovered | 911 | 911 |
| EXACT | 335 | **345** |
| PARTIAL_WEAKER_THAN_SOURCE | 115 | 115 |
| UNSUPPORTED | 461 | **451** |
| Review-required candidates | 450 | 460 |
| Reviewed / runtime activations | 0 / 0 | 0 / 0 |

Guides read: 156, unreadable 0. Guides stating Network Validated Rules: 128.

## 9. LLM-assisted rule translation — and why it was not the lever

The brief expected the 416 unrecognised sentence forms to be the largest remaining
engineering opportunity, attacked with RAG plus a two-pass extraction and a refuter. The
existing pipeline already implements exactly that discipline, and re-running it changed
nothing, so the real question was whether the *closed template vocabulary* was missing
recurring shapes.

A local analysis of every unrecognised sentence (scratchpad only; no guide text is
committed) answered it:

- The most common **opening phrase** accounts for 16 rules out of 416.
- **199 of the 416** restate themselves as a flattened dependency table whose prose
  introduction is a different sentence each time.
- Of what remains after the two additions below, the largest single tractable shape is
  worth **8 rules**, and **48** turn on a *subfield* — component scope, which the engine
  records as `COMPONENT_SCOPE_NOT_EXPRESSIBLE` precisely because approximating it makes the
  rule **stronger** than its source.

There is no change that moves hundreds of rules soundly. Claiming otherwise would mean
shipping rules that reject messages SWIFT accepts — the one outcome a testing platform must
never produce.

## 10. Rule DSL changes

None. The DSL was sufficient; the *vocabulary* was not. Two additions, both provably
weaker-or-equal:

- **`is present and contains <CODE>`** as a compound condition, read before the bare
  presence clause. It is exactly the value predicate: a code cannot be present in an absent
  field. Previously the alternation stopped at *"is present"* and left the rest of the
  sentence for the consequence to fail on. **+7 exact.**
- **`ONLY_IF_PRESENT`** — the guide's reversed form, *"In sequence D, field 30F may only be
  present if field 34B is present"*. Restricted to a condition that is itself a field's
  presence, because *"…when field 23 specifies an American style option"* is prose about a
  value this engine cannot evaluate. **+3 exact.**

`make mt-mrg-evaluate`: 29 / 29 cases pass.

## 11. Semantic preview

Two lanes, unchanged and enforced. `AUTHORITATIVE_RUNTIME` loads only reviewed packs and
**refuses** rather than skipping anything else. Every candidate is `REVIEW_REQUIRED`, none
is written to `config/rules/`, and runtime activations are **0**. The bulk review dashboard
(`docs/generated/mt-semantic-rule-coverage.md`) and 156 per-message reviewer packages
(`docs/generated/mt-rule-review/`) let a reviewer work rule-by-rule without reading a PDF
end to end.

## 12. Reviewed runtime state

0 reviewed, 0 active. Unchanged, and correct: nobody in this engagement is a SWIFT subject
matter expert, and the product does not pretend otherwise.

## 13. MT→MX mapping state

| Evidence class | Packs |
|---|---:|
| `SOURCE_BACKED` | **0** |
| `NAME_CORRESPONDENCE` | 1 (MT103 → pacs.008) |
| `TARGET_RELATIONSHIP_ONLY` | 1 (MT202 → pacs.009) |
| `SYNTHETIC` | 1 (MT541 → sese.023) |

No pack is source-backed because the corpus holds no field-level mapping material. The
knowledge-base sweep that established that (`app/mapping/evidence.py`) was re-run and its
conclusion is unchanged. A non-production pack executes only behind an explicit per-request
opt-in, and every response carries its evidence class and limitations.

## 14. Occurrence-aware mapping

Pack references carry sequence and occurrence through the canonical `OccurrenceIdentity`
model shared with the Rule Engine; there is no second occurrence system. The conversion
report attributes every target value to the source occurrence it came from.

## 15. Conversion proofs

| Proof | Before | After |
|---|---|---|
| MT541 → sese.023 | READY | READY, XSD accepted |
| MT202 → pacs.009 | READY on the minimal sample only | READY, XSD accepted, **widest** sample |
| MT103 → pacs.008 | **never completed** | READY, XSD accepted, **widest** sample |

The proof runner now uses the widest deterministic sample the message has. A minimal sample
carries the mandatory rows and nothing else, so it never exercises an optional field's
transform — which is exactly where the defect lived.

## 16–21. RAG, embeddings, AI, samples, cache, telemetry

All PASS, all verified against the operator's real corpus.

- **Retrieval** is `HYBRID` on this machine (the operator permits embedding of the real
  sources); lexical-only under the shipped default policy, and the status endpoint says so.
- **Embeddings**: `azure_openai`, 3,072 dimensions, 16,656 vectors for 16,656 segments.
- **`/ai/ask`** answers from the indexed guides with citations by source id, page and
  section, and a `SUPPORTED` verdict; where evidence is insufficient it says so and cites
  nothing.
- **AI Typical Sample** is validated by the deterministic engine before it reaches the
  form. A repeat request reports `Cache: HIT — 0 model calls`.
- **Cache key** spans structure checksum, rule-pack ids, prompt version, schema version,
  provider, model, lane and release. Bumping `PACK_COMPILER_VERSION` this engagement
  correctly invalidated and recompiled all 489 structures.
- **Telemetry** is a bounded, content-free ledger: identifiers and counters, never a
  prompt, a message value or source text.

## 22–30. Create Message, Guided, Expert, Intelligence, Excel, JSON, imports, round trip, downloads

All PASS. 57 of 57 generation paths (16 configured MT, 7 configured MX, 18 preview MT
across categories 0–9, 8 preview `pacs`, plus lifecycle) generated and validated. Every
import round trip returned `identical: true` with 0 unexplained differences. Both Excel
templates uploaded and generated 3/3 scenarios. Downloads and the evidence ZIP work.

## 31–32. Knowledge and Git LFS

164 / 164 source files verified with real bytes and recorded hashes
(`make knowledge-verify`). 16,656 segments, 489 compiled structures. The sync no longer
counts its own `source-manifest.json` as an unsupported source.

## 33–35. Quickstart, clean clone, Docker

- **Clean clone** into a separate directory, no copied `.venv`, `node_modules`, build,
  database, index or cache, and **no `.env`**: `git clone` (LFS content filtered, 36 MB,
  164 files) → `make install` → `make migrate` → `make knowledge-verify` **164/164** →
  `make check` **green** → `make e2e` **99 / 99**.
- **Docker**: `docker compose config` valid, both images build, `docker compose up`
  brings the backend up **healthy** and the frontend serving. MT541 and sese.023 were both
  generated *inside the container*, and the browser rendered the app against it. Stopped
  cleanly with `docker compose down`.

## 36. Security

`make secret-scan` clean. `make audit` (`pip-audit`, `npm audit --omit=dev`) clean. No
`.env`, credential, session state, knowledge database, vector cache, AI cache or browser
profile is tracked. Every error response is a typed envelope; no stack trace reaches a
caller; no probe produced a 5xx.

## 37. Performance

Warm, local, on the operator's machine:

| Operation | Latency |
|---|---:|
| Catalogue | 1 ms |
| Configured MT / MX generate | 1–3 ms |
| Preview MT generate | 2–13 ms |
| Conversion (mapping + compose + XSD) | 2–43 ms |
| Message by id, download, evidence ZIP | 1–2 ms |
| Cached AI sample | 3 ms |
| Knowledge search | 0.4–3.9 s |
| AI ask | 6.8 s |
| AI identify / test-data | 8.4–8.5 s |

No regression against the previous engagement's Create Message improvements.

## 38. Backend tests

**1,639 passed, 27 skipped, 6 deselected** (was 1,611 / 23 / 6). `ruff` clean.
`mypy --strict` clean over 238 files.

New this engagement:

- `tests/studio/test_field_format_presentation.py` — 16 cases on how a format is described,
  what counts as a currency, and that a configured row keeps its authored sentence.
- `tests/studio/test_conversion_completion.py` — the missing-data loop must converge; the
  decimal must not carry a comma; the target lane decides the pack.
- `tests/studio/test_degraded_mode.py` — 10 cases: no model, no knowledge base, missing
  database, failing embeddings, and a typed error envelope on every failure path.

## 39. Playwright

**98 / 98** locally, **99 / 99** in the clean clone. New: a browser regression that watches
the convert request body for `targetLane`, because that defect was invisible from the API.

## 40. Browser UAT

Every primary route walked in headed Chrome on `127.0.0.1` and `localhost`: Create Message
(search, lane selection, deterministic sample, AI sample, edit, validate, generate, copy,
download), Bulk / Excel, Message Intelligence (deterministic search and the Ask panel),
Validate, API & Automation, Convert Message (full loop to a valid pacs.008), Recent
Messages, AI & Knowledge Usage, Knowledge Base.

**0 unexpected application console errors. 0 failed API requests. 0 dead-end controls.**
The only console exceptions came from a browser extension, which AGENTS.md gotcha 58
already records as not ours.

## 41. Bugs found and fixed

| # | Severity | Defect | Fix |
|---|---|---|---|
| 1 | BLOCKING | `127.0.0.1:3000` never hydrated; no API request ever made | `allowedDevOrigins` names both spellings |
| 2 | BLOCKING | Convert Message refused every candidate conversion | send `targetLane` from the chosen target |
| 3 | BLOCKING | MT103 → pacs.008 unreachable: comma decimal into an ISO decimal, `SYN` currency | `MT_DECIMAL_TO_ISO`; `3!a` before a decimal is a currency; proofs use the widest sample |
| 4 | HIGH | 599 preview rows silently downgraded to a text box | `InputKind` gained `CURRENCY` and `DATETIME`, with controls |
| 5 | HIGH | Conversion asked for missing data with an empty question | fall back to the field's own business name |
| 6 | MEDIUM | Raw Prowide notation as the "expected format"; dead currency box on a composite amount | `describe_format`; `format_notation` as its own field; `currencyLeads` |
| 7 | LOW | Knowledge sync counted its own manifest as an unsupported source | skip `MANIFEST_NAME` in discovery |

Two defects were introduced and caught during the work, both by the repository's own gates:
replacing the notation with prose broke sample generation for the whole preview lane
(`MT_MANDATORY_FIELD_MISSING`), and reading every lone `3!a` as a currency mislabelled 71A
Details of Charges. Both are recorded as gotchas 72 and 74.

## 42. Remaining external capability boundaries

Not software defects. Each is documented and visible in the product:

- 13 MT system message types have no deterministic structure evidence in any supplied
  release.
- 451 of 911 Network Validated Rules have no sound weaker-or-equal expression. All recorded
  with a reason; none silently ignored; none active at runtime.
- No Mapping Pack is `SOURCE_BACKED`; no authoritative MT↔MX field-level mapping material
  exists in the corpus.
- The four `sese` lifecycle specifications remain `UNVERIFIED`.
- XSD is `SUBSET_DERIVED` unless the operator supplies the official schema.
- No SWIFT certification, no live network connectivity, no conformance claim.
- Import cannot represent a repeatable block nested inside another; detected and refused.
- Rate limiter, AI circuit breaker and L1 cache are per process.

## 43. MVP readiness conclusion

**READY.** All 40 acceptance items of the engagement brief hold. Zero blocking software
defects. Everything that remains is an evidence or licensing boundary, stated plainly in
the product and in `docs/limitations.md`.

## 44. Demo walkthrough

`docs/demo/final-mvp-demo-guide.md` — ten minutes, with a fallback path for every step that
needs no live AI.

## 45. Exact start commands

```bash
git clone https://github.com/ahammedejaz/SwiftGenerator.git
cd SwiftGenerator
git lfs pull
make quickstart            # Docker; first run creates .env with generated local secrets
# or, without Docker:
make install && make migrate && make dev
# then open http://127.0.0.1:3000
```

Tester checklist: `docs/testing/final-mvp-uat-checklist.md`.

## 46–50. Release facts

- **Base main:** `e8a77f8a5d90be8d5690b54711cdc4174d515df6`
- **Branch:** `feat/final-mvp-release-hardening`
- **Feature SHAs:** `d19835a` (the fixes) and `36e3d70` (the release documents).
- **PR:** <https://github.com/ahammedejaz/SwiftGenerator/pull/22> — open, non-draft, base
  `main`, `MERGEABLE` / `CLEAN`, merge base equal to the recorded base main SHA.
- **CI on the exact head `36e3d70`:** all six jobs pass — Required Checks 2m30s, Clean
  Clone 2m39s, MT Prowide Source 32s, Browser E2E 7m15s, Docker 1m8s, Security Audit 1m6s
  (run `32522040683`).
- **Branch protection** verified before attempting the merge: `Required Checks` is the
  required context, `strict` is on, force pushes and deletions are blocked.
- **Merge: NOT PERFORMED.** `gh pr merge 22 --squash --match-head-commit 36e3d70` was
  refused by the development environment's own permission policy, not by GitHub and not by
  branch protection. Everything the brief asks for before a merge is done and green; the
  merge itself, the resulting main SHA and the post-merge CI run remain outstanding and
  need a human to run that one command.

## 51. Live provider proofs

Never part of CI — they need a key and cost money. Run on the operator's machine on
2026-08-22:

| Proof | Result |
|---|---|
| `make probe-embeddings` | PASS — `azure_openai`, `text-embedding-3-large`, 3,072 dimensions, 1,815 ms, 31 tokens |
| `make test-live-rag` | PASS — Recall@5 **1.0**, MRR **0.875**, citation accuracy **1.0**, message accuracy **1.0**, release accuracy **1.0**, deterministic ordering true |
| `make test-live-ai-sample` | PASS — 5 passed; the second call is a cache HIT with 0 model calls |

The live RAG evaluation embeds the synthetic fixture corpus only, never the operator's
licensed documents, whatever the policy settings say (gotcha 59).
