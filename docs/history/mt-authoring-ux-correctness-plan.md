# MT authoring UX and domain-correctness plan

Branch `feat/mt-authoring-ux-correctness`. Written after the audit in §1–§7 and before any
code change, as [AGENTS.md](../AGENTS.md) §3 requires: most of what follows is a YAML edit, and
knowing which parts are *not* is the point of writing it down first.

---

## 1. Reproduction

The tester's message was replayed through the real service, not read.

```
cd backend && PYTHONPATH=. APP_ENV=test .venv/bin/python scratch/repro.py
```

```
valid: False
  [MT_FORMAT_INVALID] loc=MT541-B-35B-NONE field=Financial Instrument Identification
     message : Financial Instrument Identification does not match the expected format.
     expected: The subset renders the literal ISIN followed by a validated 12-character identifier.
     current : ISIN US9897778ABC
     suggest : For example: XS0000000001
```

Block 4 was still composed, and it composed **everything else the tester typed without
complaint**:

```
:22F::SETR//SELL          <- accepted
:22F::SETR//RECE          <- accepted, second SETR in the same message
:95R::DEAG//MGTHMEXXX     <- a BIC-shaped value accepted under the proprietary option
:95R::REAG//BEBE76XXX     <- second agent, also mandatory today
```

So the reported experience is not one defect. One field was rejected with an unhelpful
sentence; four genuinely wrong things were accepted silently.

The single error is also **self-contradictory**: `expected` tells the tester to type the
literal `ISIN`, `suggestion` shows an example without it. Both come from configuration, and
they disagree, which is the shortest possible statement of the root cause.

---

## 2. ISIN root cause

**Two owners of the literal `ISIN `, and they disagree.**

| Path | Who writes `ISIN ` | Canonical value |
|---|---|---|
| Studio MT (`/api/v1/messages/generate`, UI, Excel, import) | **the caller** | `ISIN XS0000000001` |
| Legacy composers (`app/composers/*.py`, Advanced screens) | **the composer** (`f"ISIN {id}"`) | `XS0000000001` |
| MX (`sese.023`, same business path `security.identifier`) | n/a — no prefix exists | `XS0000000001` |
| Knowledge YAML `exampleValues` for 35B | — | `XS0000000001` |
| Excel **Reference** sheet "Example" column | — | `XS0000000001` (from the knowledge example) |
| Excel **Scenarios** sheet (built from `build_sample`) | — | `ISIN XS0000000001` |

Three of the six say bare, three say prefixed, and the same generated workbook says both on
two different sheets.

The enforcement lives in `app/authoring/composer.py:293`:

```python
"35B": r"ISIN [A-Z]{2}[A-Z0-9]{9}\d",
```

and the UI placeholder lives in `FieldEditor.tsx`, where it is
`field.examples[0]?.value` — the bare form. So the studio literally shows the tester a
placeholder its own validator rejects.

Secondary findings:

- **No check-digit validation anywhere.** The regex ends `\d`, which only asserts the last
  character is numeric. `US9897778ABC` fails that (`C`), which is why the tester saw an
  error — but for the coarsest of the reasons available, and never stated.
- **The repository's own sample ISIN fails ISO 6166.** `XS0000000001` carries check digit
  `1`; the correct digit for body `XS000000000` is `9`. Verified with the modulus-10
  algorithm, not asserted. `XS0000000009` is the checksum-valid form. Every golden fixture,
  the demo pack and both Excel templates currently ship the invalid one.
- **35B is not the only unowned literal.** `36B` is `4!c/15d` (`UNIT/1000`) and the tester
  types the `UNIT/` too, for the same reason.

## 3. SETR root cause

Already recorded as a known defect in [AGENTS.md](../AGENTS.md) §14, [limitations.md](../limitations.md)
and §16 item 4 — *"fix once an authoritative source exists"*. **The authoritative source is
already in this repository**, which is the finding that unblocks it.

`backend/config/mx/sese.023.001.11.yaml` is the configured ISO 20022 definition of the same
business message as MT540–MT543. It models the three concepts separately:

