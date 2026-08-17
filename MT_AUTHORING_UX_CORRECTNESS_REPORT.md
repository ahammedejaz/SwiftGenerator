# MT authoring UX and domain-correctness report

Branch `feat/mt-authoring-ux-correctness` · commit `af327e5`.
Plan and self-review: [MT_AUTHORING_UX_CORRECTNESS_PLAN.md](MT_AUTHORING_UX_CORRECTNESS_PLAN.md).

---

## 1. Executive summary

A tester's MT541 was refused with one unhelpful sentence, and **four genuinely wrong things
in the same message were accepted without comment**. Both halves of that are fixed.

| | Before | After |
|---|---|---|
| Field 35B | caller typed `ISIN XS…`; the form's own placeholder showed a value its validator rejected | caller types the identifier; the composer writes the literal, once |
| ISIN quality | never checked | ISO 6166 check digit, as a separate verdict in its own layer |
| `22F::SETR` | twice — `//BUY` in Trade Details, `//RECE` in Settlement Details | once, in Settlement Details, carrying a transaction type |
| Settlement agents | both required on every message | the one the direction needs; the other stays available |
| Party option | 95R only, and a BIC passed its check | "BIC or proprietary identifier", each validated as itself |
| Controlled codes | a React heuristic, showing bare codes | specification-driven selects, `TRAD — Trade`, one shared vocabulary |
| Samples | four clicks down, under two large cards | the first thing offered, one click, marked as sample data |

Verified: **986 backend tests**, **73 browser tests**, ruff, `mypy --strict`, eslint, `tsc`,
coverage gate, demo-pack gate, secret scan, `git diff --check`, `docker compose build`
(both images), and a manual walk of the wizard in Chrome.

**No capability claim moved.** Every message is still `PARTIAL` with
`authoritativeCompletenessKnown: false`. Nothing here claims SWIFT certification, SR
conformance, registered-BIC verification or ISIN allocation.

## 2. User-reported reproduction

Replayed through the real service rather than read:

```
[MT_FORMAT_INVALID] MT541-B-35B-NONE
  message : Financial Instrument Identification does not match the expected format.
  expected: The subset renders the literal ISIN followed by a validated 12-character identifier.
  current : ISIN US9897778ABC
  suggest : For example: XS0000000001
```

The single error **contradicted itself**: `expected` told the tester to type the literal,
`suggestion` showed an example without it. Both came from configuration, and they disagreed
— the shortest possible statement of the root cause.

Everything else the tester typed was composed without complaint:

```
:22F::SETR//SELL        accepted
:22F::SETR//RECE        accepted — a second SETR in one message
:95R::DEAG//MGTHMEXXX   a BIC accepted in the proprietary field
:95R::REAG//BEBE76XXX   a second agent, also mandatory
```

## 3. Root causes

**ISIN — two owners of one literal.** The studio's canonical value carried `ISIN `; the
legacy composers, the MX definition of the same `businessPath`, the knowledge example and
the Excel *Reference* sheet all used the bare identifier. A single generated workbook
disagreed with itself across two sheets. Enforcement lived in one regex in
`app/authoring/composer.py`, and the form's placeholder was drawn from the knowledge example
— so the studio showed a placeholder its own validator refused.

**SETR — a demonstration taxonomy rendered into a real field.** The Sequence B record
declared `ruleLayer: INTERNAL_RULE_PACK` and `standardsRelease: DEMO_SR2026`; it was never
an ISO 15022 code list. The Sequence E record was labelled `BASE_STANDARD` with an
`OFFICIAL_ISO_15022` source while carrying `RECE`/`DELI` — a mislabel.

**Parties — one YAML anchor for both agents.** `DEAG` and `REAG` came from the same anchor
with `presence: MANDATORY`, applied to all four instructions and all four confirmations, so
a receipt demanded a receiving agent. The client profiles required both as well.

**Party option — option R was not validated as option R.** `_format_valid` checked
`[A-Z0-9._/-]{1,70}`, which does not require the data source scheme that makes a value an
option-R value. `95P` did not exist in the configuration at all.

