from __future__ import annotations

import re
from datetime import date
from hashlib import sha256

from app.config import CONFIG_ROOT
from app.mapping.models import (
    AppliedMapping,
    ConversionReport,
    ConversionResponse,
    ConversionTarget,
    ConversionTargetsResponse,
    ConvertRequest,
    MappingIdentity,
    MappingKind,
    MappingOutput,
    MappingPack,
    MappingReviewState,
    MappingRule,
    MissingTarget,
    TransformName,
)
from app.mapping.registry import MappingRegistry, mapping_registry
from app.studio.catalogue import message_spec
from app.studio.models import ElementInput, FieldInput, GenerateRequest, Presence
from app.studio.service import studio_service


class MappingError(ValueError):
    pass


class MappingService:
    def __init__(self, registry: MappingRegistry | None = None) -> None:
        self._registry = registry or mapping_registry()

    def targets(self, source: MappingIdentity) -> ConversionTargetsResponse:
        targets = [self._target(pack) for pack in self._registry.targets(source)]
        return ConversionTargetsResponse(
            source=source,
            targets=targets,
            authority_note=(
                "No production-eligible mapping evidence is configured. Synthetic preview "
                "packs demonstrate the deterministic workflow only."
            ),
        )

    def convert(self, request: ConvertRequest, fields: list[FieldInput]) -> ConversionResponse:
        source = MappingIdentity(
            format=request.source_format,
            message_type=request.source_message or "",
            release=request.source_release,
            lane=request.source_lane,
        )
        target = MappingIdentity(
            format=request.target_format,
            message_type=request.target_message,
            release=request.target_version,
            lane=request.target_lane,
        )
        pack = self._registry.resolve(source, target, request.mapping_pack_id)
        if pack is None:
            return self._blocked(
                source, target, "No exact Mapping Pack matches this source and target."
            )
        if pack.provenance.review_state is MappingReviewState.CANDIDATE:
            return self._blocked(
                source,
                target,
                "The exact Mapping Pack is an unreviewed candidate and cannot execute.",
            )
        self._validate_pack(pack)
        if not pack.provenance.production_eligible and not request.allow_synthetic_preview:
            return self._blocked(
                source,
                target,
                "The only exact Mapping Pack is synthetic and is disabled until "
                "allowSyntheticPreview is explicitly set.",
            )

        source_values = {field.id: field.value for field in fields if field.id}
        target_values: dict[str, str] = {}
        mapped_source: set[str] = set()
        not_represented: set[str] = set()
        derived: set[str] = set()
        applied: list[AppliedMapping] = []
        declared_missing: set[str] = set()

        for rule in pack.rules:
            if not self._condition(rule, source_values):
                continue
            if rule.kind is MappingKind.NOT_REPRESENTED:
                not_represented.update(ref for ref in rule.source_refs if ref in source_values)
                continue
            if rule.kind is MappingKind.TARGET_REQUIRED_MISSING:
                declared_missing.update(output.target_ref for output in rule.outputs)
                continue
            values = [source_values[ref] for ref in rule.source_refs if ref in source_values]
            if rule.source_refs and len(values) != len(rule.source_refs):
                continue
            for output in rule.outputs:
                value = self._transform(output, values, rule.delimiter)
                if value is None:
                    continue
                target_values[output.target_ref] = value
                if output.transform is not TransformName.IDENTITY:
                    derived.add(output.target_ref)
            mapped_source.update(rule.source_refs)
            applied.append(
                AppliedMapping(
                    rule_id=rule.id,
                    kind=rule.kind,
                    semantic=rule.semantic,
                    source_refs=rule.source_refs,
                    target_refs=[output.target_ref for output in rule.outputs],
                    transform=", ".join(output.transform.value for output in rule.outputs),
                )
            )

        user_supplied = {item.path for item in request.target_values}
        target_values.update({item.path: item.value for item in request.target_values})
        target_spec = message_spec(
            pack.target.format, pack.target.release or pack.target.message_type, pack.target.lane
        )
        required = {
            field.id for field in target_spec.fields if field.presence is Presence.MANDATORY
        }
        missing_ids = (required | declared_missing) - target_values.keys()
        by_id = {field.id: field for field in target_spec.fields}
        missing = [
            MissingTarget(
                field_id=field_id,
                display_name=by_id[field_id].display_name,
                question=by_id[field_id].business_question,
                reason=(
                    "Required by the target structure and not established by the source mapping."
                ),
            )
            for field_id in sorted(missing_ids)
            if field_id in by_id
        ]
        report = ConversionReport(
            source=source,
            target=target,
            mapping_pack_id=pack.pack_id,
            mapping_pack_version=pack.version,
            provenance=pack.provenance,
            mapped_source_fields=sorted(mapped_source),
            source_fields_not_represented=sorted(
                not_represented | (set(source_values) - mapped_source)
            ),
            mapped_target_fields=sorted(set(target_values) - derived - user_supplied),
            derived_target_fields=sorted(derived - user_supplied),
            user_supplied_target_fields=sorted(user_supplied),
            target_required_missing=missing,
            transformations_applied=applied,
            limitations=pack.provenance.limitations,
        )
        elements = [
            ElementInput(path=path, value=value)
            for path, value in sorted(target_values.items())
        ]
        if missing:
            return ConversionResponse(
                status="NEEDS_INPUT",
                target_values=elements,
                report=report,
                message="Required target information is missing; no value was invented.",
            )

        generated = studio_service.generate(
            GenerateRequest(
                format=pack.target.format,
                message_type=pack.target.release or pack.target.message_type,
                profile_id=request.profile_id,
                elements=elements,
                persist=False,
                lane=pack.target.lane,
                release=pack.target.release,
            ),
            source="CONVERSION",
        )
        status = "READY" if generated.valid else "INVALID_TARGET"
        return ConversionResponse(
            status=status,
            target_values=elements,
            report=report,
            validation=generated.validation,
            generation=generated,
            output_xml=generated.outputs.xml if generated.valid else None,
            message=(
                "Target generated and validated by the deterministic engine."
                if generated.valid
                else "Mapped target values failed deterministic validation."
            ),
        )

    def _validate_pack(self, pack: MappingPack) -> None:
        source_spec = message_spec(
            pack.source.format, pack.source.message_type, pack.source.lane, pack.source.release
        )
        target_spec = message_spec(
            pack.target.format, pack.target.release or pack.target.message_type, pack.target.lane
        )
        source_checksum = sha256(
            source_spec.model_dump_json(by_alias=True, exclude={"capability"}).encode("utf-8")
        ).hexdigest()
        target_checksum = sha256(
            target_spec.model_dump_json(by_alias=True, exclude={"capability"}).encode("utf-8")
        ).hexdigest()
        if source_checksum != pack.source_structure_checksum:
            raise MappingError("Mapping Pack source structure checksum does not match")
        if target_checksum != pack.target_structure_checksum:
            raise MappingError("Mapping Pack target structure checksum does not match")

        repository_root = CONFIG_ROOT.parents[1]
        evidence = (repository_root / pack.provenance.source_reference).resolve()
        if not evidence.is_relative_to(repository_root) or not evidence.is_file():
            raise MappingError("Mapping Pack evidence reference is unavailable")
        evidence_checksum = sha256(evidence.read_bytes()).hexdigest()
        if evidence_checksum != pack.provenance.source_checksum.removeprefix("sha256:"):
            raise MappingError("Mapping Pack evidence checksum does not match")

        source_ids = {field.id for field in source_spec.fields}
        target_ids = {field.id for field in target_spec.fields}
        for rule in pack.rules:
            unknown_sources = set(rule.source_refs) - source_ids
            if rule.condition is not None and rule.condition.source_ref not in source_ids:
                unknown_sources.add(rule.condition.source_ref)
            unknown_targets = {output.target_ref for output in rule.outputs} - target_ids
            if unknown_sources or unknown_targets:
                raise MappingError(
                    f"{pack.pack_id}/{rule.id} has unknown refs: "
                    f"source={sorted(unknown_sources)}, target={sorted(unknown_targets)}"
                )

    @staticmethod
    def _condition(rule: MappingRule, values: dict[str, str]) -> bool:
        condition = rule.condition
        if condition is None:
            return True
        current = values.get(condition.source_ref)
        if condition.operator == "PRESENT":
            return bool(current)
        if condition.operator == "EQUALS":
            return current == condition.value
        return current is not None and current != condition.value

    @staticmethod
    def _transform(output: MappingOutput, values: list[str], delimiter: str) -> str | None:
        transform = output.transform
        if transform is TransformName.CONSTANT:
            return output.constant
        if not values:
            return None
        value = values[0] if len(values) == 1 else delimiter.join(values)
        if transform is TransformName.IDENTITY:
            return value
        if transform is TransformName.JOIN:
            return delimiter.join(values)
        if transform is TransformName.ENUM:
            return output.enum.get(value)
        if transform is TransformName.MT_DATE_TO_ISO:
            if not re.fullmatch(r"\d{8}", value):
                raise MappingError(f"Expected an MT YYYYMMDD date, got {value!r}")
            parsed = date(int(value[:4]), int(value[4:6]), int(value[6:]))
            return parsed.isoformat()
        if transform is TransformName.MT_UNIT_QUANTITY:
            match = re.fullmatch(r"UNIT/([0-9]+(?:[,.][0-9]+)?)", value)
            if not match:
                raise MappingError(f"Expected UNIT/quantity, got {value!r}")
            return match.group(1).replace(",", ".")
        if transform is TransformName.MT_AMOUNT_TO_ISO:
            match = re.fullmatch(r"([A-Z]{3})([0-9]+(?:,[0-9]+)?)", value)
            if not match:
                raise MappingError(f"Expected MT currency amount, got {value!r}")
            return f"{match.group(1)} {match.group(2).replace(',', '.')}"
        raise MappingError(f"Unsupported transform: {transform}")

    @staticmethod
    def _target(pack: MappingPack) -> ConversionTarget:
        return ConversionTarget(
            pack_id=pack.pack_id,
            pack_version=pack.version,
            target=pack.target,
            review_state=pack.provenance.review_state,
            production_eligible=pack.provenance.production_eligible,
            preview_only=not pack.provenance.production_eligible,
            provenance=pack.provenance,
        )

    @staticmethod
    def _blocked(
        source: MappingIdentity, target: MappingIdentity, message: str
    ) -> ConversionResponse:
        del source, target
        return ConversionResponse(
            status="BLOCKED_BY_MAPPING_EVIDENCE",
            target_values=[],
            report=None,
            message=message,
        )


mapping_service = MappingService()