| sese.023 element | Codes | Concept |
|---|---|---|
| `SttlmTpAndAddtlParams/SctiesMvmntTp` | `RECE`, `DELI` | direction |
| `SttlmTpAndAddtlParams/Pmt` | `APMT`, `FREE` | payment |
| `SttlmParams/SctiesTxTp/Cd` | `TRAD, COLI, COLO, PLAC, PORT, REDM, SUBS, TURN, NETT, OWNE, OWNI` | transaction type |

and its `SctiesTxTp/Cd` node already carries, in `commonMistakes`, the exact instruction:

> *Using the MT direction codes RECE or DELI here; direction is carried by SctiesMvmntTp.*

with `searchTerms: [SctiesTxTp, TRAD, transaction type, SETR, 22F]` — the repository's own
statement that `SttlmParams/SctiesTxTp` **is** `22F::SETR`.

Against that, the MT configuration does three wrong things:

1. **`B / 22F::SETR` with `allowedCodes: [BUY, SELL]`.** Not a transaction-type code list.
   Its own record admits this: `ruleLayer: INTERNAL_RULE_PACK`,
   `source.sourceType: APPROVED_INTERNAL_RULE_PACK`, `standardsRelease: DEMO_SR2026`. It is
   a demonstration taxonomy that was rendered into a real field.
2. **`E / 22F::SETR` with `allowedCodes: [RECE, DELI]`** and `businessPath: direction`.
   `RECE`/`DELI` are the `ReceiveDelivery1Code` values that belong to `SctiesMvmntTp`; in
   ISO 15022 the direction is carried by the *message type*. This record is labelled
   `ruleLayer: BASE_STANDARD` with an `OFFICIAL_ISO_15022` source, which is a mislabel.
3. **Two `22F::SETR` fields in one message.** Neither is the transaction type.

The deterministic resolver `app/domain/resolver.py` is already correct and needs no change —
`(RECEIVE, AGAINST_PAYMENT) → MT541`, `(DELIVER, AGAINST_PAYMENT) → MT543`. Direction and
payment are already business inputs that *select the message*; nothing needs to restate them
inside it.

## 4. Party-selection root cause

Two separate defects.

**(a) Both agents are mandatory in every message.** `settlement_v1.yaml` defines `DEAG` and
`REAG` from one YAML anchor with `presence: MANDATORY`, applied to `[MT540, MT541, MT542,
MT543]` and again to `[MT544..MT547]`. So an MT541 requires a receiving agent and an MT543
requires a delivering agent.

The same authoritative artifact settles this. sese.023:

- `DlvrgSttlmPties` — *"Required when the account owner is **receiving** securities, because
  the chain that delivers them must be identified."*
- `RcvgSttlmPties` — *"Required when the account owner is **delivering** securities, because
  the chain that receives them must be identified."*

and `samples.py::_apply_consistency` already drops the wrong chain for MX. MT never got the
same rule.

Note what this does **not** say: it does not say the other chain is illegal. sese.023 marks
both containers `CONDITIONAL`, not mutually exclusive. So the correction is a presence
change (`MANDATORY` → `OPTIONAL` for the non-required side), never a prohibition —
matching the brief's `REQUIRED CORE PARTY` / `OPTIONAL ADDITIONAL PARTY` distinction.

**(b) Only option R exists, and it is not validated as option R.** Every settlement party is
configured `supportedOptions: [R]` — the proprietary form. `_format_valid` checks
`[A-Z0-9._/-]{1,70}`, which does not require the Data Source Scheme that makes a value an
option-R value at all. So `:95R::DEAG//MGTHMEXXX` — a BIC written into the proprietary
field — was accepted. That is exactly the anti-pattern the brief names, and the studio
taught it.

sese.023 identifies all three parties by `AnyBIC`, with
`searchTerms: [..., 95P]` and `commonMistakes: [Supplying a proprietary code where a BIC is
required]`. So the BIC form (95P) is the one the repository's own equivalent message uses,
and it does not exist in the MT configuration.

## 5. Guided / Expert consistency findings

They already share `message_spec()`. The disagreements are all *presentation decisions made
outside it*:

| Decision | Where it lives now | Consequence |
|---|---|---|
| "is this field a dropdown?" | `FieldEditor.tsx`, heuristic `codesAreWholeValue` | React owns a rule configuration should own |
| "is the current value still a valid code?" | same line: `!value \|\| allowedCodes.includes(value)` | a value outside the list silently downgrades the control to a text box |
| "what does this code mean?" | nowhere | dropdowns show `TRAD`, never `TRAD — Trade` |
| ISIN, BIC, quantity, date, amount | nowhere | every field is `TextInput` |

`visibleSpec` in `CreateMessage.tsx:178` is dead code — both branches return `spec`. The only
real difference between the modes is the `revealed` set.

**A real data-loss path:** `chooseMode("GUIDED")` clears `revealed`, but never clears
`values`. An optional field filled in Expert mode becomes invisible in Guided and is *still
submitted*. Not "silently dropped" — worse: silently kept and unreviewable.

## 6. Sample discoverability findings

Samples are already production-composer output (`samples.py` is candidate-and-check plus
validate-and-repair against the real validator), so the architecture is right and the brief's
"do not build a second demo system" is already satisfied.

The problem is placement. Step 4 asks "How do you want to enter the data?" with two large
cards, and samples are a secondary block *below* them under "Or start from a sample". A
tester reads the two cards, picks one, and never sees the row that would have filled the form
in one click.

`applySample` itself is sound — it writes the same `values` state manual entry writes, then
lands on step 5 in Guided mode. Nothing marks the result as sample data.

## 7. Current API metadata gaps

`/api/v1/catalogue` and `/api/v1/messages/{type}/spec` expose `allowedCodes: string[]` and
nothing else a client needs to build a safe form:

- no `inputKind` — a client cannot tell a code list from a free-text field
- no code labels or descriptions
- no statement of who writes a literal prefix
- no `maxLength`
- no choice grouping for MT (it exists for MX as `choiceGroup`)

---

## 8. Proposed specification metadata changes

All configuration. No new code path.

**New file `backend/config/knowledge/code_lists.yaml`** — named code lists, each entry
`code` / `label` / `description`. One vocabulary for the UI, the JSON API, Excel and both
formats. Referenced by id, never duplicated.

**`TagKnowledgeDefinition` (`app/knowledge/models.py`) gains optional keys** — the model is
`extra="forbid"`, so each is explicit:

| Key | Purpose |
|---|---|
| `codeList` | id in `code_lists.yaml`; derives `allowedCodes`, loader asserts they agree if both are given |
| `inputKind` | `TEXT` · `SELECT` · `DATE` · `AMOUNT` · `QUANTITY` · `NARRATIVE` · `REFERENCE` · `IDENTIFIER` · `PARTY_BIC` · `PARTY_PROPRIETARY` · `INDICATOR` |
| `literalPrefix` | the literal the **composer** writes, e.g. `ISIN ` |
| `identifierTypes` | e.g. `[ISIN]` |
| `choiceGroup` | rows sharing one are alternatives; exactly one satisfies the group |
| `maxLength` | for the character counter |

**MX YAML nodes gain optional `codeList`**, so `SctiesTxTp/Cd`, `SctiesMvmntTp` and `Pmt`
read the same lists the MT records do. Nodes without it keep working and render as
code-only selects.

**`settlement_v1.yaml` changes:**

1. Delete the `B / 22F::SETR` record (`BUY`/`SELL`).
2. Rewrite `E / 22F::SETR`: `businessPath: trade.transactionType`,
   `codeList: SETTLEMENT_TRANSACTION_TYPE`, example `TRAD`, and copy explaining that
   direction comes from the message type. `ruleLayer` and `source` corrected to match
   the reconciliation actually performed.
3. Split the party records by direction family:
   - receive (`MT540 MT541 MT544 MT545`) → `DEAG` required, `REAG` optional
   - deliver (`MT542 MT543 MT546 MT547`) → `REAG` required, `DEAG` optional
   - `PSET` conditional in both, unchanged
