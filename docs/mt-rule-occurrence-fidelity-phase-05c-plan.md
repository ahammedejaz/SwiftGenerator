# MT rule occurrence fidelity Phase 5C plan

## 1. Executive objective

Add deterministic, occurrence-aware evaluation to the generic Rule Engine so a rule can be
evaluated inside one repeat occurrence of a sequence or subsequence. Recompile the MT540
and MT541 SR2026 candidate rules against that support, improve only the rules that become
soundly representable, and keep every real rule candidate inactive and `REVIEW_REQUIRED`.

## 2. Current Phase 5B baseline

Base main: `422293627b702d8a3d5ef9248cc0d2c1da38ee05`.

Pre-change verification:

- `make check`: passed; 1431 backend tests passed, 23 skipped, 1 deselected; ruff, mypy
  over 194 files, eslint, TypeScript, coverage, XSD compatibility, demo pack, Prowide,
  MT semantic readiness and MRG report checks passed.
- `make e2e`: passed; 80 Playwright tests.
- `make build`: passed.
- `make audit`: passed; no known Python vulnerabilities and 0 npm production
  vulnerabilities.
- `make secret-scan`: passed.
- `make mt-mrg-evaluate`: passed; 24/24 Phase 5B candidate evaluator cases.
- `make verify-real-mt540-mt541-source`: passed; committed evidence reproduced from the
  operator PDFs.
- `docker compose config --quiet`: passed.
- `docker compose build`: passed for backend and frontend.
- `git diff --check`: passed.

## 3. Real-source inventory

The source drop is `swiftKnowledgeBase/`, which is ignored and not committed.

Verified documents:

- MT540: `SR_2026_MT540.pdf`, 109 pages, `sha256:ef69b239e6483dbbebbc0fe531c3d91f386039012a14715ce0e16d503a86fe8c`.
- MT541: `SR_2026_MT541.pdf`, 110 pages, `sha256:b15cbfcb4e15fd056aede2d92bd522d75c28bd92b560066cc50b8c6031233a39`.

Both match the Phase 5B recorded hashes and reproduce the committed derived evidence.
`RAW_SWIFT_SOURCE_COMMITTED = NO`.

## 4. Current 38-rule fidelity matrix

Before Phase 5C:

| Message | Total | Exact | Partial | Unsupported |
| --- | ---: | ---: | ---: | ---: |
| MT540 | 18 | 7 | 7 | 4 |
| MT541 | 20 | 8 | 8 | 4 |

Unsupported occurrence-scope rules:

- MT540 C8, C14, C16, C17.
- MT541 C9, C16, C18, C19.

Partial rules with residual occurrence content:

- MT540 C3 and MT541 C4: same-subsequence amount dependency.
- MT541 C15: same-subsequence amount dependency plus data-source-scheme residual.
- MT540 C5 and MT541 C6: different E1 occurrences, not same occurrence.
- MT540 C6 and MT541 C7: next party in another occurrence.

Other partial residuals are component scope, data-source-scheme scope, paired-code
requirements, or source exceptions that remain outside this phase unless a small generic
primitive already covers them.

## 5. Current Rule DSL

The DSL is closed Pydantic data: predicates, `ALL_OF`, `ANY_OF`, `NOT`, `IMPLIES`,
`EXACTLY_ONE`, `AT_LEAST_ONE`, and `AT_MOST_ONE`. Predicates operate globally over the
field values in a value bag. `COUNT` counts global present values for one field.

## 6. Current canonical field/value model

Runtime values are still public `FieldInput` and `ElementInput` records with an optional
one-based `occurrence`. The current rule-engine value bag groups only by field key, so the
occurrence dimension is lost before evaluation.

## 7. Current sequence occurrence model

MT occurrence planning lives in `plan_sequences()`. A child repeat does not imply the same
occurrence number on every ancestor; parent lineage matters. Phase 5C must reuse that
lesson rather than treating local occurrence number as a unique identity.

## 8. Current parser occurrence model

MT import reconstructs the composer-plan tree and refuses nested repeats that cannot be
represented by the public flat occurrence address. That behaviour stays unchanged.

## 9. Current composer occurrence model

Composition threads the public occurrence number through planned sequence instances. Phase
5C must not alter FIN output, sequence opening/closing, or golden files.

## 10. Current Excel occurrence model

Excel uses the existing `SequenceOccurrence` column and maps to the same canonical inputs.
No spreadsheet contract change is planned.

## 11. Current JSON API occurrence model

JSON API callers submit `occurrence` on field/element inputs. No request contract change is
planned.

## 12. Current Rule Engine limitation

The engine receives `field key -> values`. A scoped source rule such as "where field X is
present in this E1 occurrence, field Y is absent in that same E1 occurrence" cannot be
distinguished from a global message-wide relationship.

