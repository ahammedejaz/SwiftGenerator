# Security

What is protected, how, and what is deliberately not attempted.

---

## The shape of the risk

This tool takes untrusted input (typed values, uploaded spreadsheets, free text destined
for a model) and produces financial message text. Three things could go wrong:

1. **Someone makes it produce a message it should not** — a fabricated envelope, a
   smuggled block, a message claiming authority it does not have.
2. **Someone gets something out of it they should not** — another tenant's draft, a secret,
   a stack trace naming internals.
3. **Someone gets it to run something** — through an upload, a template, or a model prompt.

Every control below exists for one of those three.

---

## It cannot send anything

There is no live SWIFT integration and no arbitrary outbound action.

Submission **fails closed**: it requires an authorised connector, an approval policy and
external validation evidence, all explicitly configured. The mock UAT connector is refused
outside development. The shipped connector is `DOWNLOAD_ONLY`.

## It will not invent authority

Values that a messaging interface or the SWIFT network assigns are never produced:

| Value | Behaviour |
|---|---|
| Session and sequence numbers | Must be configured or supplied; otherwise output fails with a named error |
| MAC, CHK, PDE, PDM, DLM, TNG, SYS trailers | Refused outright, even if a profile lists them |
| MX `Sgntr` | Never written |

A message from this tool cannot carry a fabricated authentication trailer, because the code
will not write one.

## Message text comes only from composers

No `eval`, no dynamic templates, no user-supplied template execution. Field values are
rejected if they contain FIN block fragments (`{1:`, `{2:`, `{4:`), so a value cannot
smuggle structure into the envelope.

---

## Input handling

**Requests** are strict Pydantic models: unknown fields rejected, enums allowlisted, lengths
bounded, control characters refused. Body size is capped and rate-limited per client.

**Spreadsheet uploads** must pass content type at the API, an `.xlsx` extension, a
basename-only filename (no path component), a byte limit, real OOXML ZIP validity, and a
row limit — in that order, before a single cell is read. Cells that begin `=`, `+`, `-` or
`@` are prefixed on output so a downloaded workbook cannot execute a formula.

**Raw message content** is parsed as inert data and refused at the model boundary with
`AI_RAW_CONTENT_NOT_ACCEPTED`.

**Downloads** use server-controlled filenames. Report retrieval takes a repository-known
UUID, so a caller cannot select a filesystem path.

---

## The model boundary

Prompt-injection-shaped narrative is treated as untrusted delimited data, with automated
regression tests for XML, JSON, Markdown, repetition and control-character attacks.

Before any text leaves the process, sensitive values — ISINs, accounts, references, party
names, BICs — are replaced with request-local typed placeholders. Only placeholders the
platform issued are rehydrated afterwards; the mapping is cleared and never logged or
stored.

Every provider call requires compatible structured-output parameters, denies data
collection and requires zero data retention. Those are enforced in production and are never
weakened during a retry or an escalation. Models are pinned slugs — never `latest`, never
`auto`.

The response schema is normalised and linted before transmission: no root union, every
object property required, nullable optionals, recursive `additionalProperties: false`, no
defaults, no arbitrary maps, resolved local references, controlled enums, and no
raw-message, tag or sequence fields.

---

## Two authentication models, kept apart

| | Interactive | Automation |
|---|---|---|
| Who | A person in a browser | A test suite or pipeline |
| Mechanism | Session cookie + CSRF + role checks | `X-API-Key` |
| Scope | Drafts, approvals, submission | `/api/v1` |
| Config | `SESSION_HMAC_SECRET` | `AUTOMATION_API_KEYS` |

**Automation keys** come only from the environment. They are compared with
`hmac.compare_digest` against every configured key, so timing does not reveal which
matched, and the key never appears in a response, a log line or the source. A rejection
says the key was not recognised; it never hints at the shape of a valid one.

In development the automation API is open — that is what makes a fresh clone usable.
Outside development it is **closed until keys are configured**, returning `503` with an
explanation rather than being quietly open.

**Interactive sessions** are HMAC-hashed before storage, CSRF-protected, and role-checked.
Development login is refused when `APP_ENV=production`.

## Tenants and data at rest

Drafts are scoped to a tenant and encrypted at rest. Field values are masked from roles
that should not see them. An approver cannot be the author of what they approve. Tenant
isolation has its own tests.

---

## What never appears in a response

Stack traces, SQL, secrets, API keys, raw authentication data, internal exception detail.

Every error returns the same envelope:

```json
{ "error": { "code": "RESOURCE_NOT_FOUND", "message": "…", "details": [], "requestId": "…" } }
```

Payload logging is absent. Telemetry and audit records contain ids, versions, model names,
counts and outcomes — never content. A defensive log filter masks accounts, bearer values
and anything shaped like a raw message.

## Transport and headers

CORS permits only the configured frontend origin. Every API response sets
`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`
and a restrictive `Content-Security-Policy`. Containers run as unprivileged users.

---

## Verifying it yourself

```bash
# No secret-shaped string in any tracked file
git ls-files -z | xargs -0 grep -nIE "sk-[A-Za-z0-9]{32,}|AKIA[0-9A-Z]{16}|-----BEGIN.*PRIVATE KEY"

# Nothing in history either
git log --all -p | grep -cE "sk-or-v1-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}"

# .env is ignored
git check-ignore .env

# Dependency advisories
make audit
```

`.env` is gitignored; `.env.example` ships with every secret blank and a comment saying so.

---

## Known gaps

Named plainly, because a security document that lists only strengths is not one:

- No production identity-provider adapter. The OIDC/SAML boundary exists; the adapter does
  not.
- No KMS or HSM integration; no operational key rotation procedure.
- No row-level security, secure purge, SIEM or DLP integration.
- Rate limits and the AI circuit breaker are **per process**. A multi-instance deployment
  needs shared state or the limits multiply by instance count.
- No penetration test has been performed.

See [limitations.md](limitations.md) for the functional equivalent of this list.
