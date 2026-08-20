# Specification engine Phase 4B report

Date: 2026-08-20

Branch: `feat/mt-prowide-multicategory-scaleout`

## Scope

Phase 4B widens the offline Prowide-derived MT structure importer from Category 5 to every
MT source model class present in the pinned Prowide Core SRU2025 artifact. The branch adds
multi-category discovery, explicit candidate lifecycle/readiness evidence, generated
coverage reports and canonical MT structural references for future authorised rule packs.

It remains build-time only. It does not add a runtime Prowide, Java, Maven or Gradle
dependency; it does not install candidate MT messages; and it does not claim Swift
certification, ISO 15022 conformance, UHB completeness or qualifier/code-list legality.

## Phase 4 Merge Evidence

Phase 4 PR #12 (`feat/mt-prowide-structure-importer`) was merged before starting Phase 4B.

- PR head SHA before merge: `ea00fe90c3abe064b8212df2f0202b9be05dfaa3`
- Merge method: squash merge, with `--match-head-commit`
- Main SHA after merge: `a6e22b9bdf1d74cc397383ada6db17a4c0786d9b`
- PR state after merge: `MERGED`
- Main post-merge CI run: all six jobs passed
- Branch protection was not bypassed
- Raw jars, compiled classes and Prowide build caches remained ignored and uncommitted

## Source Verification

Swift and Prowide source identity stayed on the Phase 4 lock:

- Swift Standards Release page: `https://www.swift.com/standards/standards-releases`
- Swift standards overview: `https://www.swift.com/standards`
- Prowide Core repository: `https://github.com/prowide/prowide-core`
- Prowide Core download docs:
  `https://dev.prowidesoftware.com/SRU2025-10/getting-started/download-core/`
- Maven Central package:
  `https://central.sonatype.com/artifact/com.prowidesoftware/pw-swift-core`
- Maven metadata:
  `https://repo.maven.apache.org/maven2/com/prowidesoftware/pw-swift-core/maven-metadata.xml`

The active lock is `backend/config/mt_prowide_sru2025_10_3_18.lock.yaml`. It records
`com.prowidesoftware:pw-swift-core:SRU2025-10.3.18`, Swift release `SR2025`, Maven latest
observed `SRU2025-10.3.18`, metadata timestamp `20260814195521`, verified date
`2026-08-20`, and Apache License Version 2.0.

SR2026 remains future/test evidence until the documented live-release procedure says
otherwise.

## Artifact Checksums

| Artifact | SHA-256 |
| --- | --- |
| `pw-swift-core-SRU2025-10.3.18.jar` | `84993fffae87f7da5db3cad439351072aa5d04fb59fe56515e08eae4b4523997` |
| `pw-swift-core-SRU2025-10.3.18-sources.jar` | `1335e5bf848f8226cad569f45c89728687716b5ce0cb0a5e483e6400293ada0a` |
| `commons-lang3-3.20.0.jar` | `69e5c9fa35da7a51a5fd2099dfe56a2d8d32cf233e2f6d770e796146440263f4` |
| `commons-text-1.15.0.jar` | `58d2da30f058512a1e7f914e39241deca4dff5c27a085b4ed2faa9e7208067f6` |
| `gson-2.14.0.jar` | `2cbd119bf1961c28788310963dc80ba65f58cdeec1dd139c8bdb1240faa2c36f` |

Downloaded jars and compiled Java classes are stored only under ignored `build/`
directories.

## Implementation

Added:

- `backend/app/spec_engine/mt_prowide/references.py`
- `backend/tests/fixtures/mt_prowide/all-categories-sru2025-10.3.18.json`
- `docs/generated/mt-multicategory-coverage.md`
- `docs/mt-multicategory-scaleout-plan.md`
- `docs/history/specification-engine-phase-04b-report.md`

Updated:

- `Makefile`
- `backend/app/spec_engine/__main__.py`
- `backend/app/spec_engine/mt_prowide/extractor.py`
- `backend/app/spec_engine/mt_prowide/models.py`
- `backend/app/spec_engine/mt_prowide/reports.py`
- `backend/app/spec_engine/mt_prowide/source.py`
- `backend/app/spec_engine/mt_prowide/source_scheme.py`
- `backend/app/studio/coverage.py`
- `backend/tests/spec_engine/test_mt_prowide_importer.py`
- generated and human documentation

Removed:

- `backend/tests/fixtures/mt_prowide/category5-sru2025-10.3.18.json`

## Evidence Produced

The committed fixture records:

- Prowide MT source model classes: 274
- Categories discovered: 0 through 9
- Per-category counts: Cat0 59, Cat1 19, Cat2 14, Cat3 25, Cat4 17, Cat5 55, Cat6 17,
  Cat7 38, Cat8 9, Cat9 21
- Configured MT messages observed in Prowide: 16 of 16
- Candidate-only source models: 258
- Newly activated messages: 0
- Prowide-observed sequences: 1,042
- Prowide-observed fieldsets: 990
- Prowide-observed field groups: 9,710
- Reflected global field classes: 620
- Global field reflection errors: 0