## 13. Same-occurrence semantics

Add a scoped expression node that evaluates an assertion independently for each occurrence
of a named scope. Inside the scope, ordinary predicates read only values belonging to that
same structural occurrence.

## 14. Any-occurrence semantics

Global `EXISTS` already expresses "somewhere in the message". A distinct any-occurrence
node is not needed unless a source rule requires a condition over occurrence-local
contents. Phase 5C will avoid adding it prematurely.

## 15. Every-occurrence semantics

The planned `forEachOccurrence` node is every-occurrence semantics: every occurrence that
exists for the scope must satisfy the inner assertion. With zero occurrences, it is true,
matching ordinary universal semantics.

## 16. Cross-occurrence semantics if required

Rules requiring a different or next occurrence remain partial unless a small generic
distinct-occurrence primitive is justified by the rule set and can be tested safely. This
phase prioritises same-occurrence correctness and per-occurrence count limits.

## 17. Sequence scoping

The scope is a sequence path string resolved through the same structure index used by the
compiler. A scoped expression is valid only when the target scope exists and is repeatable
for the compiled structure.

## 18. Nested repeating subsequences

Occurrence identity is structural lineage plus local index. Synthetic tests must prove
`P[1]/C[1]`, `P[1]/C[2]`, and `P[2]/C[1]` are distinct.

## 19. Canonical occurrence identity

Internal identity is a tuple of levels: `(sequencePath, oneBasedOccurrence)`. A local
occurrence index is never compared without its path and parent lineage.

## 20. MT structural-reference identity

MT field references remain existing row ids or sequence/tag/qualifier references. The
occurrence scope wraps existing references; it does not invent a second MT reference
syntax.

## 21. Generic format-neutral possibilities

The evaluator support is format-neutral. MT MRG candidate evaluation will be the first
producer of occurrence-indexed values. Existing MX and MT runtime validation can keep
passing plain value bags.

## 22. MT-specific adapter boundary

Mapping MRG synthetic values into occurrence identities is MT-specific and belongs in
`app.rule_engine.mt_mrg.evaluation`. The evaluator only sees resolved field keys and
occurrence identities.

## 23. AST changes

Add `forEachOccurrence` to the DSL. The node holds `sequencePath` and an inner `assert`
expression. It is declarative data and contains no executable predicate language.

## 24. DSL changes

Bump the current DSL version for new scoped packs while preserving support for old packs.
Old unscoped packs keep their current semantics.

## 25. Compiler changes

The compiler must bind references as before, validate the scope exists, validate the scope
is repeatable, reject scoped references that escape the scope, and reject a new scoped AST
declared under the old DSL version.

## 26. Evaluator changes

Evaluation accepts either a legacy value bag or an `EvaluationContext`. A legacy bag
evaluates byte-for-byte as before. Scoped nodes require an occurrence-indexed context and
fall back to zero occurrences when none is supplied.

## 27. Validation finding paths

Normal public issue shape remains. Add optional occurrence metadata only when a scoped
assertion fails and the evaluator can identify the failing occurrence.

## 28. Candidate Rule Pack compatibility

SR2026 candidate packs produced after Phase 5C use the new DSL version and remain
`REVIEW_REQUIRED`. They are still not written to `backend/config/rules/`.

## 29. Existing Rule Pack backward compatibility

Existing reviewed MX overlay packs remain loadable and evaluate unchanged.

## 30. Cache compatibility

The MRG reader version and fixture schema will move because candidate expression semantics
and fixture shape change. Phase 5B fixtures must not be silently reused.

## 31. Rule Pack diff compatibility

The existing pack diff serialises expression JSON; scoped assertions are therefore visible
as assertion changes. Add a test to pin that visibility.

## 32. Overlay compatibility

Overlay narrowing logic walks expression references. The walker must include scoped child
references so overlay checks keep seeing the same fields.

## 33. MT540 unsupported-rule recovery

Aim to recover same-occurrence exclusions C8, C14, C17 as exact candidates, and C16 as at
least a weaker scoped count candidate if the component/format-option part remains
unexpressed.

## 34. MT541 unsupported-rule recovery

Aim to recover C9, C16, C19 as exact candidates, and C18 as at least a weaker scoped count
candidate if the component/format-option part remains unexpressed.

## 35. PARTIAL-to-EXACT strategy

Only remove an occurrence residual when the scoped AST represents exactly that missing
clause. Keep component and DSS residuals. Do not turn different-occurrence rules exact via
same-occurrence support.

## 36. Structural gaps E1/A1/E3 if relevant

SR2026 candidate compilation uses the MRG future-test structure index. It does not alter
SR2025 runtime structure.

## 37. SR2025 isolation

