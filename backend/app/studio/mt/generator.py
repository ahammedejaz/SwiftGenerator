"""Tag-level MT generation.

This module is a thin, stateless door onto assets that already exist and are already
tested: :mod:`app.specifications.registry` supplies the ordered format rows and
:class:`app.authoring.composer.SpecificationComposer` renders Block 4. What is added here
is address resolution (row id, or sequence/tag/qualifier), structured validation and the
FIN envelope.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.authoring.composer import (
    ComposeField,
    ComposeSequence,
    _format_valid,
    specification_composer,
)
from app.authoring.models import DataClassification, FieldValueSource
from app.domain.enums import MessageType
from app.profiles.loader import ClientProfile
from app.specifications.models import FieldSpecification, MessageSpecification
from app.specifications.registry import specification_registry
from app.studio.models import (
    EnvelopeField,
    EnvelopeOverride,
    FieldInput,
    FieldOrigin,
    IssueSeverity,
    RenderedLine,
    ValidationIssue,
    ValidationLayer,
)
from app.studio.mt.fin import FinEnvelopeUnavailable, build_fin_message

#: Tags whose value is a controlled code taken directly from the row's code list.
DIRECT_CODE_TAG_PREFIXES = frozenset({"11", "17", "22", "23", "24", "25"})


@dataclass
class ResolvedField:
    row: FieldSpecification
    occurrence: int
    value: str
    origin: FieldOrigin = FieldOrigin.USER_ENTERED


@dataclass
class MtBuildResult:
    specification: MessageSpecification
    block_4: str
    fin: str | None
    envelope_fields: list[EnvelopeField]
    rendered_lines: list[RenderedLine]
    resolved: list[ResolvedField]
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
    fin_blocked_reason: str | None = None

    @property
    def checksum(self) -> str:
        return hashlib.sha256((self.fin or self.block_4).encode()).hexdigest()


def _error(
    rule_id: str,
    message: str,
    *,
    layer: ValidationLayer,
    field_name: str | None = None,
    location: str | None = None,
    expected: str | None = None,
    current: str | None = None,
    suggestion: str | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        rule_id=rule_id,
        severity=IssueSeverity.ERROR,
        layer=layer,
        field=field_name,
        location=location,
        message=message,
        expected=expected,
        current_value=current,
        suggestion=suggestion,
    )


def _normalise_sequence(specification: MessageSpecification, value: str | None) -> str | None:
    """Accept either a sequence path (``A``) or a sequence code (``GENL``)."""
    if not value:
        return None
    candidate = value.strip().upper()
    for sequence in specification.sequences:
        if candidate in {sequence.path.upper(), sequence.code.upper()}:
            return sequence.path
    return None


class MtGenerator:
    def supports(self, message_type: str) -> bool:
        try:
            MessageType(message_type.upper())
        except ValueError:
            return False
        return True

    def specification(self, message_type: str) -> MessageSpecification:
        return specification_registry.get(MessageType(message_type.upper()))

    # -- address resolution ------------------------------------------------------------

    def resolve(
        self, specification: MessageSpecification, inputs: list[FieldInput]
    ) -> tuple[list[ResolvedField], list[ValidationIssue]]:
        by_id = {row.row_id.upper(): row for row in specification.fields}
        by_address: dict[tuple[str, str, str | None], FieldSpecification] = {
            (row.sequence_path, row.tag, row.qualifier): row for row in specification.fields
        }
        resolved: list[ResolvedField] = []
        issues: list[ValidationIssue] = []
        seen: set[tuple[str, int]] = set()

        for index, item in enumerate(inputs, start=1):
            row: FieldSpecification | None = None
            if item.id:
                row = by_id.get(item.id.strip().upper())
                if row is None:
                    issues.append(
                        _error(
                            "MT_UNKNOWN_FIELD_ID",
                            f"'{item.id}' is not a field of {specification.message_type.value}.",
                            layer=ValidationLayer.CANONICAL,
                            field_name=item.id,
                            location=f"input[{index}]",
                            suggestion="Call the message specification endpoint for the list "
                            "of valid field identifiers.",
                        )
                    )
                    continue
            else:
                sequence_path = _normalise_sequence(specification, item.sequence)
                if item.sequence and sequence_path is None:
                    issues.append(
                        _error(
                            "MT_UNKNOWN_SEQUENCE",
                            f"'{item.sequence}' is not a sequence of "
                            f"{specification.message_type.value}.",
                            layer=ValidationLayer.STRUCTURE,
                            field_name=item.sequence,
                            location=f"input[{index}]",
                            expected=", ".join(
                                f"{s.path} ({s.code})" for s in specification.sequences
                            ),
                            suggestion="Use the sequence code, for example GENL or SETDET.",
                        )
                    )
                    continue
                tag = (item.tag or "").strip().upper()
                qualifier = (item.qualifier or "").strip().upper() or None
                if not tag:
                    issues.append(
                        _error(
                            "MT_FIELD_NOT_ADDRESSED",
                            "Every value needs either a field id or a tag.",
                            layer=ValidationLayer.CANONICAL,
                            location=f"input[{index}]",
                            suggestion="Supply Tag and Qualifier, or the field id.",
                        )
                    )
                    continue
                if sequence_path:
                    row = by_address.get((sequence_path, tag, qualifier))
                else:
                    matches = [
                        candidate
                        for candidate in specification.fields
                        if candidate.tag == tag and candidate.qualifier == qualifier
                    ]
                    row = matches[0] if len(matches) == 1 else None
                    if len(matches) > 1:
                        issues.append(
                            _error(
                                "MT_AMBIGUOUS_FIELD",
                                f"Tag {tag}"
                                + (f"/{qualifier}" if qualifier else "")
                                + " appears in more than one sequence.",
                                layer=ValidationLayer.CANONICAL,
                                location=f"input[{index}]",
                                expected=", ".join(sorted({m.sequence_code for m in matches})),
                                suggestion="Add the Sequence column to identify which one "
                                "you mean.",
                            )
                        )
                        continue
                if row is None:
                    label = f"{tag}" + (f"/{qualifier}" if qualifier else "")
                    issues.append(
                        _error(
                            "MT_UNKNOWN_FIELD",
                            f"{label} is not a supported field of "
                            f"{specification.message_type.value}"
                            + (f" in sequence {item.sequence}." if item.sequence else "."),
                            layer=ValidationLayer.STRUCTURE,
                            field_name=label,
                            location=f"input[{index}]",
                            suggestion="Download the Excel template or read the message "
                            "specification for the supported tags.",
                        )
                    )
                    continue

            if item.option and item.option.strip().upper() != row.option:
                issues.append(
                    _error(
                        "MT_OPTION_MISMATCH",
                        f"{row.tag} is supported in option {row.option}, not "
                        f"{item.option.strip().upper()}.",
                        layer=ValidationLayer.FORMAT,
                        field_name=row.business_name,
                        location=row.row_id,
                        expected=row.option,
                        current=item.option,
                        suggestion=f"Use option {row.option} or remove the Option column.",
                    )
                )
                continue

            key = (row.row_id, item.occurrence)
            if key in seen:
                issues.append(
                    _error(
                        "MT_DUPLICATE_FIELD",
                        f"{row.business_name} was supplied more than once for occurrence "
                        f"{item.occurrence}.",
                        layer=ValidationLayer.CANONICAL,
                        field_name=row.business_name,
                        location=row.row_id,
                        suggestion="Remove the duplicate row, or increment "
                        "SequenceOccurrence to build a repeated sequence.",
                    )
                )
                continue
            seen.add(key)
            resolved.append(
                ResolvedField(row=row, occurrence=item.occurrence, value=item.value.strip())
            )
        return resolved, issues

    # -- validation --------------------------------------------------------------------

    def validate(
        self,
        specification: MessageSpecification,
        profile: ClientProfile,
        resolved: list[ResolvedField],
    ) -> tuple[list[ValidationIssue], list[ValidationIssue]]:
        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []
        supplied = {(item.row.row_id, item.occurrence) for item in resolved}
        occurrences = {item.occurrence for item in resolved} or {1}
        by_business_path = {item.row.business_path: item for item in resolved}

        # Mandatory rows, per sequence occurrence that the caller actually used.
        for row in specification.fields:
            if row.presence.value != "MANDATORY":
                continue
            sequence_occurrences = sorted(
                {
                    item.occurrence
                    for item in resolved
                    if item.row.sequence_path == row.sequence_path
                }
            ) or ([1] if any(o == 1 for o in occurrences) else [])
            for occurrence in sequence_occurrences or [1]:
                if (row.row_id, occurrence) in supplied:
                    continue
                errors.append(
                    _error(
                        "MT_MANDATORY_FIELD_MISSING",
                        f"{row.business_name} is required.",
                        layer=ValidationLayer.STRUCTURE,
                        field_name=row.business_name,
                        location=row.row_id,
                        expected=row.format,
                        suggestion=_first_example(row) or f"Provide {row.business_name}.",
                    )
                )

        for item in resolved:
            row = item.row
            value = item.value
            if not _format_valid(row.tag, value):
                errors.append(
                    _error(
                        "MT_FORMAT_INVALID",
                        f"{row.business_name} does not match the expected format.",
                        layer=ValidationLayer.FORMAT,
                        field_name=row.business_name,
                        location=row.row_id,
                        expected=row.format,
                        current=value,
                        suggestion=_first_example(row)
                        or "Correct the value to match the expected format.",
                    )
                )
                continue
            if (
                row.tag[:2] in DIRECT_CODE_TAG_PREFIXES
                and row.allowed_codes
                and value not in row.allowed_codes
            ):
                errors.append(
                    _error(
                        "MT_CODE_NOT_ALLOWED",
                        f"{row.business_name} must be one of the supported codes.",
                        layer=ValidationLayer.FORMAT,
                        field_name=row.business_name,
                        location=row.row_id,
                        expected=", ".join(row.allowed_codes),
                        current=value,
                        suggestion=f"Use {row.allowed_codes[0]}.",
                    )
                )

        errors.extend(self._business_rules(by_business_path))
        errors.extend(self._profile_rules(profile, resolved))
        return errors, warnings

    @staticmethod
    def _business_rules(by_path: dict[str, ResolvedField]) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        trade = by_path.get("trade.tradeDate")
        settlement = by_path.get("trade.settlementDate")
        if trade and settlement:
            try:
                trade_date = datetime.strptime(trade.value, "%Y%m%d").date()
                settlement_date = datetime.strptime(settlement.value, "%Y%m%d").date()
            except ValueError:
                trade_date = settlement_date = None  # type: ignore[assignment]
            if trade_date and settlement_date and settlement_date < trade_date:
                issues.append(
                    _error(
                        "SETTLEMENT_DATE_BEFORE_TRADE_DATE",
                        "The settlement date is earlier than the trade date.",
                        layer=ValidationLayer.BUSINESS_RULES,
                        field_name="Intended Settlement Date",
                        location=settlement.row.row_id,
                        expected=f"A date on or after {trade.value}",
                        current=settlement.value,
                        suggestion="Set the settlement date on or after the trade date.",
                    )
                )
        function = by_path.get("function")
        if function and function.value == "CANC" and "relatedReference" not in by_path:
            issues.append(
                _error(
                    "CANCELLATION_REQUIRES_PREVIOUS_REFERENCE",
                    "A cancellation must state which earlier message it cancels.",
                    layer=ValidationLayer.BUSINESS_RULES,
                    field_name="Previous Message Reference",
                    expected="The sender reference of the original instruction",
                    suggestion="Add the 20C PREV field with the original SEME reference.",
                )
            )
        return issues

    @staticmethod
    def _profile_rules(
        profile: ClientProfile, resolved: list[ResolvedField]
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        rule = profile.validation.sender_reference
        for item in resolved:
            row = item.row
            if row.business_path == "senderReference":
                if len(item.value) > rule.max_length:
                    issues.append(
                        _error(
                            "PROFILE_SENDER_REFERENCE_TOO_LONG",
                            f"{profile.name} allows a sender reference of at most "
                            f"{rule.max_length} characters.",
                            layer=ValidationLayer.CLIENT_PROFILE,
                            field_name=row.business_name,
                            location=row.row_id,
                            expected=f"At most {rule.max_length} characters",
                            current=item.value,
                            suggestion="Shorten the reference.",
                        )
                    )
                if rule.uppercase and item.value != item.value.upper():
                    issues.append(
                        _error(
                            "PROFILE_SENDER_REFERENCE_CASE",
                            f"{profile.name} requires an uppercase sender reference.",
                            layer=ValidationLayer.CLIENT_PROFILE,
                            field_name=row.business_name,
                            location=row.row_id,
                            expected="Uppercase characters",
                            current=item.value,
                            suggestion=f"Use {item.value.upper()}.",
                        )
                    )
            if row.tag in {"19A", "19B"} and len(item.value) >= 3:
                currency = item.value.lstrip("N")[:3]
                if currency not in profile.allowed_currencies:
                    issues.append(
                        _error(
                            "PROFILE_CURRENCY_NOT_ALLOWED",
                            f"{profile.name} does not allow settlement in {currency}.",
                            layer=ValidationLayer.CLIENT_PROFILE,
                            field_name=row.business_name,
                            location=row.row_id,
                            expected=", ".join(profile.allowed_currencies),
                            current=currency,
                            suggestion=f"Use {profile.allowed_currencies[0]}.",
                        )
                    )
                amount_text = item.value.lstrip("N")[3:].replace(",", ".")
                try:
                    if Decimal(amount_text) <= 0:
                        issues.append(
                            _error(
                                "AMOUNT_NOT_POSITIVE",
                                f"{row.business_name} must be greater than zero.",
                                layer=ValidationLayer.BUSINESS_RULES,
                                field_name=row.business_name,
                                location=row.row_id,
                                current=item.value,
                                suggestion="Enter a positive amount.",
                            )
                        )
                except (InvalidOperation, ValueError):
                    pass
        return issues

    # -- rendering ---------------------------------------------------------------------

    def build(
        self,
        message_type: str,
        profile: ClientProfile,
        inputs: list[FieldInput],
        *,
        envelope: EnvelopeOverride | None = None,
        want_fin: bool = True,
    ) -> MtBuildResult:
        specification = self.specification(message_type)
        resolved, address_issues = self.resolve(specification, inputs)
        errors, warnings = self.validate(specification, profile, resolved)
        errors = [*address_issues, *errors]

        sequences, compose_fields = self._compose_inputs(specification, resolved)
        composition = specification_composer.compose(
            specification,
            sequences,
            compose_fields,
            client_profile_enabled=True,
        )
        # The composer restates problems the structured validator has already reported, in
        # its own words and by row id. Surface only what is genuinely new, otherwise a form
        # with twelve missing fields reports twenty-four errors.
        reported_rows = {issue.location for issue in errors if issue.location}
        reported_messages = {issue.message for issue in errors}
        for finding in composition.findings:
            if finding in reported_messages:
                continue
            if any(row_id and row_id in finding for row_id in reported_rows):
                continue
            errors.append(
                _error(
                    "MT_COMPOSITION_FINDING",
                    finding,
                    layer=ValidationLayer.STRUCTURE,
                    suggestion="Correct the highlighted field and generate again.",
                )
            )

        fin_text: str | None = None
        envelope_fields: list[EnvelopeField] = []
        fin_blocked: str | None = None
        if want_fin:
            try:
                fin_message = build_fin_message(
                    message_type=specification.message_type.value,
                    block_4=composition.block_4,
                    profile=profile,
                    override=envelope,
                )
                fin_text = fin_message.text
                envelope_fields = fin_message.fields
                warnings.extend(fin_message.warnings)
            except FinEnvelopeUnavailable as unavailable:
                fin_blocked = unavailable.issues[0].message
                warnings.extend(
                    issue.model_copy(update={"severity": IssueSeverity.WARNING})
                    for issue in unavailable.issues
                )

        rendered_lines = self._rendered_lines(composition.block_4, resolved)
        return MtBuildResult(
            specification=specification,
            block_4=composition.block_4,
            fin=fin_text,
            envelope_fields=envelope_fields,
            rendered_lines=rendered_lines,
            resolved=resolved,
            errors=errors,
            warnings=warnings,
            fin_blocked_reason=fin_blocked,
        )

    @staticmethod
    def _compose_inputs(
        specification: MessageSpecification, resolved: list[ResolvedField]
    ) -> tuple[list[ComposeSequence], list[ComposeField]]:
        by_path = {sequence.path: sequence for sequence in specification.sequences}
        needed: set[tuple[str, int]] = {
            (item.row.sequence_path, item.occurrence) for item in resolved
        }
        # Mandatory root sequences always exist so their missing fields are reported.
        for sequence in specification.sequences:
            if sequence.parent_path is None and sequence.min_occurs >= 1:
                needed.add((sequence.path, 1))
        # A child sequence needs its parent chain present.
        for path, occurrence in list(needed):
            current = by_path.get(path)
            while current and current.parent_path:
                needed.add((current.parent_path, 1 if occurrence == 1 else occurrence))
                current = by_path.get(current.parent_path)

        ordered = sorted(needed, key=lambda item: (by_path[item[0]].order, item[1]))
        instances: dict[tuple[str, int], ComposeSequence] = {}
        for path, occurrence in ordered:
            spec_sequence = by_path[path]
            parent_id: str | None = None
            if spec_sequence.parent_path:
                parent_key = (spec_sequence.parent_path, occurrence)
                if parent_key not in instances:
                    parent_key = (spec_sequence.parent_path, 1)
                parent = instances.get(parent_key)
                parent_id = parent.sequence_id if parent else None
            instances[(path, occurrence)] = ComposeSequence(
                sequence_id=f"{path}#{occurrence}",
                sequence_path=path,
                parent_sequence_id=parent_id,
                occurrence=occurrence,
            )
        compose_fields = [
            ComposeField(
                row=item.row,
                sequence_id=f"{item.row.sequence_path}#{item.occurrence}",
                value=item.value,
                source=FieldValueSource.USER_ENTERED,
                classification=DataClassification.INTERNAL,
            )
            for item in resolved
            if (item.row.sequence_path, item.occurrence) in instances
        ]
        return list(instances.values()), compose_fields

    @staticmethod
    def _rendered_lines(block_4: str, resolved: list[ResolvedField]) -> list[RenderedLine]:
        remaining = list(resolved)
        lines: list[RenderedLine] = []
        for number, text in enumerate(block_4.splitlines(), start=1):
            matched: ResolvedField | None = None
            for candidate in remaining:
                prefix = f":{candidate.row.tag}:"
                if candidate.row.qualifier:
                    prefix += f":{candidate.row.qualifier}//"
                if text.startswith(prefix):
                    matched = candidate
                    break
            if matched is not None:
                remaining.remove(matched)
                lines.append(
                    RenderedLine(
                        line_number=number,
                        text=text,
                        field_id=matched.row.row_id,
                        display_name=matched.row.business_name,
                        origin=matched.origin,
                    )
                )
            else:
                lines.append(
                    RenderedLine(
                        line_number=number,
                        text=text,
                        display_name=(
                            "Sequence marker" if text.startswith((":16R:", ":16S:")) else None
                        ),
                        origin=FieldOrigin.APPLICATION_GENERATED,
                    )
                )
        return lines


def _first_example(row: FieldSpecification) -> str | None:
    from app.knowledge.loader import knowledge_repository

    try:
        knowledge = knowledge_repository.get(row.knowledge_id)
    except KeyError:
        return None
    if not knowledge.example_values:
        return None
    return f"For example: {knowledge.example_values[0].value}"


mt_generator = MtGenerator()
