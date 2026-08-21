# Universal MT generation, semantic ingestion and MT→MX mapping — completion plan

Engagement plan written before implementation, from a measured baseline on `main`
`0bbd7d097b876cef3956ad2358446071bdf7516a` (2026-08-21). Every number in §1–§7 was
measured on this machine from the knowledge database the operator's `swiftKnowledgeBase/`
folder produces; nothing is copied from a previous report. §47 is the self-review that
corrected the first draft.

## 1. Current counts

| Measure | Value | How measured |
|---|---|---|
| MT catalogue entries | **419** (16 configured + 403 knowledge-preview) | `build_catalogue()` — 417 MT structures − 16 shadowed + 2 source-only entries |
| MT structures (message × release) | 417 — SR2025 271, SR2026 146 | `knowledge_structure` |
| MT generation-ready entries | **250** (16 configured + 234 preview) | `readiness = GENERATION_READY` |
| MT blocked entries | **169** preview entries (183 structures − 14 shadowed non-ready) | see §4 |
| Distinct MT message types with ≥1 ready structure | 227 of 271 | — |
| MX structures | 15 (7 configured + 8 preview pacs), all generation-ready | — |
| Knowledge sources | 163 discovered: 146 MRG, 2 misidentified `USAGE_GUIDE` (MT110, MT752), 7 `UNIDENTIFIED` (MT n90–n99 guides), 8 XSD | `knowledge_source` |
| Backend tests | 1563 passed, 22 skipped, 6 deselected; ruff, mypy --strict (231 files) clean | `make check` |

## 2. Exact 419 MT inventory

The inventory is machine-generated: `docs/generated/universal-mt-generation-coverage.md`
lists every entry with category, release, structure source, generation, sample, parser,
round-trip, Excel, JSON, semantic source, rule count and fidelity. The baseline lists are
kept with the engagement: 271 Prowide SR2025 message models (categories 0–9), 146 SR2026
MRG structures, and the two guides the identifier could not place.

## 3. Exact 250 ready inventory

234 preview structures pass all six gates at baseline (187 SR2025 + 47 SR2026) plus the 16
configured messages. The per-entry list is in the generated coverage document, `Generation`
column, and in this engagement's blocker report as the "before" column.

## 4. Exact blocked MT inventory

183 structures (169 listed entries) fail a gate. First failing gate, grouped:

| # | First failing gate and detail | Structures | Examples |
|---|---|---:|---|
| G1 | LOAD "pack declares no sequences" | 76 | 71 SR2026 MRG (MT103, MT105, MT111 …), 5 SR2025 (MT035/043/048/049/096) |
| G2 | SAMPLE "generic fields without qualifier evidence" | 53 | SR2025 Prowide-only MT321, MT370, MT380/381, MT500–MT5xx |
| G3 | SAMPLE "no synthetic value" (format grammar) | 20 | MT021/023 `<HHMM><MIR>1!a<?>`, MT056 `<YYMMDDHHMM><?>`, MT063 `<CC>[14<DATE1>]`, MT074 `{65x}n`, MT600/601/620/604–608 26C `<VAR-SEQU-4>`, MT801 26A |
| G4 | VALIDATE `MT_CODE_NOT_ALLOWED` on 22C Common Reference / 22L Reporting Jurisdiction / 23B etc. | 14 | MT300, MT304–306, MT320, MT330, MT340/341, MT350, MT360–365 SR2026, MT102 SR2026 |
| G5 | VALIDATE "Sequence A1 occurrence count 0 is outside 1..100" | 6 | MT503–MT507 SR2026, MT670 SR2026 |
| G6 | PARSE `MT_IMPORT_NESTED_REPEAT_UNSUPPORTED` | 5 | MT020, MT022, MT066, MT082, MT083 |
| G7 | PARSE `MT_IMPORT_DUPLICATE_FIELD` | 5 | MT011, MT360, MT361, MT575 SR2026, MT671 SR2026 |
| G8 | ROUND_TRIP differs | 2 | MT306, MT362 SR2025 |
| G9 | VALIDATE `MT_FORMAT_INVALID` (141 Key) | 1 | MT026 |
| — | Source not identified (no structure at all) | 9 sources | MT110, MT752 (cover title has `(`/`,`), MT n90–n99 |

## 5. Blocker classification (root causes)

