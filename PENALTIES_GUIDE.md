# Penalties Guide

## Implemented MT537 subset

The Penalties module reports supplied penalty data using a deterministic MT537 subset. The secure
generic builder accepts actual values for all 23 configured rows and repeatable configured
currency/counterparty/penalty subsequences; the legacy guided workflow and all shipped samples use
synthetic values. It supports current, new-only, and updated-or-removed lists; new, updated, and
removed items; active, not-computed, and removed status; Settlement Fail Penalty and Late Matching
Fail Penalty; payable/receivable direction; detection date; common/previous/settlement references;
and profile-allowed currency.

The platform does not calculate penalty amounts. An explicit amount is required. It only produces the source-required grouped net by deterministic arithmetic over supplied amounts. Market rates, instrument calculation details, market-specific netting, and production claims are unsupported.

## Validation and correlation

Validation covers typed status/action consistency, non-negative amount, direction, currency, grouped currency/date, duplicate references, previous-reference semantics, profile enablement, and optional correlation to a persisted settlement instruction. A bad row cannot prevent other Excel rows from being processed.

## Interfaces

- UI: `/penalties`
- Generate: `POST /api/penalties/generate`
- Validate: `POST /api/penalties/validate`
- Workflow Excel: `/api/bulk/workflow-template` and `/api/bulk/workflow-generate`
- Lifecycle: `GET /api/workflows/{workflowId}/lifecycle`
- Provenance report: `GET /api/workflows/messages/{messageId}/report`

All output is labelled as a source-bounded configured subset. The amount is user-entered; no
unapproved calculation or full MT537 pending-transaction completeness is claimed.
