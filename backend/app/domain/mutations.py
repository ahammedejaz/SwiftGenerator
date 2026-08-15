from datetime import timedelta
from decimal import Decimal

from app.domain.enums import MessageFunction, MessageType, NegativeMutation
from app.domain.models import SettlementScenario

EXPECTED_RULES: dict[NegativeMutation, set[str]] = {
    NegativeMutation.MISSING_SETTLEMENT_AMOUNT: {
        "MT541-SETTLEMENT-AMOUNT-REQUIRED",
        "MT543-SETTLEMENT-AMOUNT-REQUIRED",
    },
    NegativeMutation.SETTLEMENT_DATE_BEFORE_TRADE_DATE: {"SETTLEMENT-DATE-NOT-BEFORE-TRADE"},
    NegativeMutation.SENDER_REFERENCE_TOO_LONG: {"SENDER-REFERENCE-MAX-LENGTH"},
    NegativeMutation.MISSING_PLACE_OF_SETTLEMENT: {
        "MT540-SETTLEMENT-PLACE_OF_SETTLEMENT-REQUIRED",
        "MT541-SETTLEMENT-PLACE_OF_SETTLEMENT-REQUIRED",
        "MT542-SETTLEMENT-PLACE_OF_SETTLEMENT-REQUIRED",
        "MT543-SETTLEMENT-PLACE_OF_SETTLEMENT-REQUIRED",
    },
    NegativeMutation.UNSUPPORTED_CURRENCY: {"PROFILE-CURRENCY-NOT-ALLOWED"},
    NegativeMutation.MISSING_PREVIOUS_REFERENCE_FOR_CANCELLATION: {
        "CANCELLATION-PREVIOUS-REFERENCE-REQUIRED"
    },
    NegativeMutation.CONFIRMATION_QUANTITY_EXCEEDS_INSTRUCTION: {
        "CONFIRMATION-QUANTITY-NOT-EXCEED-INSTRUCTION"
    },
    NegativeMutation.CONFIRMATION_MESSAGE_TYPE_MISMATCH: {
        "MESSAGE-TYPE-BUSINESS-MISMATCH",
        "CONFIRMATION-MESSAGE-TYPE-MATCH",
    },
    NegativeMutation.MT548_MISSING_RELATED_REFERENCE: {
        "MT548-RELATED_REFERENCE-REQUIRED",
        "LIFECYCLE-RELATED-REFERENCE",
    },
    NegativeMutation.INVALID_STATUS_REASON_COMBINATION: {"MT548-STATUS-REASON-COMBINATION"},
}


def apply_negative_mutation(
    scenario: SettlementScenario,
    mutation: NegativeMutation,
) -> tuple[SettlementScenario, set[str]]:
    if mutation == NegativeMutation.MISSING_SETTLEMENT_AMOUNT:
        mutated_settlement = scenario.settlement.model_copy(update={"amount": None})
        return (
            scenario.model_copy(update={"settlement": mutated_settlement}),
            expected_rules_for(scenario, mutation),
        )
    if mutation == NegativeMutation.SETTLEMENT_DATE_BEFORE_TRADE_DATE:
        if scenario.trade.trade_date is None:
            raise ValueError("Trade date is required before applying the date mutation")
        trade = scenario.trade.model_copy(
            update={"settlement_date": scenario.trade.trade_date - timedelta(days=1)}
        )
        return scenario.model_copy(update={"trade": trade}), expected_rules_for(scenario, mutation)
    if mutation == NegativeMutation.SENDER_REFERENCE_TOO_LONG:
        return scenario.model_copy(update={"sender_reference": "X" * 40}), expected_rules_for(
            scenario, mutation
        )
    if mutation == NegativeMutation.MISSING_PLACE_OF_SETTLEMENT:
        settlement = scenario.settlement.model_copy(update={"place_of_settlement": None})
        return scenario.model_copy(update={"settlement": settlement}), expected_rules_for(
            scenario, mutation
        )
    if mutation == NegativeMutation.UNSUPPORTED_CURRENCY:
        settlement = scenario.settlement.model_copy(update={"currency": "ZZZ"})
        return scenario.model_copy(update={"settlement": settlement}), expected_rules_for(
            scenario, mutation
        )
    if mutation == NegativeMutation.MISSING_PREVIOUS_REFERENCE_FOR_CANCELLATION:
        return scenario.model_copy(
            update={"function": MessageFunction.CANC, "related_reference": None}
        ), expected_rules_for(scenario, mutation)
    if mutation == NegativeMutation.CONFIRMATION_QUANTITY_EXCEEDS_INSTRUCTION:
        if scenario.security.quantity is None:
            raise ValueError("Instruction quantity is required before applying this mutation")
        confirmation = scenario.confirmation.model_copy(
            update={"settled_quantity": scenario.security.quantity + Decimal("1")}
        )
        return scenario.model_copy(update={"confirmation": confirmation}), expected_rules_for(
            scenario, mutation
        )
    if mutation == NegativeMutation.CONFIRMATION_MESSAGE_TYPE_MISMATCH:
        return scenario.model_copy(update={"message_type": MessageType.MT547}), expected_rules_for(
            scenario, mutation
        )
    if mutation == NegativeMutation.MT548_MISSING_RELATED_REFERENCE:
        return scenario.model_copy(update={"related_reference": None}), expected_rules_for(
            scenario, mutation
        )
    if mutation == NegativeMutation.INVALID_STATUS_REASON_COMBINATION:
        status = scenario.status.model_copy(update={"reason_code": "INVALID_DEMO_REASON"})
        return scenario.model_copy(update={"status": status}), expected_rules_for(
            scenario, mutation
        )
    raise ValueError(f"Negative mutation is not implemented: {mutation.value}")


def expected_rules_for(
    scenario: SettlementScenario,
    mutation: NegativeMutation,
) -> set[str]:
    rules = EXPECTED_RULES[mutation]
    if mutation in {
        NegativeMutation.MISSING_SETTLEMENT_AMOUNT,
        NegativeMutation.MISSING_PLACE_OF_SETTLEMENT,
    }:
        if scenario.message_type is None:
            return rules
        prefix = scenario.message_type.value
        return {rule for rule in rules if rule.startswith(prefix)}
    return rules
