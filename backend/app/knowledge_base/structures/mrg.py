"""Read a Message Reference Guide's structure once, at sync time, and keep what a pack
compiler needs as a compact artifact in the knowledge database.

Everything here reuses the Phase 5B reader (`app.rule_engine.mt_mrg`). What is persisted is
derived structural metadata — sequences, rows, qualifiers, codes, short field headings —
never the guide's prose; and it lives in the ignored local database, never in Git.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.knowledge_base.identify import ParsedSource

MRG_STRUCTURE_KIND = "mrg-structure/1"
LINE_PROBLEM = re.compile(r"UNPARSED_TABLE_TEXT_AT_LINE_(\d+)_")


@dataclass(frozen=True)
class MrgStructureArtifact:
    source_id: str
    message_type: str
    message_name: str
    release: str
    structure_checksum: str
    sequences: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    qualifier_rows: list[dict[str, Any]]
    field_specs: list[dict[str, Any]]
    problems: list[str]
    network_validated_rules: int

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> MrgStructureArtifact:
        return cls(**payload)


def read_structure(parsed: ParsedSource) -> MrgStructureArtifact:
    from app.rule_engine.mt_mrg.document import classify, identify, pages_of
    from app.rule_engine.mt_mrg.formatspec import StructureBuilder
    from app.rule_engine.mt_mrg.rules import discover

    pages = pages_of(parsed.text)
    identity, problems = identify(pages)
    if identity is None:
        raise ValueError("not a Message Reference Guide: " + ", ".join(problems))
    spans = classify(pages, identity.message_type)
    structure = StructureBuilder(identity.message_type, identity.standards_release).build(
        pages,
        spans,
        message_name=identity.message_name,
        release_text=identity.release_cover_text,
    )
    rules = discover(
        pages,
        spans,
        message_type=identity.message_type,
        message_name=identity.message_name,
        standards_release=identity.standards_release,
        release_text=identity.release_cover_text,
    )
    return MrgStructureArtifact(
        source_id=identity.logical_source_id,
        message_type=identity.message_type,
        message_name=identity.message_name,
        release=identity.standards_release,
        structure_checksum=structure.checksum(),
        sequences=[
            {
                "path": item.path,
                "presence": item.presence.value,
                "repetitive": item.repetitive,
                "name": item.name,
                "order": item.order,
                "parentPath": item.parent_path,
                "page": item.page,
            }
            for item in structure.sequences
        ],
        rows=[
            {
                "number": item.number,
                "sequencePath": item.sequence_path,
                "status": item.status.value,
                "tag": item.tag,
                "qualifier": item.qualifier,
                "genericQualifier": item.generic_qualifier,
                "options": list(item.options),
                "content": item.content,
                "description": item.description[:80],
                "repetitive": item.repetitive,
                "page": item.page,
            }
            for item in structure.rows
        ],
        qualifier_rows=[
            {
                "sequencePath": item.sequence_path,
                "tag": item.tag,
                "order": item.order,
                "status": item.status.value,
                "qualifier": item.qualifier,
                "repetition": item.repetition,
                "conditionalRules": list(item.conditional_rules),
                "options": list(item.options),
                "description": item.description[:80],
                "page": item.page,
            }
            for spec in structure.field_specs
            for item in spec.qualifiers
        ],
        field_specs=[
            {
                "ordinal": spec.ordinal,
                "tag": spec.tag,
                "heading": spec.heading[:80],
                "sequencePath": spec.sequence_path,
                "fieldStatus": spec.field_status,
                "conditionalRules": list(spec.conditional_rules),
                "codes": {qualifier: list(codes) for qualifier, codes in spec.codes},
                "openCodeLists": list(spec.open_code_lists),
                "formats": {option: notation for option, notation in spec.formats},
                "errorCodes": list(spec.error_codes),
                "firstPage": spec.first_page,
                "lastPage": spec.last_page,
            }
            for spec in structure.field_specs
        ],
        problems=list(structure.problems),
        network_validated_rules=len(rules),
    )


def cached_text_path(cache_dir: Path, checksum: str) -> Path:
    """Where the sync keeps a guide's page-marked text, by content checksum."""
    return cache_dir / "mrg-text" / f"{checksum.removeprefix('sha256:')}.txt"


def table_problem_pages(parsed: ParsedSource, artifact: MrgStructureArtifact) -> frozenset[int]:
    """Pages where the Format Specifications table could not be read completely."""
    from app.rule_engine.mt_mrg.document import pages_of

    line_to_page: dict[int, int] = {}
    for page in pages_of(parsed.text):
        for line in page.lines:
            line_to_page[line.number] = page.number
    found: set[int] = set()
    for problem in artifact.problems:
        match = LINE_PROBLEM.search(problem)
        if match:
            number = line_to_page.get(int(match.group(1)))
            if number is not None:
                found.add(number)
    return frozenset(found)


def artifact_checksum(artifact: MrgStructureArtifact) -> str:
    return hashlib.sha256(json.dumps(artifact.as_payload(), sort_keys=True).encode()).hexdigest()