4. Add a **95P** row beside every 95R party row, in `choiceGroup`
   `<MSG>-E-<QUAL>`, ranked first, `inputKind: PARTY_BIC`.
5. 35B: `literalPrefix: "ISIN "`, `identifierTypes: [ISIN]`, `inputKind: IDENTIFIER`,
   example `XS0000000009`, and rewritten `formatExplanation` /
   `businessMeaning` / `commonMistakes` for Message Intelligence.
6. 36B/93B: `inputKind: QUANTITY`, `codeList: QUANTITY_TYPE`.
7. 23G, 25D, 24B, 13A, 22F STCO: `codeList` references.

**Python constants that mirror the YAML must move with it** — `KNOWN_FIELD_SIGNATURES` in
`app/knowledge/loader.py`, `ALLOWED_FIELDS` and `FIELD_RANK` in `app/raw/validator.py`.
These are a hand-maintained whitelist and rank table; missing one turns a config change into
a startup failure or a silently misordered message.

## 9. UI changes

`FieldEditor.tsx` renders from `inputKind` only. The `codesAreWholeValue` heuristic is
deleted, not fixed.

| `inputKind` | Control |
|---|---|
| `SELECT` | searchable combobox, `CODE — Label`, description under it; preselected and read-only when the list has one entry |
| `IDENTIFIER` | `ISIN` badge, 12-char input, live `n / 12`, live check-digit state, paste-normalisation |
| `PARTY_BIC` | uppercase BIC input, 8/11 length state |
| `PARTY_PROPRIETARY` | separate Data Source Scheme + identifier inputs, joined to `DSS/identifier` |
| `QUANTITY` | code select + numeric input, joined to `CODE/number` |
| `DATE` | date picker, rendered to `YYYYMMDD` |
| `AMOUNT` | currency select + decimal input |
| `REFERENCE` | text with `n / max` |
| `NARRATIVE` | textarea |

Party choice groups render one question — *"How do you want to identify the party?"* →
**BIC** / **Proprietary identifier** — and select the row. Never `95P` vs `95Q` vs `95R`.

`CreateMessage.tsx`:

- step 4 leads with **Start with: `[Empty message] [Typical sample] [Minimal sample] [Full sample]`**;
  the Guided/Expert choice follows it
- loaded samples carry a `SAMPLE_DATA` banner and per-row badge, cleared on edit
- switching to Guided keeps any optional field that holds a value revealed, and says so
- delete dead `visibleSpec`

Client-side validation is usability only; the server keeps deciding.

## 10. Backend changes

**New `app/domain/identifiers.py`** — the one deterministic identifier utility. No model
call, no network.

```
normalise_isin(raw)      strip, uppercase, collapse space, drop a leading "ISIN "
isin_check_digit(body11) ISO 6166 modulus-10
validate_isin(value)     -> IsinVerdict(format_valid, check_digit_valid, reason)
synthetic_isin(body11)   deterministic checksum-valid test value
normalise_bic / validate_bic
```

`FORMAT_VALID` and `CHECK_DIGIT_VALID` stay separate verdicts and are reported in different
layers, because they are different claims:

| Failure | Layer | ruleId | Why there |
|---|---|---|---|
| length / character / final-character-not-numeric | `FORMAT` | `MT_ISIN_LENGTH`, `MT_ISIN_PREFIX`, `MT_ISIN_CHARACTER`, `MT_ISIN_CHECK_DIGIT_NOT_NUMERIC` | ISO 15022 field format |
| check digit does not match | `CLIENT_PROFILE` | `MT_ISIN_CHECK_DIGIT_INVALID` | ISO 6166 identifier quality, **not** a SWIFT field-format rule; severity is profile-driven |

Neither claims the identifier is registered. A synthetic value is labelled
`STRUCTURALLY_VALID_SYNTHETIC`; `REGISTERED_REAL_IDENTIFIER` is a state no code path can
currently produce, and says so.

**`app/authoring/composer.py`** — `_format_valid` becomes specification-driven for the cases
configuration now describes: a row with a `literalPrefix` is validated on the canonical value
and rendered with the prefix; `95R` requires `DSS/identifier`; `95P` requires a BIC shape.
The composer stays the only thing that writes Block 4.

