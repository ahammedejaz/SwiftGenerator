"""Every Message Reference Guide in the knowledge base, read as semantic evidence at once.

Phase 5B read two guides through a hand-written source catalogue. The knowledge base now
holds every SR2026 guide the operator is licensed for, identified from its own cover, so
the corpus reader walks that folder, reads each guide with the same reader, and records a
*compact* evidence index: identity, checksums, and one disposition per Network Validated
Rule — ``EXACT``, ``PARTIAL_WEAKER_THAN_SOURCE`` or ``UNSUPPORTED`` with its reason. The
index carries no sentence of any guide: a rule is its number, its error codes, its page
and the hash of its text.

Offline only. Nothing here runs in the request path, and nothing here writes a Rule Pack:
every translation stays ``REVIEW_REQUIRED`` and runtime activations remain zero.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.rule_engine.mt_mrg import MRG_READER_VERSION
from app.rule_engine.mt_mrg.document import classify, identify, missing_sections, pages_of
from app.rule_engine.mt_mrg.formatspec import StructureBuilder
from app.rule_engine.mt_mrg.pipeline import STRUCTURE_ENFORCED, refute
from app.rule_engine.mt_mrg.rules import RuleFidelity, RuleTranslation, discover
from app.rule_engine.mt_mrg.templates import translate
from app.rule_engine.sources import normalise

CORPUS_SCHEMA = "mt-mrg-corpus-evidence/1"
PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_GUIDE_DIRECTORY = PROJECT_ROOT / "swiftKnowledgeBase" / "MT"
DEFAULT_TEXT_CACHE = PROJECT_ROOT / "build" / "knowledge" / "source-cache" / "mrg-text"
INDEX_PATH = (
    PROJECT_ROOT / "backend" / "tests" / "fixtures" / "mt_mrg" / "sr2026-corpus-evidence.json"
)
COVERAGE_PATH = PROJECT_ROOT / "docs" / "generated" / "mt-semantic-rule-coverage.md"
REVIEW_DIRECTORY = PROJECT_ROOT / "docs" / "generated" / "mt-rule-review"

#: The three dispositions every discovered rule receives. ``NOT_RECOGNISED`` is a reader
#: outcome, and it is reported as ``UNSUPPORTED`` with the reason
#: ``SENTENCE_FORM_NOT_RECOGNISED`` — never silently dropped.
DISPOSITIONS = ("EXACT", "PARTIAL_WEAKER_THAN_SOURCE", "UNSUPPORTED")


def disposition_of(translation: RuleTranslation) -> str:
    if translation.fidelity is RuleFidelity.EXACT:
        return "EXACT"
    if translation.fidelity is RuleFidelity.PARTIAL:
        return "PARTIAL_WEAKER_THAN_SOURCE"
    return "UNSUPPORTED"


@dataclass(frozen=True)
class GuideEvidence:
    source_id: str
    message_type: str
    message_name: str
    release: str
    page_count: int
    source_checksum: str
    structure_checksum: str
    sequences: int
    rows: int
    field_specifications: int
    problems: tuple[str, ...]
    rules: tuple[dict[str, Any], ...]
    objections: int

    def counts(self) -> dict[str, int]:
        found = {name: 0 for name in DISPOSITIONS}
        for rule in self.rules:
            found[str(rule["disposition"])] += 1
        return found

    def as_payload(self) -> dict[str, Any]:
        return {
            "sourceId": self.source_id,
            "messageType": self.message_type,
            "messageName": self.message_name,
            "release": self.release,
            "pageCount": self.page_count,
            "sourceChecksum": self.source_checksum,
            "structureChecksum": self.structure_checksum,
            "sequences": self.sequences,
            "rows": self.rows,
            "fieldSpecifications": self.field_specifications,
            "problems": list(self.problems),
            "networkValidatedRules": list(self.rules),
            "objections": self.objections,
            "reviewStatus": "REVIEW_REQUIRED",
            "runtimeActivations": 0,
        }


@dataclass
class CorpusEvidence:
    guides: list[GuideEvidence] = field(default_factory=list)
    unreadable: list[dict[str, str]] = field(default_factory=list)

    def as_payload(self) -> dict[str, Any]:
        return {
            "schemaVersion": CORPUS_SCHEMA,
            "readerVersion": MRG_READER_VERSION,
            "guides": [
                item.as_payload() for item in sorted(self.guides, key=lambda g: g.message_type)
            ],
            "unreadable": list(self.unreadable),
            "liveModelCalls": 0,
        }


def read_guide_text(text: str, *, source_checksum: str) -> GuideEvidence:
    """Read one guide from its page-marked text."""
    normalised = normalise(text)
    pages = pages_of(normalised)
    identity, problems = identify(pages)
    if identity is None:
        raise ValueError("not a Message Reference Guide: " + ", ".join(problems))
    spans = classify(pages, identity.message_type)
    structure = StructureBuilder(identity.message_type, identity.standards_release).build(
        pages, spans, message_name=identity.message_name, release_text=identity.release_cover_text
    )
    rules = discover(
        pages,
        spans,
        message_type=identity.message_type,
        message_name=identity.message_name,
        standards_release=identity.standards_release,
        release_text=identity.release_cover_text,
    )
    translations = tuple(translate(item, structure) for item in rules)
    objections = refute(translations, structure)
    records: list[dict[str, Any]] = []
    for translation in translations:
        rule = translation.rule
        objected = sorted(
            {item.code for item in objections if item.source_rule_id == rule.source_rule_id}
        )
        reason = translation.reason.value if translation.reason else None
        if translation.fidelity is RuleFidelity.NOT_RECOGNISED:
            reason = "SENTENCE_FORM_NOT_RECOGNISED"
        records.append(
            {
                "ruleId": rule.source_rule_id,
                "canonicalRuleId": rule.canonical_rule_id,
                "errorCodes": list(rule.error_codes),
                "page": rule.first_page,
                "textHash": rule.text_hash,
                "characters": rule.character_count,
                "disposition": disposition_of(translation),
                "template": translation.template or None,
                "reason": reason,
                "residual": list(translation.residual),
                "enforcedByStructure": STRUCTURE_ENFORCED in translation.residual,
                "references": [
                    item.canonical_id for item in translation.references if item.resolved
                ],
                "objections": objected,
                "reviewStatus": "REVIEW_REQUIRED",
            }
        )
    problems_found = [
        *(f"SECTION_MISSING_{item.value}" for item in missing_sections(spans)),
        *structure.problems,
    ]
    return GuideEvidence(
        source_id=identity.logical_source_id,
        message_type=identity.message_type,
        message_name=identity.message_name,
        release=identity.standards_release,
        page_count=identity.page_count,
        source_checksum=source_checksum,
        structure_checksum=structure.checksum(),
        sequences=len(structure.sequences),
        rows=len(structure.rows),
        field_specifications=len(structure.field_specs),
        problems=tuple(problems_found),
        rules=tuple(records),
        objections=len(objections),
    )


def read_corpus(directory: Path | None = None, *, text_cache: Path | None = None) -> CorpusEvidence:
    """Read every PDF in the guide directory, through the sync's text cache when present."""
    from app.knowledge_base.identify import _pdf_text

    folder = directory or DEFAULT_GUIDE_DIRECTORY
    cache = text_cache or DEFAULT_TEXT_CACHE
    corpus = CorpusEvidence()
    for path in sorted(folder.glob("*.pdf")):
        raw = path.read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()
        cached = cache / f"{checksum}.txt"
        try:
            text = (
                cached.read_text(encoding="utf-8")
                if cached.exists()
                else _pdf_text(raw, path.name)[0]
            )
            corpus.guides.append(read_guide_text(text, source_checksum=checksum))
        except Exception as error:  # noqa: BLE001 - one guide must not stop the corpus
            corpus.unreadable.append(
                {
                    "path": path.name,
                    "checksum": checksum,
                    "detail": f"{type(error).__name__}: {error}"[:200],
                }
            )
    return corpus


