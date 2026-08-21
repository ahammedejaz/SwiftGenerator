# For automation testers

**You want a valid SWIFT message in your pipeline. You do not want to open a browser.**

One HTTP call. No login, no session, no CSRF token.

---

## The 30-second version

```bash
curl -s -X POST http://localhost:8000/api/v1/messages/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "format": "MT",
    "messageType": "MT541",
    "fields": [
      { "sequence": "GENL",    "tag": "20C", "qualifier": "SEME", "value": "TESTREF001" },
      { "sequence": "GENL",    "tag": "23G",                      "value": "NEWM" },
      { "sequence": "TRADDET", "tag": "98A", "qualifier": "TRAD", "value": "20260814" },
      { "sequence": "TRADDET", "tag": "98A", "qualifier": "SETT", "value": "20260818" },
      { "sequence": "TRADDET", "tag": "35B",                      "value": "XS0000000009" },
      { "sequence": "TRADDET", "tag": "36B", "qualifier": "SETT", "value": "UNIT/1000" },
      { "sequence": "FIAC",    "tag": "97A", "qualifier": "SAFE", "value": "SAFE0000001" },
      { "sequence": "SETDET",  "tag": "22F", "qualifier": "SETR", "value": "TRAD" },
      { "sequence": "SETDET",  "tag": "95P", "qualifier": "PSET", "value": "DEMOGB2LXXX" },
      { "sequence": "SETDET",  "tag": "95P", "qualifier": "DEAG", "value": "DEMODEAGXXX" },
      { "sequence": "SETDET",  "tag": "19A", "qualifier": "SETT", "value": "USD25000,00" }
    ]
  }' | jq -r '.outputs.fin'
```

```
{1:F01DEMOGB2LAXXX0001000001}
{2:I541DEMOUS33XXXXN}
{4:
:16R:GENL
:20C::SEME//TESTREF001
...
-}
```

Send that string to your system under test. It is byte-for-byte what the tool produced.

---

## Do not hand-write that payload

Ask the API for a working one:

```bash
curl -s http://localhost:8000/api/v1/messages/MT541/samples/TYPICAL | jq '.inputs'
```

That returns a complete, valid field set. Change what your test cares about, leave the
rest. Three depths are available: `MINIMAL`, `TYPICAL`, `FULL`.

To see every field a message accepts, with formats and examples:

```bash
curl -s http://localhost:8000/api/v1/messages/MT541/spec \
  | jq '.fields[] | {id, displayName, presence, formatExplanation, tag, qualifier}'
```

---

## Addressing a field, two ways

Both work. Use whichever suits your data.

**By specification row id** — stable, unambiguous:

```json
{ "id": "MT541-A-20C-SEME", "value": "TESTREF001" }
```

**By sequence, tag and qualifier** — what a spreadsheet naturally holds:

```json
{ "sequence": "GENL", "tag": "20C", "qualifier": "SEME", "value": "TESTREF001" }
```

`sequence` accepts either the code (`GENL`) or the path (`A`). It can be omitted when the
tag appears in only one sequence — but if it is ambiguous the API will say so rather than
guess.

For MX, address by element path:

```json
{ "path": "/Document/SctiesSttlmTxInstr/TradDtls/SttlmDt/Dt/Dt", "value": "2026-08-18" }
```

---

## MX in one call

```bash
curl -s -X POST http://localhost:8000/api/v1/messages/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "format": "MX",
    "messageType": "sese.023",
    "elements": [
      { "path": "/Document/SctiesSttlmTxInstr/TxId", "value": "TEST001" },
      { "path": "/Document/SctiesSttlmTxInstr/SttlmTpAndAddtlParams/SctiesMvmntTp", "value": "RECE" },
      { "path": "/Document/SctiesSttlmTxInstr/SttlmTpAndAddtlParams/Pmt", "value": "APMT" },
      { "path": "/Document/SctiesSttlmTxInstr/TradDtls/SttlmDt/Dt/Dt", "value": "2026-08-18" },
      { "path": "/Document/SctiesSttlmTxInstr/FinInstrmId/ISIN", "value": "XS0000000009" },
      { "path": "/Document/SctiesSttlmTxInstr/QtyAndAcctDtls/SttlmQty/Qty/Unit", "value": "1000" },
      { "path": "/Document/SctiesSttlmTxInstr/QtyAndAcctDtls/SfkpgAcct/Id", "value": "SAFE0000001" },
      { "path": "/Document/SctiesSttlmTxInstr/SttlmParams/SctiesTxTp/Cd", "value": "TRAD" },
      { "path": "/Document/SctiesSttlmTxInstr/DlvrgSttlmPties/Pty1/Id/AnyBIC", "value": "DEMODEAGXXX" },
      { "path": "/Document/SctiesSttlmTxInstr/SttlmAmt/Amt", "value": "USD 25000.00" },
      { "path": "/Document/SctiesSttlmTxInstr/SttlmAmt/CdtDbtInd", "value": "DBIT" }
    ]
  }' | jq -r '.outputs.xml'
```

