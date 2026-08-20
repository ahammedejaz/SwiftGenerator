# Automation API — deterministic generation and AI test data

The platform has two automation surfaces that sit side by side:

| Surface | Prefix | Model calls | What it is for |
|---|---|---|---|
| Deterministic API | `/api/v1/messages`, `/api/v1/catalogue`, `/api/v1/templates`, `/api/v1/intelligence` | **0, always** | Generate, validate, import, diff and download messages from values you supply |
| Knowledge Base API | `/api/v1/knowledge` | 0 (retrieval only; embeddings are made at sync time, never per request) | Status, sources, messages, cited search over the indexed sources |
| AI authoring API | `/api/v1/ai` | 1+ on a cache miss, **0 on a cache hit** | Identify a message, prepare values from a business description, validated AI samples, bulk test data, field explanations, cited answers, release comparison |

Every message that leaves any of these surfaces was composed and validated by the same
deterministic engine. The model, where one is involved, proposes values inside a closed
schema; it never writes the FIN or XML, never chooses a message type the catalogue does not
hold, and never activates a rule. Nothing costs money unless `/api/v1/ai/*` is called with a
configured provider, and a cached sample is served with zero model calls.

All examples below use `http://127.0.0.1:8000` and synthetic values. Field ids, tags and
element paths are the ones the running server actually serves — read them from `spec`
first rather than copying from memory.

## Two lanes, stated on every call

| Lane | Where the structure comes from | How you select it |
|---|---|---|
| `CONFIGURED` (default) | The reviewed YAML packs under `backend/config/` — the 16 MT and 7 MX messages that existed before Phase 6 | Omit `lane`, or pass `lane=CONFIGURED` |
| `KNOWLEDGE_PREVIEW` | A Structure Pack the knowledge base compiled from indexed evidence (Prowide SR2025 + SWIFT MRG PDFs for MT; an XSD for MX) | Pass `lane=KNOWLEDGE_PREVIEW` **and** the release (MT: `release=SR2025` or `SR2026`; MX: the full version as `messageType`, e.g. `pacs.008.001.14`) |

The preview lane is **never implicit**. A request that omits `lane` runs against the
configured registries, and a configured MT541 is the same MT541 it was before Phase 6.
Responses from both lanes carry `lane` and a `provenance` block (`structureSource`,
`ruleStatus`, `validationLevel`, `capabilityStatement`, `sourceProvenance`) so a test log
can record what the message rested on.

A preview message for the current live release that duplicates a configured message (for
example a Prowide-only MT541 SR2025) is not listed in the catalogue; the configured pack is
the authority for that release. A future release of the same message (MT541 SR2026) is a
distinct entry.

## Authentication

Send `X-API-Key: <key>` on every request. Keys come from `AUTOMATION_API_KEYS`
(comma-separated). In `APP_ENV=development` or `test` with no keys configured the API is
open; outside development with no keys it answers `503 SERVICE_NOT_CONFIGURED`; with keys
configured a missing header is `401 AUTHENTICATION_REQUIRED` and a wrong one is
`403 NOT_AUTHORISED`. The same rule applies to `/api/v1/knowledge/*` and `/api/v1/ai/*`.

## Error envelope

Every non-2xx response is one shape:

```json
{
  "error": {
    "code": "MESSAGE_GENERATION_NOT_READY",
    "message": "MT541 SR2025 is STRUCTURE_AVAILABLE; generation is disabled.",
    "details": []
  }
}
```

`details` carries structured extras when the handler has them — for an exhausted AI repair
loop it holds the validation `findings`, the `repairLog` and the `aiUsage`.

