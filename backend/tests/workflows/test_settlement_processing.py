from copy import deepcopy


def _instruction(client, payload, reference: str):  # type: ignore[no-untyped-def]
    scenario = deepcopy(payload)
    scenario["scenarioId"] = f"SCENARIO-{reference}"
    scenario["senderReference"] = reference
    response = client.post("/api/messages/generate", json={"scenario": scenario})
    assert response.status_code == 200, response.text
    return response.json()


def test_cancellation_status_and_recursive_lifecycle(client, valid_mt541_payload) -> None:  # type: ignore[no-untyped-def]
    original = _instruction(client, valid_mt541_payload, "ORIGCANCEL001")
    before = client.get(f"/api/messages/{original['messageId']}").json()

    cancelled = client.post(
        "/api/settlement/cancellations",
        json={
            "originalInstructionId": original["messageId"],
            "cancellationReference": "CANCELREQ001",
        },
    )
    assert cancelled.status_code == 200, cancelled.text
    cancellation = cancelled.json()
    assert cancellation["resolvedMessageType"] == "MT541"
    assert cancellation["scenario"]["function"] == "CANC"
    assert cancellation["scenario"]["relatedReference"] == "ORIGCANCEL001"
    assert ":23G:CANC" in cancellation["rawMessage"]

    duplicate = client.post(
        "/api/settlement/cancellations",
        json={"originalInstructionId": original["messageId"]},
    )
    assert duplicate.status_code == 400
    assert "active cancellation" in duplicate.json()["error"]["message"]

    status = client.post(
        f"/api/messages/{cancellation['messageId']}/responses",
        json={
            "action": "CANCELLATION_ACCEPTED_STATUS",
            "reasonCode": "CANCELLATION_PROCESSED",
            "responseReference": "CANCELSTAT001",
        },
    )
    assert status.status_code == 200, status.text
    assert status.json()["resolvedMessageType"] == "MT548"
    assert status.json()["scenario"]["status"]["category"] == "CANCELLATION_ACCEPTED"

    timeline = client.get(f"/api/workflows/{original['messageId']}/lifecycle")
    assert timeline.status_code == 200
    assert [item["messageType"] for item in timeline.json()["entries"]] == [
        "MT541",
        "MT541",
        "MT548",
    ]
    assert client.get(f"/api/messages/{original['messageId']}").json() == before


def test_amendment_decision_is_explicit_and_source_referenced(client, valid_mt541_payload) -> None:  # type: ignore[no-untyped-def]
    original = _instruction(client, valid_mt541_payload, "ORIGDECIDE001")
    cases = [
        ("processing.priority", "PROCESSING_DATA_MODIFICATION", "MT530_PRIORITY"),
        ("security.quantity", "CORE_BUSINESS_DATA_CHANGE", "CANCEL_REBOOK"),
        ("processing.holdRelease", "UNSUPPORTED_MODIFICATION", "UNSUPPORTED"),
    ]
    for field_path, classification, method in cases:
        response = client.post(
            "/api/settlement/amendment-decision",
            json={
                "originalInstructionId": original["messageId"],
                "changes": [{"fieldPath": field_path, "proposedValue": "42"}],
            },
        )
        assert response.status_code == 200
        assert response.json()["classification"] == classification
        assert response.json()["method"] == method
        assert "ISO15022" in response.json()["sourceReference"]

    mixed = client.post(
        "/api/settlement/amendment-decision",
        json={
            "originalInstructionId": original["messageId"],
            "changes": [
                {"fieldPath": "transaction.cancel"},
                {"fieldPath": "security.quantity", "proposedValue": "1200"},
            ],
        },
    )
    assert mixed.json()["classification"] == "CLARIFICATION_REQUIRED"


def test_mt530_priority_command_composes_validates_parses_and_correlates(
    client, valid_mt541_payload
) -> None:  # type: ignore[no-untyped-def]
    original = _instruction(client, valid_mt541_payload, "ORIGCMD000001")
    response = client.post(
        "/api/settlement/commands",
        json={
            "originalInstructionId": original["messageId"],
            "commandReference": "COMMAND000001",
            "commandType": "MODIFY_PRIORITY",
            "priority": 42,
        },
    )
    assert response.status_code == 200, response.text
    command = response.json()
    assert command["resolvedMessageType"] == "MT530"
    assert ":20C::PREV//ORIGCMD000001" in command["rawMessage"]
    assert ":22F::PRIR//0042" in command["rawMessage"]
    assert command["validation"]["status"] == "VALID"

    parsed = client.post(
        "/api/messages/validate-raw",
        json={"rawMessage": command["rawMessage"], "profileId": "BASE_DEMO_V1"},
    )
    assert parsed.status_code == 200
    assert parsed.json()["supportedSubset"] is True
    assert parsed.json()["messageType"] == "MT530"

    timeline = client.get(f"/api/messages/{command['messageId']}/lifecycle")
    assert [item["messageType"] for item in timeline.json()["entries"]] == [
        "MT541",
        "MT530",
    ]


def test_cancel_and_rebook_changes_core_data_and_preserves_original(
    client, valid_mt541_payload
) -> None:  # type: ignore[no-untyped-def]
    original = _instruction(client, valid_mt541_payload, "ORIGREBOOK001")
    response = client.post(
        "/api/settlement/cancel-rebook",
        json={
            "originalInstructionId": original["messageId"],
            "cancellationReference": "REBOOKCANCEL01",
            "replacementReference": "REPLACEMENT001",
            "changes": [{"fieldPath": "security.quantity", "proposedValue": "1500"}],
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["decision"]["requiresCancelRebook"] is True
    assert result["beforeValues"]["security.quantity"] == "1000"
    assert result["afterValues"]["security.quantity"] == "1500"
    assert result["replacement"]["scenario"]["senderReference"] == "REPLACEMENT001"
    assert result["replacement"]["scenario"]["function"] == "NEWM"
    persisted_original = client.get(f"/api/messages/{original['messageId']}").json()
    assert persisted_original["scenario"]["security"]["quantity"] == "1000"


def test_invalid_command_and_missing_original_fail_safely(client) -> None:  # type: ignore[no-untyped-def]
    missing = client.post(
        "/api/settlement/commands",
        json={
            "originalInstructionId": "missing",
            "commandReference": "COMMANDMISS01",
            "commandType": "MODIFY_PRIORITY",
            "priority": 1,
        },
    )
    assert missing.status_code == 404
    assert "stack" not in missing.text.casefold()

    invalid = client.post(
        "/api/settlement/commands",
        json={
            "originalInstructionId": "missing",
            "commandReference": "COMMANDMISS01",
            "commandType": "MODIFY_PRIORITY",
            "priority": 0,
        },
    )
    assert invalid.status_code == 422
