# For manual testers

**You need a SWIFT message. You have never made one. This page gets you there in five
minutes.** No prior knowledge assumed.

---

## First, what am I making?

A **message** is how one bank tells another bank to do something. Like an email with very
strict rules about what goes where.

You will be making one of these:

- **MT541** — "please send me these securities, I will pay for them"
- **MT543** — "I am sending you these securities, please pay me"
- **MT548** — "here is the status of that instruction you sent me"
- **sese.023** — the same idea as MT541, written in the newer XML format

Your ticket almost certainly names one. If it says something starting with `MT`, that is
the old format. If it says something like `sese.023`, that is the new one. The tool handles
both.

---

## Make your first message

Open <http://localhost:3000>. You land straight on **Create Message**. Six steps.

### Step 1 — Which format?

Two big cards: **MT** and **MX**. Your ticket tells you which. If it says MT541, click MT.

### Step 2 — Which business area?

For settlement instructions, that is **Securities Settlement**. Only areas that actually
have messages are shown, so you cannot pick a dead end.

### Step 3 — Which message?

A list, each with a plain-English line under it:

> **MT541** — Receive Against Payment
> *Instruct the receipt of securities against a cash payment.*

Click yours.

### Step 4 — How do you want to fill it in?

- **Guided** *(recommended)* — shows only the fields this message needs
- **Expert** — shows every field the tool supports, all at once

Underneath there is also **start from a sample**. This is the shortcut:

| Sample | What you get |
|---|---|
| **Minimal valid** | Only what is required — the smallest thing that works |
| **Typical** | The required fields plus the ones a real message normally has |
| **Full** | Everything, so you can see the whole shape |

**If you are in a hurry, click Typical.** You get a complete, valid message pre-filled.
Change the two or three values your ticket cares about and generate. This is the fastest
honest path and there is nothing wrong with it.

### Step 5 — Fill in the boxes

Each row looks like this:

```
Intended Settlement Date              ℹ
Required   :98A::SETT//                    [ 20260818                    ]
                                           Date is rendered as YYYYMMDD.
```

- The **big label** is the business name — that is the one to read.
- The **small grey code** is the technical tag. Ignore it unless you need it.
- The **red "Required" chip** means the message will not generate without it. "Conditional"
  means it depends on other choices. "Optional" means it is up to you.
- **Click the ℹ** for what the field means, why it exists, the exact expected format, a
  worked example, common mistakes, and what breaks if you leave it out.

Two buttons worth knowing:

- **+ Add optional field** — the tool hides optional fields so you are not staring at
  eighty empty boxes. Click this when you actually need one.
- **+ Add another** — for parts of a message that can repeat.

### Step 6 — Validate, then Generate

**Validate** checks without producing anything. You get one of two answers:

> ✅ **Ready to generate**
> Everything required is present and every value matches its expected format.

or

> ⚠ **3 issues need attention**
> Fix the items below and the message will generate.

Each issue tells you the field, the problem, what was expected, and what to do:

> **Intended Settlement Date** — Error
> The settlement date is earlier than the trade date.
> **What to do:** Set the settlement date on or after the trade date.
> Expected: A date on or after 20260814 · You entered: 20260801

Press **Generate message** and the message appears on a dark panel below.

---

## Reading the result

```
 1  {1:F01DEMOGB2LAXXX0001000001}
 2  {2:I541DEMOUS33XXXXN}
 3  {4:
 4  :16R:GENL                                    Sequence marker
 5  :20C::SEME//TESTREF001                       Sender's Message Reference
 6  :23G:NEWM                                    Function of the Message
 7  :16R:TRADDET                                 Sequence marker
 8  :98A::SETT//20260818                         Intended Settlement Date
...
```

- The **numbers on the left** are line numbers.
- The **grey text on the right** tells you which of your fields produced that line. This is
  the fastest way to check the tool put your value where you expected.
- **Copy** puts the whole message on your clipboard.
- **Download** saves it as a file, exactly as generated — no extra characters, no reformatting.
- The **tabs** switch between output forms:
  - **Block 4 only** — just the content, no envelope
  - **FIN message** — the complete thing, with all the blocks
  - **Canonical JSON** — the same data as structured JSON, for a script to read

### "Where did that first line come from? I did not type it."

Correct — and the tool will tell you. Expand **Envelope values** underneath:

| Value | Source |
|---|---|
| Sender logical terminal | From the client profile |
| Session number | From the client profile |
| Message type `541` | Built by the platform |
| Trailer | *not written* — the network adds this |

Some values are yours, some come from configuration, some the tool works out, and some it
**deliberately refuses to invent** because a real SWIFT interface or the network assigns
them. That last row is the tool being honest rather than plausible.

---

## Making many messages at once

Go to **Bulk / Excel**.

1. **Download the MT template.** It arrives with three sheets:
   - **Scenarios** — the rows you edit, already filled in with a working example
   - **Reference** — every field the message supports, with format and example. Required
     rows are shaded.
   - **Read me** — what each column means
2. **Edit the Scenarios sheet.** One `ScenarioID` per message. All rows sharing an ID build
   one message together.
3. **Drop it back on the page.** You get one result per scenario. A scenario that fails
   does not stop the others.

---

## Looking things up

**Message Intelligence** answers "what on earth is `PSET`?"

Type anything you have in front of you — a tag (`95R`), a qualifier (`PSET`), an XML
element (`SttlmDt`), or plain English (`settlement amount`). You get:

- what it means in business terms
- why it is used
- the exact expected format
- what it is called in both MT and MX
- an example
- common mistakes
- **the field shown inside a real generated message**

No AI is involved and no model is called. These are written answers from the tool's own
reference data, so they are the same every time.

---

## When something goes wrong

| What you see | What it means |
|---|---|
| **"The studio API could not be reached"** | The backend is not running. Start it with `make backend`. |
| **"Settlement Amount is required"** | A required field is empty. The message names it; scroll up to it. |
| **"MX uses YYYY-MM-DD, not the MT format YYYYMMDD"** | You used an MT-style date in an MX message. The tool suggests the corrected value. |
| **"Coverage is a configured subset"** (amber note) | Not an error. It means the tool supports part of the standard, not all of it. Read [limitations.md](limitations.md). |

You will never see a stack trace or a database error. If you do, that is a bug worth
reporting.

---

## Handing the message over

Whatever your downstream test system needs:

- **Copy** — clipboard, paste it wherever
- **Download** — a file with the exact bytes, nothing added
- **Recent Messages → Evidence ZIP** — every output form plus the validation report and
  the inputs you used. Good for attaching to a test result.

The message you download is byte-for-byte what the API returns. Nothing is reformatted for
display and then saved differently.
