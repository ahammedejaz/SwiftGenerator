# Specification engine Phase 4 report

Date: 2026-08-20

Branch: `feat/mt-prowide-structure-importer`

## Scope

Phase 4 added a generic MT structure evidence importer using Prowide Core. The importer is
offline and build-time only. It produces reviewed fixtures and reports; it does not add a
runtime Prowide dependency, does not install candidate MT messages, and does not claim
Swift certification or ISO 15022 conformance.

## Phase 3 Merge Evidence

PR #11 (`feat/mx-real-schema-scaleout`) was merged before starting Phase 4.

- PR head SHA before merge: `f0cbe028e30d1d506ce103d1ec2ca5d25ca0247c`
- Merge method: squash merge, with `--match-head-commit`
- Main SHA after merge: `34c48a17158b81ad82e191ead5cf1b122d276bc2`
- PR state after merge: `MERGED`
- Main post-merge CI run: all five jobs passed
- Branch protection was not bypassed
- Raw MX/XSD source artifacts remained ignored and uncommitted

## Source Verification

Swift primary-source check:

- Swift Standards Release page: `https://www.swift.com/standards/standards-releases`
- Swift standards overview: `https://www.swift.com/standards`
- SR2026 material is published for future release use, with live date `2026-11-14`
- On `2026-08-20`, SR2026 was not yet live; SR2025 remains the live default evidence
  stream for this phase

Prowide primary-source check:

- Prowide Core repository: `https://github.com/prowide/prowide-core`
- Prowide Core download docs:
  `https://dev.prowidesoftware.com/SRU2025-10/getting-started/download-core/`
- Maven Central package:
  `https://central.sonatype.com/artifact/com.prowidesoftware/pw-swift-core`
- Maven metadata:
  `https://repo.maven.apache.org/maven2/com/prowidesoftware/pw-swift-core/maven-metadata.xml`

The lock records `com.prowidesoftware:pw-swift-core:SRU2025-10.3.18`, Maven latest
observed `SRU2025-10.3.18`, metadata timestamp `20260814195521`, and Apache License
Version 2.0.

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

- `backend/app/spec_engine/mt_prowide/source.py`
- `backend/app/spec_engine/mt_prowide/source_scheme.py`
- `backend/app/spec_engine/mt_prowide/java_probe.py`
- `backend/app/spec_engine/mt_prowide/extractor.py`
- `backend/app/spec_engine/mt_prowide/reports.py`
- `tools/mt-prowide-extractor/MtProwideProbe.java`
- `backend/tests/fixtures/mt_prowide/category5-sru2025-10.3.18.json`
- `backend/tests/spec_engine/test_mt_prowide_importer.py`

Updated:

- `Makefile`
- `.github/workflows/ci.yml`
- `backend/app/spec_engine/__main__.py`
- `backend/app/studio/coverage.py`
- generated and human documentation

## Evidence Produced

The committed fixture records:

- Prowide Category 5 MT message classes: 55
- Configured MT messages observed in Prowide: 16 of 16
- Candidate-only Category 5 messages: 39
- Newly activated messages: 0
- Prowide-observed sequences: 500
- Prowide-observed fieldsets: 972
- Prowide-observed field groups: 6,387
- Reflected global field classes: 151
- Global field reflection errors: 0

Generated reports:

- `docs/generated/mt-importer-compatibility.md`
- `docs/generated/mt-prowide-structure-diff.md`
- `docs/generated/message-coverage.md`

The structure diff reports 10 configured MT messages with missing tag/sequence evidence
when compared against Prowide-derived structure by sequence delimiter code and tag option.
Those differences are reported only. Existing runtime MT structures were not rewritten.

## MT541 Cross-Engine Proof

`make verify-prowide-mt-source` regenerates the fixture from the pinned source and parses
the repository's generated MT541 sample through Prowide.

Observed result:

- source extraction: PASS
- messages extracted: 55
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
make check
make e2e
make build
make audit
make secret-scan
make coverage
make demo-pack-check
make xsd-compatibility
docker compose config --quiet
git diff --check
make mt-prowide-reports-write
make mt-prowide-check
make verify-prowide-mt-source
cd backend && .venv/bin/pytest tests/spec_engine/test_mt_prowide_importer.py -q
cd backend && .venv/bin/ruff check app/spec_engine/mt_prowide app/spec_engine/__main__.py app/studio/coverage.py tests/spec_engine/test_mt_prowide_importer.py
cd backend && .venv/bin/mypy app/spec_engine/mt_prowide app/spec_engine/__main__.py app/studio/coverage.py tests/spec_engine/test_mt_prowide_importer.py --strict
```

Observed results:

- `make check`: PASS
- backend tests: 1,317 passed, 23 skipped, 1 deselected, 2 warnings
- mypy: PASS on 182 source files
- Playwright: 80 passed
- production frontend build: PASS
- dependency audit: PASS, no known vulnerabilities and 0 npm vulnerabilities
- secret scan: PASS
- coverage, XSD compatibility, demo pack and MT Prowide report gates: PASS
- YAML parsing for CI and the Prowide lock: PASS
- `docker compose config --quiet`: PASS
- `git diff --check`: PASS

Local `docker compose build` was retried and failed before any repository Dockerfile step
while Docker was loading metadata for `python:3.13-slim` from Docker Hub:
`DeadlineExceeded: context deadline exceeded`. Direct `docker pull python:3.13-slim` also
timed out after 60 seconds, and neither `python:3.13-slim` nor `node:22-alpine` was cached
locally. An HTTPS probe to `https://registry-1.docker.io/v2/` returned the expected
registry authentication challenge, so this is recorded as a local Docker daemon/base-image
pull limitation rather than a repository Dockerfile failure. The post-merge main Docker CI
job for SHA `34c48a17158b81ad82e191ead5cf1b122d276bc2` passed; the Phase 4 PR Docker job
remains the remote authority.

## Boundaries Preserved

- No runtime package imports `app.spec_engine.mt_prowide`.
- No Java, Maven, Gradle or Prowide dependency is needed for normal generation.
- Candidate structures are not exposed in the catalogue.
- Existing configured MT messages are not silently overwritten.
- Global field classes are stored separately from message-level field groups.
- Qualifier legality, code-list legality, network validation and usage rules remain
  `UNKNOWN`.
- Prowide evidence is labelled as structural evidence only.

## Remaining Work

After this PR, a separate reviewed phase can decide whether any reported structure
differences should become runtime configuration changes. That future work needs authorised
source evidence and should not be bundled with Prowide fixture maintenance.
