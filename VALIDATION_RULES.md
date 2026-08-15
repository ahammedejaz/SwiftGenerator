# Validation rules

Validation findings contain `ruleId`, severity, field path, friendly message, technical explanation, current value, expected condition, suggestion, and an `intentional` flag. A valid-mode error blocks composition. Negative-test mode only emits when the selected mutation causes its expected rule and no unexpected error.

## Layer 1: canonical model

- Pydantic types, strict extra-field rejection, enum values, ISO dates, and exact decimals.
- `MESSAGE-TYPE-REQUIRED` when resolution remains incomplete.
- `SENDER-REFERENCE-MAX-LENGTH` and `SENDER-REFERENCE-FORMAT`.
- `SECURITY-ISIN-FORMAT`, `SECURITY-QUANTITY-POSITIVE`, and `SETTLEMENT-AMOUNT-POSITIVE`.
- Required-field rules are generated per message and canonical path, such as `MT541-SETTLEMENT-AMOUNT-REQUIRED`.

## Layer 2: message business rules

- `MESSAGE-TYPE-BUSINESS-MISMATCH` enforces the direction/payment table.
- `FOP-CASH-LEG-NOT-ALLOWED` prevents cash data on MT540/542/544/546.
- `SETTLEMENT-DATE-NOT-BEFORE-TRADE` enforces positive chronology.
- `CANCELLATION-PREVIOUS-REFERENCE-REQUIRED` and `CONFIRMATION-LIFECYCLE` enforce supported functions/lifecycles.
- DVP messages require currency/amount while FOP messages do not.

## Layer 3: client profile

- `PROFILE-MESSAGE-NOT-SUPPORTED` applies the message allowlist.
- `PROFILE-CURRENCY-NOT-ALLOWED` applies the currency allowlist.
- Versioned required/client-required paths, defaults, and sender-reference restrictions apply before composition.

## Layer 4: raw structure subset

- Block rules: `RAW-BLOCK-1`, `RAW-BLOCK-2`, `RAW-BLOCK-4-OPEN`, `RAW-BLOCK-4-CLOSE`.
- Sequence rules: boundary match, no nesting, complete closure, and fixed type-specific order.
- Field rules: generated syntax, inside a sequence, and an explicit tag/qualifier allowlist.
- Null controls are rejected. Narrative content, including prompt-like text, remains inert data.

This layer does not claim complete ISO 15022 parsing, network validation, checksum validation, or all legal sequence/field variants.

## Layer 5: lifecycle correlation

- `LIFECYCLE-ORIGINAL-INSTRUCTION` and `LIFECYCLE-RESPONSE-TYPE`.
- `LIFECYCLE-RELATED-REFERENCE`.
- `LIFECYCLE-SECURITY-MATCH`, `LIFECYCLE-DIRECTION-MATCH`, and `LIFECYCLE-PAYMENT-TYPE-MATCH`.
- `CONFIRMATION-MESSAGE-TYPE-MATCH` and `CONFIRMATION-QUANTITY-NOT-EXCEED-INSTRUCTION`.
- `MT548-RELATED-INSTRUCTION-TYPE` and controlled status/reason compatibility.

## Controlled statuses

| Category | Code | Reasons |
| --- | --- | --- |
| Pending | PEND | AWAITING_CASH, AWAITING_SECURITIES |
| Rejected | REJT | INVALID_REFERENCE, UNSUPPORTED_SECURITY |
| Matched | MACH | DETAILS_MATCHED |
| Unmatched | NMAT | COUNTERPARTY_MISMATCH |
| Cancellation accepted | CAND | CANCELLATION_PROCESSED |
| Cancellation rejected | CANR | SETTLEMENT_ALREADY_FINAL |

These are demonstration configuration values from `backend/config/statuses.yaml`.

## Negative-test mutations

1. Missing settlement amount.
2. Settlement date before trade date.
3. Sender reference too long.
4. Missing place of settlement.
5. Unsupported currency.
6. Missing previous reference for cancellation.
7. Confirmation quantity exceeding instruction.
8. Confirmation type mismatching instruction.
9. MT548 missing related instruction reference.
10. Invalid status/reason combination.

Every emitted negative message carries “Intentionally invalid message generated for negative testing.” and marks expected findings with `intentional: true`. Selecting a mutation not enabled by the profile is rejected.

## Expanded workflow validation

- MT530: original instruction/account/reference/profile and priority-range correlation.
- Cancellation: original existence/immutability, relationship, and duplicate-active prevention.
- MT537: list/action/status consistency, supplied amount/direction/currency/date, duplicates, profile, and optional settlement linkage.
- MT564–MT568: event/profile/reference continuity, options, eligibility/instruction quantities, deadline, cash fields, status/reason shape, and narrative safety.
- Raw parsing: exact sequence/tag/qualifier allowlists, including application-emitted nested penalty/corporate-action structures.

Knowledge and cache hits are never validity decisions and cannot bypass these layers.

## Separated authoring validation levels

Secure drafts report `CANONICAL_VALID`, `STRUCTURE_VALID`, `FORMAT_VALID`,
`NETWORK_RULES_LOCALLY_VALID`, `USAGE_RULES_LOCALLY_VALID`, `CLIENT_PROFILE_VALID`,
`MARKET_PROFILE_VALID`, `EXTERNAL_VALIDATION_PASSED`, and `APPROVED_FOR_SUBMISSION` independently.
Absent authorised network/usage/market evidence is `EXTERNAL_EVIDENCE_REQUIRED`, never a generic
pass. Uploaded evidence must match checksum, profile, and release. A passing cache result or LLM
interpretation cannot change any level.
