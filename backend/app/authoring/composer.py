from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime

from app.authoring.models import (
    DataClassification,
    FieldValueSource,
    LineMapping,
    ValidationLevel,
    ValidationLevelState,
)
from app.domain.identifiers import (
    bic_format_valid,
    normalise_isin,
    proprietary_party_valid,
    validate_isin,
)
from app.knowledge.presentation import choice_key, is_direct_code_field
from app.specifications.models import FieldSpecification, MessageSpecification


@dataclass(frozen=True)
class ComposeField:
    row: FieldSpecification
    sequence_id: str
    value: str
    source: FieldValueSource
    classification: DataClassification


@dataclass(frozen=True)
class ComposeSequence:
    sequence_id: str
    sequence_path: str
    parent_sequence_id: str | None
    occurrence: int


@dataclass(frozen=True)
class GenericComposition:
    block_4: str
    checksum: str
    line_mappings: list[LineMapping]
    validation_levels: dict[ValidationLevel, ValidationLevelState]
    findings: list[str]


class SpecificationComposer:
    def compose(
        self,
        specification: MessageSpecification,
        sequences: list[ComposeSequence],
        fields: list[ComposeField],
        *,
        client_profile_enabled: bool,
    ) -> GenericComposition:
        sequence_specs = {item.path: item for item in specification.sequences}
        instances = {item.sequence_id: item for item in sequences}
        children: dict[str | None, list[ComposeSequence]] = {}
        structure_findings: list[str] = []
        format_findings: list[str] = []
        for instance in sequences:
            sequence_spec = sequence_specs.get(instance.sequence_path)
            if sequence_spec is None:
                structure_findings.append(f"Unknown sequence {instance.sequence_path}.")
                continue
            parent = (
                instances.get(instance.parent_sequence_id) if instance.parent_sequence_id else None
            )
            expected_parent = sequence_spec.parent_path
            if expected_parent and (parent is None or parent.sequence_path != expected_parent):
                structure_findings.append(
                    f"Sequence {instance.sequence_path} requires a {expected_parent} parent."
                )
            if not expected_parent and instance.parent_sequence_id is not None:
                structure_findings.append(
                    f"Sequence {instance.sequence_path} cannot have a parent."
                )
            children.setdefault(instance.parent_sequence_id, []).append(instance)

        counts: dict[tuple[str | None, str], int] = {}
        for instance in sequences:
            key = (instance.parent_sequence_id, instance.sequence_path)
            counts[key] = counts.get(key, 0) + 1
        for sequence_spec in specification.sequences:
            relevant_parents: list[str | None]
            if sequence_spec.parent_path:
                relevant_parents = [
                    item.sequence_id
                    for item in sequences
                    if item.sequence_path == sequence_spec.parent_path
                ]
            else:
                relevant_parents = [None]
            for parent_id in relevant_parents:
                count = counts.get((parent_id, sequence_spec.path), 0)
                if not sequence_spec.min_occurs <= count <= sequence_spec.max_occurs:
                    structure_findings.append(
                        f"Sequence {sequence_spec.path} occurrence count {count} is outside "
                        f"{sequence_spec.min_occurs}..{sequence_spec.max_occurs}."
                    )

        fields_by_sequence: dict[str, list[ComposeField]] = {}
        field_ids = {row.row_id: row for row in specification.fields}
        for field in fields:
            field_instance = instances.get(field.sequence_id)
            expected = field_ids.get(field.row.row_id)
            if field_instance is None:
                structure_findings.append(
                    f"Field {field.row.row_id} has an unknown sequence instance."
                )
                continue
            if expected is None or expected.sequence_path != field_instance.sequence_path:
                structure_findings.append(
                    f"Field {field.row.row_id} is not valid in this sequence."
                )
                continue
            if "\r" in field.value or "\n" in field.value:
                continuation = field.value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
                if any(line.startswith((":", "-}")) for line in continuation[1:]):
                    format_findings.append(
                        f"Field {field.row.row_id} has an unsafe continuation line."
                    )
            if (
                is_direct_code_field(field.row.tag, field.row.allowed_codes)
                and field.value not in field.row.allowed_codes
            ):
                format_findings.append(
                    f"Field {field.row.row_id} requires one of its configured controlled codes."
                )
            if not row_format_valid(field.row, field.value):
                format_findings.append(
                    f"Field {field.row.row_id} does not match its configured local format."
                )
            fields_by_sequence.setdefault(field.sequence_id, []).append(field)

        # A row in a choice group is satisfied by any member of that group: the BIC form and
        # the proprietary form of a settlement party are two field options carrying one
        # business value, so requiring both would demand the party twice.
        group_members: dict[str, set[str]] = {}
        for row in specification.fields:
            group = choice_key(row.choice_group)
            if group:
                group_members.setdefault(group, set()).add(row.row_id)
        for row in specification.fields:
            if row.min_occurs == 0:
                continue
            group = choice_key(row.choice_group)
            satisfying = group_members.get(group, {row.row_id}) if group else {row.row_id}
            matching_instances = [
                item for item in sequences if item.sequence_path == row.sequence_path
            ]
            for instance in matching_instances:
                matching = [
                    field
                    for field in fields_by_sequence.get(instance.sequence_id, [])
                    if field.row.row_id in satisfying
                ]
                if len(matching) < row.min_occurs:
                    structure_findings.append(
                        f"Mandatory configured field {row.row_id} is missing."
                    )

        lines = ["{4:"]
        mappings: list[LineMapping] = []

        def render(instance: ComposeSequence) -> None:
            sequence_spec = sequence_specs[instance.sequence_path]
            lines.append(f":16R:{sequence_spec.code}")
            mappings.append(
                LineMapping(
                    line_number=len(lines),
                    sequence_path=instance.sequence_path,
                    tag="16R",
                )
            )
            ordered_fields = sorted(
                fields_by_sequence.get(instance.sequence_id, []),
                key=lambda item: (item.row.row_number, item.row.row_id),
            )
            ordered_children = sorted(
                children.get(instance.sequence_id, []),
                key=lambda item: (sequence_specs[item.sequence_path].order, item.occurrence),
            )
            rendered_children: set[str] = set()
            for field in ordered_fields:
                prefix = f":{field.row.tag}:"
                if field.row.qualifier:
                    prefix += f":{field.row.qualifier}//"
                # The one place a field's literal is written. A caller supplies the
                # identifier alone — `XS0000000009`, never `ISIN XS0000000009` — so the
                # canonical value stays a business value and exactly one component turns it
                # into SWIFT syntax. The importer strips the same literal on the way back.
                if field.row.literal_prefix:
                    prefix += field.row.literal_prefix
                value_lines = field.value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
                lines.append(prefix + value_lines[0])
                lines.extend(value_lines[1:])
                mappings.append(
                    LineMapping(
                        line_number=len(lines) - len(value_lines) + 1,
                        sequence_path=instance.sequence_path,
                        row_id=field.row.row_id,
                        tag=field.row.tag,
                        qualifier=field.row.qualifier,
                        value_source=field.source,
                        classification=field.classification,
                    )
                )
                for child in ordered_children:
                    child_spec = sequence_specs[child.sequence_path]
                    if (
                        child.sequence_id not in rendered_children
                        and child_spec.insert_after_tag == field.row.tag
                    ):
                        render(child)
                        rendered_children.add(child.sequence_id)
            for child in ordered_children:
                if child.sequence_id not in rendered_children:
                    render(child)
            lines.append(f":16S:{sequence_spec.code}")
            mappings.append(
                LineMapping(
                    line_number=len(lines),
                    sequence_path=instance.sequence_path,
                    tag="16S",
                )
            )

        for root in sorted(
            children.get(None, []),
            key=lambda item: (sequence_specs[item.sequence_path].order, item.occurrence),
        ):
            render(root)
        lines.append("-}")
        block_4 = "\n".join(lines)
        levels = {
            ValidationLevel.CANONICAL_VALID: (
                ValidationLevelState.PASSED
                if not structure_findings and not format_findings
                else ValidationLevelState.FAILED
            ),
            ValidationLevel.STRUCTURE_VALID: (
                ValidationLevelState.PASSED
                if not structure_findings
                else ValidationLevelState.FAILED
            ),
            ValidationLevel.FORMAT_VALID: (
                ValidationLevelState.PASSED if not format_findings else ValidationLevelState.FAILED
            ),
            ValidationLevel.NETWORK_RULES_LOCALLY_VALID: (
                ValidationLevelState.EXTERNAL_EVIDENCE_REQUIRED
            ),
            ValidationLevel.USAGE_RULES_LOCALLY_VALID: (
                ValidationLevelState.EXTERNAL_EVIDENCE_REQUIRED
            ),
            ValidationLevel.CLIENT_PROFILE_VALID: (
                ValidationLevelState.PASSED
                if client_profile_enabled
                else ValidationLevelState.FAILED
            ),
            ValidationLevel.MARKET_PROFILE_VALID: (ValidationLevelState.EXTERNAL_EVIDENCE_REQUIRED),
            ValidationLevel.EXTERNAL_VALIDATION_PASSED: (ValidationLevelState.NOT_EVALUATED),
            ValidationLevel.APPROVED_FOR_SUBMISSION: ValidationLevelState.NOT_EVALUATED,
        }
        return GenericComposition(
            block_4=block_4,
            checksum=hashlib.sha256(block_4.encode()).hexdigest(),
            line_mappings=mappings,
            validation_levels=levels,
            findings=[*structure_findings, *format_findings],
        )


