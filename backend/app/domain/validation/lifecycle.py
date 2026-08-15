from app.domain.enums import Lifecycle, MessageType, Severity
from app.domain.models import SettlementScenario, ValidationFinding
from app.domain.resolver import CONFIRMATION_TYPES
from app.domain.statuses import statuses


def validate_lifecycle_response(
    response: SettlementScenario,
    instruction: SettlementScenario,
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []

    def add(
        rule_id: str,
        field_path: str,
        message: str,
        technical: str,
        current: object,
        expected: str,
    ) -> None:
        findings.append(
            ValidationFinding(
                rule_id=rule_id,
                severity=Severity.ERROR,
                field_path=field_path,
                message=message,
                technical_explanation=technical,
                current_value=current,
                expected_condition=expected,
                suggestion="Generate the response from the original instruction.",
            )
        )

    if (
        instruction.lifecycle != Lifecycle.INSTRUCTION
        or instruction.message_type not in CONFIRMATION_TYPES
    ):
        add(
            "LIFECYCLE-ORIGINAL-INSTRUCTION",
            "relatedReference",
            "This response must be generated from a supported settlement instruction.",
            "Supported lifecycle roots are MT540, MT541, MT542, and MT543.",
            instruction.message_type.value if instruction.message_type else None,
            "MT540, MT541, MT542, or MT543",
        )
        return findings
    assert instruction.message_type is not None

    if response.related_reference != instruction.sender_reference:
        add(
            "LIFECYCLE-RELATED-REFERENCE",
            "relatedReference",
            "The response does not reference the original instruction.",
            "Response correlation uses the instruction sender reference.",
            response.related_reference,
            instruction.sender_reference or "Original instruction reference",
        )
    if response.security.identifier != instruction.security.identifier:
        add(
            "LIFECYCLE-SECURITY-MATCH",
            "security.identifier",
            "Response security must match the instruction security.",
            "The security identifier is inherited from the original instruction.",
            response.security.identifier,
            instruction.security.identifier or "Original security identifier",
        )
    if response.direction != instruction.direction:
        add(
            "LIFECYCLE-DIRECTION-MATCH",
            "direction",
            "Response direction must match the instruction direction.",
            "Confirmation and status direction is inherited from the instruction.",
            response.direction.value if response.direction else None,
            instruction.direction.value if instruction.direction else "Instruction direction",
        )
    if response.payment_type != instruction.payment_type:
        add(
            "LIFECYCLE-PAYMENT-TYPE-MATCH",
            "paymentType",
            "Response payment type must match the instruction payment type.",
            "Response payment type is inherited from the instruction.",
            response.payment_type.value if response.payment_type else None,
            instruction.payment_type.value
            if instruction.payment_type
            else "Instruction payment type",
        )

    if response.message_type in CONFIRMATION_TYPES.values():
        expected_confirmation = CONFIRMATION_TYPES[instruction.message_type]
        if response.message_type != expected_confirmation:
            add(
                "CONFIRMATION-MESSAGE-TYPE-MATCH",
                "messageType",
                "Confirmation type does not correspond to the original instruction.",
                "Confirmation pairing is controlled by the deterministic mapping table.",
                response.message_type.value if response.message_type else None,
                expected_confirmation.value,
            )
        if (
            response.confirmation.settled_quantity is not None
            and instruction.security.quantity is not None
            and response.confirmation.settled_quantity > instruction.security.quantity
        ):
            add(
                "CONFIRMATION-QUANTITY-NOT-EXCEED-INSTRUCTION",
                "confirmation.settledQuantity",
                "Confirmed quantity must not exceed the instructed quantity.",
                "Lifecycle correlation compares confirmed and instructed quantities.",
                str(response.confirmation.settled_quantity),
                f"At most {instruction.security.quantity}",
            )
    elif response.message_type == MessageType.MT548:
        if response.status.related_instruction_message_type != instruction.message_type:
            add(
                "MT548-RELATED-INSTRUCTION-TYPE",
                "status.relatedInstructionMessageType",
                "MT548 must identify the related instruction message type.",
                "The status is correlated to its original instruction type.",
                (
                    response.status.related_instruction_message_type.value
                    if response.status.related_instruction_message_type
                    else None
                ),
                instruction.message_type.value,
            )
        if (
            response.status.category
            and response.status.reason_code
            and not statuses.validate_reason(response.status.category, response.status.reason_code)
        ):
            add(
                "MT548-STATUS-REASON-COMBINATION",
                "status.reasonCode",
                "The reason is not enabled for this status.",
                "Status/reason pairs are controlled by versioned configuration.",
                response.status.reason_code,
                ", ".join(statuses.get(response.status.category).reasons),
            )
    else:
        add(
            "LIFECYCLE-RESPONSE-TYPE",
            "messageType",
            "The response type is not supported for this lifecycle.",
            "The lifecycle supports mapped confirmations and MT548 responses.",
            response.message_type.value if response.message_type else None,
            "Mapped confirmation or MT548",
        )

    return findings
