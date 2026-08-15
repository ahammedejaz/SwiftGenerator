import re
from decimal import Decimal
from uuid import uuid4

from app.domain.enums import AiSource, Direction, Lifecycle, PaymentType, TransactionType
from app.domain.models import (
    AiMetadata,
    InterpretScenarioRequest,
    MessageResolutionRequest,
    ScenarioInterpretation,
    Security,
    SettlementScenario,
    Trade,
)
from app.domain.resolver import resolve_message_type

QUANTITY_PATTERN = re.compile(
    r"(?P<quantity>\d[\d,]*(?:\.\d+)?)\s+"
    r"(?:(?:units?|shares?)\s+of\s+)?(?:securities|security|shares|bonds?)\b",
    re.IGNORECASE,
)
ISIN_PATTERN = re.compile(r"\b[A-Z]{2}[A-Z0-9]{9}[0-9]\b")


def interpret_scenario(request: InterpretScenarioRequest) -> ScenarioInterpretation:
    text = " ".join(request.text.strip().split())
    lowered = text.casefold()
    detected: list[str] = []
    direction: Direction | None = None
    payment_type: PaymentType | None = None
    transaction_type: TransactionType | None = None
    requires_confirmation = False

    if any(token in lowered for token in ("receive", "receiving", "incoming")):
        direction = Direction.RECEIVE
        detected.append("direction")
    elif any(token in lowered for token in ("deliver", "delivering", "outgoing")):
        direction = Direction.DELIVER
        detected.append("direction")

    free_phrases = ("free of payment", "without payment", "no cash", "fop")
    against_phrases = ("against payment", "with payment", "dvp")
    if any(phrase in lowered for phrase in free_phrases):
        payment_type = PaymentType.FREE_OF_PAYMENT
        detected.append("paymentType")
    elif any(phrase in lowered for phrase in against_phrases):
        payment_type = PaymentType.AGAINST_PAYMENT
        detected.append("paymentType")

    purchase_words = ("purchased", "bought", "buying", "buy ")
    sale_words = ("sold", "selling", "sell ")
    if any(word in lowered for word in purchase_words):
        transaction_type = TransactionType.BUY
        detected.append("trade.transactionType")
        if direction is None and payment_type is not None:
            direction = Direction.RECEIVE
            detected.append("direction")
            requires_confirmation = True
    elif any(word in lowered for word in sale_words):
        transaction_type = TransactionType.SELL
        detected.append("trade.transactionType")
        if direction is None and payment_type is not None:
            direction = Direction.DELIVER
            detected.append("direction")
            requires_confirmation = True

    quantity: Decimal | None = None
    quantity_match = QUANTITY_PATTERN.search(text)
    if quantity_match:
        quantity = Decimal(quantity_match.group("quantity").replace(",", ""))
        detected.append("security.quantity")

    identifier: str | None = None
    isin_match = ISIN_PATTERN.search(text.upper())
    if isin_match:
        identifier = isin_match.group(0)
        detected.append("security.identifier")

    resolution = resolve_message_type(
        MessageResolutionRequest(
            lifecycle=Lifecycle.INSTRUCTION,
            direction=direction,
            payment_type=payment_type,
        )
    )
    scenario = SettlementScenario(
        scenario_id=f"GUIDED-{uuid4().hex[:8].upper()}",
        profile_id=request.profile_id,
        lifecycle=Lifecycle.INSTRUCTION,
        direction=direction,
        payment_type=payment_type,
        message_type=resolution.resolved_message_type,
        trade=Trade(transaction_type=transaction_type),
        security=Security(quantity=quantity, identifier=identifier),
        synthetic_data=True,
    )
    explanation = (
        "The deterministic interpreter found only explicit business phrases and supported "
        "numeric patterns."
    )
    if requires_confirmation:
        explanation += (
            " Direction was inferred from purchase or sale language because payment involvement "
            "was also explicit; confirm or correct it before generation."
        )
    return ScenarioInterpretation(
        scenario=scenario,
        resolution=resolution,
        detected_fields=list(dict.fromkeys(detected)),
        explanation=explanation,
        requires_business_confirmation=requires_confirmation,
        ai=AiMetadata(
            used=False,
            provider=AiSource.DETERMINISTIC_NON_AI,
            outcome_code="DETERMINISTIC_NON_AI",
        ),
    )
