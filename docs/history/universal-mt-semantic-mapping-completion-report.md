# Universal MT generation, semantic rules and MT→MX mapping — completion report

Engagement date: 2026-08-21. Base: `main` at `0bbd7d097b876cef3956ad2358446071bdf7516a`.
Branch: `feat/universal-mt-semantic-mapping-completion`. Plan:
[../universal-mt-semantic-mapping-completion-plan.md](../universal-mt-semantic-mapping-completion-plan.md).

## Executive summary

The knowledge base (156 SR2026 Message Reference Guides, 8 `pacs` XSDs) is now read in full by
one generic reader and one generic compiler. MT generation moved from 250 generation-ready
catalogue entries to 424 (every SR2026 guide-backed structure, 210/210; 258 of 271 distinct
MT types) without a single message-specific branch. Every numbered Network Validated Rule in
every guide (911 rules across 128 rule-bearing guides) received a disposition — 330 exact,
115 weaker-than-source, 466 unsupported with a named reason — and a per-message review pack;
none was activated. The whole knowledge base was searched for MT↔ISO 20022 mapping evidence:
it holds **no** field-level coexistence or translation material, so no mapping is labelled
authoritative. Two cited candidate packs (MT202→pacs.009, MT103→pacs.008), a relationship
registry with evidence classes, and deterministic conversion proofs were added instead. The
source tree `swiftKnowledgeBase/` is committed through Git LFS with a verified manifest, so
`git clone → git lfs pull → make quickstart` yields a working application.

## Starting and final coverage

| Measure | Base `0bbd7d0` | Final |
|---|---:|---:|
| MT catalogue entries | 419 | 481 |
| Generation-ready entries | 250 (16 configured + 234 preview) | 424 (16 + 408) |
| SR2026 structures ready | 47 / 146 | 210 / 210 |
| SR2025 (Prowide) structures ready | 187 / 271 | 198 / 271 |
| Distinct MT types with a ready structure | 227 / 271 | 258 / 271 |
| API generation matrix (sample → FIN → import → round trip → Excel → JSON) | — | 408 / 408 |
| Guides read for semantic rules | 2 (MT540, MT541) | 156 |
| Rules with a disposition | 38 | 911 |
| Mapping packs with citations | 0 | 2 (+1 synthetic fixture) |

Generated evidence: `docs/generated/universal-mt-generation-coverage.md`,
`docs/generated/mt-generation-blockers.md`, `docs/generated/mt-semantic-rule-coverage.md`,
`docs/generated/mt-rule-review/*.md` (156), `docs/generated/mt-mx-mapping-coverage.md`.

## 419 MT blocker audit → generic fixes → messages unlocked

The 169 blocked entries at base were grouped by root cause before any code was touched. Each
fix is generic (reader, compiler, format grammar, composer/parser) and is listed with the
defect it removed in [../universal-mt-generation.md](../universal-mt-generation.md):

| Root cause at base | Generic fix | Unlocked |
|---|---|---:|
| Guides with no `16R` sequences compiled to no structure (flat Cat 1/2/9, MT101 A/B, MT300 `15A`-delimited) | unbracketed `ROOT` and path-keyed sequences, Prowide delimiter cross-check | 61 |
| Multi-row `---->` blocks read as independent rows; nested arrows (MT801) | implicit repetitive groups (`_A`, `B1_A`), repeat stack | 19 |
| Misnumbered table rows stalled the reader (MT548) | delimiter rows authoritative, ±3 resync recorded as `ROW_NUMBER_RESYNC_…` | 8 |
| Prose swallowed row 1, wrapped formats truncated, `No letter option` unparsed | shortest-tail row split, fragment joining, bare-tag option | 24 |
| Covers with `(`, `,`, `MT n9x` unidentified; wrapped titles; common-group guides | widened identification; one structure per Prowide member (`MT190`…`MT990`) | 14 |
| Format grammar lacked groups/alternation/bounded repeats; Prowide-only macros | `N*(…)`, `A|B`, `[…]*N`; guide FORMAT notation as per-option fallback | 21 |
| Code lists merged across tags; open lists enforced; wide/camel-case codes missed | exact-tag specs, open lists → no allowed set, single-token rule | 11 |
| Same tag twice in a sequence (MT011 `175`, MT360 `18A`, MT942 `34F`) | ordinal addressing in composer, parser, Excel, JSON | 6 |
| Nested unbracketed repeats refused on import; all-optional mandatory sequences never materialised | implicit parent opening, nearest-structure ranking; sample opener logic | 10 |

(Counts are entries whose first failed gate moved to `GENERATION_READY` after the fix, from the
gate matrix at each step; several entries needed more than one fix.)

## Remaining generation blockers (57 entries, 13 MT types without any ready structure)

