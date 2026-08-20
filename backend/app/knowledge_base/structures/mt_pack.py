"""Compile local MT Structure Packs from Prowide evidence and MRG Format Specifications.

Build-time only (it reads the Prowide fixture through ``app.spec_engine.mt_prowide``, which
the runtime never imports). One generic compiler for every message: no branch anywhere
names a message type, and a test greps this package to keep it that way.

Two sources, complementary:

- Prowide (SR2025): sequences, field groups with presence/order/options/repetition, and
  per-tag format notation. No qualifiers, no codes.
- Message Reference Guide (its own release): Format Specification rows with qualifiers,
  options and presence; qualifier tables; CODES blocks.

A pack for a release the guide covers is built from the guide and corroborated against
Prowide; a pack for a message with Prowide evidence only is built from Prowide and, where
a generic field has no qualifier evidence, stays ``STRUCTURE_AVAILABLE`` rather than
pretending the tester should type the qualifier.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.config import Settings
from app.knowledge_base import PACK_COMPILER_VERSION
from app.knowledge_base.db import KnowledgeDatabase
from app.knowledge_base.models import Readiness, SyncProgress, release_lane
from app.knowledge_base.structures.mrg import MRG_STRUCTURE_KIND, MrgStructureArtifact
from app.knowledge_base.structures.mt_loader import (
    MT_PACK_VERSION,
    PREVIEW_CAPABILITY_STATEMENT,
    load_mt_pack_dict,
)
from app.knowledge_base.structures.swift_format import (
    FormatUnsupported,
    compile_format,
    input_kind_for,
    is_value_less,
    synthetic_value,
)

PROWIDE_RELEASE = "SR2025"
CATEGORY_AREA: dict[int, str] = {
    0: "SYSTEM_MESSAGES",
    1: "CUSTOMER_PAYMENTS",
    2: "FINANCIAL_INSTITUTION_TRANSFERS",
    3: "TREASURY_MARKETS",
    4: "COLLECTIONS_CASH_LETTERS",
    5: "SECURITIES_MARKETS",
    6: "PRECIOUS_METALS_SYNDICATIONS",
    7: "DOCUMENTARY_CREDITS_GUARANTEES",
    8: "TRAVELLERS_CHEQUES",
    9: "CASH_MANAGEMENT",
}
LIMITATIONS = [
    "Structure-backed test generation; complete semantic rules are not established.",
    "Repetitive fields inside one sequence occurrence render once per occurrence.",
    "Network Validated Rules, usage rules, market practice and client rules are not "
    "evaluated unless a reviewed Rule Pack is installed.",
    "Not Swift certification, conformance, or proof of User Handbook completeness.",
]


@dataclass
class PackRow:
    row_id: str
    sequence_path: str
    tag: str
    qualifier: str | None
    presence: str
    format: str
    format_pattern: str | None
    format_fidelity: str
    qualifier_separator: str
    display_name: str
    technical_name: str
    allowed_codes: list[str]
    input_kind: str
    max_length: int | None
    choice_group: str | None
    repetitive: bool
    order: float
    evidence: str
    page: int | None = None
    blockers: list[str] = field(default_factory=list)
    value_less: bool = False

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "rowId": self.row_id,
            "valueLess": self.value_less,
            "sequencePath": self.sequence_path,
            "tag": self.tag,
            "option": self.tag[2:],
            "qualifier": self.qualifier,
            "businessPath": _business_path(self.sequence_path, self.tag, self.qualifier),
            "displayName": self.display_name,
            "technicalName": self.technical_name,
            "presence": self.presence,
            "format": self.format,
            "formatPattern": self.format_pattern,
            "formatFidelity": self.format_fidelity,
            "qualifierSeparator": self.qualifier_separator,
            "allowedCodes": list(self.allowed_codes),
            "inputKind": self.input_kind,
            "maxLength": self.max_length,
            "choiceGroup": self.choice_group,
            "repetitive": self.repetitive,
            "evidence": self.evidence,
            "sourcePage": self.page,
        }
        if self.blockers:
            payload["blockers"] = list(self.blockers)
        return payload


@dataclass
class PackSequence:
    path: str
    code: str
    name: str
    parent_path: str | None
    order: int
    min_occurs: int
    max_occurs: int
    bracketed: bool = True
    insert_after_tag: str | None = None
    leading_tags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "path": self.path,
            "code": self.code,
            "name": self.name,
            "parentPath": self.parent_path,
            "order": self.order,
            "minOccurs": self.min_occurs,
            "maxOccurs": self.max_occurs,
            "bracketed": self.bracketed,
        }
        if self.insert_after_tag:
            payload["insertAfterTag"] = self.insert_after_tag
        if self.leading_tags:
            payload["leadingTags"] = list(self.leading_tags)
        return payload


@dataclass
class CompiledMtPack:
    message_type: str
    release: str
    pack: dict[str, Any]
    blockers: list[str]
    gates: dict[str, dict[str, Any]]
    readiness: Readiness
    reconciliation: dict[str, Any]
    source_ids: list[str]
    source_checksums: list[str]

    @property
    def pack_checksum(self) -> str:
        return str(self.pack["packChecksum"])


# -- entry point ---------------------------------------------------------------------------


def compile_mt_structures(
    settings: Settings,
    database: KnowledgeDatabase,
    pack_dir: Path,
    report: SyncProgress,
    *,
    include_prowide: bool = True,
) -> None:
    from app.spec_engine.mt_prowide.extractor import load_extraction

    del settings
    pack_dir.mkdir(parents=True, exist_ok=True)
    try:
        extraction = load_extraction()
    except (OSError, ValueError) as error:
        report.failures.append(
            {
                "path": "prowide-fixture",
                "code": "STRUCTURE_SOURCE_MISSING",
                "detail": type(error).__name__,
            }
        )
        extraction = None
    prowide_messages = {}
    global_fields: dict[str, Any] = {}
    prowide_checksum = ""
    if extraction is not None:
        prowide_messages = {item.message_type: item for item in extraction.messages}
        global_fields = {item.tag: item for item in extraction.global_fields}
        prowide_checksum = hashlib.sha256(
            json.dumps(extraction.source.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()
    mrg_artifacts: dict[tuple[str, str], tuple[str, MrgStructureArtifact]] = {}
    for _key, checksum, payload in database.artifacts(MRG_STRUCTURE_KIND):
        artifact = MrgStructureArtifact.from_payload(payload)
        mrg_artifacts[(artifact.message_type, artifact.release)] = (checksum, artifact)

    targets: dict[tuple[str, str], str] = {}
    for message_type in prowide_messages if include_prowide else {}:
        if "_" in message_type:
            continue  # STP/REMIT variants share the FIN type; recorded, not compiled
        targets[(message_type, PROWIDE_RELEASE)] = "PROWIDE"
    for message_type, release in mrg_artifacts:
        targets[(message_type, release)] = "MRG"

    existing = {(row["message_type"], row["release"]): row for row in _structure_rows(database)}
    for (message_type, release), primary in sorted(targets.items()):
        mrg_entry = mrg_artifacts.get((message_type, release))
        prowide = prowide_messages.get(message_type)
        source_checksums = sorted(
            item
            for item in [prowide_checksum if prowide else "", mrg_entry[0] if mrg_entry else ""]
            if item
        )
        identity = hashlib.sha256(
            f"{PACK_COMPILER_VERSION}|{message_type}|{release}|{'|'.join(source_checksums)}".encode()
        ).hexdigest()
        previous = existing.get((message_type, release))
        if (
            previous is not None
            and previous["detail_identity"] == identity
            and Path(previous["pack_path"] or "").exists()
        ):
            report.structures_reused += 1
            continue
        try:
            compiled = compile_mt_pack(
                message_type,
                release,
                prowide=prowide,
                global_fields=global_fields,
                mrg=mrg_entry[1] if mrg_entry else None,
                mrg_checksum=mrg_entry[0] if mrg_entry else None,
                prowide_checksum=prowide_checksum if prowide else None,
                primary=primary,
            )
        except Exception as error:  # noqa: BLE001 - one message must not stop the corpus
            report.structures_failed += 1
            report.failures.append(
                {
                    "path": f"{message_type}:{release}",
                    "code": "STRUCTURE_COMPILATION_FAILED",
                    "detail": f"{type(error).__name__}: {str(error)[:120]}",
                }
            )
            _record_structure(
                database,
                message_type,
                release,
                pack_path=None,
                pack_checksum=None,
                structure_source=primary,
                readiness=Readiness.KNOWLEDGE_ONLY,
                blockers=["STRUCTURE_COMPILATION_FAILED"],
                gates={},
                source_ids=[],
                source_checksums=source_checksums,
                detail={"identity": identity, "error": type(error).__name__},
            )
            continue
        pack_path = pack_dir / f"{message_type}-{release}.yaml"
        pack_path.write_text(
            yaml.safe_dump(compiled.pack, sort_keys=False, allow_unicode=True, width=100),
            encoding="utf-8",
        )
        report.structures_compiled += 1
        _record_structure(
            database,
            message_type,
            release,
            pack_path=str(pack_path),
            pack_checksum=compiled.pack_checksum,
            structure_source=str(compiled.pack["structureSource"]),
            readiness=compiled.readiness,
            blockers=compiled.blockers,
            gates=compiled.gates,
            source_ids=compiled.source_ids,
            source_checksums=compiled.source_checksums,
            detail={
                "identity": identity,
                "reconciliation": compiled.reconciliation,
                "fieldCount": len(compiled.pack["fields"]),
                "sequenceCount": len(compiled.pack["sequences"]),
                "name": compiled.pack["name"],
                "businessArea": compiled.pack["businessArea"],
                "category": compiled.pack.get("category"),
            },
        )


def _structure_rows(database: KnowledgeDatabase) -> list[dict[str, Any]]:
    with database.read() as connection:
        rows = connection.execute(
            "SELECT * FROM knowledge_structure WHERE format = 'MT'"
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        detail = json.loads(row["detail"])
        result.append(
            {
                "message_type": row["message_type"],
                "release": row["release"],
                "pack_path": row["pack_path"],
                "detail_identity": detail.get("identity"),
            }
        )
    return result


def _record_structure(
    database: KnowledgeDatabase,
    message_type: str,
    release: str,
    *,
    pack_path: str | None,
    pack_checksum: str | None,
    structure_source: str,
    readiness: Readiness,
    blockers: list[str],
    gates: dict[str, Any],
    source_ids: list[str],
    source_checksums: list[str],
    detail: dict[str, Any],
) -> None:
    with database.write() as connection:
        connection.execute(
            """
            INSERT INTO knowledge_structure(format, message_type, release, lane, pack_path,
                pack_checksum, structure_source, readiness, blockers, gates, compiler_version,
                source_ids, source_checksums, detail, updated_at)
            VALUES ('MT', ?, ?, 'KNOWLEDGE_PREVIEW', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(format, message_type, release, lane) DO UPDATE SET
                pack_path = excluded.pack_path, pack_checksum = excluded.pack_checksum,
                structure_source = excluded.structure_source, readiness = excluded.readiness,
                blockers = excluded.blockers, gates = excluded.gates,
                compiler_version = excluded.compiler_version, source_ids = excluded.source_ids,
                source_checksums = excluded.source_checksums, detail = excluded.detail,
                updated_at = excluded.updated_at
            """,
            (
                message_type,
                release,
                pack_path,
                pack_checksum,
                structure_source,
                readiness.value,
                json.dumps(blockers),
                json.dumps(gates, sort_keys=True),
                PACK_COMPILER_VERSION,
                json.dumps(source_ids),
                json.dumps(source_checksums),
                json.dumps(detail, sort_keys=True),
            ),
        )


# -- compilation --------------------------------------------------------------------------


def compile_mt_pack(
    message_type: str,
    release: str,
    *,
    prowide: Any,
    global_fields: dict[str, Any],
    mrg: MrgStructureArtifact | None,
    mrg_checksum: str | None,
    prowide_checksum: str | None,
    primary: str,
) -> CompiledMtPack:
    blockers: list[str] = []
    if primary == "MRG" and mrg is not None:
        sequences, rows, seq_blockers = _rows_from_mrg(message_type, mrg, prowide, global_fields)
        structure_source = (
            f"SWIFT_MRG_{release}_PROWIDE_{PROWIDE_RELEASE}_CORROBORATED"
            if prowide is not None
            else f"SWIFT_MRG_{release}"
        )
        name = mrg.message_name
        source_type = "SWIFT_MRG_FORMAT_SPECIFICATION"
    elif prowide is not None:
        sequences, rows, seq_blockers = _rows_from_prowide(message_type, prowide, global_fields)
        structure_source = f"PROWIDE_{PROWIDE_RELEASE}"
        name = str(prowide.name or message_type)
        source_type = "PROWIDE_DERIVED_STRUCTURAL_EVIDENCE"
    else:
        raise ValueError("no structural source")
    blockers.extend(seq_blockers)
    for row in rows:
        for blocker in row.blockers:
            if blocker not in blockers:
                blockers.append(blocker)
    reconciliation = _reconcile(sequences, rows, prowide, mrg) if (prowide and mrg) else {}
    if reconciliation.get("conflict"):
        blockers.append("STRUCTURE_SOURCE_CONFLICT")
    category = int(prowide.category) if prowide is not None else int(message_type[2])
    rows.sort(
        key=lambda item: (_sequence_rank(sequences, item.sequence_path), item.order, item.row_id)
    )
    pack: dict[str, Any] = {
        "packVersion": MT_PACK_VERSION,
        "format": "MT",
        "messageType": message_type,
        "name": name,
        "shortDescription": f"{name} ({release}, structure-backed test preview).",
        "scope": (
            f"Every sequence and field the {structure_source.replace('_', ' ')} evidence states."
        ),
        "release": release,
        "releaseLane": release_lane(release).value,
        "lane": "KNOWLEDGE_PREVIEW",
        "category": category,
        "businessArea": CATEGORY_AREA.get(category, "OTHER"),
        "structureSource": structure_source,
        "sourceType": source_type,
        "sourceReference": f"{structure_source}-{message_type}",
        "compilerVersion": PACK_COMPILER_VERSION,
        "capabilityStatement": PREVIEW_CAPABILITY_STATEMENT,
        "limitations": list(LIMITATIONS),
        "sources": [
            item
            for item in [
                {
                    "sourceId": f"PROWIDE-{PROWIDE_RELEASE}-{message_type}",
                    "checksum": prowide_checksum,
                    "role": "STRUCTURAL_EVIDENCE",
                }
                if prowide_checksum
                else None,
                {
                    "sourceId": mrg.source_id,
                    "checksum": mrg_checksum,
                    "role": "FORMAT_SPECIFICATION",
                }
                if mrg is not None
                else None,
            ]
            if item
        ],
        "reconciliation": reconciliation,
        "sequences": [item.as_dict() for item in sequences],
        "fields": [item.as_dict() for item in rows],
    }
    pack["packChecksum"] = (
        "sha256:"
        + hashlib.sha256(json.dumps(pack, sort_keys=True, default=str).encode()).hexdigest()
    )
    gates, gate_blockers = run_mt_gates(pack)
    blockers.extend(item for item in gate_blockers if item not in blockers)
    pack["blockers"] = list(blockers)
    readiness = _readiness(gates, blockers)
    pack["readiness"] = readiness.value
    pack["gates"] = gates
    return CompiledMtPack(
        message_type=message_type,
        release=release,
        pack=pack,
        blockers=blockers,
        gates=gates,
        readiness=readiness,
        reconciliation=reconciliation,
        source_ids=[str(item["sourceId"]) for item in pack["sources"]],
        source_checksums=sorted(str(item["checksum"]) for item in pack["sources"]),
    )


def _sequence_rank(sequences: list[PackSequence], path: str) -> int:
    for sequence in sequences:
        if sequence.path == path:
            return sequence.order
    return 10_000


def _business_path(sequence_path: str, tag: str, qualifier: str | None) -> str:
    parts = [sequence_path.lower(), tag.lower()]
    if qualifier:
        parts.append(qualifier.lower())
    return ".".join(parts)


def _row_id(message_type: str, sequence_path: str, tag: str, qualifier: str | None) -> str:
    return f"{message_type}-{sequence_path}-{tag}-{qualifier or 'NONE'}"


def _format_for(
    tag: str, global_fields: dict[str, Any], fallback: str | None
) -> tuple[str, str | None, str, str, int | None, str]:
    """``(notation, pattern, fidelity, separator, max_length, value_notation)``."""
    evidence = global_fields.get(tag)
    notation = (
        str(evidence.validator_pattern)
        if evidence is not None and evidence.validator_pattern
        else (fallback or "")
    )
    if not notation or notation.upper() == "CUSTOM":
        # Prowide parses a few fields (61, 79, 86, 22C) with hand-written code and states no
        # notation for them; the pack says so instead of guessing one.
        return "", None, "UNKNOWN", "//", None, ""
    try:
        compiled = compile_format(notation)
    except FormatUnsupported:
        return notation, None, "PARTIAL", "//", None, notation
    return (
        notation,
        compiled.pattern,
        "EXACT",
        compiled.qualifier_separator,
        compiled.max_length,
        compiled.value_notation,
    )


def _labels(tag: str, global_fields: dict[str, Any]) -> str:
    evidence = global_fields.get(tag)
    if evidence is None:
        return tag
    labels = [label for label in evidence.component_labels if label and label != "Qualifier"]
    return " / ".join(labels) if labels else tag


# -- from Prowide -----------------------------------------------------------------------------


def _rows_from_prowide(
    message_type: str, prowide: Any, global_fields: dict[str, Any]
) -> tuple[list[PackSequence], list[PackRow], list[str]]:
    blockers: list[str] = []
    sequences: list[PackSequence] = []
    root_has_fields = any(group.sequence_path == "ROOT" for group in prowide.field_groups)
    has_real_sequences = any(seq.path != "ROOT" for seq in prowide.sequences)
    for seq in prowide.sequences:
        if seq.path == "ROOT":
            if not root_has_fields:
                continue
            sequences.append(
                PackSequence(
                    path="ROOT",
                    code="ROOT",
                    name="Message body",
                    parent_path=None,
                    order=1,
                    min_occurs=1,
                    max_occurs=1,
                    bracketed=False,
                )
            )
            continue
        parent = seq.parent_path
        if parent is None and root_has_fields:
            parent = "ROOT"
        own_groups = sorted(
            (g for g in prowide.field_groups if g.sequence_path == seq.path), key=lambda g: g.order
        )
        # A sequence delimited by :16R:/:16S: lists them as its own field groups; one that is
        # not (Categories 1-4, 9) is opened by its first field when read back.
        bracketed = any("16R" in g.tags for g in own_groups)
        leading: list[str] = []
        if not bracketed:
            # Any field up to and including the first mandatory one can be the first line
            # of an occurrence, so each of them opens the sequence when read back.
            for group in own_groups:
                leading.extend(group.tags)
                if group.presence.value == "MANDATORY":
                    break
        sequences.append(
            PackSequence(
                path=seq.path,
                # Prowide reports UNKNOWN for a sequence without a block code; the path is
                # then the only name it has, and codes must stay unique within a message.
                code=seq.code if seq.code and seq.code != "UNKNOWN" else seq.path,
                name=seq.name or seq.code,
                parent_path=parent,
                # Orders start at 1; the unbracketed body, when present, takes 1 itself.
                order=int(seq.order) + (1 if root_has_fields else 0),
                min_occurs=max(0, int(seq.min_occurs)),
                max_occurs=int(seq.max_occurs or (100 if seq.repeatable else 1)),
                bracketed=bracketed,
                leading_tags=leading,
            )
        )
    if root_has_fields and has_real_sequences:
        # Field groups are numbered in document order across the whole message, so a
        # top-level sequence sits after the last root field whose group precedes the
        # sequence's first group. That is what lets MT935's ``72`` follow its repeats.
        root_groups = sorted(
            (g for g in prowide.field_groups if g.sequence_path == "ROOT"), key=lambda g: g.order
        )
        for sequence in sequences:
            if sequence.parent_path != "ROOT":
                continue
            own = [g.order for g in prowide.field_groups if g.sequence_path == sequence.path]
            if not own:
                continue
            first = min(own)
            before = [
                g
                for g in root_groups
                if g.order < first and g.tags and g.tags[0] not in {"16R", "16S"}
            ]
            if before:
                sequence.insert_after_tag = before[-1].tags[0]
    rows: list[PackRow] = []
    seen_ids: dict[str, int] = {}
    for group in prowide.field_groups:
        tags = [tag for tag in group.tags if tag not in {"16R", "16S"}]
        if not tags:
            continue
        for tag in tags:
            # The repository's convention: ``parent/branch`` — members share the parent,
            # each branch is its own option. That is what lets one value satisfy the group.
            choice = f"{group.id}/{tag}" if len(tags) > 1 else None
            base_id = _row_id(message_type, group.sequence_path, tag, None)
            seen_ids[base_id] = seen_ids.get(base_id, 0) + 1
            duplicate_ordinal = seen_ids[base_id]
            notation, pattern, fidelity, separator, max_length, value_notation = _format_for(
                tag, global_fields, None
            )
            evidence = global_fields.get(tag)
            generic = bool(evidence is not None and evidence.generic)
            row_blockers: list[str] = []
            qualifier: str | None = None
            value_less = is_value_less(notation) and bool(notation)
            if value_less:
                pattern, fidelity = "", "EXACT"
            if generic:
                row_blockers.append("QUALIFIER_EVIDENCE_MISSING")
                # The whole ``:4!c//…`` shape is the value until a guide supplies qualifiers.
                pattern = None
                fidelity = "PARTIAL"
            if fidelity == "PARTIAL" and "FORMAT_FIDELITY_PARTIAL" not in row_blockers:
                row_blockers.append("FORMAT_FIDELITY_PARTIAL")
            row_id = base_id
            if duplicate_ordinal > 1:
                # The same tag twice in one sequence with two meanings (MT360's 18A). The
                # flat (sequence, tag) address cannot tell them apart when reading back.
                row_id = f"{base_id}-{duplicate_ordinal}"
                row_blockers.append("DUPLICATE_TAG_IN_SEQUENCE")
            rows.append(
                PackRow(
                    row_id=row_id,
                    sequence_path=group.sequence_path,
                    tag=tag,
                    qualifier=qualifier,
                    presence="MANDATORY" if group.presence.value == "MANDATORY" else "OPTIONAL",
                    format=notation,
                    format_pattern=pattern,
                    format_fidelity=fidelity,
                    qualifier_separator=separator,
                    display_name=f"{tag} {_labels(tag, global_fields)}",
                    technical_name=notation or tag,
                    allowed_codes=[],
                    input_kind=input_kind_for(compile_format(notation), codes=False)
                    if pattern
                    else "TEXT",
                    max_length=max_length,
                    choice_group=choice,
                    repetitive=bool(group.repeatable),
                    order=float(group.order),
                    evidence="PROWIDE_SOURCE_JAVADOC_SCHEME",
                    blockers=row_blockers,
                    value_less=value_less,
                )
            )
    if not rows:
        blockers.append("STRUCTURE_SOURCE_MISSING")
    return sequences, rows, blockers


# -- from a Message Reference Guide --------------------------------------------------------------


def _rows_from_mrg(
    message_type: str,
    mrg: MrgStructureArtifact,
    prowide: Any,
    global_fields: dict[str, Any],
) -> tuple[list[PackSequence], list[PackRow], list[str]]:
    blockers: list[str] = []
    prowide_codes = {
        seq.path: seq.code for seq in (prowide.sequences if prowide is not None else [])
    }
    # The 16R row of each sequence names its block code in the content column.
    codes_from_table: dict[str, str] = {}
    for row in mrg.rows:
        if row["tag"] == "16R" and row["content"].strip():
            codes_from_table.setdefault(row["sequencePath"], row["content"].strip().split()[0])
    sequences: list[PackSequence] = []
    omitted_paths: set[str] = set()
    for seq in sorted(mrg.sequences, key=lambda item: int(item["order"])):
        bracketed = seq["path"] in codes_from_table
        code = codes_from_table.get(seq["path"]) or prowide_codes.get(seq["path"])
        if not code:
            # Neither the guide's table nor Prowide states the block code. Rendering the
            # path as a code would be an invention, so the sequence is left out and said so.
            blockers.append(f"SEQUENCE_OMITTED_CODE_UNKNOWN:{seq['path']}")
            omitted_paths.add(seq["path"])
            continue
        own_rows = [
            row
            for row in mrg.rows
            if row["sequencePath"] == seq["path"] and row["tag"] not in {"16R", "16S"}
        ]
        leading_rows: list[str] = []
        for row in own_rows:
            number = row["tag"][:2]
            options = list(row["options"]) or [row["tag"][2:]]
            leading_rows.extend(
                f"{number}{option}" if option and option != "a" else number for option in options
            )
            if row["status"] == "M":
                break
        sequences.append(
            PackSequence(
                path=seq["path"],
                code=code,
                name=seq["name"] or code,
                parent_path=seq.get("parentPath"),
                order=int(seq["order"]),
                min_occurs=1 if seq["presence"] == "MANDATORY" else 0,
                max_occurs=100 if seq["repetitive"] else 1,
                bracketed=bracketed,
                leading_tags=[] if bracketed else leading_rows,
            )
        )
    omitted_paths.update(
        seq["path"]
        for seq in mrg.sequences
        if any(seq["path"].startswith(parent) and seq["path"] != parent for parent in omitted_paths)
    )
    sequences = [item for item in sequences if item.path not in omitted_paths]
    known_paths = {item.path for item in sequences}
    qualifier_rows: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for qrow in mrg.qualifier_rows:
        qualifier_rows[(qrow["sequencePath"], qrow["tag"][:2])].append(qrow)
    codes_by_field: dict[tuple[str, str], dict[str, list[str]]] = {}
    headings: dict[tuple[str, str], str] = {}
    for spec in mrg.field_specs:
        key = (spec["sequencePath"], spec["tag"][:2])
        codes_by_field.setdefault(key, {}).update(spec.get("codes", {}))
        headings.setdefault(key, spec["heading"])

    rows: list[PackRow] = []
    for row in mrg.rows:
        tag = row["tag"]
        if tag in {"16R", "16S"}:
            continue
        if row["sequencePath"] in omitted_paths:
            continue
        if row["sequencePath"] not in known_paths:
            blockers.append("ROW_OUTSIDE_KNOWN_SEQUENCE")
            continue
        number = tag[:2]
        row_options = list(row["options"]) or (
            [tag[2:].upper()] if len(tag) > 2 and tag[2:] != "a" else []
        )
        key = (row["sequencePath"], number)
        heading = headings.get(key, "")
        field_label = heading.split(":", 1)[1].strip() if ":" in heading else heading
        if row["genericQualifier"]:
            table = qualifier_rows.get(key, [])
            if not table:
                # A generic field whose qualifier table the reader could not find.
                rows.append(
                    _mrg_row(
                        message_type,
                        row,
                        tag,
                        None,
                        row_options,
                        global_fields,
                        field_label,
                        None,
                        [],
                        "MANDATORY" if row["status"] == "M" else "OPTIONAL",
                        blockers=["QUALIFIER_EVIDENCE_MISSING"],
                    )
                )
                continue
            by_order: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for qrow in table:
                by_order[int(qrow["order"])].append(qrow)
            for order, group in sorted(by_order.items()):
                combos: list[tuple[str, str]] = []
                for qrow in group:
                    options = list(qrow["options"]) or row_options or [""]
                    for option in options:
                        combos.append((qrow["qualifier"], option))
                parent = (
                    f"{message_type}-{row['sequencePath']}-{number}-ORDER{order}"
                    if len(combos) > 1
                    else None
                )
                for qrow in group:
                    options = list(qrow["options"]) or row_options or [""]
                    presence = (
                        "MANDATORY"
                        if row["status"] == "M" and qrow["status"] == "M"
                        else "OPTIONAL"
                    )
                    for option in options:
                        concrete = f"{number}{option}" if option else tag
                        choice = f"{parent}/{qrow['qualifier']}-{option or 'X'}" if parent else None
                        rows.append(
                            _mrg_row(
                                message_type,
                                row,
                                concrete,
                                qrow["qualifier"],
                                [option] if option else [],
                                global_fields,
                                qrow["description"] or field_label,
                                choice,
                                codes_by_field.get(key, {}).get(qrow["qualifier"], []),
                                presence,
                                order_hint=float(row["number"]) + order / 1000.0,
                                page=qrow.get("page"),
                                repetitive=qrow["repetition"] == "R" or bool(row["repetitive"]),
                            )
                        )
            continue
        # A literal qualifier, or none at all (23G, 35B, 16R…).
        qualifier = row["qualifier"]
        options = row_options or [""]
        parent = (
            f"{message_type}-{row['sequencePath']}-{number}-{qualifier or 'NONE'}"
            if len(options) > 1
            else None
        )
        for option in options:
            concrete = f"{number}{option}" if option else tag
            choice = f"{parent}/{option or 'X'}" if parent else None
            rows.append(
                _mrg_row(
                    message_type,
                    row,
                    concrete,
                    qualifier,
                    [option] if option else [],
                    global_fields,
                    row["description"] or field_label,
                    choice,
                    codes_by_field.get(key, {}).get(qualifier or "", []),
                    "MANDATORY" if row["status"] == "M" else "OPTIONAL",
                )
            )
    # The same (sequence, tag, qualifier) can be listed twice by a guide — once per format
    # option group or once per repeat. Row ids must stay unique, and the reader cannot tell
    # the two apart, so the later one is suffixed and marked.
    seen_ids: dict[str, int] = {}
    for item in rows:
        seen_ids[item.row_id] = seen_ids.get(item.row_id, 0) + 1
        if seen_ids[item.row_id] > 1:
            item.row_id = f"{item.row_id}-{seen_ids[item.row_id]}"
            item.blockers.append("DUPLICATE_TAG_IN_SEQUENCE")
    if not rows:
        blockers.append("STRUCTURE_SOURCE_MISSING")
    return sequences, rows, sorted(set(blockers))


def _mrg_row(
    message_type: str,
    row: dict[str, Any],
    tag: str,
    qualifier: str | None,
    options: list[str],
    global_fields: dict[str, Any],
    label: str,
    choice: str | None,
    codes: list[str],
    presence: str,
    *,
    blockers: list[str] | None = None,
    order_hint: float | None = None,
    page: int | None = None,
    repetitive: bool | None = None,
) -> PackRow:
    del options
    fallback = row["content"] if not row["options"] else None
    notation, pattern, fidelity, separator, max_length, _value = _format_for(
        tag, global_fields, fallback
    )
    row_blockers = list(blockers or [])
    value_less = bool(notation) and is_value_less(notation)
    if value_less:
        pattern, fidelity = "", "EXACT"
    if qualifier is None and "QUALIFIER_EVIDENCE_MISSING" in row_blockers:
        pattern = None
        fidelity = "PARTIAL"
    if fidelity != "EXACT":
        row_blockers.append("FORMAT_FIDELITY_PARTIAL")
    input_kind = "TEXT"
    if pattern:
        try:
            input_kind = input_kind_for(compile_format(notation), codes=bool(codes))
        except FormatUnsupported:
            input_kind = "TEXT"
    elif codes:
        input_kind = "SELECT"
    return PackRow(
        row_id=_row_id(message_type, row["sequencePath"], tag, qualifier),
        sequence_path=row["sequencePath"],
        tag=tag,
        qualifier=qualifier,
        presence=presence,
        format=notation,
        format_pattern=pattern,
        format_fidelity=fidelity,
        qualifier_separator=separator,
        display_name=(label or tag).strip()[:80],
        technical_name=notation or tag,
        allowed_codes=list(codes),
        input_kind=input_kind,
        max_length=max_length,
        choice_group=choice,
        repetitive=bool(repetitive if repetitive is not None else row["repetitive"]),
        order=order_hint if order_hint is not None else float(row["number"]),
        evidence="SWIFT_MRG_FORMAT_SPECIFICATION",
        page=page or row.get("page"),
        blockers=row_blockers,
        value_less=value_less,
    )


# -- reconciliation ------------------------------------------------------------------------------


def _reconcile(
    sequences: list[PackSequence],
    rows: list[PackRow],
    prowide: Any,
    mrg: MrgStructureArtifact,
) -> dict[str, Any]:
    """Compare the guide's structure with Prowide's, per sequence and per field.

    Two releases are compared (the guide's against SR2025), so a difference is a
    RELEASE_CHANGE or a SOURCE_MODEL_DIFFERENCE — classified, never resolved. A CONFLICT
    verdict is reserved for two sources of the *same* release disagreeing.
    """
    same_release = mrg.release == PROWIDE_RELEASE
    differ = "CONFLICT" if same_release else "RELEASE_CHANGE"
    prowide_sequences = {seq.path: seq for seq in prowide.sequences if seq.path != "ROOT"}
    sequence_verdicts: list[dict[str, Any]] = []
    for sequence in sequences:
        other = prowide_sequences.get(sequence.path)
        if other is None:
            verdict = "SOURCE_MODEL_DIFFERENCE"
        else:
            presence = "MANDATORY" if sequence.min_occurs else "OPTIONAL"
            mine = f"{presence}{'/R' if sequence.max_occurs > 1 else ''}"
            theirs = f"{other.presence.value}{'/R' if other.repeatable else ''}"
            verdict = "MATCH" if mine == theirs else differ
        sequence_verdicts.append({"path": sequence.path, "code": sequence.code, "verdict": verdict})
    for path in sorted(set(prowide_sequences) - {s.path for s in sequences}):
        sequence_verdicts.append(
            {
                "path": path,
                "code": prowide_sequences[path].code,
                "verdict": "SOURCE_MODEL_DIFFERENCE",
            }
        )
    prowide_fields: dict[tuple[str, str], Any] = {}
    for group in prowide.field_groups:
        prowide_fields[(group.sequence_path, group.field_number)] = group
    field_verdicts: dict[str, int] = defaultdict(int)
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row.sequence_path, row.tag[:2])
        if key in seen:
            continue
        seen.add(key)
        group = prowide_fields.get(key)
        if group is None:
            field_verdicts["SOURCE_MODEL_DIFFERENCE"] += 1
            continue
        mandatory_any = any(
            r.presence == "MANDATORY" for r in rows if (r.sequence_path, r.tag[:2]) == key
        )
        theirs = group.presence.value == "MANDATORY"
        field_verdicts["MATCH" if mandatory_any == theirs else differ] += 1
    for key in set(prowide_fields) - seen:
        if key[1] in {"16", "ROOT"}:
            continue
        field_verdicts["SOURCE_MODEL_DIFFERENCE"] += 1
    return {
        "comparedAgainst": f"PROWIDE_{PROWIDE_RELEASE}",
        "sameRelease": same_release,
        "sequences": sequence_verdicts,
        "fieldVerdictCounts": dict(sorted(field_verdicts.items())),
        "conflict": any(item["verdict"] == "CONFLICT" for item in sequence_verdicts)
        or field_verdicts.get("CONFLICT", 0) > 0,
    }


# -- gates -------------------------------------------------------------------------------------


def run_mt_gates(pack: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Load → sample → validate → compose → parse → round trip, through the ordinary engine."""
    from app.profiles.loader import profiles
    from app.studio.models import FieldInput
    from app.studio.mt.generator import mt_generator
    from app.studio.mt.parser import MtImportError, parse_message

    gates: dict[str, dict[str, Any]] = {}
    blockers: list[str] = []

    def fail(name: str, detail: str, blocker: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
        gates[name] = {"passed": False, "detail": detail[:300]}
        blockers.append(blocker)
        return gates, blockers

    try:
        specification = load_mt_pack_dict(pack)
    except Exception as error:  # noqa: BLE001 - the gate reports, never raises
        return fail("LOAD", f"{type(error).__name__}: {error}", "STRUCTURE_COMPILATION_FAILED")
    gates["LOAD"] = {
        "passed": True,
        "detail": f"{len(specification.sequences)} sequence(s), {len(specification.fields)} row(s)",
    }
    if any("QUALIFIER_EVIDENCE_MISSING" in item.get("blockers", []) for item in pack["fields"]):
        gates["SAMPLE"] = {
            "passed": False,
            "detail": "generic fields without qualifier evidence cannot be sampled",
        }
        blockers.append("QUALIFIER_EVIDENCE_MISSING")
        return gates, blockers

    # Sample: one value per mandatory row (first member of each choice group).
    inputs: list[FieldInput] = []
    seen_groups: set[str] = set()
    for row in pack["fields"]:
        if row["presence"] != "MANDATORY" or row.get("valueLess"):
            continue
        group = row.get("choiceGroup")
        if group:
            parent = str(group).rsplit("/", 1)[0]
            if parent in seen_groups:
                continue
            seen_groups.add(parent)
        try:
            value = synthetic_value(row["format"], codes=row.get("allowedCodes") or None)
        except FormatUnsupported:
            return fail(
                "SAMPLE",
                f"no synthetic value for {row['rowId']} ({row['format']})",
                "FORMAT_FIDELITY_PARTIAL",
            )
        if not value:
            return fail(
                "SAMPLE", f"empty synthetic value for {row['rowId']}", "FORMAT_FIDELITY_PARTIAL"
            )
        inputs.append(FieldInput(id=row["rowId"], occurrence=1, value=value))
    gates["SAMPLE"] = {"passed": True, "detail": f"{len(inputs)} mandatory value(s)"}

    profile = profiles.get("BASE_DEMO_V1")
    build = mt_generator.build(
        specification.message_type, profile, inputs, want_fin=True, specification=specification
    )
    if build.errors:
        return fail(
            "VALIDATE",
            "; ".join(f"{issue.rule_id}: {issue.message}" for issue in build.errors[:5]),
            "MESSAGE_GENERATION_NOT_READY",
        )
    gates["VALIDATE"] = {"passed": True, "detail": "no findings"}
    gates["COMPOSE"] = {
        "passed": True,
        "detail": f"{len(build.block_4)} bytes; FIN {'available' if build.fin else 'unavailable'}",
    }
    try:
        parsed = parse_message(build.block_4, specification=specification)
    except MtImportError as error:
        return fail("PARSE", error.issue.message, "ROUND_TRIP_FAILED")
    if parsed.errors:
        return fail(
            "PARSE",
            "; ".join(f"{issue.rule_id}: {issue.message}" for issue in parsed.errors[:5]),
            "ROUND_TRIP_FAILED",
        )
    gates["PARSE"] = {"passed": True, "detail": f"{len(parsed.fields)} field(s) read back"}
    rebuilt = mt_generator.build(
        specification.message_type,
        profile,
        parsed.fields,
        want_fin=False,
        specification=specification,
    )
    if rebuilt.block_4 != build.block_4:
        return fail("ROUND_TRIP", "Compose(Parse(Compose(v))) differs", "ROUND_TRIP_FAILED")
    gates["ROUND_TRIP"] = {"passed": True, "detail": "identical"}
    return gates, blockers


def _readiness(gates: dict[str, dict[str, Any]], blockers: list[str]) -> Readiness:
    if not gates.get("LOAD", {}).get("passed"):
        return Readiness.KNOWLEDGE_ONLY
    if "QUALIFIER_EVIDENCE_MISSING" in blockers or "STRUCTURE_SOURCE_CONFLICT" in blockers:
        return Readiness.STRUCTURE_AVAILABLE
    if all(gates.get(name, {}).get("passed") for name in ("SAMPLE", "VALIDATE", "COMPOSE")):
        if all(gates.get(name, {}).get("passed") for name in ("PARSE", "ROUND_TRIP")):
            return Readiness.GENERATION_READY
        return Readiness.STRUCTURE_VERIFIED
    return Readiness.STRUCTURE_AVAILABLE
