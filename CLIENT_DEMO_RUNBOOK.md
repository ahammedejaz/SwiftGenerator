# Client demo runbook

Twenty minutes, six steps, no slides. Everything below is a real generated message — nothing
is mocked, staged or pre-recorded.

The synthetic inputs and expected outputs are in [`demo/`](demo/README.md).

---

## Start

```bash
make backend      # terminal 1 → http://127.0.0.1:8000
make frontend     # terminal 2 → http://127.0.0.1:3000
```

or, if you would rather not install anything:

```bash
docker compose up --build
```

Then open **<http://127.0.0.1:3000>**. No `.env`, no API key, no database setup.

> First run only: `make install` then `make migrate`.

**Before you present:** run `make check` once. If it is green, everything in this runbook
works. If a demo step fails, that is a real defect, not a setup problem.

---

## Demo order

### 1. Create Message — the landing screen (1 min)

Six numbered steps across the top, one decision each. Say: *"A tester who has never seen a
SWIFT message can follow this. Every field explains itself."*

Point out the footer once, then leave it: the platform states on every screen that it does
not transmit, validate or certify through the Swift network.

### 2. MT541 — a complete FIN message (4 min)

**Choose MT → Securities Settlement → MT541 → Typical.**

The form is filled with a coherent scenario. Change **Sender's Message Reference** to
something recognisable, then **Validate**, then **Generate message**.

Three things to point at:

- The **proof sheet** is line-numbered, and the grey text on the right names the field that
  produced each line. That is the fastest way for a tester to check their value landed where
  they expected.
- **Envelope values** underneath shows where every value came from — profile, platform, or
  *not written*. The trailer row says the network adds it and the platform will not invent it.
- **Download** gives the exact bytes, no reformatting.

### 3. Message Intelligence — PSET (3 min)

Search **`PSET`**. One deterministic lookup returns: what it means, why it is used, expected
format, when it applies, which sequence it sits in, common mistakes, an example, and **the
line as it appears in a real generated message**.

Then search **`SttlmDt`** to show the same for ISO 20022: the full XPath, cardinality `1..1`,
the representation class, and the rendered element.

Say: *"This is the SME dependency the tool is designed to remove. No model is called — a
Playwright test watches the network and asserts it."*

### 4. sese.023 — the same business event in ISO 20022 (3 min)

**Choose MX → Securities Settlement → sese.023 → Typical → Generate.**

Point out that it is an **AppHdr plus a Document**, that the schema layer reports which
schema it used, and that MT and MX never share a rendering path.

### 5. Import and compare (4 min)

Back to **Create Message**, step 1, **Import a message**. Paste the FIN message from step 2
(or `demo/expected/MT541.fin`).

The studio identifies it from Block 2 — nobody tells it what it is. Change one value and
**Generate message**.

**Original and regenerated** is the part to dwell on. Every difference carries a reason:

| Shown as | Means |
|---|---|
| You changed this | Your edit |
| Written the studio's way | Same meaning, specification order |
| Never generated | Trailers and signatures the network supplies. **Not a fault** |
| Could not be imported | Outside the configured subset — reported, never dropped silently |
| Unexplained | The only one worth investigating |

If you have a spare minute, paste the same message with `{5:{CHK:123456789ABC}}` appended.
The trailer is shown as *never generated*, and the verdict still reads *every difference is
accounted for*.

### 6. Excel and the API (4 min)

**Bulk / Excel → download the MT template.** It is generated from the specification, so the
columns cannot be wrong. Upload it back.

Then show **API & Automation**: the same call in curl, Java, Python and JavaScript, and the
full endpoint list. Say: *"The browser calls exactly these endpoints. There is no capability
a manual tester has that an automation tester cannot reach."*

`demo/curl.md` and `demo/RestAssuredDemoTest.java` are copy-paste ready.

### 7. AI interpretation — only if credentials are configured (2 min)

If `OPENROUTER_API_KEY` is set, show the natural-language screen. **If it is not, skip this
step** — the platform reports `AI interpretation is not configured. Use the deterministic
form instead.` and everything else keeps working.

That is the point worth making either way: **the model never generates the message.**

---

## Talking points

- **One platform, two audiences.** A manual tester uses the wizard; an automation tester
  POSTs JSON or uploads a spreadsheet. Same backend, same code path, same result.
- **The browser calls the same `/api/v1` endpoints automation calls.** No UI-only capability.
- **AI interprets intent; it never produces the message.** Rendering, parsing, validation,
  Excel and Intelligence are deterministic. Model calls are optional, cached, and off by
  default.
- **MT FIN and MX XML are deterministic.** The same inputs produce the same bytes; golden
  files fail on any change.
- **Tag and element Intelligence reduces SME dependency** — meaning, format, mistakes and a
  real example for any tag or element, with no model call.
- **Excel and the API let a regression framework consume generated messages** — raw message
  plus structured findings in one response.
- **Import, round trip and comparison support debugging real messages.**
  `Compose(Parse(Compose(v))) == Compose(v)` is asserted for every sample of every configured
  message.
- **Nothing is invented.** Session and sequence numbers, MAC/CHK trailers and the MX `Sgntr`
  are allocated by a messaging interface or the network; the platform fails closed with a
  named error rather than fabricating one.

---

## Honest limitations — say these out loud

Do not let the demo imply more than it is. All of this is stated in the product itself.

- **No SWIFT certification is claimed or implied.** This is a testing tool, not a
  conformance authority.
- **Every message capability is `PARTIAL`.** The API reports
  `authoritativeCompletenessKnown: false` for all 23.
- **Authoritative licensed specifications are not loaded.** Coverage is a
  repository-configured subset, never reconciled against a licensed MT or ISO 20022 source.
- **Official ISO 20022 XSDs are not bundled.** MX validates against a schema derived from
  this repository's own configuration. It is a real XSD compiled by libxml2 and it catches
  order, cardinality and datatype errors — but it proves internal consistency, not conformance.
- **`sese.020`, `sese.027`, `sese.030` and `sese.031` are additionally `UNVERIFIED`.** Their
  versions, root element names and element sets were modelled on ISO 20022 idioms already in
  the repository and reconciled against nothing. Do not demo them as finished work.
- **No live SWIFT network transmission.** Nothing leaves the machine.
- **No production connector contract.** RJE export fails closed for the same reason.

What we would need to remove these caveats is in
[AUTHORITATIVE_ARTIFACT_CHECKLIST.md](AUTHORITATIVE_ARTIFACT_CHECKLIST.md).

---

## If something goes wrong

| Symptom | Cause |
|---|---|
| "The studio API could not be reached" | The backend is not running. `make backend`. |
| Port 8000 or 3000 in use | A previous run. `pkill -f uvicorn; pkill -f "next dev"`. |
| `make migrate` fails | Run `make install` first. |
| A demo step behaves differently from this runbook | A real defect. `make check` and report it. |
