# Specification Pack Format

A pack is one YAML file describing one message — the same format `backend/config/mx/`
has always used, extended additively for compiled provenance and generic schema types.
Hand-authored and compiled packs are loaded by the same registry and drive the same
platform; the differences are provenance and how much presentation they carry.

## Identity

```yaml
messageType: sese.023            # family.number — how callers address it
version: sese.023.001.11         # full versioned identity; also the pack's file name
namespace: urn:iso:std:iso:20022:tech:xsd:sese.023.001.11
messageRoot: SctiesSttlmTxInstr
documentElement: Document
```

The namespace must equal `urn:iso:std:iso:20022:tech:xsd:<version>` — the model refuses
anything else, and duplicate message types are refused at registry load. Two different
structures can never silently share an identity.

## Provenance (`source`)

```yaml
source:
  sourceType: OFFICIAL_ISO_20022_XSD      # declared by the operator — honestly
  sourceReference: COMPILED-FROM-SESE.023.001.11.XSD
  reviewedAt: NOT_REVIEWED
  reviewedBy: SPECIFICATION_COMPILER
  generated: true                          # marks a compiled pack; drives the
                                           # structure capability dimension
  sourceLocation: sese.023.001.11.xsd      # file name inside its bundle, never a path
  sourceVersion: sese.023.001.11
  sourceChecksum: sha256:…                 # the exact bytes the pack was compiled from
  compilerVersion: spec-engine/1
  reviewStatus: NOT_REVIEWED
```

Everything below `reviewedBy` is optional and absent from hand-authored packs. No
timestamps: identical source bytes and compiler version produce byte-identical packs,
asserted by test.

## Structure

A nested tree of elements; document order in the YAML **is** element order in the XML.
A leaf carries exactly one of:

- `dataType:` — one of the named representation classes (`Max35Text`,
  `ISINOct2015Identifier`, `ActiveCurrencyAndAmount` + `currencyAttribute: true`,
  `Code` + `codes:` …), or
- `restriction:` — an arbitrary simple type carried verbatim from a source schema:

```yaml
- name: Qty
  displayName: Quantity
  presence: MANDATORY
  restriction:
    base: DECIMAL              # TEXT | DECIMAL | DATE | DATE_TIME | BOOLEAN
    typeName: RestrictedQuantity   # the schema's own name, display only
    totalDigits: 14
    fractionDigits: 3
    minInclusive: '0'
```

Validation, the derived XSD, Excel formats and samples all read the restriction's
facets; `typeName` is presentation. Choices are containers with `choice: true`, and a
branch of a choice is never individually `MANDATORY` — the choice itself carries
"exactly one".

## Presentation

`displayName`, `businessMeaning`, `businessQuestion`, `whyUsed`, `examples`,
`commonMistakes`, `searchTerms` — optional prose with **zero authority** over structure
or validation. Compiled packs ship mechanical display names and schema-derived examples
only.

## Honesty markers

```yaml
authoritativeCompletenessKnown: false
limitations:
  - This specification was machine-compiled from a source schema. …
  - The source schema allows unbounded occurrences of …; capped at 1000.
```

Every pack declares what it does not establish. The capability dimensions shown in the
catalogue, the spec API and the coverage report are derived from the pack's provenance
and the configured rules — never from a self-declared status flag.
