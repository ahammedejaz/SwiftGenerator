# Specification Engine — Phases 0 & 1 Implementation Report

Point-in-time record of the engagement that built the dynamic message registry, the
dimensional capability model and the ISO 20022 XSD → specification-pack compiler.
Current-state documentation lives in [../specification-engine.md](../specification-engine.md)
and [../specification-pack-format.md](../specification-pack-format.md); the programme plan
is [../specification-engine-plan.md](../specification-engine-plan.md).

Throughout this report, **proven** means a test or command shown here ran and passed;
**inferred** and **unverified** are marked as such.

---

## 1. Executive summary

The platform now onboards message definitions through **versioned specification packs**
instead of application development:

- **Phase 0.** The studio path no longer consults a closed Python enum to decide which
  MT messages exist. The specification manifest is the single authority — message list,
  owner module, catalogue description, sequences — and the knowledge loader validates
  records against it. Two code-level duplicates of configuration
  (`KNOWN_MESSAGE_OWNERS`, `KNOWN_FIELD_SIGNATURES`) were deleted. Every message now
  carries five derived **capability dimensions** beside the legacy `PARTIAL`, and no
  existing message was upgraded.
- **Phase 1.** `app/spec_engine` compiles an ISO 20022 XSD (plus its local bundle) into
  a pack in the existing `config/mx` YAML format, deterministically, through a safe
  loader → IR → mapper → emitter pipeline with structured diagnostics. Six gates prove a
  pack through the platform's own code paths, including validating a generated sample
  against the **source** schema and proving the source schema rejects deliberately
  broken variants. A subprocess integration test proves a compiled synthetic message
  drives catalogue, form projection, samples, generation (reported `OFFICIAL` against
  the source schema), Excel, Message Intelligence and import round trip with **zero
  message-specific Python or React changes**.

All 23 existing messages generate byte-identically (golden fixtures untouched). No LLM
is used anywhere in this work.

## 2. Git starting state