| HTTP | `code` | When |
|---|---|---|
| 404 | `MESSAGE_GENERATION_NOT_READY` | The preview structure exists but is `STRUCTURE_AVAILABLE` or `STRUCTURE_VERIFIED`; the message names the blockers |
| 404 | `STRUCTURE_SOURCE_MISSING` | No preview pack is loaded for that message/format |
| 422 | `KNOWLEDGE_RELEASE_REQUIRED` | Import in the preview lane without naming the message type (and release), or an MT message that exists in several releases and none was named |
| 404 | `KNOWLEDGE_SOURCE_NOT_FOUND` | `GET /api/v1/knowledge/messages/{message}/status` for a message the knowledge base holds nothing for |
| 404 | `RAG_NO_RELEVANT_EVIDENCE` | `prepare` without a message type and no catalogue candidate matched the description |
| 422 | `AI_SAMPLE_GENERATION_FAILED` | The repair loop ran out of attempts without a valid sample, or the deterministic seed itself did not validate |
| 404 | `AI_UNKNOWN_FIELD` | `presentation` for a field id the structure does not have |
| 503 | `AI_NOT_CONFIGURED` | An `/ai/` call with no provider configured **and** no deterministic fallback for that operation |
| 200 | `EXCEL_UNSUPPORTED_MESSAGE_TYPE` | Not an HTTP error: it is the `ruleId` on a failed Excel scenario whose `MessageType` is not known in the requested lane |
| 400 / 413 / 415 / 422 / 429 | `INVALID_REQUEST`, `REQUEST_TOO_LARGE`, `UNSUPPORTED_MEDIA_TYPE`, `REQUEST_NOT_PROCESSABLE`, `RATE_LIMIT_EXCEEDED` | Framework-level failures |

A **validation failure is not an HTTP error**: `generate` and `validate` answer `200` with
`valid: false` and the findings, because that is a result.

---

## Deterministic API (0 LLM calls)

### Discover

`GET /api/v1/catalogue` — every message in both lanes.

```bash
curl -s http://127.0.0.1:8000/api/v1/catalogue \
  | jq '{formats: [.formats[] | {id, messageCount, configuredMessageCount}],
         ready: [.messages[] | select(.generatable) | {format, messageType, release, lane, readiness}] | length,
         blocked: [.messages[] | select(.generatable | not) | {messageType, release, readiness, blockers}]}'
```

Each entry carries `lane`, `release`, `releaseLane` (`CURRENT_LIVE` / `FUTURE_TEST`),
`readiness` (`KNOWLEDGE_ONLY` / `STRUCTURE_AVAILABLE` / `STRUCTURE_VERIFIED` /
`GENERATION_READY`), `readinessLabel`, `blockers`, `structureSource`, `rulesStatus`,
`knowledgeSources`, `aiSampleReady`, `automationReady` and `generatable`. Each format
carries `messageCount` (both lanes) and `configuredMessageCount` (the reviewed packs only).
A non-generatable entry always has a non-empty `blockers` list and no `sampleVariants`.

`GET /api/v1/messages/{messageType}/spec?format=MT|MX[&lane=KNOWLEDGE_PREVIEW&release=…]`
— the fields or elements, with ids, presence, formats and codes.

```bash
curl -s 'http://127.0.0.1:8000/api/v1/messages/MT541/spec?format=MT' | jq '.fields[0]'
curl -s 'http://127.0.0.1:8000/api/v1/messages/MT103/spec?format=MT&lane=KNOWLEDGE_PREVIEW&release=SR2025' \
  | jq '{lane, release, structureSource, capabilityStatement, ids: [.fields[].id][:8]}'
```

`GET /api/v1/messages/{messageType}/samples` and `…/samples/{MINIMAL|TYPICAL|FULL}` — the
deterministic samples, with the same `lane`/`release` query. Preview messages offer
`MINIMAL` and, when the structure has optional fields and at most 500 inputs, `FULL`.

### Generate and validate

`POST /api/v1/messages/validate` (never persists) and `POST /api/v1/messages/generate`
take the same body:

| Field | Notes |
|---|---|
| `format` | `MT` or `MX` |
| `messageType` | `MT541`; for MX preview the full version, e.g. `pacs.008.001.14` |
| `lane`, `release` | Optional; see the lane table |
| `profileId` | Default `BASE_DEMO_V1` |
| `scenarioId` | Your correlation id, echoed back |
| `fields` | MT: `{id}` **or** `{sequence, tag, qualifier?, option?, occurrence?}`, plus `value` |
| `elements` | MX: `{path, occurrence?, value}` |
| `outputModes` | Optional subset of `FIN`, `BLOCK4`, `TXT`, `XML`, `APPHDR`, `DOCUMENT`, `CANONICAL_JSON` |
| `persist` | `generate` defaults to `true`; `validate` is always `false` |

