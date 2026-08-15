# Corporate Actions Guide

## Implemented lifecycle

The initial verified event is a voluntary Dividend With Options (`DVOP`):

`MT564 Notification → MT565 Cash Election → MT567 Processing Status → MT566 Cash Confirmation`

MT568 may carry sanitised additional text related to the notification. It cannot be used to bypass structured fields.

MT564 provides event/message references, event/classification/completeness, synthetic ISIN/account, eligible quantity, payment date, two controlled options, default option, and response deadline. MT565 selects a valid notified option and quantity. MT567 supports acknowledged, pending, and rejected instruction status with controlled reason shape. MT566 confirms the selected cash option, supplied posting amount, and posting date. MT568 provides bounded `ADTX` text.

## Validation

The deterministic service enforces unique references, one event/workflow/profile, security/account reuse, offered option number/code, one default, positive quantities, eligibility/instruction bounds, election deadline, cash fields/currency, and related-message type. Narrative controls, code fences, script-like text, and raw MT fragments are rejected.

## Boundaries

- Only `DVOP` is enabled.
- Cash dividend, interest, redemption, and exchange offer are not enabled without approved event-specific rule packs.
- MT566 cash movement is supported. Securities-movement confirmation is rejected pending a verified movement pack.
- MT565 cancellation construction is not enabled in this slice.
- Reversal and unsolicited variants are unsupported.

## Interfaces

- UI: `/corporate-actions`
- APIs: `/api/corporate-actions/notifications`, `/instructions`, `/statuses`, `/confirmations`, `/narratives`
- Workflow Excel: `/api/bulk/workflow-template` and `/api/bulk/workflow-generate`
- Lifecycle: `/api/workflows/{workflowId}/lifecycle`
- Provenance report: `/api/workflows/messages/{messageId}/report`

The secure generic builder accepts actual user values for every configured MT564–MT568 row. All
shipped samples remain synthetic and the legacy event wizard remains DVOP-specific. This is not a
complete corporate-action or ISO 15022 implementation; no event is production-capable without an
authorised event/profile import and external validation.