Three output fields matter for MX:

| Field | What it is |
|---|---|
| `outputs.document` | The `Document` on its own |
| `outputs.appHdr` | The `head.001.001.03` Business Application Header on its own |
| `outputs.xml` | Both, inside the transport wrapper the client profile configures |

---

## Reading the response

```json
{
  "messageId": "8f2c…",
  "correlationId": "b41e…",
  "scenarioId": "TC001",
  "format": "MT",
  "messageType": "MT541",
  "valid": false,
  "validation": {
    "summary": "1 issue needs attention",
    "errors": [
      {
        "ruleId": "MT_MANDATORY_FIELD_MISSING",
        "severity": "ERROR",
        "layer": "STRUCTURE",
        "field": "Settlement Amount",
        "location": "MT541-E-19A-SETT",
        "message": "Settlement Amount is required.",
        "expected": "ISO currency plus a positive decimal amount",
        "suggestion": "For example: USD25000,00"
      }
    ],
    "warnings": [],
    "layers": [
      { "layer": "STRUCTURE", "state": "FAILED", "detail": "1 issue(s) found." },
      { "layer": "FORMAT",    "state": "PASSED", "detail": "No issues found." }
    ]
  },
  "outputs": { "block4": "...", "fin": "...", "canonicalJson": {} },
  "checksum": "2c57614539b5…",
  "availableOutputModes": ["BLOCK4", "FIN", "TXT", "CANONICAL_JSON"]
}
```

**Assert on `valid`, report with `validation.errors`.** Every error carries a stable
`ruleId` you can branch on and a `location` you can map back to your input row. A failing
test should print `field`, `message` and `suggestion` — that is a bug report your team can
act on without opening the tool.

`checksum` is a SHA-256 of the message. Use it to prove two runs produced identical output.

---

## Reading an existing message back

`POST /api/v1/messages/import` takes a message you already have — an MT FIN message, an MT
text block, or an ISO 20022 `Document` with or without its `AppHdr` — and gives back the
canonical values, the envelope it arrived with, and the regenerated message.

```bash
curl -s http://localhost:8000/api/v1/messages/import \
  -H 'Content-Type: application/json' \
  -d '{"text": "{1:F01DEMOGB2LAXXX0001000001}\n{2:I541DEMOUS33XXXXN}\n{4:\n:16R:GENL\n…\n-}"}'
```

Three things are worth knowing:

- **You do not say what it is.** The format and the message type come from the message —
  the ISO 20022 namespace, or FIN Block 2. A caller-supplied label would let a mislabelled
  file be parsed against the wrong specification. The one exception is an MT text block
  pasted on its own, which genuinely cannot name itself: send `messageType` for that, and
  only then. A header that disagrees with it is refused, not reconciled.
- **`fields` (MT) and `elements` (MX) are exactly what `generate` accepts.** Change a value
  and POST them straight back; the same composer produces the new message. That is the
  whole round trip, and it is asserted byte-for-byte in the test suite for every sample of
  every configured message.
- **Nothing is dropped in silence.** Anything the message held that could not be imported
  comes back in `importIssues`, and is folded into `result.validation` as well, so a partial
  import cannot be mistaken for a faithful one.

### Comparing what you got with what you had

`POST /api/v1/messages/diff` takes the original message *and* the values to regenerate from,
and returns the new message plus a line-by-line comparison in which **every difference
carries a reason**:

```json
{
  "diff": {
    "basis": "FIN_LINES",
    "compared": "the complete FIN message",
    "summary": { "identical": false, "changed": 1, "expected": 1, "dropped": 0, "unexplained": 0 },
    "lines": [
      {
        "kind": "CHANGED",
        "reason": "USER_EDIT",
        "field": "Sender's Message Reference",
        "originalText": ":20C::SEME//TESTREF001",
        "regeneratedText": ":20C::SEME//EDITEDREF01"
      }
    ]
  }
}
```

`summary.unexplained` is the only figure worth asserting on in a pipeline. The others are
expected by construction:

