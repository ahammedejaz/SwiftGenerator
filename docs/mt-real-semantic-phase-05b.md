# Reading a SWIFT Message Reference Guide

How this repository reads a real, authorised SWIFT MyStandards MT Message Reference Guide
as evidence — and why nothing it produces validates anything.

Design record: [mt-real-semantic-phase-05b-plan.md](mt-real-semantic-phase-05b-plan.md).
Measurements: [history/specification-engine-phase-05b-report.md](history/specification-engine-phase-05b-report.md).

---

## Why SR2026 is future-test

The two guides state `Standards MT November 2026` on their cover pages. SWIFT's published
schedule puts Standards Release 2026 live on **14 November 2026**. Everything derived from
them therefore belongs to a **future-test** lane and cannot touch the current-live one.

Three releases are in play, and confusing any two of them is the failure this phase is
designed around:

| Lane | Release | Where it comes from | What it governs |
|---|---|---|---|
| Installed runtime | `PUBLIC_UHB_REVIEW_2026_08_05` | `backend/config/specifications/` | every message this platform generates today |
| Structural evidence | `SR2025` | pinned Prowide `SRU2025-10.3.18` | comparison only, never semantics |
| This phase | `SR2026` | the two Message Reference Guides | candidate rules, active nowhere |

The lane is a **recorded constant**, not a comparison against the clock. A report rendered
in 2027 says the same thing as one rendered today, because a release lane that moved on its
own would be a validation rule that changed overnight without a commit.

## Where the documents live, and why not here

The guides are licensed. Their own Legal Notices restrict disclosure outside the licensee's
organisation, so:

- the documents are read from a local drop directory — `MT_MRG_SOURCE_DIRECTORY`, default
  `swiftKnowledgeBase/` — which `.gitignore` excludes;
- `sourceMayBeCommitted` and `excerptsMayBeCommitted` are both `false`, so no candidate
  carries an excerpt;
- `sourceAllowsExternalModelProcessing` and `providerApprovedForSourceClassification` are
  both `false`, so no segment may be sent to any model provider.

What *is* committed is `backend/config/rule_sources/mt-mrg-sources.yaml`: the declaration.
It names each guide, the release it states, the message it describes and the SHA-256 of the
exact bytes the candidates were read from. Re-export the guide and the digest stops
matching, and ingestion refuses rather than deriving rules from bytes nobody reviewed.

Reading a PDF needs a text extractor this application deliberately does not depend on:

```bash
backend/.venv/bin/pip install pypdf
```

## How evidence is identified without being reproduced

Everything downstream of reading a guide works from
`backend/tests/fixtures/mt_mrg/sr2026-mt540-mt541.json` — derived metadata, committed. It
holds message and release identity, digests, page numbers, sequence and field identifiers,
the qualifier tables, source rule numbers, SWIFT error codes and the expressions this
repository generated. It holds no sentence of the source: a rule's wording is represented
only by its hash, which is enough to notice that SWIFT reworded it and not enough to read
it. A test walks the whole file and fails if any recorded string is long enough to be a
sentence.

That file is what lets `make check` verify the entire pipeline on a machine that has never
held a licensed document — including CI, which never will.

## How the reading works

Deterministic end to end. The guide states its own structure, so asking a model which page
holds the rules would replace a fact with a guess.

```
declared source                     mt-mrg-sources.yaml, with the expected digest
      │
   ingest                           app/rule_engine/sources.py — the ordinary path
      │                             bytes → checksum → page-marked text → segments
   identity                         the cover page: release, book, message, publisher
      │                             a filename is never trusted
   classify                         section spans from the guide's own headings,
      │                             at line granularity — two sections share a page
   format tables                    sequences, rows, qualifier tables, code lists
      │
   discover                         every Cn, with page, error codes and a text digest
      │
   translate                        a closed set of sentence forms; refusal for the rest
      │
   resolve                          references against the structure the guide states
      │
   refute                           the guide's own CR columns, against what was bound
      │
   compile                          app/rule_engine/compiler.py — the same compiler
      │
   REVIEW_REQUIRED
```

### Translation is sound in one direction

An expression may say **less** than the source rule; it may never say **more**. A weaker
rule misses a violation a reviewer can still catch. A stronger rule rejects messages SWIFT
accepts, which is the one outcome a testing platform must never produce.

Every translated rule is classified:

| Fidelity | Meaning |
|---|---|
| `EXACT` | the expression means what the source rule means |
| `PARTIAL` | strictly weaker; the dropped clause is recorded and travels with the candidate |
| `UNSUPPORTED` | no sound expression exists; the reason is recorded, never approximated |
| `NOT_RECOGNISED` | the guide states the rule in a form this reader does not know |