Variants present in the source jar, including `MT102_STP`, `MT103_REMIT` and `MT103_STP`,
remain distinct source models. `MT202COV` was not present in the selected Prowide source
artifact.

Generated reports:

- `docs/generated/mt-multicategory-coverage.md`
- `docs/generated/mt-importer-compatibility.md`
- `docs/generated/mt-prowide-structure-diff.md`
- `docs/generated/message-coverage.md`

The structure diff still reports 10 configured MT messages with missing tag/sequence
evidence when compared against Prowide-derived structure by sequence delimiter code and tag
option. Those differences are classified as
`REPOSITORY_CONFIGURATION_DIFFERENCE` or `SEQUENCE_DELIMITER_MATCHING_LIMITATION` and are
reported only. Existing runtime MT structures were not rewritten.

## Authoring Readiness

Phase 4B adds explicit structural state and authoring-readiness fields:

- Existing configured MT messages are `PARTIAL`, with installed runtime specs preserved.
- Candidate-only source models are `STRUCTURAL_EVIDENCE_ONLY`.
- Candidate blockers include `NO_RUNTIME_SPECIFICATION`, `REQUIREDNESS_REVIEW_MISSING`,
  `QUALIFIER_RULES_UNKNOWN`, `CODE_LIST_RULES_UNKNOWN`,
  `BUSINESS_RULE_SOURCE_MISSING` and `SAMPLE_MISSING`.
- `AUTHORING_READY` count is 0.

Global field definitions remain separate from message-level field use. Prowide field
constants and parser patterns are global syntax evidence only; they are not promoted into
message-context dropdowns, requiredness rules or qualifier legality.

## Canonical References

`backend/app/spec_engine/mt_prowide/references.py` resolves a Prowide structural location
to a stable `MtStructuralReference`. The resolver accepts internal sequence paths or
delimiter-code paths and returns a canonical identifier shaped for future authorised rule
packs, for example:

```text
MT:SR2025:MT541:SETDET:22F:SETR
```

This is an addressing seam only. Phase 5 semantic import is not started in this branch.

## Cross-Engine Proof

`make verify-prowide-mt-source` regenerates the all-category fixture from the pinned source
and parses the repository's generated MT541 sample through Prowide.

Observed result:

- source extraction: PASS
- messages extracted: 274
- MT541 Prowide parse proof: PASS
- Python tag count: 20
- Prowide tag count: 20
- Python import errors: 0
- Python import warnings: 0

The proof compares the tag stream only. It is not a Prowide validation result and not a
Swift conformance claim.

## Final Local Verification

Commands run during implementation and final verification:

```bash
make mt-prowide-extract
make mt-prowide-reports-write
make mt-prowide-check
make verify-prowide-mt-source
cd backend && .venv/bin/pytest tests/spec_engine/test_mt_prowide_importer.py -q
cd backend && .venv/bin/ruff check app/spec_engine/mt_prowide app/spec_engine/__main__.py app/studio/coverage.py tests/spec_engine/test_mt_prowide_importer.py
cd backend && .venv/bin/mypy app/spec_engine/mt_prowide app/spec_engine/__main__.py app/studio/coverage.py tests/spec_engine/test_mt_prowide_importer.py --strict
make check
make e2e
make build
make audit
make secret-scan
make coverage
make demo-pack-check
make xsd-compatibility
docker compose config --quiet
docker compose build
git diff --check
```

Observed results:

- `make check`: PASS
- backend tests: 1,320 passed, 23 skipped, 1 deselected, 2 warnings
- mypy: PASS on 183 source files
- Playwright: 80 passed
- production frontend build: PASS
- dependency audit: PASS, no known pip vulnerabilities and 0 npm vulnerabilities
- secret scan: PASS
- coverage, XSD compatibility, demo pack and MT Prowide report gates: PASS
- `docker compose config --quiet`: PASS
- `docker compose build`: PASS
- `git diff --check`: PASS
- candidate catalogue leakage check: PASS for representative candidates
- no Prowide probe or `javac` process remained after verification

## Pull Request and CI

Pending until the Phase 4B branch is pushed and its final pull request head finishes CI.

## Boundaries Preserved

- No runtime package imports `app.spec_engine.mt_prowide`.
- No Java, Maven, Gradle or Prowide dependency is needed for normal generation.
- Candidate structures are not exposed in the catalogue.
- Existing configured MT messages are not silently overwritten.
- Global field classes are stored separately from message-level field groups.
- Qualifier legality, code-list legality, network validation and usage rules remain
  `UNKNOWN`.
- Prowide evidence is labelled as structural evidence only.
- `build/mt-prowide-cache/`, `build/mt-prowide-candidates/`, jars and class files remain
  uncommitted.

## Remaining Work

Future authorised-source phases can use the new canonical structural references to attach
message-specific requiredness, qualifier, code-list, market-practice and business-rule
evidence. That work needs approved SWIFT/UHB material, approved MyStandards/client exports
or reviewed client rule packs, and should not be bundled with Prowide fixture maintenance.
