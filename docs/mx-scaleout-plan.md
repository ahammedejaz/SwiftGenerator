# MX Real Schema Scale-Out Plan

Phase 3 proves that real, legitimately obtained ISO 20022 structure can move through the
existing specification engine without message-specific application code. It does not claim
complete ISO 20022 compliance, CBPR+, MyStandards support, or business-rule coverage.

## 1. Executive Objective

Compile operator-approved ISO 20022 message XSDs into ordinary MX Specification Packs, run
them through the existing registry, sample, composer, source-XSD, parser, Excel, API,
Intelligence and coverage paths, and report exactly what was structurally verified.

## 2. Current Architecture

The platform already treats a message as specification plus values. MX specifications are
YAML trees in `backend/config/mx/`, loaded by `MxRegistry`, projected into catalogue/API/UI
metadata, and consumed by the generic MX generator/parser/XSD validator. The running app
does not compile schemas.

## 3. Current MX Catalogue

Baseline on `main` SHA `39b2e9bce63120e24fe6fd2267833b606bd63136`:

- Configured messages: 23 total, 16 MT and 7 MX.
- Configured rows/elements: 309.
- MX definitions installed: `sese.020.001.08`, `sese.023.001.11`,
  `sese.024.001.13`, `sese.025.001.12`, `sese.027.001.08`,
  `sese.030.001.10`, `sese.031.001.09`.
- Official ISO 20022 schemas present locally: 0 of 7.
- Production-capable messages: 0.

## 4. Existing Hand-Authored MX Definitions

All installed MX packs are configured subsets. `sese.020`, `sese.027`, `sese.030` and
`sese.031` also carry explicit `UNVERIFIED` limitations because their versions, roots and
element sets have not been reconciled against authoritative message-definition reports.
Phase 3 must compile official candidates separately and compare; it must not silently
replace these packs.

## 5. Existing Compiled-Specification Path

`make spec-compile SOURCE=...` calls `app.spec_engine`: safe XSD loader, IR reader, mapper,
deterministic emitter and six gates. The output is the same YAML format loaded by the
runtime. The compiler already records source checksum and compiler version.

## 6. Official ISO 20022 Source Model

The ISO 20022 catalogue is the authoritative discovery surface for current message IDs,
message-set documentation, XSD downloads, examples and BAH material. Operator-supplied
local artifacts and previously reviewed local bundles are also acceptable structural
inputs. Random mirrors, tutorials and generated third-party schemas are not.

## 7. Source Acquisition Policy

Source acquisition is offline/developer-time only. The production runtime consumes only
reviewed Specification Packs. Fetching must be constrained to `iso20022.org` and local
drop directories. Raw source bodies default to gitignored storage.

## 8. Version-Resolution Policy

Logical IDs such as `pacs.008` are resolved from the live ISO catalogue or a recorded
operator manifest at execution time. The manifest records both logical ID and exact
message definition, for example `pacs.008` and `pacs.008.001.14`, plus `CURRENT` or
`ARCHIVED`. No exact "latest" version may be hardcoded from memory.

## 9. Message-Set Metadata Model

Each message set records source URL, title, business area, last-updated date where
discoverable, downloadable artifact references, MDR/MUG references where discoverable,
and redistribution declarations.

## 10. Message-Definition Metadata Model

Each message definition records logical message, exact message definition, message name,
family, business area, submitting organisation, catalogue state, XSD source URL when
available, checksum after acquisition, source type, authority declaration and
redistribution status.

## 11. Standards-Release Identity

A compiled real-world pack must answer: which definition, version, catalogue state, source
URL, exact source bytes, compiler version, and observed-current status. Retrieval time is
kept in manifest/report metadata, not deterministic pack content.

## 12. Source Bundle Layout

Use an ignored directory such as `backend/config/mx/xsd/sources/`. A bundle may contain
downloaded/operator-supplied XSDs, imports/includes, and a manifest. Committed generated
packs must never embed raw source bodies.

## 13. Source Manifest

The manifest may be committed when it contains safe metadata only: URL, logical ID, exact
version, checksum, source type, source location and redistribution declaration. Unknown
licensing remains `UNKNOWN` and means raw source is not committed.

## 14. XSD Dependency Resolution

All includes/imports must resolve inside the declared bundle root. Network schema
locations remain blocked by the safe loader. Missing or escaped dependencies fail with
structured diagnostics.

## 15. BAH Handling

