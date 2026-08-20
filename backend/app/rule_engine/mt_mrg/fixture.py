"""The derived metadata a reading leaves behind, so the rest of the work needs no document.

Everything downstream of reading a guide — the reconciliation reports, the reviewer
packages, the readiness matrix, the tests — depends on *what the guide established*, never
on its words. Writing that down once, as identifiers and digests, is what lets continuous
integration check the whole pipeline on a machine that has never seen a licensed document
and never will.

What is written here is deliberately restricted to derived facts: message and release
identity, digests, page numbers, sequence and field identifiers, qualifier tables, source
rule numbers and SWIFT error codes, and expressions this repository generated. No sentence
of the source is reproduced, and the rule text is represented only by its hash — which is
enough to notice that SWIFT reworded a rule, and not enough to read it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.rule_engine.dsl import ForEachOccurrence, walk
from app.rule_engine.mt_mrg import MRG_READER_VERSION
from app.rule_engine.mt_mrg.pipeline import MrgReading, MrgRun, source_fingerprint
from app.rule_engine.mt_mrg.rules import RuleFidelity

#: Bumped when the shape of the fixture changes, so a stale file is refused rather than
#: half-read. The reader version travels beside it: a change to how the guide is read must
#: invalidate every candidate derived from the old reading.
FIXTURE_SCHEMA = "mt-mrg-evidence/2"

FIXTURE_PATH = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "mt_mrg"
    / "sr2026-mt540-mt541.json"
)


def _sequences(reading: MrgReading) -> list[dict[str, Any]]:
    return [
        {
            "path": item.path,
            "presence": item.presence.value,
            "repetitive": item.repetitive,
            "name": item.name,
            "order": item.order,
            "parentPath": item.parent_path,
            "page": item.page,
        }
        for item in reading.structure.sequences
    ]


def _rows(reading: MrgReading) -> list[dict[str, Any]]:
    return [
        {
            "number": item.number,
            "sequencePath": item.sequence_path,
            "status": item.status.value,
            "tag": item.tag,
            "qualifier": item.qualifier,
            "genericQualifier": item.generic_qualifier,
            "options": list(item.options),
            "repetitive": item.repetitive,
            "page": item.page,
        }
        for item in reading.structure.rows
    ]


def _qualifiers(reading: MrgReading) -> list[dict[str, Any]]:
    return [
        {
            "sequencePath": item.sequence_path,
            "tag": item.tag,
            "qualifier": item.qualifier,
            "status": item.status.value,
            "repetition": item.repetition,
            "conditionalRules": list(item.conditional_rules),
            "options": list(item.options),
            "page": item.page,
        }
        for spec in reading.structure.field_specs
        for item in spec.qualifiers
    ]


def _field_specs(reading: MrgReading) -> list[dict[str, Any]]:
    return [
        {
            "ordinal": item.ordinal,
            "tag": item.tag,
            "sequencePath": item.sequence_path,
            "sequencePresence": item.sequence_presence.value,
            "fieldStatus": item.field_status,
            "conditionalRules": list(item.conditional_rules),
            "qualifierCount": len(item.qualifiers),
            "codeLists": {name: list(codes) for name, codes in item.codes},
            "errorCodes": list(item.error_codes),
            "blocks": [block.value for block in item.blocks],
            "firstPage": item.first_page,
            "lastPage": item.last_page,
        }
        for item in reading.structure.field_specs
    ]


def _rules(reading: MrgReading) -> list[dict[str, Any]]:
    compiled = (
        {item.rule.rule_id for item in reading.compiled.rules} if reading.compiled else set()
    )
    entries: list[dict[str, Any]] = []
    for translation in reading.translations:
        rule = translation.rule
        candidate_id = rule.canonical_rule_id
        entries.append(
            {
                "sourceRuleId": rule.source_rule_id,
                "ordinal": rule.ordinal,
                "candidateRuleId": candidate_id,
                "errorCodes": list(rule.error_codes),
                "firstPage": rule.first_page,
                "lastPage": rule.last_page,
                "textHash": rule.text_hash,
                "characterCount": rule.character_count,
                "fidelity": translation.fidelity.value,
                "template": translation.template,
                "reason": translation.reason.value if translation.reason else None,
                "residual": list(translation.residual),
                "interpretation": translation.interpretation,
                "occurrenceScopes": _occurrence_scopes(translation),
                "compiled": candidate_id in compiled,
                "references": [
                    {
                        "sequencePath": item.sequence_path,
                        "tag": item.tag,
                        "qualifier": item.qualifier,
                        "value": item.value,
                        "resolved": item.resolved,
                        "detail": item.detail,
                    }
                    for item in translation.references
                ],
            }
        )
    return entries


def _occurrence_scopes(translation: Any) -> list[str]:
    scopes: list[str] = []
    for node in (translation.when, translation.assertion):
        if node is None:
            continue
        for item in walk(node):
            if not isinstance(item, ForEachOccurrence):
                continue
            scope = item.for_each_occurrence.sequence_path
            if scope not in scopes:
                scopes.append(scope)
    return scopes


def _segment_sections(reading: MrgReading) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in reading.classifications:
        counts[item.section.value] = counts.get(item.section.value, 0) + 1
    return dict(sorted(counts.items()))


def to_fixture(reading: MrgReading) -> dict[str, Any]:
    identity = reading.identity
    return {
        "sourceId": reading.source_id,
        "messageType": identity.message_type,
        "messageName": identity.message_name,
        "standardsRelease": identity.standards_release,
        "releaseCoverText": identity.release_cover_text,
        "guideTitle": identity.guide_title,
        "publisherStatement": identity.publisher_statement,
        "pageCount": reading.page_count,
        "sourceChecksum": reading.checksum,
        "structureChecksum": reading.structure.checksum(),
        "fingerprint": source_fingerprint(reading),
        "sections": [
            {
                "section": item.section.value,
                "heading": item.heading,
                "firstPage": item.first_page,
                "lastPage": item.last_page,
            }
            for item in reading.spans
        ],
        "segmentCount": len(reading.segments),
        "segmentsBySection": _segment_sections(reading),
        "sequences": _sequences(reading),
        "formatRows": _rows(reading),
        "qualifierRows": _qualifiers(reading),
        "fieldSpecifications": _field_specs(reading),
        "networkValidatedRules": _rules(reading),
        "objections": [
            {"sourceRuleId": item.source_rule_id, "code": item.code, "detail": item.detail}
            for item in reading.objections
        ],
        "candidatePack": (
            {
                "packId": reading.pack.pack_id,
                "ruleCount": len(reading.pack.rules),
                "reviewStatus": reading.pack.review.status.value,
                "ruleReviewStatuses": sorted(
                    {item.review.status.value for item in reading.pack.rules}
                ),
                "compiles": reading.compiled is not None,
                "limitations": list(reading.pack.limitations),
            }
            if reading.pack
            else None
        ),
        "problems": list(reading.problems),
        "liveModelCalls": 0,
    }


def build(outcome: MrgRun) -> dict[str, Any]:
    return {
        "schemaVersion": FIXTURE_SCHEMA,
        "readerVersion": MRG_READER_VERSION,
        "sources": [to_fixture(item) for item in outcome.readings],
        "missing": sorted(outcome.missing),
    }


def render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=True) + "\n"


def write(outcome: MrgRun, path: Path | None = None) -> Path:
    target = path or FIXTURE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(build(outcome)), encoding="utf-8")
    return target


def load(path: Path | None = None) -> dict[str, Any]:
    target = path or FIXTURE_PATH
    payload: dict[str, Any] = json.loads(target.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != FIXTURE_SCHEMA:
        raise ValueError(
            f"{target.name} is {payload.get('schemaVersion')}; this reader expects "
            f"{FIXTURE_SCHEMA}"
        )
    return payload


@dataclass(frozen=True)
class FixtureSource:
    """One guide's derived metadata, read back with the accessors the reports want."""

    payload: dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.payload[key]

    @property
    def message_type(self) -> str:
        return str(self.payload["messageType"])

    @property
    def standards_release(self) -> str:
        return str(self.payload["standardsRelease"])

    def rules(self) -> list[dict[str, Any]]:
        return list(self.payload["networkValidatedRules"])

    def by_fidelity(self, fidelity: RuleFidelity) -> list[dict[str, Any]]:
        return [item for item in self.rules() if item["fidelity"] == fidelity.value]

    def sequence(self, path: str) -> dict[str, Any] | None:
        return next(
            (item for item in self.payload["sequences"] if item["path"] == path), None
        )

    def qualifier_rows(self, sequence_path: str, field_number: str) -> list[dict[str, Any]]:
        return [
            item
            for item in self.payload["qualifierRows"]
            if item["sequencePath"] == sequence_path and item["tag"][:2] == field_number
        ]


def sources(payload: dict[str, Any]) -> list[FixtureSource]:
    return [FixtureSource(item) for item in payload["sources"]]


def source_for(payload: dict[str, Any], message_type: str) -> FixtureSource | None:
    return next(
        (item for item in sources(payload) if item.message_type == message_type.upper()), None
    )
