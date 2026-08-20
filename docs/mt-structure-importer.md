# MT Prowide structure importer

The MT Prowide structure importer is an offline developer tool. It uses Prowide Core as
release-pinned structural evidence for all MT source model classes discovered in the
pinned artifact, then writes deterministic fixtures and reports that can be reviewed in a
normal pull request.

It is not part of message generation. The FastAPI runtime does not load Java, Prowide,
Maven or Gradle.

## Files

| File | Purpose |
| --- | --- |
| `backend/config/mt_prowide_sru2025_10_3_18.lock.yaml` | Pinned source, artifact URLs and checksums. |
| `backend/app/spec_engine/mt_prowide/` | Offline extractor, source parser, Java probe wrapper and report renderers. |
| `tools/mt-prowide-extractor/MtProwideProbe.java` | Small Java reflection/parse probe compiled only by the offline target. |
| `backend/tests/fixtures/mt_prowide/all-categories-sru2025-10.3.18.json` | Committed deterministic evidence fixture. |
| `docs/generated/mt-prowide-structure-diff.md` | Diff between configured MT rows and Prowide-derived structure evidence. |
| `docs/generated/mt-importer-compatibility.md` | Counts, runtime boundary, candidate lifecycle and limitations. |
| `docs/generated/mt-multicategory-coverage.md` | Category distribution, candidate blockers and authoring-readiness analysis. |

## Commands

```bash
make mt-prowide-extract
make mt-prowide-reports-write
make mt-prowide-check
make verify-prowide-mt-source
```

`make mt-prowide-check` is part of `make check`. It reads only the committed fixture and
generated reports, so it needs no network, Java, Maven or Gradle.

`make verify-prowide-mt-source` is a stronger developer and CI proof. It downloads the
pinned artifacts into `build/mt-prowide-cache/`, verifies checksums, refresh-extracts a
candidate fixture into `build/mt-prowide-candidates/`, compares it with the committed
fixture, then parses the repository's generated MT541 sample through Prowide and compares
the tag stream with the Python importer.

## Evidence Model

The importer stores four kinds of evidence:

| Evidence | Source | What it means |
| --- | --- | --- |
| `PROWIDE_SOURCE_JAVADOC_SCHEME` | Generated scheme in the Prowide source jar | Message class, sequence, fieldset and field-group shape was observed. |
| `PROWIDE_FIELD_CLASS_REFLECTION` | Prowide `FieldNNx` classes | Global parser and validator patterns were observed for a tag option. |
| `PROWIDE_PARSER_ROUND_TRIP` | Prowide parser probe | A generated MT541 FIN sample produced the same tag stream. |
| `REPOSITORY_REVIEWED_CONFIGURATION` | Existing YAML configuration | The row already belongs to the configured runtime subset. |

Global field definitions and message field use are deliberately separate. A global class
such as `Field20C` can expose a validator pattern, but that never means `20C` is
mandatory, permitted or qualifier-legal in a specific message.

## What Stays Unknown

These values remain `UNKNOWN` until reviewed against an authorised source:

- qualifier legality in a message
- code-list legality in a message
- full message-level field permission
- network validation rules
- market practice
- client usage rules
- authoritative completeness against ISO 15022 or a Swift UHB release

## Candidate Lifecycle

The fixture contains all observed Prowide MT source model classes, but only the
repository's existing configured MT set is active at runtime. As of the SRU2025-10.3.18
fixture, 274 source models are structurally extracted across categories 0-9; 258 source
models are inert candidates and zero are activated.

Candidates are written as evidence only. Promoting one requires a separate review that
adds a message manifest entry, knowledge records, samples, validation behavior, docs and
tests. This phase does not perform that promotion.

## Runtime Boundary

The importer package is under `app.spec_engine`, the existing offline developer surface.
Runtime generation still reads the reviewed YAML specification and knowledge files. A test
scans runtime packages and fails if they import `app.spec_engine.mt_prowide`.

Ignored directories:

```text
build/mt-prowide-cache/
build/mt-prowide-candidates/
build/mt-prowide-inspect/
```

Those directories may contain downloaded jars, compiled Java classes and fresh extraction
candidates. They are never committed.
