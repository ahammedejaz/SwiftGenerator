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

Alongside that single word, every message now reports **capability dimensions** —
structure, business rules, market practice, client profile, external validation — each
derived from what actually exists, so a message compiled from a schema can never present
itself as more than structure-verified. A pack produced by the
[specification engine](specification-engine.md) reads `structure: COMPILED_FROM_SCHEMA`
and `businessRules: NOT_CONFIGURED`: XSD validation proves structure, and **only**
structure. Market practice (CBPR+, HVPS+, MyStandards guidelines) is a separate,
deliberately unbuilt layer — those artifacts are licensed and deployment-specific.

**Use it to produce test data. Do not use it as a conformance authority.**

Exact numbers per message: [generated/message-coverage.md](generated/message-coverage.md).

### One known domain-rule gap, now closed

The configured MT subset used to render `:22F::SETR//BUY` in Sequence B and
`:22F::SETR//RECE` in Sequence E. Neither is a settlement transaction type, and the field
belongs in Sequence E only — receive versus deliver is implied by the message type.

It is corrected. The source that settled it was already in this repository:
`backend/config/mx/sese.023.001.11.yaml` is the configured ISO 20022 definition of the same
business message, and it separates the three concepts explicitly — `SctiesMvmntTp`
(RECE/DELI) for direction, `Pmt` (APMT/FREE) for payment, and `SttlmParams/SctiesTxTp` for
the transaction type, whose own guidance names using the direction codes as a transaction
type as a mistake. Both formats now read one shared code list.

**What still is not established** is whether that code list is *complete*. It is this
repository's configured subset of the transaction types, not the authoritative one, and the
usual caveat above applies to it unchanged.

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

| **sese.020 / sese.027 / sese.030 / sese.031** | Implemented and generatable — the cancellation and modification lifecycle generates, validates and round-trips end to end — but the four specifications are **UNVERIFIED**: their version numbers, root element names and element sets were modelled on the ISO 20022 idioms already in this repository, not reconciled against an authoritative message-definition report. Reconcile before any use beyond internal testing. |

**Not implemented at all:** payments (`pacs.*`), cash management (`camt.*`) and
reconciliation (`semt.*`).

The extension point for all of these is a YAML file. See
[ARCHITECTURE.md](ARCHITECTURE.md#adding-things).

---

## Round trips and imports

Both formats import. `POST /api/v1/messages/import` reads an MT FIN message, an MT text
block or an ISO 20022 document back into canonical values and regenerates it through the
ordinary generation path, and `Compose(Parse(Compose(v))) == Compose(v)` is asserted for
every sample of every configured message. What it still cannot do:

- **A repeated block nested inside another repeated block cannot be addressed.** The
  occurrence address carries one index, so a structure that would come back somewhere else
  is refused — `MT_IMPORT_NESTED_REPEAT_UNSUPPORTED` and
  `MX_IMPORT_NESTED_REPEAT_UNSUPPORTED` — rather than silently reshaped. No configured
  message currently has such a structure in its samples.
- **An MT text block does not say what message it is.** Where the sequence skeleton fits
  more than one configured message — MT540 through MT543 share `GENL/TRADDET/FIAC/SETDET` —
  the import refuses and asks, instead of picking. A complete FIN message names itself in
  Block 2 and needs no help.
- **Anything outside the configured subset is reported, not imported.** An unknown tag or
  element is named in the response; it is never silently dropped, and it is never
  re-emitted either.
- **Block 5 trailers and the MX `Sgntr` element are read and deliberately not reproduced.**
  They are interface- and network-generated. The comparison labels them *never generated*
  and never counts them as a fault.
- **A message over 3,000 lines, or with more than 200 import problems, is not compared line
  by line.** You are still told whether the two messages are the same, and why the
  differences were not listed. Both limits sit far above anything the tool itself generates
  — a field occurrence caps at 100.

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

## Business rules are only as good as their evidence

The [rule engine](specification-rule-engine.md) enforces rules that trace to a named source
location. That is a claim about *this evidence*, never about the standard:

- **A reviewed rule pack means reviewed against the cited document.** It does not mean the
  document covers the standard, and `authoritativeCompletenessKnown` stays `false` — the
  model refuses `true`.
- **What ships is synthetic.** `DEMO_MARKET_V1` is a market invented for this repository and
  `DEMO_MARKET_CLIENT_V1` an invented client. Neither is CBPR+, HVPS+, SEPA, MyStandards or
  any custodian's guideline, and no real market practice is installed.
- **No base-business rule pack ships for any real message.** Deriving one from a synthetic
  document would claim knowledge of a real message's rules. The base layer is exercised in
  tests against a synthetic compiled message.
- **`sourceType` is an operator declaration.** The platform can know a document arrived
  through the drop directory and that someone labelled it; it cannot prove the file is the
  genuine licensed artifact.
- **Two extraction passes are not independent authorities.** They may share a provider, a
  model family and training data. Their agreement reduces review effort and establishes
  nothing.
- **The candidate vocabulary is nine rule shapes.** A source rule needing two conditions at
  once, or an exception that cannot be folded in, is reported as an ambiguity rather than
  approximated — so extraction misses things by design.
- **Conflict analysis is a set of deterministic checks, not a theorem prover.** It finds
  required-versus-forbidden, disjoint and widened code sets, unsatisfiable groups,
  contradictory dates and impossible conditions. A subtler contradiction can still pass.
- **PDF ingestion is a seam, not an implementation.** `pypdf` is not a dependency of this
  repository; convert with `pdftotext -layout` first. Scanned and image-only documents are
  refused, and there is no OCR.
- **The field list given to an extraction pass is capped.** For a very large message a rule
  about a field beyond the cap could not be found. Truncation is reported, never silent.

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

- **23 message types generate end to end**, from the browser, from JSON and from Excel.
- **The FIN envelope is real.** Block 1 is a correctly structured basic header; Block 2 is a
  correctly structured application header. No `{1:DEMONSTRATION}` placeholder anywhere.
- **MX XML is namespace-correct, order-correct, and schema-validated** by libxml2.
- **Every value carries an origin**, so you can always tell what the tool produced and what
  it refused to.
- **All 46 samples across all 23 message types validate**, and a test asserts it — so a
  specification change that breaks one fails the build.
- **1,354 automated tests** cover it: 1,274 backend, 80 in a real browser.
- **A clean clone works with nothing configured** — `make install`, `make check` and
  `make e2e` all pass with no `.env` and no API keys. That is verified, not assumed.