**`app/studio/mt/generator.py`** — canonicalisation runs once in `resolve()`, so UI, JSON,
Excel and import share it; choice-group requiredness and conflict; identifier verdicts.

**`app/studio/mt/parser.py`** — strips a configured `literalPrefix` on the way in.

**`app/studio/catalogue.py` / `models.py`** — `SpecField` gains `inputKind`,
`allowedValues[]`, `literalPrefix`, `userEntersLiteralPrefix`, `identifierTypes`,
`maxLength`, and MT `choiceGroup`. Additive; existing `allowedCodes` stays populated.

**Legacy composers** (`app/composers/dvp_instruction.py`, `fop_instruction.py`) emit one
`:22F::SETR//TRAD` in SETDET. They already own the `ISIN ` literal, so after this change
they and the studio composer agree for the first time. `TransactionType` (BUY/SELL) stays a
*business-intent* enum that selects the message; it stops being rendered into a field.

## 11. Excel changes

- **New `Codes` sheet**: message · sequence · tag · qualifier · option · code · label ·
  description. One row per allowed code.
- **Reference sheet** gains `Input kind`, `Literal prefix`, `Max length`.
- **Scenarios sheet** gets per-cell `DataValidation` dropdowns on `Value` for rows whose
  field has a finite list, within Excel's 255-character inline-list limit; longer lists get a
  note pointing at `Codes` rather than a silently missing dropdown.
- **35B canonical representation: the bare identifier, `XS0000000009`.** A legacy
  `ISIN XS0000000009` is normalised, not rejected. Stated on the `Read me` sheet.

## 12. Import compatibility

`Parse(":35B:ISIN XS0000000009") → "XS0000000009"`, `Compose("XS0000000009") → ":35B:ISIN
XS0000000009"`. Exactly one literal, never `ISIN ISIN`, never a lost prefix. The existing
`Compose(Parse(Compose(v))) == Compose(v)` assertion over every sample of every message and
all 17 golden fixtures already covers this once the fixtures are regenerated; an explicit
directed test is added because that identity would also hold if both sides were wrong.

## 13. Migration and backward compatibility

| Change | Impact | Handling |
|---|---|---|
| 35B canonical value | a caller POSTing `ISIN XS…` today | normalised, not rejected; documented |
| `22F::SETR//BUY` in TRADDET | removed from the specification | `MT_UNKNOWN_FIELD` naming the field and the correct one — the standing behaviour for a field outside the subset |
| `22F::SETR//RECE` | code list replaced | `MT_CODE_NOT_ALLOWED` listing the real codes |
| golden fixtures | all 17 change | regenerated in this commit, with the reason, per AGENTS.md §15 |
| `demo/` | regenerated by `make demo-pack` | gated by `make check` |
| `docs/generated/message-coverage.md` | row counts change | `make coverage-write`, gated |
| `SpecField` additions | additive only | existing clients unaffected |

**No capability claim moves.** Every message stays `PARTIAL` with
`authoritativeCompletenessKnown: false`. This work corrects and explains what is inside the
configured subset; it does not enlarge it.

## 14. Test plan

**ISIN** (`tests/unit/test_identifiers.py`, `tests/studio/test_mt_generation.py`) —
identifier only · pasted `ISIN ` prefix · lowercase · too short · too long · invalid
character · non-numeric final character · invalid check digit · valid checksum ·
`US9897778ABC` rejected *specifically* for the final character · `XS0000000001` rejected for
the check digit · round trip · Excel · JSON API.

**MT541** — exactly one `22F::SETR` · in `SETDET` · `TRAD` · `DEAG` required · `PSET` ·
`REAG` **not** mandatory · party option is `95P` when identified by BIC · `35B` well formed ·
settlement amount present.

**MT543** — `TRAD` · `REAG` required · `PSET` · `DEAG` not mandatory.

**MT540 / MT542** — party direction · no cash amount in the free-of-payment scenario.

**MT544–MT547** — each confirmation's party default asserted individually, parametrised over
the set rather than picking a member (AGENTS.md §17).

