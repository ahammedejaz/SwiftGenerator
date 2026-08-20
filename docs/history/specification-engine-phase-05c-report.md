# Specification Engine Phase 5C Report

Date: 2026-08-20
Scope: MT540 / MT541 SR2026 occurrence-aware candidate-rule fidelity
Status: implementation complete, PR/remote CI recorded outside this commit to avoid
self-referential commit churn.

## 1. Executive summary

Phase 5C added a generic occurrence-aware evaluation model to the deterministic Rule
Engine and used it to retranslate the MT540/MT541 SR2026 Message Reference Guide
candidates. The eight Phase 5B occurrence-sensitive `UNSUPPORTED` candidates are no
longer unsupported. No SR2026 candidate was approved, installed or activated.

## 2. Base main SHA

The branch started from `422293627b702d8a3d5ef9248cc0d2c1da38ee05`.

## 3. Feature branch

`feat/phase-5c-occurrence-aware-rule-fidelity`.

## 4. Baseline tests

Before changing code, the branch reverified the Phase 5B baseline with `make check`,
`make e2e`, `make build`, `make audit`, `make secret-scan`, `make mt-mrg-evaluate`,
`make verify-real-mt540-mt541-source`, `docker compose config --quiet`,
`docker compose build` and `git diff --check`.

## 5. Source re-verification

`make verify-real-mt540-mt541-source` reproduced the committed evidence from the local
operator documents:

| Source | Pages | SHA-256 |
|---|---:|---|
| `SR_2026_MT540.pdf` | 109 | `ef69b239e6483dbbebbc0fe531c3d91f386039012a14715ce0e16d503a86fe8c` |
| `SR_2026_MT541.pdf` | 110 | `b15cbfcb4e15fd056aede2d92bd522d75c28bd92b560066cc50b8c6031233a39` |

The PDFs remain ignored and outside Git.

## 6. Phase 5B starting fidelity

| Message | Total | Exact | Partial | Unsupported |
|---|---:|---:|---:|---:|
| `MT540` | 18 | 7 | 7 | 4 |
| `MT541` | 20 | 8 | 8 | 4 |

## 7. Root cause of occurrence limitation

The v1 evaluator used a flat value bag: field key to values present in the whole message.
That could represent message-wide presence and counts, but not "this field in the same
occurrence of E1" without becoming stronger than the source.

## 8. Canonical occurrence model

`backend/app/rule_engine/occurrences.py` adds `OccurrenceIdentity`, made from one or more
`OccurrenceLevel` values. The identity includes sequence path and one-based local
occurrence number; a nested occurrence also carries parent lineage.

## 9. Evaluation context

`EvaluationContext` wraps the legacy global value bag plus optional occurrence-indexed
values. Legacy callers can still pass the original mapping. Scoped callers pass
`OccurrenceValue` entries with the field key, value and occurrence identity.

## 10. DSL changes

`rule-dsl/2` adds:

```yaml
forEachOccurrence:
  sequencePath: E1
  assert: { ... }
```

The nested assertion runs independently inside each occurrence of the named repeating
sequence or subsequence.

## 11. Compiler changes

The compiler now accepts both v1 and v2 engine/DSL versions. It rejects scoped expressions
in `rule-dsl/1`, unknown scopes, non-repeatable scopes, and scoped assertions that
reference fields outside the selected scope.

## 12. Evaluator changes

`evaluate()` now accepts either a legacy value bag or an `EvaluationContext`.
`evaluate_rules()` carries the first failing scoped occurrence into the generated
`ValidationIssue` when useful.

## 13. Backward compatibility

Existing reviewed Rule Packs compile under their declared v1 versions. Flat runtime calls
keep global message semantics. A scoped assertion with no occurrence projection is
vacuously true, which prevents accidental behaviour changes for legacy callers.

## 14. Nested occurrence handling

Nested repeat identity is lineage-based. `P[1]/C[1]` and `P[2]/C[1]` are distinct even
though both child occurrences have local index `1`. Synthetic DSL tests cover this case.

## 15. Finding occurrence metadata

`ValidationIssue` now has optional `occurrence` metadata with `sequencePath`, `occurrence`,
`path` and `lineage`. Ordinary finding prose remains business-field oriented.

## 16. Rule Pack schema/version change

The engine constants are now `rule-engine/2` and `rule-dsl/2`, with v1 still supported for
existing packs. The MRG reader and evidence fixture were bumped to `mt-mrg-reader/2` and
`mt-mrg-evidence/2`.

## 17. Cache invalidation

The MRG fixture schema and reader version changed, so stale Phase 5B evidence is refused
rather than half-read. Generated reports include occurrence scopes.

## 18. MT540 C1-C18 final disposition

