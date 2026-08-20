# Specification Engine Phase 5A Report

## 1. Executive summary

Phase 5A adds the evidence-backed MT semantic rule ingestion foundation. It connects
authorised MT semantic source material to the existing Phase 2 Rule Engine through
deterministic source ingestion, stable segmentation, MT canonical reference
resolution, candidate-only extraction, review packaging, and readiness reporting.

This phase does not activate new production MT semantic rules and does not treat
Prowide structural evidence as semantic authority.

## 2. Base main SHA

`e43372e015210106960b993813a8e09cca86b3b5`

## 3. Feature branch

`feat/mt-semantic-rule-ingestion`

## 4. Baseline test results

The feature branch was created from a clean, fast-forwarded `main`. Baseline checks
were run before feature work and passed locally. Final verification on the Phase 5A
implementation is the authoritative result set for this report.

## 5. Phase 2 reuse audit

Phase 5A reuses the existing Phase 2 Rule Engine source bundle, extraction pipeline,
review model, Rule Pack format, effective rule evaluation, deterministic diagnostics,
and fake/scripted provider paths for normal tests. It does not introduce a separate
MT-only runtime rule evaluator.

## 6. Phase 4B reuse audit

Phase 5A reuses Phase 4/4B MT structural evidence and canonical MT references as
metadata for deterministic reference validation. Prowide remains build-time/offline
structural evidence only.

## 7. Existing MT runtime coverage

The existing configured runtime MT set remains 16 messages:
`MT530`, `MT537`, `MT540`, `MT541`, `MT542`, `MT543`, `MT544`, `MT545`, `MT546`,
`MT547`, `MT548`, `MT564`, `MT565`, `MT566`, `MT567`, `MT568`.

## 8. 274-model structural status

The 274 Prowide-discovered MT source models remain structural/reporting evidence.
They are not mass-activated and do not become semantic-rule authority.

## 9. Semantic authority model

Authority remains:

1. Authorised source evidence for semantic/business rules.
2. LLM output as candidate interpretation only.
3. Deterministic compiler/reference validation.
4. Review.
5. Source-controlled reviewed Rule Pack.
6. Runtime execution of reviewed deterministic rules only.

## 10. Local source audit

No real authorised MT semantic source was found in the repository-configured source
locations. The only committed MT semantic source is the synthetic fixture
`SYNTH-MT-SEMANTIC-V1`.

## 11. Real source availability

`REAL_MT_SEMANTIC_SOURCE_AVAILABLE = NO`

Real-source extraction was not attempted because no legitimate authorised source was
available locally.

## 12. Licensing/privacy boundaries

Default source policy remains conservative:

- source material is not automatically commit-safe;
- excerpts are not automatically commit-safe;
- redistribution is `UNKNOWN` unless established by the source/operator;
- non-synthetic source cannot be sent to an external model unless both source and
  provider approval flags are explicitly true.

## 13. Source Bundle changes

The source model now supports MT semantic metadata:

- standards release/SRU;
- applicable MT categories;
- message identifiers;
- MT semantic source types;
- explicit external model processing approval;
- explicit provider approval for source classification.

## 14. Source ingestion

The ingestion path remains local and deterministic. The synthetic MT source fixture
ingests into 19 stable segments with checksum
`sha256:e96783668aa8e1c3f76e5c94eb59981d863dd1b9b7f931cdc3321e21db98d139`.

## 15. PDF behaviour

Phase 5A documents and supports text-layer PDF handling only. OCR and scanned-PDF
interpretation remain outside scope.

## 16. Segmentation

Stable Phase 2 segmentation is reused. Segment identity is based on source identity,
source checksum, source location metadata, and segment content hash.

## 17. Exact SRU binding

MT semantic sources and reference requests can bind to exact standards releases such
as `SRU2025`. A release mismatch fails with a deterministic diagnostic rather than
silently floating a rule across SRUs.

## 18. Canonical MT references

