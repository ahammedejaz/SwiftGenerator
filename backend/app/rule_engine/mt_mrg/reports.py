"""The documents a reviewer actually reads, rendered from committed evidence alone.

Every report below is built from the derived-metadata fixture, the pinned Prowide
structural evidence and the installed configuration — all of them committed. None of them
needs the licensed guides, which is what lets continuous integration check that the reports
are current on a machine that has never held one.

The reports are deliberately three different jobs:

*Structure reconciliation* compares the shape three sources describe and classifies every
difference, without changing any of them.

*Semantic reconciliation* asks, rule by rule, what this repository already does about what
the guide says — and, just as importantly, what this repository does that the guide does
not say.

*The reviewer package* is the handover. It gives a person the page, the rule number, the
error code and the expression, and asks them to agree or not.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from app.rule_engine.mt_mrg import MRG_READER_VERSION
from app.rule_engine.mt_mrg.fixture import FixtureSource, load, source_for, sources
from app.rule_engine.mt_mrg.rules import RuleFidelity
from app.spec_engine.mt_prowide.extractor import load_extraction
from app.spec_engine.mt_prowide.models import MtProwideExtraction
from app.specifications.registry import MessageSpecificationRegistry, specification_registry

GENERATED = Path(__file__).resolve().parents[4] / "docs" / "generated"

STRUCTURE_REPORT = GENERATED / "mt540-mt541-sr2026-structure-reconciliation.md"
SEMANTIC_REPORTS = {
    "MT540": GENERATED / "mt540-sr2026-semantic-reconciliation.md",
    "MT541": GENERATED / "mt541-sr2026-semantic-reconciliation.md",
}
REVIEW_REPORTS = {
    "MT540": GENERATED / "mt540-sr2026-rule-review.md",
    "MT541": GENERATED / "mt541-sr2026-rule-review.md",
}
READINESS_REPORT = GENERATED / "mt-sr2026-semantic-readiness.md"

#: The date SWIFT's published schedule gives for Standards MT Release 2026 going live.
#: Recorded rather than computed: a release lane must never depend on the clock of the
#: machine rendering a report.
SR2026_GO_LIVE = "14 November 2026"


class StructureVerdict(StrEnum):
    MATCH = "MATCH"
    RELEASE_CHANGE = "RELEASE_CHANGE"
    SOURCE_MODEL_DIFFERENCE = "SOURCE_MODEL_DIFFERENCE"
    REPOSITORY_SUBSET = "REPOSITORY_SUBSET"
    COMPARISON_LIMITATION = "COMPARISON_LIMITATION"
    UNKNOWN = "UNKNOWN"


class SemanticVerdict(StrEnum):
    SOURCE_RULE_MATCHES_EXISTING = "SOURCE_RULE_MATCHES_EXISTING"
    SOURCE_RULE_NOT_CONFIGURED = "SOURCE_RULE_NOT_CONFIGURED"
    EXISTING_RULE_NOT_FOUND_IN_SOURCE = "EXISTING_RULE_NOT_FOUND_IN_SOURCE"
    RELEASE_DIFFERENCE = "RELEASE_DIFFERENCE"
    STRUCTURE_DIFFERENCE = "STRUCTURE_DIFFERENCE"
    DSL_UNSUPPORTED = "DSL_UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RuntimeBusinessRule:
    """One rule this repository enforces for MT in Python rather than in configuration.

    Named here so semantic reconciliation can compare against it. A test asserts each
    identifier still exists in the generator, so the table cannot quietly go stale.
    """

    rule_id: str
    summary: str
    #: Source rule numbers this appears to correspond to, per message. Empty means the
    #: repository enforces something the guides do not state as a Network Validated Rule.
    source_rules: dict[str, str]


RUNTIME_MT_BUSINESS_RULES: tuple[RuntimeBusinessRule, ...] = (
    RuntimeBusinessRule(
        rule_id="CANCELLATION_REQUIRES_PREVIOUS_REFERENCE",
        summary="A cancellation must state which earlier message it cancels.",
        source_rules={"MT540": "C7", "MT541": "C8"},
    ),
    RuntimeBusinessRule(
        rule_id="SETTLEMENT_DATE_BEFORE_TRADE_DATE",
        summary="The settlement date must not precede the trade date.",
        source_rules={},
    ),
)


# --------------------------------------------------------------------------------------
# Structure reconciliation
# --------------------------------------------------------------------------------------


def _document(lines: list[str]) -> str:
    """One rendered document, ending in exactly one newline.

    `git diff --check` fails a *new* blank line at end of file, and it only sees one when a
    base ref is supplied — which CI does and a local `git diff --check` does not. Normalising
    here rather than in each renderer means a new report cannot reintroduce it.
    """
    return "\n".join(lines).rstrip("\n") + "\n"


def _prowide_message(extraction: MtProwideExtraction, message_type: str) -> Any:
    return next(
        (item for item in extraction.messages if item.message_type == message_type), None
    )


def _sequence_rows(
    guide: FixtureSource,
    extraction: MtProwideExtraction,
    registry: MessageSpecificationRegistry,
) -> list[tuple[str, ...]]:
    message = _prowide_message(extraction, guide.message_type)
    installed = (
        {item.path: item for item in registry.get(guide.message_type).sequences}
        if registry.known(guide.message_type)
        else {}
    )
    prowide = {item.path: item for item in (message.sequences if message else [])}
    rows: list[tuple[str, ...]] = []
    paths = sorted({*(item["path"] for item in guide["sequences"]), *prowide, *installed})
    for path in paths:
        source = guide.sequence(path)
        other = prowide.get(path)
        here = installed.get(path)
        mrg = (
            f"{source['presence']}{'/R' if source['repetitive'] else ''}"
            if source
            else "ABSENT"
        )
        sru2025 = (
            f"{other.presence.value}{'/R' if other.repeatable else ''}" if other else "ABSENT"
        )
        runtime = (
            f"{'MANDATORY' if here.min_occurs >= 1 else 'OPTIONAL'}"
            f"{'/R' if here.max_occurs > 1 else ''}"
            if here
            else "ABSENT"
        )
        rows.append(
            (
                path,
                (source or {}).get("name") or (other.name if other else "") or "",
                mrg,
                sru2025,
                runtime,
                _sequence_verdict(mrg, sru2025, runtime).value,
            )
        )
    return rows


def _sequence_verdict(mrg: str, sru2025: str, runtime: str) -> StructureVerdict:
    # A genuine difference between the two releases is reported first. Testing the
    # repository subset before it would hide every release change behind the fact that
    # this repository models fewer sequences than either release describes.
    if mrg == "ABSENT" or sru2025 == "ABSENT":
        return StructureVerdict.SOURCE_MODEL_DIFFERENCE
    if mrg != sru2025:
        return StructureVerdict.RELEASE_CHANGE
    if runtime == "ABSENT" or runtime != mrg:
        return StructureVerdict.REPOSITORY_SUBSET
    return StructureVerdict.MATCH


def _sequence_name_rows(
    guide: FixtureSource, extraction: MtProwideExtraction
) -> list[tuple[str, ...]]:
    message = _prowide_message(extraction, guide.message_type)
    prowide = {item.path: item for item in (message.sequences if message else [])}
    rows: list[tuple[str, ...]] = []
    for item in guide["sequences"]:
        other = prowide.get(item["path"])
        if other is None or other.name == item["name"]:
            continue
        # Prowide leaves some sequence names empty. An absent name is not a rename, and
        # calling it one would invent a release change out of a gap in the other source.
        verdict = (
            StructureVerdict.COMPARISON_LIMITATION
            if not other.name.strip()
            else StructureVerdict.RELEASE_CHANGE
        )
        rows.append(
            (item["path"], item["name"], other.name or "NOT_STATED", verdict.value)
        )
    return rows


def render_structure_reconciliation(
    payload: dict[str, Any] | None = None,
    extraction: MtProwideExtraction | None = None,
    registry: MessageSpecificationRegistry | None = None,
) -> str:
    payload = payload or load()
    extraction = extraction or load_extraction()
    registry = registry or specification_registry
    guides = sources(payload)
    lines = [
        "# MT540 / MT541 SR2026 structure reconciliation",
        "",
        "Generated by `make mt-mrg-check`. Three descriptions of the same two messages,",
        "compared without any of them being changed.",
        "",
        "| Column | What it is | Authority |",
        "| --- | --- | --- |",
        "| `SR2026 MRG` | the SWIFT Message Reference Guide's own Format Specifications | "
        "documentary structural evidence for SR2026 |",
        "| `SR2025 Prowide` | the pinned Prowide Core source model | "
        "structural evidence only, never semantic |",
        "| `Runtime` | this repository's installed MT specification | "
        "a configured subset, deliberately smaller |",
        "",
        "A difference is classified, never resolved. Nothing here modifies the installed",
        "structure, and an SR2026 statement never becomes an SR2025 or runtime fact.",
        "",
        "## Release lanes",
        "",
        "| Lane | Release | Structural source | Status |",
        "| --- | --- | --- | --- |",
        f"| `CURRENT_LIVE` | `{extraction.source.swift_standards_release}` | "
        f"`{extraction.source.prowidesoftware_version}` | in force |",
        f"| `FUTURE_TEST` | `SR2026` | `SWIFT MRG Format Specifications` | "
        f"live from {SR2026_GO_LIVE} |",
        "",
    ]
    for guide in guides:
        lines += [
            f"## {guide.message_type} sequences",
            "",
            "| Sequence | Name | SR2026 MRG | SR2025 Prowide | Runtime | Verdict |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for row in _sequence_rows(guide, extraction, registry):
            lines.append("| " + " | ".join(f"`{item}`" for item in row) + " |")
        renamed = _sequence_name_rows(guide, extraction)
        lines += [
            "",
            f"Format Specification rows: `{len(guide['formatRows'])}`. "
            f"Qualifier-table rows: `{len(guide['qualifierRows'])}`. "
            f"Field Specifications: `{len(guide['fieldSpecifications'])}`.",
            "",
        ]
        if renamed:
            lines += [
                f"### {guide.message_type} sequences the two releases name differently",
                "",
                "| Sequence | SR2026 MRG | SR2025 Prowide | Verdict |",
                "| --- | --- | --- | --- |",
            ]
            for row in renamed:
                lines.append("| " + " | ".join(f"`{item}`" for item in row) + " |")
            lines.append("")
    lines += _structure_notes(guides, registry)
    return _document(lines)


def _structure_notes(
    guides: list[FixtureSource], registry: MessageSpecificationRegistry
) -> list[str]:
    installed_release = (
        registry.get("MT541").standards_release if registry.known("MT541") else "UNKNOWN"
    )
    notes = [
        "## What this comparison does and does not establish",
        "",
        "- The Message Reference Guide is the only SR2026 structural source here. No "
        "SR2026 Prowide artifact is published to Maven Central, so there is no independent "
        "second description of SR2026 to cross-check against.",
        f"- The installed runtime structure is `{installed_release}`, which is neither of "
        "the two releases compared above. A candidate rule compiled for SR2026 does not "
        "resolve against it, and that is the intended behaviour rather than a gap.",
        "- `REPOSITORY_SUBSET` is the expected verdict for most rows. This repository "
        "models a configured subset of each message and has never claimed otherwise.",
        "- A `RELEASE_CHANGE` verdict says the two releases describe the sequence "
        "differently. It does not say which is correct for a given date; the release lane "
        "does.",
        "",
    ]
    for guide in guides:
        amounts = guide.sequence("E3")
        if amounts:
            notes.append(
                f"- {guide.message_type} subsequence `E3 Amounts` is "
                f"`{amounts['presence']}` in SR2026. That difference between the two "
                "messages is the free-versus-against-payment distinction, stated "
                "structurally rather than inferred from the message name."
            )
    notes.append("")
    return notes


# --------------------------------------------------------------------------------------
# Semantic reconciliation
# --------------------------------------------------------------------------------------


def _installed_targets(
    registry: MessageSpecificationRegistry, message_type: str
) -> dict[tuple[str, str | None], str]:
    if not registry.known(message_type):
        return {}
    return {
        (row.tag[:2], row.qualifier): row.row_id
        for row in registry.get(message_type).fields
    }


def _semantic_rows(
    guide: FixtureSource, registry: MessageSpecificationRegistry
) -> list[tuple[str, ...]]:
    installed = _installed_targets(registry, guide.message_type)
    matched = {
        item.source_rules.get(guide.message_type)
        for item in RUNTIME_MT_BUSINESS_RULES
        if item.source_rules.get(guide.message_type)
    }
    rows: list[tuple[str, ...]] = []
    for rule in guide.rules():
        references = rule["references"]
        present = [
            installed.get((item["tag"][:2], item["qualifier"]))
            for item in references
            if item["qualifier"]
        ]
        found = [item for item in present if item]
        if rule["sourceRuleId"] in matched:
            verdict = SemanticVerdict.SOURCE_RULE_MATCHES_EXISTING
        elif rule["fidelity"] == RuleFidelity.UNSUPPORTED.value:
            verdict = SemanticVerdict.DSL_UNSUPPORTED
        elif references and not found:
            verdict = SemanticVerdict.STRUCTURE_DIFFERENCE
        else:
            verdict = SemanticVerdict.SOURCE_RULE_NOT_CONFIGURED
        rows.append(
            (
                rule["sourceRuleId"],
                ", ".join(rule["errorCodes"]) or "-",
                str(rule["firstPage"]),
                rule["fidelity"],
                _targets(references),
                f"{len(found)}/{len([item for item in references if item['qualifier']])}",
                verdict.value,
            )
        )
    return rows


def _targets(references: list[dict[str, Any]]) -> str:
    seen: list[str] = []
    for item in references:
        label = f"{item['sequencePath']}:{item['tag']}"
        if item["qualifier"]:
            label += f"::{item['qualifier']}"
        if label not in seen:
            seen.append(label)
    joined = " ".join(seen[:6])
    return joined + (" …" if len(seen) > 6 else "")


def render_semantic_reconciliation(
    message_type: str,
    payload: dict[str, Any] | None = None,
    registry: MessageSpecificationRegistry | None = None,
) -> str:
    payload = payload or load()
    registry = registry or specification_registry
    guide = source_for(payload, message_type)
    if guide is None:
        raise KeyError(f"No {message_type} evidence in the fixture")
    rows = _semantic_rows(guide, registry)
    installed_release = (
        registry.get(message_type).standards_release
        if registry.known(message_type)
        else "UNKNOWN"
    )
    lines = [
        f"# {message_type} SR2026 semantic reconciliation",
        "",
        "Generated by `make mt-mrg-check`. What the SR2026 Message Reference Guide states",
        "as a Network Validated Rule, set beside what this repository currently does.",
        "",
        f"Source: `{guide['sourceId']}` · `{guide['sourceChecksum'][:23]}…` · "
        f"`{guide['pageCount']}` pages · release `{guide.standards_release}`",
        "",
        f"Installed runtime structure: `{installed_release}` — a different release from the",
        "source above, and a configured subset of it. Nothing in this report changes it.",
        "",
        "## Every Network Validated Rule the guide states",
        "",
        "| Source rule | SWIFT error | Page | Representation | Canonical targets | "
        "Targets installed | Verdict |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(f"`{item}`" for item in row) + " |")

    lines += [
        "",
        "## What this repository enforces for this message today",
        "",
        "| Runtime rule | Layer | Corresponding source rule | Verdict |",
        "| --- | --- | --- | --- |",
    ]
    for runtime in RUNTIME_MT_BUSINESS_RULES:
        corresponding = runtime.source_rules.get(message_type)
        verdict = (
            SemanticVerdict.SOURCE_RULE_MATCHES_EXISTING
            if corresponding
            else SemanticVerdict.EXISTING_RULE_NOT_FOUND_IN_SOURCE
        )
        lines.append(
            f"| `{runtime.rule_id}` | `BUSINESS_RULES` | "
            f"`{corresponding or 'NONE'}` | `{verdict.value}` |"
        )
    lines += _semantic_notes(guide, registry, message_type)
    return _document(lines)


def _semantic_notes(
    guide: FixtureSource, registry: MessageSpecificationRegistry, message_type: str
) -> list[str]:
    installed = _installed_targets(registry, message_type)
    counts = {
        item: len(guide.by_fidelity(item))
        for item in (
            RuleFidelity.EXACT,
            RuleFidelity.PARTIAL,
            RuleFidelity.UNSUPPORTED,
            RuleFidelity.NOT_RECOGNISED,
        )
    }
    notes = [
        "",
        "## Counts",
        "",
        "| Measure | Value |",
        "| --- | --- |",
        f"| Network Validated Rules discovered | `{len(guide.rules())}` |",
        f"| Fully representable in the rule DSL | `{counts[RuleFidelity.EXACT]}` |",
        f"| Representable more weakly than stated | `{counts[RuleFidelity.PARTIAL]}` |",
        f"| Not representable | `{counts[RuleFidelity.UNSUPPORTED]}` |",
        f"| Sentence form not recognised | `{counts[RuleFidelity.NOT_RECOGNISED]}` |",
        f"| Candidate rules compiled | "
        f"`{guide['candidatePack']['ruleCount'] if guide['candidatePack'] else 0}` |",
        "| Reviewed rules | `0` |",
        "| Runtime activations | `0` |",
        "",
        "## Reading the verdicts",
        "",
        "- `SOURCE_RULE_MATCHES_EXISTING` — this repository already enforces something "
        "that corresponds to the source rule. It does not mean the two are equivalent in "
        "every case; the reviewer decides that.",
        "- `SOURCE_RULE_NOT_CONFIGURED` — the guide states a rule this repository does not "
        "enforce. Expected: no reviewed MT rule pack is installed for any message.",
        "- `STRUCTURE_DIFFERENCE` — the rule's targets are not in the installed subset at "
        "all, usually because the subset has no `E1`/`E3` subsequences.",
        "- `DSL_UNSUPPORTED` — the rule cannot be expressed soundly. It is recorded, never "
        "approximated.",
        "- `EXISTING_RULE_NOT_FOUND_IN_SOURCE` — this repository enforces something the "
        "guide does not state as a Network Validated Rule for this message. That is not "
        "necessarily wrong; it is a claim that needs its own evidence.",
        "",
    ]
    settlement_amount = installed.get(("19", "SETT"))
    if settlement_amount:
        notes.append(
            f"- The installed structure declares `{settlement_amount}` in sequence `E`, "
            "whereas the guide places the settlement amount in subsequence `E3 Amounts`. "
            "The requirement is expressed structurally here and as a Network Validated "
            "Rule there; a reviewer should decide whether the runtime subset should gain "
            "the subsequence."
        )
    else:
        notes.append(
            "- The installed structure declares no settlement amount for this message, "
            "which is consistent with the guide: a receive *free* of payment has no "
            "settlement-amount rule at all."
        )
    notes.append("")
    return notes


# --------------------------------------------------------------------------------------
# Reviewer packages
# --------------------------------------------------------------------------------------


def render_review_package(
    message_type: str, payload: dict[str, Any] | None = None
) -> str:
    payload = payload or load()
    guide = source_for(payload, message_type)
    if guide is None:
        raise KeyError(f"No {message_type} evidence in the fixture")
    objections: dict[str, list[str]] = {}
    for item in guide["objections"]:
        objections.setdefault(item["sourceRuleId"], []).append(
            f"{item['code']}: {item['detail']}"
        )
    lines = [
        f"# {message_type} SR2026 candidate rule review",
        "",
        "Generated by `make mt-mrg-check`. One entry per Network Validated Rule the guide",
        "states. Every entry is `REVIEW_REQUIRED`; nothing here is installed, and nothing",
        "here has been reviewed by a person.",
        "",
        "**How to review one entry.** Open the named page of the guide, read the rule under",
        "its own number, and decide whether the expression below says the same thing — no",
        "more, and preferably no less. The residual notes say what was deliberately left",
        "out. Approving an entry means editing it into a rule pack and putting it through",
        "the ordinary review path; there is no approval switch here.",
        "",
        f"Source: `{guide['sourceId']}`",
        f"Document digest: `{guide['sourceChecksum']}`",
        f"Structure digest: `{guide['structureChecksum']}`",
        f"Reader: `{MRG_READER_VERSION}` · fingerprint `{guide['fingerprint'][:23]}…`",
        "",
        "No source text is reproduced below. A reviewer needs the guide open; a reader who",
        "does not have it learns nothing from this file that they were not licensed to.",
        "",
    ]
    for rule in guide.rules():
        lines += _review_entry(guide, rule, objections.get(rule["sourceRuleId"], []))
    return _document(lines)


def _review_entry(
    guide: FixtureSource, rule: dict[str, Any], objections: list[str]
) -> list[str]:
    representable = rule["fidelity"] in {
        RuleFidelity.EXACT.value,
        RuleFidelity.PARTIAL.value,
    }
    codes = ", ".join(rule["errorCodes"]) or "no error code stated"
    lines = [
        f"## {rule['sourceRuleId']} — {codes}",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Candidate rule id | `{rule['candidateRuleId'] if representable else 'NOT_COMPILED'}` |",
        f"| Source rule id | `{rule['sourceRuleId']}` |",
        f"| SWIFT error code | `{', '.join(rule['errorCodes']) or 'NONE_STATED'}` |",
        f"| Message | `{guide.message_type}` |",
        f"| Release | `{guide.standards_release}` |",
        f"| Source page | `{rule['firstPage']}`"
        + (f"–`{rule['lastPage']}`" if rule["lastPage"] != rule["firstPage"] else "")
        + " |",
        "| Source section | `Network Validated Rules` |",
        f"| Rule text digest | `{rule['textHash'][:23]}…` |",
        f"| Representation | `{rule['fidelity']}` |",
        f"| Sentence form | `{rule['template'] or 'NOT_RECOGNISED'}` |",
        f"| Compiled | `{'YES' if rule['compiled'] else 'NO'}` |",
        f"| Reference resolution | `{_reference_status(rule)}` |",
        "| Review status | `REVIEW_REQUIRED` |",
        "",
    ]
    if rule["interpretation"]:
        lines += [
            "**What the candidate says** (this repository's words, derived from the "
            "expression):",
            "",
            f"> {rule['interpretation']}",
            "",
        ]
    if rule["reason"]:
        lines += [f"**Why it is not represented:** `{rule['reason']}`", ""]
    if rule["residual"]:
        lines += ["**What the expression leaves out:**", ""]
        lines += [f"- {item}" for item in rule["residual"]]
        lines.append("")
    lines += ["**Canonical references:**", ""]
    for item in rule["references"]:
        qualifier = f"::{item['qualifier']}" if item["qualifier"] else ""
        value = f"//{item['value']}" if item["value"] else ""
        state = "resolved" if item["resolved"] else f"UNRESOLVED — {item['detail']}"
        lines.append(
            f"- `MT:{guide.standards_release}:{guide.message_type}:"
            f"{item['sequencePath']}:{item['tag']}{qualifier}{value}` — {state}"
        )
    if not rule["references"]:
        lines.append("- none")
    lines.append("")
    lines += ["**Deterministic cross-check against the guide's own rule references:**", ""]
    if objections:
        lines += [f"- {item}" for item in objections]
    else:
        lines.append("- no disagreement between this reading and the guide's own "
                     "conditional-rule columns")
    lines.append("")
    return lines


def _reference_status(rule: dict[str, Any]) -> str:
    references = rule["references"]
    if not references:
        return "NO_REFERENCES"
    unresolved = [item for item in references if not item["resolved"]]
    return "ALL_RESOLVED" if not unresolved else f"{len(unresolved)}_UNRESOLVED"


# --------------------------------------------------------------------------------------
# Readiness
# --------------------------------------------------------------------------------------


def render_readiness(
    payload: dict[str, Any] | None = None,
    registry: MessageSpecificationRegistry | None = None,
) -> str:
    payload = payload or load()
    registry = registry or specification_registry
    guides = sources(payload)
    installed_release = (
        registry.get("MT541").standards_release if registry.known("MT541") else "UNKNOWN"
    )
    lines = [
        "# MT SR2026 semantic readiness",
        "",
        "Generated by `make mt-mrg-check`. Two release lanes, reported separately, because",
        "a future release becoming readable is not the same as it becoming effective.",
        "",
        "## Status",
        "",
        "| Status | Value |",
        "| --- | --- |",
        "| `REAL_MT_SEMANTIC_SOURCE_AVAILABLE` | "
        f"`{'YES' if guides else 'NO'}` |",
        "| `SOURCE_RELEASE` | `SR2026` |",
        "| `RELEASE_LANE` | `FUTURE_TEST` |",
        f"| `SR2026_GO_LIVE` | `{SR2026_GO_LIVE}` |",
        f"| `CURRENT_LIVE_RUNTIME_STRUCTURE` | `{installed_release}` |",
        "| `SR2026_STRUCTURAL_GROUNDING` | `MRG_DOCUMENTARY_ONLY` |",
        "| `REAL_SOURCE_LIVE_LLM_EXTRACTION` | `BLOCKED_BY_SOURCE_POLICY` |",
        "| `REAL_RULE_HUMAN_REVIEW` | `REQUIRED` |",
        "| `REAL_RULE_RUNTIME_ACTIVATION` | `0` |",
        "| `RUNTIME_LLM_CALLS` | `0` |",
        "",
        "## Per message, per lane",
        "",
        "| Message | Lane | Release | Structure source | Semantic source | "
        "Rules discovered | Candidates compiled | Reviewed | Runtime active |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for guide in guides:
        pack = guide["candidatePack"] or {}
        lines.append(
            "| "
            + " | ".join(
                f"`{item}`"
                for item in (
                    guide.message_type,
                    "CURRENT_LIVE",
                    installed_release,
                    "repository configuration",
                    "NONE",
                    "0",
                    "0",
                    "0",
                    "YES",
                )
            )
            + " |"
        )
        lines.append(
            "| "
            + " | ".join(
                f"`{item}`"
                for item in (
                    guide.message_type,
                    "FUTURE_TEST",
                    guide.standards_release,
                    "SWIFT MRG Format Specifications",
                    guide["sourceId"],
                    str(len(guide.rules())),
                    str(pack.get("ruleCount", 0)),
                    "0",
                    "NO",
                )
            )
            + " |"
        )
    lines += [
        "",
        "## Rule representation, per message",
        "",
        "| Message | Discovered | Exact | Weaker than stated | Not representable | "
        "Form not recognised |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for guide in guides:
        lines.append(
            "| "
            + " | ".join(
                f"`{item}`"
                for item in (
                    guide.message_type,
                    str(len(guide.rules())),
                    str(len(guide.by_fidelity(RuleFidelity.EXACT))),
                    str(len(guide.by_fidelity(RuleFidelity.PARTIAL))),
                    str(len(guide.by_fidelity(RuleFidelity.UNSUPPORTED))),
                    str(len(guide.by_fidelity(RuleFidelity.NOT_RECOGNISED))),
                )
            )
            + " |"
        )
    lines += [
        "",
        "## What this does not say",
        "",
        "- Not that MT540 or MT541 is SWIFT certified. No certification exists here.",
        "- Not that SR2026 validation is implemented. No SR2026 rule is active.",
        "- Not that every SR2026 rule is supported. The counts above say exactly which are.",
        f"- Not that SR2026 is current. It becomes live on {SR2026_GO_LIVE}; until then the "
        "installed structure and rules are the effective ones.",
        "- Not that client market practice or MyStandards usage guidelines are covered. "
        "Neither has been supplied.",
        "- Not that any candidate has been reviewed. Every one is `REVIEW_REQUIRED`.",
        "",
    ]
    return _document(lines)


# --------------------------------------------------------------------------------------
# Writing and checking
# --------------------------------------------------------------------------------------


def rendered() -> dict[Path, str]:
    payload = load()
    documents = {
        STRUCTURE_REPORT: render_structure_reconciliation(payload),
        READINESS_REPORT: render_readiness(payload),
    }
    for message_type, path in SEMANTIC_REPORTS.items():
        documents[path] = render_semantic_reconciliation(message_type, payload)
    for message_type, path in REVIEW_REPORTS.items():
        documents[path] = render_review_package(message_type, payload)
    return documents


def write_reports() -> list[Path]:
    written: list[Path] = []
    for path, body in rendered().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        written.append(path)
    return written


def stale_reports() -> list[Path]:
    stale: list[Path] = []
    for path, body in rendered().items():
        if not path.is_file() or path.read_text(encoding="utf-8") != body:
            stale.append(path)
    return stale
