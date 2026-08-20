# MT semantic rule ingestion plan

Phase 5A builds the foundation for authorised MT semantic source material to produce
reviewable candidate Rule Packs. It does not derive real SWIFT rules, install candidate MT
messages or merge any resulting PR.

The governing sentence stays unchanged:

> A message is a specification plus values.

Phase 5A adds the MT bridge between release-pinned structural evidence and the existing
Phase 2 rule engine:

> Prowide may identify where an MT field can be structurally addressed. Semantic authority
> still comes only from an authorised source, deterministic compilation and review.

## 1. Executive objective

Build a generic, source-ready MT semantic ingestion foundation:

- local source readiness and MT metadata;
- deterministic source ingestion and segmentation reuse;
- exact SRU/release binding;
- canonical MT structural reference resolution;
- candidate extraction through the existing A/B, diff, refuter and compiler pipeline;
- reviewer artifacts and readiness reports;
- synthetic MT proof through reviewed, test-only Rule Packs;
- zero candidate leakage into normal runtime validation.

## 2. Current main baseline

Base main SHA: `e43372e015210106960b993813a8e09cca86b3b5`.

Measured before Phase 5A edits on `feat/mt-semantic-rule-ingestion`:

| Check | Result |
| --- | --- |
| `make check` | PASS: ruff, eslint, mypy on 183 files, TypeScript, 1320 passed, 23 skipped, 1 deselected, 2 warnings |
| `make e2e` | PASS: 80 Playwright tests in 1.7 min |
| `make build` | PASS |
| `make audit` | PASS: pip-audit and npm audit clean |
| `make secret-scan` | PASS |
| `make coverage` | PASS |
| `make demo-pack-check` | PASS |
| `make xsd-compatibility` | PASS |
| `make mt-prowide-check` | PASS |
| `docker compose config --quiet` | PASS |
| `docker compose build` | PASS |
| `git diff --check` | PASS |

## 3. Phase 2 Rule Engine capabilities

Phase 2 already provides the machinery Phase 5A must reuse: Source Bundles, safe local
ingestion, deterministic segmentation, isolated extractor A/B, canonicalisation, candidate
diff, adversarial refuter, deterministic compiler, review package, source-controlled
activation, cache and offline evaluation.

## 4. Phase 4/4B MT structural capabilities

Phase 4B provides Prowide-derived structural evidence for 274 MT source models on
`SR2025`. It added metadata-only canonical MT structural references such as
`MT:SR2025:MT541:SETDET:22F:SETR`. It installed zero candidate messages.

## 5. Current 274-model structural discovery

The all-category fixture records 274 source models, 1,042 sequences, 990 fieldsets, 9,710
field groups and 620 global field classes. Sixteen configured MTs overlap with the
runtime registry; 258 source models remain candidate-only.

## 6. Current runtime MT coverage

Runtime MT messages remain: MT530, MT537, MT540, MT541, MT542, MT543, MT544, MT545, MT546,
MT547, MT548, MT564, MT565, MT566, MT567 and MT568.

## 7. Remaining semantic gaps

Requiredness, qualifier legality, code-list legality, network rules, market practice,
client rules and standards completeness remain unknown without authorised MT semantic
evidence.

## 8. Source authority model

Authority order:

1. Authorised source document establishes semantic evidence.
2. Deterministic segmentation and reference resolution bind that evidence to structure.
3. LLM extraction proposes candidates only.
4. Compiler/refuter/diff package candidates for review.
5. Reviewed, source-controlled Rule Packs activate at runtime.

Prowide remains structural evidence only.

## 9. Licensing boundary

Default source policy remains conservative:

- `sourceMayBeCommitted = false`;
- `excerptsMayBeCommitted = false`;
- external model processing blocked unless explicitly allowed.

No licensed source text is scraped, copied, paraphrased from memory or committed.

## 10. Source discovery/readiness

The configured source locations to audit are `backend/config/rule_sources/`,
`RULE_SOURCE_DIRECTORY`, `backend/config/mx/xsd/official/` and the MX source metadata
cache. No unrelated personal directories are scanned.

## 11. Source Bundle model

Reuse `SourceBundle` and extend it only with MT-needed metadata:

- `standardsRelease`;
- applicable MT categories;
- applicable message identifiers;
- external-model privacy approval;
- provider approval for the source classification.

## 12. MT source adapters

Reuse the generic adapters: TXT, Markdown, HTML and text-layer PDF where a local extractor
is installed. Structured exports remain future-ready unless a real supported export
appears.

## 13. PDF handling

PDF remains text-layer only. No OCR. Scanned/image-only PDFs fail clearly. Large or
garbled extractions fail before any rule extraction.

## 14. Text/Markdown handling

Reuse deterministic Phase 2 normalisation and segmentation. Synthetic MT fixtures are
Markdown and clearly labelled `SYNTHETIC_FIXTURE`.

## 15. HTML handling

Reuse the existing clean-HTML adapter. No script/style content, no network, no DTD.

## 16. Structured export handling

