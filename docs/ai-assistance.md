# AI assistance

**Short version: the AI is optional, it is off by default, and it never touches a message.**

If you switch it off completely, you lose one convenience feature and nothing else.

---

## What a model does

Exactly one thing: turns a sentence into structured intent.

```
"I bought 1000 shares, settling Tuesday against payment"
                    │
                    ▼
              AI interpretation          ← the only step involving a model
                    │
                    ▼
    { direction: RECEIVE, paymentType: AGAINST_PAYMENT, ... }
                    │
                    ▼
        deterministic code from here on  ← rendering, validation, output
```

## What a model never does

| Never | Because |
|---|---|
| Renders an MT message | A composer does it, from a specification, the same way every time |
| Renders MX XML | Same |
| Validates anything | Rules are code and configuration, and must be reproducible |
| Validates against a schema | libxml2 does it |
| Parses a spreadsheet | openpyxl does it |
| Looks up a tag or element | Message Intelligence is dictionary lookup over authored data |
| Builds a download | Deterministic |

A generated message is byte-identical across runs. A model in the loop would make that
untrue, and an untrustworthy test fixture is worse than no fixture.

---

## Turning it off

```bash
AI_PROVIDER=disabled
```

Everything except the "describe a scenario in English" screen keeps working. That is why
the default `.env.example` ships with no key: a fresh clone is fully functional.

---

## When it is on

The order is **deterministic → cache → model**:

1. Can the deterministic interpreter handle this phrasing? Then no call is made.
2. Has this exact question been asked before? Then the cached answer is returned.
3. Otherwise, call the model.

The cache is keyed by HMAC. It stores results, never prompt content and never the mapping
back to what a user typed.

Also in place: a circuit breaker that stops calling a failing provider, daily request and
token budgets, a rate limit, pinned model versions (never `latest`, never `auto`), and
zero-data-retention required.

---

## Seeing what it cost

**Advanced → AI Efficiency** shows live calls, cache hits, tokens consumed, provider cost,
latency, and — the useful number — how many calls and tokens were *avoided* by the
deterministic path and the cache.

Every interaction is recorded with its source: `LIVE_API`, `CACHE`, `DETERMINISTIC` or
`AI_UNAVAILABLE`. You can always tell which produced a given answer.

---

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `AI_PROVIDER` | `openrouter` | `openrouter`, `disabled` or `mock` (`mock` only when `APP_ENV=test`) |
| `AI_MODE` | `required` | `optional` lets the deterministic path answer when the model is unavailable |
| `OPENROUTER_API_KEY` | *(empty)* | Server-side only; never sent to the browser |
| `OPENROUTER_PRIMARY_MODEL` | `openai/gpt-5.4-mini` | Must be a pinned slug |
| `OPENROUTER_ESCALATION_MODEL` | `openai/gpt-5.4` | Used when confidence is low |
| `OPENROUTER_DAILY_REQUEST_BUDGET` | *(none)* | Hard stop on calls per day |
| `OPENROUTER_DAILY_TOKEN_BUDGET` | *(none)* | Hard stop on tokens per day |
| `AI_CACHE_ENABLED` | `true` | |
| `AI_CACHE_HMAC_SECRET` | *(empty)* | Required when caching in production |