| `reason` | Counted as | Meaning |
|---|---|---|
| `USER_EDIT` | `expected` | You changed the value. |
| `NORMALISATION` | `expected` | Same meaning, written in specification order. |
| `NOT_REPRODUCED` | `expected` | A trailer, user-header field or signature. Interface- and network-generated; never written. **Never an application error.** |
| `IMPORT_DROPPED` | `dropped` | Outside the configured subset. Reported on import, absent from the result. |
| `UNEXPLAINED` | `unexplained` | Could not be accounted for. Fail your test on this one. |

MT is compared line by line, so FIN line structure is preserved. MX is compared on a
canonical serialisation, so indentation, attribute order and whitespace can never register
as a difference — only structure and values can.

The same comparison is on every `POST /api/v1/messages/import` response as `diff`, which
answers "did importing lose anything?" without a second call. Both are deterministic; no
model is involved in either.

`diff.comparable` is `false` for a message over 3,000 lines or with more than 200 import
problems — attribution costs lines × issues, so an unbounded comparison is a way to spend
the server's time rather than something anyone reads. `summary.identical` still answers the
question, `lines` is empty, and `notComparedReason` says why. Both bounds sit far above
anything the platform itself generates.

---

## Excel in, messages out

Keep scenarios in a spreadsheet, get every message back in one response.

```bash
# Get a template with the right columns and a working example already in it
curl -o mt-template.xlsx http://localhost:8000/api/v1/templates/MT.xlsx
curl -o mx-template.xlsx http://localhost:8000/api/v1/templates/MX.xlsx

# Edit it, then send it
curl -s -X POST 'http://localhost:8000/api/v1/messages/generate-from-excel?profileId=BASE_DEMO_V1' \
  -F 'file=@scenarios.xlsx' \
  | jq '.results[] | { scenarioId, messageType, valid, message: (.outputs.fin // .outputs.xml) }'
```

**MT columns** — one row per tag:

| ScenarioID | MessageType | Sequence | SequenceOccurrence | Tag | Qualifier | Option | Value |
|---|---|---|---:|---|---|---|---|
| TC001 | MT541 | GENL | 1 | 20C | SEME | C | TESTREF001 |
| TC001 | MT541 | TRADDET | 1 | 98A | SETT | A | 20260818 |

**MX columns** — one row per element:

| ScenarioID | MessageType | XPath | Occurrence | Value |
|---|---|---|---:|---|
| MX001 | sese.023 | /Document/SctiesSttlmTxInstr/TxId | 1 | TEST001 |

Things worth knowing:

- **All rows with the same `ScenarioID` build one message.**
- **The format is detected from the columns.** A `Tag` column means MT, an `XPath` column
  means MX. You do not pass it.
- **`SequenceOccurrence` / `Occurrence`** build repeated blocks. Use `1` for the first,
  `2` for the second. Blank means `1`.
- **A bad scenario fails alone.** The others still generate; every scenario is reported
  with its own validation.
- **Headers are matched loosely.** `scenario id`, `ScenarioID` and `SCENARIO_ID` all work.
- **Excel dates are handled.** If Excel turns `2026-08-18` into a date cell, the parser
  turns it back into the right text.
- **The Reference sheet** in every template lists every supported field with its format and
  an example, so nobody has to invent an XPath.

---

## In your test framework

### Java + REST Assured

```java
import io.restassured.RestAssured;
import io.restassured.response.Response;
import static io.restassured.RestAssured.given;
import static org.hamcrest.Matchers.equalTo;

public class GenerateMt541 {

    @Test
    void generatesAFinMessage() {
        RestAssured.baseURI = "http://localhost:8000";

        String body = """
            {
              "format": "MT",
              "messageType": "MT541",
              "scenarioId": "TC001",
              "fields": [
                { "sequence": "GENL",    "tag": "20C", "qualifier": "SEME", "value": "TESTREF001" },
                { "sequence": "GENL",    "tag": "23G",                      "value": "NEWM" },
                { "sequence": "TRADDET", "tag": "98A", "qualifier": "SETT", "value": "20260818" }
              ]
            }
            """;

        Response response = given()
                .contentType("application/json")
                // .header("X-API-Key", System.getenv("STUDIO_API_KEY"))  // outside development
                .body(body)
            .when()
                .post("/api/v1/messages/generate")
            .then()
                .statusCode(200)
                .body("valid", equalTo(true))
                .extract().response();

        String fin = response.path("outputs.fin");
        // Hand `fin` straight to the system under test.
    }
}
```

### Python

