# MT structure importer plan

Phase 4 adds an offline MT structure importer that reads Prowide Core as build-time
structural evidence. It does not install new runtime MT messages and it does not claim
Swift certification or ISO 15022 conformance.

## Goal

The repository already owns a reviewed configured MT subset. The importer adds a broader,
release-pinned view of Prowide MT message structure so maintainers can compare that subset
against a generic structural source before deciding what to reconcile by hand.

The importer must answer these questions without changing generation:

- Which Prowide MT source model classes exist for the pinned release?
- Which generated sequence, fieldset and field-group shapes can be observed from source?
- Which global field classes expose parser or validator patterns?
- Which configured rows line up by sequence delimiter code and tag option?
- Which Prowide-observed messages remain inert candidates?

## Non-goals

- No runtime Java, JVM, Maven, Gradle or Prowide dependency.
- No Swift certification, conformance, validation or UHB-completeness claim.
- No inference of qualifier legality, code-list legality, network validation or usage
  rules from a global Prowide field class.
- No promotion of candidate MT messages into `backend/config/specifications/`.
- No silent rewrite of the existing hand-reviewed MT subset.
- No committed raw SWIFT specification artifacts.

## Source Strategy

The pinned source lock is
`backend/config/mt_prowide_sru2025_10_3_18.lock.yaml`.

It records:

- Prowide Core artifact: `com.prowidesoftware:pw-swift-core:SRU2025-10.3.18`
- Swift release represented by the artifact: `SR2025`
- Verification date: `2026-08-20`
- Maven metadata latest observed: `SRU2025-10.3.18`
- SHA-256 and Maven SHA-1 for the Prowide jar, source jar and Java probe dependencies

As of `2026-08-20`, Swift's official Standards Release page identifies SR2026 material as
future-dated for live use on `2026-11-14`. Therefore this phase uses SR2025 as the current
live release evidence and documents SR2026 as a future/test stream.

## Implementation Stages

1. Lock the primary source and artifact checksums.
2. Download only pinned Maven artifacts into ignored `build/mt-prowide-cache/`.
3. Parse the Prowide source jar's generated MT message schemes.
4. Reflect global field classes through a small Java probe.
5. Write a deterministic JSON evidence fixture under `backend/tests/fixtures/`.
6. Generate compatibility and structure-diff reports under `docs/generated/`.
7. Add offline checks to `make check`.
8. Add live pinned-source verification to `make verify-prowide-mt-source` and a dedicated
   non-required CI job.
9. Add documentation that explains source versioning, upgrade policy and limitations.

## Acceptance Gates

- `make mt-prowide-check` must pass without network or Java.
- `make verify-prowide-mt-source` must reproduce the committed fixture from pinned
  artifacts and prove the MT541 tag stream against Prowide parsing.
- `make check` must remain runnable from a clean clone without credentials.
- The generated reports must state that candidate messages are not activated.
- The runtime package tree must not import `app.spec_engine.mt_prowide`.

## Current Result

The Phase 4B fixture contains 274 Prowide MT source model classes across categories 0-9,
1,042 observed sequences, 990 fieldsets, 9,710 field groups and 620 reflected global field
classes. Two hundred fifty-eight source models are candidates only and zero are activated.

The configured runtime set remains MT530, MT537, MT540-MT548 and MT564-MT568. The
structure diff reports that all 16 configured MT message classes exist in the Prowide
evidence, while 10 configured messages have row-placement differences when compared by
sequence delimiter code and tag option. Those differences are reported, not applied.
