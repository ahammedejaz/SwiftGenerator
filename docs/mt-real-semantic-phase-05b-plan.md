# Phase 5B plan — reading real authorised MT semantic source

The design record for Phase 5B, and the self-review it was corrected by. What was built is
described in [mt-real-semantic-phase-05b.md](mt-real-semantic-phase-05b.md); what actually
happened, with measurements, is in
[history/specification-engine-phase-05b-report.md](history/specification-engine-phase-05b-report.md).

> **Order of work.** The audit, the git and source verification and the baseline ran first.
> The reader was then built against the real documents, and this plan was written and
> self-reviewed alongside it rather than ahead of it. Several decisions below — the
> soundness rule for translation, the refusal to extend the DSL, the choice of structural
> grounding — were reached *because* of what the sources turned out to say, and recording
> them as if they had been foreseen would misrepresent how they were arrived at.

---

## 1. Executive objective

Prove that a real, authorised SWIFT MyStandards Message Reference Guide can be read into
this repository's existing rule engine as **evidence** — producing candidate deterministic
rules with exact provenance — without any of it becoming active validation, and without the
document itself entering Git.

## 2. Current main baseline

`4739049836e089121ddb7664e2429b59b8d671bd` — Phase 5A, "MT semantic rule ingestion
foundation" (#14). Verified green before any change: see the report's baseline section.

## 3. Phase 5A architecture, and what Phase 5B reuses

Phase 5A left five seams and Phase 5B uses all of them rather than duplicating any:

| Seam | Phase 5A | Phase 5B use |
|---|---|---|
| `sources.ingest` | declared source → checksum → segments | reads the guides, unchanged |
| `StructureIndex` | read-only door onto structure | subclassed for the guide's own structure |
| `compile_pack` | the one compiler for every pack | compiles candidates, unchanged |
| `RulePack` / `Rule` | the pack contract | candidate packs, unchanged |
| `RulePackRegistry` | loads only fully reviewed packs | still loads nothing |

## 4. Operator source inventory

`swiftKnowledgeBase/` — an ignored local drop directory. Fourteen guides are present;
**only MT540 and MT541 are processed in this phase**, as the brief requires.

## 5–7. Source identity and hashes

Verified from the documents rather than their filenames. Recorded in
`backend/config/rule_sources/mt-mrg-sources.yaml` and in the report.

## 8. Licensing and redistribution boundary

The guides' own Legal Notices restrict disclosure outside the licensee's organisation.
Therefore, for both sources: `sourceMayBeCommitted: false`, `excerptsMayBeCommitted: false`,
`sourceAllowsExternalModelProcessing: false`, `providerApprovedForSourceClassification:
false`. These are the conservative defaults *and* the accurate ones.

## 9. SR2026 identification

The cover page states `Standards MT November 2026`. SWIFT's published schedule puts
Standards Release 2026 live on **14 November 2026**. At the time of this work the date is
2026-08-20, so SR2026 is **future-test**.

## 10. Current-live versus future-test

Three releases are in play and none may be confused with another:

| Lane | Release | Source |
|---|---|---|
| Installed runtime structure | `PUBLIC_UHB_REVIEW_2026_08_05` | this repository's configured subset |
| Structural evidence, current | `SR2025` | pinned Prowide `SRU2025-10.3.18` |
| Semantic + structural, future | `SR2026` | the two Message Reference Guides |

## 11–12. SR2026 structural grounding, and the Prowide future-test strategy

Prowide publishes SRU2026 **source tags** on GitHub but **no SRU2026 artifact on Maven
Central**, and this repository's importer is built on pinned, checksummed Maven artifacts.
Guessing a version, or building from a source tag, would be exactly the "do not guess a
Prowide version" failure the brief forbids.

Therefore SR2026 structural grounding comes from the guides' **own Format Specification and
qualifier tables** — a first-party SWIFT statement, and a stronger source than Prowide for
this purpose. Grounding is recorded as `MRG_DOCUMENTARY_ONLY`: complete for these two
messages, with no independent second description of SR2026 to cross-check against.

## 13. MRG structural cross-check

`docs/generated/mt540-mt541-sr2026-structure-reconciliation.md` compares three descriptions
and classifies every difference. It changes none of them.

## 14–16. Ingestion, text-layer validation, page-preserving segmentation

Through `sources.ingest`, with one general improvement: segmentation now ends a block at a
page break and at the segment ceiling. Without it an extracted PDF with no blank lines
becomes a single segment, and every rule in the book would share one evidence identity.

## 17–18. Section and normative-authority classification

Deterministic, from the guide's own headings, at **line** granularity — two sections share a
page, and attributing a usage paragraph to the Field Specifications would file evidence
under the wrong authority. Rules are only ever taken from `NETWORK_VALIDATED_RULE`.

## 19–25. What is extracted, and what is not

Network Validated Rules are the primary target: every `Cn`, with its page, its SWIFT error
codes and a digest of its text. Format Specifications and qualifier tables are read as
structure. `EXAMPLE`, `MESSAGE_SCOPE` and `LEGAL_NOTICE` are recorded as present and never
read for rules.

## 26–29. Canonical references, SRU binding, DSL coverage

A reference resolves against the structure *the same guide states*. Where the rule names a
sequence, that sequence must declare the tag; where it does not, the qualifier tables decide
and only when they decide uniquely. Ambiguity is reported, never resolved by likelihood.

## 30–34. Extraction, comparison, refutation

**The external-model path is blocked by source policy**, so there is no extraction A, no
extraction B and no model refuter. Translation is deterministic: a closed set of the
sentence forms the guide actually uses, and a refusal for anything else.

