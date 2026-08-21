# MVP acceptance checklist

For a tester. No SWIFT knowledge and no architecture knowledge assumed. Work top to bottom
and tick each box. Anything you cannot tick is a finding — write down what you saw and what
you expected.

**Setup:** open a terminal in the project folder and run `make quickstart`, or run
`make dev` and open <http://127.0.0.1:3000> in Chrome. Both spellings of the address work
(`127.0.0.1` and `localhost`).

---

## A · It starts

- [ ] The page loads and the top bar shows six items: Create Message, Bulk / Excel, Message Intelligence, Validate, API & Automation, Convert Message.
- [ ] The MT card shows a count of messages. The MX card shows a count of messages.
- [ ] Nothing says "Loading…" for more than a couple of seconds.
- [ ] Press F12, open Console, reload. There are **no red errors** from the application. (Messages mentioning a browser extension, `bis_skin_checked` or `__processed_` are not ours.)

## B · Create one message the fast way

- [ ] **Choose MT** → type `MT103` in the search box.
- [ ] Two rows appear, one marked *SR2025 · current release* and one *SR2026 · future release*. Pick either.
- [ ] A coloured banner explains what the platform does and does not claim about this message.
- [ ] Click **Load minimal valid sample**. The form fills in.
- [ ] Every field has a name in plain English and a sentence under the box saying what it accepts.
- [ ] Click **Validate**. It says the message is ready.
- [ ] Click **Generate message**. A complete message appears, numbered line by line.
- [ ] Click **Copy**. Paste it somewhere — the whole message is on the clipboard.
- [ ] Click **Download**. A file is saved.

## C · The same message, with the assistant

- [ ] Go back and click **AI Typical sample**.
- [ ] A strip appears saying the sample was **validated by the deterministic engine**.
- [ ] Click **AI Typical sample** a second time. The strip now says **Cache: HIT — 0 model calls**.
- [ ] The values look like realistic test data, not `xxxxx`.
- [ ] Generate the message. It is valid.

*If your environment has no AI configured, the AI buttons say so clearly and the sample
buttons in section B still work. That is expected, not a fault.*

## D · Change something and see it refuse

- [ ] Clear a required field. **Validate**.
- [ ] The error names the field in business words (for example *"Settlement Amount is required."*), not a code.
- [ ] It tells you what was expected and suggests what to do.
- [ ] Put the value back. Validate passes.

## E · Read a message back in

- [ ] On the first screen click **Import a message**.
- [ ] Paste the message you generated in section B.
- [ ] It is recognised, the form fills in, and the comparison says the two messages are the same.
- [ ] Change one value and generate again. The comparison now shows exactly that one difference, and says it was your edit.

## F · An ISO 20022 message

- [ ] Start again, **Choose MX**, pick `sese.023`.
- [ ] Load a sample, generate. XML appears with a header and a document.
- [ ] The validation list shows a line for **XSD** and it passed.
- [ ] Download it.

## G · Convert MT to ISO 20022

- [ ] Create and generate an `MT103` (SR2026), then click **Convert to MX** underneath it.
- [ ] The Convert screen shows the message you just made and names the mapping pack.
- [ ] It states the evidence behind the mapping and lists its limitations before anything runs.
- [ ] Tick the box that says you understand this is a candidate, then **Preview conversion**.
- [ ] A report appears with counts: Mapped, Derived, Missing, Not represented.
- [ ] Under **Required target information** each missing item asks a question in words.
- [ ] Fill them in and click **Generate target**. If it asks for one more, fill that too.
- [ ] A valid `pacs.008.001.14` document appears and the XSD line passed.
- [ ] The table below labels every value **Mapped**, **Derived** or **You supplied**.
- [ ] Repeat for `MT202` → `pacs.009` and `MT541` → `sese.023`.

## H · Spreadsheet

- [ ] **Bulk / Excel** → **Download MT template**.
- [ ] Open it. There are sheets for Scenarios, Reference, Codes and Read me.
- [ ] Upload the file back without changing it. It reports 3 messages generated, 0 failed.
- [ ] Do the same with the MX template.
- [ ] Change one value in the spreadsheet, upload again, and see that value in the output.

## I · Look something up

- [ ] **Message Intelligence** → click the `PSET` chip.
- [ ] Results appear for both MT and MX, with what it means, why it is used, the expected format and common mistakes.
- [ ] Type something nonsensical. It says plainly that nothing matched — it does not guess.
- [ ] Click **Ask about this field**. An answer appears with the sources it came from.

## J · For an automation tester

- [ ] **API & Automation** → the same request is shown in curl, Java / REST Assured, Python and JavaScript.
- [ ] Copy the curl example, run it in a terminal, and get a message back.
- [ ] Click **Swagger UI**. The full API opens and you can try a call from the page.

## K · Everything else on the menu

- [ ] **Validate** — paste a message, get a verdict, without saving anything.
- [ ] **Recent Messages** — everything you generated is listed and can be reopened and downloaded again.
- [ ] **AI & Knowledge Usage** — counts for model calls, tokens, cache hits and retrieval. No message content anywhere on the page.
- [ ] **Knowledge Base** (via Advanced) — the sources, how many were indexed, and when it last ran.

## L · Awkward things

- [ ] Reload the page in the middle of filling a form. Nothing crashes.
- [ ] Use the browser Back and Forward buttons across the wizard. Nothing crashes.
- [ ] Paste a URL for a screen directly into the address bar. It loads.
- [ ] Make the window narrow, or open the site on a phone. Nothing runs off the side of the screen.
- [ ] Paste something that is not a message into Import. It explains the problem — no stack trace, no blank screen.
- [ ] Click every button you can find. **None of them do nothing.**

## M · Finish

- [ ] Console still shows no application errors.
- [ ] Network tab shows no failed requests to `/api/`.
- [ ] Nothing on any screen claims the product is SWIFT certified, compliant, or connected to the SWIFT network.

---

### What is expected to be limited

These are boundaries, not faults. Do not raise them as defects:

- Thirteen MT system message types cannot be generated at all; the catalogue lists them and says why.
- Business-rule validation beyond structure and format is not claimed for preview-lane messages, and the banner says so.
- No mapping is described as authoritative — every conversion is a candidate or a synthetic preview and is labelled.
- XSD validation is against a schema derived from this repository's own subset unless your operator supplied the official one.
