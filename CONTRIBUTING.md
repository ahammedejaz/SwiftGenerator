# Working on this repository

---

## Set up

```bash
make install     # Python virtualenv + npm packages
make migrate     # create the database
```

Needs **Python 3.13** and **Node 22**. No API keys, no external services.

```bash
make backend     # terminal 1 → :8000
make frontend    # terminal 2 → :3000
```

## Before you push

```bash
make check       # lint + typecheck + backend tests
make e2e         # browser tests
```

Both must pass. `make check` runs in about ten seconds; there is no reason to skip it.

---

## Where things live

```
backend/
  app/studio/          the studio — what most new work touches
  app/specifications/  MT specification registry      ← reused, rarely changed
  app/knowledge/       MT knowledge base loader       ← reused, rarely changed
  app/authoring/       Block 4 composer + the draft/approval stack
  app/domain/          the original scenario model, serving the Advanced screens
  app/agents/          the AI layer
  config/              THE SPECIFICATIONS — most changes start here
  tests/studio/        the studio test suite

frontend/
  app/                 one folder per route
  components/studio/   the studio components
  lib/studio-types.ts  TypeScript mirror of the API contract
  lib/studio-api.ts    the typed client — the only place fetch() is called
  tests/e2e/           Playwright
```

[ARCHITECTURE.md](ARCHITECTURE.md) explains how they fit together.

---

## Most changes are YAML, not code

This is the thing to internalise. **Before writing code, check whether the change belongs
in `backend/config/`.**

### Add a field to an MT message

Add a record to the right file in `backend/config/knowledge/`:

```yaml
- messageTypes: [MT541, MT543]
  workflowModule: SETTLEMENT
  sequencePath: E
  fieldTag: 22F
  qualifier: STCO
  businessPath: settlement.condition
  displayName: Settlement Transaction Condition
  businessMeaning: Conditions that apply to the settlement of this transaction.
  technicalMeaning: Controlled four-character indicator.
  whyUsed: Controls whether partial settlement is permitted.
  businessQuestion: Do any special settlement conditions apply?
  missingImpact: The instruction settles under default market conditions.
  presence: OPTIONAL
  supportedOptions: [F]
  allowedCodes: [NOMC, PART, PARC]
  formatExplanation: Four-character controlled condition code.
  exampleValues:
    - value: NOMC
      synthetic: true
      explanation: No automatic market claim.
  lifecycleImpact: Affects whether the transaction may settle partially.
  ruleLayer: BASE_STANDARD
  standardsRelease: PUBLIC_UHB_REVIEW_2026_08_05
  knowledgeVersion: KB_2026_08_05_V1
  source: *settlement_source
  searchTerms: [STCO, settlement condition, partial]
```

Restart. It now appears in the API, the UI, the Excel template and Message Intelligence.
No TypeScript, no Python.

### Add an MX message

One new file in `backend/config/mx/`, named `<type>.<version>.yaml`. Follow
`sese.023.001.11.yaml`. The registry finds it, the catalogue lists it, samples generate
themselves, the Excel template gains a sheet, and the XSD is derived from it.

Two rules the loader enforces:

- The namespace must be `urn:iso:std:iso:20022:tech:xsd:<version>`.
- A node has either `dataType` (a leaf) or `children` (a container), never both.

**Document order in the YAML is element order in the XML.** Get it right; a receiver will
reject an out-of-order message.

### Add a client profile

One file in `backend/config/profiles/`. See [docs/configuration.md](docs/configuration.md).

---

## When you do write code

### A new validation rule

MT: `MtGenerator._business_rules` or `._profile_rules`.
MX: `MxGenerator._business_rules`.

Every issue must carry all of:

```python
_error(
    "SETTLEMENT_DATE_BEFORE_TRADE_DATE",              # stable id — automation branches on it
    "The settlement date is earlier than the trade date.",   # what is wrong, plainly
    layer=ValidationLayer.BUSINESS_RULES,             # which layer failed
    field_name="Intended Settlement Date",            # the BUSINESS name, not the tag
    location=settlement.row.row_id,                   # so the UI can jump to it
    expected=f"A date on or after {trade.value}",
    current=settlement.value,
    suggestion="Set the settlement date on or after the trade date.",   # what to DO
)
```

The suggestion is not optional. A manual tester reads that line and nothing else.

Prefer configuration to code where you can — `requireOneOf` in the MX YAML is a rule
expressed as data rather than as a branch.

### A new endpoint

Add it to `app/studio/routes.py`, and add the matching call to `lib/studio-api.ts` and the
matching type to `lib/studio-types.ts`. Those three stay in step by hand; there is no
generator.

**The UI must not gain a capability the API lacks.** If a screen needs something, the
endpoint comes first.

---

## Style

**Backend** — ruff and mypy in strict mode, 100 columns, Python 3.12 target. Both run in
`make check`; neither is advisory.

**Frontend** — ESLint and `tsc --noEmit`. Tailwind 4 with tokens from `app/globals.css`.

Three frontend rules that came from real bugs:

1. **Base styles go in `@layer base`.** An unlayered rule beats everything in Tailwind's
   utilities layer regardless of specificity. An unlayered `button { color: inherit }` once
   silently killed every text-colour utility on every button in the product.
2. **Grid and flex children that can hold wide content need `min-w-0`.** They default to
   `min-width: auto`, so a wide code block or table expands its track instead of scrolling,
   and the page scrolls sideways.
3. **No synchronous `setState` in an effect body.** React 19 lints it. Put the fetch inside
   the effect and use a reload token for retry, rather than calling a callback that sets
   state.

**Comments** explain *why*, not *what*. A comment that restates the code is noise; one that
records a decision, a constraint, or a bug that was fixed is the reason the next person
does not reintroduce it.

---

## Rules with a reason

**Never invent a value the tool cannot legitimately produce.** Session numbers, sequence
numbers, MAC and CHK trailers, signatures. If you cannot get it honestly, fail with a
message naming what is missing. A plausible fake in a test message is a bug waiting to
reach production.

**Never claim coverage the repository does not have.** Everything ships
`authoritativeCompletenessKnown: false`. Only a reconciled, licensed specification changes
that.

**MT and MX never share a rendering path.** They meet at the dispatching service and at the
result. Blending them produces plausible nonsense.

**Errors name the business field.** "Settlement Amount is required", not
"MT541-E-19A-SETT missing". The rule id belongs in the payload, not in the sentence.

---

## Commits

Explain **why**, not what — the diff already says what.

```
Deduplicate composer findings against structured errors

Twelve missing fields produced twenty-four errors: the composer restates in its
own words what the structured validator already reported, and the previous
dedupe compared message strings, which never matched. It now drops any composer
finding naming a row id already covered.
```

If a test caught the bug, say so. If you changed a golden file, say why the output changed.

---

## Adding tests

See [docs/testing.md](docs/testing.md). In short: name the test after the behaviour, assert
on rule ids rather than prose, parametrise over sets rather than picking a member, and
prefer a real end-to-end assertion to a mock — the whole backend suite runs in about three
seconds, so there is no speed argument for faking things.
