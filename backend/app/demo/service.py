from datetime import date
from decimal import Decimal

from app.domain.enums import (
    Direction,
    GenerationMode,
    Lifecycle,
    MessageFunction,
    NegativeMutation,
    PaymentType,
    ResponseAction,
    TransactionType,
)
from app.domain.models import (
    Account,
    DemoResetResponse,
    LifecycleResponseRequest,
    Security,
    Settlement,
    SettlementScenario,
    TestConfiguration,
    Trade,
)
from app.persistence.repository import MessageRepository
from app.services.generation import GenerationService
from app.services.lifecycle import LifecycleService


class DemoService:
    def __init__(
        self,
        generation: GenerationService,
        lifecycle: LifecycleService,
        messages: MessageRepository,
    ) -> None:
        self._generation = generation
        self._lifecycle = lifecycle
        self._messages = messages

    def reset(self) -> DemoResetResponse:
        removed = self._messages.reset_synthetic()
        roots = [
            self._generation.generate(
                self._instruction("DEMO540REF", Direction.RECEIVE, PaymentType.FREE_OF_PAYMENT)
            ),
            self._generation.generate(
                self._instruction("DEMO541REF", Direction.RECEIVE, PaymentType.AGAINST_PAYMENT)
            ),
            self._generation.generate(
                self._instruction("DEMO542REF", Direction.DELIVER, PaymentType.FREE_OF_PAYMENT)
            ),
            self._generation.generate(
                self._instruction("DEMO543REF", Direction.DELIVER, PaymentType.AGAINST_PAYMENT)
            ),
        ]
        for root in roots:
            self._lifecycle.generate_response(
                root.message_id,
                LifecycleResponseRequest(
                    action=ResponseAction.FULL_CONFIRMATION,
                    actual_settlement_date=date(2026, 8, 6),
                ),
            )

        mt541 = roots[1]
        for action, reason in [
            (ResponseAction.PENDING_STATUS, "AWAITING_CASH"),
            (ResponseAction.REJECTED_STATUS, "INVALID_REFERENCE"),
            (ResponseAction.MATCHED_STATUS, "DETAILS_MATCHED"),
            (
                ResponseAction.CANCELLATION_ACCEPTED_STATUS,
                "CANCELLATION_PROCESSED",
            ),
        ]:
            self._lifecycle.generate_response(
                mt541.message_id,
                LifecycleResponseRequest(action=action, reason_code=reason),
            )

        extra_valid = self._generation.generate(
            self._instruction("DEMOVALID541", Direction.RECEIVE, PaymentType.AGAINST_PAYMENT)
        )
        negative = self._instruction("DEMONEG541", Direction.RECEIVE, PaymentType.AGAINST_PAYMENT)
        negative = negative.model_copy(
            update={
                "test_configuration": TestConfiguration(
                    mode=GenerationMode.NEGATIVE_TEST,
                    mutation=NegativeMutation.MISSING_SETTLEMENT_AMOUNT,
                    expected_outcome="MT541-SETTLEMENT-AMOUNT-REQUIRED",
                )
            }
        )
        self._generation.generate(negative)
        self._lifecycle.generate_response(
            extra_valid.message_id,
            LifecycleResponseRequest(
                action=ResponseAction.PARTIAL_CONFIRMATION,
                actual_settlement_date=date(2026, 8, 6),
                settled_quantity=Decimal("400"),
                settled_amount=Decimal("10000.00"),
            ),
        )
        return DemoResetResponse(
            removed_messages=removed,
            seeded_messages=15,
            root_instruction_id=mt541.message_id,
            lifecycle_path=f"/api/messages/{mt541.message_id}/lifecycle",
        )

    @staticmethod
    def _instruction(
        reference: str,
        direction: Direction,
        payment_type: PaymentType,
    ) -> SettlementScenario:
        return SettlementScenario(
            scenario_id=f"SYNTH-{reference}",
            profile_id="BASE_DEMO_V1",
            lifecycle=Lifecycle.INSTRUCTION,
            direction=direction,
            payment_type=payment_type,
            function=MessageFunction.NEWM,
            sender_reference=reference,
            trade=Trade(
                transaction_type=(
                    TransactionType.BUY if direction == Direction.RECEIVE else TransactionType.SELL
                ),
                trade_date=date(2026, 8, 3),
                settlement_date=date(2026, 8, 6),
            ),
            security=Security(identifier="XS0000000001", quantity=Decimal("1000")),
            account=Account(safekeeping_account="SYNTHSAFE01"),
            settlement=Settlement(
                currency=("USD" if payment_type == PaymentType.AGAINST_PAYMENT else None),
                amount=(
                    Decimal("25000.00") if payment_type == PaymentType.AGAINST_PAYMENT else None
                ),
                place_of_settlement="SYNTHPSET01",
                delivering_agent="SYNTHDEAG01",
                receiving_agent="SYNTHREAG01",
            ),
            synthetic_data=True,
        )
