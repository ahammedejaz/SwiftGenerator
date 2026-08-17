from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from app.domain.enums import MessageType
from app.knowledge.code_lists import CODE_LIST_FILENAME, code_lists
from app.knowledge.models import (
    EffectiveTagKnowledge,
    InputKind,
    KnowledgeDependencyResponse,
    KnowledgeMessageSummary,
    PresenceRule,
    ProfileKnowledgeOverlay,
    ReviewStatus,
    TagKnowledge,
    TagKnowledgeDefinition,
    WorkflowModuleId,
)
from app.knowledge.presentation import derive_input_kind
from app.profiles.loader import ProfileRepository, profiles

KNOWN_MESSAGE_OWNERS: dict[MessageType, WorkflowModuleId] = {
    MessageType.MT530: WorkflowModuleId.SETTLEMENT_COMMAND,
    MessageType.MT537: WorkflowModuleId.PENALTIES,
    **{
        message_type: WorkflowModuleId.SETTLEMENT
        for message_type in (
            MessageType.MT540,
            MessageType.MT541,
            MessageType.MT542,
            MessageType.MT543,
            MessageType.MT544,
            MessageType.MT545,
            MessageType.MT546,
            MessageType.MT547,
            MessageType.MT548,
        )
    },
    **{
        message_type: WorkflowModuleId.CORPORATE_ACTIONS
        for message_type in (
            MessageType.MT564,
            MessageType.MT565,
            MessageType.MT566,
            MessageType.MT567,
            MessageType.MT568,
        )
    },
}

