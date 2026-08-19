# MX Real Schema Scale-Out — Phase 3 Report

Point-in-time report for `feat/mx-real-schema-scaleout`, started from `main` at
`39b2e9bce63120e24fe6fd2267833b606bd63136`.

## Summary

Phase 3 adds the build-time pipeline needed to scale MX onboarding from legitimate ISO
20022 sources without adding message-family-specific runtime code:

- metadata-only ISO catalogue snapshot support with parallel current definition groups;
- ignored source-cache/drop directory for raw XSD bundles;
- source manifest model with authority and redistribution declarations;
- ISO-only source discovery/fetch command surface;
- ISO message-set bundle discovery/fetch/inspection with safe ZIP validation;
- per-message source acquisition, batch compilation and six-gate reporting;
- generated XSD compiler compatibility matrix;
- business-area mapping for `pacs`, `pain`, `camt`, `sese`, `semt` and `seev`;
- GitHub Actions hygiene update to current Node-24-based official action majors while
  preserving cache behaviour.

No raw ISO XSD body is committed. No real generated pack is installed. No business rule is
created or promoted. The foundation is complete; real ISO-schema proof is not complete
because official XSD and message-set bundle bytes could not be downloaded from this
execution environment.

## Git Safety

- Started on clean `main`.
- Fetched and fast-forward pulled `origin/main`.
- Confirmed `HEAD == origin/main` at
  `39b2e9bce63120e24fe6fd2267833b606bd63136`.
- Created `feat/mx-real-schema-scaleout`.
- `workPrompt.txt` remained local/ignored and was not committed.

## Baseline Verification

Before changes:

- `make check`: pass.
- Backend tests: 1274 passed, 23 skipped, 1 deselected.
- mypy strict source count: 173 files.
- Playwright: 80 passed.
- `make secret-scan`: pass.
- `make coverage`: current.
- `make demo-pack-check`: current.
- `docker compose config --quiet`: pass.
- `docker compose build`: pass.
- `git diff --check`: clean.
- Configured messages: 23 total, 16 MT and 7 MX.
- Official ISO 20022 schemas present: 0 of 7 configured MX messages.

## First Pass: Official Catalogue Snapshot

A representative current set was resolved from official ISO 20022 catalogue pages on
2026-08-20 and recorded in
`backend/config/mx/xsd/sources/catalogue-snapshot-2026-08-20.yaml`.

The first-pass snapshot covered 14 definitions across the requested families:

| Logical | Current definition | Area |
| --- | --- | --- |
| pacs.008 | pacs.008.001.14 | Payments Clearing & Settlement |
| pacs.009 | pacs.009.001.13 | Payments Clearing & Settlement |
| pain.001 | pain.001.001.13 | Payment Initiation |
| pain.002 | pain.002.001.15 | Payment Initiation |
| camt.052 | camt.052.001.14 | Cash Management |
| camt.053 | camt.053.001.14 | Cash Management |
| camt.054 | camt.054.001.14 | Cash Management |
| sese.023 | sese.023.001.13 | Securities Settlement |
| sese.024 | sese.024.001.14 | Securities Settlement |
| sese.025 | sese.025.001.13 | Securities Settlement |
| semt.002 | semt.002.001.12 | Securities Management |
| semt.017 | semt.017.001.14 | Securities Management |
| seev.031 | seev.031.001.16 | Securities Events |
| seev.035 | seev.035.001.17 | Securities Events |

Redistribution is `UNKNOWN` for every entry. `sourceChecksum` is absent because raw XSD
bytes were not acquired into this repository.

## First Pass: Source Acquisition Result

The Python direct discovery command first hit sandbox DNS restrictions, then local TLS CA
configuration, then a long ISO catalogue read stall. The implementation now uses `certifi`
when available and records per-message unresolved fetches instead of losing the whole run,
but the committed snapshot was created from official catalogue page data rather than raw
schema download.

`make mx-scaleout` was run against the empty ignored source cache and produced the expected
failure-isolated report:

- attempted: 14;
- compiled: 0;
- six-gate passed: 0;
- failed: 14;
- failure reason: each exact `<messageDefinition>.xsd` source file was missing.

This is the correct Phase 3 result without operator-supplied raw source artifacts.

## Completion Pass: Acquisition Fixes

This pass fixed the generic acquisition path rather than manually creating source files:

- `mx-source-fetch` now validates `application/octet-stream` XSD responses instead of
  blindly trusting or rejecting them.
- The initial URL, every redirect and final URL must remain HTTPS `iso20022.org`.
- Cross-domain redirects and HTTP downgrade are rejected.
- The fetched body must be within the configured XSD file-size limit, parse as safe XML,
  reject DOCTYPE/entity declarations, have an `xs:schema` root and match the exact ISO
  target namespace for the message definition.