The MT semantic resolver produces canonical provenance such as
`MT:SR2025:MT541:SETDET:22F:SETR` and runtime field rows such as
`MT541-E-22F-SETR` without claiming semantic legality from structure alone.

## 19. Sequence resolution

Sequence paths are resolved deterministically against installed MT runtime structure
and Prowide structural evidence. Missing sequences fail with
`MT_RULE_SEQUENCE_NOT_FOUND`.

## 20. Tag resolution

Message/tag mismatches fail with `MT_RULE_FIELD_NOT_FOUND`.

## 21. Option resolution

Option requests are validated deterministically. Missing or unsupported options fail
with `MT_RULE_OPTION_NOT_RESOLVED`.

## 22. Qualifier resolution

Qualifier requests are resolved only where evidence supports a runtime structural row.
Unknown qualifier legality remains unknown; unresolved qualifiers fail with
`MT_RULE_QUALIFIER_NOT_RESOLVED`.

## 23. Component resolution

Component references are checked against known component structure and fail with
`MT_RULE_COMPONENT_NOT_FOUND` when unsupported.

## 24. Rule DSL reuse

The existing Rule DSL remains the active representation. Phase 5A does not add
executable DSL hooks, arbitrary code, or a parallel MT evaluator.

## 25. MT-specific DSL changes

No MT-only runtime DSL was added. MT-specific work is limited to source metadata,
reference grounding, diagnostics, and review/readiness support.

## 26. Extraction A/B

The existing strict extraction pipeline remains the path for candidate generation.
Synthetic evaluation uses deterministic offline fixtures in normal tests.

## 27. Diff

Candidate diff/review behavior continues to be handled by the existing Phase 2
review pipeline.

## 28. Refuter

The refuter remains a critic only. Refuter output does not approve or activate rules.

## 29. Reference validation

New deterministic MT diagnostics include:

- `MT_RULE_MESSAGE_NOT_FOUND`
- `MT_RULE_SRU_MISMATCH`
- `MT_RULE_SEQUENCE_NOT_FOUND`
- `MT_RULE_FIELD_NOT_FOUND`
- `MT_RULE_OPTION_NOT_RESOLVED`
- `MT_RULE_QUALIFIER_NOT_RESOLVED`
- `MT_RULE_COMPONENT_NOT_FOUND`
- `MT_RULE_REFERENCE_AMBIGUOUS`

## 30. Candidate compilation

Candidates remain inert unless reviewed and source-controlled as active Rule Packs.
No candidate output can mutate MT structure.

## 31. Review artifacts

Review artifacts now carry MT source metadata and canonical MT target references so a
reviewer can evaluate the evidence without relying on model memory.

## 32. Runtime activation boundary

Runtime activation count from Phase 5A: `0`.

## 33. Cache

Cache identity remains source/checksum/segment/model/prompt grounded through Phase 2
paths. Source or structure changes invalidate extracted candidate identity.

## 34. Prompt injection

Synthetic fixtures cover prompt-injection text and prove that malicious source text is
untrusted input. Runtime validation performs no model calls.

## 35. Model-memory leakage defence

Synthetic fixtures cover no-rule/model-memory traps. Model familiarity with MT tags or
qualifiers is not standards evidence.

## 36. Privacy gate

Non-synthetic, unapproved sources are blocked before any model call with
`RULE_EXTRACTION_PRIVACY_BLOCKED`; token and call counts remain zero.

## 37. Synthetic corpus

The MT synthetic corpus contains 18 cases covering rule/no-rule behavior, invalid MT
references, wrong SRU, ambiguity, prompt injection, and model-memory traps.

## 38. Offline results

`make evaluate-mt-rule-extraction` passed with 18/18 synthetic MT cases.

## 39. Live synthetic results

Live synthetic extraction was probed and returned
`LIVE_EXTRACTION_NOT_VERIFIED` because no approved model provider was configured.
This is a missing measurement, not a passing live extraction result.

