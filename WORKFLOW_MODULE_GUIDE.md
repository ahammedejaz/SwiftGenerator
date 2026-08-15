# Workflow Module Guide

## Registry

`backend/app/workflows/registry.py` owns message-type capability discovery. It enforces one module owner per implemented message type and publishes profile-aware capabilities through `GET /api/capabilities`.

Registered modules:

| Module | Message types | Status |
|---|---|---|
| Settlement | MT540–MT548 | Implemented demonstration subset |
| Settlement Command | MT530 | Partial: priority command plus cancellation/cancel-rebook policy |
| Penalties | MT537 | Partial penalty-reporting subset |
| Corporate Actions | MT564–MT568 | Partial DVOP lifecycle subset |

Planned capability names are metadata only; they have no executable handlers.

## Extension steps

1. Obtain an authorised rule source and define the bounded use cases.
2. Add strong canonical models and controlled enums.
3. Implement deterministic resolution, missing-field logic, validation, composition, parsing, and correlation inside the module.
4. Add client-profile enablement and restrictions.
5. Add full emitted-field knowledge coverage with provenance.
6. Register unique message ownership and capability status.
7. Add API, UI, Excel/report, golden, negative, lifecycle, and security tests.
8. Document unsupported variants explicitly.

Domain composers must not depend on OpenRouter. Model output is an untrusted partial intent only. No module may use model output to select sequences, tags, qualifiers, validity, or final raw output.

Future candidates include additional Category 5 messages, reconciliation, collateral, trade confirmation, treasury, payments, and ISO 20022 equivalents. None is currently claimed as implemented.