specification_composer = SpecificationComposer()


def row_format_valid(row: FieldSpecification, value: str) -> bool:
    """Whether a **canonical** value fits the field it is addressed to.

    Canonical means the business value alone: the identifier without the ``ISIN`` literal,
    because the composer writes that. Checking the rendered form instead is what previously
    forced testers to type SWIFT syntax into a business field.
    """
    if row.literal_prefix and "ISIN" in row.identifier_types:
        return validate_isin(value).format_valid
    if row.tag == "95P":
        return bic_format_valid(value)
    if row.tag == "95R":
        # Option R is a data source scheme and an identifier. Without the scheme it is not
        # an option-R value at all, and the field silently accepted BIC-shaped values.
        return proprietary_party_valid(value)
    return _format_valid(row.tag, value)


def _format_valid(tag: str, value: str) -> bool:
    if not value or "\x00" in value:
        return False
    if tag == "20C":
        return bool(
            len(value) <= 16
            and re.fullmatch(r"[A-Z0-9._/-]+", value)
            and not value.startswith("/")
            and not value.endswith("/")
            and "//" not in value
        )
    if tag == "98A":
        if not re.fullmatch(r"\d{8}", value):
            return False
        try:
            datetime.strptime(value, "%Y%m%d")
        except ValueError:
            return False
        return True
    patterns = {
        "11A": r"[A-Z]{3}",
        "13A": r"\d{3}",
        "17B": r"[YN]",
        "19A": r"N?[A-Z]{3}\d+(?:,\d+)?",
        "19B": r"N?[A-Z]{3}\d+(?:,\d+)?",
        "28E": r"\d{1,5}/[A-Z]{4}",
        # 35B carries the identifier alone; the ISIN literal is added at render time and is
        # never part of the value. Kept for any caller that still addresses the tag without
        # a specification row.
        "35B": r"[A-Z]{2}[A-Z0-9]{9}\d",
        "36B": r"[A-Z]{4}/\d+(?:,\d*)?",
        "93B": r"[A-Z]{4}/\d+(?:,\d*)?",
        "99A": r"\d{1,3}",
    }
    if tag in patterns:
        return re.fullmatch(patterns[tag], value) is not None
    if tag == "97A":
        return len(value) <= 35 and "\n" not in value
    if tag == "95P":
        return bic_format_valid(value)
    if tag == "95R":
        return proprietary_party_valid(value)
    if tag in {"70D", "70E"}:
        return len(value) <= 350 and all(
            ord(character) >= 32 or character == "\n" for character in value
        )
    return len(value) <= 1_000


def canonical_field_value(row: FieldSpecification, value: str) -> str:
    """Normalise presentation before anything judges the value.

    One place, reached by the browser, the JSON API, Excel and MT import alike, so a value
    pasted with the field's own literal in front of it — ``ISIN XS0000000009`` — is accepted
    and stored the same way as one typed without it. Only spacing, case and the literal are
    touched; the identifier's characters are never rewritten.
    """
    if row.literal_prefix and "ISIN" in row.identifier_types:
        return normalise_isin(value)
    if row.tag in {"95P", "95R"}:
        return value.strip().upper()
    return value