Configured lane (MT541):

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/messages/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "format": "MT", "messageType": "MT541", "profileId": "BASE_DEMO_V1", "scenarioId": "TC001",
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
  }' | jq '{valid, lane, checksum, fin: .outputs.fin}'
```

Knowledge-preview lane (MT103 SR2025, compiled from Prowide SR2025 evidence — ids from the
`spec` call above):

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/messages/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "format": "MT", "messageType": "MT103", "lane": "KNOWLEDGE_PREVIEW", "release": "SR2025",
    "scenarioId": "TC-MT103-001",
    "fields": [
      { "id": "MT103-ROOT-20-NONE",  "value": "TESTREF001" },
      { "id": "MT103-ROOT-23B-NONE", "value": "CRED" },
      { "id": "MT103-ROOT-32A-NONE", "value": "260818USD1000," },
      { "id": "MT103-ROOT-50A-NONE", "value": "DEMOGB2LXXX" },
      { "id": "MT103-ROOT-59-NONE",  "value": "/12345678 BENEFICIARY" },
      { "id": "MT103-ROOT-71A-NONE", "value": "SHA" }
    ]
  }' | jq '{valid, lane, provenance, fin: .outputs.fin}'
```

The response (`GenerateResult`) carries `messageId`, `correlationId`, `valid`,
`validation` (layers, errors with `ruleId`, `field`, `location`, `message`, `suggestion`),
`outputs` (`fin`, `block4`, `txt`, `xml`, `appHdr`, `document`, `canonicalJson`),
`envelopeFields`, `renderedLines`, `checksum`, `lane`, `provenance` and
`availableOutputModes`. In the preview lane `provenance.ruleStatus` states that no
reviewed Rule Pack applies; `provenance.structureSource` is `PROWIDE_SR2025`,
`SWIFT_MRG_SR2026_PROWIDE_SR2025_CORROBORATED` or `OPERATOR_SUPPLIED_XSD`.

### Read back, compare, download

`POST /api/v1/messages/import` — `{ "text": "<FIN or XML>", "lane"?, "release"?,
"messageType"? }`. The message identifies itself from its header or namespace; `messageType`
is consulted only for a bare MT text block, and is **required** together with `lane` when
importing against the preview lane (`KNOWLEDGE_RELEASE_REQUIRED` otherwise). The result is
the canonical values, the regenerated message and a `comparison` of the two.

`POST /api/v1/messages/diff` — a `GenerateRequest` plus `original`; every difference is
attributed (caller edit, normalisation, outside the configured subset, interface-generated).

`GET /api/v1/messages/id/{messageId}`, `…/download/{FIN|BLOCK4|TXT|XML|APPHDR|DOCUMENT|CANONICAL_JSON}`,
`…/evidence.zip` and `GET /api/v1/messages/recent` — for persisted messages.

### Excel

`GET /api/v1/templates/{MT|MX}.xlsx[?messageType=…&lane=KNOWLEDGE_PREVIEW&release=…]` — a
workbook with a Reference sheet listing every supported tag or element path.
`POST /api/v1/messages/generate-from-excel?profileId=BASE_DEMO_V1[&lane=…&release=…]` —
multipart `file`; one message per `ScenarioID`. `lane` and `release` apply to every
scenario in the workbook.

```bash
curl -s -o mt103-template.xlsx \
  'http://127.0.0.1:8000/api/v1/templates/MT.xlsx?messageType=MT103&lane=KNOWLEDGE_PREVIEW&release=SR2025'
curl -s -X POST 'http://127.0.0.1:8000/api/v1/messages/generate-from-excel?profileId=BASE_DEMO_V1&lane=KNOWLEDGE_PREVIEW&release=SR2025' \
  -F 'file=@filled-mt103.xlsx' \
  | jq '{generated, failed, results: [.results[] | {scenarioId, status, valid, lane, checksum}]}'
```

