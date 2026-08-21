# Final MVP / POC release plan

The last implementation engagement on this repository. Everything below is measured from
the working tree at base `e8a77f8`, on branch `feat/final-mvp-release-hardening`, on the
operator's machine with the committed Git-LFS knowledge base present and AI credentials
configured. Nothing here is copied from an earlier report.

---

## 1. Executive goal

Leave the Financial Message Studio **internal MVP / POC ready**: it clones, starts,
demonstrates, tests and automates without a workaround, and every remaining boundary is a
stated evidence limitation rather than a software defect.

The product proposition is unchanged and is not being re-architected:

> Authorised MT/MX standards knowledge and deterministic structure; RAG + LLM help a user
> understand, populate, test and convert; deterministic engines generate and validate the
> actual MT FIN and MX XML.

## 2. Current product state — measured, not quoted

| Measure | Value | How it was measured |
|---|---:|---|
| Backend tests | 1611 passed, 23 skipped, 6 deselected | `make check` |
| ruff / mypy --strict | clean over 237 files | `make check` |
| `make check` overall | green | all 13 sub-targets |
| `make secret-scan` | clean | tracked files |
| `docker compose config` | valid | exit 0 |
| `git diff --check` | clean | — |
| Knowledge sources | 164/164 verified | `make knowledge-verify` |
| Indexed segments / embeddings | 16,656 / 16,656 | `make knowledge-status` |
| Compiled structures | 489 | `make knowledge-status` |
| Catalogue entries | 496 (481 MT + 15 MX) | `GET /api/v1/catalogue` |
| MT generatable entries | 424 / 481 | same |
| Distinct MT types | 271; 258 with a generation-ready structure | same |
| MX generatable | 15 / 15 (7 configured + 8 preview `pacs`) | same |
| SR2026 ready / SR2025 ready | 210 / 210 · 198 / 255 | `docs/generated/universal-mt-generation-coverage.md` |
| Semantic guides / rules | 156 / 911 | `docs/generated/mt-semantic-rule-coverage.md` |
| Rule dispositions | 335 EXACT · 115 PARTIAL · 461 UNSUPPORTED | same |
| Review-required / reviewed / active | 450 / 0 / 0 | same |

The baseline numbers in the engagement brief (330 EXACT / 466 UNSUPPORTED) are **stale by
five rules**; the measured figures above are the ones this engagement works from.

## 3. Current architecture

Unchanged and correct. Knowledge base → (RAG/LLM) and (Structure Engine) → canonical
values → deterministic rules → mapping engine → deterministic composer → MT FIN / MX XML.
No model writes FIN or XML. Deterministic endpoints make zero model calls.

## 4. Remaining MT structure gaps

13 distinct MT types have no generation-ready structure in any release:

- **`PROWIDE_NO_BLOCK4_FIELDS` (5):** MT035, MT043, MT048, MT049, MT096. The Prowide model
  states no Block 4 field groups and no guide exists. There is nothing to compile.
- **`FORMAT_NOTATION_NOT_IN_SOURCE` (8):** MT021, MT023 (`<HHMM><MIR>1!a<?>`), MT056
  (`<YYMMDDHHMM><?>`), MT063 (`<CC>[14<DATE1>]`), MT074/MT090/MT092/MT094 (`{65x}n`).
  The only notation is a Prowide-internal macro with no SWIFT spelling.

All 13 are FIN **system** messages (category 0) exchanged with the network itself, not
business messages. `<?>` is literally "unknown" in the Prowide source; inventing a width
for it would be an invention, which §13 of the brief forbids. **Decision: they stay
blocked, with a deterministic reason, a visible UI state and no dead end.**

The 35 `QUALIFIER_EVIDENCE_MISSING` and 17 `FORMAT_NOTATION_NOT_IN_SOURCE` *entries* are
release-bound: the same message type is generation-ready in the SR2026 lane where its
guide is read. They are not additional blocked types.

## 5. Remaining semantic gaps

461 unsupported of 911. Root causes, measured: 416 `SENTENCE_FORM_NOT_RECOGNISED`, 10
`COMPONENT_SCOPE_NOT_EXPRESSIBLE`, 10 `REFERENCE_NOT_RESOLVED`, 9 `REFERENCE_AMBIGUOUS`,
9 `ENVELOPE_DEPENDENT`, 7 `ARITHMETIC_NOT_MODELLED`.

A local analysis of the 416 unrecognised sentences (scratchpad only; no guide text is
committed) shows the tail is genuinely long: the most common opening phrase accounts for
16 rules, and 199 of the 416 restate themselves as a flattened dependency table whose
prose introduction is a different sentence form each time. There is no single change that
moves hundreds of rules soundly.

