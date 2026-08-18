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
    canonical_field_value,
    row_format_valid,
    specification_composer,
)
from app.authoring.models import DataClassification, FieldValueSource
from app.domain.identifiers import IsinProblem, validate_isin
from app.knowledge.presentation import (
    DIRECT_CODE_TAG_PREFIXES,
    choice_key,
    is_direct_code_field,
)
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

#: Re-exported: the definition lives beside the rest of the presentation rules, which is
#: what the composer and the catalogue read.
__all__ = ["DIRECT_CODE_TAG_PREFIXES", "MtGenerator", "mt_generator", "plan_sequences"]


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


def plan_sequences(
    specification: MessageSpecification,
    addressed: set[tuple[str, int]],
) -> dict[tuple[str, int], ComposeSequence]:
    """Work out which sequence instances a set of ``(path, occurrence)`` addresses implies.

    This is the whole of the MT occurrence model, in one place. It is shared with the
    importer, which runs it over what it read and compares the result with the nesting the
    message actually had — the only reliable way to know whether an imported structure can
    be expressed at all, rather than restating the rule and hoping the two stay in step.
    """
    by_path = {sequence.path: sequence for sequence in specification.sequences}
    needed: set[tuple[str, int]] = set(addressed)
    # Mandatory root sequences always exist so their missing fields are reported.
    for sequence in specification.sequences:
        if sequence.parent_path is None and sequence.min_occurs >= 1:
            needed.add((sequence.path, 1))
    # A child sequence needs its parent chain present. A child at occurrence N does *not*
    # imply an ancestor at occurrence N: carrying the index up used to build a whole
    # parallel branch, so asking for two penalty details produced two PENA sequences and
    # broke PENA's own 1..1 cardinality. An ancestor repeats only where the caller
    # addressed a field inside that repeat directly; otherwise its first instance is the
    # container.
    for path, occurrence in list(needed):
        current = by_path.get(path)
        level = occurrence
        while current and current.parent_path:
            parent_path = current.parent_path
            if (parent_path, level) not in needed:
                needed.add((parent_path, 1))
                level = 1
            current = by_path.get(parent_path)

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
    return instances