Refutation is deterministic too, and comes from the document: every qualifier table carries
a `CR` column naming the rules that govern that qualifier. Comparing that column against
what a translation binds is a criticism the source itself supplies — with no way for two
readings to agree by having made the same mistake.

## 35–38. Candidate packs, lifecycle, review, activation boundary

Candidate packs are built in memory and **not written to `backend/config/rules/`**. The
committed artefact is derived metadata plus reviewer packages. Expected runtime activations:
**0**.

## 39–44. Reconciliation, tests, evaluation, anchors

Two semantic reconciliation reports, one structure reconciliation report, two reviewer
packages, one readiness report — all rendered from committed evidence so CI can check them
without the documents.

## 45–49. Privacy, cache, telemetry, invalidation

No model is called, so there is no cache entry, no token count and no telemetry to leak.
Invalidation is by digest: the document's SHA-256, the structure checksum and the reader
version are combined into a fingerprint recorded beside every candidate.

## 50–57. Diff, upgrade path, and the rest of the platform

Message Intelligence, the API, Excel and the browser are untouched. No endpoint exposes a
candidate; no screen mentions SR2026.

## 58–60. Handover and next steps

The reviewer packages name the page, the rule number and the error code for each of the 38
rules. The next family — MT542–MT548 — needs no new message-specific code.

---

# Plan self-review

The questions the brief requires, answered against what was built. Where the answer changed
the design, the change is named.

**Are we accidentally applying SR2026 rules to SR2025?**
No. Candidates bind to fields the SR2026 guide declares. A test compiles a candidate pack
against the installed runtime index and asserts it *fails*.

**Are we treating November 2026 as current-live before 14 November?**
No. The release lane is a recorded constant, not a computation against the clock, so a
report rendered on any date says the same thing.

**Are we treating Prowide as semantic authority?**
No. Prowide appears in exactly one place — the structure reconciliation report — as the
SR2025 column.

**Are we treating the MRG examples as normative rules?**
No. Rules come only from the section the guide's own heading establishes. The synthetic
fixture carries an `EXAMPLES` block containing fields no rule requires, and a test asserts
none of them became a requirement.

**Are headings or explanatory text being mistaken for requirements?**
No. A rule starts at a `Cn` label and stops at the next one.

**Are Network Validated Rules distinguished from Usage Rules?**
Yes — different sections, and only the first produces candidates.

**Are field format statements distinguished from cross-field semantic rules?**
Yes. Format Specifications build structure; Network Validated Rules build candidates.

**Can a rule reference the wrong sequence occurrence?**
It cannot reference an occurrence at all — and *that* is the finding. Five of the 38 rules
constrain fields within one occurrence of a repeating subsequence. **This was the plan's
biggest correction:** the first design intended to represent them by presence, which is
*stronger* than the source and would reject messages SWIFT accepts. They are now recorded
`UNSUPPORTED` with the reason, and no DSL extension was attempted — occurrence-aware values
would change the live runtime's value model for the benefit of inactive future candidates.

**Can MT540 rules accidentally apply to MT541, or the reverse?**
No. Each guide is read in isolation and produces its own structure and its own pack. A test
asserts that `C2` means different things in the two books — a settlement-amount rule with
error `E92` in MT541, a linked-count rule with error `E90` in MT540 — which is exactly the
mistake a reader that matched rules by number would make.

**Is free-versus-against-payment being inferred rather than sourced?**
Sourced. MT541 makes subsequence `E3 Amounts` mandatory and MT540 makes it optional; MT541
states a settlement-amount rule (`C2`, `E92`) and MT540 states none. **A second correction
came from here:** MT540 does *not* forbid a settlement amount — its own `C1` lists
`:19A::SETT` among the amounts it constrains, and it additionally lists `:19A::BOOK`, which
MT541 does not. "Receive free" means the amount is not required, not that it is not allowed.

**Are qualifier lists being interpreted globally rather than in context?**
In context. A qualifier is resolved through the qualifier table of the field *in that
sequence*.

**Are error codes preserved? Are rule identifiers stable? Are source pages preserved?**
Yes to all three. `SWIFT-SR2026-MT541-C6` carries `sourceErrorCodes: [E91]` and page 14.
The SWIFT error code never replaces the rule identifier.

**Are raw source excerpts entering Git?**
No. `excerpt` is `None` on every candidate, and a test walks the whole evidence fixture and
fails if any recorded string is long enough to be a sentence of the guide.

**Can source text prompt-inject the extraction model? Can the model use remembered SWIFT
knowledge?**
There is no model. The synthetic fixture's Usage Rules contain an instruction to mark every
rule reviewed; a test asserts it produces no rule and changes no review status.

**Can two LLM passes agreeing auto-approve a rule? Can Codex mark a rule human-reviewed?**
No, and no. Every candidate is `REVIEW_REQUIRED`, and nothing in this phase writes to the
rules directory.

**Can a candidate enter normal runtime? Can it alter MT structure?**
No. The registry loads only fully reviewed packs from `backend/config/rules/`, and no
candidate is written there. The structure index is read-only and has no writer.

**Can a rule compiled for SR2026 run against SR2025?**
No — it does not resolve. Fail-closed is the default state rather than an added check.

**Does normal runtime remain zero-LLM?**
Yes. Nothing in `app/rule_engine/mt_mrg/` is imported by the request path.

**Are we unnecessarily creating a second Rule Engine?**
No. One compiler, one DSL, one evaluator, one pack model. What is new is a *reader* and a
second structure source behind the index seam the engine already had.
