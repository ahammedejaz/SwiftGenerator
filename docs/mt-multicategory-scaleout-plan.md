# MT multicategory scale-out plan

Phase 4B widens the Prowide-derived MT structural evidence importer from Category 5 to
all MT source model classes actually present in the pinned Prowide Core release. It remains
an offline, build-time evidence path. It does not install new MT messages, does not rewrite
runtime specifications, and does not claim Swift certification or ISO 15022 conformance.

## 1. Executive objective

Determine how far generic structural onboarding can go across the MT universe before
authorised semantic evidence is required. The output is deterministic source evidence,
reports, reconciliation metrics and authoring-readiness blockers, not runtime message
support.

## 2. Phase 4 merged baseline

Phase 4 PR #12 was squash-merged into `main` at
`a6e22b9bdf1d74cc397383ada6db17a4c0786d9b`. Post-merge CI passed on that SHA. Phase 4B
starts from the same SHA on `feat/mt-prowide-multicategory-scaleout`.

## 3. Current extractor architecture

The Phase 4 importer already has the right boundaries: pinned source lock, ignored build
cache, source-jar parser, Java reflection probe, committed JSON fixture, generated reports,
and an offline verification target. The category restriction is localized to source-path
filtering, extraction naming, default fixture paths and report copy.

## 4. Why Category 5-only evidence is insufficient

Category 5 proves the architecture against securities messages only. It does not prove the
source parser handles service messages, payments, treasury, collections, documentary
credits, traveller cheques or cash/reporting classes. Phase 4B must exercise the actual
source shapes across categories and report where the generic importer stops.

## 5. Selected pinned source

Keep `com.prowidesoftware:pw-swift-core:SRU2025-10.3.18` from
`backend/config/mt_prowide_sru2025_10_3_18.lock.yaml`. Do not update to a newer artifact in
this branch unless checksum or reproducibility evidence proves the current same-release
pin unusable.

## 6. Release identity

The lock represents `SR2025`, verified on `2026-08-20`. SR2026 remains future/test evidence
until the repository's documented live-release procedure says otherwise.

## 7. Category discovery strategy

Discover categories by scanning the pinned source jar for
`com/prowidesoftware/swift/model/mt/mtNxx/MT*.java`. Do not start from a typed category
list. Observed categories include `0` through `9`; Category 0 is retained as source
evidence because it is present in the artifact.

## 8. Message class discovery

Record every source class path, package, class name and message identity. Preserve variants
such as `MT102_STP`, `MT103_REMIT` and `MT103_STP` as distinct source models instead of
collapsing them into their numeric base.

## 9. Sequence extraction

Continue parsing generated Prowide source schemes. Generalise sequence paths beyond
Category 5 assumptions, including paths that begin with `_`. Sequence delimiter codes from
`START_END_16RS` are structural evidence only.

## 10. Fieldset extraction

Keep fieldsets as message-level structural evidence. Generalise field numbers beyond
two-digit Category 5 tags when the source uses service-message fields.

## 11. Field-group extraction

Accept options including `NONE` where Prowide uses it to express an unlettered option in a
source scheme. Keep `NONE` as structural option evidence, not as a qualifier or semantic
code.

## 12. Global field-definition extraction

Reflect global field classes only for tags observed in message field groups. Store parser
patterns, validator patterns and components as global evidence. A reflected class still
does not establish message permission, requiredness or qualifier legality.

## 13. Generic category abstraction

Category is metadata on a source model. There must not be per-category extractors. The
pipeline is source jar -> discovered source model -> generic scheme parser -> fixture.

## 14. Canonical MT IR

The committed fixture remains the canonical MT structural evidence IR. Add category,
source-model identity and authoring status fields without making runtime registries read
candidate structures.

## 15. Candidate Structure Pack strategy

Candidate structures stay in the fixture and generated reports only. If build candidates
are produced, they remain under ignored `build/mt-prowide-candidates/`.

## 16. Message-level field-use model

Message field groups describe observed placement within a message scheme. They are separate
from global fields and from reviewed runtime rows.

## 17. Global-field model

Global field definitions remain keyed by tag/class evidence. They can support syntax
investigation but cannot produce message-specific dropdowns, required fields or
authoring-ready claims.

## 18. Requiredness limits

Prowide scheme `(M)/(O)` is recorded as observed source presence. It is not promoted to
runtime requiredness and is not enough for authoring readiness without authorised
message-specific review.

## 19. Cardinality limits

Only directly observed repeatability is captured. Unknown or unrepresented cardinality
stays `UNKNOWN`; do not fabricate `0..1`, `1..1`, `0..n` or `1..n`.

## 20. Qualifier limits

Qualifier constants or value patterns from global field classes are
`GLOBAL_CONSTANT_OBSERVED` at most. Message-context qualifier legality remains `UNKNOWN`.

## 21. Code-list limits