| Root cause | Groups | Generic? |
|---|---|---|
| `MRG_FLAT_OR_UNBRACKETED_SEQUENCE_GAP` — the MRG→pack compiler only accepts sequences that have a `16R` block code; flat tables (sequencePath `?`) and A/B/C sequences without `16R` are dropped | G1 (71) | yes — compiler |
| `PROWIDE_NO_BLOCK4_FIELDS` — Prowide model has no field groups | G1 (5) | no evidence exists |
| `QUALIFIER_EVIDENCE_MISSING` — Prowide records no qualifier legality; only an MRG does | G2 | release-bound: solved in SR2026 lane by the MRG; SR2025 stays honest |
| `FORMAT_GRAMMAR_GAP` — no alternation, `{…}n`, `L*(…)` groups, `<PARTYFLD-J>`, `<MIR>`, `<?>`, `<CC>`, `<DATE1>`, `<YYMMDDHHMM>` | G3 (+29 global field classes) | yes — grammar |
| `CODE_LIST_MISATTRIBUTION` — a CODES block belonging to another qualifier/field is attached to a non-generic field | G4 | yes — MRG reader |
| `MANDATORY_REPEATING_SUBSEQUENCE_NOT_SAMPLED` — mandatory repetitive subsequence with only optional rows yields zero occurrences | G5 | yes — sample gate / planner |
| `NESTED_UNBRACKETED_REPEAT` — `_A1` inside `_A` without a 16R opener | G6 | yes — parser |
| `DUPLICATE_TAG_ADDRESS` — `(sequence, tag, qualifier)` address cannot distinguish a second same-tag row | G7 (+57 latent) | yes — ordinal-aware address |
| `LEADING_TAG_REOPEN` — unbracketed reopen rule reassigns a field | G8 | yes — parser |
| `FORMAT_PATTERN_DEFECT` | G9 | yes — grammar |
| `COVER_IDENTITY_REGEX` — `(`, `,` and `n9x` not accepted on the cover | 9 sources | yes — identify |

## 6. Prowide structural coverage

274 source models (3 STP/REMIT variants not compiled), 1,042 sequences, 9,710 field groups,
620 global field classes, `SRU2025-10.3.18`. Records nesting (`parentPath`), repetition and
option letters; records **no** qualifier legality and **no** code lists. 96 classes generic.
29 validator patterns do not compile in the current grammar.

## 7. MRG structural coverage

146 SR2026 guides identified; Format Specifications parsed for all of them (sequences, rows,
qualifier tables, CODES blocks, 1,246 Network Validated Rule segments indexed). Two more
guides and seven common-group guides are readable once the cover regex accepts them.

## 8. Structure Pack architecture

`mt-structure-pack/1` YAML per (message, release): sequences (path, code, parent, order,
occurrence bounds, bracketed, leading tags, insert-after) and rows (row id, tag, option,
qualifier, presence, format, pattern, fidelity, codes, choice group, repetitive, evidence,
page). Compiled at sync time from the IR (§13); loaded at runtime by `mt_loader.py` into
`MessageSpecification`. Unchanged shape; the compiler gains the generic cases in §12.

## 9. Composer architecture

`SpecificationComposer` writes rows in specification order per planned sequence
occurrence. Changes: repeatable fields render once per supplied occurrence of the field
(today the loader discards `repetitive`); duplicate-tag rows are addressed by ordinal.

## 10. Parser architecture

`parser.py` is the composer's inverse and re-runs `plan_sequences` to prove expressibility.
Changes: ordinal-aware field addressing within a sequence occurrence; nested unbracketed
occurrence resolution opens the parent implicitly when a child leading tag arrives; the
leading-tag reopen rule consults row order monotonicity before reopening.

## 11. Sequence planner

`plan_sequences` stays the single occurrence model. An ancestor repeats only where a field
addresses that repeat directly — unchanged. The nested-unbracketed fix is in the parser's
parent resolution, not in the planner.

## 12. Generic structural gaps and fixes (implementation order, expected impact)

1. MRG compiler: flat root sequence, unbracketed sequences keyed by path, "No letter
   option" parsing, cover regex, common-group expansion against Prowide → G1 (≈ +60–70).
2. Format grammar: alternation, `{…}n`, `L*(…)`, party macro, time/date/MIR/CC macros → G3.
3. CODES attribution in the MRG reader → G4.
4. Mandatory repeating subsequence sampling → G5.
5. Ordinal-aware field address (compiler, loader, composer, parser, Excel) → G7 and the
   latent `DUPLICATE_TAG_IN_SEQUENCE` on 57 packs.
6. Nested unbracketed repeat parent resolution → G6.
7. Leading-tag reopen → G8; 141 pattern → G9.
8. Field repetition carried to runtime (correctness, no gate change).

After each step `make knowledge-sync` (compiler version bumped) re-runs all gates and the
coverage document records messages unlocked.

## 13. Universal MT compiler strategy (IR)

`MrgStructureArtifact` (MRG) and `MtMessageEvidence` (Prowide) are the two evidence
models; `compile_mt_pack` reconciles them into `PackSequence`/`PackRow`, which is the
intermediate representation the runtime pack is serialised from. It represents message,
sequence, nested sequence, repetition, field, option, qualifier, cardinality, order and
constraints (choice groups, value-less rows). Components stay a single canonical value with
a format-derived pattern; that is recorded as a limitation, not hidden.