#: A settlement party may be identified by a BIC (option P) or by a proprietary scheme
#: identifier (option R). Both are configured for every party, because which one applies is
#: the caller's business decision, not the platform's.
_SETTLEMENT_PARTIES = {
    (sequence, f"95{option}", qualifier)
    for sequence in ("E",)
    for option in ("P", "R")
    for qualifier in ("PSET", "DEAG", "REAG")
}
_INSTRUCTION_FIELDS = {
    ("A", "20C", "SEME"),
    ("A", "20C", "PREV"),
    ("A", "20C", "COMM"),
    ("A", "23G", None),
    ("B", "98A", "TRAD"),
    ("B", "98A", "SETT"),
    ("B", "35B", None),
    ("B", "36B", "SETT"),
    ("C", "97A", "SAFE"),
    # 22F::SETR carries the type of settlement transaction and belongs to Settlement
    # Details only. It was previously configured in Trade Details as well, carrying BUY or
    # SELL, and in Settlement Details carrying RECE or DELI — neither of which is a
    # transaction type. Receive versus deliver is carried by the message type.
    ("E", "22F", "SETR"),
    *_SETTLEMENT_PARTIES,
}
_CONFIRMATION_FIELDS = {
    ("A", "20C", "SEME"),
    ("A", "20C", "RELA"),
    ("A", "20C", "COMM"),
    ("A", "23G", None),
    ("B", "98A", "ESET"),
    ("B", "35B", None),
    ("B", "36B", "ESTT"),
    ("B", "22F", "STCO"),
    ("C", "97A", "SAFE"),
    *_SETTLEMENT_PARTIES,
}
_STATUS_FIELDS = {
    ("A", "20C", "SEME"),
    ("A", "20C", "RELA"),
    ("A", "23G", None),
    ("A1", "13A", "LINK"),
    ("D", "25D", "SETT"),
    ("D", "24B", "PEND"),
    ("D", "24B", "REJT"),
    ("D", "24B", "MACH"),
    ("D", "24B", "NMAT"),
    ("D", "24B", "CAND"),
    ("D", "24B", "CANR"),
    ("D", "70D", "REAS"),
}
_MT530_FIELDS = {
    ("A", "20C", "SEME"),
    ("A", "23G", None),
    ("A", "97A", "SAFE"),
    ("B", "20C", "PREV"),
    ("B", "22F", "PRIR"),
}
_MT537_FIELDS = {
    ("A", "28E", None),
    ("A", "20C", "SEME"),
    ("A", "23G", None),
    ("A", "98A", "STAT"),
    ("A", "22H", "STST"),
    ("A", "97A", "SAFE"),
    ("A", "17B", "ACTI"),
    ("D", "22F", "CODE"),
    ("D1", "11A", "PECU"),
    ("D1", "98A", "DACO"),
    ("D1", "95R", "ASDP"),
    ("D1", "22F", "TRCA"),
    ("D1a", "95R", "REPA"),
    ("D1a", "22F", "TRCA"),
    ("D1a", "19A", "AGNT"),
    ("D1a1", "20C", "PREF"),
    ("D1a1", "20C", "PCOM"),
    ("D1a1", "20C", "PPRF"),
    ("D1a1", "22H", "PNTP"),
    ("D1a1", "25D", "PNST"),
    ("D1a1", "19A", "AMCO"),
    ("D1a1", "99A", "DAAC"),
    ("D1a1B", "20C", "RELA"),
}
_MT564_FIELDS = {
    ("A", "20C", "CORP"),
    ("A", "20C", "SEME"),
    ("A", "23G", None),
    ("A", "22F", "CAEV"),
    ("A", "22F", "CAMV"),
    ("A", "25D", "PROC"),
    ("B", "35B", None),
    ("B1", "97A", "SAFE"),
    ("B", "93B", "ELIG"),
    ("C", "98A", "PAYD"),
    ("E", "13A", "CAON"),
    ("E", "22F", "CAOP"),
    ("E", "17B", "DFLT"),
    ("E", "98A", "RDDT"),
}
_MT565_FIELDS = {
    ("A", "20C", "CORP"),
    ("A", "20C", "SEME"),
    ("A", "23G", None),
    ("A", "22F", "CAEV"),
    ("A1", "20C", "RELA"),
    ("B", "35B", None),
    ("B1", "97A", "SAFE"),
    ("D", "13A", "CAON"),
    ("D", "22F", "CAOP"),
    ("D", "36B", "QINS"),
}
_MT566_FIELDS = {
    ("A", "20C", "CORP"),
    ("A", "20C", "SEME"),
    ("A", "23G", None),
    ("A", "22F", "CAEV"),
    ("A1", "20C", "RELA"),
    ("B", "97A", "SAFE"),
    ("B", "35B", None),
    ("B", "93B", "ELIG"),
    ("D", "13A", "CAON"),
    ("D", "22H", "CAOP"),
    ("D2", "22H", "CRDB"),
    ("D2", "19B", "PSTA"),
    ("D2", "98A", "POST"),
}
_MT567_FIELDS = {
    ("A", "20C", "CORP"),
    ("A", "20C", "SEME"),
    ("A", "23G", None),
    ("A", "22F", "CAEV"),
    ("A1", "20C", "RELA"),
    ("C", "25D", "IPRC"),
    ("C", "25D", "CPRC"),
    ("C1", "24B", "IPRC"),
    ("C1", "24B", "CPRC"),
}
_MT568_FIELDS = {
    ("A", "20C", "CORP"),
    ("A", "20C", "SEME"),
    ("A", "23G", None),
    ("A", "22F", "CAEV"),
    ("A1", "20C", "RELA"),
    ("C", "70E", "ADTX"),
}
KNOWN_FIELD_SIGNATURES: dict[MessageType, set[tuple[str, str, str | None]]] = {
    MessageType.MT530: _MT530_FIELDS,
    MessageType.MT537: _MT537_FIELDS,
    MessageType.MT540: set(_INSTRUCTION_FIELDS),
    MessageType.MT541: {*_INSTRUCTION_FIELDS, ("E", "19A", "SETT")},
    MessageType.MT542: set(_INSTRUCTION_FIELDS),
    MessageType.MT543: {*_INSTRUCTION_FIELDS, ("E", "19A", "SETT")},
    MessageType.MT544: set(_CONFIRMATION_FIELDS),
    MessageType.MT545: {*_CONFIRMATION_FIELDS, ("B", "19A", "ESTT")},
    MessageType.MT546: set(_CONFIRMATION_FIELDS),
    MessageType.MT547: {*_CONFIRMATION_FIELDS, ("B", "19A", "ESTT")},
    MessageType.MT548: _STATUS_FIELDS,
    MessageType.MT564: _MT564_FIELDS,
    MessageType.MT565: _MT565_FIELDS,
    MessageType.MT566: _MT566_FIELDS,
    MessageType.MT567: _MT567_FIELDS,
    MessageType.MT568: _MT568_FIELDS,
}