| Rule | Fidelity | Scope | Compiled | Residual |
|---|---|---|---|---|
| `C1` | `EXACT` | `NONE` | `YES` | none |
| `C2` | `EXACT` | `NONE` | `YES` | none |
| `C3` | `EXACT` | `E3` | `YES` | none |
| `C4` | `EXACT` | `NONE` | `YES` | none |
| `C5` | `PARTIAL` | `NONE` | `YES` | Different-occurrence requirement remains weaker. |
| `C6` | `PARTIAL` | `NONE` | `YES` | Party-chain "another occurrence" requirement remains weaker. |
| `C7` | `EXACT` | `NONE` | `YES` | none |
| `C8` | `EXACT` | `E1` | `YES` | none |
| `C9` | `PARTIAL` | `NONE` | `YES` | Data-source-scheme exception remains unmodelled. |
| `C10` | `EXACT` | `NONE` | `YES` | none |
| `C11` | `PARTIAL` | `NONE` | `YES` | Data-source-scheme exception remains unmodelled. |
| `C12` | `PARTIAL` | `NONE` | `YES` | Field component scope remains unmodelled. |
| `C13` | `PARTIAL` | `NONE` | `YES` | Paired quantity-type-code semantics remain unmodelled. |
| `C14` | `EXACT` | `F` | `YES` | none |
| `C15` | `EXACT` | `NONE` | `YES` | none |
| `C16` | `PARTIAL` | `E1, E2, F` | `YES` | Format-option requirement remains unmodelled. |
| `C17` | `EXACT` | `F` | `YES` | none |
| `C18` | `EXACT` | `NONE` | `YES` | none |

## 19. MT541 C1-C20 final disposition

| Rule | Fidelity | Scope | Compiled | Residual |
|---|---|---|---|---|
| `C1` | `EXACT` | `NONE` | `YES` | none |
| `C2` | `EXACT` | `NONE` | `YES` | none |
| `C3` | `EXACT` | `NONE` | `YES` | none |
| `C4` | `EXACT` | `E3` | `YES` | none |
| `C5` | `EXACT` | `NONE` | `YES` | none |
| `C6` | `PARTIAL` | `NONE` | `YES` | Different-occurrence requirement remains weaker. |
| `C7` | `PARTIAL` | `NONE` | `YES` | Party-chain "another occurrence" requirement remains weaker. |
| `C8` | `EXACT` | `NONE` | `YES` | none |
| `C9` | `EXACT` | `E1` | `YES` | none |
| `C10` | `PARTIAL` | `NONE` | `YES` | Data-source-scheme exception remains unmodelled. |
| `C11` | `EXACT` | `NONE` | `YES` | none |
| `C12` | `PARTIAL` | `NONE` | `YES` | Data-source-scheme exception remains unmodelled. |
| `C13` | `PARTIAL` | `NONE` | `YES` | Field component scope remains unmodelled. |
| `C14` | `PARTIAL` | `NONE` | `YES` | Paired quantity-type-code semantics remain unmodelled. |
| `C15` | `PARTIAL` | `E3` | `YES` | Data-source-scheme exception remains unmodelled. |
| `C16` | `EXACT` | `F` | `YES` | none |
| `C17` | `EXACT` | `NONE` | `YES` | none |
| `C18` | `PARTIAL` | `E1, E2, F` | `YES` | Format-option requirement remains unmodelled. |
| `C19` | `EXACT` | `F` | `YES` | none |
| `C20` | `EXACT` | `NONE` | `YES` | none |

## 20. EXACT before/after

| Message | Before | After |
|---|---:|---:|
| `MT540` | 7 | 11 |
| `MT541` | 8 | 12 |

## 21. PARTIAL before/after

| Message | Before | After |
|---|---:|---:|
| `MT540` | 7 | 7 |
| `MT541` | 8 | 8 |

## 22. UNSUPPORTED before/after

| Message | Before | After |
|---|---:|---:|
| `MT540` | 4 | 0 |
| `MT541` | 4 | 0 |

## 23. Remaining unsupported rules

None.

## 24. Remaining partial rules

MT540: `C5`, `C6`, `C9`, `C11`, `C12`, `C13`, `C16`.
MT541: `C6`, `C7`, `C10`, `C12`, `C13`, `C14`, `C15`, `C18`.

## 25. Why each remains incomplete

The remaining gaps are narrower than Phase 5B's occurrence-scope gap: component-level
data-source-scheme exceptions, format-option tests, paired-code semantics, and rules that
require a different or next occurrence rather than the same occurrence.

## 26. PSET/97a same-occurrence proof

`make mt-mrg-evaluate` includes positive and negative cases for MT541 `C9` and MT540 `C8`.
Different E1 occurrences hold; same E1 occurrence violates. Result: pass.

## 27. Multi-occurrence proof

