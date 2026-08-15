# Submission Operations Guide

The controlled state model is:

```text
DRAFT → VALIDATED → REVIEW_REQUESTED → APPROVED → QUEUED → SUBMITTED → ACKNOWLEDGED
                                             ↘ REJECTED / NACKED / FAILED / RETRY_PENDING
```

Before submission, verify tenant, message type, masked sender/receiver, environment, connector,
checksum, all required validation levels, profile/release, immutable approval, and idempotency key.
Production requires an explicit end-user confirmation in addition to server configuration.

Attempts store only safe provider/correlation identifiers, safe response code, attempt count,
timestamp, connector, and checksum. The application never fabricates a real ACK/NAK. Mock UAT
references are labelled `MOCK` and exist solely for test evidence. Changed messages cannot reuse
an earlier approval. Retry and destination policies must be implemented by an authorised connector
adapter before live use.
