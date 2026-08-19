# Importing an authoritative source

This repository generates SWIFT messages from configuration it owns. It does **not** contain
any licensed SWIFT or ISO 20022 artifact, and nothing here reproduces, paraphrases or
approximates one. Every coverage figure the platform reports is bounded by that, and says so.

Four classes of artifact would move the boundary. This document is the procedure for each:
where it goes, what reads it, what changes, and what must be re-run. None of them requires a
code change — that is the point of the layout described here.

`GET /api/v1/sources` reports the same information at runtime, including what is actually
present, and `make coverage` renders it into
[generated/message-coverage.md](generated/message-coverage.md).

## Before you start

Obtain the artifact through your own licence. Do not download it into the repository from an
unlicensed mirror, and do not commit it: `.gitignore` already excludes `*.xsd` under the
official-schema directory, and anything else licensed must be excluded the same way before
it is copied in. A drop directory outside the checkout is safer still — every location below
has a setting that points somewhere else.

---

## 1. Official ISO 20022 schemas

| | |
| --- | --- |
| **Artifact** | The published `.xsd` for a message definition. |
| **Location** | `backend/config/mx/xsd/official/` |
| **Setting** | `MX_OFFICIAL_XSD_DIRECTORY` |
| **Naming** | Exactly the version string: `sese.023.001.11.xsd`. |

**Procedure.** Copy the file in, restart the backend, generate any message of that version.

**What changes.** The `XSD` validation layer reports `OFFICIAL` instead of `SUBSET_DERIVED`,
for that version only. Validation then proves conformance to the schema you supplied —
today the derived schema proves only that a document matches this repository's own YAML.
One honesty boundary is yours to hold: the platform verifies against the file in the drop
location; it cannot verify that the file is the genuine ISO artifact. That assurance comes
from your licence and your procedure, and `OFFICIAL` records your declaration, not a
verification the platform performed.

**What to re-run.** `make check` — the derived-schema tests still pass, because messages
without an official schema are unaffected.

**Going further.** The same schema can also *create* the message's specification pack:
`make spec-compile SOURCE=path/to/schema.xsd` compiles it into the `config/mx` format,
runs six gates (including validating a generated sample against the schema itself), and
records the schema's sha256 in the pack's provenance. See
[specification-engine.md](specification-engine.md). Whether the compiled pack — a derived
structural description — may be committed to a repository is a licensing judgement that
belongs to you, not to this tool; when in doubt, keep packs in a drop directory alongside
the schema and point `MX_SPECIFICATION_DIRECTORY` at it.

---

## 2. ISO 20022 message definition reports

| | |
| --- | --- |
| **Artifact** | The approved message-definition report, or metadata derived from it under your licence. |
| **Location** | `backend/config/mx/` — one YAML file per message. |
| **Setting** | `MX_SPECIFICATION_DIRECTORY` |

**Procedure.** Reconcile the existing YAML against the report rather than replacing it
wholesale: element names, order, cardinality, representation classes and the message root.
The file format is documented by the files already there; a node has `dataType` **or**
`children`, never both, and document order is element order.

Then, and only for a message actually reconciled:

- set `authoritativeCompletenessKnown: true`
- change `source.sourceType` from `CONFIGURED_SUBSET_REQUIRES_VERIFICATION` to the identifier
  of what you reconciled against, and set `sourceReference`, `reviewedAt` and `reviewedBy`
- remove the `UNVERIFIED` limitation, if the message carries one

**What changes.** `capability` may rise above `PARTIAL` for that message. The coverage report
stops listing it under "message definitions that are themselves unverified".

**What to re-run.** `make check` and `make coverage-write`. `tests/studio/test_mx_lifecycle.py`
asserts the `UNVERIFIED` caveat is present on the four lifecycle messages; a reconciled
message must be removed from that list in the same commit, with the source named in the
commit message.

**Currently unverified:** `sese.020.001.08`, `sese.027.001.08`, `sese.030.001.10`,
`sese.031.001.09`. Their version numbers, root element names and element sets were modelled
on the ISO 20022 idioms already present here and reconciled against nothing.