## 40. Real source results

No real authorised MT semantic source was available, so real-source extraction was not
attempted.

## 41. Synthetic MT E2E proof

Focused tests prove a temporary reviewed synthetic MT client-profile Rule Pack loads
only for an isolated test profile, produces deterministic validation behavior, and
does not activate in the normal base profile.

## 42. Rule validation result

Correct values pass; violating synthetic values fail only under the isolated reviewed
test profile. Normal runtime validation remains candidate-free.

## 43. Semantic readiness matrix

`docs/generated/mt-semantic-readiness.md` reports configured/runtime messages
separately from semantic-source availability and authoring readiness.

## 44. Source-readiness matrix

`docs/generated/mt-semantic-source-readiness.md` reports supported formats, configured
drop points, synthetic fixture availability, and the absence of real authorised MT
semantic source material.

## 45. Capability impact

Existing reviewed capabilities remain unchanged. Candidate rules do not improve user
visible capability until reviewed and source-controlled.

## 46. Runtime activation count

`EXISTING_MT_RUNTIME_ACTIVATIONS = 0`

## 47. Existing regression

Final local regression passed:

- backend pytest: 1335 passed, 23 skipped, 1 deselected;
- Playwright: 80 passed;
- build: passed;
- audit: passed;
- secret scan: passed;
- Docker compose config/build: passed;
- git whitespace check: passed.

## 48. Browser verification

`make e2e` passed locally with 80 Playwright tests. CI Browser E2E also passed on the
PR head.

## 49. Performance

Runtime message validation remains zero-LLM. MT semantic extraction is build/review
time only.

## 50. Security

Security audit and secret scan passed. No tracked Prowide JARs, `.class` files,
Maven/Gradle caches, source archives, credentials, API keys, restricted sources, or
`workPrompt.txt` were committed.

## 51. Test counts

Focused MT semantic tests: 15 passed.

Full local backend suite in `make check`: 1335 passed, 23 skipped, 1 deselected.

Playwright: 80 passed.

## 52. Docker

`docker compose config --quiet` and `docker compose build` passed locally and in CI.

## 53. CI

PR CI passed on the implementation head before this report artifact was added:
`88599964d1cbfbba4d8277508b4e11894f82cd24`.

The final PR head and final CI run are recorded in the PR metadata and Codex final
response after the report commit is pushed.

## 54. Known limitations

- No real authorised MT semantic source is present.
- Live extraction quality is unmeasured without an approved provider.
- Scanned/image-only PDF OCR is out of scope.
- Phase 4B candidate MTs remain inactive.
- No SWIFT-compliance or standards-completeness claim is made.

## 55. Exact operator source needed for Phase 5B

Phase 5B needs one or more authorised sources with clear SRU/release identity:

- authorised SWIFT MT Standards/UHB material for the target SRU;
- approved MyStandards export;
- client implementation guide;
- approved internal rule specification.

Preferred formats: `.txt`, `.md`, clean `.html`, or text-layer `.pdf`.
Acceptable local structured formats can include `.json`, `.xml`, `.csv`, `.yaml`,
`.yml`, or `.xlsx` if mapped by repository tooling. Scanned PDFs need preprocessing
outside Phase 5A.

## 56. Phase 5B readiness

`PHASE_5B_READY = NO`

The foundation is ready, but meaningful Phase 5B promotion requires real authorised
semantic source material and review.

## 57. Final commit

The implementation commit before this report-only update is
`88599964d1cbfbba4d8277508b4e11894f82cd24`.

The PR head after this report is authoritative for merge consideration.

## 58. PR

Phase 5A PR: https://github.com/ahammedejaz/SwiftGenerator/pull/14

The PR is intentionally left open.

## 59. CI run

The final CI run is the latest CI run attached to the final PR head. It must include:

- Required Checks
- MT Prowide Source
- Clean Clone
- Docker
- Security Audit
- Browser E2E

All must be completed successfully before merging in a later task.