Prowide constants must not become UI dropdowns. Code-list coverage for generic candidates
is `UNKNOWN` or `GLOBAL_ONLY` until authorised message-context evidence exists.

## 22. Source provenance

Every fixture and report carries the source name, coordinate, version, SRU, release,
checksums and source class path. No raw licensed Swift artifacts are committed.

## 23. Candidate lifecycle

Use explicit structural states: `SOURCE_DISCOVERED`, `STRUCTURE_EXTRACTED`,
`STRUCTURE_COMPILED`, `CROSS_ENGINE_PARSED`, `ROUNDTRIP_VERIFIED`, `AUTHORING_READY`,
`INSTALLED`. Phase 4B should normally stop at `STRUCTURE_EXTRACTED` or a limited parser
proof, with zero installed candidates.

## 24. Authoring-readiness model

For each candidate report discovered model, sequence evidence, field-use evidence, global
syntax evidence, requiredness evidence, qualifier evidence, option evidence, sample
availability, parser feasibility, round trip, business-rule evidence and final status.
`AUTHORING_READY` requires more than class existence.

## 25. Cross-engine parsing

Keep MT541 as the configured control. Add source-safe representative controls only where
the repository can generate a FIN message or where deterministic structural evidence is
sufficient. Report `NOT_RUN` or a blocker instead of inventing messages.

## 26. Round-trip testing

Repository-configured MTs continue using the existing Python compose/import round trip.
Prowide parse success is a parser proof, not validation. Generic candidates do not gain
round-trip status without installed runtime specifications.

## 27. Existing-control reconciliation

Compare the existing 16 configured MTs against the widened fixture. Report structural
matches and differences; do not apply differences automatically.

## 28. New-category representatives

Investigate representative source models from categories actually present. Prefer common
classes such as MT103, MT202, MT300, MT320, MT400, MT700, MT707, MT760, MT900, MT910,
MT940, MT942 and MT950 when present, plus variants and difficult shapes found by source
discovery. Do not fabricate absent support.

## 29. Coverage metrics

Report total source models, per-category counts, extracted structures, candidate-only
models, configured overlap, structure-compilable counts, cross-engine attempts/passes,
authoring-ready counts and blockers.

## 30. Failure taxonomy

Classify extraction and comparison issues as `COMPARISON_LIMITATION`,
`SOURCE_MODEL_DIFFERENCE`, `REPOSITORY_CONFIGURATION_DIFFERENCE`,
`OPTION_MAPPING_DIFFERENCE`, `SEQUENCE_DELIMITER_MATCHING_LIMITATION`, or `UNKNOWN`.

## 31. Performance

Measure source verification, all-category discovery, extraction, global reflection,
fixture generation, report generation, configured diff and parser proof. Normal FastAPI
runtime cost remains zero.

## 32. Security

Keep pinned artifact URLs, checksum verification, ignored caches, no jar upload API, no
runtime reflection from user input, no arbitrary class-name endpoint and no Maven
credentials.

## 33. Runtime isolation

FastAPI generation, import, Excel and API paths must require no Java, JVM, Maven, Gradle or
Prowide. Runtime packages must not import `app.spec_engine.mt_prowide`.

## 34. CI

`make check` should validate committed fixtures and reports without network or Java. The
dedicated `MT Prowide Source` job may reproduce the source extraction with Java and pinned
downloads.

## 35. Browser impact

Phase 4B should not alter the normal tester UI except updated documentation/coverage text.
Candidate messages must not appear in Create Message.

## 36. Phase 5 canonical-reference seam

Expose stable references for future authorised rule packs:
`sourceRelease`, `messageType`, `sourceModel`, `sequencePath`, `sequenceOccurrence`, `tag`,
`option`, `qualifier` and `component`. Add resolver tests before any Phase 5 importer uses
them.

## 37. Acceptance criteria

All source categories in the pinned artifact are discovered. Structures are extracted
deterministically or blockers are reported. Variants remain distinct. The 16 configured
MTs remain the only active runtime MTs. Generated reports are current. `make check`,
`make verify-prowide-mt-source`, browser checks and CI pass. The final PR is not merged.

## 38. Known limitations

This phase still lacks authorised message-specific semantic source material. It therefore
does not prove qualifier legality, code-list legality, market practice, network rules,
business-rule completeness, Swift certification or ISO 15022 completeness.

## Self-review corrections

- Categories are discovered from source paths, not hardcoded.
- Class existence is reported as source discovery, not message support.
- Global `FieldNN` definitions stay separate from message field use.
- Requiredness, qualifier legality, sequence cardinality and code-list legality are not
  inferred into runtime behavior.
- Candidate structures stay inert and out of the runtime catalogue.
- Phase 5 is not started; the branch only creates addressing seams for authorised sources.
- Normal runtime must still work without Java/Prowide, and tests must enforce that.
