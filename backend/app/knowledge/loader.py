from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

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
from app.specifications.manifest import ManifestIndex, manifest_index


def knowledge_id_for(
    message_type: str,
    sequence_path: str,
    field_tag: str,
    qualifier: str | None,
) -> str:
    safe_sequence = sequence_path.replace("/", "-")
    return f"{message_type}-{safe_sequence}-{field_tag}-{qualifier or 'NONE'}"


class TagKnowledgeRepository:
    def __init__(
        self,
        config_dir: Path | None = None,
        profile_repository: ProfileRepository | None = None,
        manifest: ManifestIndex | None = None,
    ) -> None:
        self._config_dir = (
            config_dir or Path(__file__).resolve().parents[2] / "config" / "knowledge"
        )
        self._profiles = profile_repository or profiles
        self._manifest = manifest or manifest_index()
        self._records, self._overlays = self._load()

    def _load(
        self,
    ) -> tuple[
        dict[str, TagKnowledge],
        dict[tuple[str, str], ProfileKnowledgeOverlay],
    ]:
        manifest = self._manifest
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
                    # The manifest is the single authority for which messages exist, who
                    # owns them, and which sequences they have. A record referencing a
                    # message or sequence the manifest does not declare is a configuration
                    # error, reported at load — never a silently ignored row.
                    if not manifest.known(message_type):
                        raise ValueError(
                            f"Knowledge record names a message the specification manifest "
                            f"does not declare: {message_type}"
                        )
                    manifest_message = manifest.get(message_type)
                    if manifest_message.workflow_module != definition.workflow_module:
                        raise ValueError(
                            f"{message_type} belongs to {manifest_message.workflow_module}, "
                            f"not {definition.workflow_module}"
                        )
                    if definition.sequence_path not in manifest_message.sequence_paths:
                        raise ValueError(
                            f"{message_type} has no sequence {definition.sequence_path}; "
                            f"the manifest declares {', '.join(manifest_message.sequence_paths)}"
                        )
                    knowledge_id = knowledge_id_for(
                        message_type,
                        definition.sequence_path,
                        definition.field_tag,
                        definition.qualifier,
                    )
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
        by_message_qualifier: dict[tuple[str, str], list[TagKnowledge]] = defaultdict(list)
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

    def _validate_coverage(self, records: dict[str, TagKnowledge]) -> None:
        """Every manifest message must have field records; an empty message is a mistake.

        The per-field signature list this used to check lived in Python and duplicated the
        configuration it guarded, which meant adding a field was a code change despite the
        repository's own rule that it must not be. Field-level drift is now guarded where
        the fields are defined — the manifest sequence check at load, the golden fixtures,
        and the studio suite.
        """
        covered = {record.message_type for record in records.values()}
        missing = [item for item in self._manifest.message_types() if item not in covered]
        if missing:
            raise ValueError(
                "Manifest messages with no tag knowledge records: " + ", ".join(missing)
            )

    def list_messages(self) -> list[KnowledgeMessageSummary]:
        grouped: dict[tuple[str, WorkflowModuleId, str], int] = defaultdict(int)
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
                grouped.items(), key=lambda item: item[0][0]
            )
        ]

    def list_records(
        self,
        *,
        message_type: str | None = None,
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
        message_type: str,
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