| Root cause | Entries | Why it is not fixed in code |
|---|---:|---|
| `QUALIFIER_EVIDENCE_MISSING` | 35 | SR2025 Prowide-only Cat 3/5 structures; Prowide records no qualifier legality. The SR2026 lane of every one is ready. Reusing SR2026 tables for SR2025 would conflate releases. |
| `FORMAT_NOTATION_NOT_IN_SOURCE` | 17 | Cat 0/6/8 messages whose only notation is a Prowide macro and for which no guide exists. A pattern would be invented. |
| `PROWIDE_NO_BLOCK4_FIELDS` | 5 | MT035/043/048/049/096: no Block 4 groups in Prowide, no guide. |

## Structural architecture, composer/parser, samples, Excel/API, import/round trip

- IR: `PackSequence`/`PackRow` (`app/knowledge_base/structures/mt_pack.py`), compiled by
  `knowledge-pack-compiler/6` from `mt-mrg-reader/3` artifacts + Prowide; identity includes the
  guide artifact checksum so a reader change recompiles.
- Gates LOAD→SAMPLE→VALIDATE→COMPOSE→PARSE→ROUND_TRIP, every failure recorded on the structure
  and in the catalogue; `MT_GENERATION_GATE` test runs the fixture corpus in CI and the real
  corpus with `KNOWLEDGE_MATRIX_DB`.
- Composer/parser: ordinal `rows_at` addressing, implicit parent occurrences, nearest-structure
  leading-tag ranking; Block 4 only — Blocks 1/2 from configured interface values, no Block 5,
  MAC, CHK or session values ever produced.
- Samples: MINIMAL opens mandatory sequences with their first value row; FULL configured subset
  unchanged; AI typical samples validated through the same engine before return.
- Excel/JSON API: same addressing; 408/408 entries round-trip through Excel template → upload.
- `make knowledge-rebuild-structures` re-reads cached page text and recompiles all packs.

## Semantic source inventory, rules, DSL, dispositions, review state

- Sources: 156 guides, identified from their covers (no catalogue); evidence index
  `backend/tests/fixtures/mt_mrg/sr2026-corpus-evidence.json` carries identity, hashes, pages,
  dispositions — no rule text. `make mt-mrg-corpus-check` (in `make check`) fails on drift.
- 911 rules discovered; 330 `EXACT`, 115 `PARTIAL_WEAKER_THAN_SOURCE` (residual recorded),
  466 `UNSUPPORTED` (421 sentence form, 10 component scope, 10 unresolved ref, 9 ambiguous ref,
  9 envelope-dependent, 7 arithmetic). Nothing silently skipped; nothing stronger than source.
- Phase 5B MT540/MT541 result (23 exact / 15 partial / 0 unsupported) unchanged.
- Rule DSL `rule-dsl/3`: component `extract`/`otherExtract` (regex derived from the field's own
  notation) and `allEqual`; /1 and /2 packs load unchanged.
- 19 generic templates in `templates_generic.py` (conditional presence with scopes, dependency
  tables as token streams, currency consistency, either/or, counts, uniqueness, refusals).
- Review state: 445 candidates `REVIEW_REQUIRED`, 0 reviewed, 0 active; runtime registry
  unchanged; review packs per MT in `docs/generated/mt-rule-review/`.

## Mapping source inventory, real mappings, partial mappings, blockers, proofs

- Sweep (`make mt-mx-mapping-scan`): 164 sources, 16,656 segments, fixed phrase vocabulary,
  results by identity in `backend/config/mappings/evidence-index.json`.
- Finding: no coexistence/migration/translation document in the KB. The MT205 Scope names the
  ISO 20022 Financial Institution Credit Transfer as the equivalent of MT200/201/202/203/205 —
  the only documentary target relationship. MT101/103/200/202/205 say "converted to the ISO
  20022 equivalent over FINplus" without naming it.
- Evidence classes `SOURCE_BACKED` / `TARGET_RELATIONSHIP_ONLY` / `NAME_CORRESPONDENCE` /
  `SYNTHETIC`; the model refuses an uncited `SOURCE_BACKED` rule and refuses `REVIEWED` on
  name-only or synthetic packs. **No pack is `SOURCE_BACKED`; none is production eligible.**
- Relationships registry: MT205(+200/201/202/203)→pacs.009 (`TARGET_RELATIONSHIP_ONLY`),
  MT103(+102)→pacs.008 and MT104(+107)→pacs.003 (`NAME_CORRESPONDENCE`, the latter with no
  pack: `NO_DOCUMENT_RELATES_THE_TWO`), MT541→sese.023 (`SYNTHETIC`).
