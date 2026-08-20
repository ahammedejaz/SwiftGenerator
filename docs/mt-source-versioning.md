# MT source versioning

MT source evidence is release-specific. Do not update an artifact version just because a
newer one exists. First decide whether it represents the current live Swift MT release,
then update the lock, fixture, generated reports and docs together.

## Current Lock

The active importer lock is
`backend/config/mt_prowide_sru2025_10_3_18.lock.yaml`.

The active committed evidence fixture is
`backend/tests/fixtures/mt_prowide/all-categories-sru2025-10.3.18.json`.

| Field | Value |
| --- | --- |
| Source | Prowide Core |
| Maven coordinate | `com.prowidesoftware:pw-swift-core:SRU2025-10.3.18` |
| Swift release represented | `SR2025` |
| Verified date | `2026-08-20` |
| Maven metadata latest observed | `SRU2025-10.3.18` |
| Maven metadata last updated | `20260814195521` |
| Prowide license recorded | Apache License Version 2.0 |

The lock records SHA-256 checksums for every jar the offline Java probe needs. The
checksum gate is the authority, not the mutable Maven metadata endpoint.

## Live Release Rule

As of `2026-08-20`, Swift's official Standards Release page publishes SR2026 material and
dates the SR2026 live release for `2026-11-14`. That makes SR2026 useful for future/test
planning, but not the default live evidence stream for this repository yet.

Until `2026-11-14`, the importer treats:

- `SRU2025-10.3.18` as the current live Prowide structural evidence stream.
- `SRU2026-*` as future/test evidence.

After `2026-11-14`, update this document and the lock only after re-running the full
upgrade procedure in [mt-standards-upgrades.md](mt-standards-upgrades.md).

## Source Links

- Swift Standards Release schedule: `https://www.swift.com/standards/standards-releases`
- Swift standards overview: `https://www.swift.com/standards`
- Prowide Core repository: `https://github.com/prowide/prowide-core`
- Prowide Core download docs: `https://dev.prowidesoftware.com/SRU2025-10/getting-started/download-core/`
- Maven Central package: `https://central.sonatype.com/artifact/com.prowidesoftware/pw-swift-core`
- Maven metadata: `https://repo.maven.apache.org/maven2/com/prowidesoftware/pw-swift-core/maven-metadata.xml`

## What Versioning Does Not Claim

The lock proves only that a deterministic extractor read a known Prowide artifact. It does
not prove the repository implements the Swift release, and it does not prove Prowide's
model is complete for this repository's intended use.

The generated reports therefore use precise language:

- `Prowide-derived structural evidence`
- `observed`
- `candidate`
- `UNKNOWN`
- `NOT_CLAIMED`

Avoid these phrases unless a licensed source has been reviewed:

- Swift-certified
- Swift-compliant
- ISO 15022 compliant
- UHB-complete
- all qualifiers supported
- all network rules supported

## Reproducibility

`make verify-prowide-mt-source` performs the reproducibility proof:

1. Download every pinned artifact to `build/mt-prowide-cache/`.
2. Verify each SHA-256.
3. Parse Prowide source schemes and reflect global field classes.
4. Write a fresh candidate extraction under `build/mt-prowide-candidates/`.
5. Compare the fresh candidate with the committed fixture.
6. Parse MT541 with Prowide and compare the tag stream with the Python importer.

The fresh candidate path is ignored by git. Reviewers should inspect the diff in the
committed fixture and generated reports, not raw downloaded jars.
