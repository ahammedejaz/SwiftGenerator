# MT → MX mapping

What the knowledge base says about MT ↔ ISO 20022 correspondence, how much of a mapping it
supports, and how a conversion reports what it could and could not establish. The measured
state is [generated/mt-mx-mapping-coverage.md](generated/mt-mx-mapping-coverage.md);
the contract of a Mapping Pack is in [message-conversion.md](message-conversion.md).

## Evidence first

`python -m app.mapping evidence --scan` (`make mt-mx-mapping-scan`) sweeps every segment of
every indexed source for a fixed vocabulary — coexistence, migration, "ISO 20022",
equivalent, "replaced by", mapping, translation, the business-area prefixes (`pacs`,
`pain`, `camt`, `sese`, `seev`, `semt`), FINplus, InterAct, "Financial Institution Credit
Transfer" — and records every hit by identity: source id, checksum, page, section, segment
hash, phrase. No text, no model, no top-k. The committed index is
`backend/config/mappings/evidence-index.json`.

What the sweep found on 2026-08-21 (164 sources, 16,656 segments):

- **No coexistence, migration or translation document exists in the knowledge base.**
- The MT101, MT103, MT200, MT202 and MT205 guides state that the message is converted to
  its ISO 20022 equivalent over InterAct FINplus — without naming the equivalent.
- The MT205 Scope (page 4) names the **ISO 20022 Financial Institution Credit Transfer** as
  the equivalent of MT 200, 201, 202, 203 and 205. This is the one documentary target
  relationship in the corpus.
- The eight `pacs` XSDs name their own message definitions.

## Evidence classes

| Class | Meaning |
|---|---|
| `SOURCE_BACKED` | the target relationship **and every field rule** cite a document in the knowledge base |
| `TARGET_RELATIONSHIP_ONLY` | a document establishes which ISO 20022 message family corresponds to the MT; nothing states the field mapping |
| `NAME_CORRESPONDENCE` | the two documents' own titles correspond (an MT "Customer Credit Transfer" guide and an XSD named `FIToFICustomerCreditTransfer`); nothing relates them |
| `SYNTHETIC` | a repository fixture |

A pack declares its class in `provenance.evidenceClass`; the model refuses a
`SOURCE_BACKED` pack with an uncited rule, and a `NAME_CORRESPONDENCE` or `SYNTHETIC` pack
that claims to be `REVIEWED`. **No pack in the repository is `SOURCE_BACKED`**, because the
knowledge base holds no field-level mapping material; none is production eligible.

## Relationships registry

`backend/config/mappings/relationships.yaml` lists the correspondences the knowledge base
supports, each with its class, citations, the messages the same statement covers, and a
blocker where no pack can be built:

| Relationship | Class | Basis |
|---|---|---|
| MT205 (also MT200/201/202/203) → pacs.009.001.13 | `TARGET_RELATIONSHIP_ONLY` | MT205 Scope p.4; pacs.009 XSD |
| MT103 (also MT102) → pacs.008.001.14 | `NAME_CORRESPONDENCE` | MT103 p.4 conversion note; pacs.008 XSD title |
| MT104 (also MT107) → pacs.003.001.12 | `NAME_CORRESPONDENCE` | XSD title only; `NO_DOCUMENT_RELATES_THE_TWO`, no pack |
| MT541 → sese.023.001.11 | `SYNTHETIC` | repository fixture |

`GET /api/v1/messages/{mt}/conversion-targets` lists a relationship with no pack as a
target that is **not convertible**, with its evidence, so the UI can say "the relationship
is recorded; the field mapping is not".

## Mapping Packs

Three packs, all declarative YAML under `backend/config/mappings/`:

| Pack | Class | Review state | Rules (cited) |
|---|---|---|---|
| `CANDIDATE_MT202_TO_PACS009_V1` | `TARGET_RELATIONSHIP_ONLY` | `CANDIDATE_PREVIEW` | 17 (17) |
| `CANDIDATE_MT103_TO_PACS008_V1` | `NAME_CORRESPONDENCE` | `CANDIDATE_PREVIEW` | 21 (21) |
| `SYNTHETIC_MT541_TO_SESE023_V1` | `SYNTHETIC` | `SYNTHETIC_TEST_ONLY` | 17 (0) |

