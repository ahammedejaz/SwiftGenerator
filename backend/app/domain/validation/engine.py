import re
from typing import Any

from app.domain.enums import (
    GenerationMode,
    Lifecycle,
    MessageType,
    PaymentType,
    Severity,
    ValidationStatus,
)
from app.domain.missing_fields import get_value
from app.domain.models import (
    MessageResolutionRequest,
    SettlementScenario,
    ValidationFinding,
    ValidationReport,
)
from app.domain.resolver import resolve_message_type
from app.domain.statuses import statuses
from app.profiles.loader import ClientProfile

ISIN_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
UPPER_REFERENCE_PATTERN = re.compile(r"^[A-Z0-9]+$")


def _finding(
    rule_id: str,
    field_path: str | None,
    message: str,
    technical: str,
    *,
    current: Any = None,
    expected: str | None = None,
    suggestion: str | None = None,
    severity: Severity = Severity.ERROR,
) -> ValidationFinding:
    return ValidationFinding(
        rule_id=rule_id,
        severity=severity,
        field_path=field_path,
        message=message,
        technical_explanation=technical,
        current_value=current,
        expected_condition=expected,
        suggestion=suggestion,
    )


def validate_scenario(
    scenario: SettlementScenario,
    profile: ClientProfile,
) -> ValidationReport:
    findings: list[ValidationFinding] = []

    if scenario.message_type is None:
        findings.append(
            _finding(
                "MESSAGE-TYPE-REQUIRED",
                "messageType",
                "A message type could not be resolved.",
                "The deterministic composer requires a supported resolved message type.",
                suggestion="Provide direction and payment type so the message can be resolved.",
            )
        )
    elif scenario.message_type not in profile.supported_message_types:
        findings.append(
            _finding(
                "PROFILE-MESSAGE-NOT-SUPPORTED",
                "messageType",
                f"{scenario.message_type.value} is not enabled by this profile.",
                "The selected profile contains an explicit supported-message allowlist.",
                current=scenario.message_type.value,
                expected="A message type enabled by the selected profile",
            )
        )
    else:
        for path in profile.requirements_for(scenario.message_type):
            if get_value(scenario, path) in (None, ""):
                findings.append(
                    _finding(
                        f"{scenario.message_type.value}-{path.upper().replace('.', '-')}-REQUIRED",
                        path,
                        f"{_friendly_name(path)} is required for this message and profile.",
                        "The field is listed in the versioned profile requirements.",
                        expected="A non-empty value",
                        suggestion=f"Provide {_friendly_name(path).lower()}.",
                    )
                )

    if scenario.sender_reference:
        max_length = profile.validation.sender_reference.max_length
        if len(scenario.sender_reference) > max_length:
            findings.append(
                _finding(
                    "SENDER-REFERENCE-MAX-LENGTH",
                    "senderReference",
                    f"Sender reference must not exceed {max_length} characters for this profile.",
                    "The client-profile sender-reference length rule was exceeded.",
                    current=scenario.sender_reference,
                    expected=f"At most {max_length} characters",
                    suggestion="Use a shorter synthetic sender reference.",
                )
            )
        if profile.validation.sender_reference.uppercase and not UPPER_REFERENCE_PATTERN.fullmatch(
            scenario.sender_reference
        ):
            findings.append(
                _finding(
                    "SENDER-REFERENCE-FORMAT",
                    "senderReference",
                    "Sender reference must contain uppercase letters and digits only.",
                    "The demonstration profile applies an uppercase alphanumeric format.",
                    current=scenario.sender_reference,
                    expected="Uppercase A-Z and digits 0-9",
                    suggestion=(
                        "Remove spaces and punctuation and convert the reference to uppercase."
                    ),
                )
            )

    if scenario.security.identifier and not ISIN_PATTERN.fullmatch(scenario.security.identifier):
        findings.append(
            _finding(
                "SECURITY-ISIN-FORMAT",
                "security.identifier",
                "The synthetic ISIN does not match the supported 12-character format.",
                "This prototype checks format only and does not certify the identifier.",
                current=scenario.security.identifier,
                expected="Two letters followed by nine alphanumeric characters and one digit",
                suggestion="Use a clearly synthetic identifier in the supported format.",
            )
        )

    if scenario.security.quantity is not None and scenario.security.quantity <= 0:
        findings.append(
            _finding(
                "SECURITY-QUANTITY-POSITIVE",
                "security.quantity",
                "Security quantity must be greater than zero.",
                "The canonical quantity must be a positive decimal.",
                current=str(scenario.security.quantity),
                expected="A value greater than zero",
            )
        )

    if scenario.settlement.amount is not None and scenario.settlement.amount <= 0:
        findings.append(
            _finding(
                "SETTLEMENT-AMOUNT-POSITIVE",
                "settlement.amount",
                "Settlement amount must be greater than zero.",
                "The canonical cash amount must be a positive decimal.",
                current=str(scenario.settlement.amount),
                expected="A value greater than zero",
            )
        )

    if (
        scenario.trade.trade_date
        and scenario.trade.settlement_date
        and scenario.trade.settlement_date < scenario.trade.trade_date
    ):
        findings.append(
            _finding(
                "SETTLEMENT-DATE-NOT-BEFORE-TRADE",
                "trade.settlementDate",
                "Settlement date must not be earlier than trade date.",
                "The normal positive scenario requires chronological trade and settlement dates.",
                current=scenario.trade.settlement_date.isoformat(),
                expected=f"On or after {scenario.trade.trade_date.isoformat()}",
                suggestion="Correct the settlement date or use an enabled negative-test mutation.",
            )
        )

    if scenario.settlement.currency:
        currency = scenario.settlement.currency.upper()
        if currency not in profile.allowed_currencies:
            findings.append(
                _finding(
                    "PROFILE-CURRENCY-NOT-ALLOWED",
                    "settlement.currency",
                    f"Currency {currency} is not allowed by this client profile.",
                    "The currency is absent from the profile allowlist.",
                    current=currency,
                    expected=", ".join(profile.allowed_currencies),
                    suggestion="Choose an allowed demonstration currency.",
                )
            )

    if scenario.direction and scenario.payment_type and scenario.message_type:
        resolution = resolve_message_type(
            MessageResolutionRequest(
                lifecycle=scenario.lifecycle,
                direction=scenario.direction,
                payment_type=scenario.payment_type,
            )
        )
        if resolution.resolved_message_type != scenario.message_type:
            findings.append(
                _finding(
                    "MESSAGE-TYPE-BUSINESS-MISMATCH",
                    "messageType",
                    "The message type does not match the scenario direction and payment type.",
                    "Message selection is determined by the approved resolver table.",
                    current=scenario.message_type.value,
                    expected=(
                        resolution.resolved_message_type.value
                        if resolution.resolved_message_type
                        else "Resolvable instruction type"
                    ),
                )
            )

    if scenario.payment_type == PaymentType.FREE_OF_PAYMENT and (
        scenario.settlement.currency is not None or scenario.settlement.amount is not None
    ):
        findings.append(
            _finding(
                "FOP-CASH-LEG-NOT-ALLOWED",
                "settlement.amount",
                "A Free of Payment scenario must not include a settlement cash leg.",
                "FOP instruction and confirmation engines omit settlement currency and amount.",
                current=f"{scenario.settlement.currency or ''}{scenario.settlement.amount or ''}",
                expected="No settlement currency or amount",
                suggestion="Remove the cash fields or choose Against Payment.",
            )
        )

    if scenario.function and scenario.function.value == "CANC" and not scenario.related_reference:
        findings.append(
            _finding(
                "CANCELLATION-PREVIOUS-REFERENCE-REQUIRED",
                "relatedReference",
                "A cancellation requires the previous instruction reference.",
                "The supported cancellation subset must identify the message being cancelled.",
                expected="A non-empty previous reference",
            )
        )

    if (
        scenario.message_type
        in {
            MessageType.MT544,
            MessageType.MT545,
            MessageType.MT546,
            MessageType.MT547,
        }
        and scenario.lifecycle != Lifecycle.CONFIRMATION
    ):
        findings.append(
            _finding(
                "CONFIRMATION-LIFECYCLE",
                "lifecycle",
                f"{scenario.message_type.value} must be a confirmation.",
                "Confirmation message types are generated from supported instructions.",
                current=scenario.lifecycle.value,
                expected="CONFIRMATION",
            )
        )

    if scenario.message_type == MessageType.MT548 and scenario.status.category:
        definition = statuses.get(scenario.status.category)
        if scenario.status.code and scenario.status.code != definition.code:
            findings.append(
                _finding(
                    "MT548-STATUS-CODE-COMBINATION",
                    "status.code",
                    "The status code does not match the selected status category.",
                    "Status category and code combinations come from controlled configuration.",
                    current=scenario.status.code,
                    expected=definition.code,
                )
            )
        if scenario.status.reason_code and not statuses.validate_reason(
            scenario.status.category, scenario.status.reason_code
        ):
            findings.append(
                _finding(
                    "MT548-STATUS-REASON-COMBINATION",
                    "status.reasonCode",
                    "The reason code is not valid for the selected status category.",
                    "Status and reason combinations come from controlled configuration.",
                    current=scenario.status.reason_code,
                    expected=", ".join(definition.reasons),
                )
            )

    errors = sum(item.severity == Severity.ERROR for item in findings)
    warnings = sum(item.severity == Severity.WARNING for item in findings)
    status = ValidationStatus.VALID if errors == 0 else ValidationStatus.INVALID
    if scenario.test_configuration.mode == GenerationMode.NEGATIVE_TEST and errors:
        status = ValidationStatus.INTENTIONALLY_INVALID
    return ValidationReport(
        status=status,
        profile_id=profile.profile_id,
        profile_version=profile.version,
        findings=findings,
        error_count=errors,
        warning_count=warnings,
    )


def _friendly_name(path: str) -> str:
    return path.split(".")[-1].replace("_", " ").capitalize()
