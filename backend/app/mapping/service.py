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
    MappingCoverage,
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


def _iso_decimal(amount: str) -> str:
    """``1234,56`` → ``1234.56``; a trailing comma (``1000,``) → ``1000``."""
    normalised = amount.replace(",", ".")
    return normalised[:-1] if normalised.endswith(".") else normalised


class MappingError(ValueError):
    pass


class MappingService:
    def __init__(self, registry: MappingRegistry | None = None) -> None:
        self._registry = registry or mapping_registry()

    def targets(self, source: MappingIdentity) -> ConversionTargetsResponse:
        """Every Mapping Pack for the source, then every relationship the knowledge base
        supports that has no pack — listed as not convertible, with its evidence."""
        targets = [self._target(pack) for pack in self._registry.targets(source)]
        packed = {(item.target.message_type, item.target.release) for item in targets}
        for relationship in self._registry.relationships_for(source):
            key = (relationship.target.message_type, relationship.target.release)
            if key in packed:
                continue
            targets.append(
                ConversionTarget(
                    pack_id=None,
                    pack_version=None,
                    target=relationship.target,
                    review_state="NO_PACK",
                    production_eligible=False,
                    preview_only=True,
                    evidence_class=relationship.evidence_class,
                    convertible=False,
                    relationship=relationship,
                )
            )
        eligible = any(item.production_eligible for item in targets)
        return ConversionTargetsResponse(
            source=source,
            targets=targets,
            authority_note=(
                "A production-eligible, reviewed Mapping Pack exists for this source."
                if eligible
                else "No production-eligible mapping evidence is configured. Candidate and "
                "synthetic preview packs demonstrate the deterministic workflow only; a "
                "relationship without a pack is listed with its evidence and is not "
                "convertible."
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
            kind = (
                "a candidate preview"
                if pack.provenance.review_state is MappingReviewState.CANDIDATE_PREVIEW
                else "synthetic"
            )
            return self._blocked(
                source,
                target,
                f"The only exact Mapping Pack is {kind} ({pack.provenance.evidence_class.value}) "
                "and is disabled until allowSyntheticPreview is explicitly set.",
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
            if rule.kind in {MappingKind.NOT_REPRESENTED, MappingKind.OMIT}:
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
        source_spec = message_spec(
            pack.source.format, pack.source.message_type, pack.source.lane, pack.source.release
        )
        coverage = MappingCoverage(
            mandatory_target_total=len(required),
            mandatory_target_mapped=len(required & set(target_values)),
            source_rows_total=len(source_spec.fields),
            source_rows_represented=len(
                {ref for rule in pack.rules for ref in rule.source_refs}
                - {
                    ref
                    for rule in pack.rules
                    if rule.kind in {MappingKind.NOT_REPRESENTED, MappingKind.OMIT}
                    for ref in rule.source_refs
                }
            ),
            rules_total=len(pack.rules),
            rules_cited=pack.cited_rule_count,
        )
        report = ConversionReport(
            source=source,
            target=target,
            mapping_pack_id=pack.pack_id,
            mapping_pack_version=pack.version,
            provenance=pack.provenance,
            evidence_class=pack.provenance.evidence_class,
            coverage=coverage,
            relationship_citations=pack.provenance.relationship_citations,
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
        # A mandatory block whose leaves are all optional (pacs.009's Debtor, a choice of
        # identifications) is required even though no single leaf is: the deterministic
        # validator names the block and the leaf that would open it, and the caller is asked
        # for that leaf rather than have the platform invent a party.
        blocks = [
            issue
            for issue in generated.validation.errors
            if issue.rule_id == "MX_MANDATORY_BLOCK_MISSING" and issue.expected
        ]
        if blocks:
            report.target_required_missing = [
                MissingTarget(
                    field_id=str(issue.expected),
                    display_name=by_id[str(issue.expected)].display_name
                    if str(issue.expected) in by_id
                    else str(issue.expected),
                    question=by_id[str(issue.expected)].business_question
                    if str(issue.expected) in by_id
                    else f"Which value opens {issue.field}?",
                    reason=(
                        f"{issue.field} is a required block of the target structure and "
                        "nothing in the source mapping populates it."
                    ),
                )
                for issue in blocks
                if str(issue.expected) not in target_values
            ]
            if report.target_required_missing:
                return ConversionResponse(
                    status="NEEDS_INPUT",
                    target_values=elements,
                    report=report,
                    validation=generated.validation,
                    message="Required target information is missing; no value was invented.",
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
        if transform is TransformName.MT_DECIMAL_TO_ISO:
            if not re.fullmatch(r"[0-9]+(?:,[0-9]*)?", value):
                raise MappingError(f"Expected a SWIFT decimal (d), got {value!r}")
            return _iso_decimal(value)
        if transform is TransformName.MT_AMOUNT_TO_ISO:
            match = re.fullmatch(r"([A-Z]{3})([0-9]+(?:,[0-9]*)?)", value)
            if not match:
                raise MappingError(f"Expected MT currency amount, got {value!r}")
            return f"{match.group(1)} {_iso_decimal(match.group(2))}"
        if transform in {TransformName.MT_DATED_AMOUNT_DATE, TransformName.MT_DATED_AMOUNT_TO_ISO}:
            match = re.fullmatch(r"(\d{6})([A-Z]{3})([0-9]+(?:,[0-9]*)?)", value)
            if not match:
                raise MappingError(f"Expected an MT dated amount (6!n3!a15d), got {value!r}")
            if transform is TransformName.MT_DATED_AMOUNT_DATE:
                raw = match.group(1)
                parsed = date(2000 + int(raw[:2]), int(raw[2:4]), int(raw[4:6]))
                return parsed.isoformat()
            return f"{match.group(2)} {_iso_decimal(match.group(3))}"
        if transform is TransformName.MT_PARTY_BIC:
            bic = value.strip().splitlines()[-1].strip()
            if not re.fullmatch(r"[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?", bic):
                raise MappingError(f"Expected a party option A value ending in a BIC: {value!r}")
            return bic
        raise MappingError(f"Unsupported transform: {transform}")

    def _target(self, pack: MappingPack) -> ConversionTarget:
        relationship = next(
            (
                item
                for item in self._registry.relationships_for(pack.source)
                if item.target.message_type == pack.target.message_type
            ),
            None,
        )
        return ConversionTarget(
            pack_id=pack.pack_id,
            pack_version=pack.version,
            target=pack.target,
            review_state=pack.provenance.review_state,
            production_eligible=pack.provenance.production_eligible,
            preview_only=not pack.provenance.production_eligible,
            evidence_class=pack.provenance.evidence_class,
            convertible=pack.provenance.review_state is not MappingReviewState.CANDIDATE,
            provenance=pack.provenance,
            relationship=relationship,
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
