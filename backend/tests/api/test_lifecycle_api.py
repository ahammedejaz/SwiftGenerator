def generate_instruction(client, payload):
    response = client.post("/api/messages/generate", json={"scenario": payload})
    assert response.status_code == 200, response.text
    return response.json()


def test_complete_mt541_pending_mt545_lifecycle(client, valid_mt541_payload) -> None:
    instruction = generate_instruction(client, valid_mt541_payload)
    instruction_id = instruction["messageId"]

    status_response = client.post(
        f"/api/messages/{instruction_id}/responses",
        json={
            "action": "PENDING_STATUS",
            "reasonCode": "AWAITING_CASH",
            "reasonNarrative": "SYNTHETIC CASH CHECK PENDING",
        },
    )
    assert status_response.status_code == 200, status_response.text
    status = status_response.json()
    assert status["resolvedMessageType"] == "MT548"
    assert status["scenario"]["relatedReference"] == "TEST000000001"
    assert ":25D::SETT//PEND" in status["rawMessage"]

    confirmation_response = client.post(
        f"/api/messages/{instruction_id}/responses",
        json={
            "action": "FULL_CONFIRMATION",
            "actualSettlementDate": "2026-08-06",
        },
    )
    assert confirmation_response.status_code == 200, confirmation_response.text
    confirmation = confirmation_response.json()
    assert confirmation["resolvedMessageType"] == "MT545"
    assert confirmation["scenario"]["confirmation"]["settledQuantity"] == "1000"
    assert confirmation["scenario"]["confirmation"]["settledAmount"] == "25000.00"
    assert ":22F::STCO//FULL" in confirmation["rawMessage"]

    lifecycle_response = client.get(f"/api/messages/{instruction_id}/lifecycle")
    assert lifecycle_response.status_code == 200
    lifecycle = lifecycle_response.json()
    assert [item["messageType"] for item in lifecycle["entries"]] == [
        "MT541",
        "MT548",
        "MT545",
    ]
    assert lifecycle["correlationValid"] is True

    retrieved = client.get(f"/api/messages/{confirmation['messageId']}")
    assert retrieved.status_code == 200
    assert retrieved.json()["rawMessage"] == confirmation["rawMessage"]


def test_rejected_status_uses_controlled_reason(client, valid_mt541_payload) -> None:
    instruction = generate_instruction(client, valid_mt541_payload)
    response = client.post(
        f"/api/messages/{instruction['messageId']}/responses",
        json={"action": "REJECTED_STATUS", "reasonCode": "INVALID_REFERENCE"},
    )
    assert response.status_code == 200
    assert response.json()["scenario"]["status"]["category"] == "REJECTED"
    assert ":25D::SETT//REJT" in response.json()["rawMessage"]


def test_status_rejects_invalid_reason_combination(client, valid_mt541_payload) -> None:
    instruction = generate_instruction(client, valid_mt541_payload)
    response = client.post(
        f"/api/messages/{instruction['messageId']}/responses",
        json={"action": "PENDING_STATUS", "reasonCode": "INVALID_REFERENCE"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_partial_confirmation_requires_less_than_instruction_quantity(
    client, valid_mt541_payload
) -> None:
    instruction = generate_instruction(client, valid_mt541_payload)
    response = client.post(
        f"/api/messages/{instruction['messageId']}/responses",
        json={
            "action": "PARTIAL_CONFIRMATION",
            "actualSettlementDate": "2026-08-06",
            "settledQuantity": "400",
            "settledAmount": "10000.00",
        },
    )
    assert response.status_code == 200, response.text
    confirmation = response.json()
    assert confirmation["scenario"]["confirmation"]["settlementResult"] == "PARTIAL"
    assert ":22F::STCO//PARTIAL" in confirmation["rawMessage"]

    invalid = client.post(
        f"/api/messages/{instruction['messageId']}/responses",
        json={
            "action": "PARTIAL_CONFIRMATION",
            "actualSettlementDate": "2026-08-06",
            "settledQuantity": "1200",
            "settledAmount": "30000.00",
        },
    )
    assert invalid.status_code == 400