Clean tree on `main`; only `workPrompt.txt` untracked (the brief itself; left
untracked). Local branches from previous engagements present; none disturbed. Remote
fetch brought `main` `4dcd25a → b69766a` (PR #8 docs reorganisation) and it
fast-forwarded cleanly.

## 3. Base `main` SHA

`b69766ad6277679bd85aea9f85d64e145087725b` — "Reorganise documentation: root has only
README, rest under docs/ (#8)".

## 4. Branch

`feat/specification-engine-foundation` (fresh from that SHA; no force pushes, no history
rewrites).

## 5. Baseline verification (before any change) — all run, all recorded

| Check | Result |
|---|---|
| `make check` | pass — 986 backend tests; ruff, mypy --strict (132 files), eslint, tsc clean |
| `make e2e` | 72/73; `bulk.spec.ts` timed out once under full-suite load (5s `toBeVisible`), **passes alone** — pre-existing flake on unmodified `main`, not introduced here |
| `make secret-scan` / `make coverage` / `make demo-pack-check` | pass |
| `docker compose config --quiet` / `docker compose build` | pass |
| `git diff --check` | clean |

## 6. Audit findings (what actually blocked onboarding)

| Location | Blocker |
|---|---|
| `app/domain/enums.py` | closed 16-member `MessageType` |
| `app/specifications/registry.py` | keyed by the enum **and** required the manifest to cover every member — closed in both directions |
| `app/knowledge/loader.py` | `KNOWN_MESSAGE_OWNERS` (hardcoded owner dict) refused unknown messages at load; `KNOWN_FIELD_SIGNATURES` (~150 lines of per-message field sets, enforced both ways) made even *adding a field* a code change — contradicting AGENTS.md §15's "one YAML record, no code" |
| `app/studio/catalogue.py` | enum conversions; `MT_DESCRIPTIONS` enum-keyed dict; catalogue iterated the enum |
| `app/studio/{intelligence,samples,coverage}.py`, `mt/{generator,parser}.py` | enum conversions |
| frontend | none — `messageType: string` throughout (verified; the §52.16 property needed no frontend change) |

Legacy scenario stack (`app/domain`, `app/composers`, `app/workflows`) and
`app/raw/validator.py` keep the enum deliberately: they are per-message code for the
demonstration flows, outside the studio onboarding path. `StrEnum` members being `str`
is what makes the string-keyed registries accept legacy enum arguments unchanged.

## 7–10. Architecture before / after, Phase 0 implementation

Before: message existence was decided in four places (enum, owner dict, signature sets,
description dict). After: the manifest decides, everything else derives.

- **`app/specifications/manifest.py`** (new) — `ManifestIndex`: message type, name,
  scope, `shortDescription` (new manifest field replacing `MT_DESCRIPTIONS`),
  `workflowModule` (new manifest field replacing `KNOWN_MESSAGE_OWNERS`), sequences.
  Imports no loader, so it cannot cycle.
- **Knowledge loader** validates each record against the manifest: message exists,
  module matches, sequence exists. Deleted: `KNOWN_MESSAGE_OWNERS`,
  `KNOWN_FIELD_SIGNATURES` and the per-message signature sets. Coverage check becomes
  "every manifest message has records". Field-level drift stays guarded by the manifest
  sequence check, the golden fixtures and the studio suite.
- **`MessageSpecificationRegistry`** — string-keyed, gains `known()`; the enum
  completeness check is gone; owner and description flow from the manifest. Both the
  registry and the loader take an injectable manifest (they always index the same file
  they load).
- **Consumers** (`catalogue`, `intelligence`, `coverage`, `samples`, `mt/generator`,
  `mt/parser`, `routes`) iterate the registry and pass strings.
- **`app/studio/registry.py`** (new) — the format-neutral `MessageDefinition` projection
  (`get / all_definitions / by_format / by_family / capabilities`). Catalogue metadata
  only; MT and MX rendering paths remain separate.

Proven by `tests/specifications/test_dynamic_registry.py`: a synthetic **MT599** onboards
through a manifest entry plus one knowledge record — YAML only; duplicates, missing
owners and non-MT identifiers are refused loudly; catalogue and descriptions derive from
the registry; legacy enum callers still work.

## 11. Dynamic registry — see §7–10. ## 12. Capability model

`app/studio/capability.py`, values **derived, never declared** (the measured-coverage
principle):

| Dimension | Existing 23 | Compiled pack | Derived from |
|---|---|---|---|
| `structure` | `CONFIGURED_SUBSET` | `COMPILED_FROM_SCHEMA` | provenance `source.generated` |
| `businessRules` | `CONFIGURED_SUBSET` | `NOT_CONFIGURED` | configured cross-field rules / `requireOneOf` / businessPath annotations |
| `marketPractice` | `NOT_CONFIGURED` | `NOT_CONFIGURED` | no configured source exists yet |
| `clientProfile` | `CONFIGURED` (MT) / `NOT_CONFIGURED` (MX) | `NOT_CONFIGURED` | measured from the profiles' requirements |
| `externalValidation` | `NOT_RUN` | `NOT_RUN` | no evidence exists |

Plus one deterministic plain-language summary per message; it never says certified /
compliant / production-ready (asserted by test). Surfaced on the spec endpoint, the
catalogue, the coverage API, the generated coverage document (new table) and the Create
Message screen. The legacy `capability: PARTIAL` field is untouched. "Official-ness" of
a schema stays a **provenance fact** (`sourceType`, `sourceChecksum`) — deliberately not
a capability claim the tool cannot verify.

## 13. Structure/Rule/Presentation pack model

The pack **is** the existing MX YAML. Structure: the `structure:` tree (schema-derived
for compiled packs; LLM authority: none — no LLM runs anywhere in this branch). Rules:
`requireOneOf` + generator rules; compiled packs declare none; the evidence fields for
Phase 2 exist in provenance. Presentation: mechanical for compiled packs (camelCase +
published ISO abbreviation table, e.g. `SttlmDt` → "Settlement Date"); missing prose
never blocks anything.

## 14. Provenance

`MxSource` extended additively: `generated`, `sourceLocation` (file name, never a server
path), `sourceVersion`, `sourceChecksum` (sha256 of the exact source bytes),
`compilerVersion`, `reviewStatus`. No timestamps in pack content — determinism. Existing
YAML unaffected (all optional).

## 15. XSD loader / 16. Security controls

`app/spec_engine/xsd_loader.py`: lxml parser with `resolve_entities=False`,
`no_network=True`, `load_dtd=False`; **any DOCTYPE refused outright**
(`XSD_DOCTYPE_FORBIDDEN` — kills XXE and billion-laughs in one move); remote
schemaLocations blocked; include/import resolution confined to the explicit bundle root
after symlink resolution; 5 MB/file and 64-file caps; cyclic includes handled by a
visited set; missing dependencies name the namespace and location. Nothing from a source
artifact is executed. Proven by `tests/spec_engine/test_xsd_loader_security.py`
(9 tests: XXE/DOCTYPE, remote fetch, traversal, symlink escape, missing import, size cap,
malformed XML, non-schema XML, cycles, missing file).

## 17. Intermediate representation

`app/spec_engine/ir.py` — `SchemaIR / ElementIR / ComplexTypeIR / SimpleTypeIR /
AttributeIR / Facets`. Small by design; the reader owns lxml, the mapper owns the
repository model, and later MDR metadata can enrich the IR without either changing.

## 18. Compiler / 19. Supported constructs

`xsd_reader.py` + `mapper.py` + `emit.py` + `pipeline.py`. Supported and **tested**:
`xs:schema`/`targetNamespace`, global/inline elements, named + anonymous complex and
simple types, `ref=`, sequences, choices (as content models), `minOccurs` 0/1,
`maxOccurs` incl. `unbounded` (capped at 1000 with a recorded limitation), restrictions
with `enumeration`, `pattern`, `minLength`/`maxLength`/`length`,
`totalDigits`/`fractionDigits`, `minInclusive`/`maxInclusive` over bases
string/decimal/boolean/date/dateTime, XSD built-ins as element types, `xs:include`
(same namespace) and cross-namespace `xs:import`, and the amount shape (simpleContent
extension of decimal + required `Ccy` → `ActiveCurrencyAndAmount` +
`currencyAttribute`). Simple types matching the platform's named representation classes
map by name; everything else becomes a verbatim `restriction:` block (new additive model
support wired through validation, the derived XSD, input kinds, Excel formats and
samples).

## 20. Unsupported constructs — visible, never flattened

`xs:all`, `xs:group`, `complexContent`, union/list simple types, inline choice/sequence
particles mixed among siblings, `minOccurs > 1`, required attributes other than the
amount's `Ccy`, unsupported restriction bases → **ERROR** findings; optional attributes
and `xs:any` (supplementary data) → **WARNING** + recorded pack limitation. Each has a
named code (`XSD_UNSUPPORTED_CONSTRUCT`, `XSD_TYPE_UNRESOLVED`, `XSD_ROOT_AMBIGUOUS`,
`XSD_RECURSION_LIMIT`…) with source, location, message and suggestion — never a stack
trace. Each behaviour is pinned by a test.

## 21. Import/include behaviour — see §15; includes merge into the including namespace,
imports load sibling namespaces for type resolution, location-less imports must be
satisfied by the bundle.

## 22. Deterministic compilation

Identical source bytes + compiler version ⇒ byte-identical packs
(`test_compilation_is_deterministic_byte_for_byte`). Keys keep model order; `structure`
order is document order (semantic, never sorted); no timestamps; the emitter re-validates
its own output through `MxMessageSpec` on every emission.

## 23. Generated pack format — see [../specification-pack-format.md](../specification-pack-format.md).

## 24. XSD → pack → registry flow / 25–29. Integrations

Proven end to end by `tests/spec_engine/test_pack_integration.py`, which compiles the
synthetic fixture, drops the pack into a directory via `MX_SPECIFICATION_DIRECTORY`, the
source schema via `MX_OFFICIAL_XSD_DIRECTORY`, boots the application in a subprocess and
asserts through the ordinary `/api/v1` surface:

- catalogue lists `test.001`, generatable, `structure: COMPILED_FROM_SCHEMA`,
  `businessRules: NOT_CONFIGURED` (nothing over-claimed)
- the spec projection renders fields and the choice group (Expert UI's data source)
- samples exist (derived from the pack's schema-derived examples)
- generation succeeds and the XSD layer reports **`OFFICIAL`** — the application itself
  validated the document against the source schema through the existing drop-point
  mechanism
- the MX Excel template builds with the new message included
- Message Intelligence finds `SynthTstInstr` deterministically
- import reads the generated XML back with zero problems

**No message-specific Python or React edit exists for `test.001`** — the acceptance
property of the brief's §42.

## 30. Parser/round-trip

Gate 6 parses the composed document with the ordinary parser and recomposes; canonical
XML (c14n2) equality is required. `MxGenerator` and `parse_message` gained an optional
injected registry (defaulting to the singleton) so gates and tests can drive a candidate
pack without touching installed configuration.

## 31. Source-XSD validation

The critical gate, run both in the compiler (`gates.py`) and inside the application (the
integration test above). Broken variants — missing mandatory element, wrong element
order, invalid datatype, invalid enumeration where derivable — must be **rejected** by
the source schema, proving the gate can fail
(`test_the_source_schema_rejects_the_broken_variants`).

## 32. Synthetic compiler fixtures

`backend/tests/fixtures/xsd/test.001.001.01.xsd` (Document root, nesting, choice, enum,
amount shape, unbounded repetition, ISO-style pattern types, decimal facets, boolean,
date/dateTime) plus in-test schemas for include/import, security cases, recursion,
multiple globals, unsupported constructs.

## 33. Official schemas tested

**None were legitimately available in this environment, and none were fabricated.** This
is the honest boundary the brief demands: what is proven is **compiler feature
coverage** over synthetic ISO-style fixtures and the existing seven hand-authored
message shapes — not "N official ISO 20022 messages compiled". The pipeline's first
official artifact should be run through `make spec-compile` + `make spec-validate` by an
operator holding a licence.

## 34. Capability results

`tests/studio/test_capability_dimensions.py`: no existing message upgraded (all 23
`structure: CONFIGURED_SUBSET`, `externalValidation: NOT_RUN`); the client-profile
dimension is measured (MT `CONFIGURED`, MX `NOT_CONFIGURED` — no profile declares MX
requirements today); compiled packs read `COMPILED_FROM_SCHEMA` without touching any
other dimension; forbidden claims never appear in summaries; dimensions travel on spec,
catalogue and coverage responses; legacy `capability: PARTIAL` unchanged.

## 35. Performance (median, this machine)

| Path | Time |
|---|---|
| schema load (loader) | 0.1 ms |
| full compile (load→read→map→emit) | 10.3 ms |
| all six pack gates | 7.8 ms |
| `MxRegistry` load, 7 specs | 89.6 ms (startup, unchanged path) |
| catalogue projection | 0.3 ms |
| sample generation (sese.023 FULL) | <0.1 ms |
| XML generation incl. XSD layer | 1.0 ms |

Nothing compiles at request time; packs load as ordinary startup configuration.

## 36. Files changed / 37. Test changes

New: `app/spec_engine/` (10 modules), `app/specifications/manifest.py`,
`app/studio/capability.py`, `app/studio/registry.py`,
`tests/spec_engine/` (5 files, 50 tests), `tests/specifications/test_dynamic_registry.py`
(8), `tests/studio/test_capability_dimensions.py` (5), the XSD fixture, three docs and
this report. Modified: the registry/loader/catalogue/consumer chain, `MxSource`/
`MxElement` (additive), `MxGenerator`/`parse_message` (injectable registry;
`_business_rules` became an instance method), the manifest YAML (`workflowModule`,
`shortDescription` per message), Makefile (three `spec-*` targets),
`studio-types.ts` + `CreateMessage.tsx` (capability display), AGENTS/ARCHITECTURE/
limitations/authoritative-sources/README docs, regenerated coverage document.
Five pre-existing test files updated only where they asserted the enum type itself
(`.value` accessors, two `is MessageType.X` identity assertions, one case that tested
the deleted in-code signature list — replaced by two manifest-gate cases).

## 38. Exact test results

- Backend: **1036 passed, 23 skipped, 1 deselected** (was 986; +50 new, all listed above)
- `mypy --strict`: clean, 147 source files (was 132)
- `ruff`: clean · frontend `tsc --noEmit`: clean · `eslint`: clean
- `make check` (runs all of the above + coverage + demo-pack gates): pass
- `make e2e`: see §39
- `make secret-scan`, `make coverage`, `make demo-pack-check`,
  `docker compose config --quiet`, `docker compose build`, `git diff --check`: pass

## 39. Browser verification

`make e2e` on the branch: **73/73 passed** (baseline was 72 + one pre-existing flake) —
covering MT and MX creation, import round trips, Excel, diff, all screens, responsive
("works on a phone", "never scrolls sideways") and accessibility.

Manual pass with the compiled pack live (backend started with
`MX_SPECIFICATION_DIRECTORY`/`MX_OFFICIAL_XSD_DIRECTORY` pointing at the fixture pack):
the catalogue shows an "Other Configured Messages" area containing `test.001`; the picker
shows its compiled-from description; the Enter Data screen shows the derived capability
summary ("Structure was compiled from a source schema and validated against it. Business
rules are not configured…"), mechanical labels, restriction-derived format hints ("up to
14 digits, 3 after the separator, minimum 0"), the party-choice toggle and the
"1 of up to 1000 / Add another" repeatable block; the MINIMAL sample loads and generates
**Valid** with every layer green including Schema validation; the proof sheet renders
AppHdr + Document with `MsgDefIdr test.001.001.01`; Message Intelligence finds
`FinInstrmId` under `test.001` with honestly empty business prose. Browser console:
zero application errors (the only console entries came from a third-party browser
extension, `bis_*` attribute injection — reproduced with the extension only, absent in
the clean-profile Playwright runs).

The manual pass also caught a real defect the automated gates could not see: the
**MINIMAL sample of a compiled pack omitted a mandatory choice**, because the
validator's repair hint only searched *mandatory* leaves and choice branches are
individually optional. Fixed in `MxGenerator.validate_structure` (the hint now falls
back to the first leaf of the first branch), verified by regenerating the sample —
7 elements including `Pty/AnyBIC`, valid — and the improved hint also makes the
user-facing error actionable.

## 40. Docker result — both images build; compose config clean.

## 41. Security review — §15/§16 controls, all tested; no secrets in packs, reports or
findings (`make secret-scan` clean); public API responses carry no server paths
(`sourceLocation` is a file name).

## 42. Licensing boundaries

No licensed artifact is present, referenced, or required by CI. Packs never embed source
bytes (checksum reference only). Whether a compiled pack — a derived structural
description — may be committed is documented as the operator's licensing judgement
([../authoritative-sources.md](../authoritative-sources.md)); when unknown, keep packs
outside git via `MX_SPECIFICATION_DIRECTORY`. `--source-type` defaults are declarations,
not verifications, and are recorded as such.

## 43. Known limitations

- The compiler covers the constructs in §19; anything else is refused visibly. `xs:all`,
  substitution groups, `complexContent` extension hierarchies and non-Ccy required
  attributes are the notable absences for real-world corpora.
- The deterministic pattern sampler covers the character-class/counted-quantifier subset
  ISO uses; an underivable pattern is a warning and that leaf ships without an example.
- Nested-repeatable import (`(path, occurrence)` single index) is unchanged from before.
- The four lifecycle specs keep their UNVERIFIED caveat; dimensions do not overwrite it.
- `businessArea` for families outside the configured four lands in `OTHER` until a
  reviewer assigns one.

## 44. Technical debt

- `raw/validator.py` still hardcodes its demonstration-subset tables (deliberate — legacy
  surface, documented in §6).
- The three `studio-types.ts` mirrors remain hand-maintained (pre-existing).
- `_sample_inputs` in the gates duplicates a slice of the sample builder's choice logic;
  worth unifying if it grows.

## 45. Phase 2 prerequisites — in place

Provenance fields (`sourceChecksum`, `reviewStatus`, `extractedBy`-ready shape), the
`businessRules` dimension (`SOURCE_DERIVED`/`REVIEWED` values reserved), the overlay
merge (`effective()`) and the pack identity/diff tooling for release upgrades.

## 46. Updated roadmap — unchanged from the plan (§49): Phase 2 rule extraction next,
then MX scale-out, the Prowide-gated MT importer (verify project/version/SRU/licence at
implementation time — never from memory), the Specification Factory, client guideline
ingestion.

## 47. PR URL — RECORDED_AT_PR
## 48. Final commit SHA — RECORDED_AT_PR
## 49. CI run — RECORDED_AT_PR
## 50. CI status — RECORDED_AT_PR