The same evaluator keeps repeated E1 and E3 cases distinct and proves count rules still
fail or hold as expected. Result: pass.

## 28. Nested synthetic proof

`backend/tests/rule_engine/test_dsl.py` covers nested lineage where child occurrence index
`1` appears under two different parents. Result: pass.

## 29. Settlement amount regression

MT541 `C2` anchor cases remain green in `make mt-mrg-evaluate`. Result: pass.

## 30. DBNM/DEAG/PSET regression

MT540 `C5` and MT541 `C6` DBNM/party anchor cases remain green. Result: pass.

## 31. SETR reconciliation

Existing MT settlement transaction type regression tests passed under `make check`.

## 32. 35B reconciliation

Existing financial instrument identifier and golden MT tests passed under `make check`.

## 33. Party-chain reconciliation

Party-chain candidates remain partial where the source needs "another occurrence"; the
weaker candidates still compile and the regression anchors remain green.

## 34. SR2025/SR2026 isolation

SR2026 remains `FUTURE_TEST`. Candidate packs compile against the guide-stated structures,
are not written to `backend/config/rules/`, and are not loadable by the runtime registry.

## 35. Candidate review isolation

Every real-source candidate remains `REVIEW_REQUIRED`. Human-reviewed real rules remain 0.

## 36. Runtime activations

Runtime activations from SR2026 candidates remain 0.

## 37. Runtime LLM calls

Runtime LLM calls for validation remain 0. The MRG pipeline used 0 live model calls.

## 38. Excel/API compatibility

Live local API smoke passed for MT540, MT541, MT543, MT548, `sese.023`, and both MT/MX
Excel template uploads.

## 39. Import compatibility

Live local import/regenerate smoke passed for MT540, MT541, MT543, MT548 and `sese.023`.

## 40. MT composer regression

`make check`, golden tests, E2E MT authoring tests and manual MT smoke passed.

## 41. MX regression

`make check`, E2E MX paths and manual `sese.023` smoke passed.

## 42. Performance

After guide parsing, 58,000 local candidate evaluations completed in 5.785025 seconds:
average 0.099742 ms per evaluation, about 10,025 evaluations per second.

## 43. Security

`make secret-scan` found no secret-shaped strings in tracked files. `make audit` found no
known Python vulnerabilities and `npm audit --omit=dev` found 0 vulnerabilities. The DSL
remains closed Pydantic data with no eval/exec path.

## 44. Backend tests

`make check` passed with ruff, mypy over 195 source files, TypeScript, eslint, 1,446
backend tests passed, 23 skipped and 1 live-AI test deselected.

## 45. Playwright

`make e2e` passed: 80 Chromium tests.

## 46. Browser/manual UAT smoke

Local backend/frontend smoke passed. Desktop pages `/`, `/message-builder`, `/validate`,
`/excel`, `/intelligence` loaded without page errors or server errors; mobile
`/message-builder` had no horizontal scroll.

## 47. Docker

`docker compose config --quiet` and `docker compose build` passed for backend and frontend.

## 48. CI

Remote PR CI is external to the commit and must be verified on the final pushed head. The
final response records the PR URL, head SHA and CI run status after the PR is opened.

## 49. Files changed

The change is scoped to `backend/app/rule_engine/`, MRG candidate tooling, rule-engine
tests, generated MRG evidence/reports, studio validation issue typing, frontend API types
and documentation. No runtime MT structures or reviewed rule packs were added.

## 50. Known limitations

Remaining partial rules still need component scope, format-option semantics,
paired-code semantics and different-occurrence relationships. SR2026 is future-test and
unreviewed.

## 51. Human-review debt

All 38 real-source candidates still require a human/SME review against the licensed guide
before any runtime Rule Pack can be created.

## 52. Whether application is ready for internal UAT

`INTERNAL_UAT_READY: YES` for currently supported messages and profiles. This means normal
generation, validation, FIN/XML output, import, Excel, API and browser flows are ready for
internal testing. It does not mean SWIFT certification, production connectivity or SR2026
rule approval.

## 53. Recommended UAT scenarios

Use `docs/testing/phase-05c-internal-uat-checklist.md`: MT540 typical sample, MT541
typical sample, Guided, Expert, invalid/corrected ISIN, PSET, Validate, Excel, API,
Message Intelligence and one MX sample.

## 54. Recommended next phase

Do not start Phase 5 from this branch. A later phase should decide whether component scope,
format-option tests, paired-code semantics or different-occurrence relationships deserve
new generic DSL primitives.

## 55. Final commit

Recorded in the final Codex response after commit creation. The commit cannot embed its own
SHA without changing that SHA.

## 56. PR

Recorded in the final Codex response after the PR is opened. The PR must remain open.

## 57. CI run

Recorded in the final Codex response after GitHub Actions completes on the final PR head.