class MtGenerator:
    def supports(self, message_type: str) -> bool:
        return specification_registry.known(message_type)

    def specification(self, message_type: str) -> MessageSpecification:
        return specification_registry.get(message_type)

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
                            f"'{item.id}' is not a field of {specification.message_type}.",
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
                            f"{specification.message_type}.",
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
                            f"{specification.message_type}"
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
            # Every entry point — the browser, the JSON API, Excel and MT import — reaches
            # a value through here, so "what does this field actually hold?" is answered in
            # one place rather than four.
            resolved.append(
                ResolvedField(
                    row=row,
                    occurrence=item.occurrence,
                    value=canonical_field_value(row, item.value.strip()),
                )
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
        #
        # A row that belongs to a choice group is satisfied by any member of that group: a
        # settlement party identified by its BIC and the same party identified by a
        # proprietary scheme are two field options carrying one business value, not two
        # required fields.
        alternatives = _choice_members(specification)
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
            group = choice_key(row.choice_group)
            for occurrence in sequence_occurrences or [1]:
                if (row.row_id, occurrence) in supplied:
                    continue
                if group and any(
                    (member.row_id, occurrence) in supplied for member in alternatives[group]
                ):
                    continue
                if group and row.row_id != alternatives[group][0].row_id:
                    # One message per missing business value, reported against the option
                    # the form offers first, rather than one per field option.
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

        # Two field options for one business value cannot both be present.
        for members in alternatives.values():
            for occurrence in sorted(occurrences):
                present = [
                    member for member in members if (member.row_id, occurrence) in supplied
                ]
                if len(present) > 1:
                    errors.append(
                        _error(
                            "MT_FIELD_OPTION_CONFLICT",
                            f"{present[0].business_name} was identified in more than one way.",
                            layer=ValidationLayer.STRUCTURE,
                            field_name=present[0].business_name,
                            location=present[1].row_id,
                            expected=" or ".join(
                                f"{item.tag} ({_option_label(item)})" for item in members
                            ),
                            suggestion=(
                                "Identify the party once. Remove "
                                f"{present[1].tag} or {present[0].tag}."
                            ),
                        )
                    )

        for item in resolved:
            row = item.row
            value = item.value
            identifier_issue = _identifier_issue(row, value)
            if identifier_issue is not None:
                errors.append(identifier_issue)
                continue
            if not row_format_valid(row, value):
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
            if is_direct_code_field(row.tag, row.allowed_codes) and value not in row.allowed_codes:
                errors.append(
                    _error(
                        "MT_CODE_NOT_ALLOWED",
                        f"{row.business_name} must be one of the supported codes.",
                        layer=ValidationLayer.FORMAT,
                        field_name=row.business_name,
                        location=row.row_id,
                        expected=_code_expectation(row),
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
                    message_type=specification.message_type,
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
        instances = plan_sequences(
            specification, {(item.row.sequence_path, item.occurrence) for item in resolved}
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


def _choice_members(
    specification: MessageSpecification,
) -> dict[str, list[FieldSpecification]]:
    groups: dict[str, list[FieldSpecification]] = {}
    for row in specification.fields:
        key = choice_key(row.choice_group)
        if key:
            groups.setdefault(key, []).append(row)
    for members in groups.values():
        members.sort(key=lambda item: item.row_number)
    return groups


def _option_label(row: FieldSpecification) -> str:
    """The business words for a field option, so an error never says "95P or 95R" alone."""
    if row.tag == "95P":
        return "BIC"
    if row.tag == "95R":
        return "proprietary identifier"
    return f"option {row.option}"


def _code_expectation(row: FieldSpecification) -> str:
    """Allowed codes with the words for them, from the shared code list."""
    from app.knowledge.code_lists import code_lists

    values = code_lists.describe(row.code_list, row.allowed_codes)
    return ", ".join(
        f"{item.code} ({item.label})" if item.label != item.code else item.code
        for item in values
    )


#: What to say for each way an identifier can be wrong. Naming the actual defect is the
#: whole point: "does not match the expected format" sent a tester to re-read a regex.
_ISIN_MESSAGES: dict[IsinProblem, tuple[str, str, str]] = {
    IsinProblem.EMPTY: (
        "MT_ISIN_LENGTH",
        "{name} needs an identifier.",
        "Enter the twelve-character identifier, for example XS0000000009.",
    ),
    IsinProblem.LENGTH: (
        "MT_ISIN_LENGTH",
        "An ISIN must contain exactly 12 characters.",
        "Enter only the 12-character identifier. You do not need to type \u201cISIN\u201d.",
    ),
    IsinProblem.PREFIX_NOT_ALPHABETIC: (
        "MT_ISIN_PREFIX",
        "An ISIN must start with two letters.",
        "The first two characters are the country or issuing prefix, for example XS or US.",
    ),
    IsinProblem.INVALID_CHARACTER: (
        "MT_ISIN_CHARACTER",
        "An ISIN may contain only letters and digits.",
        "Remove spaces, punctuation and any other character.",
    ),
    IsinProblem.CHECK_DIGIT_NOT_NUMERIC: (
        "MT_ISIN_CHECK_DIGIT_NOT_NUMERIC",
        "The final ISIN character must be a numeric check digit.",
        "Check you have copied a real ISIN rather than another kind of identifier.",
    ),
}


def _identifier_issue(row: FieldSpecification, value: str) -> ValidationIssue | None:
    """Verify an identifier field, keeping two different claims apart.

    Shape is an ISO 15022 field-format question and is reported in the FORMAT layer. The
    check digit is an ISO 6166 identifier-quality question — the FIN network does not
    compute it — so it is reported in the CLIENT_PROFILE layer, where a counterparty's own
    requirements live. Collapsing the two would claim a SWIFT rule that does not exist.
    """
    if not (row.literal_prefix and "ISIN" in row.identifier_types):
        return None
    verdict = validate_isin(value)
    if verdict.format_valid and verdict.check_digit_valid:
        return None
    example = _first_example(row) or "For example: XS0000000009"
    if not verdict.format_valid:
        rule_id, message, suggestion = _ISIN_MESSAGES[
            verdict.problem or IsinProblem.INVALID_CHARACTER
        ]
        return _error(
            rule_id,
            message.format(name=row.business_name),
            layer=ValidationLayer.FORMAT,
            field_name=row.business_name,
            location=row.row_id,
            expected="12 characters: two letters, nine letters or digits, one check digit",
            current=value,
            suggestion=f"{suggestion} {example}",
        )
    return _error(
        "MT_ISIN_CHECK_DIGIT_INVALID",
        "The ISIN check digit is not valid.",
        layer=ValidationLayer.CLIENT_PROFILE,
        field_name=row.business_name,
        location=row.row_id,
        expected=(
            f"A final check digit of {verdict.expected_check_digit} for identifier "
            f"{value[:11]}"
        ),
        current=value,
        suggestion=(
            "The last character is derived from the other eleven by the ISO 6166 "
            "calculation, so a mistyped character usually shows up here. Check the "
            f"identifier, or use {value[:11]}{verdict.expected_check_digit}. This is an "
            "identifier-quality rule, not a SWIFT field-format rule."
        ),
    )


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