## 14. Dynamic preview lane

Unchanged contract: `lane=KNOWLEDGE_PREVIEW` + `release` on every request; separate
registry instances; nothing promoted into the configured lane.

## 15. Generation safety

Gate order LOAD → SAMPLE → VALIDATE → COMPOSE → PARSE → ROUND_TRIP is unchanged and every
gate is terminal. A `MT_GENERATION_GATE` finding list (structured: gate, code, detail,
row) is written on each structure and rendered in the coverage report.

## 16. FIN envelope handling

Block 4 always; Block 1/2 only from profile data; MAC/CHK/PDE/… never. Unchanged.

## 17. Excel · 18. JSON · 19. AI samples · 20. Import · 21. Round trip

All four are already generic over the Structure Pack (Phase 6). Duplicate-tag ordinals
must reach the Excel template (new `RowOrdinal` semantics inside the existing `Tag` column
via the row id) and the JSON field id. AI sample flow (Structure Pack + RAG + reviewed
packs → LLM canonical values → validator → FIN) needs no message code. Import resolves
through the same runtime pack; round trip is the ROUND_TRIP gate.

## 22. MT semantic-rule source inventory

155 PDFs: 146 MRG + 2 + 7 after the identity fix = 155 sourced messages/groups. Each
carries release SR2026, page count, SHA-256 (already in the knowledge DB and written to the
committed `swiftKnowledgeBase/source-manifest.json`).

## 23. Semantic extraction architecture

Reuse `app.rule_engine.mt_mrg` unchanged in its reading logic. Generic changes only:
source catalogue generated from content identity (no per-message YAML by hand); relative
sub-paths allowed in `sourceLocation`; the page-marked text is taken from the knowledge
sync's source cache when present so a PDF is parsed once; per-message compact evidence
records (`mt-mrg-evidence-index/1`) instead of one 30 MB fixture; reports rendered from the
index for every message.

## 24. Rule DSL current coverage

`rule-dsl/2`: EXISTS/ABSENT/EQUALS/NOT_EQUALS/IN/NOT_IN/MATCHES/comparisons/date
comparisons over VALUE or COUNT; AllOf/AnyOf/Not/Implies/ExactlyOne/AtLeastOne/AtMostOne;
`forEachOccurrence`. 16 sentence templates (§ agent map) — 23 exact + 15 partial on
MT540/541.

## 25. Rule DSL missing semantics (to be confirmed by discovery over 1,246 rules)

