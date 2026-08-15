import pytest

from app.domain.enums import Direction, Lifecycle, MessageType, PaymentType
from app.domain.models import MessageResolutionRequest
from app.domain.resolver import resolve_message_type


@pytest.mark.parametrize(
    ("direction", "payment_type", "expected"),
    [
        (Direction.RECEIVE, PaymentType.FREE_OF_PAYMENT, MessageType.MT540),
        (Direction.RECEIVE, PaymentType.AGAINST_PAYMENT, MessageType.MT541),
        (Direction.DELIVER, PaymentType.FREE_OF_PAYMENT, MessageType.MT542),
        (Direction.DELIVER, PaymentType.AGAINST_PAYMENT, MessageType.MT543),
    ],
)
def test_instruction_resolution(direction, payment_type, expected) -> None:
    result = resolve_message_type(
        MessageResolutionRequest(
            lifecycle=Lifecycle.INSTRUCTION,
            direction=direction,
            payment_type=payment_type,
        )
    )
    assert result.resolved_message_type == expected
    assert result.confidence == "DETERMINISTIC"


def test_resolution_reports_missing_decisions_without_guessing() -> None:
    result = resolve_message_type(MessageResolutionRequest(lifecycle=Lifecycle.INSTRUCTION))
    assert result.resolved_message_type is None
    assert result.missing_decision_information == ["direction", "paymentType"]


def test_mt541_confirmation_resolves_to_mt545() -> None:
    result = resolve_message_type(
        MessageResolutionRequest(
            lifecycle=Lifecycle.CONFIRMATION,
            original_instruction_type=MessageType.MT541,
        )
    )
    assert result.resolved_message_type == MessageType.MT545


def test_supported_instruction_status_resolves_to_mt548() -> None:
    result = resolve_message_type(
        MessageResolutionRequest(
            lifecycle=Lifecycle.STATUS,
            original_instruction_type=MessageType.MT541,
        )
    )
    assert result.resolved_message_type == MessageType.MT548