`CANDIDATE_PREVIEW` is a new review state: the pack executes only behind the explicit
preview opt-in (`allowSyntheticPreview`), every response labels it a candidate, and it can
never be production eligible. Every rule of a candidate pack cites the MT field
specification page its source field comes from and the XSD element its target is — the
citation states where each side is *defined*; the correspondence between them is the
candidate a reviewer accepts or refuses. The evidence record each pack points to
(`backend/config/mapping_sources/candidate_*.md`) says so in words.

Identity: source format/message/release/lane, target format/message/version/lane, pack
version, both structure checksums (a re-sync that changes either structure invalidates the
pack), the evidence file and its checksum.

### Operators

`DIRECT`, `TRANSFORM`, `CODE_MAP` (a closed `ENUM` table — `71A` `BEN/OUR/SHA` →
`ChrgBr` `CRED/DEBT/SHAR` as a candidate correspondence by definition), `CONDITIONAL`,
`ONE_TO_MANY`, `MANY_TO_ONE`, `OMIT`, `NOT_REPRESENTED`, `TARGET_REQUIRED_MISSING`. Kinds
are enforced against rule shape (`DIRECT` carries the value unchanged; `CODE_MAP` outputs
are tables). Transforms are a closed set — no Python evaluation: `IDENTITY`, `CONSTANT`,
`ENUM`, `JOIN`, `MT_DATE_TO_ISO`, `MT_AMOUNT_TO_ISO`, `MT_UNIT_QUANTITY`,
`MT_DATED_AMOUNT_DATE` and `MT_DATED_AMOUNT_TO_ISO` (the two halves of `32A`;
`YYMMDD` is read as `20YY-MM-DD`, recorded as a limitation), `MT_PARTY_BIC` (the BIC line of
a party option A).

### Business-semantic labels

Rules carry a `semantic` label from the small closed set (`transaction_reference`,
`settlement_date`, `settlement_amount`, `delivering_agent`, `receiving_agent`, …). It is the
lightweight intermediate vocabulary conversion reports group by; it is not an ontology.

## The conversion report

Every conversion returns: source, target, pack id and version, provenance, evidence class,
relationship citations, mapped / derived / user-supplied target fields, source fields not
represented (explicit `OMIT`/`NOT_REPRESENTED` plus anything no rule consumed),
`targetRequiredMissing` with a question per field, the transformations applied, the pack's
limitations, and **coverage**: mandatory target elements established / total, source rows
represented / total, rules cited / total. The UI states "N fields need additional
information before MX can be generated" and shows the evidence class and citations before
anything runs.

### Missing target data

`NEEDS_INPUT` is returned when a mandatory target leaf has no value — and, since this
engagement, when a mandatory **block** whose leaves are all optional (pacs.009's Debtor, a
choice of identifications) has nothing mapped into it: the deterministic validator names
the block and the leaf that would open it, and the caller is asked for that leaf. No party,
date or method is invented.

## Conversion proofs

`make mt-mx-mapping-write` converts each pack's source MINIMAL sample, answers every
`NEEDS_INPUT` question with the target's own deterministic sample values (never a value
drawn from the source), and records what came back. On 2026-08-21:

| Pack | Result |
|---|---|
| MT202 → pacs.009.001.13 | `NEEDS_INPUT` (CreDtTm, SttlmMtd, Debtor) → `READY` after 3 answers; 6/6 mandatory target elements; 8/20 source rows represented; XSD accepted |
| MT103 → pacs.008.001.14 | `NEEDS_INPUT` → `READY` after 6 answers; 7/7; 12/39; XSD accepted |
| MT541 → sese.023.001.11 | `READY`; 8/8; 12/17; XSD accepted |

Each proof runs MT → parse → canonical → mapping → target canonical → missing data →
deterministic MX composer → XSD validation through the ordinary `StudioService`; the LLM is
not in the path. `make mt-mx-mapping-check` (part of `make check`) re-renders the coverage
report from the committed index and proofs and fails on drift.

## What the LLM may do here

Explain a source or target field with citations (`POST /api/v1/ai/ask` with message
filters), and help a tester answer a `NEEDS_INPUT` question. It does not decide a mapping,
does not supply a mandatory target value, and never serialises XML.

## Remaining blockers

- No field-level mapping evidence (CBPR+ usage guidelines, translation rules, MyStandards
  coexistence material) is present in the knowledge base; until it is, no pack can be
  `SOURCE_BACKED` and none should be reviewed as authoritative.
- Target schemas for MT101 (`pain.001`), MT9xx statements (`camt.05x`) and cancellation
  requests (`camt.056`) are not in the knowledge base; no relationship is recorded for them.
- Repeated MX structures and repeated MT sequences are addressed at occurrence 1 only.