**Dropdowns** — for every configured finite code list: `inputKind == SELECT`, labels exist,
values come from the catalogue, and the **server still rejects an invalid code posted
directly to the API**.

**Samples** — every production-composer sample generates, validates, loads in both modes and
produces byte-identical Block 4 from equivalent JSON and Excel input.

**Playwright** — the five scenarios A–E in the brief.

## 15. Risks

| Risk | Mitigation |
|---|---|
| Golden churn hides a real regression | regenerate in one commit, then read every diff line; the SETR/party/ISIN lines are the only ones that may move |
| `KNOWN_FIELD_SIGNATURES` / `FIELD_RANK` drift | both are load-time assertions — a miss fails at import, not at runtime |
| `test_ambiguous_tag_without_a_sequence_is_reported` depends on two SETRs in MT541 | after the fix MT541 has no ambiguous address; retarget the test at a message that genuinely has one, derived from the registry rather than hardcoded (AGENTS.md §13.24) |
| Excel per-cell data validation is slow or corrupts on large sheets | bounded by the 255-char list limit and asserted by reopening the workbook in the test |
| A tightened `95R` breaks MT537 | checked: MT537 already emits `BFSDEMO1/SYNTHSERVICER`, which satisfies the DSS form |
| Scope: the legacy `/advanced` composers | in scope — they emit the same wrong structure and the brief forbids samples that teach it. They are *not* forked; they are corrected in place |

## 16. Acceptance criteria

1. No path asks a tester to type `ISIN `; exactly one component writes it.
2. 35B errors name the actual defect, with entered/expected/example/fix.
3. Check-digit validation exists as a separate deterministic verdict in its own layer.
4. Every configured finite code list renders as a labelled select, sourced from configuration.
5. MT540/541/544/545 Guided requires `PSET` + `DEAG`; MT542/543/546/547 requires `PSET` + `REAG`.
6. Direction is never encoded in `22F::SETR`; an ordinary trade is `TRAD`, once, in `SETDET`.
7. `95P` for BIC identification, `95R` only with a Data Source Scheme.
8. Guided and Expert disagree about nothing; switching preserves every value.
9. A typical sample is one click from choosing a message, for every MT540–MT548.
10. Excel, JSON and the UI produce byte-identical Block 4 for equivalent values.
11. MT import still round-trips.
12. `make check`, `make e2e`, `make secret-scan`, `make coverage`, `make demo-pack-check`,
    `docker compose build`, `git diff --check` all pass, and CI is green.
13. No message is promoted from `PARTIAL`; no new claim of conformance, registration or
    certification appears anywhere.

---

## 17. Self-review of this plan

Four things were changed after writing it down.

**The SETR fix was going to be blocked.** The first draft deferred it, because AGENTS.md §14
says correcting it "needs an authoritative source, not a guess". Re-reading
`sese.023.001.11.yaml` showed the source is committed to this repository and even names
`22F` and `SETR` in the search terms of the element that replaces it. Deferring would have
been the guess.

**"REAG is illegal in MT541" was the wrong correction** and the brief warns against it
directly. sese.023 marks both party chains `CONDITIONAL`, not exclusive. The change is
`MANDATORY → OPTIONAL`, so an optional additional chain party stays available in Expert mode.

**The ISIN literal was going to move to the *value*.** Making the caller's value canonical
would have been one line and would have matched the studio's existing behaviour. It is the
wrong direction: it keeps SWIFT syntax in the business value, contradicts the knowledge
example, contradicts MX for the same `businessPath`, and leaves the legacy composers
disagreeing. The composer owns it.

**Check-digit severity nearly went in the `FORMAT` layer.** That would have claimed a SWIFT
field-format rule that does not exist — the ISO 15022 format for 35B is
`4!c//12!c`, and the network does not verify ISO 6166 check digits. Keeping the two verdicts
in different layers is the honest arrangement, and it is why the brief asks for the
distinction.

One thing was deliberately *not* changed: the deterministic resolver. It already implements
the brief's `Receive + Against Payment → MT541` mapping, and remains authoritative over any
AI-suggested intent.
