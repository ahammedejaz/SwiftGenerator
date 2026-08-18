# What we need from you, and what it unlocks

This platform generates SWIFT MT and ISO 20022 messages from configuration it owns. It
contains **no licensed SWIFT or ISO artifact**, and nothing in it reproduces, paraphrases or
approximates one. Every coverage figure it reports is bounded by that, and it says so.

Four classes of artifact would move that boundary. This is the shopping list: what each one
is, where it goes, which setting points at it, what must be re-run, and — the part that
matters commercially — **what claim it lets us make that we cannot make today.**

**Please do not send copyrighted specification text into this repository.** Every location
below is either gitignored or must be added to `.gitignore` before a licensed file is copied
in. A drop directory outside the checkout is safer still; every location has a setting for
exactly that.

`GET /api/v1/sources` reports which of these are present right now, and `make coverage`
renders the same into [generated/message-coverage.md](generated/message-coverage.md).
The step-by-step procedure is [authoritative-sources.md](authoritative-sources.md).

---

## 1 · SWIFT MT (ISO 15022)

### What we need

| # | Artifact | Why |
|---|---|---|
| 1.1 | **Licensed, release-specific MT message specification** for MT530, MT537, MT540–MT548, MT564–MT568 | The format rows, sequences, options, qualifiers and code lists we currently hold as a hand-built subset |
| 1.2 | **Message Format Validation Rules** for the same release | Network validated rules (the `C`/`D`/`E` rules) that we defer today rather than enforce |
| 1.3 | **Client-specific message usage rules** | Which optional fields your counterparties require, and which codes they refuse |
| 1.4 | The **standards release** those documents belong to (e.g. SR2026) | So the registry can state what it was reconciled against |

### Where it goes

| | |
|---|---|
| **Location** | `backend/config/specifications/` (the manifest) and `backend/config/knowledge/` (per-tag records) |
| **Setting** | `MT_SPECIFICATION_MANIFEST` |
| **Format** | YAML. The structure already fits; the existing files are the worked example |

### Re-run after loading

`make check` — **all of it**. Golden fixtures in `backend/tests/golden/expected/` will change
if any row order, format or qualifier changes; update them in the same commit and say why.
Then `make coverage-write` and `make demo-pack`.

### What it unlocks

- A **real denominator**. Coverage stops being subset-relative and starts being a percentage
  of the standard.
- Network validated rules become **enforceable** rather than deferred.
- The documented `22F::SETR` sequence-placement question can finally be settled from a source
  instead of left as a recorded discrepancy.
- **This is the only artifact that changes what the platform may claim about MT.** Nothing
  else on this page does.

---

## 2 · ISO 20022 (MX)

### What we need

| # | Artifact | Why |
|---|---|---|
| 2.1 | **Official XSDs** for each message version in use | So schema validation is conformance rather than internal consistency |
| 2.2 | **Message Definition Reports** for those messages | Element sets, cardinality, representation classes and the message root |
| 2.3 | **Message Usage Guides** where they exist | Which optional elements are used in practice |
| 2.4 | **The approved message versions** for your environment | We currently guess nothing — but we also cannot confirm we chose the right versions |

### Where it goes

| | |
|---|---|
| **Location** | XSDs: `backend/config/mx/xsd/official/<version>.xsd` — e.g. `sese.023.001.11.xsd`. Definitions: `backend/config/mx/*.yaml` |
| **Setting** | `MX_OFFICIAL_XSD_DIRECTORY`, `MX_SPECIFICATION_DIRECTORY` |
| **Already gitignored** | `backend/config/mx/xsd/official/*.xsd` |

### Re-run after loading

XSDs: restart the backend, generate any message of that version, confirm the XSD layer
reports `OFFICIAL`. Then `make check`.

Definitions: reconcile the existing YAML rather than replacing it. For a message actually
reconciled, set `authoritativeCompletenessKnown: true`, update `source.sourceType`,
`sourceReference`, `reviewedAt` and `reviewedBy`, and remove the `UNVERIFIED` limitation.
`tests/studio/test_mx_lifecycle.py` asserts that caveat is present on the four lifecycle
messages — a reconciled message must be removed from that list **in the same commit, with the
source named in the commit message**.

### What it unlocks