---

## 3. Licensed SWIFT MT specification

| | |
| --- | --- |
| **Artifact** | Release-specific ISO 15022 format rows, sequences, qualifiers, code lists, usage rules and network validated rules. |
| **Location** | `backend/config/specifications/supported_subset_v1.yaml` and `backend/config/knowledge/*.yaml` |
| **Setting** | `MT_SPECIFICATION_MANIFEST` |

**Procedure.** Point the setting at a manifest built from the licensed release. The manifest
declares `registryVersion`, `standardsRelease`, `authoritativeCompletenessKnown`, a `source`
block and one entry per message with its sequences; field rows come from the knowledge base
keyed by `knowledgeId`. Both must be reconciled together — the registry refuses to load a
sequence a knowledge record references but the manifest does not declare.

**What changes.** This is the only artifact that changes what the platform may *claim*.
Coverage percentages stop being subset-relative. Network validated rules and usage rules
become enforceable rather than deferred. The documented `22F::SETR` sequence-placement
question can finally be settled from a source instead of a guess.

**What to re-run.** Everything. Golden fixtures in `backend/tests/golden/expected/` will
change if any row order or format changes; update them in the same commit and say why.

---

## 4. Client MyStandards usage guidelines

| | |
| --- | --- |
| **Artifact** | A counterparty's own restrictions: permitted codes, mandatory optional fields, reference formats, envelope values. |
| **Location** | `backend/config/profiles/` — one YAML file per profile. |
| **Setting** | `CLIENT_PROFILE_DIRECTORY` |

**Procedure.** Add a profile file. `profileId` must be unique; the loader refuses a
duplicate. Set `allowedCurrencies`, `clientRequiredFields`, `validation.senderReference` and
the `finEnvelope` / `mxEnvelope` blocks from the guideline.

**What changes.** The `CLIENT_PROFILE` validation layer starts reflecting a real
counterparty. Envelope values stop being demonstration placeholders — which also means the
`FIN_ENVELOPE` layer can produce a complete Block 1 without the studio failing closed.

**What to re-run.** `make check`. A new profile is picked up by the catalogue automatically.

---

## 5. Business-rule source documents

| | |
| --- | --- |
| **Artifact** | A message definition report, message usage guide, market-practice document or client guideline — the *evidence* business rules are derived from. |
| **Location** | `backend/config/rule_sources/` — the documents, plus `sources.yaml` declaring them. |
| **Setting** | `RULE_SOURCE_DIRECTORY` |

**Procedure.** Drop the document in, declare it in `sources.yaml` with a stable
`sourceId`, its `sourceType` and a redistribution policy, then
`make rule-source-ingest SOURCE_ID=…` and record the checksum it prints. From there the
rule engine's offline pipeline produces candidates, a person reviews them, and the reviewed
pack is committed to `backend/config/rules/`.

**What changes.** The `BUSINESS_RULES`, `MARKET_PRACTICE` and `CLIENT_PROFILE` validation
layers start enforcing rules traceable to a named source location, and the corresponding
capability dimension moves.

**What is committed.** The derived pack only — identity, location, checksums, and a short
excerpt **only** where the operator declared excerpts redistributable. `.gitignore` keeps
the documents themselves out of the repository. `sourceType` is an operator declaration in
exactly the sense §1 describes: the platform can know a file arrived through this directory
and that someone labelled it, and cannot prove it is the genuine licensed artifact.

**What to re-run.** `make check` and `make rule-validate PACK=…`. See
[rule-source-handling.md](rule-source-handling.md).

---

## What none of this changes

Session and sequence numbers, MAC, CHK and other authentication trailers, and the MX
`Sgntr` element remain **never generated**, whatever a source says. They are allocated by a
messaging interface or by the network, and a test asserts the platform refuses to invent
them even when a profile asks it to. An authoritative specification describes what those
values look like; it does not make it honest for this platform to produce one.
