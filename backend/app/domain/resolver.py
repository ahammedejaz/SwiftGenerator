from app.domain.enums import Direction, Lifecycle, MessageType, PaymentType
from app.domain.models import MessageResolution, MessageResolutionRequest

INSTRUCTION_TYPES = {
    (Direction.RECEIVE, PaymentType.FREE_OF_PAYMENT): MessageType.MT540,
    (Direction.RECEIVE, PaymentType.AGAINST_PAYMENT): MessageType.MT541,
    (Direction.DELIVER, PaymentType.FREE_OF_PAYMENT): MessageType.MT542,
    (Direction.DELIVER, PaymentType.AGAINST_PAYMENT): MessageType.MT543,
}

CONFIRMATION_TYPES = {
    MessageType.MT540: MessageType.MT544,
    MessageType.MT541: MessageType.MT545,
    MessageType.MT542: MessageType.MT546,
    MessageType.MT543: MessageType.MT547,
}


def resolve_message_type(request: MessageResolutionRequest) -> MessageResolution:
    if request.lifecycle == Lifecycle.STATUS:
        if (
            request.original_instruction_type
            and request.original_instruction_type not in CONFIRMATION_TYPES
        ):
            return MessageResolution(
                resolved_message_type=None,
                explanation="A status must refer to a supported settlement instruction.",
                missing_decision_information=["originalInstructionType"],
                confidence="NONE",
            )
        return MessageResolution(
            resolved_message_type=MessageType.MT548,
            explanation=(
                "MT548 is used for status and processing advice for supported instructions."
            ),
            confidence="DETERMINISTIC",
        )

    if request.lifecycle == Lifecycle.CONFIRMATION and request.original_instruction_type:
        result = CONFIRMATION_TYPES.get(request.original_instruction_type)
        if result:
            return MessageResolution(
                resolved_message_type=result,
                explanation=(
                    f"{result.value} is the confirmation paired with "
                    f"{request.original_instruction_type.value}."
                ),
                confidence="DETERMINISTIC",
            )
        return MessageResolution(
            resolved_message_type=None,
            explanation="The original message is not a supported settlement instruction.",
            missing_decision_information=["supportedOriginalInstructionType"],
            confidence="NONE",
        )

    missing: list[str] = []
    if request.direction is None:
        missing.append("direction")
    if request.payment_type is None:
        missing.append("paymentType")
    if missing:
        return MessageResolution(
            resolved_message_type=None,
            explanation=(
                "Direction and payment involvement are needed before choosing a message type."
            ),
            missing_decision_information=missing,
            confidence="INCOMPLETE",
        )

    direction = request.direction
    payment_type = request.payment_type
    assert direction is not None
    assert payment_type is not None
    instruction_type = INSTRUCTION_TYPES[(direction, payment_type)]
    if request.lifecycle == Lifecycle.CONFIRMATION:
        confirmation_type = CONFIRMATION_TYPES[instruction_type]
        return MessageResolution(
            resolved_message_type=confirmation_type,
            explanation=(
                f"{confirmation_type.value} confirms a {direction.value.title()} "
                f"{payment_type.value.replace('_', ' ').title()} instruction."
            ),
            confidence="DETERMINISTIC",
        )

    return MessageResolution(
        resolved_message_type=instruction_type,
        explanation=(
            f"{instruction_type.value} is the instruction for "
            f"{direction.value.title()} and "
            f"{payment_type.value.replace('_', ' ').title()}."
        ),
        confidence="DETERMINISTIC",
    )