def knowledge_id_for(
    message_type: MessageType | str,
    sequence_path: str,
    field_tag: str,
    qualifier: str | None,
) -> str:
    message_value = message_type.value if isinstance(message_type, MessageType) else message_type
    safe_sequence = sequence_path.replace("/", "-")
    return f"{message_value}-{safe_sequence}-{field_tag}-{qualifier or 'NONE'}"


class TagKnowledgeRepository:
    def __init__(
        self,
        config_dir: Path | None = None,
        profile_repository: ProfileRepository | None = None,
    ) -> None:
        self._config_dir = (
            config_dir or Path(__file__).resolve().parents[2] / "config" / "knowledge"
        )
        self._profiles = profile_repository or profiles
        self._records, self._overlays = self._load()

    def _load(
        self,
    ) -> tuple[
        dict[str, TagKnowledge],
        dict[tuple[str, str], ProfileKnowledgeOverlay],
    ]:
        records: dict[str, TagKnowledge] = {}
        for path in sorted(self._config_dir.glob("*.yaml")):
            # Shared code lists live beside the records but are not records themselves.
            if path.name == CODE_LIST_FILENAME:
                continue
            payload = self._read_yaml(path)
            definitions = payload.get("records")
            if not isinstance(definitions, list):
                raise ValueError(f"Knowledge file {path.name} must contain a records list")
            for raw in definitions:
                definition = TagKnowledgeDefinition.model_validate(raw)
                definition = self._resolve_code_list(definition, path.name)
                definition = self._derive_presentation(definition)
                for message_type in definition.message_types:
                    expected_owner = KNOWN_MESSAGE_OWNERS.get(message_type)
                    if expected_owner is None or expected_owner != definition.workflow_module:
                        raise ValueError(
                            f"Unknown or incorrectly owned message type {message_type.value}"
                        )
                    knowledge_id = knowledge_id_for(
                        message_type,
                        definition.sequence_path,
                        definition.field_tag,
                        definition.qualifier,
                    )
                    signature = (
                        definition.sequence_path,
                        definition.field_tag,
                        definition.qualifier,
                    )
                    known_signatures = KNOWN_FIELD_SIGNATURES.get(message_type)
                    if known_signatures is not None and signature not in known_signatures:
                        raise ValueError(f"Unknown supported field signature: {knowledge_id}")
                    if knowledge_id in records:
                        raise ValueError(f"Duplicate knowledge ID: {knowledge_id}")
                    payload_data = definition.model_dump(mode="python", exclude={"message_types"})
                    record = TagKnowledge(
                        knowledge_id=knowledge_id,
                        message_type=message_type,
                        **payload_data,
                    )
                    option = record.field_tag[-1]
                    if option not in record.supported_options:
                        raise ValueError(
                            f"{knowledge_id} does not allow emitted field option {option}"
                        )
                    if record.source.review_status != ReviewStatus.VERIFIED:
                        raise ValueError(f"Enabled knowledge must be verified: {knowledge_id}")
                    records[knowledge_id] = record

        overlays: dict[tuple[str, str], ProfileKnowledgeOverlay] = {}
        overlay_dir = self._config_dir / "overlays"
        for path in sorted(overlay_dir.glob("*.yaml")):
            payload = self._read_yaml(path)
            for raw in payload.get("overlays", []):
                overlay = ProfileKnowledgeOverlay.model_validate(raw)
                key = (overlay.profile_id, overlay.knowledge_id)
                if key in overlays:
                    raise ValueError(f"Duplicate knowledge overlay: {key}")
                overlay_record = records.get(overlay.knowledge_id)
                if overlay_record is None:
                    raise ValueError(
                        f"Overlay references unknown knowledge: {overlay.knowledge_id}"
                    )
                profile = self._profiles.get(overlay.profile_id)
                if profile.version != overlay.profile_version:
                    raise ValueError(f"Overlay profile version mismatch: {overlay.profile_id}")
                self._validate_overlay(overlay_record, overlay)
                overlays[key] = overlay

        if not records:
            raise RuntimeError("No tag knowledge records are configured")
        self._validate_dependencies(records)
        self._validate_coverage(records)
        return records, overlays

    @staticmethod
    def _resolve_code_list(
        definition: TagKnowledgeDefinition, filename: str
    ) -> TagKnowledgeDefinition:
        """Fill ``allowedCodes`` from the named shared list, or prove the two agree.

        Declaring both is allowed and deliberately checked rather than silently preferred: a
        record that names a list and then restates a different set of codes is a mistake,
        and load is the only useful moment to say so.
        """
        if definition.code_list is None:
            return definition
        if not code_lists.known(definition.code_list):
            raise ValueError(f"{filename} references unknown code list {definition.code_list}")
        codes = code_lists.get(definition.code_list).codes
        if definition.allowed_codes and definition.allowed_codes != codes:
            raise ValueError(
                f"{filename}: {definition.field_tag}/{definition.qualifier} declares codes "
                f"that differ from code list {definition.code_list}"
            )
        return definition.model_copy(update={"allowed_codes": list(codes)})

    @staticmethod
    def _derive_presentation(definition: TagKnowledgeDefinition) -> TagKnowledgeDefinition:
        """Fill the control from the tag and the field option, unless the record states one."""
        if definition.input_kind is not InputKind.TEXT:
            return definition
        return definition.model_copy(
            update={
                "input_kind": derive_input_kind(
                    definition.field_tag,
                    allowed_codes=definition.allowed_codes,
                    literal_prefix=definition.literal_prefix,
                    identifier_types=definition.identifier_types,
                )
            }
        )

    @staticmethod
    def _read_yaml(path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as source:
            payload = yaml.safe_load(source)
        if not isinstance(payload, dict):
            raise ValueError(f"Knowledge file {path.name} must contain an object")
        return payload

    @staticmethod
    def _validate_overlay(record: TagKnowledge, overlay: ProfileKnowledgeOverlay) -> None:
        if overlay.source.review_status != ReviewStatus.VERIFIED:
            raise ValueError("Profile knowledge overlays must be verified")
        if overlay.allowed_options and not set(overlay.allowed_options).issubset(
            record.supported_options
        ):
            raise ValueError(f"Overlay broadens allowed options: {overlay.knowledge_id}")
        if overlay.allowed_codes and not set(overlay.allowed_codes).issubset(record.allowed_codes):
            raise ValueError(f"Overlay broadens allowed codes: {overlay.knowledge_id}")
        if record.presence == PresenceRule.MANDATORY and overlay.presence != PresenceRule.MANDATORY:
            raise ValueError(f"Overlay weakens mandatory presence: {overlay.knowledge_id}")

    @staticmethod
    def _validate_dependencies(records: dict[str, TagKnowledge]) -> None:
        by_message_qualifier: dict[tuple[MessageType, str], list[TagKnowledge]] = defaultdict(list)
        for record in records.values():
            if record.qualifier:
                by_message_qualifier[(record.message_type, record.qualifier)].append(record)
        for record in records.values():
            for qualifier in {
                *record.depends_on,
                *record.required_with,
                *record.conflicts_with,
                *record.related_fields,
            }:
                if not by_message_qualifier.get((record.message_type, qualifier)):
                    raise ValueError(
                        f"Broken dependency {qualifier} in knowledge {record.knowledge_id}"
                    )

    @staticmethod
    def _validate_coverage(records: dict[str, TagKnowledge]) -> None:
        actual = {
            (record.message_type, record.sequence_path, record.field_tag, record.qualifier)
            for record in records.values()
        }
        for message_type, signatures in KNOWN_FIELD_SIGNATURES.items():
            missing = {
                (message_type, sequence, tag, qualifier)
                for sequence, tag, qualifier in signatures
                if (message_type, sequence, tag, qualifier) not in actual
            }
            if missing:
                rendered = ", ".join(knowledge_id_for(*item) for item in sorted(missing, key=str))
                raise ValueError(f"Missing tag knowledge coverage: {rendered}")

    def list_messages(self) -> list[KnowledgeMessageSummary]:
        grouped: dict[tuple[MessageType, WorkflowModuleId, str], int] = defaultdict(int)
        for record in self._records.values():
            grouped[(record.message_type, record.workflow_module, record.knowledge_version)] += 1
        return [
            KnowledgeMessageSummary(
                message_type=message_type,
                workflow_module=module,
                record_count=count,
                knowledge_version=version,
            )
            for (message_type, module, version), count in sorted(
                grouped.items(), key=lambda item: item[0][0].value
            )
        ]

    def list_records(
        self,
        *,
        message_type: MessageType | None = None,
        sequence: str | None = None,
        tag: str | None = None,
        qualifier: str | None = None,
        workflow_module: WorkflowModuleId | None = None,
        presence: PresenceRule | None = None,
        profile_id: str = "BASE_DEMO_V1",
    ) -> list[EffectiveTagKnowledge]:
        records = self._records.values()
        filtered = [
            record
            for record in records
            if (message_type is None or record.message_type == message_type)
            and (sequence is None or record.sequence_path == sequence)
            and (tag is None or record.field_tag == tag.upper())
            and (qualifier is None or record.qualifier == qualifier.upper())
            and (workflow_module is None or record.workflow_module == workflow_module)
            and (presence is None or record.presence == presence)
        ]
        return [self.effective(record.knowledge_id, profile_id) for record in filtered]

    def get(self, knowledge_id: str) -> TagKnowledge:
        try:
            return self._records[knowledge_id]
        except KeyError as exc:
            raise KeyError(f"Unknown tag knowledge: {knowledge_id}") from exc

    def effective(self, knowledge_id: str, profile_id: str) -> EffectiveTagKnowledge:
        record = self.get(knowledge_id)
        profile = self._profiles.get(profile_id)
        overlay = self._overlays.get((profile_id, knowledge_id))
        requirements = set(profile.requirements_for(record.message_type))
        required_by_profile = _normalise_business_path(record.business_path) in {
            _normalise_business_path(path) for path in requirements
        }
        presence = PresenceRule.MANDATORY if required_by_profile else record.presence
        if overlay and overlay.presence:
            presence = overlay.presence
        return EffectiveTagKnowledge(
            record=record,
            profile_id=profile.profile_id,
            profile_version=profile.version,
            effective_presence=presence,
            effective_options=(
                overlay.allowed_options
                if overlay and overlay.allowed_options
                else record.supported_options
            ),
            effective_codes=(
                overlay.allowed_codes if overlay and overlay.allowed_codes else record.allowed_codes
            ),
            client_explanation=overlay.client_explanation if overlay else None,
            effective_business_question=(
                overlay.business_question
                if overlay and overlay.business_question
                else record.business_question
            ),
            profile_common_mistakes=overlay.common_mistakes if overlay else [],
            profile_override_applied=bool(overlay or required_by_profile),
        )

    def search(
        self, query: str, *, profile_id: str = "BASE_DEMO_V1", limit: int = 25
    ) -> list[EffectiveTagKnowledge]:
        needle = " ".join(query.casefold().split())
        if not needle:
            return []
        scored: list[tuple[int, TagKnowledge]] = []
        for record in self._records.values():
            values = [
                record.knowledge_id,
                record.field_tag,
                record.qualifier or "",
                record.display_name,
                record.business_meaning,
                record.technical_meaning,
                *record.search_terms,
            ]
            haystack = " ".join(values).casefold()
            if needle in haystack:
                score = 3 if needle in {value.casefold() for value in values[:4]} else 1
                scored.append((score, record))
        return [
            self.effective(record.knowledge_id, profile_id)
            for _, record in sorted(scored, key=lambda item: (-item[0], item[1].knowledge_id))[
                :limit
            ]
        ]

    def dependencies(self, knowledge_id: str, profile_id: str) -> KnowledgeDependencyResponse:
        record = self.get(knowledge_id)

        def resolve(qualifiers: list[str]) -> list[EffectiveTagKnowledge]:
            return [
                self.effective(item.knowledge_id, profile_id)
                for item in self._records.values()
                if item.message_type == record.message_type and item.qualifier in qualifiers
            ]

        return KnowledgeDependencyResponse(
            knowledge_id=knowledge_id,
            depends_on=resolve(record.depends_on),
            required_with=resolve(record.required_with),
            conflicts_with=resolve(record.conflicts_with),
            related_fields=resolve(record.related_fields),
        )

    def find_for_rendered_field(
        self,
        message_type: MessageType,
        sequence: str,
        tag: str,
        qualifier: str | None,
        profile_id: str,
    ) -> EffectiveTagKnowledge:
        return self.effective(knowledge_id_for(message_type, sequence, tag, qualifier), profile_id)


def _normalise_business_path(path: str) -> str:
    parts = path.replace("_", "").casefold().split(".")
    return ".".join(parts)


knowledge_repository = TagKnowledgeRepository()
