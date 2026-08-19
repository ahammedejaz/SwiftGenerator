# Rule Pack Format

One YAML file, one message, one authority layer. A pack says what a *valid use* of an
already-valid structure looks like. It never says what the structure is.

Packs live in `backend/config/rules/` and are loaded at startup — but only when they are
fully reviewed. See [specification-rule-engine.md](specification-rule-engine.md) for how
one gets there.

## Identity

```yaml
packId: MX:sese.023.001.11:MARKET_PRACTICE:DEMO_MARKET_V1:v1
format: MX                       # MX | MT
messageType: sese.023
messageVersion: sese.023.001.11  # required for MX, forbidden for MT
layer: MARKET_PRACTICE           # BASE_STANDARD | MARKET_PRACTICE | CLIENT_PROFILE
profileId: DEMO_MARKET_V1        # required on an overlay layer, forbidden on the base
packVersion: v1
title: Synthetic demo market practice for securities settlement instructions
engineVersion: rule-engine/1
dslVersion: rule-dsl/1
```

`packId` is derived from those fields and asserted against them, and the file name is
`packId` lower-cased with `:` → `_`. Two packs may never share an identity. The layer
names are the repository's existing `RuleLayer`, so a rule layer and the validation layer
it reports under carry the same word.

## Structure compatibility

```yaml
structureCompatibility:
  structureVersion: sese.023.001.11
  structureChecksum: sha256:…
```

A digest of everything a rule can depend on — element identity, order, presence,
cardinality, kind, code set — and nothing it cannot. Presentation prose is deliberately
excluded: rewording a business explanation has no authority over a rule and must not expire
one. A mismatch is `RULE_STRUCTURE_VERSION_MISMATCH` and the pack does not load.

## Review

```yaml
review:
  status: REVIEWED               # AI_CANDIDATE | MACHINE_CHECKED | REVIEW_REQUIRED |
  reviewedBy: A. Reviewer        # REVIEWED | REJECTED | SUPERSEDED
  reviewedAt: SOURCE_CONTROLLED  # the commit is the timestamp; no clock in the file
```

The registry loads a pack only when the pack **and every rule in it** is `REVIEWED`.
Anything else is refused, not skipped.

## Sources

```yaml
sources:
  - sourceId: SYNTH-DEMO-MARKET-V1
    sourceType: SYNTHETIC_FIXTURE
    title: Synthetic Demo Market Practice — Securities Settlement
    version: '1.0'
    sourceLocation: synthetic-demo-market-v1.md
    sourceChecksum: sha256:…
    excerptsMayBeCommitted: true
```

Derived metadata only — never the document. `sourceType` is an operator **declaration**:
the platform can know a file arrived through the drop directory and that someone labelled
it, and cannot prove it is the genuine licensed artifact. Every `sourceId` an evidence
record names must be declared here.

## Honesty markers

```yaml
authoritativeCompletenessKnown: false      # refused if true
limitations:
  - DEMO_MARKET_V1 is a synthetic market invented for this repository.
  - Reviewed against the cited synthetic document only.
```

A pack establishes what its evidence says. Whether the evidence covers the standard is a
different claim, and one nothing here supports — so `authoritativeCompletenessKnown: true`
is a validation error, not a choice.

## Rules

```yaml
rules:
  - ruleId: DEMO-MKT-SESE023-CREDIT-DEBIT-WITH-AMOUNT
    title: Credit or debit indicator accompanies a settlement amount
    severity: ERROR                     # ERROR | WARNING | INFO
    when:                               # optional; absent means unconditional
      field: {format: MX, path: /Document/SctiesSttlmTxInstr/SttlmAmt/Amt}
      operator: EXISTS
    assert:
      field: {format: MX, path: /Document/SctiesSttlmTxInstr/SttlmAmt/CdtDbtInd}
      operator: EXISTS
    finding:
      message: An instruction carrying a settlement amount must say whether the cash is
        credited or debited.
      suggestion: Add the credit or debit indicator, or remove the amount.
    evidence: [ … ]
    review: { … }
```

If `when` is absent or holds, `assert` must hold. `finding` is prose with **zero
authority**: it is never parsed and cannot change an outcome. The finding points at the
field the *assertion* names — the one a tester has to change.

## Field references

The formats' own addressing, never a third scheme:

```yaml
field: {format: MX, path: /Document/SctiesSttlmTxInstr/SttlmParams/SttlmTxCond/Cd}
field: {format: MT, fieldId: MT541-E-22F-SETR}
field: {format: MT, sequencePath: SETDET, tag: 22F, qualifier: SETR}
```

A reference that resolves to nothing — or, for MT, to more than one row — fails
compilation. A rule addressing whichever field the resolver happened to pick first would be
worse than one that does not compile.

## The expression language

Closed, declarative and non-executable. No `eval`, no expression strings, no templating.
An unknown operator or key fails validation before anything runs, and the compiler
additionally refuses `eval(`, `exec(`, `__import__`, `{{ }}`, `<script`, `$(`, `://` and
SQL fragments anywhere in a pack.

**Predicate**

