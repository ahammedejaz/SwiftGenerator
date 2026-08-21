"""Compile every discovered ISO 20022 XSD into a local MX Structure Pack.

Entirely the existing machinery: ``spec_engine.compile_schema`` reads the schema safely,
``spec_engine.validate_pack`` runs the six gates (registry load, sample, compose, source-XSD
validation, invalid variants rejected, round trip), and the pack written here is an
ordinary ``config/mx`` pack with a ``KNOWLEDGE_PREVIEW`` lane marker. The source schema is
copied beside it so runtime validation can use the supplied XSD itself.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from app.config import Settings
from app.knowledge_base import PACK_COMPILER_VERSION
from app.knowledge_base.db import KnowledgeDatabase
from app.knowledge_base.models import Readiness, SourceType, SyncProgress

XSD_CACHE_DIRNAME = "xsd"


def cached_xsd_path(cache_dir: Path, checksum: str) -> Path:
    return cache_dir / XSD_CACHE_DIRNAME / f"{checksum}.xsd"


def compile_mx_structures(
    settings: Settings, database: KnowledgeDatabase, pack_dir: Path, report: SyncProgress
) -> None:
    from app.knowledge_base.paths import resolve_project_path

    cache_dir = resolve_project_path(settings.knowledge_source_cache_dir)
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "xsd").mkdir(parents=True, exist_ok=True)
    existing = _existing(database)
    for source in database.sources():
        if source.source_type is not SourceType.ISO20022_XSD or not source.message_version:
            continue
        version = source.message_version
        identity = hashlib.sha256(
            f"{PACK_COMPILER_VERSION}|{version}|{source.checksum}".encode()
        ).hexdigest()
        previous = existing.get(version)
        if (
            previous is not None
            and previous["identity"] == identity
            and Path(previous["pack_path"] or "").exists()
        ):
            report.structures_reused += 1
            continue
        xsd_path = cached_xsd_path(cache_dir, source.checksum)
        if not xsd_path.exists():
            report.structures_failed += 1
            _record(
                database,
                source.message_type or version,
                version,
                None,
                None,
                Readiness.KNOWLEDGE_ONLY,
                ["STRUCTURE_SOURCE_MISSING"],
                {},
                [source.source_id],
                [source.checksum],
                {"identity": identity},
            )
            continue
        try:
            compiled, gates, blockers, readiness = compile_mx_pack(xsd_path)
        except Exception as error:  # noqa: BLE001 - recorded per message, never fatal
            report.structures_failed += 1
            report.failures.append(
                {
                    "path": source.source_id,
                    "code": "STRUCTURE_COMPILATION_FAILED",
                    "detail": f"{type(error).__name__}: {str(error)[:160]}",
                }
            )
            _record(
                database,
                source.message_type or version,
                version,
                None,
                None,
                Readiness.KNOWLEDGE_ONLY,
                ["STRUCTURE_COMPILATION_FAILED"],
                {},
                [source.source_id],
                [source.checksum],
                {"identity": identity, "error": type(error).__name__},
            )
            continue
        pack_path = pack_dir / f"{version}.yaml"
        pack_path.write_text(compiled["yaml"], encoding="utf-8")
        shutil.copyfile(xsd_path, pack_dir / "xsd" / f"{version}.xsd")
        report.structures_compiled += 1
        _record(
            database,
            compiled["messageType"],
            version,
            str(pack_path),
            compiled["packChecksum"],
            readiness,
            blockers,
            gates,
            [source.source_id],
            [source.checksum],
            {
                "identity": identity,
                "name": compiled["name"],
                "businessArea": compiled["businessArea"],
                "leafCount": compiled["leafCount"],
            },
        )


def compile_mx_pack(
    xsd_path: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[str], Readiness]:
    from app.spec_engine.gates import validate_pack
    from app.spec_engine.pipeline import compile_schema

    compiled = compile_schema(xsd_path, source_type="OPERATOR_SUPPLIED_XSD")
    raw = yaml.safe_load(compiled.yaml_text)
    if not isinstance(raw, dict):
        raise ValueError("compiler produced no pack")
    raw["lane"] = "KNOWLEDGE_PREVIEW"
    raw["capabilityStatement"] = (
        "XSD-backed structure; business rules, market practice and client rules are not "
        "established."
    )
    limitations = list(raw.get("limitations") or [])
    limitations.append(
        "Compiled from an operator-supplied schema; conformance is to that file, which the "
        "platform cannot verify is the genuine ISO 20022 artifact."
    )
    raw["limitations"] = limitations
    yaml_text = yaml.safe_dump(raw, sort_keys=False, allow_unicode=True, width=100)
    validation = validate_pack(yaml_text, compiled.version, xsd_path)
    gates = {
        "LOAD": {
            "passed": validation.registry_load.passed,
            "detail": validation.registry_load.detail,
        },
        "SAMPLE": {"passed": validation.sample.passed, "detail": validation.sample.detail},
        "COMPOSE": {"passed": validation.compose.passed, "detail": validation.compose.detail},
        "SOURCE_XSD": {
            "passed": validation.source_xsd.passed,
            "detail": validation.source_xsd.detail,
        },
        "INVALID_VARIANTS": {
            "passed": validation.invalid_variants.passed,
            "detail": validation.invalid_variants.detail,
        },
        "ROUND_TRIP": {
            "passed": validation.round_trip.passed,
            "detail": validation.round_trip.detail,
        },
    }
    blockers = [f"GATE_{name}_FAILED" for name, result in gates.items() if not result["passed"]]
    if validation.passed:
        readiness = Readiness.GENERATION_READY
    elif validation.registry_load.passed and validation.compose.passed:
        readiness = Readiness.STRUCTURE_VERIFIED
    elif validation.registry_load.passed:
        readiness = Readiness.STRUCTURE_AVAILABLE
    else:
        readiness = Readiness.KNOWLEDGE_ONLY
    pack_checksum = "sha256:" + hashlib.sha256(yaml_text.encode()).hexdigest()
    leaves = sum(1 for _ in _leaves(raw.get("structure", [])))
    return (
        {
            "yaml": yaml_text,
            "messageType": str(raw.get("messageType") or compiled.message_type),
            "version": compiled.version,
            "name": str(raw.get("name") or compiled.version),
            "businessArea": str(raw.get("businessArea") or "OTHER"),
            "packChecksum": pack_checksum,
            "leafCount": leaves,
        },
        gates,
        blockers,
        readiness,
    )


def _leaves(nodes: list[Any]) -> Any:
    for node in nodes:
        if isinstance(node, dict):
            children = node.get("children")
            if children:
                yield from _leaves(children)
            else:
                yield node


def _existing(database: KnowledgeDatabase) -> dict[str, dict[str, Any]]:
    with database.read() as connection:
        rows = connection.execute(
            "SELECT release, pack_path, detail FROM knowledge_structure WHERE format = 'MX'"
        ).fetchall()
    return {
        str(row["release"]): {
            "pack_path": row["pack_path"],
            "identity": json.loads(row["detail"]).get("identity"),
        }
        for row in rows
    }


def _record(
    database: KnowledgeDatabase,
    message_type: str,
    version: str,
    pack_path: str | None,
    pack_checksum: str | None,
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
            VALUES ('MX', ?, ?, 'KNOWLEDGE_PREVIEW', ?, ?, 'OPERATOR_SUPPLIED_XSD',
                ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(format, message_type, release, lane) DO UPDATE SET
                pack_path = excluded.pack_path, pack_checksum = excluded.pack_checksum,
                readiness = excluded.readiness, blockers = excluded.blockers,
                gates = excluded.gates, compiler_version = excluded.compiler_version,
                source_ids = excluded.source_ids, source_checksums = excluded.source_checksums,
                detail = excluded.detail, updated_at = excluded.updated_at
            """,
            (
                message_type,
                version,
                pack_path,
                pack_checksum,
                readiness.value,
                json.dumps(blockers),
                json.dumps(gates, sort_keys=True),
                PACK_COMPILER_VERSION,
                json.dumps(source_ids),
                json.dumps(source_checksums),
                json.dumps(detail, sort_keys=True),
            ),
        )
