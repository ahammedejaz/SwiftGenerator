import pytest


def instruction_payload(base, direction: str, payment_type: str) -> dict[str, object]:
    payload = base
    payload["scenarioId"] = f"TC-{direction}-{payment_type}"
    payload["direction"] = direction
    payload["paymentType"] = payment_type
    payload.pop("messageType", None)
    payload["trade"]["transactionType"] = "BUY" if direction == "RECEIVE" else "SELL"
    if payment_type == "FREE_OF_PAYMENT":
        payload["settlement"]["currency"] = None
        payload["settlement"]["amount"] = None
    return payload


@pytest.mark.parametrize(
    ("direction", "payment_type", "expected"),
    [
        ("RECEIVE", "FREE_OF_PAYMENT", "MT540"),
        ("RECEIVE", "AGAINST_PAYMENT", "MT541"),
        ("DELIVER", "FREE_OF_PAYMENT", "MT542"),
        ("DELIVER", "AGAINST_PAYMENT", "MT543"),
    ],
)
def test_all_instruction_types_generate(
    client, valid_mt541_payload, direction, payment_type, expected
) -> None:
    payload = instruction_payload(valid_mt541_payload, direction, payment_type)
    response = client.post("/api/messages/generate", json={"scenario": payload})
    assert response.status_code == 200, response.text
    assert response.json()["resolvedMessageType"] == expected
    assert f"{{2:{expected}}}" in response.json()["rawMessage"]


@pytest.mark.parametrize(
    ("direction", "payment_type", "instruction_type", "confirmation_type"),
    [
        ("RECEIVE", "FREE_OF_PAYMENT", "MT540", "MT544"),
        ("RECEIVE", "AGAINST_PAYMENT", "MT541", "MT545"),
        ("DELIVER", "FREE_OF_PAYMENT", "MT542", "MT546"),
        ("DELIVER", "AGAINST_PAYMENT", "MT543", "MT547"),
    ],
)
def test_all_instructions_generate_paired_confirmation_and_status(
    client,
    valid_mt541_payload,
    direction,
    payment_type,
    instruction_type,
    confirmation_type,
) -> None:
    payload = instruction_payload(valid_mt541_payload, direction, payment_type)
    instruction_response = client.post("/api/messages/generate", json={"scenario": payload})
    assert instruction_response.status_code == 200, instruction_response.text
    instruction = instruction_response.json()
    assert instruction["resolvedMessageType"] == instruction_type

    confirmation_response = client.post(
        f"/api/messages/{instruction['messageId']}/responses",
        json={
            "action": "FULL_CONFIRMATION",
            "actualSettlementDate": "2026-08-06",
        },
    )
    assert confirmation_response.status_code == 200, confirmation_response.text
    assert confirmation_response.json()["resolvedMessageType"] == confirmation_type

    status_response = client.post(
        f"/api/messages/{instruction['messageId']}/responses",
        json={"action": "MATCHED_STATUS", "reasonCode": "DETAILS_MATCHED"},
    )
    assert status_response.status_code == 200, status_response.text
    status = status_response.json()
    assert status["resolvedMessageType"] == "MT548"
    assert status["scenario"]["status"]["relatedInstructionMessageType"] == instruction_type