**Guided and Expert.** They already shared `message_spec()`. Every disagreement came from a
presentation decision made *outside* it — the "is this a dropdown?" heuristic in
`FieldEditor.tsx`, which inferred the control from whether one of the field's examples
happened to appear in its code list. `visibleSpec` was dead code: both branches returned the
same object. And `chooseMode("GUIDED")` cleared `revealed` without clearing `values`, so a
field filled in Expert became invisible **and was still submitted**.

**Samples.** Already produced by the production composer — the architecture was right. They
sat below two large cards under "Or start from a sample", where a tester picked a card and
never saw them.

## 4. Authoritative rules verified

AGENTS.md §14 recorded the SETR defect as needing "an authoritative source, not a guess", and
§16 listed fixing it as pending. **The source was already committed to this repository.**

`backend/config/mx/sese.023.001.11.yaml` is the configured ISO 20022 definition of the same
business message as MT540–MT543. It separates three concepts that the MT configuration had
collapsed into one field:

| sese.023 element | Codes | Concept |
|---|---|---|
| `SttlmTpAndAddtlParams/SctiesMvmntTp` | `RECE`, `DELI` | direction |
| `SttlmTpAndAddtlParams/Pmt` | `APMT`, `FREE` | payment |
| `SttlmParams/SctiesTxTp/Cd` | `TRAD, COLI, COLO, PLAC, PORT, REDM, SUBS, TURN, NETT, OWNE, OWNI` | transaction type |

Its `SctiesTxTp/Cd` node carries, in its own `commonMistakes`, the instruction this change
implements — *"Using the MT direction codes RECE or DELI here; direction is carried by
SctiesMvmntTp"* — and its `searchTerms` name `22F` and `SETR` explicitly, which is the
repository's own statement that `SttlmParams/SctiesTxTp` **is** `22F::SETR`.

The same artifact settles the parties: `DlvrgSttlmPties` is *"required when the account owner
is receiving securities"*, `RcvgSttlmPties` *"required when the account owner is delivering
securities"* — and both are `CONDITIONAL`, not mutually exclusive. It identifies all three
parties by `AnyBIC`, tagged `95P`, and names *"supplying a proprietary code where a BIC is
required"* as a mistake.

**What is still not established**, and is stated as such in `docs/limitations.md`: whether
that transaction-type code list is *complete*. It is this repository's configured subset.

The deterministic resolver (`app/domain/resolver.py`) already implemented the brief's
`Receive + Against Payment → MT541` mapping and needed no change; it remains authoritative
over any AI-suggested intent.

## 5. ISIN implementation

**One owner.** `literalPrefix: 'ISIN '` is configuration on the 35B record. The composer
writes it at render time; the importer strips it; `canonical_field_value()` normalises it in
`MtGenerator.resolve()`, which the browser, the JSON API, Excel and MT import all pass
through. The legacy composers already owned the literal, so for the first time both
composers agree.

**`app/domain/identifiers.py`** — deterministic, no model call, no network:

```
normalise_isin(raw)       strip, uppercase, collapse space, drop a leading "ISIN"
isin_check_digit(body11)  ISO 6166 modulus-10
validate_isin(value)      -> IsinVerdict(format_valid, check_digit_valid, problem)
synthetic_isin(body11)    completes a body into a checksum-valid test value
normalise_bic / bic_format_valid / proprietary_party_valid
```

Normalisation touches **presentation only** — spacing, case, the field's own literal. The
identifier's characters are never rewritten, because silently repairing a check digit would
hide the mistake the tester needs to see.

**Two verdicts, two layers**, because they are two different claims:

| Failure | Layer | ruleId |
|---|---|---|
| length, prefix, character, final character not numeric | `FORMAT` | `MT_ISIN_LENGTH`, `MT_ISIN_PREFIX`, `MT_ISIN_CHARACTER`, `MT_ISIN_CHECK_DIGIT_NOT_NUMERIC` |
| check digit does not match | `CLIENT_PROFILE` | `MT_ISIN_CHECK_DIGIT_INVALID` |