```yaml
{field: {…}, operator: EQUALS, value: APMT}
{field: {…}, operator: IN, values: [NOMC, PART]}
{field: {…}, subject: COUNT, operator: GREATER_OR_EQUAL, value: '2'}
{field: {…}, operator: DATE_ON_OR_BEFORE, otherField: {…}}
```

| Group | Operators | Operand |
|---|---|---|
| Presence | `EXISTS`, `ABSENT` | none |
| Equality | `EQUALS`, `NOT_EQUALS` | `value` or `otherField` |
| Membership | `IN`, `NOT_IN` | `values` |
| Text | `MATCHES` | `value` (a regex) |
| Numeric | `GREATER_THAN`, `GREATER_OR_EQUAL`, `LESS_THAN`, `LESS_OR_EQUAL` | `value` or `otherField` |
| Date | `DATE_BEFORE`, `DATE_AFTER`, `DATE_ON_OR_BEFORE`, `DATE_ON_OR_AFTER` | `value` or `otherField` |

`subject: COUNT` turns the numeric and equality operators into occurrence comparisons.

**Boolean and group**

```yaml
{allOf: [ … ]}        {anyOf: [ … ]}        {not: { … }}
{implies: {if: { … }, then: { … }}}
{exactlyOne: [field, field]}   {atLeastOne: [field]}   {atMostOne: [field, field]}
```

### Evaluation semantics

Spelled out because silence here is how a rule engine becomes unpredictable. Over the
values a message actually contains:

- `EXISTS` is true when at least one non-empty occurrence is present; `ABSENT` is its
  negation. A whitespace-only value is not present.
- **Positive** operators (`EQUALS`, `IN`, `MATCHES`, numeric, date) are true when *some*
  present value satisfies them. With no values present they are **false**.
- **Negative** operators (`NOT_EQUALS`, `NOT_IN`) are true when *every* present value
  satisfies them. With no values present they are **true** — which is what makes "this
  field must not be X" behave correctly when the field is simply not there.
- `subject: COUNT` compares occurrences, which is always defined.
- A value that cannot be read as the operator's type makes that one comparison false and
  reports nothing extra; the FORMAT layer already owns malformed values.
- `MATCHES` anchors the whole value.

### What the compiler refuses

Reference unresolvable · operator/datatype mismatch · a code the structure does not declare
· a count beyond the field's cardinality · a regex with nested unbounded quantifiers or a
backreference · a duplicate identifier · a rule that unconditionally forbids a field the
structure requires in every message · evidence missing · an expression nested more than
twelve deep · executable-looking content anywhere.

## Code restrictions

Narrowing is first class rather than expressed as an `IN` rule, because it has to be
*compared across layers* — the only way to refuse a higher layer that widens a lower one.

```yaml
codeRestrictions:
  - restrictionId: DEMO-MKT-SESE023-SETTLEMENT-CONDITION
    field: {format: MX, path: /Document/SctiesSttlmTxInstr/SttlmParams/SttlmTxCond/Cd}
    codes: [NOMC, PART, CLEN]
    severity: ERROR
    finding: { … }
    evidence: [ … ]
    review: { … }
```

`codes` must be a subset of the structural code set, and of the effective set from every
layer beneath. Widening is `RULE_OVERLAY_WIDENING`; a disjoint set is
`RULE_OVERLAY_CONFLICT`. Rules and restrictions share one identifier namespace.

## Evidence

```yaml
evidence:
  - sourceId: SYNTH-DEMO-MARKET-V1
    segmentId: SYNTH-DEMO-MARKET-V1#S0003
    sourceLocation: synthetic-demo-market-v1.md
    sourceVersion: '1.0'
    sourceChecksum: sha256:…
    segmentHash: sha256:…
    excerptHash: sha256:…
    excerpt: 'Instructions sent in this market carry a settlement transaction condition…'
    heading: 2 Settlement transaction condition
    lineStart: 16
    lineEnd: 17
```

Every rule carries at least one. A reviewer can always answer *which exact source location
caused this rule to exist* — and can do so with their own copy of the document when no
excerpt may be stored, which is the default. Silence is not permission: a source whose
licence has not been considered is treated as one that may not be redistributed.

## Extraction metadata

Present only on model-derived rules; absent on hand-authored ones.

```yaml
extraction:
  method: ISOLATED_DUAL_EXTRACTION
  agreement: AGREE                  # AGREE | PARTIAL_AGREEMENT | CONFLICT | ONLY_A | ONLY_B
  extractorModels: [ …, … ]
  refuterModel: …
  promptVersion: rule-extraction-v1
  schemaVersion: rule-candidate-v1
  refuterObjections: [ 'SOURCE_AMBIGUOUS: …' ]
```

`ISOLATED_DUAL_EXTRACTION`, not "independent": two passes may share a provider, a model
family and training data. No chain-of-thought is requested or stored — only the closed
schema's fields are persisted.

## Determinism

The same pack always writes the same bytes: no timestamps, no clock, sorted where order
carries no meaning. `review.candidateHash` and `review.ruleHash` are over the rule's
*behaviour* — identity, condition, assertion, evidence — so equal hashes are themselves the
evidence that a reviewer approved a candidate unchanged, and reworded prose leaves both
alone.