# -- the committed index ---------------------------------------------------------------


def write_index(corpus: CorpusEvidence, path: Path | None = None) -> Path:
    target = path or INDEX_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(corpus.as_payload(), indent=1, sort_keys=False, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return target


def load_index(path: Path | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads((path or INDEX_PATH).read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != CORPUS_SCHEMA:
        raise ValueError(
            f"corpus evidence index is {payload.get('schemaVersion')}, not {CORPUS_SCHEMA}"
        )
    return payload


# -- reports -----------------------------------------------------------------------------


def _document(lines: list[str]) -> str:
    return "\n".join(lines).rstrip("\n") + "\n"


def render_coverage(payload: dict[str, Any]) -> str:
    guides = payload["guides"]
    totals = {name: 0 for name in DISPOSITIONS}
    total_rules = 0
    reasons: dict[str, int] = {}
    templates: dict[str, dict[str, int]] = {}
    for guide in guides:
        for rule in guide["networkValidatedRules"]:
            total_rules += 1
            totals[rule["disposition"]] += 1
            if rule["disposition"] == "UNSUPPORTED":
                reasons[rule["reason"] or "UNSPECIFIED"] = (
                    reasons.get(rule["reason"] or "UNSPECIFIED", 0) + 1
                )
            if rule["template"]:
                bucket = templates.setdefault(rule["template"], {name: 0 for name in DISPOSITIONS})
                bucket[rule["disposition"]] += 1
    with_rules = sum(1 for guide in guides if guide["networkValidatedRules"])
    lines = [
        "# MT semantic rule coverage",
        "",
        "Generated by `python -m app.rule_engine mrg-corpus --write` from the committed evidence",
        f"index (`{INDEX_PATH.relative_to(PROJECT_ROOT)}`, schema `{payload['schemaVersion']}`,",
        f"reader `{payload['readerVersion']}`). Every numbered Network Validated Rule of every",
        "guide in the knowledge base has exactly one disposition. `EXACT` and",
        "`PARTIAL_WEAKER_THAN_SOURCE` translations are candidates; all are `REVIEW_REQUIRED`;",
        "none is installed and runtime activations are 0. No rule text is reproduced here.",
        "",
        "## Summary",
        "",
        f"- Guides read: {len(guides)} (unreadable: {len(payload.get('unreadable', []))})",
        f"- Guides stating Network Validated Rules: {with_rules}",
        f"- Rules discovered: {total_rules}",
        f"- Exact: {totals['EXACT']}",
        f"- Partial (weaker than source): {totals['PARTIAL_WEAKER_THAN_SOURCE']}",
        f"- Unsupported: {totals['UNSUPPORTED']}",
        f"- Review required: {totals['EXACT'] + totals['PARTIAL_WEAKER_THAN_SOURCE']} "
        "candidates · Reviewed: 0 · Active: 0",
        "",
        "## Unsupported, by reason",
        "",
        "| Reason | Rules |",
        "|---|---:|",
    ]
    for reason, count in sorted(reasons.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| {reason} | {count} |")
    lines += [
        "",
        "## Templates",
        "",
        "| Template | Exact | Partial | Unsupported |",
        "|---|---:|---:|---:|",
    ]
    for name, bucket in sorted(templates.items()):
        lines.append(
            f"| {name} | {bucket['EXACT']} | {bucket['PARTIAL_WEAKER_THAN_SOURCE']} | "
            f"{bucket['UNSUPPORTED']} |"
        )
    lines += [
        "",
        "## Per message",
        "",
        "| MT | Release | Pages | Rule count | Exact | Partial | Unsupported | "
        "Review required | Reviewed | Active | Review pack |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for guide in guides:
        counts = {name: 0 for name in DISPOSITIONS}
        for rule in guide["networkValidatedRules"]:
            counts[rule["disposition"]] += 1
        review_required = counts["EXACT"] + counts["PARTIAL_WEAKER_THAN_SOURCE"]
        pack = (
            f"[{guide['messageType']}](mt-rule-review/{guide['messageType']}-{guide['release']}.md)"
        )
        lines.append(
            f"| {guide['messageType']} | {guide['release']} | {guide['pageCount']} | "
            f"{len(guide['networkValidatedRules'])} | {counts['EXACT']} | "
            f"{counts['PARTIAL_WEAKER_THAN_SOURCE']} | {counts['UNSUPPORTED']} | "
            f"{review_required} | 0 | 0 | {pack} |"
        )
    if payload.get("unreadable"):
        lines += ["", "## Unreadable", ""]
        for item in payload["unreadable"]:
            lines.append(f"- {item['path']}: {item['detail']}")
    return _document(lines)


def render_review_pack(guide: dict[str, Any]) -> str:
    """One reviewer package per guide: what a SWIFT SME needs to approve or refuse each
    candidate — page, rule id, error codes, disposition, template, residual — without
    the guide's own words, which the reviewer has in the licensed document."""
    lines = [
        f"# {guide['messageType']} {guide['release']} — Network Validated Rule review pack",
        "",
        f"Source `{guide['sourceId']}` · sha256 `{guide['sourceChecksum']}` · "
        f"{guide['pageCount']} pages · structure `{guide['structureChecksum']}`.",
        "",
        "Every candidate below is `REVIEW_REQUIRED`. A machine reading is not a SWIFT SME review;",
        "nothing here is installed or evaluated at runtime until a reviewed pack is committed.",
        "Open the page named and compare the rule's own wording with the interpretation.",
        "",
        f"Sequences read: {guide['sequences']} · format rows: {guide['rows']} · "
        f"field specifications: {guide['fieldSpecifications']} · reader objections: "
        f"{guide['objections']}",
        "",
    ]
    if guide["problems"]:
        lines += ["Reader notes: " + ", ".join(guide["problems"][:12]), ""]
    if not guide["networkValidatedRules"]:
        lines += ["This guide states no Network Validated Rules.", ""]
        return _document(lines)
    lines += [
        "| Rule | Page | Error codes | Disposition | Template / reason | Residual limitation | "
        "Refuter objections | Review |",
        "|---|---:|---|---|---|---|---|---|",
    ]
    for rule in guide["networkValidatedRules"]:
        template = rule["template"] or rule["reason"] or ""
        if rule["disposition"] == "UNSUPPORTED" and rule["reason"] and rule["template"]:
            template = f"{rule['template']} / {rule['reason']}"
        residual = "; ".join(item for item in rule["residual"] if item != STRUCTURE_ENFORCED)[:200]
        if rule.get("enforcedByStructure"):
            residual = "Enforced by the structure validator; no expression needed."
        lines.append(
            f"| {rule['ruleId']} | {rule['page']} | {', '.join(rule['errorCodes']) or '—'} | "
            f"{rule['disposition']} | {template} | {residual or '—'} | "
            f"{', '.join(rule['objections']) or '—'} | {rule['reviewStatus']} |"
        )
    return _document(lines)


def write_reports(payload: dict[str, Any]) -> list[Path]:
    written: list[Path] = []
    COVERAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    COVERAGE_PATH.write_text(render_coverage(payload), encoding="utf-8")
    written.append(COVERAGE_PATH)
    REVIEW_DIRECTORY.mkdir(parents=True, exist_ok=True)
    expected: set[Path] = set()
    for guide in payload["guides"]:
        path = REVIEW_DIRECTORY / f"{guide['messageType']}-{guide['release']}.md"
        path.write_text(render_review_pack(guide), encoding="utf-8")
        written.append(path)
        expected.add(path)
    for stray in REVIEW_DIRECTORY.glob("*.md"):
        if stray not in expected:
            stray.unlink()
    return written


def stale_reports(payload: dict[str, Any]) -> list[Path]:
    stale: list[Path] = []
    if not COVERAGE_PATH.exists() or COVERAGE_PATH.read_text(encoding="utf-8") != render_coverage(
        payload
    ):
        stale.append(COVERAGE_PATH)
    for guide in payload["guides"]:
        path = REVIEW_DIRECTORY / f"{guide['messageType']}-{guide['release']}.md"
        if not path.exists() or path.read_text(encoding="utf-8") != render_review_pack(guide):
            stale.append(path)
    return stale