### Occurrence scope after Phase 5C

Phase 5B deliberately refused occurrence-blind approximations for rules that constrain
fields **within one occurrence** of a repeating subsequence. Phase 5C added a generic
`rule-dsl/2` primitive, `forEachOccurrence`, so the deterministic evaluator can run an
assertion separately inside each structural repeat occurrence.

That closed the eight Phase 5B `UNSUPPORTED` MT540/MT541 candidates. The current counts
are:

| Message | Exact | Partial | Unsupported |
|---|---:|---:|---:|
| `MT540` | 11 | 7 | 0 |
| `MT541` | 12 | 8 | 0 |

The remaining partial candidates are still weaker than the source. They drop clauses the
DSL still does not claim to understand, such as data-source-scheme exceptions, field
component scope, format-option tests, paired-code semantics and "another occurrence"
relationships. No candidate became active or reviewed as part of this change.

### Refutation without a second opinion

The guide cross-references itself: every qualifier table carries a `CR` column naming the
Network Validated Rules that govern that qualifier. Comparing that column against what a
translation actually binds is a criticism the document supplies, and there is no way for two
readings to agree by having made the same mistake. Both directions are reported —
a rule that binds more than the guide says it governs, and a rule that binds less.

## How review works, and why candidates are inactive

`docs/generated/mt540-sr2026-rule-review.md` and its MT541 counterpart give one entry per
rule: the candidate identifier, the source rule number, the SWIFT error code, the page, the
resolved references, the expression in plain language, what the expression leaves out, and
the deterministic cross-check. No source text.

Reviewing one entry means opening the named page, reading the rule under its own number,
and deciding whether the expression says the same thing. There is no approval switch. A
reviewer who agrees edits the candidate into a rule pack and puts it through the ordinary
path — `candidate → review → git diff → PR → CI → merge` — which is the only way anything
becomes active in this repository.

Until that happens:

- no candidate pack is written to `backend/config/rules/`;
- `RulePackRegistry` loads only fully reviewed packs, and refuses rather than skips;
- every candidate is `REVIEW_REQUIRED`;
- runtime activations from this phase: **0**.

## How SR2026 eventually becomes current-live

1. A reviewer approves candidates, message by message, against the guide.
2. The runtime MT structure gains the subsequences the rules target — `E1`, `E3`, `A1` —
   because most candidates today resolve against the guide's structure and not the
   installed subset.
3. On 14 November 2026 the release lane moves, and the reviewed packs for SR2026 become the
   current-live ones. Nothing about that step is automatic.

## Commands

```bash
make mt-mrg-check                     # generated reports are current       (no documents)
make mt-mrg-inspect                   # what is declared, and what is present
make mt-mrg-extract                   # re-read the guides into the evidence fixture
make mt-mrg-reports-write             # regenerate docs/generated/*sr2026*
make mt-mrg-evaluate                  # prove the candidate rules behave
make verify-real-mt540-mt541-source   # the committed evidence reproduces exactly
```

Only the first is part of `make check`, and it is the only one that needs no document.
The others report `SOURCE_NOT_AVAILABLE` and exit cleanly where the guides are absent, which
is the normal state of a clean clone.

Point `MT_MRG_SOURCE_DIRECTORY` at a drop directory, or leave it unset for
`swiftKnowledgeBase/` beside the checkout:

```bash
make verify-real-mt540-mt541-source MT_MRG_SOURCE_DIRECTORY=/path/to/guides
```

## What this does not establish

- Not that MT540 or MT541 is SWIFT certified. No certification exists here.
- Not that SR2026 validation is implemented. No SR2026 rule is active anywhere.
- Not that every SR2026 rule is supported. The counts in
  [generated/mt-sr2026-semantic-readiness.md](generated/mt-sr2026-semantic-readiness.md)
  say exactly which are.
- Not that any candidate is correct. Machine checks establish that a candidate is well
  formed; only a person who can read the page establishes that it is right.
- Not that client market practice or MyStandards usage guidelines are covered. Neither has
  been supplied.

## Adding the next message

Drop the guide in, add an entry to `mt-mrg-sources.yaml` with its digest, and run
`make mt-mrg-extract`. No message-specific code exists or is needed: identity, sections,
structure, rules and references all come from the document. A guide whose rules use a
sentence form this reader does not know reports `NOT_RECOGNISED` for those rules and
extracts the rest — which is the behaviour to want, because the alternative is inventing a
reading of a sentence nobody anticipated.