The FIN network validates 35B's field format (`4!c//12!c`); it does not compute an ISO 6166
check digit. Reporting both in `FORMAT` would assert a SWIFT rule that does not exist, and
the check-digit error says so in its own suggestion.

**Assurance is never inflated.** A value passing both is
`STRUCTURALLY_VALID_SYNTHETIC`. `REGISTERED_REAL_IDENTIFIER` is declared and no code path can
produce it; a test asserts that.

**The repository's own sample ISIN was invalid.** `XS0000000001` satisfies the field format
and fails ISO 6166 — the correct digit for that body is `9`. It shipped in every golden
fixture, the demo pack, both Excel templates and three MX definitions. `SAMPLE_ISIN` is now
`synthetic_isin("XS000000000")`, derived rather than typed.

**In the browser:** an `ISIN` badge beside the input, live `12 / 12 characters`, a live
check-digit verdict, automatic uppercase, and paste normalisation.

## 6. SETR correction

- The Sequence B record is **deleted**. `22F::SETR` exists once, in Settlement Details.
- The Sequence E record carries `businessPath: trade.transactionType` and
  `codeList: SETTLEMENT_TRANSACTION_TYPE` — the same list `sese.023` reads.
- An ordinary settlement of a trade is `TRAD`.
- `BUY`, `SELL`, `RECE` and `DELI` are rejected with the labelled list of what is allowed.
- Addressing `22F/SETR` in `TRADDET` returns `MT_UNKNOWN_FIELD`.
- The legacy composers emit one `:22F::SETR//TRAD`; `TransactionType` (BUY/SELL) survives as
  *business intent* that selects the message, and is no longer rendered into a field.

## 7. DEAG / REAG / PSET behaviour

Presence by message, not a global prohibition:

| Messages | Required core party | Optional additional party |
|---|---|---|
| MT540, MT541, MT544, MT545 (receive) | `DEAG` + `PSET` | `REAG` |
| MT542, MT543, MT546, MT547 (deliver) | `REAG` + `PSET` | `DEAG` |

The client profiles were corrected the same way — they had required both agents for every
message, via anchors that paired MT540 with MT542 and MT541 with MT543.

Guided shows the required party with the reason inline — *"Required on a receive
instruction, because the chain that delivers the securities has to be identified."* The other
chain lives under **Add settlement party**. Expert reveals both.

## 8. Party identifier option

`95P` and `95R` now both exist for each of `PSET`, `DEAG` and `REAG`, paired by a
`choiceGroup`. Exactly one satisfies the requirement; supplying both is
`MT_FIELD_OPTION_CONFLICT`, phrased in business words ("BIC or proprietary identifier"), not
option letters.

The form asks **"How do you want to identify this party?" → BIC · Proprietary identifier**
and derives the field option. The proprietary control asks for the data source scheme and the
identifier as two inputs and joins them, so a BIC cannot be typed into it by accident —
`:95R::DEAG//MGTHMEXXX`, the reported message's value, is now refused by name.

BIC validation checks **shape only** (8 or 11, 4 alpha + 2 alpha country + 2 alphanumeric +
optional branch) and says so on screen: *"The format is checked; whether the BIC is
registered is not."* No directory is integrated and none is claimed.

## 9. Dropdown and control system

**`backend/config/knowledge/code_lists.yaml`** — 35 named lists, each code with a `label` and
a `description`, each list with a `source`. A record references one with `codeList:` instead
of restating `allowedCodes`; the loader fills the codes and **refuses at load** if a record
names a list and declares different codes.

**`app/knowledge/presentation.py`** derives the control from the tag and the field option —
which is where ISO 15022 already encodes it (`98a` is a date, `95P` is a BIC, `95R` is a
scheme plus an identifier). Configuration owns the *codes*; this owns the *control*, in one
testable place, with a per-record `inputKind:` override available and currently unused.

