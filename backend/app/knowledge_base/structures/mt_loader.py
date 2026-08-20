"""Load a local MT Structure Pack into the runtime's own ``MessageSpecification``.

Runtime-safe: YAML in, the same pydantic types the configured registry produces out. It
never imports the compiler, Prowide tooling or the MRG reader.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from app.knowledge.models import InputKind, PresenceRule, RuleLayer, SourceType, WorkflowModuleId
from app.specifications.models import (
    CapabilityState,
    FieldSpecification,
    MessageSpecification,
    SequenceSpecification,
    SpecificationSource,
    VerificationMethod,
    VerificationStatus,
)

MT_PACK_VERSION = "mt-structure-pack/1"
PREVIEW_CAPABILITY_STATEMENT = (
    "Structure-backed test generation; complete semantic rules not established."
)


class MtPackError(ValueError):
    pass


def load_mt_pack_dict(pack: dict[str, Any]) -> MessageSpecification:
    if pack.get("packVersion") != MT_PACK_VERSION:
        raise MtPackError(f"unsupported pack version {pack.get('packVersion')!r}")
    message_type = str(pack["messageType"]).upper()
    release = str(pack.get("release") or "")
    sequences = [
        SequenceSpecification(
            path=str(item["path"]),
            code=str(item["code"]),
            parent_path=item.get("parentPath"),
            order=int(item["order"]),
            min_occurs=int(item.get("minOccurs", 0)),
            max_occurs=int(item.get("maxOccurs", 1)),
            insert_after_tag=item.get("insertAfterTag"),
            bracketed=bool(item.get("bracketed", True)),
            leading_tags=[str(tag) for tag in item.get("leadingTags", [])],
        )
        for item in pack.get("sequences", [])
    ]
    if not sequences:
        raise MtPackError(f"{message_type} pack declares no sequences")
    by_path = {sequence.path: sequence for sequence in sequences}
    verified_at = datetime.combine(
        datetime.fromisoformat(str(pack.get("compiledAt", "2026-01-01"))[:10]).date(),
        datetime.min.time(),
        tzinfo=UTC,
    )
    source_type_raw = str(pack.get("sourceType") or "PROWIDE_DERIVED_STRUCTURAL_EVIDENCE")
    source = SpecificationSource(
        source_type=(
            SourceType(source_type_raw)
            if source_type_raw in {item.value for item in SourceType}
            else SourceType.PROWIDE_DERIVED_STRUCTURAL_EVIDENCE
        ),
        source_reference=str(pack.get("sourceReference") or f"{message_type}-{release}-PACK"),
        standards_release=release,
        verification_status=VerificationStatus.UNVERIFIED,
        verified_at=verified_at,
        verification_method=VerificationMethod.SOURCE_IMPORT,
    )
    fields: list[FieldSpecification] = []
    for number, row in enumerate(pack.get("fields", []), start=1):
        sequence = by_path.get(str(row["sequencePath"]))
        if sequence is None:
            raise MtPackError(f"{row['rowId']} references unknown sequence {row['sequencePath']}")
        presence = PresenceRule(str(row.get("presence", "OPTIONAL")))
        input_kind_raw = str(row.get("inputKind", "TEXT"))
        input_kind = (
            InputKind(input_kind_raw)
            if input_kind_raw in {item.value for item in InputKind}
            else InputKind.TEXT
        )
        fields.append(
            FieldSpecification(
                row_id=str(row["rowId"]),
                row_number=number,
                message_type=message_type,
                workflow_module=WorkflowModuleId.KNOWLEDGE_PREVIEW,
                sequence_path=sequence.path,
                sequence_code=sequence.code,
                tag=str(row["tag"]),
                option=str(row.get("option") or row["tag"][2:] or ""),
                qualifier=row.get("qualifier"),
                business_path=str(row["businessPath"]),
                business_name=str(row.get("displayName") or row["tag"]),
                technical_name=str(row.get("technicalName") or row.get("format") or ""),
                presence=presence,
                min_occurs=1 if presence is PresenceRule.MANDATORY else 0,
                max_occurs=1,
                repeatable=False,
                format=str(row.get("format") or ""),
                allowed_options=[str(item) for item in row.get("allowedOptions", [])],
                allowed_codes=[str(item) for item in row.get("allowedCodes", [])],
                code_list=None,
                input_kind=input_kind,
                literal_prefix=row.get("literalPrefix"),
                identifier_types=[str(item) for item in row.get("identifierTypes", [])],
                choice_group=row.get("choiceGroup"),
                max_length=row.get("maxLength"),
                condition_expression=None,
                condition_explanation=row.get("conditionExplanation"),
                rule_layer=RuleLayer.BASE_STANDARD,
                knowledge_id=str(row["rowId"]),
                source=source,
                format_pattern=row.get("formatPattern"),
                qualifier_separator=str(row.get("qualifierSeparator") or "//"),
                structure_source=str(pack.get("structureSource") or ""),
                value_less=bool(row.get("valueLess", False)),
            )
        )
    return MessageSpecification(
        message_type=message_type,
        name=str(pack.get("name") or message_type),
        scope=str(pack.get("scope") or f"Structure compiled from {pack.get('structureSource')}."),
        short_description=str(pack.get("shortDescription") or pack.get("name") or message_type),
        capability=CapabilityState.PARTIAL,
        capability_explanation=str(pack.get("capabilityStatement") or PREVIEW_CAPABILITY_STATEMENT),
        workflow_module=WorkflowModuleId.KNOWLEDGE_PREVIEW,
        standards_release=release,
        registry_version=f"KNOWLEDGE_PREVIEW_{release}",
        authoritative_completeness_known=False,
        sequences=sequences,
        fields=fields,
        source=source,
        lane="KNOWLEDGE_PREVIEW",
        release=release or None,
        business_area=pack.get("businessArea"),
        structure_source=pack.get("structureSource"),
        capability_statement=str(pack.get("capabilityStatement") or PREVIEW_CAPABILITY_STATEMENT),
        limitations=[str(item) for item in pack.get("limitations", [])],
        pack_checksum=pack.get("packChecksum"),
    )


def load_mt_pack(path: Path) -> MessageSpecification:
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise MtPackError(f"{path.name} is not a pack")
    return load_mt_pack_dict(raw)