Each scenario result carries `scenarioId`, `rowNumbers`, `status` (`GENERATED` / `INVALID`
/ `FAILED`), `valid`, `validation`, `outputs`, `checksum`, `lane` and `provenance`.

### Message Intelligence (deterministic)

`GET /api/v1/intelligence/search?q=settlement%20amount[&format=MT&messageType=MT541&limit=60]`
and `GET /api/v1/intelligence/field?id=MT541-E-19A-SETT` — configured-pack knowledge
(meaning, format, codes, examples). No model, no retrieval.

---

## Knowledge Base API (retrieval only)

| Method | Path | Returns |
|---|---|---|
| GET | `/api/v1/knowledge/status` | `mode`, `enabled`, `indexed`, `adminEnabled`, `databasePresent`, `roots` (relative names only), `counts`, `lastRun`, `corpusVersion`, `embeddingProvider`, `embeddingDeploymentConfigured` (a boolean — never the key or the endpoint), `embeddingDimensions`, `embeddingPolicyStatement`, `llmProvider`, `sourcesEmbeddingBlocked`, `sourcesEmbeddingAllowed`, `loadErrors`, `message` |
| GET | `/api/v1/knowledge/messages` | Every message identity the index knows: `format`, `messageType`, `messageVersion`, `release`, `title`, `sources[]`, `segments`, `embedded`, `embeddingPolicy`, `llmPolicy`, `readiness`, `blockers`, `structureSource` |
| GET | `/api/v1/knowledge/messages/{message}/status` | `{ "message", "entries": [...] }` — the same rows for one message across releases; `404 KNOWLEDGE_SOURCE_NOT_FOUND` when none |
| POST | `/api/v1/knowledge/search` | Cited hits (below) |
| GET | `/api/v1/knowledge/sources[?includeDeleted=true]` | Every source: `sourceId`, `checksum`, `relativePaths`, `documentType`, `classification`, `pageCount`, `embeddingPolicy`, `llmPolicy`, `state`, `segments`, `embedded`, `failureCode` |
| GET | `/api/v1/knowledge/telemetry` | Retrieval and AI counters: calls, tokens, cache hits, latency. `costAvailable` is `false`; no cost is invented |
| POST | `/api/v1/knowledge/sync` | Incremental sync. `404` unless `KNOWLEDGE_MODE=local_uat` |

When the index does not exist, `status.indexed` is `false` and `message` reads
*"Knowledge Base has not been indexed yet. Run `make knowledge-sync`."* Every other
endpoint keeps working; the configured lane is unaffected.

Search body: `query` (required), `format` (`MT`/`MX`), `messageType`, `release`,
`releases` (explicit multi-release comparison — the only way two releases mix),
`sections` (e.g. `NETWORK_VALIDATED_RULE`, `FIELD_SPECIFICATION`, `FORMAT_SPECIFICATION`,
`USAGE_RULE`, `ELEMENT_DEFINITION`), `limit` (1–40, default 8), `lexicalOnly`.

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/knowledge/search \
  -H 'Content-Type: application/json' \
  -d '{"query": ":22F::SETR", "format": "MT", "messageType": "MT541", "release": "SR2026", "limit": 5}' \
  | jq '{indexed, semanticAvailable, semanticReason, policyStatement,
         results: [.results[] | {sourceId, release, section, page, heading, score, method}]}'