No JSON/XML/CSV/XLSX semantic adapter is added unless a legitimate configured source
requires it. Readiness docs name them as acceptable future formats, not implemented ones.

## 17. Stable segmentation

Source bytes produce stable checksum and stable segment hashes. LLMs do not choose
segment boundaries.

## 18. Exact release/SRU binding

An MT semantic source binds to `standardsRelease` when known. `SR2025` and `SR2026` are
not interchangeable. Unknown remains `UNKNOWN`.

## 19. Canonical MT reference model

Use Phase 4B canonical references as the structural bridge:
`sourceRelease`, `messageType`, `sourceModel`, `sequencePath`, `tag`, `option`,
`qualifier`, `component` and optional sequence occurrence.

## 20. Sequence path resolution

Resolve by internal path or delimiter code. Missing or ambiguous targets fail with
structured diagnostics.

## 21. Tag resolution

The tag must exist in the message-level field group for the selected sequence. Global
field class existence is not enough.

## 22. Option resolution

An option can be derived from a tag such as `95P` or supplied separately with numeric tag
`95`. Mismatches fail.

## 23. Qualifier resolution

Prowide does not establish message-context qualifier legality. A qualifier can be bound to
an installed runtime row when one exists, or left unresolved. It is never fabricated from a
global constant.

## 24. Component resolution

Component references are checked only against reflected global component evidence. Missing
or out-of-range components fail.

## 25. Rule target resolver

Candidate MT rules ultimately compile through the existing `FieldRef` and `StructureIndex`
against installed MT runtime rows. Canonical MT references are metadata/evidence; runtime
evaluation still uses reviewed Rule Pack fields.

## 26. Existing Rule DSL reuse

Reuse the closed Phase 2 DSL: presence, equality, membership, date, numeric and group
operators. Do not add a separate MT evaluator.

## 27. MT-specific Rule DSL gaps

No new operator is planned for Phase 5A. Synthetic fixtures exercise common shapes already
representable by the DSL.

## 28. Candidate extraction grounding

For MT extraction, pass only the target MT message fields and relevant release/structure
metadata. Do not send the 274-message universe.

## 29. Extraction A/B

Reuse isolated extractor A and B. Both see the same evidence and structure context; neither
sees the other's answer.

## 30. Candidate diff

Reuse deterministic candidate canonicalisation and diff. Disagreement remains review
input, not an automatic selection.

## 31. Refuter

Reuse the adversarial refuter and strengthen MT prompts/evaluation around wrong sequence,
wrong tag, wrong option, wrong qualifier, wrong SRU and model-memory leakage.

## 32. Reference validation

Before review, deterministic code validates source release, message, sequence, tag, option,
qualifier binding where possible, component and operator/type compatibility.

## 33. Rule compilation

Candidate rules compile through the same `compile_pack` path that guards installed packs.
A candidate is never checked more weakly than a reviewed pack.

## 34. Structural compatibility

Reviewed MT packs record installed structure checksum/version. SRU mismatch is a blocker,
not a warning.

## 35. Source release compatibility

If a source declares `SR2025` and the structure context is not `SR2025`, the candidate is
not applied silently. Unknown release remains conservative.

## 36. Review workflow

Keep CLI/file review. Do not add a review API or PR automation.

## 37. Evidence artifacts

Review packages show rule ID, MT type, SRU, sequence, tag, option, qualifier, source
identity, source location, segment hashes, A/B diff, refuter findings and deterministic
resolver results. Chain-of-thought is never stored.

## 38. Candidate state

Candidates are `MACHINE_CHECKED` or `REVIEW_REQUIRED` and stay outside runtime load paths.

## 39. Activation state

Only reviewed, source-controlled Rule Packs under `backend/config/rules/` can activate.
Synthetic reviewed packs used by tests live in isolated temporary rule directories.

## 40. Source-control workflow

Phase 5A ends with an open PR and green CI. The PR is not merged.

## 41. Runtime isolation

Normal generation, validation, import, Excel and Message Intelligence must continue with
zero LLM calls and no Java/Prowide/Maven/Gradle runtime dependency.

## 42. LLM security/privacy

Real operator/client sources are not sent to a model unless the source metadata explicitly
allows external model processing and the provider is approved for the source class.

## 43. Prompt injection

Source text remains untrusted data. Synthetic MT fixtures include injected instructions
and assert that they cannot alter structure, expose secrets or approve rules.

## 44. Cache

Reuse extraction cache identity. It includes source checksum, segment hash, structure
checksum, prompt/schema versions, model/provider and role. No raw source text in keys.

## 45. Cost/token telemetry

Report only provider-reported tokens and calls. Do not fabricate cost.

## 46. Source-change invalidation

A changed source checksum blocks ingest or changes the cache key. Rules derived from the
old checksum need review again.

## 47. Rule Pack diff

Existing deterministic pack diff is sufficient. MT evidence/reference changes must appear
as source, target or assertion changes.

## 48. Message Intelligence

