from datetime import date
from decimal import Decimal

from app.domain.enums import (
    Direction,
    Lifecycle,
    MessageFunction,
    MessageType,
    PaymentType,
    SettlementResult,
    StatusCategory,
    TransactionType,
)
from app.domain.models import (
    Account,
    Confirmation,
    Security,
    Settlement,
    SettlementScenario,
    StatusDetails,
    Trade,
)

INSTRUCTION_CONFIG = {
    MessageType.MT540: (Direction.RECEIVE, PaymentType.FREE_OF_PAYMENT),
    MessageType.MT541: (Direction.RECEIVE, PaymentType.AGAINST_PAYMENT),
    MessageType.MT542: (Direction.DELIVER, PaymentType.FREE_OF_PAYMENT),
    MessageType.MT543: (Direction.DELIVER, PaymentType.AGAINST_PAYMENT),
}
CONFIRMATION_CONFIG = {
    MessageType.MT544: (Direction.RECEIVE, PaymentType.FREE_OF_PAYMENT),
    MessageType.MT545: (Direction.RECEIVE, PaymentType.AGAINST_PAYMENT),
    MessageType.MT546: (Direction.DELIVER, PaymentType.FREE_OF_PAYMENT),
    MessageType.MT547: (Direction.DELIVER, PaymentType.AGAINST_PAYMENT),
}


def golden_scenario(message_type: MessageType) -> SettlementScenario:
    if message_type in INSTRUCTION_CONFIG:
        direction, payment = INSTRUCTION_CONFIG[message_type]
        return SettlementScenario(
            scenario_id=f"GOLDEN-{message_type.value}",
            lifecycle=Lifecycle.INSTRUCTION,
            direction=direction,
            payment_type=payment,
            message_type=message_type,
            function=MessageFunction.NEWM,
            sender_reference=f"GOLDEN{message_type.value[2:]}",
            trade=Trade(
                transaction_type=(
                    TransactionType.BUY if direction == Direction.RECEIVE else TransactionType.SELL
                ),
                trade_date=date(2026, 8, 3),
                settlement_date=date(2026, 8, 6),
            ),
            security=Security(identifier="XS0000000009", quantity=Decimal("1000")),
            account=Account(safekeeping_account="SYNTHSAFE01"),
            settlement=Settlement(
                currency="USD" if payment == PaymentType.AGAINST_PAYMENT else None,
                amount=Decimal("25000.00") if payment == PaymentType.AGAINST_PAYMENT else None,
                place_of_settlement="SYNTHPSET01",
                delivering_agent="SYNTHDEAG01",
                receiving_agent="SYNTHREAG01",
            ),
        )
    if message_type in CONFIRMATION_CONFIG:
        direction, payment = CONFIRMATION_CONFIG[message_type]
        return SettlementScenario(
            scenario_id=f"GOLDEN-{message_type.value}",
            lifecycle=Lifecycle.CONFIRMATION,
            direction=direction,
            payment_type=payment,
            message_type=message_type,
            function=MessageFunction.NEWM,
            sender_reference=f"GOLDEN{message_type.value[2:]}",
            related_reference=f"GOLDEN{int(message_type.value[2:]) - 4}",
            security=Security(identifier="XS0000000009", quantity=Decimal("1000")),
            account=Account(safekeeping_account="SYNTHSAFE01"),
            settlement=Settlement(
                currency="USD" if payment == PaymentType.AGAINST_PAYMENT else None,
                amount=Decimal("25000.00") if payment == PaymentType.AGAINST_PAYMENT else None,
                place_of_settlement="SYNTHPSET01",
                delivering_agent="SYNTHDEAG01",
                receiving_agent="SYNTHREAG01",
            ),
            confirmation=Confirmation(
                confirmation_reference=f"GOLDEN{message_type.value[2:]}",
                actual_settlement_date=date(2026, 8, 6),
                settled_quantity=Decimal("1000"),
                settled_amount=(
                    Decimal("25000.00") if payment == PaymentType.AGAINST_PAYMENT else None
                ),
                settlement_result=SettlementResult.FULL,
            ),
        )
    return SettlementScenario(
        scenario_id="GOLDEN-MT548",
        lifecycle=Lifecycle.STATUS,
        direction=Direction.RECEIVE,
        payment_type=PaymentType.AGAINST_PAYMENT,
        message_type=MessageType.MT548,
        function=MessageFunction.NEWM,
        sender_reference="GOLDEN548",
        related_reference="GOLDEN541",
        status=StatusDetails(
            category=StatusCategory.PENDING,
            code="PEND",
            reason_code="AWAITING_CASH",
            narrative="SYNTHETIC PENDING STATUS",
            related_instruction_message_type=MessageType.MT541,
        ),
    )
