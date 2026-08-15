"""ISO 20022 XML composition and validation.

The composer builds the ``Document`` from element-path values, writing children strictly in
specification order so the result is schema-valid by construction. The Business Application
Header is built separately and is profile-driven: the sending and receiving BICs and the
transport wrapper come from the client profile and are never invented.

MX output is structurally prevented from carrying FIN blocks, and MT output is structurally
prevented from carrying XML — the two formats never share a rendering path.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree
from xml.sax.saxutils import escape

from app.profiles.loader import ClientProfile
from app.studio.models import (
    ElementInput,
    EnvelopeField,
    EnvelopeOverride,
    FieldOrigin,
    IssueSeverity,
    Presence,
    RenderedLine,
    ValidationIssue,
    ValidationLayer,
)
from app.studio.mx.models import FlatElement, MxDataType, MxMessageSpec
from app.studio.mx.registry import mx_registry

APPHDR_NAMESPACE = "urn:iso:std:iso:20022:tech:xsd:head.001.001.03"
APPHDR_DEFINITION = "head.001.001.03"

BIC_PATTERN = re.compile(r"^[A-Z0-9]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$")
ISIN_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
LEI_PATTERN = re.compile(r"^[A-Z0-9]{18}[0-9]{2}$")
EXACT4_PATTERN = re.compile(r"^[A-Z0-9]{4}$")
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
DECIMAL_PATTERN = re.compile(r"^-?\d{1,14}(\.\d{1,5})?$")

TEXT_LIMITS: dict[MxDataType, int] = {
    MxDataType.MAX16_TEXT: 16,
    MxDataType.MAX35_TEXT: 35,
    MxDataType.MAX70_TEXT: 70,
    MxDataType.MAX140_TEXT: 140,
    MxDataType.MAX350_TEXT: 350,
}


class MxEnvelopeUnavailable(Exception):
    def __init__(self, issues: list[ValidationIssue]) -> None:
        super().__init__("; ".join(issue.message for issue in issues))
        self.issues = issues


@dataclass
class ResolvedElement:
    flat: FlatElement
    occurrence: int
    value: str
    currency: str | None = None


@dataclass
class MxBuildResult:
    specification: MxMessageSpec
    document: str
    app_hdr: str | None
    xml: str
    envelope_fields: list[EnvelopeField]
    rendered_lines: list[RenderedLine]
    resolved: list[ResolvedElement]
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.xml.encode()).hexdigest()


def _issue(
    rule_id: str,
    message: str,
    *,
    layer: ValidationLayer,
    severity: IssueSeverity = IssueSeverity.ERROR,
    field_name: str | None = None,
    location: str | None = None,
    expected: str | None = None,
    current: str | None = None,
    suggestion: str | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        rule_id=rule_id,
        severity=severity,
        layer=layer,
        field=field_name,
        location=location,
        message=message,
        expected=expected,
        current_value=current,
        suggestion=suggestion,
    )


# --------------------------------------------------------------------------------------
# Value validation
# --------------------------------------------------------------------------------------


def validate_value(flat: FlatElement, value: str) -> tuple[str | None, ValidationIssue | None]:
    """Return the currency component (amounts only) and a format issue if the value is bad."""
    element = flat.element
    data_type = element.data_type
    assert data_type is not None
    label = element.display_name

    def bad(expected: str, suggestion: str) -> ValidationIssue:
        return _issue(
            "MX_FORMAT_INVALID",
            f"{label} does not match the expected format.",
            layer=ValidationLayer.FORMAT,
            field_name=label,
            location=flat.path,
            expected=expected,
            current=value,
            suggestion=suggestion,
        )

    if data_type in TEXT_LIMITS:
        limit = TEXT_LIMITS[data_type]
        if not value or len(value) > limit:
            return None, bad(
                f"1 to {limit} characters",
                f"Shorten the value to {limit} characters or fewer.",
            )
        return None, None
    if data_type is MxDataType.EXACT4_ALPHANUMERIC:
        if not EXACT4_PATTERN.fullmatch(value):
            return None, bad("Exactly 4 uppercase letters or digits", "Use a 4-character code.")
        return None, None
    if data_type is MxDataType.ISIN:
        if not ISIN_PATTERN.fullmatch(value):
            return None, bad(
                "A 12-character ISIN",
                "Enter the ISIN on its own, for example XS0000000001, without the MT "
                "'ISIN ' prefix.",
            )
        return None, None
    if data_type is MxDataType.ANY_BIC:
        if not BIC_PATTERN.fullmatch(value):
            return None, bad("An 8- or 11-character BIC", "Enter a valid BIC, e.g. DEMOGB2LXXX.")
        return None, None
    if data_type is MxDataType.LEI:
        if not LEI_PATTERN.fullmatch(value):
            return None, bad("A 20-character LEI", "Enter a valid Legal Entity Identifier.")
        return None, None
    if data_type is MxDataType.ISO_DATE:
        try:
            date.fromisoformat(value)
        except ValueError:
            return None, bad(
                "An ISO date, YYYY-MM-DD",
                "MX uses YYYY-MM-DD, not the MT format YYYYMMDD. "
                + (f"Try {value[:4]}-{value[4:6]}-{value[6:8]}." if len(value) == 8 else ""),
            )
        return None, None
    if data_type is MxDataType.ISO_DATE_TIME:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None, bad(
                "An ISO date and time",
                "Use YYYY-MM-DDThh:mm:ss with an optional time zone.",
            )
        return None, None
    if data_type is MxDataType.DECIMAL:
        if not DECIMAL_PATTERN.fullmatch(value):
            return None, bad(
                "A decimal number using a full stop separator",
                "MX uses a full stop as the decimal separator, not the MT comma.",
            )
        try:
            if Decimal(value) <= 0:
                return None, _issue(
                    "MX_QUANTITY_NOT_POSITIVE",
                    f"{label} must be greater than zero.",
                    layer=ValidationLayer.BUSINESS_RULES,
                    field_name=label,
                    location=flat.path,
                    current=value,
                    suggestion="Enter a positive quantity.",
                )
        except InvalidOperation:
            return None, bad("A decimal number", "Enter a numeric value.")
        return None, None
    if data_type is MxDataType.AMOUNT:
        parts = value.replace(" ", " ").split()
        if len(parts) != 2:
            return None, bad(
                "CURRENCY AMOUNT, for example USD 25000.00",
                "Write the three-letter currency, a space, then the amount.",
            )
        currency, amount_text = parts[0].upper(), parts[1]
        if not CURRENCY_PATTERN.fullmatch(currency):
            return None, bad(
                "A three-letter ISO currency code",
                "For example USD, EUR or GBP.",
            )
        if not DECIMAL_PATTERN.fullmatch(amount_text):
            return None, bad(
                "A decimal amount using a full stop separator",
                "MX uses a full stop as the decimal separator, not the MT comma.",
            )
        try:
            if Decimal(amount_text) <= 0:
                return currency, _issue(
                    "MX_AMOUNT_NOT_POSITIVE",
                    f"{label} must be greater than zero.",
                    layer=ValidationLayer.BUSINESS_RULES,
                    field_name=label,
                    location=flat.path,
                    current=value,
                    suggestion="Enter a positive amount.",
                )
        except InvalidOperation:
            return currency, bad("A decimal amount", "Enter a numeric amount.")
        return currency, None
    if data_type is MxDataType.CODE:
        if value not in element.codes:
            return None, _issue(
                "MX_CODE_NOT_ALLOWED",
                f"{label} must be one of the supported codes.",
                layer=ValidationLayer.FORMAT,
                field_name=label,
                location=flat.path,
                expected=", ".join(element.codes),
                current=value,
                suggestion=f"Use {element.codes[0]}.",
            )
        return None, None
    if data_type is MxDataType.YES_NO:
        if value.lower() not in {"true", "false"}:
            return None, bad("true or false", "Enter true or false.")
        return None, None
    return None, None


# --------------------------------------------------------------------------------------
# Composition
# --------------------------------------------------------------------------------------


class MxGenerator:
    def supports(self, message_type: str) -> bool:
        return mx_registry.known(message_type)

    def specification(self, message_type: str) -> MxMessageSpec:
        return mx_registry.get(message_type)

    def resolve(
        self, spec: MxMessageSpec, inputs: list[ElementInput]
    ) -> tuple[list[ResolvedElement], list[ValidationIssue]]:
        by_path = mx_registry.by_path(spec.message_type)
        root = f"/{spec.document_element}/{spec.message_root}"
        resolved: list[ResolvedElement] = []
        issues: list[ValidationIssue] = []
        seen: set[tuple[str, int]] = set()

        for index, item in enumerate(inputs, start=1):
            path = item.path.strip()
            if not path.startswith("/"):
                path = f"{root}/{path.lstrip('/')}"
            path = re.sub(r"/{2,}", "/", path).rstrip("/")
            flat = by_path.get(path)
            if flat is None:
                issues.append(
                    _issue(
                        "MX_UNKNOWN_ELEMENT",
                        f"'{item.path}' is not an element of {spec.message_type}.",
                        layer=ValidationLayer.STRUCTURE,
                        location=f"input[{index}]",
                        current=item.path,
                        suggestion="Download the MX Excel template or read the message "
                        "specification for the supported element paths.",
                    )
                )
                continue
            if not flat.element.is_leaf:
                issues.append(
                    _issue(
                        "MX_CONTAINER_NOT_A_VALUE",
                        f"'{path}' is a container. Supply values for its child elements.",
                        layer=ValidationLayer.CANONICAL,
                        field_name=flat.element.display_name,
                        location=path,
                        expected=", ".join(
                            f"{path}/{child.name}" for child in flat.element.children
                        ),
                        suggestion="Address a leaf element that holds a value.",
                    )
                )
                continue
            key = (path, item.occurrence)
            if key in seen:
                issues.append(
                    _issue(
                        "MX_DUPLICATE_ELEMENT",
                        f"{flat.element.display_name} was supplied more than once for "
                        f"occurrence {item.occurrence}.",
                        layer=ValidationLayer.CANONICAL,
                        field_name=flat.element.display_name,
                        location=path,
                        suggestion="Remove the duplicate row, or increment Occurrence.",
                    )
                )
                continue
            seen.add(key)
            currency, format_issue = validate_value(flat, item.value.strip())
            if format_issue is not None:
                issues.append(format_issue)
                continue
            resolved.append(
                ResolvedElement(
                    flat=flat,
                    occurrence=item.occurrence,
                    value=item.value.strip(),
                    currency=currency,
                )
            )
        return resolved, issues

    def validate_structure(
        self, spec: MxMessageSpec, resolved: list[ResolvedElement]
    ) -> list[ValidationIssue]:
        """Check mandatory chains, choices, cardinality and configured business rules."""
        issues: list[ValidationIssue] = []
        supplied_paths = {item.flat.path for item in resolved}
        by_path = mx_registry.by_path(spec.message_type)

        def branch_used(container_path: str) -> bool:
            prefix = container_path + "/"
            return any(path.startswith(prefix) for path in supplied_paths)

        for flat in mx_registry.flat(spec.message_type):
            element = flat.element
            parent = by_path.get(flat.parent_path or "")
            parent_present = parent is None or branch_used(parent.path)
            if element.presence is Presence.MANDATORY and parent_present:
                if element.is_leaf:
                    if flat.path not in supplied_paths:
                        issues.append(
                            _issue(
                                "MX_MANDATORY_ELEMENT_MISSING",
                                f"{element.display_name} is required.",
                                layer=ValidationLayer.STRUCTURE,
                                field_name=element.display_name,
                                location=flat.path,
                                expected=element.format_text(),
                                suggestion=(
                                    f"For example: {element.examples[0].value}"
                                    if element.examples
                                    else f"Provide {element.display_name}."
                                ),
                            )
                        )
                elif not branch_used(flat.path):
                    leaf_hint = next(
                        (
                            item.path
                            for item in mx_registry.flat(spec.message_type)
                            if item.path.startswith(flat.path + "/")
                            and item.element.is_leaf
                            and item.element.presence is Presence.MANDATORY
                        ),
                        None,
                    )
                    issues.append(
                        _issue(
                            "MX_MANDATORY_BLOCK_MISSING",
                            f"{element.display_name} is required but no value was supplied "
                            "for any of its elements.",
                            layer=ValidationLayer.STRUCTURE,
                            field_name=element.display_name,
                            location=flat.path,
                            expected=leaf_hint,
                            suggestion=(
                                f"Supply a value for {leaf_hint}." if leaf_hint else None
                            ),
                        )
                    )
            if element.choice and branch_used(flat.path):
                chosen = [
                    child
                    for child in element.children
                    if branch_used(f"{flat.path}/{child.name}")
                    or f"{flat.path}/{child.name}" in supplied_paths
                ]
                if len(chosen) > 1:
                    issues.append(
                        _issue(
                            "MX_CHOICE_VIOLATION",
                            f"{element.display_name} accepts exactly one of its options, "
                            f"but {len(chosen)} were supplied.",
                            layer=ValidationLayer.STRUCTURE,
                            field_name=element.display_name,
                            location=flat.path,
                            expected=", ".join(child.name for child in element.children),
                            current=", ".join(child.name for child in chosen),
                            suggestion="Remove all but one option.",
                        )
                    )
            if element.max_occurs == 1:
                repeated = [item for item in resolved if item.flat.path == flat.path]
                if len(repeated) > 1:
                    issues.append(
                        _issue(
                            "MX_CARDINALITY_EXCEEDED",
                            f"{element.display_name} may appear once, but "
                            f"{len(repeated)} values were supplied.",
                            layer=ValidationLayer.STRUCTURE,
                            field_name=element.display_name,
                            location=flat.path,
                            expected="1 occurrence",
                            suggestion="Remove the extra occurrences.",
                        )
                    )
        issues.extend(self._business_rules(spec, resolved))
        return issues

    @staticmethod
    def _business_rules(
        spec: MxMessageSpec, resolved: list[ResolvedElement]
    ) -> list[ValidationIssue]:
        """Configured cross-element rules for the securities settlement subsets."""
        issues: list[ValidationIssue] = []
        by_business: dict[str, ResolvedElement] = {
            item.flat.element.business_path: item
            for item in resolved
            if item.flat.element.business_path
        }
        by_path = {item.flat.path: item for item in resolved}
        root = f"/{spec.document_element}/{spec.message_root}"

        trade = by_business.get("trade.tradeDate")
        settlement = by_business.get("trade.settlementDate")
        if trade and settlement:
            try:
                if date.fromisoformat(settlement.value) < date.fromisoformat(trade.value):
                    issues.append(
                        _issue(
                            "SETTLEMENT_DATE_BEFORE_TRADE_DATE",
                            "The settlement date is earlier than the trade date.",
                            layer=ValidationLayer.BUSINESS_RULES,
                            field_name=settlement.flat.element.display_name,
                            location=settlement.flat.path,
                            expected=f"A date on or after {trade.value}",
                            current=settlement.value,
                            suggestion="Set the settlement date on or after the trade date.",
                        )
                    )
            except ValueError:
                pass

        # The amount rule is driven by the specification rather than a fixed path, so it
        # applies to any configured message that has a currency-and-amount element and stays
        # silent for messages such as a status advice that have none.
        payment_element = by_business.get("paymentType")
        payment = payment_element.value if payment_element else None
        amount_leaves = [
            item
            for item in mx_registry.leaves(spec.message_type)
            if item.element.data_type is MxDataType.AMOUNT
        ]
        amount = next(
            (item for item in resolved if item.flat.element.data_type is MxDataType.AMOUNT),
            None,
        )
        if payment == "APMT" and amount_leaves and amount is None:
            target = amount_leaves[0]
            issues.append(
                _issue(
                    "MX_AMOUNT_REQUIRED_FOR_APMT",
                    "An against-payment message needs a settlement amount.",
                    layer=ValidationLayer.BUSINESS_RULES,
                    field_name=target.element.display_name,
                    location=target.path,
                    expected=target.path,
                    suggestion="Add the settlement amount, or change Payment to FREE.",
                )
            )
        if payment == "FREE" and amount is not None:
            issues.append(
                _issue(
                    "MX_AMOUNT_NOT_ALLOWED_FOR_FREE",
                    "A free-of-payment message must not carry a settlement amount.",
                    layer=ValidationLayer.BUSINESS_RULES,
                    field_name=amount.flat.element.display_name,
                    location=amount.flat.path,
                    current=amount.value,
                    suggestion="Remove the settlement amount, or change Payment to APMT.",
                )
            )

        movement_element = by_business.get("direction")
        movement = movement_element.value if movement_element else None
        if movement and spec.message_type == "sese.023":
            delivering = any(
                path.startswith(f"{root}/DlvrgSttlmPties/") for path in by_path
            )
            receiving = any(path.startswith(f"{root}/RcvgSttlmPties/") for path in by_path)
            if movement == "RECE" and not delivering:
                issues.append(
                    _issue(
                        "MX_DELIVERING_PARTIES_REQUIRED",
                        "A receipt instruction must state who is delivering the securities.",
                        layer=ValidationLayer.BUSINESS_RULES,
                        field_name="Delivering Settlement Parties",
                        location=f"{root}/DlvrgSttlmPties",
                        expected=f"{root}/DlvrgSttlmPties/Pty1/Id/AnyBIC",
                        suggestion="Add the delivering agent BIC.",
                    )
                )
            if movement == "DELI" and not receiving:
                issues.append(
                    _issue(
                        "MX_RECEIVING_PARTIES_REQUIRED",
                        "A delivery instruction must state who is receiving the securities.",
                        layer=ValidationLayer.BUSINESS_RULES,
                        field_name="Receiving Settlement Parties",
                        location=f"{root}/RcvgSttlmPties",
                        expected=f"{root}/RcvgSttlmPties/Pty1/Id/AnyBIC",
                        suggestion="Add the receiving agent BIC.",
                    )
                )
        return issues

    def validate_profile(
        self, profile: ClientProfile, resolved: list[ResolvedElement]
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        rule = profile.validation.sender_reference
        for item in resolved:
            business_path = item.flat.element.business_path
            if business_path == "senderReference" and len(item.value) > rule.max_length:
                issues.append(
                    _issue(
                        "PROFILE_SENDER_REFERENCE_TOO_LONG",
                        f"{profile.name} allows a transaction identification of at most "
                        f"{rule.max_length} characters.",
                        layer=ValidationLayer.CLIENT_PROFILE,
                        field_name=item.flat.element.display_name,
                        location=item.flat.path,
                        expected=f"At most {rule.max_length} characters",
                        current=item.value,
                        suggestion="Shorten the reference.",
                    )
                )
            if item.currency and item.currency not in profile.allowed_currencies:
                issues.append(
                    _issue(
                        "PROFILE_CURRENCY_NOT_ALLOWED",
                        f"{profile.name} does not allow settlement in {item.currency}.",
                        layer=ValidationLayer.CLIENT_PROFILE,
                        field_name=item.flat.element.display_name,
                        location=item.flat.path,
                        expected=", ".join(profile.allowed_currencies),
                        current=item.currency,
                        suggestion=f"Use {profile.allowed_currencies[0]}.",
                    )
                )
        return issues

    # -- rendering ---------------------------------------------------------------------

    def compose_document(
        self, spec: MxMessageSpec, resolved: list[ResolvedElement], *, pretty: bool = True
    ) -> str:
        """Build the Document, writing children strictly in specification order."""
        values: dict[tuple[str, int], ResolvedElement] = {
            (item.flat.path, item.occurrence): item for item in resolved
        }
        present_paths = {item.flat.path for item in resolved}

        def used(path: str) -> bool:
            prefix = path + "/"
            return path in present_paths or any(
                candidate.startswith(prefix) for candidate in present_paths
            )

        lines: list[str] = []
        indent = "  " if pretty else ""
        newline = "\n" if pretty else ""

        def write(elements, parent_path: str, depth: int) -> None:  # type: ignore[no-untyped-def]
            for element in elements:
                path = f"{parent_path}/{element.name}"
                if not used(path):
                    continue
                occurrences = sorted(
                    {
                        occurrence
                        for candidate, occurrence in values
                        if candidate == path or candidate.startswith(path + "/")
                    }
                ) or [1]
                if element.max_occurs == 1:
                    occurrences = [occurrences[0]]
                for occurrence in occurrences:
                    pad = indent * depth
                    if element.is_leaf:
                        item = values.get((path, occurrence))
                        if item is None:
                            continue
                        attributes = ""
                        text = item.value
                        if element.currency_attribute and item.currency:
                            amount = item.value.split()[1]
                            attributes = f' Ccy="{item.currency}"'
                            text = amount
                        lines.append(
                            f"{pad}<{element.name}{attributes}>{escape(text)}"
                            f"</{element.name}>"
                        )
                    else:
                        lines.append(f"{pad}<{element.name}>")
                        write(element.children, path, depth + 1)
                        lines.append(f"{pad}</{element.name}>")

        root = f"/{spec.document_element}/{spec.message_root}"
        lines.append(f'<{spec.document_element} xmlns="{spec.namespace}">')
        lines.append(f"{indent}<{spec.message_root}>")
        write(spec.structure, root, 2)
        lines.append(f"{indent}</{spec.message_root}>")
        lines.append(f"</{spec.document_element}>")
        return newline.join(lines) if pretty else "".join(lines)

    def compose_app_hdr(
        self,
        spec: MxMessageSpec,
        profile: ClientProfile,
        override: EnvelopeOverride | None,
    ) -> tuple[str, list[EnvelopeField]]:
        """Build the head.001.001.03 Business Application Header.

        :raises MxEnvelopeUnavailable: when the sending or receiving BIC is neither
            supplied on the request nor configured on the profile.
        """
        configured = profile.mx_envelope
        override = override or EnvelopeOverride()
        issues: list[ValidationIssue] = []

        sender = override.sender or (configured.from_bic if configured else None)
        receiver = override.receiver or (configured.to_bic if configured else None)
        sender_origin = (
            FieldOrigin.USER_ENTERED if override.sender else FieldOrigin.PROFILE_CONFIGURED
        )
        receiver_origin = (
            FieldOrigin.USER_ENTERED if override.receiver else FieldOrigin.PROFILE_CONFIGURED
        )

        if not sender:
            issues.append(
                _issue(
                    "MX_APPHDR_SENDER_NOT_CONFIGURED",
                    "The Business Application Header needs a sending BIC.",
                    layer=ValidationLayer.APPHDR_CONSISTENCY,
                    field_name="Fr/FIId/FinInstnId/BICFI",
                    suggestion="Configure mxEnvelope.fromBic on the client profile, or send "
                    "envelope.sender.",
                )
            )
        elif not BIC_PATTERN.fullmatch(sender):
            issues.append(
                _issue(
                    "MX_APPHDR_SENDER_INVALID",
                    f"Sending BIC '{sender}' is not a valid BIC.",
                    layer=ValidationLayer.APPHDR_CONSISTENCY,
                    field_name="Fr/FIId/FinInstnId/BICFI",
                    current=sender,
                    suggestion="Use an 8- or 11-character BIC.",
                )
            )
        if not receiver:
            issues.append(
                _issue(
                    "MX_APPHDR_RECEIVER_NOT_CONFIGURED",
                    "The Business Application Header needs a receiving BIC.",
                    layer=ValidationLayer.APPHDR_CONSISTENCY,
                    field_name="To/FIId/FinInstnId/BICFI",
                    suggestion="Configure mxEnvelope.toBic on the client profile, or send "
                    "envelope.receiver.",
                )
            )
        elif not BIC_PATTERN.fullmatch(receiver):
            issues.append(
                _issue(
                    "MX_APPHDR_RECEIVER_INVALID",
                    f"Receiving BIC '{receiver}' is not a valid BIC.",
                    layer=ValidationLayer.APPHDR_CONSISTENCY,
                    field_name="To/FIId/FinInstnId/BICFI",
                    current=receiver,
                    suggestion="Use an 8- or 11-character BIC.",
                )
            )
        if issues:
            raise MxEnvelopeUnavailable(issues)
        assert sender is not None and receiver is not None

        business_identifier = override.business_message_identifier or _derive_bizmsgidr(spec)
        identifier_origin = (
            FieldOrigin.USER_ENTERED
            if override.business_message_identifier
            else FieldOrigin.APPLICATION_GENERATED
        )
        creation = override.creation_date or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        creation_origin = (
            FieldOrigin.USER_ENTERED
            if override.creation_date
            else FieldOrigin.APPLICATION_GENERATED
        )
        business_service = configured.business_service if configured else None
        priority = configured.priority if configured else None

        lines = [f'<AppHdr xmlns="{APPHDR_NAMESPACE}">']
        lines.append("  <Fr>")
        lines.append("    <FIId>")
        lines.append("      <FinInstnId>")
        lines.append(f"        <BICFI>{escape(sender)}</BICFI>")
        lines.append("      </FinInstnId>")
        lines.append("    </FIId>")
        lines.append("  </Fr>")
        lines.append("  <To>")
        lines.append("    <FIId>")
        lines.append("      <FinInstnId>")
        lines.append(f"        <BICFI>{escape(receiver)}</BICFI>")
        lines.append("      </FinInstnId>")
        lines.append("    </FIId>")
        lines.append("  </To>")
        lines.append(f"  <BizMsgIdr>{escape(business_identifier)}</BizMsgIdr>")
        lines.append(f"  <MsgDefIdr>{escape(spec.version)}</MsgDefIdr>")
        if business_service:
            lines.append(f"  <BizSvc>{escape(business_service)}</BizSvc>")
        lines.append(f"  <CreDt>{escape(creation)}</CreDt>")
        if priority:
            lines.append(f"  <Prty>{escape(priority)}</Prty>")
        lines.append("</AppHdr>")

        fields = [
            EnvelopeField(
                block="AppHdr",
                name="From (Fr/FIId/FinInstnId/BICFI)",
                value=sender,
                origin=sender_origin,
                explanation="Sending institution BIC.",
            ),
            EnvelopeField(
                block="AppHdr",
                name="To (To/FIId/FinInstnId/BICFI)",
                value=receiver,
                origin=receiver_origin,
                explanation="Receiving institution BIC.",
            ),
            EnvelopeField(
                block="AppHdr",
                name="Business Message Identifier (BizMsgIdr)",
                value=business_identifier,
                origin=identifier_origin,
                explanation="Identifies this business message to the receiving party.",
            ),
            EnvelopeField(
                block="AppHdr",
                name="Message Definition Identifier (MsgDefIdr)",
                value=spec.version,
                origin=FieldOrigin.APPLICATION_GENERATED,
                explanation="Derived from the selected message version so the header and the "
                "document always agree.",
            ),
            EnvelopeField(
                block="AppHdr",
                name="Business Service (BizSvc)",
                value=business_service,
                origin=FieldOrigin.PROFILE_CONFIGURED,
                explanation=(
                    "Business service configured on the client profile."
                    if business_service
                    else "No business service is configured, so BizSvc is not written."
                ),
            ),
            EnvelopeField(
                block="AppHdr",
                name="Creation Date (CreDt)",
                value=creation,
                origin=creation_origin,
                explanation="Header creation timestamp in UTC.",
            ),
            EnvelopeField(
                block="AppHdr",
                name="Signature (Sgntr)",
                value=None,
                origin=FieldOrigin.NETWORK_GENERATED,
                explanation="Digital signatures are applied by the messaging infrastructure "
                "and are never fabricated here.",
            ),
        ]
        return "\n".join(lines), fields

    def build(
        self,
        message_type: str,
        profile: ClientProfile,
        inputs: list[ElementInput],
        *,
        envelope: EnvelopeOverride | None = None,
        include_app_hdr: bool = True,
    ) -> MxBuildResult:
        spec = self.specification(message_type)
        resolved, address_issues = self.resolve(spec, inputs)
        errors = [
            *address_issues,
            *self.validate_structure(spec, resolved),
            *self.validate_profile(profile, resolved),
        ]
        warnings: list[ValidationIssue] = []

        document = self.compose_document(spec, resolved)
        app_hdr: str | None = None
        envelope_fields: list[EnvelopeField] = []
        if include_app_hdr:
            try:
                app_hdr, envelope_fields = self.compose_app_hdr(spec, profile, envelope)
            except MxEnvelopeUnavailable as unavailable:
                warnings.extend(
                    issue.model_copy(update={"severity": IssueSeverity.WARNING})
                    for issue in unavailable.issues
                )

        xml, wrapper_warning = self._wrap(profile, app_hdr, document)
        if wrapper_warning:
            warnings.append(wrapper_warning)

        rendered_lines = self._rendered_lines(spec, xml, resolved)
        return MxBuildResult(
            specification=spec,
            document=document,
            app_hdr=app_hdr,
            xml=xml,
            envelope_fields=envelope_fields,
            rendered_lines=rendered_lines,
            resolved=resolved,
            errors=errors,
            warnings=warnings,
        )

    @staticmethod
    def _wrap(
        profile: ClientProfile, app_hdr: str | None, document: str
    ) -> tuple[str, ValidationIssue | None]:
        """Apply the profile-configured transport wrapper. Never invent one."""
        declaration = '<?xml version="1.0" encoding="UTF-8"?>'
        configured = profile.mx_envelope
        wrapper = configured.wrapper_element if configured else None
        if not wrapper:
            if app_hdr:
                return (
                    f"{declaration}\n{document}",
                    _issue(
                        "MX_WRAPPER_NOT_CONFIGURED",
                        "No transport wrapper is configured for this profile, so the combined "
                        "output contains the Document only.",
                        layer=ValidationLayer.APPHDR_CONSISTENCY,
                        severity=IssueSeverity.WARNING,
                        suggestion="Download the AppHdr separately, or configure "
                        "mxEnvelope.wrapperElement on the client profile.",
                    ),
                )
            return f"{declaration}\n{document}", None
        indented_hdr = "\n".join(f"  {line}" for line in app_hdr.splitlines()) if app_hdr else ""
        indented_doc = "\n".join(f"  {line}" for line in document.splitlines())
        body = f"{indented_hdr}\n{indented_doc}" if app_hdr else indented_doc
        return f"{declaration}\n<{wrapper}>\n{body}\n</{wrapper}>", None

    @staticmethod
    def _rendered_lines(
        spec: MxMessageSpec, xml: str, resolved: list[ResolvedElement]
    ) -> list[RenderedLine]:
        by_name: dict[str, ResolvedElement] = {}
        for resolved_item in resolved:
            by_name.setdefault(resolved_item.flat.element.name, resolved_item)
        lines: list[RenderedLine] = []
        for number, text in enumerate(xml.splitlines(), start=1):
            stripped = text.strip()
            match = re.match(r"<([A-Za-z0-9]+)[ >]", stripped)
            item: ResolvedElement | None = by_name.get(match.group(1)) if match else None
            if item is not None and stripped.endswith(f"</{item.flat.element.name}>"):
                lines.append(
                    RenderedLine(
                        line_number=number,
                        text=text,
                        field_id=item.flat.path,
                        display_name=item.flat.element.display_name,
                        origin=FieldOrigin.USER_ENTERED,
                    )
                )
            else:
                is_header = "AppHdr" in text or "xml version" in text
                lines.append(
                    RenderedLine(
                        line_number=number,
                        text=text,
                        display_name="Business Application Header" if is_header else None,
                        origin=FieldOrigin.APPLICATION_GENERATED,
                    )
                )
        return lines


def check_well_formed(xml: str) -> ValidationIssue | None:
    try:
        ElementTree.fromstring(xml)
    except ElementTree.ParseError as error:
        return _issue(
            "MX_XML_NOT_WELL_FORMED",
            f"The generated XML is not well formed: {error}",
            layer=ValidationLayer.XML_WELL_FORMED,
            suggestion="This indicates a platform defect. Report the scenario.",
        )
    return None


def _derive_bizmsgidr(spec: MxMessageSpec) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"{spec.message_type.replace('.', '').upper()}{stamp}"


mx_generator = MxGenerator()