- Optional expected checksums are verified before the file is written.
- `mx-source-acquire` resolves a missing manifest `xsdUrl` by re-reading the official
  catalogue `sourceUrl`, locating the exact message-definition row, and then downloading
  that XSD link into the ignored source cache.
- CLI fetch failures now report a concise acquisition error instead of a traceback.

Regression tests cover valid octet-stream XSDs, arbitrary binary, HTML error pages,
trusted redirects, cross-domain redirects, HTTP downgrade, target-namespace mismatch,
checksum mismatch, oversized bodies and manifest acquisition with runtime `xsdUrl`
resolution. These tests are fully mocked, so normal CI does not depend on ISO uptime.

## Completion Pass: Current Version Semantics

The first-pass snapshot accidentally represented one current definition per logical
message. This pass corrected the metadata model and snapshot:

- `logicalMessage` is a grouping key, not a runtime Structure Pack identity.
- `currentDefinitions` records every observed current exact definition for a logical
  message.
- No numeric max-version rule is used.
- Parallel `.001` and `.002` securities/event branches remain separate exact candidates.

The updated metadata snapshot now contains 29 exact current definitions across `pacs`,
`pain`, `camt`, `sese`, `semt` and `seev`, including the current securities definitions
needed for reconciliation:

| Logical | Current definitions recorded |
| --- | --- |
| sese.020 | `sese.020.001.09`, `sese.020.002.07` |
| sese.023 | `sese.023.001.13`, `sese.023.002.11` |
| sese.024 | `sese.024.001.14`, `sese.024.002.12` |
| sese.025 | `sese.025.001.13`, `sese.025.002.11` |
| sese.027 | `sese.027.001.09`, `sese.027.002.07` |
| sese.030 | `sese.030.001.10`, `sese.030.002.09` |
| sese.031 | `sese.031.001.11`, `sese.031.002.09` |
| semt.002 | `semt.002.001.12`, `semt.002.002.11` |
| semt.017 | `semt.017.001.14`, `semt.017.002.12` |
| seev.031 | `seev.031.001.16`, `seev.031.002.15` |
| seev.035 | `seev.035.001.17`, `seev.035.002.16` |

## Completion Pass: Live ISO Download Result

Official ISO XSD acquisition was attempted through both `curl` and the repository
`mx-source-fetch` command against the official pacs.008 endpoint:

```text
https://www.iso20022.org/message/23500/download
```

The sandboxed Python command first failed on DNS. With network approval, the command
connected but timed out reading the response:

```text
source fetch failed: The read operation timed out
```

Two direct `curl` attempts to the same official endpoint, and one to the corresponding
pain.001 endpoint, also timed out with zero bytes received or receive failure. No raw XSD
file was created.

The final scaleout run therefore attempted 29 exact definitions and failed all 29 with
missing local source files. This is no longer the first-pass `14 missing-source` collapse;
it is a precise exact-definition failure caused by official source bytes being unavailable
to this execution environment.

## Real Failure Matrix

| Exact Message ID | Family | Source acquired | Safe load | Compiled | Registry | Sample | Source-XSD | Parse | Round trip | Unsupported constructs | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pacs.008.001.14 | pacs | FAIL | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | not observed | missing source; live ISO endpoint timed out |
| pacs.009.001.13 | pacs | FAIL | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | not observed | missing source |
| pain.001.001.13 | pain | FAIL | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | not observed | missing source; live ISO endpoint timed out |
| pain.002.001.15 | pain | FAIL | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | not observed | missing source |
| camt.052.001.14 | camt | FAIL | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | not observed | missing source |
| camt.053.001.14 | camt | FAIL | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | not observed | missing source |
| camt.054.001.14 | camt | FAIL | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | not observed | missing source |
| sese/semt/seev current exact definitions | mixed | FAIL | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | not observed | 22 exact source files missing after live acquisition timeout |

## Reconciliation Status

No existing installed MX pack was promoted. Exact-source reconciliation requires raw XSD
bytes and compiled candidates for the exact namespace/version being compared.

| Installed pack | Current official definitions observed | Reconciliation |
| --- | --- | --- |
| `sese.020.001.08` | `sese.020.001.09`, `sese.020.002.07` | UNVERIFIED; installed version differs and no source bytes were acquired. |
| `sese.027.001.08` | `sese.027.001.09`, `sese.027.002.07` | UNVERIFIED; installed version differs and no source bytes were acquired. |
| `sese.030.001.10` | `sese.030.001.10`, `sese.030.002.09` | UNVERIFIED; exact current `.001.10` candidate could not be compiled without source bytes. |
| `sese.031.001.09` | `sese.031.001.11`, `sese.031.002.09` | UNVERIFIED; installed version differs and no source bytes were acquired. |

