# AI and RAG observability

Every AI-authoring operation produces a content-free ledger row when the local knowledge
runtime is enabled. The row correlates model, retrieval and cache work with one UUID without
storing the business request.

## Recorded

- request ID, timestamp, operation, format/message/release filters and outcome
- provider/model, live calls, input/output tokens, cache hit, calls/tokens avoided and latency
- RAG used/mode/query type, lexical and semantic candidates, final evidence count, context
  character count, corpus version and retrieval latency
- embedding calls, reported tokens/cache hits/latency where available

Aggregate tables retain lifetime counters for the local index. The operation ledger is
bounded by `KNOWLEDGE_TELEMETRY_RETENTION_DAYS` (30 by default), and the API returns at most
`KNOWLEDGE_TELEMETRY_RECENT_LIMIT` rows (50 by default). Cleanup runs in the same transaction
as each new row. Schema initialization adds columns and tables in place; reindexing is not
required.

## Never recorded

Prompts, message values, raw messages, full queries, source excerpts, retrieved private
context, chain-of-thought, credentials, private endpoints and invented cost are excluded.
Cost remains unavailable unless a provider actually reports it.

## Surfaces

`GET /api/v1/knowledge/telemetry` returns overview, LLM, RAG, embedding, knowledge, cache and
recent-operation sections. `/ai-efficiency` renders these as **AI & Knowledge Usage**. AI
results use a small expandable indicator showing provider/model, evidence-section count,
new tokens, response time and cache state. A deterministic fallback says the model was not
called; a cached sample says zero live calls.

RAG citations remain on the result that used them. The usage ledger exposes counts and
segment identities only, never citation snippets.