**Decision:** extend the closed template vocabulary only where a form recurs *and* a
weaker-or-equal expression provably exists — starting with the compound condition
`is present and contains <CODE>`, which is exactly equivalent to a value predicate and is
the clearest recurring gap. Measure the gain, keep what is sound, and record the rest with
its reason. Do **not** approximate component-scoped, arithmetic or envelope-dependent
rules; a stronger rule rejects messages SWIFT accepts, which is the one outcome a testing
platform must never produce.

## 6. Remaining conversion gaps — and the defects found

Three POC proofs exist. Measured behaviour before this engagement:

| Proof | API | Browser |
|---|---|---|
| MT541 → sese.023 (`SYNTHETIC`) | READY, XSD passes | works |
| MT202 → pacs.009 (`TARGET_RELATIONSHIP_ONLY`) | NEEDS_INPUT → READY after 2 values | **fails** |
| MT103 → pacs.008 (`NAME_CORRESPONDENCE`) | **never completes** | **fails** |

## 7–12. Current AI/RAG behaviour, user flows, automation, clone/start, bugs, performance

AI/RAG is strong. `/api/v1/ai/ask` answers from the indexed corpus with citations and a
`SUPPORTED` verdict; retrieval is `HYBRID` (lexical + semantic) because the operator has
allowed embedding of the real corpus; the sample cache reports `Cache: HIT — 0 model
calls`. The AI & Knowledge Usage page shows calls, tokens, latency, cache-hit rate, RAG
queries, retrieved sections and embedding state, with no secrets and no source text.

Every one of the 57 generation paths exercised (16 configured MT, 7 configured MX, 18
preview MT across categories 0–9, 8 preview `pacs`, 3 lifecycle) generated and validated.
Every import round trip (MT FIN, MT Block 4, MX, both lanes) returned `identical: true`
with 0 unexplained differences. Both Excel templates uploaded and generated 3/3 scenarios.
Downloads, evidence ZIP, recent messages, Message Intelligence and the deterministic
search all pass.

**Latency measured** (warm, local): catalogue 1 ms, configured generate 1–2 ms, preview
generate 2–13 ms, conversion 2–43 ms, knowledge search 0.4–3.9 s, AI ask 6.8 s, AI
identify 8.5 s, cached AI sample 3 ms. No regression against the previous engagement.

**Browser walk:** every primary route renders with real data. **0 application console
errors** across the whole walk — the only console exceptions come from a browser
extension (`bis_skin_checked`, extension `executors/200.js`), which AGENTS.md gotcha 58
already records as not ours.

### Bugs found and reproduced

| # | Severity | Defect |
|---|---|---|
| 1 | **BLOCKING** | `http://127.0.0.1:3000` renders a permanently "Loading configured messages…" Create Message screen. Next.js dev blocks `127.0.0.1` as a cross-origin dev host (`allowedDevOrigins` unset), so the client never hydrates and **no API request is ever made**. The repository deliberately standardises on `127.0.0.1` (gotcha 21) and the docs point there. |
| 2 | **BLOCKING** | Convert Message fails with "Something went wrong — No exact Mapping Pack matches this source and target" for MT103→pacs.008 and MT202→pacs.009, even though the UI just listed the pack and the user ticked the preview opt-in. `ConvertMessage.tsx` omits `targetLane` from the convert request, so it defaults to `CONFIGURED` while both packs target `KNOWLEDGE_PREVIEW`. |
| 3 | **BLOCKING** | MT103→pacs.008 can never complete, even through the API with every declared missing value supplied: (a) MT field 36 maps to `XchgRate` with its raw SWIFT comma decimal `1000,`, which the MX FORMAT layer rejects; (b) the preview sampler invents currency `SYN` for a bare `3!a` component, which the client profile rejects. Neither is fixable by user input, so the flow dead-ends at `INVALID_TARGET`. |
| 4 | HIGH | The pack compiler emits `inputKind: CURRENCY` (83 rows) and `DATETIME` (497 rows), neither of which is a member of `InputKind`; `mt_loader.py` silently downgrades all 580 to `TEXT`. A field the compiler identified as a currency or a timestamp reaches the tester as a bare text box. |
| 5 | HIGH | `MissingTarget.question` is an empty string for every compiled preview target, so the conversion's "complete the missing data" prompt asks nothing. |
| 6 | MEDIUM | The knowledge sync counts `swiftKnowledgeBase/source-manifest.json` — its own manifest — as an `UNSUPPORTED_EXTENSION` source, so the Knowledge Base page permanently shows "Unsupported 1" and a failure entry. |

## 13. The remaining 13 MT types

Covered in §4. No code change; each must have a deterministic reason, a visible UI state,
no crash and an understandable explanation. Verify the catalogue marks them
`generatable: false` and the UI says why.

## 14–15. The 461 unsupported rules and the review strategy