- Candidate packs: `CANDIDATE_MT202_TO_PACS009_V1` (17 rules, all cited to the MT field page
  and the XSD element), `CANDIDATE_MT103_TO_PACS008_V1` (21/21) — review state
  `CANDIDATE_PREVIEW`, opt-in only, every response labelled. Operators DIRECT / TRANSFORM /
  CODE_MAP / CONDITIONAL / ONE_TO_MANY / MANY_TO_ONE / OMIT / NOT_REPRESENTED /
  TARGET_REQUIRED_MISSING; transforms `MT_DATED_AMOUNT_DATE`, `MT_DATED_AMOUNT_TO_ISO`,
  `MT_PARTY_BIC` added; `NEEDS_INPUT` now also raised for mandatory blocks (pacs.009 Debtor).
- Blockers: no CBPR+/translation material in the KB; no `pain.001`, `camt.05x`, `camt.056`
  schemas; repeated structures addressed at occurrence 1.
- Proofs (`make mt-mx-mapping-write`, checked in `make check`): MT202→pacs.009 `NEEDS_INPUT`
  ×3 → `READY`, 6/6 mandatory, XSD accepted; MT103→pacs.008 ×6 → `READY`, 7/7; MT541→sese.023
  `READY`, 8/8. LLM not in the path.

## Knowledge Git LFS and fresh clone

- `.gitattributes`: `swiftKnowledgeBase/**/*.pdf|PDF|zip|xsd|docx|xlsx` via LFS; 164 files,
  38,423,389 bytes; `swiftKnowledgeBase/source-manifest.json` (`knowledge-source-manifest/1`)
  with size, SHA-256 and content identity per file; `make knowledge-verify` names
  `LFS_POINTER_NOT_FETCHED` / `SOURCE_HASH_MISMATCH` / `SOURCE_NOT_IN_MANIFEST`.
- Never committed: `build/knowledge/**` (SQLite, vectors, packs, text cache), `.env`, browser
  state, `workPrompt.txt`, `automationPrompt.txt`.
- `scripts/quickstart.sh` pulls LFS, refuses on pointers, verifies the manifest, starts the
  stack, syncs in the background (`/app/data/knowledge-sync.log`).
- CI: only the Clean Clone job checks out with `lfs: true` and runs `make knowledge-verify`.
- Fresh clone: see *Clean clone* below.

## AI/RAG usage

Fake providers in CI and in `make check`. Live lane (operator policy, Azure): embeddings
probe PASS (3072 dims), `test-live-ai-sample` 5 passed, AI typical samples MT103/202/540/940/564
validated (cache HITs avoided 4,695 / 3,167 / 8,084 / 15,681 tokens; MT540 was a live MISS that
validated on first return), `POST /ai/ask` answers with citations. Telemetry over the
engagement: 73 LLM operations, 57 calls, 208,979 prompt / 16,524 completion tokens. The LLM
never decides a structure, a rule disposition, a mapping or a mandatory target value.

## Performance

Full knowledge sync of 164 sources: minutes (PDF parse dominated); `knowledge-rebuild-structures`
from the text cache: seconds for all 210 SR2026 + 271 SR2025 packs; API generation matrix over
408 entries inside the pytest run; `make check` ≈ 5 min locally.

## Backend tests, Playwright, browser UAT

- `make check` (ruff, mypy, pytest with coverage gate, corpus check, mapping check, frontend
  lint/typecheck): see *Verification* below.
- `make e2e`: 98 passed (Playwright, fake providers).
- Browser UAT in Chrome against `KNOWLEDGE_MODE=local_uat`: Create → MT → search lists both
  MT101 lanes labelled by release → SR2026 preview → minimal sample → Guided/Expert toggle →
  Validate "Ready to generate" → Generate: valid FIN with Blocks 1/2/4 only, annotated fields,
  Copy/Download; Convert to MX hand-off; Convert page states "No Mapping Pack and no recorded
  relationship" for MT101 and disables preview. The only console error was a hydration warning
  injected by a browser extension (`bis_skin_checked`), not application code.
- UAT defect found and fixed: the Convert page did not pass the source lane/release to
  `conversion-targets`/`convert`, so an MT202 generated in the SR2026 preview lane saw no
  candidate pack in the UI (the API already accepted `sourceLane`/`sourceRelease`). The
  Create→Convert hand-off now carries lane and release and the page sends them.

## Docker, clean clone, CI, merge, post-merge CI

Recorded below once executed.

## Known limitations

- 13 MT types (FIN system / Cat 0, macro-only or empty Prowide models) have no authoritative
  structure in the KB; 35 SR2025 Cat 3/5 entries wait on release-bound qualifier evidence.
- 421 NVR sentence forms are recorded, not translated; 310 are unique in the corpus.
- No mapping is source-backed; candidate packs are reviewer input, never authority.
- Repeated MT sequences / MX structures are mapped at occurrence 1.
- `YYMMDD` is read as `20YY-MM-DD` in dated-amount transforms.