- The XSD layer reports `OFFICIAL` instead of `SUBSET_DERIVED`, per version.
- `capability` may rise above `PARTIAL` for a reconciled message.
- **`sese.020.001.08`, `sese.027.001.08`, `sese.030.001.10` and `sese.031.001.09` stop being
  `UNVERIFIED`.** Their versions, root element names and element sets were modelled on ISO
  20022 idioms already in this repository and reconciled against nothing. This is the single
  largest outstanding risk in the platform and 2.2 is what closes it.

---

## 3 · Client and market practice

### What we need

| # | Artifact | Why |
|---|---|---|
| 3.1 | **MyStandards usage guidelines** for each counterparty | The restrictions that make a message acceptable to *them*, not just valid |
| 3.2 | **Client profiles** — allowed currencies, reference formats, envelope values | Ours are demonstration values with a `DEMO` prefix |
| 3.3 | **CSD / custodian market practice** for the settlement locations in scope | Place-of-settlement representation is currently a synthetic proprietary value |
| 3.4 | **Required code restrictions** — which values of each controlled code list are permitted | We accept the full configured list |
| 3.5 | **Mandatory/conditional overrides** — optional fields your counterparties require | We enforce the specification's presence, not yours |

### Where it goes

| | |
|---|---|
| **Location** | `backend/config/profiles/` — one YAML per profile |
| **Setting** | `CLIENT_PROFILE_DIRECTORY` |
| **Format** | The two committed profiles are the worked example |

### Re-run after loading

`make check`. A new profile is picked up by the catalogue automatically; no code change.

### What it unlocks

- The `CLIENT_PROFILE` validation layer starts reflecting a real counterparty instead of a
  demonstration one.
- Envelope values stop being placeholders, so the `FIN_ENVELOPE` layer can build a complete
  Block 1 without failing closed.
- Generated messages become **acceptable to a named counterparty**, not merely well-formed.

---

## 4 · Connectivity (UAT)

Nothing in this section exists in the platform today. RJE export and submission **fail
closed** precisely because guessing any of it would be worse than not offering it.

### What we need

| # | Artifact | Why |
|---|---|---|
| 4.1 | **UAT connector contract** | The interface we would be integrating with at all |
| 4.2 | **Required payload and envelope** — RJE, MQ, file drop, API? | Determines what "send" even means |
| 4.3 | **Authentication mechanism** and credential handling | Certificates, mTLS, API key, HSM-held keys |
| 4.4 | **Endpoint and network details** — host, port, allow-listing, VPN | |
| 4.5 | **ACK/NAK contract** — shapes, timeouts, retry and idempotency rules | So a test can assert on the response rather than on silence |
| 4.6 | Who owns the **UAT environment** and its change window | |

### Where it goes

A new adapter behind the existing submission boundary. `SUBMISSION_MODE` and
`EXTERNAL_VALIDATION_REQUIRED_FOR_SUBMISSION` already gate it; `RJE_EXPORT_ENABLED` is
`false` for the same reason.

### Re-run after loading

`make check`, plus new integration tests against the UAT endpoint. Submission must stay
disabled by default and behind an explicit environment flag.

### What it unlocks

- End-to-end testing against a real interface rather than a generated file.
- External validation evidence, which is a prerequisite for **any** capability claim above
  `PARTIAL` regardless of what else is loaded.

---

## What none of this changes

Whatever arrives, these stay true, because they are correctness properties rather than
coverage gaps:

- **Session and sequence numbers, MAC, CHK and other authentication trailers, and the MX
  `Sgntr` element are never generated.** A messaging interface or the network allocates them.
  A test asserts the platform refuses even when a profile asks it to. An authoritative
  specification describes what those values look like; it does not make it honest for this
  platform to produce one.
- **The AI layer never generates a message.** It turns natural language into structured
  intent and nothing else.
- **`capability` is not a configuration value.** It is raised only by evidence, and a
  reconciled specification is necessary but not sufficient — external validation (4.x) is
  also required.

---

## Priority, if you can only get one thing

1. **2.2 — Message Definition Reports.** Cheapest removal of the largest caveat: it takes
   four of seven MX messages out of `UNVERIFIED`.
2. **1.1 — the licensed MT specification.** The only thing that changes what we may claim
   about the 16 MT messages.
3. **2.1 — official XSDs.** One folder, no code, and MX validation becomes conformance.
4. **3.1 — MyStandards guidelines** for the counterparties actually in scope.
