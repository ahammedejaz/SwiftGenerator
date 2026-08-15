# Canonical domain model

`SettlementScenario` is independent of raw MT tags and is the sole input to deterministic business services. Pydantic rejects extra properties and enums constrain lifecycle, direction, payment type, function, transaction type, identifier/quantity types, status, settlement result, generation mode, and negative mutation.

## Main object

| Path | Meaning |
| --- | --- |
| `scenarioId`, `profileId` | Synthetic test identity and selected versioned profile. |
| `lifecycle` | `INSTRUCTION`, `STATUS`, or `CONFIRMATION`. |
| `direction` | `RECEIVE` or `DELIVER`. |
| `paymentType` | `FREE_OF_PAYMENT` or `AGAINST_PAYMENT`. |
| `messageType` | Resolver-controlled MT540–MT548 type. |
| `function` | Supported `NEWM`, `CANC`, or `REVR`. |
| `senderReference`, `relatedReference`, `clientReference` | Synthetic typed business references. |
| `trade` | Transaction type, trade date, settlement date. |
| `security` | Supported ISIN-format identifier and unit quantity. |
| `account` | Synthetic safekeeping account. |
| `settlement` | Currency, amount, synthetic PSET/delivering/receiving values. |
| `confirmation` | Actual date, settled quantity/amount, full/partial result. |
| `status` | Controlled category, code, reason, narrative, instruction type. |
| `testConfiguration` | Valid or explicit controlled negative test. |
| `syntheticData` | Must stay explicitly true in the AI adapter boundary. |

Dates use ISO `YYYY-MM-DD` in JSON and decimals are losslessly modeled before deterministic rendering. Unknown business values remain `null`; the interpreter never invents them.

## Resolution tables

| Direction | Payment | Instruction |
| --- | --- | --- |
| Receive | Free of Payment | MT540 |
| Receive | Against Payment | MT541 |
| Deliver | Free of Payment | MT542 |
| Deliver | Against Payment | MT543 |

| Instruction | Confirmation |
| --- | --- |
| MT540 | MT544 |
| MT541 | MT545 |
| MT542 | MT546 |
| MT543 | MT547 |

Any supported instruction may receive MT548. A phrase such as “buy” can suggest transaction type and a tentative receive direction, but the UI asks the user to confirm direction/payment semantics before authoritative generation.

## Lifecycle correlation

Response creation starts from a stored instruction rather than accepting a disconnected confirmation. It reuses profile, direction, payment type, security, account, place, agents, and instructed terms. A response must link to the instruction reference. Pair type, security, direction, payment type, quantity, related instruction type, and status/reason combination are revalidated.

## Database representation

The canonical object is stored as JSON in `scenarios` while queryable lifecycle fields are also
columns. Raw messages and validation findings have separate tables. Repository interfaces isolate
persistence; SQLite remains development/test, while the production configuration and clean
migration path use PostgreSQL through psycopg.

## Expanded canonical models

`PenaltyStatement` contains supplied penalty entries with controlled action/status/type/direction. `CorporateActionNotification` defines one DVOP event, security/account, eligibility, dates, and options; instruction/status/confirmation/narrative requests are linked lifecycle commands. Settlement changes use controlled amendment field paths and classifications. `WorkflowGeneratedMessage` is the persistence/report contract for non-settlement modules.

## Authoring aggregate

`MessageDraft` owns an immutable message type, effective profile/release, revision, lifecycle status,
checksum, sequence instances, encrypted field instances, validation levels, reviews, approvals,
external evidence, submissions, and audit events. A field instance references a stable specification
row and records its source. A sequence instance references a configured path, parent occurrence,
and occurrence number; structural movement outside the specification is impossible.

Configured fields remain typed metadata rather than arbitrary tag dictionaries. Values pass the
row format/code rules before rendering. All 16 message types share this generic source-bounded
authoring path; the existing strongly typed workflow/domain models remain the golden-path business
and lifecycle engines. The generic path does not promote capability beyond `PARTIAL`.
