# LLM Cache and Efficiency Guide

## Decision order

Every model-eligible operation follows this order:

1. Local validation and input limits.
2. Deterministic workflow/knowledge/rule answer when sufficient.
3. Exact context-aware cache lookup.
4. OpenRouter primary model only when language interpretation adds value.
5. Bounded escalation under the configured rules.
6. Strict response validation, placeholder rehydration, deterministic resolution, and safe caching.

Opening tag details, resolving explicit Receive+DVP, validating, composing, parsing supported raw fields, generating lifecycle responses, and downloading reports never require an LLM.

## Cache identity and privacy

Cache IDs use HMAC-SHA256 with `AI_CACHE_HMAC_SECRET`. The canonical key includes namespace, tokenised input, minimal context fingerprint, module/message, profile and standards versions, prompt/schema/knowledge/taxonomy versions, pinned primary model/settings, language, audience, and cache-key version.

Raw account values, names, internal references, raw MT messages, prompts, provider responses, keys, and placeholder maps are not cache keys or persisted cache content. Sensitive values are tokenised before key creation; cached templates contain canonical placeholders and are rehydrated only from the current request’s temporary map. Unknown placeholders invalidate the hit.

The persistent SQLite adapter is paired with a bounded TTL L1 and process-local single-flight coordinator. A distributed adapter/lock is a future deployment hardening item.

## Invalidation and TTL

Entries are rejected on expiry, corruption, result-schema failure, model-policy mismatch, or changes to prompt, schema, model, profile, standards release, knowledge base, taxonomy, or cache-key version. Default intent TTL is 30 days; explanation/translation TTL is 90 days; validation wording TTL is 30 days.

Failures and unvalidated outputs are never cached. A hit never bypasses placeholder, canonical, resolver, profile, lifecycle, or final message validation.

## Metrics

The UI distinguishes current usage from original cached usage:

- `LIVE_API`: current provider calls/tokens/cost/latency.
- `CACHE`: zero current calls/tokens; original response size and derived avoided usage shown separately.
- `DETERMINISTIC`: no AI was needed.
- `AI_UNAVAILABLE`: provider interpretation was requested but unavailable.

Avoided cost is shown only when the original cache entry contains provider-reported cost, and it is labelled estimated. No price table is fabricated.

## Operations

- Disable caching: `AI_CACHE_ENABLED=false`.
- Rotate secret: deploy a new `AI_CACHE_HMAC_SECRET` and increment `AI_CACHE_KEY_VERSION`; old entries become unreachable and may be purged offline.
- Diagnose safely: `POST /api/ai/cache/diagnose` returns configuration/statistics without keys or payloads.
- Global clearing is CLI/operator-only unless the development-only administration gate is explicitly enabled.
- Review usage through `/ai-efficiency` or the content-free `/api/ai/usage/*` endpoints.

The 195-fixture platform contract evaluation is run with `make evaluate-platform`; it labels its cache metrics synthetic and does not claim provider cost savings.