```python
import requests

BASE = "http://localhost:8000"

# Start from a known-good sample instead of hand-writing one.
sample = requests.get(f"{BASE}/api/v1/messages/MT541/samples/TYPICAL", timeout=30).json()
fields = sample["inputs"]

# Override only what this test is about.
for field in fields:
    if field["qualifier"] == "SETT" and field["tag"] == "98A":
        field["value"] = "20260901"

result = requests.post(
    f"{BASE}/api/v1/messages/generate",
    json={"format": "MT", "messageType": "MT541", "scenarioId": "TC001", "fields": fields},
    timeout=30,
).json()

assert result["valid"], [
    f'{issue["field"]}: {issue["message"]} → {issue["suggestion"]}'
    for issue in result["validation"]["errors"]
]

send_to_system_under_test(result["outputs"]["fin"])
```

### JavaScript / Playwright / Jest

```javascript
const response = await fetch("http://localhost:8000/api/v1/messages/generate", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    format: "MX",
    messageType: "sese.023",
    elements: [
      { path: "/Document/SctiesSttlmTxInstr/TxId", value: "TEST001" },
      // …
    ],
  }),
});

const result = await response.json();
if (!result.valid) {
  throw new Error(
    result.validation.errors.map((e) => `${e.field}: ${e.message}`).join("\n"),
  );
}
```

---

## Authentication

**In development the API is open.** That is deliberate — a fresh clone works with no setup.

Everywhere else, set service keys on the server:

```bash
# Generate one
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Set it (comma-separated for several; minimum 24 characters each)
export AUTOMATION_API_KEYS="key-for-ci,key-for-nightly"
```

and send it:

```bash
curl -H "X-API-Key: $STUDIO_API_KEY" http://localhost:8000/api/v1/catalogue
```

Keys come only from the environment. They never appear in a response, in a log line, or in
the source. If `APP_ENV` is not `development` or `test` and no keys are configured, the
whole `/api/v1` surface returns `503` with an explanation, rather than being quietly open.

---

## Every endpoint

| Method | Path | What it does |
|---|---|---|
| `GET` | `/api/v1/catalogue` | Every message you can generate |
| `GET` | `/api/v1/messages/{type}/spec` | Every field, with presence, format and examples |
| `GET` | `/api/v1/messages/{type}/samples` | All sample variants |
| `GET` | `/api/v1/messages/{type}/samples/{variant}` | One sample: `MINIMAL`, `TYPICAL`, `FULL` |
| `POST` | `/api/v1/messages/validate` | Validate without keeping anything |
| `POST` | `/api/v1/messages/generate` | Field or element data in, a message out |
| `POST` | `/api/v1/messages/import` | An existing MT or MX message in, its canonical values out |
| `POST` | `/api/v1/messages/diff` | Regenerate from your values and compare with a message you already have |
| `POST` | `/api/v1/messages/generate-from-excel` | Multipart `.xlsx`; one message per `ScenarioID` |
| `GET` | `/api/v1/templates/MT.xlsx` · `/MX.xlsx` | The Excel templates |
| `GET` | `/api/v1/intelligence/search?q=` | Look up any tag or element |
| `GET` | `/api/v1/intelligence/field?id=` | Everything known about one field |
| `GET` | `/api/v1/messages/recent` | Recently generated messages |
| `GET` | `/api/v1/messages/id/{id}` | One message and its outputs |
| `GET` | `/api/v1/messages/id/{id}/download/{output}` | The exact generated bytes |
| `GET` | `/api/v1/messages/id/{id}/evidence.zip` | Every output plus the validation report |
| `GET` | `/api/v1/coverage` | What is implemented for every configured message, measured |
| `GET` | `/api/v1/sources` | Which authoritative specification artifacts are present |

The complete machine-readable contract is at `/openapi.json`, and there is an interactive
console at `/docs`. The Phase 6 routes — `/api/v1/knowledge/*`, `/api/v1/ai/*`, and the
`lane`/`release` parameters on the endpoints above — are in
[automation-api.md](automation-api.md) and [ai-assisted-authoring.md](ai-assisted-authoring.md).

---

## Errors

Every failure returns the same envelope, with a stable code:

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "MT999 is not a supported MT message.",
    "details": [],
    "requestId": "b41e…"
  }
}
```

| Status | Code | Usually means |
|---|---|---|
| `401` | `AUTHENTICATION_REQUIRED` | Missing or wrong `X-API-Key` |
| `404` | `RESOURCE_NOT_FOUND` | Unknown message type or message id |
| `415` | `UNSUPPORTED_MEDIA_TYPE` | Upload was not an `.xlsx` |
| `422` | `REQUEST_NOT_PROCESSABLE` | Malformed workbook, or a request that fails schema validation |
| `503` | `SERVICE_NOT_CONFIGURED` | Automation API not enabled on this server |

A **validation failure is not an HTTP error.** A message with missing fields returns `200`
with `valid: false` and the details — because that is a result, not a broken request.

Stack traces, SQL and secrets never appear in a response.