```

A citation names `sourceId`, `documentTitle`, `release`, `documentType`, `section`,
`page`, `heading`, `segmentId`, `segmentHash`, `score` and `method` (`LEXICAL`,
`SEMANTIC`, `HYBRID`). `snippet` is present only when the source's policy allows text to
leave the index; for licensed documents it is `null` and `policyStatement` says why.
`semanticAvailable: false` with `semanticReason` (`EMBEDDING_PROVIDER_UNAVAILABLE`,
`KNOWLEDGE_NOT_INDEXED`, or a policy block) means lexical ranking served the request —
which is the normal state for licensed sources under the default policy.

---

## AI authoring API

Every operation here follows one order: deterministic seed → model proposal inside a closed
JSON schema (field ids are an enumeration of the structure) → `check_values` rejects
anything outside it (`AI_UNKNOWN_FIELD`, `AI_INVALID_CODE`, `AI_RAW_MESSAGE_REJECTED`,
`AI_EMPTY_VALUE`) → the ordinary `GenerateRequest` → the deterministic engine decides
validity. Every response carries `aiUsage` (`provider`, `model`, `llmCalls`,
`promptTokens`, `completionTokens`, `latencyMs`, `attempts`, `cacheHit`, `callsAvoided`,
`tokensAvoided`, `costAvailable: false`), `retrievalEvidence` (which indexed sections were
consulted, with citations) and `synthetic: true`.

With no provider configured (`KNOWLEDGE_AI_PROVIDER=disabled`, or no endpoint/key/
deployment), `samples` and `test-data` still answer with the deterministic seed and
`repair.outcome: "DETERMINISTIC_FALLBACK"`; `identify` ranks from the catalogue lexically;
`ask` answers *"The available indexed source does not establish this."* Only operations
that cannot proceed without a model return `503 AI_NOT_CONFIGURED`.

### `POST /api/v1/ai/messages/identify`

Body: `request` (3–2000 chars), `format?`, `limit?` (1–10). Candidates come only from the
catalogue; the model cannot name a message that does not exist.

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/ai/messages/identify \
  -H 'Content-Type: application/json' \
  -d '{"request": "receive securities against payment", "format": "MT", "limit": 3}' \
  | jq '{confidence, candidates: [.candidates[] | {messageKey, confidence, reason}]}'
```

Response: `candidates[]` (`messageKey`, `format`, `messageType`, `version`, `lane`,
`release`, `readiness`, `confidence`, `reason`), `explanation`, `missingInformation`,
`confidence`, `aiUsage`.

### `POST /api/v1/ai/messages/prepare`

Body: `scenario` (3–4000 chars), `format?`, `messageType?` (identified from the scenario
when absent), `release?`, `lane?`, `knownValues[]` (`fieldId`, `occurrence`, `value`),
`profileId`.

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/ai/messages/prepare \
  -H 'Content-Type: application/json' \
  -d '{"scenario": "Receive 1000 units of ISIN XS0000000001 against payment of EUR 25000 settling tomorrow",
       "format": "MT", "messageType": "MT541"}' \
  | jq '{messageType, valid, canonicalValues: .canonicalValues[:5], rejectedValues, missingFields, questions}'
```

Response: `canonicalValues[]` (`fieldId`, `occurrence`, `value`), `rejectedValues[]`
(`fieldId`, `code`, `reason`), `missingFields`, `questions`, `notes`, `validation`, `valid`,
`capability`, `identification` (when the message was identified), `retrievalEvidence`,
`aiUsage`. The request text cannot change `messageType`, `format` or `lane`: text such as
"use MT999" inside the scenario is fenced as untrusted and the structure the caller named is
the one that answers.

### `POST /api/v1/ai/samples`

Body: `format`, `messageType`, `release?`, `lane?`, `sampleType` (`MINIMAL` | `TYPICAL` |
`FULL`; `FULL` only where the structure has at most 500 inputs), `profileId`, `scenario?`,
`refresh?` (skip the cache and spend model calls).

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/ai/samples \
  -H 'Content-Type: application/json' \
  -d '{"format": "MT", "messageType": "MT541", "sampleType": "TYPICAL"}' \
  | jq '{valid, cache, llmCalls: .aiUsage.llmCalls, repair: .repair.outcome, roundTrip, fin: .outputs.fin}'
```

Response: the `GenerateResult` fields (`valid`, `validation`, `outputs`, `checksum`,
`provenance`), plus `canonicalValues`, `inputs`, `elements`, `capability`, `cache`
(`status` `HIT`/`MISS`, `llmCallsAvoided`, `tokensAvoided`), `aiUsage`,
`retrievalEvidence`, `repair` (`attempts`, `log`, `outcome` — `AI_VALID`,
`DETERMINISTIC_FALLBACK`, `AI_REPAIR_EXHAUSTED`, `CACHE`) and `roundTrip`
(`identical: true` means Compose → Parse → Compose reproduced the message byte for byte).