The React heuristic is deleted. `FieldControl.tsx` renders from `inputKind` alone:

| `inputKind` | Control |
|---|---|
| `SELECT` | `CODE — Label`, description under it; one allowed value is preselected and read-only |
| `IDENTIFIER` | literal badge, character counter, live check digit, paste normalisation |
| `PARTY_BIC` | uppercase, live length and shape state |
| `PARTY_PROPRIETARY` | scheme + identifier, joined |
| `QUANTITY` / `AMOUNT` | code or currency select + numeric input |
| `DATE` | date picker, rendered to the field's own format |
| `REFERENCE` / `NARRATIVE` | text with `n / max` |

A test walks every configured MT field and fails if one with a code list renders as free
text, or if any code list ships without labels.

## 10. Guided / Expert consistency

Both consume one projection — `message_spec()` — which is also what Excel and
`/api/v1/catalogue` read. Dead `visibleSpec` deleted.

The data-loss path is closed: switching to Guided now keeps any optional field that **holds a
value** revealed, so nothing is hidden while still being submitted. A mode toggle lives in
the selection bar, so switching does not mean starting over. A Playwright test fills a field
in each mode and asserts both survive the round trip.

## 11. Sample improvements

Step 4 leads with **Load typical sample** (marked *Fastest start*) beside **Empty message**,
with the other variants as a secondary row. Loaded values carry a **Sample data** badge that
clears on the first edit.

Every MT540–MT548 sample was audited and regenerated. `TYPICAL` no longer carries the agent
the message does not need — that was what put a receiving agent into every MT541. Sample
selection now runs the *real* specification row, so a candidate that would fail the check
digit or the option-R scheme is rejected during generation rather than shipped.

MT541 typical, generated by the production composer:

```
:16R:SETDET
:22F::SETR//TRAD
:95P::PSET//DEMOGB2LXXX
:95P::DEAG//DEMODEAGXXX
:19A::SETT//USD25000,00
:16S:SETDET
```

MT543 is the mirror image, with `:95P::REAG//DEMOREAGXXX`. MT540 and MT542 carry no `19A` at
all — the field is not in their specification, so the form never asks.

Synthetic values are labelled as such: the ISIN is checksum-valid and unregistered; the BICs
are correctly shaped and unregistered.

## 12. Excel and API changes

**Excel.** A new **Codes** sheet lists every controlled code with its label and description
per message, sequence, tag, qualifier and option. The **Reference** sheet gains *Input kind*,
*Literal written by the studio* and *Max length*. The **Scenarios** sheet gets real per-cell
dropdowns on `Value` for fields with a finite list, capped by Excel's 255-character inline
limit rather than silently omitted. The **Read me** sheet states the canonical form:

> Enter the 12-character identifier only, for example `XS0000000009`. Do **not** type the
> word ISIN — the studio writes it. A value that arrives with the prefix already on it is
> accepted and normalised, so an older sheet keeps working.

**API.** `SpecField` and `IntelligenceDetail` gain `inputKind`, `allowedValues[]`
(`code`/`label`/`description`), `codeList`, `literalPrefix`, `userEntersLiteralPrefix`,
`identifierTypes`, `maxLength`, and `choiceGroup` for MT. Additive — `allowedCodes` is still
populated, so existing clients are unaffected.

**One vocabulary.** A test asserts the MT and MX transaction-type lists are the same codes
*and* the same labels, and that the Excel reference rows carry the same `allowedValues` as
the catalogue.

## 13. Import compatibility

`Parse(":35B:ISIN XS0000000009") → "XS0000000009"` and
`Compose("XS0000000009") → ":35B:ISIN XS0000000009"`. Exactly one literal; never `ISIN ISIN`;
never lost. The legacy `/api/messages/import` path was corrected too — it stored the rendered
value and would have recomposed `ISIN ISIN …`.

The existing `Compose(Parse(Compose(v))) == Compose(v)` assertion over every sample of every
configured message and all 17 golden fixtures still holds, and a directed test was added
because that identity would also hold if both sides were wrong.

