# Amendment and Cancellation Guide

## Deterministic decisioning

There is no generic “amend any message” function. The versioned policy registry classifies each requested field change as processing-data modification, core-business-data change, cancellation-only, unsupported modification, or clarification required.

The current verified direct command is MT530 priority (`PRIR`) modification with values 0001–9999. MT530 is not presented as a universal amendment message. Hold/release, proprietary non-matching processing data, and settlement-party modification remain unsupported without an approved client rule pack.

Core quantity, identifier, amount, settlement-date, and safekeeping-account changes follow cancel-and-rebook when enabled:

`Original Instruction → Cancellation Request → Cancellation Accepted → Replacement Instruction`

The replacement has a new sender reference. The original remains immutable, and the result reports before/after values and the reason direct amendment was not used.

## Cancellation

Cancellation requires a persisted MT540–MT543 instruction, references it, preserves direction/payment correlation, blocks duplicate active requests, and can receive controlled MT548 accepted/rejected processing status. No LLM decides whether cancellation or direct amendment is allowed.

## Interfaces

- UI: `/settlement-processing`
- `POST /api/settlement/amendment-decision`
- `POST /api/settlement/cancellations`
- `POST /api/settlement/commands`
- `POST /api/settlement/cancel-rebook`

The authoritative policy source is referenced in `backend/config/workflows/settlement_amendment_v1.yaml`.
