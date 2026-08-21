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

## No authoritative MT-to-MX mapping ships

The conversion engine and UI are deterministic and validated, but the bundled MT541 to
sese.023 Mapping Pack is a synthetic software fixture. It is production-ineligible and
disabled unless a tester explicitly enables synthetic preview. No SWIFT coexistence guide,
approved client mapping or other authoritative mapping evidence was available, so real
source-backed conversion reports `BLOCKED_BY_MAPPING_EVIDENCE` rather than guessing.

MT and MX are not generally reversible or one-to-one. Even an approved pack must report
missing, derived and not-represented data. See [message-conversion.md](message-conversion.md).

## Operator knowledge sources are not distributed

The local audited PDF/XSD set has no recorded redistribution authorization. It is ignored by
Git and not placed in LFS. A clean clone therefore starts with configured messages only.
Authorized operators may install a checksum-pinned bundle separately; see
[knowledge-distribution.md](knowledge-distribution.md).

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

## Real-schema scale-out needs source artifacts

Phase 3 source tooling can resolve current message-definition identities from the official
ISO 20022 catalogue and can batch compile local source bundles, but this repository still
does not commit ISO XSD bodies. The committed catalogue snapshot is metadata only:
versions, source URLs, source locations and redistribution declarations. Until an operator
places legitimate XSD bytes in the ignored source cache, `make mx-scaleout` reports
missing-source failures rather than fabricating schemas.

---

## Prowide MT evidence is structural and build-time only

Phase 4B extends the pinned Prowide Core extractor to all MT source model classes present
in the selected artifact. It is a developer tool, not a runtime dependency and not a
conformance authority.

What it can say:

- a Prowide message class exists in the pinned artifact
- a generated Prowide source scheme listed a sequence, fieldset or field group
- a global Prowide field class exposed parser and validator patterns
- the repository's generated MT541 tag stream can be parsed by Prowide into the same tags

What it cannot say:

- the repository is Swift-certified or ISO 15022 compliant
- a message is complete against the Swift UHB
- a qualifier or code is legal in a particular message
- a field is mandatory in a message because a global field class exists
- network validation, market practice or client usage rules are covered