## 14. Files changed

87 files, +5,533 / −735.

**New** — `app/domain/identifiers.py`, `app/knowledge/code_lists.py`,
`app/knowledge/presentation.py`, `config/knowledge/code_lists.yaml`,
`frontend/lib/identifiers.ts`, `frontend/components/studio/FieldControl.tsx`, four test files.

**Configuration** — `settlement_v1.yaml` (SETR, parties, 35B, 36B), `corporate_actions_v1.yaml`,
`penalties_v1.yaml`, `settlement_command_v1.yaml`, both client profiles, three MX definitions.

**Backend** — `authoring/composer.py`, `authoring/parser.py`, `knowledge/{loader,models}.py`,
`specifications/{models,registry}.py`, `raw/validator.py`, `studio/{models,catalogue,samples,excel,intelligence}.py`,
`studio/mt/{generator,parser}.py`, four legacy composers.

**Frontend** — `studio-types.ts`, `FieldEditor.tsx`, `CreateMessage.tsx`, `ValidationPanel.tsx`,
`Automation.tsx`.

**Regenerated** — 9 golden fixtures, `demo/`, `docs/generated/message-coverage.md`.

**Docs** — `AGENTS.md` (§2, §5, §7, §13, §14, §16), `docs/limitations.md`,
`docs/for-automation-testers.md`, `docs/how-messages-are-built.md`, `README.md`,
`demo/README.md`.

## 15. Tests

**986 backend** (was 770) and **73 browser** (was 61).

- `test_identifiers.py` — normalisation, every malformed shape by name, ISO 6166 arithmetic,
  the format/check-digit split, and that no path can claim registration.
- `test_financial_instrument_identifier.py` — 35B through the JSON API, Excel, a legacy
  spreadsheet still carrying the prefix, MT import and round trip; byte-identical Block 4
  from JSON and Excel; every sample of every message carries a checksum-valid identifier.
- `test_settlement_domain_rules.py` — SETR once, in the right sequence, as `TRAD`; the four
  old codes rejected; party requiredness parametrised over all eight messages; the option
  conflict; free-of-payment messages having no cash field to ask for.
- `test_field_presentation.py` — every configured code list is a labelled selector; the
  server still rejects an invalid code posted directly; one vocabulary across catalogue,
  Excel and Message Intelligence; and a guard that a code list can never leak onto an
  unrelated field again.
- `mt-authoring.spec.ts` — the brief's Scenarios A–E in a real browser.

Row-count assertions were updated deliberately and annotated with why; the duplicated
hardcoded count in the API test now derives from the registry, per AGENTS.md §13.24.

## 16. Browser verification

Chrome, manually, before and after the automated suites. The wizard was walked to a generated
FIN message for MT541 and MT543; the ISIN control, the party question, the SETR dropdown, the
validation panel and the proof sheet were each inspected. Console and network were clean —
the one dev-overlay warning is a `bis_skin_checked` attribute injected by a browser extension
before React loads, not application code.

Three defects were found this way and fixed:

1. **`maxLength` truncated a paste before normalisation.** `ISIN XS0000000009` became
   `ISIN XS00000` and normalised to `XS00000`. The length is now enforced *after*
   normalising. Playwright found this; typing had not.
2. **Preselecting a single-value dropdown during render aborted the catalogue fetch**, which
   surfaced as *"the studio API could not be reached"* against a healthy backend. Moved into
   an effect.
3. **The required-field counter counted field options**, so a complete MT541 read "10 of 11".
   It counts business values now.

Two smaller ones: the party controls printed their rule twice, and an 11-code list showed a
filter box whose label was ambiguous with the field's own.

## 17. Before and after

Same business facts, MT541.

**Before**

```
:35B:ISIN XS0000000001          caller typed the literal; the ISIN fails its check digit
:22F::SETR//BUY                 a demonstration taxonomy in a real field
:22F::SETR//RECE                a direction in a transaction-type field
:95R::PSET//SYNTH/SYNTHPSET01
:95R::DEAG//SYNTH/SYNTHDEAG01
:95R::REAG//SYNTH/SYNTHREAG01   required, on a receive instruction
```

