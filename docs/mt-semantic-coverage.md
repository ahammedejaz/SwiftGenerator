# MT semantic coverage

Every SWIFT Message Reference Guide in the knowledge base is read for its Network
Validated Rules, and every numbered rule receives exactly one disposition. The measured
table is [generated/mt-semantic-rule-coverage.md](generated/mt-semantic-rule-coverage.md);
the per-message reviewer packages are in `docs/generated/mt-rule-review/`.

## From 2 guides to 156

Phase 5B read MT540 and MT541 through a hand-written source catalogue. The corpus reader
(`app/rule_engine/mt_mrg/corpus.py`) reads every guide the knowledge base holds through the
**same** reader — cover identity, sections, Format Specifications, qualifier tables, rule
discovery, translation, refutation — with no per-message declaration: a guide is identified
from its own cover. The Phase 5B fixture for MT540/MT541 is unchanged in content by the
engagement (only the reader version moved), which is the regression proof that the generic
reader still reads those two books exactly as before.

```bash
make mt-mrg-corpus-extract   # read the guides (PDFs, or the sync's text cache) → evidence index
make mt-mrg-corpus-write     # coverage table + 156 review packs from the index
make mt-mrg-corpus-check     # part of make check: the documents match the committed index
```

The committed evidence index (`backend/tests/fixtures/mt_mrg/sr2026-corpus-evidence.json`,
schema `mt-mrg-corpus-evidence/1`) carries, per guide: identity, checksums, structure
counts, and per rule: id, error codes, page, text hash, disposition, template, reason,
residual limitation, resolved references, refuter objections. No rule text.

## Dispositions

| Disposition | Meaning |
|---|---|
| `EXACT` | the expression says what the sentence says, no more and no less |
| `PARTIAL_WEAKER_THAN_SOURCE` | the expression says less; the dropped clause is recorded as a residual limitation |
| `UNSUPPORTED` | no weaker-or-equal expression exists, with a named reason |

The reasons: `SENTENCE_FORM_NOT_RECOGNISED`, `COMPONENT_SCOPE_NOT_EXPRESSIBLE`,
`REFERENCE_NOT_RESOLVED`, `REFERENCE_AMBIGUOUS`, `OCCURRENCE_SCOPE_NOT_EXPRESSIBLE`,
`ENVELOPE_DEPENDENT` (the rule reads Block 1/2/3 of the FIN envelope — BICs, user header,
validation flag), `ARITHMETIC_NOT_MODELLED` (sums and totals), `TABLE_NOT_READ`.

**Never stronger than the source.** A weaker rule misses a violation a reviewer can still
catch; a stronger one rejects messages SWIFT accepts. Every template, old and new, is
subject to the same post-checks (data-source-scheme caveat, occurrence-scope wording).

## Rule DSL: rule-dsl/3

Two additions, the smallest the sources required:

- **Component extraction on a predicate** — `extract` (and `otherExtract` for the other
  field): a regular expression with a named group, derived by the translator from the
  field's own format notation (`6!n3!a15d` → `^\d{6}(?P<value>[A-Z]{3})`), applied before
  the comparison. "The currency code in 33B is different from the currency code in 32A"
  (MT103 C1) is exact. A value without the component satisfies no existential comparison
  and is skipped by universal ones.
- **`allEqual`** — every present value, in every occurrence, of every listed field (or its
  component) is the same. "The currency code in fields 32B and 33B must be the same for all
  occurrences" is exact; "the first two characters of the currency code" narrows the group.

Occurrence scope (`forEachOccurrence`) arrived with rule-dsl/2 and is accepted under /2 and
/3; the new constructs need /3. rule-dsl/1 and /2 packs load unchanged.

## Generic templates

`app/rule_engine/mt_mrg/templates_generic.py` adds compositional sentence forms found across
every category, applied after the Category 5 templates of Phase 5B:

- `CONDITIONAL_PRESENCE_GENERAL` — scope (sequence / each occurrence / the repetitive
  sequence), condition (present, absent, equals, one of, contains code, `//value`),
  consequence (present, absent, option only, option forbidden, codes only, must be code,
  must not be code), optional `otherwise` clause; exact when every reference resolves and
  the scope is expressible, weaker with a recorded residual when the sentence names
  several sequences or a field outside the occurrence.
- `DEPENDENCY_TABLE` — "the presence of X depends on the value/presence of Y as follows"
  plus the table's rows, read as a token stream (`NEWT Mandatory`, `Any other value
  Optional`, `Not present Not allowed`); unread rows are a residual.
- `CURRENCY_CONSISTENT`, `CURRENCY_DIFFERENCE_CONDITION` — component extraction.
- `EITHER_OR`, `BOTH_OR_NEITHER`, `NOT_THE_ONLY_FIELD`, `COUNT_LIMIT`, `SEQUENCE_COUNT`
  (counted through the sequence's mandatory field), `FIELDS_UNIQUE_WITHIN_OCCURRENCE`,
  `PREVIOUS_REFERENCE_EXACTLY_ONCE`, `CODE_REQUIRES_FIELD_IN_RESPECTIVE_SEQUENCE`,
  `ABSENT_FIELD_FORBIDS_CODES`, `PRESENT_IN_ONE_SEQUENCE_NOT_ANOTHER`,
  `FLAG_FORBIDS_SEQUENCE`, `EXCHANGE_RATE_REQUIRES_RESULTING_AMOUNT` (widened),
  `CANCELLATION_REQUIRES_ONE_PREVIOUS_REFERENCE` (widened).
- `MANDATORY_FIELDS_IN_OPTIONAL_SEQUENCE` — exact by construction: the structure
  validator already enforces it, and no expression is emitted.
- `ENVELOPE_DEPENDENT`, `ARITHMETIC_RELATION` — refusals with their reason, listed before
  the conditional forms so an envelope rule that also says "if field … is present" is not
  mistaken for a field rule.

A flat message's rows sit in `ROOT`, the same name the runtime pack uses; implicit repeat
groups are scopes like any other (`_A`, `B1_A`).

## Measured result (2026-08-21)

| | |
|---|---|
| Guides read | 156 (128 state Network Validated Rules) |
| Rules discovered | 911 |
| Exact | 330 |
| Partial (weaker than source) | 115 |
| Unsupported | 466 — 421 sentence form not recognised, 10 component scope, 10 unresolved reference, 9 ambiguous reference, 9 envelope-dependent, 7 arithmetic |
| Review required | 445 candidates · Reviewed 0 · Active 0 |

Phase 5B/5C on MT540/MT541 alone: 23 exact, 15 partial, 0 unsupported — unchanged.

The 421 unrecognised sentences are a long tail: 310 of them are the only rule of their
shape in the corpus. They are recorded, not approximated; each is a line in its message's
review pack with its page and error codes.

## Review state and activation

Nothing changed in the activation model. Every candidate is `REVIEW_REQUIRED`; none is
written to `backend/config/rules/`; the runtime registry refuses any pack that is not
`REVIEWED` in full; runtime activations are 0. A machine reading is not a SWIFT SME review.
The review packs exist so a person can approve or refuse quickly: page, rule id, error
codes, disposition, template or reason, residual limitation, refuter objections, review
state — and, for the candidate itself, the expression in the evidence fixture.

`make mt-mrg-evaluate` remains the developer lane for evaluating candidate behaviour
against synthetic values; ordinary validation never reads a candidate.
