# Specification Engine — Architecture Plan (Phases 0–1)

Written before implementation, self-reviewed at the end of this document, then implemented
on `feat/specification-engine-foundation`. The companion report,
[history/specification-engine-phase-01-report.md](history/specification-engine-phase-01-report.md),
records what was actually built and verified.

---

## 1. Executive objective

Turn the platform from *"a tool that supports 23 configured messages"* into a
**Financial Message Specification Engine**: message definitions onboard through
**versioned specification packs** instead of application development. This branch delivers
Phase 0 (dynamic registry + dimensional capability model) and Phase 1 (an ISO 20022
XSD → MX specification compiler), and documents the seams for Phases 2–7 without building
them.

The governing invariant is unchanged: **a message is a specification plus values.** The
engine adds a new way to *produce* specifications; it does not add a second way to render,
validate or parse a message.

## 2. Repository starting state

- Base: `main` @ `b69766a` ("Reorganise documentation", PR #8).
- Baseline verification (recorded before any change):
  - `make check` — pass (986 backend tests, ruff / mypy --strict / eslint / tsc clean)
  - `make e2e` — 72/73; `bulk.spec.ts` timed out once under full-suite load and passes
    alone (pre-existing flake, 5s `toBeVisible` timeout on the report heading)
  - `make secret-scan`, `make coverage`, `make demo-pack-check`,
    `docker compose config --quiet`, `docker compose build`, `git diff --check` — all pass

## 3. Current architecture (relevant slice)

```
config/knowledge/*.yaml ─┐
config/specifications/ ──┼─ MT: knowledge records × manifest → MessageSpecificationRegistry
config/mx/*.yaml ────────┼─ MX: one YAML tree per message   → MxRegistry
config/profiles/*.yaml ──┘
        │
   studio/catalogue.py  → format-neutral MessageSpec projection
        │
   StudioService → MtGenerator / MxGenerator → FIN / XML
        │
   samples · excel · intelligence · import · diff · coverage   (all read the projection)
```

MX is already *almost* dynamic: `MxRegistry` globs a directory, and the four lifecycle
messages were added by YAML alone. MT is not: a closed `MessageType` enum gates the studio
path in both directions.

## 4. Current hardcoded message-type dependencies (audited)

| Location | Dependency | Blocks onboarding? |
|---|---|---|
| `app/domain/enums.py` | `MessageType` — 16 members | root cause |
| `app/specifications/registry.py` | keyed by enum; **requires the manifest to cover every enum member and vice versa** | yes, both directions |
| `app/knowledge/loader.py` | `KNOWN_MESSAGE_OWNERS` — hardcoded message → module dict; unknown type refused at load | yes |
| `app/knowledge/loader.py` | `KNOWN_FIELD_SIGNATURES` — hardcoded per-message field sets, enforced in **both** directions (`_validate_coverage`) | yes — contradicts AGENTS.md §15's "add a field: no code" |
| `app/knowledge/models.py` | records parse `messageTypes: list[MessageType]` | yes |
| `app/raw/validator.py` | `HEADER_PATTERN` regex hardcodes MT numbers; `SEQUENCE_ORDER` dict per enum | yes (legacy path) |
| `app/studio/catalogue.py` | enum conversions ×3; `MT_DESCRIPTIONS` enum-keyed dict; `build_catalogue` iterates the enum | yes |
| `app/studio/{intelligence,samples,coverage}.py` | iterate / convert through the enum | yes |
| `app/studio/mt/{generator,parser}.py` | `MessageType(...)` conversions | yes |
| frontend | none — `messageType: string` throughout; remaining mentions are copy | no |

Not in scope: `app/domain/`, `app/composers/`, `app/workflows/`, `app/services/` — the
legacy scenario API is genuinely per-message code and keeps its enum. `StrEnum` members
*are* strings, so a string-keyed registry accepts legacy enum arguments unchanged.

## 5. Registry limitations being removed

The MT registry's closed-world check (`set(MessageType) - set(messages)`) makes the enum
authoritative over the manifest. After Phase 0 the **manifest is authoritative**: message
types exist because a specification pack declares them, and the knowledge loader validates
records against the manifest instead of against Python dicts.

## 6. Current MX specification format

`MxMessageSpec` (`app/studio/mx/models.py`): identity (`messageType`, `version`, `name`,
`namespace`, `messageRoot`, `documentElement`, `standardsRelease`), provenance (`source`),
honesty flags (`authoritativeCompletenessKnown`, `limitations`), configuration-expressed
rules (`requireOneOf`), and a nested `structure` of `MxElement` where document order is
element order. Leaves carry a **closed** `MxDataType` enum of 15 representation classes.

This format is *nearly* sufficient for compiled packs. Two genuine gaps (see §31):
arbitrary XSD simple types cannot be expressed by the closed enum, and provenance lacks
checksum/compiler fields. Both are fixed **additively**.

## 7. Current XSD validation architecture

`app/studio/mx/xsd.py` validates generated documents against `OFFICIAL` (a dropped
`.xsd` named `<version>.xsd`) or `SUBSET_DERIVED` (derived from the YAML at runtime),
preferring official. This is reused as-is — it is also how Phase 1's source-XSD gate runs
inside the application: point `MX_OFFICIAL_XSD_DIRECTORY` at the compiler's source schema
and the ordinary validation layer reports `OFFICIAL`.

## 8. Existing provenance model

Every MT knowledge record and MX spec carries a `source` block (`sourceType`,
`sourceReference`, review fields); overlays carry `reviewStatus`/`reviewedBy`. Phase 1
**extends this pattern** rather than inventing a second one (§16).

## 9. Existing capability model

One `CapabilityState` per MT message, always `PARTIAL`; MX has no per-message state, only
`authoritativeCompletenessKnown: false` + limitations. Coverage (`app/studio/coverage.py`)
is measured per component. Phase 0 adds dimensions *alongside* these; nothing is removed
and no message is upgraded.

## 10. Existing client/profile model

`profiles.loader` + knowledge overlays; `effective()` merges base + profile. Untouched in
this branch; §29 records how market-practice overlays will slot between them.

## 11. Proposed Specification Engine architecture

```
Standards / Schemas / Approved sources
        │  (offline, developer-run)
   app/spec_engine  — loader → IR → compiler → deterministic YAML pack
        │  (git commit, PR, CI — never runtime self-modification)
backend/config/mx/*.yaml  (or an operator-pointed directory)
        │
   MxRegistry (unchanged loading path)
        │
   catalogue · UI · Excel · API · samples · intelligence · parser · coverage
```

The compiler is a **development-time tool**. The running application only ever loads
packs that were committed (or explicitly pointed at via the existing directory settings).

## 12. Specification Pack format

A pack **is** the existing per-message YAML, extended additively. Identity =
`format : messageType : version` (e.g. `MX:sese.023.001.11`) plus `sourceChecksum` and
`compilerVersion` in provenance. Duplicate identity fails loudly (registry already
refuses duplicate message types; the compiler additionally refuses to overwrite a pack
whose recorded source checksum differs unless `--force` names the intent).

## 13. Structure Pack

The `structure:` tree plus identity/namespace — machine authority. For compiled packs
every structural fact traces to the XSD; the LLM has **zero** authority here (none is
used anywhere in Phases 0–1).

## 14. Rule Pack

`requireOneOf` and the generator business rules are today's rule layer. Phase 1 only
scaffolds the evidence fields future extracted rules need (§28); no extraction pipeline
is built.

## 15. Presentation Pack

Display names, meanings, questions, examples, mistakes, search terms — already present in
the model. For compiled packs, deterministic mechanical presentation is generated
(camelCase split + a fixed public-abbreviation table, e.g. `SttlmDt` → "Settlement
Date"); missing business prose never blocks compilation or generation, and Message
Intelligence labels it honestly ("business explanation not yet reviewed; technical
structure from the source schema").

## 16. Provenance model

`MxSource` gains optional fields (existing YAML unaffected):

```yaml
source:
  sourceType: OFFICIAL_ISO_20022_XSD | SYNTHETIC_FIXTURE_XSD | APPROVED_REPOSITORY_REVIEW…
  sourceReference: <existing>
  sourceLocation: <file name within the bundle>       # new, optional
  sourceVersion:  <schema version string>              # new, optional
  sourceChecksum: sha256:<hex>                         # new, optional
  compilerVersion: spec-engine/1                       # new, optional
  reviewStatus: NOT_REVIEWED | VERIFIED | …            # new, optional
  generated: true                                      # new, marks compiled packs
  reviewedAt / reviewedBy: <existing; compiler writes NOT_REVIEWED / SPECIFICATION_COMPILER>
```

No timestamps in pack content (determinism, §17). Checksums are computed, never
fabricated. Source XSD bytes are **not** embedded in the pack (licensing, §19).

## 17. Capability model (dimensional)

New in `app/studio/capability.py`, names adapted to repository conventions:

| Dimension | Values | Existing 23 | Compiled pack |
|---|---|---|---|
| `structure` | `CONFIGURED_SUBSET` · `COMPILED_FROM_SCHEMA` · `UNVERIFIED` | `CONFIGURED_SUBSET` | `COMPILED_FROM_SCHEMA` |
| `businessRules` | `NOT_CONFIGURED` · `CONFIGURED_SUBSET` · `SOURCE_DERIVED` · `REVIEWED` | `CONFIGURED_SUBSET` | `NOT_CONFIGURED` |
| `marketPractice` | `NOT_CONFIGURED` · `CONFIGURED` · `VERIFIED` | `NOT_CONFIGURED` | `NOT_CONFIGURED` |
| `clientProfile` | `NOT_CONFIGURED` · `CONFIGURED` · `VERIFIED` | `CONFIGURED` (measured: a profile names rules for it) | `NOT_CONFIGURED` |
| `externalValidation` | `NOT_RUN` · `PASSED` · `FAILED` | `NOT_RUN` | `NOT_RUN` |

Derived, not declared: `structure` comes from provenance (`generated: true` →
`COMPILED_FROM_SCHEMA`), `clientProfile` is measured from the profiles, the rest from what
actually exists. "Official-ness" of a schema is a provenance fact (`sourceType`), **not**
a capability claim — the tool cannot verify an operator's assertion that a file is the
official artifact, so the dimension says *compiled from a schema* and provenance says
*which* schema, by checksum. The plain-language summary (§8 of the brief) is one
deterministic sentence per message, e.g. *"Structure compiled from the supplied schema
and validated against it. Business rules not configured. Ready for structural testing
only."* The four UNVERIFIED lifecycle messages keep `CONFIGURED_SUBSET` + their explicit
limitation text; the dimension does not overwrite a sharper existing caveat. The legacy
`capability: PARTIAL` field is retained untouched for backward compatibility.

## 18. Dynamic registry design

1. **`app/specifications/manifest.py`** (new, small): parses the manifest once into a
   `ManifestIndex` — message type (string, `^MT\d{3}$`), name, scope, `shortDescription`
   (new YAML field, replaces the code dict `MT_DESCRIPTIONS`), `workflowModule` (new YAML
   field, replaces `KNOWN_MESSAGE_OWNERS`), sequences. No imports from the knowledge
   loader, which breaks today's cycle risk.
2. **Knowledge loader** validates records against the `ManifestIndex`: the message type
   must exist in the manifest, the record's module must match the manifest's, the
   record's `sequencePath` must be one of that message's sequences.
   `KNOWN_MESSAGE_OWNERS` and `KNOWN_FIELD_SIGNATURES` are deleted — they are
   configuration duplicated in code, they contradict AGENTS.md §15's "add a field: one
   YAML record, no code", and their drift-guard role is carried by the manifest check,
   the golden fixtures and the studio suite.
3. **`MessageSpecificationRegistry`** keys by string, gains `known()`; the enum
   completeness check is replaced by mutual manifest ↔ records consistency. Legacy
   callers passing `MessageType` members keep working because `StrEnum` members are
   strings.
4. **Studio registry facade** `app/studio/registry.py`: format-neutral
   `MessageDefinition` (`message_id`, `format`, `family` — `sese` for MX, `MT5xx`
   category for MT — `version`, `capability` dimensions, structure source) with
   `get / all_definitions / by_format / by_family / capabilities`. It is catalogue
   metadata only; **rendering stays MT adapter / MX adapter** and they do not merge.
5. Consumers (`catalogue`, `intelligence`, `coverage`, `samples`, `mt/generator`,
   `mt/parser`, `raw/validator` header + sequence order) derive from the registries.

## 19. MX XSD ingestion architecture / 20. compiler design

`app/spec_engine/` (new package, no imports from it in the runtime request path):

```
xsd_loader.py   safe parse + bundle resolution → {namespace: schema DOM}
ir.py           SchemaIR · ElementIR · ComplexTypeIR · SimpleTypeIR · ChoiceIR · Facets
xsd_reader.py   DOM → IR (structured diagnostics for anything unsupported)
mapper.py       IR → MxMessageSpec dict (datatypes, presentation, deterministic examples)
emit.py         spec dict → deterministic YAML text (validated by re-loading)
pipeline.py     compile(bundle) → CompiledPack{yaml, spec, diagnostics, provenance}
gates.py        pack gates: registry load · sample · compose · round-trip · source-XSD
structdiff.py   deterministic pack-to-pack structural diff
patterns.py     deterministic sample values for the XSD pattern subset ISO uses
diagnostics.py  CompilerFinding{code, severity, source, location, message, suggestion}
__main__.py     CLI: compile · validate · diff · inspect
```

## 21. Namespace/version handling

`targetNamespace` must match `urn:iso:std:iso:20022:tech:xsd:<id>.<variant>.<version>`;
`messageType`/`version` derive from it (the existing `MxMessageSpec` validator already
enforces the pairing). Anything else → `XSD_NAMESPACE_UNSUPPORTED`.

## 22. XSD include/import resolution

`schemaLocation` resolves **only** inside the explicitly passed bundle root:
`resolve()` + `is_relative_to(bundle_root)` after symlink resolution; `http(s):`
locations → `XSD_REMOTE_FETCH_BLOCKED`; missing file → `XSD_IMPORT_NOT_FOUND` naming the
namespace and location; cycles handled with a visited set; includes merge into the same
namespace, imports load sibling namespaces for type resolution.

## 23. Type resolution

Named global complex/simple types, anonymous inline types, `ref=` to global elements,
`extension` for simple content. Type recursion depth-limited (`XSD_RECURSION_LIMIT`,
depth 64). Unresolved QName → `XSD_TYPE_UNRESOLVED`.

## 24. Enumeration extraction

`xs:enumeration` facets → `dataType: Code` + `codes:` (document order preserved — the
order is part of the schema).

## 25. Choice-group handling

A complex type whose content model is a single `xs:choice` → `choice: true` on the
element. An inline `xs:choice` particle mixed among sequence siblings is not
representable in the current model → `XSD_UNSUPPORTED_CONSTRUCT` (visible, never
flattened). ISO 20022 message schemas express choices as full content models, so this
covers the target corpus.

## 26. Repetition/cardinality

`minOccurs=0` → OPTIONAL, `1` → MANDATORY, `>1` → `XSD_UNSUPPORTED_CONSTRUCT` (never
occurs in the target corpus). `maxOccurs` carries through; `unbounded` compiles to the
model's ceiling (1000) **and** records a pack limitation stating the authoring cap — an
explicit, documented bound rather than silent flattening.

## 27. Restrictions/patterns

`pattern`, `minLength`, `maxLength`, `length`, `minInclusive`, `maxInclusive`,
`totalDigits`, `fractionDigits` over bases `xs:string`, `xs:decimal`, `xs:boolean`,
`xs:date`, `xs:dateTime`. Where a simple type exactly matches an existing `MxDataType`
representation class by name, the classic member is used (keeps packs idiomatic);
otherwise the new generic `restriction:` block (§31) captures the facts verbatim.
Unsupported bases (e.g. `xs:base64Binary`) → visible diagnostic.

## 28. Attributes

Exactly one attribute shape is generatable today: simple content extension of a decimal
with a required 3-letter `Ccy` attribute → `dataType: ActiveCurrencyAndAmount`. Any other
**required** attribute → `XSD_UNSUPPORTED_CONSTRUCT` error (a valid document could not be
generated); an **optional** attribute → warning + recorded pack limitation (the subset
simply never writes it).

## 29. Supplementary-data handling

`SplmtryData` (an `xs:any`-bearing envelope in most ISO messages) is not representable —
`xs:any` → `XSD_UNSUPPORTED_CONSTRUCT` **warning** when optional (recorded limitation:
"SplmtryData is not part of the configured subset"), error when required. This mirrors
how the hand-authored subsets already treat it: absent.

## 30. AppHdr handling

Unchanged: the AppHdr is composed by `MxGenerator.compose_app_hdr` from the profile and
the pack's version string. Compiling `head.001` itself is out of scope; the bundle
resolver accepts its schema as an import target so message bundles that reference it
still load.

## 31. Existing YAML compatibility

Two **additive** model changes, both leaving every committed YAML valid:

1. `MxElement.restriction: MxRestriction | None` — base kind (`TEXT`/`DECIMAL`/`DATE`/
   `DATE_TIME`/`BOOLEAN`), the §27 facets, and the original XSD type name for display.
   Leaf rule becomes: `dataType` **or** `restriction` (or children). `validate_value`,
   `derive_schema`, input-kind derivation, samples and Excel formats honour it.
2. `MxSource` optional provenance fields (§16).

No second message-description format is introduced; the compiler emits the existing one.

## 32. Generated-file policy

Compiled packs are ordinary config files: reviewed in a PR, committed only when their
source's licence permits (§19), regenerable at any time (`sourceChecksum` says from
what). `generated: true` marks them; a `# Generated by spec-engine …` header comment
names the source file and checksum. **No compiled pack ships in this branch's product
catalogue** — synthetic fixtures exist under `backend/tests/fixtures/` and are loaded
through directory-override settings in tests only, so no fabricated "financial message"
appears in the product.

## 33. Round-trip strategy

Existing property, applied to compiled packs in tests: build the TYPICAL sample →
compose → parse → compose again → canonical XML equality (formatting-insensitive,
semantics-sensitive — the existing MX parser tests define the comparison).

## 34. XSD validation strategy

The critical gate, run two ways:
- **In the compiler** (`gates.py` / `make spec-validate`): generate a sample from the
  compiled pack, compose the Document, validate with lxml against the **source** XSD;
  also generate deliberate mutations (wrong order, missing mandatory, bad enum, bad
  datatype, cardinality overflow) and require the source schema to reject each.
- **In the application** (integration test): point `MX_OFFICIAL_XSD_DIRECTORY` at the
  source schema; the ordinary generation path then reports `schemaSource: OFFICIAL` and
  must pass. This proves the pack is valid against the source, not merely
  self-consistent with its own derived schema.

## 35. Sample-generation strategy

The compiler writes deterministic `examples` on every leaf (enum → first code; date →
fixed date; decimal → smallest facet-conforming value; string → pattern-derived via
`patterns.py`, else length-conforming synthetic; amount → `USD 1000.00`). The existing
sample builder then works unchanged — its "prefer the element's own example" rule already
does the right thing. A leaf whose pattern the deterministic sampler cannot satisfy gets
a **warning diagnostic** and no example: compilation succeeds, the sample gate fails
visibly for that message, nothing is invented.

## 36. Message Intelligence integration

Automatic once the catalogue derives from the registry: compiled packs index by element
name, path and mechanical display name. Missing business prose renders honestly (§15).

## 37. Guided/Expert UI integration

Expert mode works from structure alone. Guided mode falls back to mechanical labels +
format text; nothing blocks. The only frontend changes are additive: the capability
summary line and dimension list on the message spec surface, mirrored in
`studio-types.ts`.

## 38. Excel integration

Automatic: templates derive from the `MessageSpec` projection. The integration test
asserts a compiled pack's template contains its XPaths, requiredness and codes with no
Excel code change.

## 39. REST API integration

`GET /api/v1/catalogue`, `/messages/{type}/spec`, `/messages/{type}/samples`,
`/messages/generate|validate|import|diff` all work on compiled packs untouched. Spec and
catalogue responses gain `capability` + `capabilitySummary` (additive). No runtime
compile/upload API is added — compilation is CLI-only in Phase 1 by design (§31 of the
brief); the existing `GET /api/v1/coverage` carries the dimensional report, so no new
endpoint is needed.

## 40. Coverage integration

`coverage.py` gains the five dimensions per message (rendered as a column in the
generated document), keeps every existing measured metric, and continues to derive
message lists from the registries.

## 41. Source/provenance integration

`GET /api/v1/sources` continues to report drop points; the pack's provenance
(checksum/compiler) appears on the spec response via the extended source block.

## 42. Security implications

Untrusted-XML handling in the loader: `resolve_entities=False`, `no_network=True`,
`load_dtd=False`, explicit rejection of DOCTYPE (`XSD_DOCTYPE_FORBIDDEN` — kills XXE and
billion-laughs in one move), per-file and total size caps, file-count cap, bundle-root
containment after symlink resolution, recursion depth caps, structured errors — never a
stack trace as the interface. No execution of source content. No archive ingestion in
Phase 1 (no zip-bomb surface). Public API responses do not echo server filesystem paths.

## 43. Licensing boundaries

Official ISO 20022 artifacts (schemas, MDRs, MUGs) and market-practice guidelines
(CBPR+, HVPS+, MyStandards exports) may carry redistribution restrictions. The engine
therefore separates: **source artifact** (dropped outside git or under the operator's
responsibility; never embedded in packs), **generated structural metadata** (the pack;
commit only where redistribution of the derived description is permitted — this is the
operator's legal call, and `docs/authoritative-sources.md` says so explicitly), and
**redistribution status** (recorded in `sourceType`/`reviewStatus`). CI depends only on
synthetic fixtures. When licensing status is unknown, packs stay out of git.

## 44. Testing strategy / 45. CI strategy

New suites under `backend/tests/spec_engine/` (loader security, reader/compiler
constructs, determinism, gates, structural diff, CLI) and
`backend/tests/studio/test_capability_dimensions.py`; one subprocess integration test
proves the §42-of-the-brief property end to end (new synthetic message via env-pointed
directories, zero message-specific code edits). Everything runs inside the existing
`make check` (pytest picks the new directories up), so all five CI jobs gate it with no
workflow change. Fixtures are synthetic XSDs covering: simple message, deep nesting,
choice, repetition, enumerations, restrictions (length/decimal/pattern/date), named +
anonymous types, include, cross-namespace import, amount shape, supplementary-style
`xs:any`, and every security case.

## 46. Rollback strategy

Additive throughout: new package, new optional model fields, string-for-enum in
internals with identical JSON serialisation. Reverting the branch restores the enum
world; no migration, no data change, no API break. Golden fixtures pin MT output bytes.

## 47. Migration strategy

None required. Existing YAML loads unchanged; existing API responses keep their fields
(new ones are additive); `capability: PARTIAL` remains.

## 48. Risks

| Risk | Mitigation |
|---|---|
| Enum-to-string ripple breaks a legacy caller | `StrEnum` members are `str`; mypy `--strict` + full suite + golden files |
| Deleting `KNOWN_FIELD_SIGNATURES` weakens drift guarding | manifest-sequence validation at load + golden fixtures + studio suite pin behaviour |
| Compiler emits a pack the runtime mishandles | every pack re-loaded through `MxMessageSpec` + gates before it is called compiled |
| Determinism claim quietly broken | byte-equality test on double compile |
| A bad pack breaks startup | registry failures stay loud and name the file — same policy as today; `spec-validate` exists to catch it pre-commit |
| Unsupported XSD construct silently flattened | every construct not on the supported list produces a named diagnostic; tests assert several |

## 49. Phase-by-phase roadmap (0–7)

- **0 (this branch)** dynamic registry + dimensional capability.
- **1 (this branch)** XSD → MX compiler + gates + CLI.
- **2** rule-pack architecture + evidence-backed extraction (source paragraph → two
  independent extractions → diff → refuter → reference validation → review). Seam: the
  provenance fields of §16 and the `businessRules` dimension.
- **3** scale MX across families with legitimately available schemas.
- **4** Prowide-derived MT structural importer — gate at implementation time on verified
  project/version/SRU/licence/checksum; provenance `PROWIDE_DERIVED_STRUCTURE`, never
  `SWIFT_VERIFIED`. Phase 0's manifest-driven MT registry is its landing seam.
- **5** evidence-backed MT semantic rules (reuses 2's pipeline).
- **6** Specification Factory (request → candidate pack → gates → PR → CI → review →
  merge → catalogue). The product may show request status; an unmerged candidate is
  never generatable. The runtime never mutates its own registry.
- **7** client-supplied market-practice/MyStandards ingestion, deployment-specific.

## 50. Acceptance criteria

The brief's §52 (Phase 0, 16 items) and §53 (Phase 1, 29 items) verbatim; the report
walks both lists item by item with evidence.

---

# Plan Self-Review

**Is the architecture unnecessarily complicated?** The largest single decision — reusing
the existing MX YAML as the pack format — is what keeps it small. The compiler is ~8
focused modules; the runtime gains no new subsystem.

**Are we duplicating existing working functionality?** No new composer, parser, Excel
writer, UI or validation path. The registry facade is projection, not duplication.
Deleted code (hardcoded owners/signatures/descriptions/sequence-orders) *was* the
duplication.

**Is configuration still the source of truth?** More than before: two code-level
authorities (enum completeness, field signatures) move into the manifest.

**Can a generated specification go through exactly the same path as a hand-authored
one?** Yes — that is the §42 subprocess test, and the pack is loaded by the unchanged
`MxRegistry`.

**Can structure ever be changed by LLM enrichment?** No LLM runs in Phases 0–1 at all.
The presentation layer is mechanical; the model boundary (AGENTS.md §10) is untouched.

**Can AI-authored text accidentally become validation authority?** No text in this
branch is AI-authored; the seam for later enrichment is presentation-only fields that no
validator reads.

**Can generated files be traced to the source artifact?** `sourceChecksum` +
`sourceLocation` + `compilerVersion` + header comment.

**Can a specification be regenerated deterministically?** Byte-for-byte, asserted by
test; timestamps are excluded from pack content by design.

**Can we diff a regenerated pack against the previous version?** `spec-diff` reports
added/removed elements, cardinality, type, enum and namespace changes deterministically.

**Are licensing boundaries explicit?** §43; CI never needs a licensed artifact.

**Are capability claims honest?** Dimensions are derived/measured; "official" stays a
provenance fact, not a capability; no existing message is upgraded; the summary sentence
never says compliant/certified/production-ready.

**Can one bad XSD break all startup?** The compiler is offline; a bad *pack* fails
registry load loudly, exactly as a bad hand-written YAML does today — and
`spec-validate` exists so it is caught before commit. This matches the repository's
existing fail-loud-at-load policy rather than adding a quarantine mechanism nothing else
has.

**Are untrusted uploaded XSDs handled safely?** There is no upload — the CLI reads local
files under an explicit bundle root, with §42's parser hardening and tests.

**Are we introducing runtime self-modification?** No. Compilation is CLI-only; the
runtime reads committed/pointed configuration, as before.

**Are we accidentally building Phase 6 early?** No request persistence, no job runner,
no PR automation, no runtime compile API. Only the §16 provenance fields double as
Phase-2+ seams.

**Can another developer understand this architecture?** The engine is "a YAML generator
for the config directory that already exists", plus a registry that stops asking a
Python enum for permission. Both are one-sentence ideas; the rest is diagnostics and
tests.

**Corrections made during this review:** (1) an earlier draft had the compiler write
`ingestedAt` into packs — removed for determinism; runtime metadata stays out of pack
content. (2) An earlier draft proposed a new `structureSource:` field in packs — dropped
in favour of deriving the dimension from the existing-pattern `source.generated`, keeping
declaration and derivation from drifting apart. (3) An earlier draft added
`GET /api/v1/specifications` endpoints — dropped; the existing spec/catalogue/coverage
endpoints already carry the data, and a parallel listing surface would be the start of a
second catalogue.