**After**

```
:35B:ISIN XS0000000009          caller typed XS0000000009; the composer wrote ISIN
:22F::SETR//TRAD                the settlement of a trade, once, in Settlement Details
:95P::PSET//DEMOGB2LXXX         identified by BIC, under the option that carries a BIC
:95P::DEAG//DEMODEAGXXX         the chain that delivers — what a receipt needs
```

### The reported message

**Does it now fail for the right reasons?** Yes — five errors, each naming a real defect,
none spurious:

| ruleId | What it says |
|---|---|
| `MT_UNKNOWN_FIELD` | `22F/SETR` is not a field of MT541 in sequence TRADDET |
| `MT_ISIN_CHECK_DIGIT_NOT_NUMERIC` | The final ISIN character must be a numeric check digit |
| `MT_CODE_NOT_ALLOWED` | `RECE` is not a settlement transaction type — `TRAD (Trade)`, … |
| `MT_FORMAT_INVALID` ×2 | `MGTHMEXXX` / `BEBE76XXX` need a data source scheme, or the BIC form |

**Can it be corrected through the UI?** Yes, and each error says how. The ISIN field shows
the count and the check-digit state as you type; the transaction type is a labelled dropdown
where `RECE` cannot be chosen; the party question offers **BIC**, which is what those two
values are.

**Does it generate afterwards?** Yes. Corrected only where the studio named a defect —
check digit `C → 6`, `SETR → TRAD`, `TRADDET` SETR removed, the agent moved to `95P` with a
valid BIC length, the unneeded `REAG` dropped:

```
{1:F01DEMOGB2LAXXX0001000001}
{2:I541DEMOUS33XXXXN}
{4:
:16R:GENL
:20C::SEME//MT56765GHT1
:23G:NEWM
:16S:GENL
:16R:TRADDET
:98A::TRAD//20260817
:98A::SETT//20260817
:35B:ISIN US9897778AB6
:36B::SETT//UNIT/10
:16S:TRADDET
:16R:FIAC
:97A::SAFE//ABCG767547
:16S:FIAC
:16R:SETDET
:22F::SETR//TRAD
:95P::DEAG//MGTHMEXX
:19A::SETT//USD10,00
:16S:SETDET
-}
```

`valid: True`. (`US9897778AB6` is structurally valid and carries a correct check digit; it is
synthetic and not claimed to be allocated.)

## 18. Known limitations

- **Coverage is still a repository-configured subset.** Every message remains `PARTIAL`.
- **The transaction-type code list is not established as complete.** It matches this
  repository's ISO 20022 definition of the same message, which is itself a configured subset.
- **BIC format ≠ BIC registration.** No directory is integrated. The UI says so.
- **ISIN check digit ≠ ISIN allocation.** Arithmetic only. Synthetic values are labelled
  `STRUCTURALLY_VALID_SYNTHETIC`; `REGISTERED_REAL_IDENTIFIER` is unreachable by design.
- **The check-digit rule is a client-profile decision**, currently an error in both demo
  profiles. A market that accepts unverified identifiers would configure it differently.
- **`28E` remains a text input.** Its code is half of a page-and-continuation value, so a
  whole-cell dropdown would drop the page number. Its vocabulary is published.
- **Four MX lifecycle specifications remain `UNVERIFIED`** — untouched by this work.

## 19. CI and PR status

| | |
|---|---|
| Branch | `feat/mt-authoring-ux-correctness` |
| Commit | `af327e5` |
| PR | see §19 note below |
| Local gates | `make check`, `make e2e`, `make secret-scan`, `make coverage`, `make demo-pack-check`, `git diff --check`, `docker compose config --quiet`, `docker compose build` — all pass |

The PR is opened against `main` and **not merged**; no instruction in this repository
authorises an automatic merge.
