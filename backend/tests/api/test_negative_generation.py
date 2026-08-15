import pytest


def test_controlled_missing_amount_negative_mt541(client, valid_mt541_payload) -> None:
    valid_mt541_payload["testConfiguration"] = {
        "mode": "NEGATIVE_TEST",
        "mutation": "MISSING_SETTLEMENT_AMOUNT",
        "expectedOutcome": "MT541-SETTLEMENT-AMOUNT-REQUIRED",
    }
    response = client.post("/api/messages/generate", json={"scenario": valid_mt541_payload})
    assert response.status_code == 200, response.text
    generated = response.json()
    assert generated["validation"]["status"] == "INTENTIONALLY_INVALID"
    assert generated["intentionalInvalidNotice"] == (
        "Intentionally invalid message generated for negative testing."
    )
    expected = next(
        item
        for item in generated["validation"]["findings"]
        if item["ruleId"] == "MT541-SETTLEMENT-AMOUNT-REQUIRED"
    )
    assert expected["intentional"] is True
    assert ":19A::SETT//" not in generated["rawMessage"]


def test_negative_generation_requires_valid_baseline(client, valid_mt541_payload) -> None:
    valid_mt541_payload["settlement"]["amount"] = None
    valid_mt541_payload["testConfiguration"] = {
        "mode": "NEGATIVE_TEST",
        "mutation": "MISSING_SETTLEMENT_AMOUNT",
    }
    response = client.post("/api/messages/generate", json={"scenario": valid_mt541_payload})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


@pytest.mark.parametrize(
    ("mutation", "expected_rule"),
    [
        (
            "SETTLEMENT_DATE_BEFORE_TRADE_DATE",
            "SETTLEMENT-DATE-NOT-BEFORE-TRADE",
        ),
        ("SENDER_REFERENCE_TOO_LONG", "SENDER-REFERENCE-MAX-LENGTH"),
        (
            "MISSING_PLACE_OF_SETTLEMENT",
            "MT541-SETTLEMENT-PLACE_OF_SETTLEMENT-REQUIRED",
        ),
        ("UNSUPPORTED_CURRENCY", "PROFILE-CURRENCY-NOT-ALLOWED"),
        (
            "MISSING_PREVIOUS_REFERENCE_FOR_CANCELLATION",
            "CANCELLATION-PREVIOUS-REFERENCE-REQUIRED",
        ),
    ],
)
def test_instruction_negative_mutations(
    client, valid_mt541_payload, mutation, expected_rule
) -> None:
    valid_mt541_payload["testConfiguration"] = {
        "mode": "NEGATIVE_TEST",
        "mutation": mutation,
    }
    response = client.post("/api/messages/generate", json={"scenario": valid_mt541_payload})
    assert response.status_code == 200, response.text
    generated = response.json()
    assert generated["validation"]["status"] == "INTENTIONALLY_INVALID"
    finding = next(
        item for item in generated["validation"]["findings"] if item["ruleId"] == expected_rule
    )
    assert finding["intentional"] is True


@pytest.mark.parametrize(
    ("action", "reason", "mutation", "expected_rule"),
    [
        (
            "FULL_CONFIRMATION",
            None,
            "CONFIRMATION_QUANTITY_EXCEEDS_INSTRUCTION",
            "CONFIRMATION-QUANTITY-NOT-EXCEED-INSTRUCTION",
        ),
        (
            "FULL_CONFIRMATION",
            None,
            "CONFIRMATION_MESSAGE_TYPE_MISMATCH",
            "CONFIRMATION-MESSAGE-TYPE-MATCH",
        ),
        (
            "PENDING_STATUS",
            "AWAITING_CASH",
            "MT548_MISSING_RELATED_REFERENCE",
            "MT548-RELATED_REFERENCE-REQUIRED",
        ),
        (
            "PENDING_STATUS",
            "AWAITING_CASH",
            "INVALID_STATUS_REASON_COMBINATION",
            "MT548-STATUS-REASON-COMBINATION",
        ),
    ],
)
def test_lifecycle_negative_mutations(
    client,
    valid_mt541_payload,
    action,
    reason,
    mutation,
    expected_rule,
) -> None:
    instruction_response = client.post(
        "/api/messages/generate", json={"scenario": valid_mt541_payload}
    )
    instruction = instruction_response.json()
    request = {
        "action": action,
        "generationMode": "NEGATIVE_TEST",
        "negativeMutation": mutation,
    }
    if action == "FULL_CONFIRMATION":
        request["actualSettlementDate"] = "2026-08-06"
    if reason:
        request["reasonCode"] = reason
    response = client.post(f"/api/messages/{instruction['messageId']}/responses", json=request)
    assert response.status_code == 200, response.text
    generated = response.json()
    assert generated["validation"]["status"] == "INTENTIONALLY_INVALID"
    assert any(
        item["ruleId"] == expected_rule and item["intentional"]
        for item in generated["validation"]["findings"]
    )