No SR2026 candidate pack is installed. Runtime SR2025 rule activation count remains zero.

## 38. SR2026 future-test isolation

SR2026 remains `FUTURE_TEST`. The calendar does not change the release lane.

## 39. Source-provenance preservation

Reports and fixtures keep identifiers, digests, page numbers, rule numbers and generated
expressions only. No raw source paragraphs are committed.

## 40. Reviewer artifact updates

Regenerate MT540 and MT541 reviewer reports and add a new before/after fidelity report.
Every real rule remains `REVIEW_REQUIRED`.

## 41. Performance

Unscoped evaluation must stay a direct bag lookup. Scoped evaluation indexes occurrence
values once and scans occurrences for the named scope.

## 42. Security

No `eval`, `exec`, dynamic imports, XPath, JS, Jinja, shell, arbitrary traversal, or model
call. Scope strings resolve through known structure only.

## 43. API compatibility

Existing request bodies and validation issue fields remain valid. Occurrence metadata is
additive and nullable.

## 44. Excel compatibility

Excel continues to use `SequenceOccurrence`. Cross-tests will verify equivalent canonical
values from Excel/API produce equivalent message output.

## 45. UI impact

No Create Message UI feature is added. Candidate reviewer evidence may mention scoped
rules; ordinary users do not see unreviewed C-rules.

## 46. UAT strategy

After automated verification, smoke the running app for MT540, MT541, MT543, MT548, and one
existing MX flow in Guided, Expert, sample, validate, generate, import, Excel/API, and
message-intelligence paths.

## 47. Regression strategy

Run focused rule-engine tests first, then `make check`, `make e2e`, `make build`, audit,
secret scan, Docker, MRG evaluate/verify, and `git diff --check`.

## 48. Migration strategy

Add scoped evaluator support, update MRG templates, regenerate the derived fixture and
reports from the verified local PDFs, then add docs and tests.

## 49. Risks

- Accidentally treating occurrence 1 under two different parents as the same identity.
- Rejecting a source-valid message by upgrading a partial rule too aggressively.
- Breaking old reviewed overlays by forcing every pack to the new DSL version.
- Letting SR2026 candidates into normal SR2025 validation.

## 50. Acceptance criteria

Same-occurrence pass/fail cases are proved, nested lineage is proved, old unscoped rules
are unchanged, all 38 rules remain accounted for, no stronger-than-source candidate exists,
runtime activations remain zero, runtime LLM calls remain zero, raw PDFs remain ignored,
and CI is green for the final PR head.

## Self-review

- Are we changing the canonical value model unnecessarily? No; occurrence state is an
  internal evaluation context layered over existing inputs.
- Can occurrence semantics be layered over existing canonical inputs? Yes; existing public
  `occurrence` values and MRG synthetic values can project into the internal context.
- Can existing Rule Packs continue evaluating byte-for-byte identically? Yes; plain value
  bags keep the old path and old DSL/engine versions stay supported.
- Are we inventing occurrence semantics beyond what source requires? No; implement
  for-each same-scope evaluation and per-occurrence count only.
- Can same occurrence accidentally mean same index under different parent sequences? Tests
  will assert lineage-sensitive identity.
- Are nested repeats uniquely addressable? Internally yes; public import limitations remain
  unchanged.
- Can an occurrence index from a child be incorrectly propagated to its parent? The context
  stores explicit lineage rather than lifting indexes.
- Is this reintroducing the `plan_sequences()` bug? No composer planning change is made.
- Are MT parser/composer/import/Excel occurrence semantics still identical? They remain on
  the same public contracts; only rule evaluation gains an internal indexed view.
- Can a rule compare occurrence 1 of one parent with occurrence 1 of another? The identity
  includes lineage, so no.
- Can an occurrence-scoped rule turn global existence into a false restriction? Scoped
  predicates see only values in the selected occurrence.
- Does COUNT still behave correctly? Global count is unchanged; scoped count counts only
  values in the current occurrence.
- Does EXISTS still preserve old behaviour? Yes outside a scoped context.
- Can current reviewed MX rules regress? Existing MX overlays stay unscoped and remain on
  old semantics.
- Can current MT rules regress? No real MT rule pack is installed.
- Are we adding message-specific evaluator code for MT540/541? No; message-specific
  content remains in templates/candidates.
- Are we changing SR2025 based on SR2026? No.
- Are real candidates becoming active? No.
- Are PARTIAL rules promoted to EXACT without proof? No; residuals remain unless the new
  scoped AST covers the missing clause.
- Are source rules still REVIEW_REQUIRED? Yes.
- Can normal runtime still operate with no LLM? Yes.
- Is the design too complicated? It is small: one context, one scoped AST node, one
  MT-specific projector.