Ordinary users see reviewed rules only. Candidate MT semantics remain hidden from normal
Create Message and Message Intelligence flows.

## 49. Validation UX

Reviewed rules report through existing `ValidationIssue` fields. User-facing messages stay
business-friendly; technical details carry rule/provenance metadata.

## 50. API contracts

Runtime `/api/v1` returns active reviewed-rule findings only. Source readiness is read-only
metadata and never exposes restricted source text.

## 51. Excel implications

Excel remains driven by installed structure and reviewed rules. Candidate rules do not
change templates, dropdowns or validation.

## 52. Capability dimensions

Keep structure, businessRules, marketPractice, clientProfile and externalValidation
separate. Structural discovery is not semantic readiness.

## 53. Readiness matrix

Generate `docs/generated/mt-semantic-readiness.md` for installed MTs plus representative
candidate-only source models.

## 54. Synthetic evaluation

Add an MT synthetic corpus for conditional requirement, prohibition, exactly one, at least
one, date relation, option/qualifier-specific references, invalid references, no-rule,
ambiguous, prompt-injection and model-memory traps.

## 55. Optional real-source evaluation

If no legitimate real MT semantic source is present, report
`REAL_MT_SEMANTIC_SOURCE = NOT_AVAILABLE` and stop at synthetic proof.

## 56. Performance

Measure ingestion, segmentation, reference resolution, candidate compilation, diff and
runtime evaluation in the report. LLM latency is build/review-time only.

## 57. Security

Audit path traversal, symlink escape, source confidentiality, prompt injection, cache
leakage, model-output injection, rule DSL execution, canonical-reference spoofing, SRU
spoofing, candidate activation and secret logging.

## 58. CI

Normal CI must not require live LLM calls. Add deterministic Phase 5A checks to local
targets and keep live evaluation separate.

## 59. Phase 5B handoff

Phase 5B requires actual authorised MT semantic source material at meaningful scale and
human-reviewed Rule Packs. Phase 5A does not start it.

## 60. Acceptance criteria

Phase 5A is complete when the foundation can ingest legitimate MT semantic source
metadata, segment it safely, bind candidates to exact MT structural references, compile
review-required candidates through the existing rule engine, prove a synthetic MT runtime
rule in isolation, report readiness honestly and pass CI.

# Plan self-review

**Can an LLM-created MT rule affect runtime validation without review?** No. The existing
registry refuses anything not fully reviewed; Phase 5A candidates remain outside the
runtime directory.

**Can a source paragraph reference a tag that does not exist?** It can, but deterministic
reference resolution returns `MT_RULE_FIELD_NOT_FOUND` or `RULE_REFERENCE_INVALID` and no
candidate is accepted as valid.

**Can a source rule resolve to the wrong repeated sequence?** The resolver must fail when
a repeated or ambiguous sequence target is not precise enough. Ambiguous is treated like
unresolved.

**Can a global Prowide qualifier constant be mistaken for message-context legality?** No.
Global field evidence remains separate. Qualifier legality stays unknown unless an
authorised source and installed row establish it.

**Can an SRU2025 rule be applied to SRU2026 silently?** No. Source release mismatch is a
structured blocker.

**Can an MT541 rule accidentally apply to MT543?** No. Rule Pack identity and structure
checksum target one message.

**Can a candidate rule mutate the Structure Pack?** No. The compiler only reads structure.

**Can a Rule Pack create a new tag?** No. A missing MT row or unresolved Prowide field
fails compilation/reference resolution.

**Can source instructions prompt-inject the extractor?** They can try. Prompts fence the
source as untrusted data, the schema is closed, compiler checks remain deterministic and
candidates are inactive.

**Are licensed source excerpts entering Git?** No. Excerpts default to not committed; no
real MT source is present in this branch.

**Are source hashes stable?** Yes, over exact bytes for real files and normalised corpus
text for synthetic evaluation.

**Does a source change invalidate cached extraction?** Yes. Source checksum and segment
hash are cache inputs.

**Can two extractions agreeing incorrectly make a rule active?** No. Agreement only
reduces review effort. Source control and review are the activation gate.

**Can the refuter approve a rule?** No. It can only criticise or recommend review/reject.

**Are UNKNOWN structural facts being guessed?** No. Requiredness, qualifier legality and
code-list legality remain UNKNOWN unless source-backed.

**Are we building a second Rule Engine?** No. Phase 5A adds MT metadata/resolution and uses
the existing DSL, compiler, evaluator and registry.

**Are we mass-activating Phase 4B candidates?** No. Runtime activation count remains zero.

**Are we implementing Phase 6 PR automation accidentally?** No. The branch creates one
normal PR manually via GitHub CLI and leaves it open.

**Is normal message validation still zero-LLM?** Yes. Extraction is offline only.

Correction from review: the first sketch put semantic references directly into runtime
Rule Packs. That would create a second addressing scheme. Runtime packs should keep using
installed `FieldRef` row IDs/triples; canonical MT structural references remain
evidence/provenance and candidate-validation metadata.
