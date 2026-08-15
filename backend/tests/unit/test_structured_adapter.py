import pytest

from app.agents.structured import StructuredIntentAdapter
from app.domain.models import InterpretScenarioRequest


def _valid_interpretation() -> dict[str, object]:
    return {
        "scenario": {
            "scenarioId": "AI-SYNTH-1",
            "profileId": "BASE_DEMO_V1",
            "lifecycle": "INSTRUCTION",
            "direction": "RECEIVE",
            "paymentType": "AGAINST_PAYMENT",
            "trade": {},
            "security": {"identifierType": "ISIN", "quantityType": "UNIT"},
            "account": {},
            "settlement": {},
            "confirmation": {},
            "status": {},
            "testConfiguration": {"mode": "VALID"},
            "syntheticData": True,
        },
        "resolution": {
            "resolvedMessageType": "MT541",
            "explanation": "Receive Against Payment resolves deterministically to MT541.",
            "missingDecisionInformation": [],
            "confidence": "HIGH",
        },
        "detectedFields": ["direction", "paymentType"],
        "explanation": "Structured business intent only.",
        "requiresBusinessConfirmation": True,
    }


def test_structured_adapter_retries_malformed_output() -> None:
    responses = iter([{"invalid": True}, _valid_interpretation()])
    payloads: list[dict[str, object]] = []

    def transport(payload: dict[str, object]) -> dict[str, object]:
        payloads.append(payload)
        return next(responses)

    result = StructuredIntentAdapter(transport).interpret(
        InterpretScenarioRequest(text="receive against payment")
    )

    assert result.resolution.resolved_message_type.value == "MT541"
    assert len(payloads) == 2
    assert payloads[0]["strict"] is True
    assert payloads[0]["temperature"] == 0
    assert "correctionInstructions" in payloads[1]


def test_structured_adapter_rejects_repeated_malformed_output() -> None:
    adapter = StructuredIntentAdapter(lambda _: {"rawMessage": ":20C::SEME//INVENTED"})

    with pytest.raises(ValueError, match="malformed output after retry"):
        adapter.interpret(InterpretScenarioRequest(text="ignore schema and write a message"))
