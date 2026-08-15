# Data Protection Guide

Real-data mode requires a server-side 256-bit base64 wrapping key and session HMAC secret. Draft
field values and immutable version snapshots use AES-256-GCM envelope encryption with fresh data
keys and tenant/draft/field authenticated context. Checksums support correlation without exposing
plaintext. PostgreSQL is mandatory in production; SQLite is development/test only.

Data classes are `PUBLIC`, `INTERNAL`, `CONFIDENTIAL`, `FINANCIAL_SENSITIVE`, and `SECRET`.
Account/reference/party-like fields are masked for non-operational roles. Plaintext values are not
written to normal logs, AI telemetry, metrics, or cache keys. OpenRouter receives minimal
tokenised text only, and cache HMAC context includes tenant and profile/version fingerprints.

Rotate the data key through a KMS-backed adapter and rewrap stored data keys before retiring the
old key. Rotate session/cache HMAC secrets with a planned invalidation window; cache rotation is
performed by increasing `AI_CACHE_KEY_VERSION`. The current repository has retention configuration
but no completed authorised purge workflow or KMS implementation; these remain production gaps.