No standards-version structural diff was performed because both source versions must be
downloaded and compiled first.

## PASS 3: Message-Set Bundle Acquisition

This continuation added official ISO message-set bundle acquisition without weakening
source authority or redistribution controls.

Observed ISO catalogue message-set links were added to
`backend/config/mx/xsd/sources/catalogue-snapshot-2026-08-20.yaml` for:

| Message set | Download URL | Families covered in snapshot |
| --- | --- | --- |
| Payments Clearing and Settlement | `https://www.iso20022.org/message-set/1249/download` | `pacs` |
| Payments Initiation | `https://www.iso20022.org/message-set/1250/download` | `pain` |
| Bank-to-Customer Cash Management | `https://www.iso20022.org/message-set/1246/download` | `camt` |
| Settlement and Reconciliation | `https://www.iso20022.org/message-set/1245/download` | `sese`, `semt` |
| Settlement and Reconciliation Variant 002 - ISO 15022 Variants | `https://www.iso20022.org/message-set/1124/download` | `sese`, `semt` |
| Corporate Actions | `https://www.iso20022.org/message-set/1241/download` | `seev` |
| Corporate Actions Variant 002 - ISO 15022 Variants | `https://www.iso20022.org/message-set/1201/download` | `seev` |

The new acquisition order is:

1. already-present local exact XSD;
2. already-acquired local message-set bundle;
3. official message-set download;
4. official individual-XSD fallback;
5. operator-supplied source required.

The live verifier target `make verify-real-iso-sources` runs with `--bundle-only` so the
Phase 3B evidence stays focused on message-set acquisition and does not spend excessive
time on 29 individual fallbacks when every bundle request has already timed out.

Safe ZIP handling rejects:

- non-HTTPS or non-ISO redirects/final URLs;
- oversized archives, too many files, oversized members and excessive total expansion;
- suspicious compression ratios;
- path traversal, absolute paths, Windows drive paths and destination-root escapes;
- symlinks, non-regular entries, nested archives and duplicate filenames;
- `.xsd` candidates that are binary, HTML, DOCTYPE-bearing, not `xs:schema`, or whose
  filename message ID disagrees with `targetNamespace`.

The local bundle index records exact message ID, target namespace, XSD filename, source
checksum, bundle checksum, message set, authority and redistribution status. It stores no
raw source content. Validated XSDs are materialised as exact `<messageDefinition>.xsd`
files only inside the ignored source cache.

### PASS 3 Live Result

`make verify-real-iso-sources OUT=build/mx-real-sources/acquired-manifest.yaml` was run
outside the sandbox after the sandboxed attempt failed DNS resolution. All seven observed
official message-set downloads timed out before archive bytes reached the tool:

| Metric | Result |
| --- | --- |
| Message-set bundles attempted | 7 |
| Message-set bundles downloaded | 0 |
| Message-set bundle failures | 7 |
| Raw XSDs discovered from bundles | 0 |
| Exact manifest definitions resolved from bundles | 0 |
| Real schemas safe-loaded | 0 |
| Compiled | 0 |
| Registry passed | 0 |
| Samples generated | 0 |
| Source-XSD validated | 0 |
| Parsed | 0 |
| Round-tripped | 0 |
| Excel | 0 |
| API | 0 |
| Exact all-gate passes | none |
| Exact failures | all 29 exact definitions, category `ACQUISITION` |
| Generic compiler defects found from real XSDs | 0 |
| Generic compiler fixes | none; no real XSD reached the compiler |
| Raw ISO artifacts committed | NO |
| Generated candidate packs committed | NO; no candidates were produced and redistribution remains `UNKNOWN` |

`make mx-scaleout` against the bundle-only acquired manifest attempted all 29 exact
definitions and failed each with missing local source. No browser, API or Excel real-XSD
proof was possible without legitimate source bytes.

`git check-ignore -v` proved the live cache and representative raw-source paths are
ignored:

```text
.gitignore:36:build/mx-real-sources/ build/mx-real-sources/acquired-manifest.yaml
.gitignore:36:build/mx-real-sources/ build/mx-real-sources/scaleout-report.md
.gitignore:33:backend/config/mx/xsd/sources/* backend/config/mx/xsd/sources/example.xsd
.gitignore:33:backend/config/mx/xsd/sources/* backend/config/mx/xsd/sources/bundles/example.zip
```