Covered in §5. The review lane is already practical: `docs/generated/mt-rule-review/` holds
one reviewer package per message (156 of them) with rule id, source page, error codes,
candidate meaning, candidate AST and residual limitation, and
`docs/generated/mt-semantic-rule-coverage.md` is the bulk dashboard with per-message
counts. No reviewer has to read a PDF end to end. Runtime activations stay 0.

## 16–17. MT→MX mapping and preview policy

Do not rebuild. Fix the three defects in §6/§12, keep the five evidence classes
(`SOURCE_BACKED`, `TARGET_RELATIONSHIP_ONLY`, `NAME_CORRESPONDENCE`, `CANDIDATE_PREVIEW`,
`SYNTHETIC`) exactly as they are, and keep the explicit opt-in before a non-production
pack executes. No pack becomes `SOURCE_BACKED`: the corpus holds no field-level mapping
material, and the evidence sweep already recorded that.

## 18–21. RAG, LLM, AI samples, error handling

No change of strategy — all verified working. Confirm the documented failure fallbacks
(AI unavailable, embeddings unavailable, knowledge DB missing) by test rather than by
assertion.

## 22–29. UI, API, Excel, import/round-trip, knowledge, offline, AI-disabled, recovery

Verified working (§7–12). Harden the two UI defects (§12 #4, #6) and re-verify.

## 30. Security

Re-run `make audit`, `make secret-scan`, confirm no `.env`, credential, knowledge database,
vector cache or browser profile is staged, and confirm the knowledge sources tracked
through LFS remain the only large tracked artifacts.

## 31–34. Clean clone, Docker, UAT, CI

Clean clone into a separate directory with documented commands only; `docker compose
build` and an actual `docker compose up` health check; full desktop browser UAT (done, to
be repeated after the fixes); `make e2e`; six CI jobs on the exact feature head.

## 35–36. MVP and release criteria

The 40 acceptance items of brief §66, with **0 blocking software defects** as the gate.
Defects 1, 2 and 3 above are release blockers and must be fixed and regression-tested.

## 37. Honest final limitations

Unchanged from `docs/limitations.md`, plus:

- 13 MT system message types have no deterministic structure evidence in any supplied
  release. Not a defect; an evidence boundary.
- 461 of 911 Network Validated Rules have no sound weaker-or-equal expression. All are
  recorded with a reason; none is silently ignored; none is active at runtime.
- No Mapping Pack is `SOURCE_BACKED`. No authoritative MT↔MX field-level mapping material
  exists in the corpus.
- No SWIFT certification, no live network connectivity, no conformance claim.

---

## Self-review — the brief's critical questions

| Question | Answer before this engagement |
|---|---|
| Can a new user demo without knowing SWIFT? | Yes — **but only on `localhost`**. Defect 1. |
| Can a tester load a sample in one click? | Yes: Minimal, Full, AI Typical, AI Minimal, AI Full. |
| Generate MT and MX without a workaround? | Yes. |
| Automate with JSON / Excel? | Yes, both, verified. |
| Run without AI? | Yes — to be re-proved by test. |
| RAG failure breaks Create Message? | No; deterministic endpoints make no model call. |
| 400+ catalogue entries load reliably? | Yes — 496 entries, configured-first then enriched. |
| Can LLM output bypass the composer? | No. |
| Can mapping invent material data? | No — `NEEDS_INPUT`, verified. |
| Can SR2026 leak into SR2025? | No — lane and release are on every request. |
| Does preview look like authoritative validation? | No — provenance banner on every preview response. |
| Dead buttons? | **Yes — "Preview conversion". Defect 2.** |
| Silent errors? | No. |
| Console errors? | None from the application. |
| Stale docs? | AGENTS.md still describes Phase 6 as an unmerged branch and quotes pre-merge counts. To fix. |
| False "fully supported" wording? | None found. |

**Correction applied to this plan after self-review:** the brief assumed the 13 blocked MT
types might be unlockable with deeper investigation. They are not — `<?>` is an explicit
unknown in the only source that describes those messages. The plan states that as a
boundary rather than carrying an aspiration it cannot honour.

## Order of work

1. Defect 1 (`allowedDevOrigins`) — restores the documented address.
2. Defect 2 (`targetLane`) — restores the conversion demo.
3. Defect 3 (decimal transform + currency sampling) — completes MT103→pacs.008.
4. Defects 4, 5, 6 — input kinds, missing-target questions, manifest self-index.
5. Sound semantic vocabulary extension; measure; keep what is sound.
6. Regression tests for every fix.
7. Failure-mode proofs (AI off, embeddings off, knowledge DB missing).
8. Full suite, e2e, Docker runtime, clean clone, browser re-walk.
9. Documentation: audit, report, demo guide, UAT checklist, AGENTS/README/limitations.
10. Commit, PR, exact-head CI, merge, post-merge CI.
