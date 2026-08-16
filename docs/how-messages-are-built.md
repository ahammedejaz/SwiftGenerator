# How messages are built

**A plain explanation of MT and MX, and what this tool does to produce one.**

You do not need this to use the tool. Read it when you want to know what you are looking at.

---

## MT: the telegram

MT is the older format (its formal name is ISO 15022). It was designed when messages went
down a telex line, and it still looks like it.

An MT message is five **blocks**. Think of posting a letter:

| Block | Postal equivalent | Who fills it in |
|---|---|---|
| `{1:}` | Your return address | Configured on the client profile |
| `{2:}` | The recipient's address, and "this is a settlement instruction" | Profile + the message type you chose |
| `{3:}` | An optional reference you write on the envelope | You, if you want one |
| `{4:}` | **The letter itself** | You — this is where your data goes |
| `{5:}` | The postmark the post office stamps on it | **The network. Not this tool.** |

A real message:

```
{1:F01DEMOGB2LAXXX0001000001}     ← from: DEMOGB2L, terminal A, branch XXX
{2:I541DEMOUS33XXXXN}             ← to: DEMOUS33, message type 541, normal priority
{4:                                ← the content starts
:16R:GENL                          ← "General Information section starts here"
:20C::SEME//TESTREF001             ← my reference for this message
:23G:NEWM                          ← this is a new instruction (not a cancellation)
:16S:GENL                          ← "General Information section ends here"
:16R:TRADDET                       ← "Trade Details section starts here"
:98A::TRAD//20260814               ← trade date
:98A::SETT//20260818               ← settlement date
:35B:ISIN XS0000000001             ← which security
:16S:TRADDET
-}                                 ← the content ends
```

### How to read a line

```
:98A::SETT//20260818
 │ │   │     └── the value
 │ │   └── qualifier: which kind of date? SETT = settlement
 │ └── option: how the value is formatted. A = a plain date
 └── tag: 98 means "date and time"
```

So `98A::SETT//` is "date, plain format, the settlement one". The same tag `98A` with
qualifier `TRAD` is the trade date. That is why a tag alone is not enough to identify a
field — you need the tag, the qualifier, **and** which section it is in.

### Sections

`:16R:GENL` … `:16S:GENL` is a section, called a **sequence**. `16R` opens, `16S` closes.
Sequences group related fields, and some can repeat.

The four you will meet most:

| Code | Contains |
|---|---|
| `GENL` | References and what kind of instruction this is |
| `TRADDET` | Dates, the security, the quantity |
| `FIAC` | The safekeeping account |
| `SETDET` | Who is delivering, who is receiving, where it settles, how much cash |

---

## MX: the XML one

MX is the newer format (ISO 20022). Same information, different shape:

```xml
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:sese.023.001.11">
  <SctiesSttlmTxInstr>
    <TxId>TEST001</TxId>
    <SttlmTpAndAddtlParams>
      <SctiesMvmntTp>RECE</SctiesMvmntTp>   <!-- receiving securities -->
      <Pmt>APMT</Pmt>                        <!-- against payment -->
    </SttlmTpAndAddtlParams>
    <TradDtls>
      <SttlmDt><Dt><Dt>2026-08-18</Dt></Dt></SttlmDt>
    </TradDtls>
    <FinInstrmId>
      <ISIN>XS0000000001</ISIN>
    </FinInstrmId>
    <SttlmAmt>
      <Amt Ccy="USD">25000.00</Amt>
      <CdtDbtInd>DBIT</CdtDbtInd>
    </SttlmAmt>
  </SctiesSttlmTxInstr>
</Document>
```

**Why is the date nested three deep?** Because ISO 20022 lets a settlement date be either
an exact date *or* a code meaning something like "on receipt", and the outer element is the
choice between them. You are picking the "an exact date" branch. The tool handles this for
you — you supply the leaf, it builds the wrapping.

**The `xmlns`** is the namespace, and it is version-specific. `sese.023.001.11` is version
11 of message sese.023. The namespace has to match the version exactly or a strict receiver
will reject the message.

### The header

An MX message travels with a **Business Application Header** (`AppHdr`) alongside the
Document. The Document says *what*; the header says *who, to whom, and when*:

```xml
<AppHdr xmlns="urn:iso:std:iso:20022:tech:xsd:head.001.001.03">
  <Fr><FIId><FinInstnId><BICFI>DEMOGB2LXXX</BICFI></FinInstnId></FIId></Fr>
  <To><FIId><FinInstnId><BICFI>DEMOUS33XXX</BICFI></FinInstnId></FIId></To>
  <BizMsgIdr>SESE023202608161520</BizMsgIdr>
  <MsgDefIdr>sese.023.001.11</MsgDefIdr>
  <CreDt>2026-08-16T15:20:41Z</CreDt>
</AppHdr>
```

`MsgDefIdr` must name the same version the Document's namespace names. The tool derives it
from the message you chose, so it cannot drift.

---

## The same instruction, both ways