The cache key includes format, message, release, lane, sample type, profile, structure
checksum, active rule packs, the message-scoped corpus version, prompt and schema version,
provider and model. A second identical call is a `HIT` with `aiUsage.llmCalls: 0`, the
same `checksum`, and the stored `roundTrip` proof. Live measurement on 2026-08-20: MT541
TYPICAL, first call 1 model call and valid; second call `HIT`, 0 calls.

### `POST /api/v1/ai/test-data/generate`

Body: `format`, `messageType`, `release?`, `lane?`, `scenario` (default "Typical
synthetic scenario"), `count` (1–100, capped by `KNOWLEDGE_AI_MAX_BATCH`, default 20),
`sampleType`, `testIntent` (`POSITIVE` | `NEGATIVE`), `profileId`, `reviewerMode`,
`outputModes?`.

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/ai/test-data/generate \
  -H 'Content-Type: application/json' \
  -d '{"format":"MT","messageType":"MT541","scenario":"Typical receive-against-payment settlement","count":5,"sampleType":"TYPICAL"}' \
  | jq '{generated, total, modelCalls: .aiUsage.llmCalls, cache: .cache.status,
         scenarios: [.scenarios[] | {scenarioId, title, valid, checksum}]}'
```

Response: `requestId`, `testIntent`, `capability`, `scenarios[]` (`scenarioId` `AI-001`…,
`title`, `canonicalValues`, `rejectedValues`, `validation`, `valid`, `outputs`,
`checksum`), `generated`, `total`, `retrievalEvidence`, `aiUsage`, `cache`, `note`,
`synthetic`. Each scenario is validated and composed independently.

`testIntent: NEGATIVE` builds scenarios that break a named rule and proves each one against
the deterministic engine (`status` `NEGATIVE_PROVEN` / `NEGATIVE_NOT_PROVEN`). It needs a
reviewed, active Rule Pack for the message; where none applies the response is `200` with
`generated: 0` and a `note` saying so. Candidate (`REVIEW_REQUIRED`) rules are never used
outside `reviewerMode`, and even then only when installed for runtime evaluation — today
that is none, so negative data is available only for the synthetic `sese.023` overlays
under `DEMO_MARKET_CLIENT_V1`.

### `POST /api/v1/ai/presentation`

Body: `format`, `messageType`, `release?`, `lane?`, `fieldId`. Plain-language
`presentation` (`businessQuestion`, `example`, `whyNeeded`, `commonMistake`, `citations`)
for one field, cached per structure; `authority: "NONE"` — it changes nothing the engine
validates.

### `POST /api/v1/ai/ask`

Body: `question` (3–2000 chars), `format?`, `messageType?`, `release?`, `queryType?`
(`FIELD_EXPLANATION` default).

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/ai/ask \
  -H 'Content-Type: application/json' \
  -d '{"question": "When is :22F::SETR mandatory?", "format": "MT", "messageType": "MT541", "release": "SR2026"}' \
  | jq '{supported, answer, citations, caveats}'
```

Response: `answer`, `supported` (`SUPPORTED`, `PARTIAL`, `UNSUPPORTED_BY_EVIDENCE`),
`citations[]` (segment ids that resolve through `/knowledge/search` results),
`caveats[]`, `retrievalEvidence`, `aiUsage`. An answer that cites nothing from the
evidence is not reported as a fact.

### `POST /api/v1/ai/releases/compare`

Body: `format`, `messageType`, `releaseA`, `releaseB`, `focus?`. Response: `summary`,
`differences[]` (structural diff of the two packs plus cited evidence), `citations`.
Neither release is promoted by comparing them.

---

## Java — REST Assured

Deterministic generate, configured lane:

```java
// Java + REST Assured
import io.restassured.RestAssured;
import io.restassured.response.Response;
import static io.restassured.RestAssured.given;
import static org.hamcrest.Matchers.equalTo;

public class GenerateMt541 {

    @Test
    void generatesAFinMessage() {
        RestAssured.baseURI = "http://127.0.0.1:8000";

        String body = """
            {
              "format": "MT",
              "messageType": "MT541",
              "profileId": "BASE_DEMO_V1",
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
                .body("lane", equalTo("CONFIGURED"))
                .extract().response();

        String fin = response.path("outputs.fin");
        // Hand `fin` straight to the system under test — the bytes are exactly as generated.
    }
}
```

AI test data — the deterministic engine decided validity; the model only proposed values:

```java
// Java + REST Assured — the same call as the curl example
import static io.restassured.RestAssured.given;
import static org.hamcrest.Matchers.*;

public class AiTestDataMt541 {

    @Test
    void generatesFiveValidatedScenarios() {
        RestAssured.baseURI = "http://127.0.0.1:8000";

        String body = """
            {"format":"MT","messageType":"MT541","scenario":"Typical receive-against-payment settlement","count":5,"sampleType":"TYPICAL"}
            """;

        given()
                .contentType("application/json")
                // .header("X-API-Key", System.getenv("STUDIO_API_KEY"))  // outside development
                .body(body)
            .when()
                .post("/api/v1/ai/test-data/generate")
            .then()
                .statusCode(200)
                .body("generated", equalTo(5))
                .body("scenarios.valid", everyItem(is(true)))
                .body("scenarios.outputs.fin", everyItem(containsString(":20C::SEME//")))
                .body("synthetic", is(true));
    }
}
```

For the preview lane add `"lane": "KNOWLEDGE_PREVIEW", "release": "SR2025"` to either
body and assert `body("provenance.lane", equalTo("KNOWLEDGE_PREVIEW"))`.

## Pipeline notes

- **Cost.** The deterministic and knowledge surfaces never call a model. `/ai/*` spends
  model calls only on a cache miss or with `refresh: true`; `aiUsage.llmCalls` on every
  response is the figure to log. Provider cost is not computed (`costAvailable: false`).
- **Determinism.** The same values produce the same `checksum` in both lanes. A cache hit
  reproduces the same checksum as the miss that filled it.
- **Structure changes.** A re-sync that changes a preview structure changes its pack
  checksum, which is part of the sample-cache key; old samples are not served against a
  new structure.
- **CI.** `make e2e` and `make check` index only the synthetic fixture corpus with fake
  embeddings and the scripted AI provider; a pipeline needs no key, no PDF and no XSD to
  exercise every endpoint above. Live proofs (`make test-live-rag`,
  `make test-live-ai-sample`) are explicit and never part of `make check`.
- **Readiness before use.** Poll `GET /api/v1/catalogue` (or
  `/api/v1/knowledge/messages/{m}/status`) and branch on `generatable` / `readiness`
  rather than on a 404: a message the knowledge base knows but cannot generate says
  exactly which gate blocked it.

## Where this lives

| Path | What |
|---|---|
| `backend/app/studio/routes.py` | Deterministic API, lane/release plumbing, Excel |
| `backend/app/knowledge_base/routes.py` | Knowledge Base API |
| `backend/app/ai_authoring/routes.py`, `service.py` | AI authoring API and the seed → propose → check → generate → repair flow |
| `backend/app/api/errors.py` | The error envelope |
| `backend/app/studio/security.py` | `X-API-Key` handling |
| `frontend/components/studio/Automation.tsx` | The same examples rendered in the Automation screen |

## Limitations

- `GENERATION_READY` means the structure loaded, a sample validated, composed, parsed back
  and re-composed identically. It is not semantic completeness, SWIFT certification or
  conformance; in the preview lane no Network Validated Rule is evaluated.
- Negative test data needs a reviewed active Rule Pack; none exists for a real message.
- `FULL` AI samples are offered only where the structure has at most 500 inputs.
- Search snippets are withheld for licensed sources under the default policy; citations
  still name source, page and section.
- Semantic ranking is available only where embeddings were allowed and made; for licensed
  sources the default policy blocks them and lexical ranking serves the request.