Expected from the MT1xx/2xx/3xx/9xx guides: component-level comparison ("currency code in
32A must equal 33B", "amount must not be zero", "first two characters …"), cross-field
value equality, "either/or but not both", "at least one of", "must not be used" in flat
messages with no sequence, per-occurrence comparisons across different occurrences, and
BIC country-code conditions (C2 in MT103) which depend on Block 1/2 and are UNSUPPORTED by
design. Smallest generic additions considered: a deterministic `extract` projection on a
predicate (named regex group applied before comparison) and flat-message templates. Nothing
is added unless the discovery counts justify it; everything else is UNSUPPORTED with a
named reason.

## 26. Source review state

Every translated rule stays `REVIEW_REQUIRED`; zero rules written to `config/rules/`;
runtime activations 0. Reviewer packs are generated per MT.

## 27. Rule activation policy

Unchanged: candidate → human review → git → PR → CI → merge. A `CANDIDATE_TEST` lane is
not added; developer evaluation uses `make mt-mrg-evaluate`.

## 28. MT→MX source inventory

Deterministic FTS search of the whole knowledge base for coexistence / migration / ISO
20022 / pacs / camt / sese / pain / equivalent / mapping. Findings at baseline: MT101, MT103,
MT200, MT202, MT205 guides state the message "will be converted to its ISO 20022 equivalent
… via InterAct FINplus" (no target named); the MT205 Scope names "ISO 20022 Financial
Institution Credit Transfer" as the equivalent of MT200/201/202/203/205; eight pacs XSDs
name their own message definitions. No field-level mapping material exists in the KB.

## 29. Mapping evidence model

Per pack: `evidenceClass` ∈ SOURCE_BACKED · TARGET_RELATIONSHIP_ONLY · NAME_CORRESPONDENCE
· SYNTHETIC; per pack and per rule: citations (source id, checksum, page/section, excerpt
hash), review state. A rule without a citation is `UNCITED` and the pack cannot be
`SOURCE_BACKED`.

## 30. Mapping Pack

Identity gains `sourceRelease` semantics (already `source.release`) and explicit
`targetVersion` (= `target.release`); `mappingVersion` (= `version`). New operator kinds
`CODE_MAP` and `OMIT` as first-class kinds (ENUM transform and NOT_REPRESENTED keep
working); `kind` is enforced against rule shape.

## 31. Business semantic model

`BusinessSemantic` labels become the lightweight IR: every rule must carry one; the
conversion report groups by semantic. No ontology.

## 32. Mapping completeness

`coverage`: mandatory target elements mapped / total; source rows represented / total.
Reported per conversion and in `docs/generated/mt-mx-mapping-coverage.md`.

## 33. Missing data

`NEEDS_INPUT` with field, question, reason — unchanged; the UI sentence "N fields need
additional information" already exists.

## 34. RAG-assisted mapping

The existing `/api/v1/ai/ask` with message filters explains source/target fields with
citations. No LLM decides a mapping.

## 35. Conversion UI · 36. Conversion API

`ConvertMessage.tsx` shows evidence class, citations and coverage; `conversion-targets`
lists relationships including `TARGET_RELATIONSHIP_ONLY` ones that have no pack (shown as
not convertible, with the evidence).

## 37. Version/release mapping

Pack binds `source.release` (SR2025/SR2026) and `target.release` (full ISO version) and
structure checksums; a re-sync that changes either structure invalidates the pack.

## 38. Knowledge Git/LFS strategy

`.gitattributes`: `swiftKnowledgeBase/**/*.pdf`, `*.zip`, `*.xsd` under
`swiftKnowledgeBase/` → LFS (test XSD fixtures stay plain text). Commit 155 PDFs + 8 XSDs
(36 MB) and `swiftKnowledgeBase/source-manifest.json`. Never: `build/`, `.env`,
`knowledge.sqlite3`, vectors, caches.

## 39. Clone/reproducibility

`git clone` → `git lfs pull` → `make quickstart`: quickstart verifies LFS bytes (refuses
pointer files with a named message), starts Docker, runs `knowledge sync` (lexical only
without credentials). `make knowledge-verify` checks file presence, manifest hashes and
identity. CI Clean Clone job checks out with LFS and asserts real bytes.

## 40. Performance

`/create` unchanged (configured catalogue first, preview enrichment in background); sync
incremental; no embedding forced — lexical index first; embeddings only when policy allows.

## 41. Security

No secrets in the tree (secret scan); PDF parsing stays sync-time only; path traversal
unchanged; prompts fence source text; no rule or mapping activates automatically.

## 42. Tests

All-message generation matrix test (parametrised over every ready structure when the KB is
present; synthetic fixture otherwise); source consistency test; LFS pointer test; DSL
additions; parser ordinal/nesting; mapping evidence classes; MRG identity regex.

## 43. Browser UAT

Real Chrome: configured MT, dynamic MT cat 1/2/5/9, AI sample, guided/expert, validate, FIN,
import, Excel, JSON; MX pacs/sese; conversion; semantic reviewer view.

## 44. CI

Existing six jobs; Clean Clone gains `lfs: true` and the pointer assertion.

## 45. Acceptance

§66–§70 of the brief, item by item, in the final report.

## 46. Limitations

Recorded in §80 report: SR2025 qualifier evidence, Prowide models without Block 4, Block
1/2-dependent rules, no field-level mapping evidence in the KB, components as single values.

## 47. Self-review (corrections applied to the first draft)

- *Are blocked MTs structurally impossible?* No: 9 of 11 root causes are generic
  compiler/grammar/parser gaps. Only `PROWIDE_NO_BLOCK4_FIELDS` (5) and SR2025
  qualifier evidence (53, release-bound) depend on evidence that does not exist.
- *Can 50 failures share one root cause?* Yes: 71 share the MRG sequence gap, 53 share
  qualifier evidence, 57 latent share the duplicate-tag address.
- *Message-specific branches?* None planned; the common-group expansion is driven by the
  guide's own `n9x` title and the Prowide models that exist, not a list.
- *Global field definitions vs message use* stay separate: Prowide global classes give
  formats; MRG rows give message use; row ids carry sequence and qualifier.
- *Occurrence identity*: the ordinal fix extends the address, it does not collapse it.
- *FIN vs Block 4*: Block 1/2-dependent NVRs (BIC country) are UNSUPPORTED, never
  approximated.
- *RAG at runtime?* No. Rule evaluation and mapping stay deterministic.
- *Candidates accidentally active?* The registry still refuses anything not REVIEWED;
  tests lock it.
- *Mappings from names only?* Name correspondence is its own evidence class and is never
  SOURCE_BACKED; the only relationship with documentary evidence is MT20x ↔ FI credit
  transfer.
- *Clone size*: 36 MB via LFS is reasonable; history stays small because LFS objects are
  not in the pack files.
- *Corrected*: the first draft proposed re-using SR2026 qualifier tables for SR2025
  Prowide packs; rejected as lane conflation. The first draft proposed a `CANDIDATE_TEST`
  runtime lane; dropped — `make mt-mrg-evaluate` already serves developer evaluation.
