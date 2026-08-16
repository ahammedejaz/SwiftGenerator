# What this tool cannot do

Read this before you trust it with anything that matters. Everything here is stated
honestly on purpose — a testing tool that overstates itself is worse than no tool.

---

## The big one: coverage is a subset

The message definitions in this repository were hand-built from public review material.
**Nobody has checked them against a licensed SWIFT or ISO 20022 specification.**

That means:

- Some fields that exist in the real standard are missing here.
- Some code lists are shorter than the real ones.
- Network validation rules, market practice and institution-specific rules are not applied.

Every message therefore reports `capability: PARTIAL` and
`authoritativeCompletenessKnown: false`, in the API and on screen. Nothing is marked
production-capable, and nothing can be until a licensed specification is imported and
reconciled field by field.

**Use it to produce test data. Do not use it as a conformance authority.**

Exact numbers per message: [generated/message-coverage.md](generated/message-coverage.md).

### One known domain-rule gap

The configured MT subset renders `:22F::SETR//BUY` in Sequence B and `:22F::SETR//RECE` in
Sequence E. In the authoritative ISO 15022 format, `22F::SETR` appears in Sequence E only,
and receive-versus-deliver is implied by the message type rather than stated.

This is recorded rather than silently corrected, because correcting it means deciding what
the right qualifier is — and that decision needs an authoritative source, not a guess.

---

## No SWIFT network, ever

There is no live SWIFT session, no certification, no signing, no authentication, no
production ACK/NAK. Download-only is the working path. A mock UAT connector exists and is
forbidden outside development.

**Submission fails closed.** Sending a real message requires an authorised connector, an
approval policy and external validation evidence, all explicitly configured. None ship here.

## Values the tool refuses to invent

By design, not by omission:

| Value | Why not |
|---|---|
| Session and sequence numbers (Block 1) | A messaging interface allocates them |
| MAC, CHK, PDE and other Block 5 trailers | The network computes them |
| `Sgntr` in the MX header | The infrastructure signs |
| The MX transport wrapper | A market convention, so it must be configured |

If one is needed and not configured, output **fails with a message naming exactly what is
missing** rather than filling in something plausible. That is the intended behaviour.

## XSD validation is against a derived schema by default

MX documents are validated against a real XSD compiled by libxml2 — but by default that
schema is generated from *this repository's* configured subset, not the official ISO 20022
schema. It genuinely catches element order, cardinality, datatype, enumeration and
attribute errors. It does **not** prove conformance.

The response always says which schema was used (`SUBSET_DERIVED` or `OFFICIAL`). Place an
official `.xsd` in `backend/config/mx/xsd/official/` and the validator prefers it
automatically.

---

## Per-message limits

| Message | What is not covered |
|---|---|
| **MT530** | Configured processing changes only (priority). Cannot amend core trade data. |
| **MT537** | The configured penalty structure only, not the full Statement of Pending Transactions. Amounts are user-entered — there is no penalty calculator, because rates and rules are market data this repository does not have. |
| **MT564–MT568** | One event profile: Dividend With Options. Other corporate-action types are catalogue-only. |
| **sese.023** | Omits `Lnkgs`, `FinInstrmAttrbts`, `StgSttlmInstrDtls`, `CshPties`, `OthrAmts`, `OthrBizPties`, `SplmtryData`. |
| **sese.024** | Only the processing, matching and settlement status branches. No inferred matching, repair or modification status. |
| **sese.025** | Omits `Lnkgs`, `FinInstrmAttrbts`, `CshPties`, `OthrAmts`, `SplmtryData`. Partial-settlement reporting beyond the confirmed quantity is not configured. |

**Not implemented at all:** payments (`pacs.*`), cash management (`camt.*`), reconciliation
(`semt.*`), and the cancellation and modification lifecycle (`sese.020`, `sese.027`,
`sese.030`, `sese.031`).

The extension point for all of these is a YAML file. See
[../ARCHITECTURE.md](../ARCHITECTURE.md#adding-things).

---

## Round trips and imports

- Raw MT import and validation exist through the API, but the secure builder has no visual
  original-versus-recomposed diff.
- Unknown fields in an imported message are preserved as unsupported findings, not
  validated.
- **MX has no import path.** You can generate XML; you cannot yet parse someone else's back
  into fields.

## Output

- **RJE output fails closed** — the repository contains no authorised client interchange
  contract, and guessing the structure would be worse than not offering it.
- Validation evidence is HTML and JSON, not PDF.

## Identity and deployment

- The OIDC/SAML boundary exists, but no production identity-provider adapter or credentials
  are included. Development login is refused when `APP_ENV=production`.
- PostgreSQL and migrations work, but high availability, row-level security,
  backup and restore, KMS/HSM integration, secure purge, SIEM/DLP and key rotation are not
  implemented.
- Rate limits, the AI circuit breaker, the L1 cache and telemetry are **per process**. A
  multi-instance deployment needs shared state for all of them.

## External validation

The platform accepts uploaded, checksum-correlated validation evidence. It does not
integrate with MyStandards, Alliance or any vendor validation API, and claims no such
contract.

## Testing

Playwright covers the critical flows on Chromium at three widths. It does not cover other
browsers, full accessibility conformance, visual regression, or destructive operational
scenarios.

---

## What is genuinely solid

To be equally honest in the other direction:

- **19 message types generate end to end**, from the browser, from JSON and from Excel.
- **The FIN envelope is real.** Block 1 is a correctly structured basic header; Block 2 is a
  correctly structured application header. No `{1:DEMONSTRATION}` placeholder anywhere.
- **MX XML is namespace-correct, order-correct, and schema-validated** by libxml2.
- **Every value carries an origin**, so you can always tell what the tool produced and what
  it refused to.
- **All 38 samples across all 19 message types validate**, and a test asserts it — so a
  specification change that breaks one fails the build.
- **453 automated tests** cover it: 417 backend, 36 browser.