Document definitions and BAH definitions are separate structural concerns. BAH versions
must be resolved from the catalogue/operator manifest and not forced globally. AppHdr
`MsgDefIdr` must match the selected Document definition where an AppHdr is used.

## 16. Message Version Selection

Selection is explicit. A logical alias may point to a preferred current version, but the
exact message definition ID is the primary identity for compilation, diffing and review.

## 17. Current vs Archived Message Versions

The manifest distinguishes `CURRENT` and `ARCHIVED`. A newer catalogue version does not
replace an installed pack automatically. Current and archived versions must be able to
coexist as candidates.

## 18. Structural Compilation

Every candidate follows: source XSD, safe loader, IR, existing compiler, ordinary
Specification Pack, ordinary private registry, then gates. No `pacs`/`pain`/`camt`/`semt`
or `seev` generator is added.

## 19. Compiler Compatibility Matrix

`docs/generated/xsd-compiler-compatibility.md` records supported, limited, unsupported and
not-seen XSD constructs, with diagnostic codes and tests. It is a construct matrix, not an
ISO coverage percentage.

## 20. Structural Verification Gates

The six mandatory gates are safe source load, compile, registry load, deterministic sample
compose, source-XSD validation and round trip. Additional checks may report warnings, but a
candidate is not installable unless mandatory gates pass.

## 21. Source-XSD Validation

Generated XML must validate against the exact source XSD bytes identified by checksum.
Broken variants must be rejected where derivable: missing required element, wrong order,
bad enum, bad datatype, excessive occurrence and invalid pattern.

## 22. Samples

Samples are deterministic and datatype-aware. They use schema-derived examples,
enumeration values, fixed dates and synthetic IDs. LLM-generated XML is never structural
proof.

## 23. Round Trip

`Compose(values) -> XML -> Parse -> Canonical -> Compose` must be canonically identical.
Formatting differences are ignored; semantic differences fail the candidate.

## 24. AppHdr Compatibility

AppHdr remains profile/envelope configuration. The compiler does not invent transport
wrappers. Where a profile emits AppHdr, its message definition identifier must match the
Document namespace/version.

## 25. SupplementaryData

Unsupported open content such as `xs:any` remains explicit. If `SupplementaryData` cannot
be represented honestly, the pack records a limitation or the compiler fails rather than
flattening it.

## 26. Choice Handling

Choice containers are preserved as choices. Branches are not individually mandatory. Gates
must prove a deterministic branch sample and parser recovery.

## 27. Deep Nesting

Depth is capped by compiler recursion controls. Real schemas that exceed the cap fail with
diagnostics until the generic model is extended.

## 28. Repetition

Unbounded occurrences compile to the established authoring ceiling with a visible
limitation. Nested repeat parsing remains a known risk; if real schemas hit it, generation
may remain supported while import is honestly refused until a hierarchical occurrence
address is implemented.

## 29. External Code-Set References

Closed XSD enumerations are structure. External code sets, client restrictions and market
restrictions are not inferred from string patterns. A future code-set ingestion seam may be
added, but Phase 3 does not fabricate external vocabularies.

## 30. Unsupported Constructs

Unsupported XSD constructs must emit `XSD_UNSUPPORTED_CONSTRUCT` or a more specific code.
Manual per-message YAML workarounds are forbidden.

## 31. Failure Isolation

Batch compilation records successes and failures per message. One bad candidate cannot
stop other independent candidates. A malformed committed installed pack still fails
startup loudly.

## 32. Registry Installation

Candidate packs are written outside installed configuration unless explicitly directed.
They become installed only through review and source control, or through an operator-owned
`MX_SPECIFICATION_DIRECTORY`.

## 33. UI Onboarding

Installed packs appear through the existing catalogue. Candidate and available-source
records must not flood the Create dropdown.

## 34. Guided/Expert Behaviour

Expert Mode can expose the full tree. Guided Mode groups by structural parent, shows
mandatory fields first, hides optional branches initially and clearly identifies unreviewed
business explanation.

## 35. Excel Behaviour

Excel templates derive from the specification projection. Reference rows include version,
XPath, datatype, cardinality, allowed values, repeatability and provenance where available.

## 36. API Behaviour

`POST /api/v1/messages/generate` works for installed Phase 3 messages without endpoint
changes. Catalogue/specification APIs expose additive identity and provenance fields.

## 37. Intelligence Behaviour