All non-configured Prowide source models remain inert candidates **in the configured
lane**. The reports name structural differences between Prowide evidence and the configured
subset, and nothing rewrites runtime MT structures from those differences. Since Phase 6 the
same evidence is also compiled into local Structure Packs for a separate, explicitly named
`KNOWLEDGE_PREVIEW` lane — see [the knowledge base section](#the-knowledge-base-and-any-message)
below for what that does and does not establish.

## MT semantic rules need real semantic sources

Phase 5A adds MT semantic-rule ingestion foundations, but no authorised MT semantic source
is present in this repository. The committed MT semantic fixture is synthetic and exists
only to prove the pipeline. The generated reports say this explicitly:

- [generated/mt-semantic-readiness.md](generated/mt-semantic-readiness.md)
- [generated/mt-semantic-source-readiness.md](generated/mt-semantic-source-readiness.md)

What this means:

- `REAL_MT_SEMANTIC_SOURCE_AVAILABLE = NO`
- candidate MT rules remain inactive until reviewed and committed as Rule Packs
- canonical MT references are evidence metadata, not runtime field definitions
- Prowide structural evidence does not establish qualifier legality, requiredness,
  cardinality, market practice, client profile rules or external-validation capability
- normal FastAPI runtime does not require Java, Prowide, Maven or Gradle

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

**Not in the configured lane:** payments (`pacs.*`), cash management (`camt.*`) and
reconciliation (`semt.*`). Eight `pacs` schemas the operator supplied compile to
`GENERATION_READY` structures in the knowledge-preview lane (below); nothing `camt.*` or
`semt.*` has been supplied, so nothing of the kind exists.

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

## Reading SWIFT Message Reference Guides

- **The two guides read are SR2026, which is not live until 14 November 2026.** Everything
  derived from them is future-test. No SR2026 rule validates anything, and the installed
  runtime structure is a third release again.
- **Occurrence-local rules can now be represented, but they remain candidates.** Phase 5C
  added `rule-dsl/2` occurrence scopes and retranslated the MT540/MT541 SR2026 candidates:
  all eight Phase 5B `UNSUPPORTED` occurrence rules are now either exact or deliberately
  partial. This did not activate any SR2026 rule, approve any candidate, or make the
  current-live runtime use the future-test guides.
- **Fifteen rules are still represented more weakly than the source states them.** Each
  carries the clause it dropped — a distinct-occurrence requirement, a data-source-scheme
  caveat, a format-option constraint, paired-code semantics or component scope — so it can
  miss a violation but never invent one.
- **A component of a field cannot be referenced.** A reference resolves to a field, so a
  rule that turns on a data source scheme or a format option within one is partial by
  construction.
- **No independent SR2026 structural source exists to cross-check against.** Prowide
  publishes SRU2026 source tags but no Maven Central artifact, and this repository pins
  checksummed artifacts. Grounding is `MRG_DOCUMENTARY_ONLY`.
- **Translation recognises a closed set of sentence forms.** A guide phrasing a rule in a
  form the reader does not know reports `NOT_RECOGNISED` for that rule and extracts the
  rest. Both guides read here were fully recognised; another message need not be.
- **No candidate has been reviewed.** Machine checks establish that a candidate is well
  formed. Only a person reading the named page establishes that it is right.

## The knowledge base and "any message"

Phase 6 lets the platform index authorised sources an operator drops into an ignored local
folder and, where deterministic structure evidence exists, generate test messages for
message types nobody configured by hand. The limits on that are exact.

- **"Any message" means any message with an authorised source *and* deterministic
  structural evidence, as far as the gates prove — no further.** The evidence today is the
  pinned Prowide `SR2025` fixture (274 MT models), the Format Specification tables of the
  14 `SR2026` Message Reference Guides in the operator's folder, and 8 `pacs` XSDs. A
  message outside that set does not exist to the platform, and no LLM is asked to invent
  it.
- **Readiness is a measured state, not a promise.** Of 293 message/release structures on
  2026-08-20: 209 `GENERATION_READY` (201 MT, 8 MX), 10 `STRUCTURE_VERIFIED` (a sample
  validated and composed, but `Compose(Parse(Compose(v)))` failed), 69
  `STRUCTURE_AVAILABLE` (a pack loads but a gate failed — `QUALIFIER_EVIDENCE_MISSING`,
  `FORMAT_FIDELITY_PARTIAL`, `MESSAGE_GENERATION_NOT_READY`, `STRUCTURE_SOURCE_CONFLICT`),
  5 `KNOWLEDGE_ONLY` (MT035, MT043, MT048, MT049, MT096 — Prowide models with no block-4
  fields). A `KNOWLEDGE_ONLY` message can be searched and asked about; it cannot be
  generated, and the API says so with the blocker rather than producing something.
- **`GENERATION_READY` is structure-backed test generation and nothing more.** Every preview
  pack carries the same `limitations`: repetitive fields inside one sequence occurrence
  render once; Network Validated Rules, usage rules, market practice and client rules are
  not evaluated unless a reviewed Rule Pack is installed; not Swift certification,
  conformance or proof of User Handbook completeness. The Prowide caveats above apply to
  every MT preview pack unchanged.
- **The preview lane is not the configured lane.** The 23 configured messages are
  unchanged, still the default, and still the only ones with reviewed rule packs, golden
  files and the full test suite behind them. A preview of a configured message in the
  current-live release is not even listed beside it. Nothing promotes a preview pack into
  `backend/config/`; that remains a reviewed commit.
- **Three releases are in play and they are kept apart.** The configured lane is
  `PUBLIC_UHB_REVIEW_2026_08_05`; Prowide evidence is `SR2025` (current live); the guides
  are `SR2026`, which is not live until 14 November 2026 and is labelled `FUTURE_TEST`.
  A future-release preview proves nothing about the current-live behaviour of that
  message.
- **Message Reference Guides are read for text and for Format Specification tables only.**
  Their rules are not activated (see the previous section); their tables corroborate or
  contradict Prowide structure and a contradiction is recorded, never resolved by guessing.
- **Retrieval over the real corpus is lexical.** By default no licensed or unclassified
  source's text may leave the machine, so none of the 23 real sources is embedded and
  semantic search does not run over them. The hybrid lexical+semantic path is proven on the
  synthetic fixture corpus and by a live probe, not on the licensed documents. Allowing it
  is a deliberate two-setting decision by the operator, recorded on every source.
- **AI answers are bounded, not deterministic.** The model proposes; the validator and
  composer decide. Two runs against a live model may propose different valid values. The
  validated-sample cache pins an answer once it passed, and the `scripted` provider pins the
  deterministic seed for tests — but "the same request gives the same sample" holds only
  while the cache key (structure checksum, rule packs, corpus version, prompt version,
  provider, model) is unchanged.
- **Citations point at a document, page and section.** They do not reproduce licensed text
  unless the source's policy allows it. A reviewer still has to open the page.
- **Identity is read from content.** A text or HTML document that is not a recognisable
  guide is indexed as an operator-supplied document with whatever message and release its
  text names, or none; a file that cannot be read at all is recorded as `UNREADABLE` with
  the classification `LICENSED_UNKNOWN` — blocked from external processing like everything
  else that is not a synthetic fixture. A suffix outside `.pdf .txt .md .markdown .html
  .htm .xsd .xml .zip` is reported as unsupported and skipped.
- **Still no SWIFT network, no MyStandards connection, no certification.** The knowledge
  base reads files an operator already holds the rights to. It fetches nothing.

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
- **Every `GENERATION_READY` preview structure earned the label** by loading, sampling,
  validating, composing, parsing back and re-composing identically through the ordinary
  engine — and for MX, by the source XSD accepting the output.
- **1,642 automated tests** cover it: 1,546 backend (22 skipped, 6 live-only deselected),
  96 in a real browser — measured 2026-08-21 on the Phase 6 branch.
- **A clean clone works with nothing configured** — `make install`, `make check` and
  `make e2e` all pass with no `.env` and no API keys. That is verified, not assumed.