| Business meaning | MT | MX |
|---|---|---|
| My reference | `:20C::SEME//TESTREF001` | `<TxId>TESTREF001</TxId>` |
| Receiving or delivering | implied by the message type | `<SctiesMvmntTp>RECE</SctiesMvmntTp>` |
| Against payment? | implied by the message type | `<Pmt>APMT</Pmt>` |
| Settlement date | `:98A::SETT//20260818` | `<SttlmDt><Dt><Dt>2026-08-18</Dt></Dt></SttlmDt>` |
| The security | `:35B:ISIN XS0000000001` | `<ISIN>XS0000000001</ISIN>` |
| Quantity | `:36B::SETT//UNIT/1000` | `<SttlmQty><Qty><Unit>1000</Unit></Qty></SttlmQty>` |
| Amount | `:19A::SETT//USD25000,00` | `<Amt Ccy="USD">25000.00</Amt>` |
| Where it settles | `:95a::PSET//` | `<Dpstry><Id><AnyBIC>…</AnyBIC></Id></Dpstry>` |

Three differences that catch people out:

1. **Dates.** MT: `20260818`. MX: `2026-08-18`. The tool detects the wrong one and suggests
   the right one.
2. **Decimals.** MT: `25000,00` (comma). MX: `25000.00` (full stop). Genuinely opposite.
3. **ISIN.** MT writes `ISIN XS0000000001` with the literal word. MX writes the code alone.

MT541 and MT543 are separate message types because direction is baked into the type. MX has
one message type and puts direction in a field.

---

## What the tool does to build one

### 1. It reads a specification

Not code — YAML. For MT, `backend/config/knowledge/` holds one record per tag, and
`backend/config/specifications/` says which sequences a message has. For MX,
`backend/config/mx/` holds the element tree.

Adding a field is a YAML edit. It then appears in the API, the UI, the Excel template and
Message Intelligence, with no code change.

### 2. It works out which field you meant

You can say `MT541-A-20C-SEME` or `GENL / 20C / SEME`. Either resolves to the same
specification row. An address matching nothing becomes an error naming your input.

### 3. It validates in layers

Each layer is reported separately, so you can see where a message went wrong:

| Layer | Question |
|---|---|
| Canonical | Do these inputs address real fields? |
| Structure | Is everything required present? |
| Format | Does each value match its shape? |
| Business rules | Do the values agree with each other? |
| Client profile | Does this client allow this currency, this reference length? |
| FIN envelope *(MT)* | Can we build a real envelope? |
| XML well-formed *(MX)* | Does the XML parse? |
| XSD *(MX)* | Does it match the schema? |
| Header consistency *(MX)* | Does the header name the same version as the document? |

A business rule is a cross-field rule. Examples the tool enforces:

- settlement date cannot precede trade date
- `Pmt = APMT` requires a settlement amount; `Pmt = FREE` forbids one
- an MX receipt must name who is delivering
- cancelling requires the reference of the message being cancelled
- a status advice must actually report a status

### 4. It writes the message in specification order

Field order is not cosmetic — a receiver will reject an out-of-order message. Order comes
from the specification, so it cannot depend on the order you happened to type things.

### 5. It wraps it, honestly

**MT** gets Blocks 1, 2, optional 3 and optional 5, built from the client profile.

**MX** gets an `AppHdr`, and both parts go inside whatever transport wrapper the profile
configures.

Every value carries a label saying where it came from:

| Label | Meaning |
|---|---|
| You entered this | from your input |
| From the client profile | configured by whoever set up the profile |
| Built by the platform | derived from your choices |
| Your messaging interface adds this | **the tool will not produce it** |
| The network adds this | **the tool will not produce it** |

Those last two are the point. A real SWIFT interface assigns session and sequence numbers;
the network computes authentication trailers. This tool refuses to invent them. If it
cannot get one legitimately, FIN output fails with a message naming exactly what is missing,
rather than filling in something plausible.

---

## The XSD question

For MX, the tool validates the XML against a schema — and always tells you which schema:

| Source | Where it comes from | What it proves |
|---|---|---|
| `OFFICIAL` | An ISO 20022 `.xsd` you place in `backend/config/mx/xsd/official/` | Real conformance |
| `SUBSET_DERIVED` | Generated from this repository's YAML | The document matches *this repository's* subset |

`SUBSET_DERIVED` is the default because official schemas are licensed and not included
here. It is a genuine XSD compiled by libxml2 and it independently catches element order,
cardinality, datatypes, enumerations and missing attributes — the tests prove each of those.
It is **not** authoritative conformance, and the tool never claims it is.

Drop an official schema into that folder and the validator prefers it automatically. That
is the single step from "checked against our subset" to "checked against the standard".

---

## Samples

Every message has samples in three depths:

| Variant | Contents |
|---|---|
| `MINIMAL` | Every required field and nothing else |
| `TYPICAL` | Required plus the optional fields a real message normally carries |
| `FULL` | Everything the configured subset supports |

Samples are **inputs**, not stored text. They are pushed through the same composer your
message uses, so a sample cannot show you something the tool would not actually produce.

Two mechanisms keep them honest:

- **Candidate-and-check** — each field offers several plausible values and the first one
  the platform's own validator accepts is used.
- **Validate-and-repair** — the candidate set is generated, validated, and any field the
  validator names as missing is added back, for a few rounds. This is how a sample
  automatically picks up a conditional block that its own values made mandatory.

All 46 samples across all 23 message types validate. A test asserts it, so a specification
change that breaks one fails the build.