Message Intelligence exposes deterministic structure facts: version, namespace, XPath,
parent/children, datatype, cardinality, choices, restrictions, provenance and reviewed
rules. It does not manufacture business explanations.

## 38. Coverage Behaviour

Coverage reports installed MX definitions, exact version, source type/checksum, structure
status, XSD gate, round trip, parser, sample, Excel, API, UI, Intelligence and rule
dimensions. Counts are reported as installed and structurally verified; no ISO percentage
is used without a defensible catalogue denominator.

## 39. Capability Behaviour

Structure compiled from a schema may move to `COMPILED_FROM_SCHEMA`; business rules,
market practice, client profile and external validation remain separate dimensions.

## 40. Rule-Engine Interaction

No reviewed Rule Pack is created by structural compilation. Newly compiled real messages
show `businessRules: NOT_CONFIGURED`, `marketPractice: NOT_CONFIGURED`,
`clientProfile: NOT_CONFIGURED` and `externalValidation: NOT_RUN` unless reviewed packs
already target that exact structure checksum.

## 41. Business-Rule Honesty

XSD success is structural only. MDR/MUG discovery is recorded for later Phase 2 extraction,
not automatically ingested or activated.

## 42. Licensing / Redistribution

Downloadable does not mean redistributable. Each source records access source, authority
declaration, redistribution status and whether raw source or derived metadata may be
committed. Defaults are `UNKNOWN` and raw source remains uncommitted.

## 43. Generated-Pack Redistribution

Generated packs are derived metadata. Committing them requires an operator decision that
derived metadata redistribution is permitted. The tool records the declaration; it does
not make legal conclusions.

## 44. Upgrade/Diff Pipeline

Use `spec-diff` for exact version-to-version structural diffs. Upgrade reports list
namespace, added/removed elements, cardinality, datatype, enum and choice differences.
No user migration is automatic.

## 45. Archive Support

Archived message definitions are compileable candidates when legitimate artifacts are
available. They remain separate exact-version packs.

## 46. Performance

Compilation is build-time. Measure registry startup, catalogue response, Intelligence,
Excel template, generation, parsing and XSD validation as installed packs scale to 25, 50
and 100 where legitimate sources are available.

## 47. CI Strategy

CI continues to run deterministic tests and synthetic fixtures. Live source discovery and
licensed-source compilation are developer/operator tasks unless safe metadata-only
snapshots are checked in.

## 48. Batch Onboarding Strategy

Start with 12 to 18 current definitions across `pacs`, `pain`, `camt`, `sese`, `semt` and
`seev`, selected from the official catalogue for structural diversity. Then run a larger
batch to find generic compiler assumptions.

## 49. Rollback

Generated candidates are isolated from installed packs. Removing a candidate output
directory rolls back the compile attempt. Installed pack rollback remains ordinary source
control rollback.

## 50. Acceptance Criteria

Acceptance requires official/operator source resolution, safe acquisition metadata,
successful batch compile where artifacts are available, six-gate reports, structural diffs
against existing hand-authored packs where applicable, updated compatibility and coverage
reports, browser/API/Excel proof for installed candidates, and green CI-equivalent checks.

## 51. Phase 4 Prerequisites

Phase 4 used the same exact-version identity, manifest checksums, version coexistence,
candidate reports, source-diff reports and honest separation of structure from business
rules for the Prowide-derived MT structure importer.

## Self-Review Corrections

- Public ISO catalogue access is source authority for discovery, not redistribution
  permission.
- Unknown redistribution means raw source must not be committed.
- XSD gates are not business-rule verification.
- Exact current versions are resolved from the catalogue or manifest at execution time.
- Standards releases are identified by exact definition and checksum, not by "latest".
- Two versions may coexist because exact message definition is primary.
- URL changes and byte changes are detected by source checksum.
- Batch compilation isolates failures per candidate.
- Unsupported constructs are not silently flattened.
- Existing hand-authored definitions are compared, not overwritten.
- New installed messages use existing UI, Excel, API, parser, composer and Intelligence
  paths.
- Samples are deterministic and synthetic.
- AppHdr and Document are separate structural concerns.
- External code sets are not confused with XSD enumerations.
- Rule Packs do not promote because a Structure Pack improved.
- Users must be able to see which gates passed against which source checksum.
- This plan does not start CBPR+, MyStandards, a rule-extraction expansion or the
  Specification Factory.