## What Changed Our Confidence

The first pass proved the synthetic compiler path and the source-management architecture.
This completion pass increased confidence in source acquisition safety and exact-version
metadata semantics:

- octet-stream XSD behavior is now covered by explicit security checks;
- redirect and namespace mismatches are rejected before writing files;
- checksums are captured at acquisition time;
- the manifest no longer collapses parallel current ISO definitions;
- scaleout failures are isolated at exact message-definition granularity.

It did not increase confidence in real ISO-schema compiler coverage because no official
XSD bytes were successfully acquired in this environment.

## CI Action Audit

Official GitHub release metadata showed:

- `actions/checkout@v7.0.1`;
- `actions/setup-node@v7.0.0`;
- `actions/setup-python@v7.0.0`.

The workflow now uses those current majors. `setup-node` v5+ can auto-cache package
managers, so Clean Clone explicitly sets `package-manager-cache: false`; jobs that already
used npm or pip caching keep explicit cache inputs.

## Tests Added

`backend/tests/spec_engine/test_source_scaleout.py` covers:

- ISO catalogue HTML parsing;
- logical-to-all-current-exact definition resolution;
- default `UNKNOWN` redistribution;
- remote URL allow-listing to `iso20022.org`;
- octet-stream XSD acceptance only after safe XML and namespace validation;
- binary, HTML, cross-domain redirect, HTTP downgrade, checksum mismatch and oversized
  body rejection;
- manifest acquisition and checksum recording with mocked official responses;
- official message-set link parsing;
- safe message-set ZIP indexing and materialisation;
- path traversal, absolute path, Windows drive path, symlink, oversized member,
  excessive file count, zip-bomb ratio, nested archive, duplicate entry, bad XSD binary,
  HTML renamed as XSD, DOCTYPE and filename/namespace mismatch rejection;
- bundle-first acquisition deduplication proving 29 exact definitions do not trigger 29
  bundle downloads;
- bundle-only live verification mode that skips individual fallback;
- batch success/failure isolation;
- Phase 3 business-area mapping.

`docs/generated/xsd-compiler-compatibility.md` is generated and gated by `make check`.

## Post-Change Verification

- Focused spec-engine source tests: 35 passed.
- `make check`: pass.
- Backend tests: 1309 passed, 23 skipped, 1 deselected.
- mypy strict source count: 175 files.
- Playwright: 80 passed in CI-mode local run. A first local run using
  `reuseExistingServer` was interrupted after the reused backend became unreachable;
  the clean CI-mode rerun passed.
- `make secret-scan`: pass.
- `make coverage`: current.
- `make demo-pack-check`: current.
- `make xsd-compatibility`: current.
- `docker compose config --quiet`: pass.
- `git diff --check`: clean.
- `docker compose build`: pass. An earlier post-change rerun failed twice while loading
  Docker Hub metadata for `python:3.13-slim` with `DeadlineExceeded`; the final retry
  succeeded without changing base images.

## Acceptance Status

| Question | Answer |
| --- | --- |
| Phase 3 foundation | `PHASE_3_FOUNDATION_COMPLETE` |
| Real ISO schema proof | Not complete; official XSD byte acquisition timed out. |
| Representative scaleout | Not complete; 29 exact definitions attempted but no source bytes were present. |
| Partial real-schema support | `PARTIAL_REAL_SCHEMA_SUPPORT` for acquisition tooling and metadata semantics only. |
| Official ISO XSDs downloaded | 0 |
| Safely parsed | 0 |
| Compiled | 0 |
| Generated samples | 0 |
| Samples passed exact source XSD | 0 |
| Parsed back | 0 |
| Round-tripped | 0 |
| Exact IDs passed | none |
| Exact IDs failed | all 29 in the updated manifest, each due missing local source after ISO download timeout |
| Generic compiler changes required by real XSDs | none identified; no real source bytes reached the compiler |
| Raw ISO sources committed | no |
| Generated real packs committed | no; derived metadata redistribution remains `UNKNOWN` and no candidates were produced |
| `sese.020/027/030/031` reconciled | no; exact source bytes were not acquired |
| Standards-version diff performed | no; both source versions must be downloaded and compiled first |
| MT functionality | green through `make check` and Playwright |
| Rule Packs | unchanged; no structural proof promoted business rules |
| Docker | final `docker compose build` passed |

## Remaining Operator Step

To compile real ISO 20022 packs, an operator must place legitimately obtained XSD files
matching the manifest `sourceLocation` values into `backend/config/mx/xsd/sources/` or a
configured external source directory. Only then can the six-gate source-XSD proof run
against exact source bytes and produce candidate packs for review.
