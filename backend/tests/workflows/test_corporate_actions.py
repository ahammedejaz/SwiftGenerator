from __future__ import annotations

from copy import deepcopy


def notification_payload(suffix: str = "001") -> dict[str, object]:
    return {
        "notification": {
            "workflowId": f"CA-WF-{suffix}",
            "profileId": "BASE_DEMO_V1",
            "eventReference": f"CAEV{suffix}",
            "messageReference": f"CA564{suffix}",
            "eventType": "DIVIDEND_WITH_OPTIONS",
            "classification": "VOLUNTARY",
            "securityIdentifier": "XS0000000001",
            "safekeepingAccount": "SYNTHSAFE01",
            "eligibleQuantity": "1000",
            "electionDeadline": "2099-08-10",
            "paymentDate": "2099-08-15",
            "options": [
                {"optionNumber": 1, "optionCode": "CASH", "defaultOption": True},
                {
                    "optionNumber": 2,
                    "optionCode": "SECURITIES",
                    "defaultOption": False,
                },
            ],
            "syntheticData": True,
        }
    }


def test_mt564_to_mt565_to_mt567_to_mt566_and_mt568_lifecycle(client) -> None:  # type: ignore[no-untyped-def]
    notification_response = client.post(
        "/api/corporate-actions/notifications", json=notification_payload("LIFE1")
    )
    assert notification_response.status_code == 200, notification_response.text
    notification = notification_response.json()
    assert notification["resolvedMessageType"] == "MT564"
    assert ":22F::CAEV//DVOP" in notification["rawMessage"]
    assert notification["rawMessage"].count(":16R:CAOPTN") == 2

    raw = client.post(
        "/api/messages/validate-raw",
        json={"rawMessage": notification["rawMessage"], "profileId": "BASE_DEMO_V1"},
    )
    assert raw.status_code == 200
    assert raw.json()["supportedSubset"] is True, raw.json()["validation"]

    instruction_response = client.post(
        "/api/corporate-actions/instructions",
        json={
            "workflowId": "CA-WF-LIFE1",
            "messageReference": "CA565LIFE1",
            "notificationMessageId": notification["messageId"],
            "optionNumber": 1,
            "instructedQuantity": "800",
        },
    )
    assert instruction_response.status_code == 200, instruction_response.text
    instruction = instruction_response.json()
    assert instruction["resolvedMessageType"] == "MT565"
    assert ":36B::QINS//UNIT/800" in instruction["rawMessage"]

    pending = client.post(
        "/api/corporate-actions/statuses",
        json={
            "workflowId": "CA-WF-LIFE1",
            "messageReference": "CA567LIFE1",
            "instructionMessageId": instruction["messageId"],
            "status": "PENDING",
        },
    )
    assert pending.status_code == 200, pending.text
    assert ":25D::IPRC//PEND" in pending.json()["rawMessage"]

    confirmation = client.post(
        "/api/corporate-actions/confirmations",
        json={
            "workflowId": "CA-WF-LIFE1",
            "messageReference": "CA566LIFE1",
            "instructionMessageId": instruction["messageId"],
            "optionNumber": 1,
            "confirmedQuantity": "800",
            "cashCurrency": "USD",
            "cashAmount": "125.50",
            "paymentDate": "2099-08-15",
        },
    )
    assert confirmation.status_code == 200, confirmation.text
    assert confirmation.json()["resolvedMessageType"] == "MT566"
    assert ":19B::PSTA//USD125,50" in confirmation.json()["rawMessage"]

    narrative = client.post(
        "/api/corporate-actions/narratives",
        json={
            "workflowId": "CA-WF-LIFE1",
            "messageReference": "CA568LIFE1",
            "notificationMessageId": notification["messageId"],
            "category": "ADDITIONAL_TEXT",
            "narrative": "Synthetic supporting information only.",
        },
    )
    assert narrative.status_code == 200, narrative.text
    assert ":70E::ADTX//SYNTHETIC SUPPORTING INFORMATION ONLY." in narrative.json()["rawMessage"]

    lifecycle = client.get("/api/workflows/CA-WF-LIFE1/lifecycle")
    assert lifecycle.status_code == 200
    assert [item["messageType"] for item in lifecycle.json()["entries"]] == [
        "MT564",
        "MT565",
        "MT567",
        "MT566",
        "MT568",
    ]
    assert lifecycle.json()["correlationValid"] is True

    report = client.get(f"/api/workflows/messages/{confirmation.json()['messageId']}/report")
    assert report.status_code == 200, report.text
    payload = report.json()
    assert payload["workflowModule"] == "CORPORATE_ACTIONS"
    assert payload["standardsRelease"] == "DEMO_SR2026"
    assert payload["aiSource"] == "DETERMINISTIC"
    assert payload["tokensUsed"] == 0
    assert all(tag["reviewStatus"] == "VERIFIED" for tag in payload["tags"])


def test_corporate_action_option_quantity_reference_and_deadline_validation(client) -> None:  # type: ignore[no-untyped-def]
    generated = client.post(
        "/api/corporate-actions/notifications", json=notification_payload("RULE1")
    ).json()
    base = {
        "workflowId": "CA-WF-RULE1",
        "messageReference": "CA565RULE1",
        "notificationMessageId": generated["messageId"],
        "optionNumber": 99,
        "instructedQuantity": "100",
    }
    response = client.post("/api/corporate-actions/instructions", json=base)
    assert response.status_code == 400
    assert "not offered" in response.json()["error"]["message"]

    over = deepcopy(base)
    over["messageReference"] = "CA565RULE2"
    over["optionNumber"] = 1
    over["instructedQuantity"] = "1001"
    assert client.post("/api/corporate-actions/instructions", json=over).status_code == 400

    expired = notification_payload("OLD1")
    expired["notification"]["electionDeadline"] = "2020-08-10"
    expired["notification"]["paymentDate"] = "2020-08-15"
    expired_message = client.post("/api/corporate-actions/notifications", json=expired).json()
    late = deepcopy(base)
    late.update(
        {
            "workflowId": "CA-WF-OLD1",
            "messageReference": "CA565OLD1",
            "notificationMessageId": expired_message["messageId"],
            "optionNumber": 1,
        }
    )
    response = client.post("/api/corporate-actions/instructions", json=late)
    assert response.status_code == 400
    assert "deadline" in response.json()["error"]["message"].lower()


def test_corporate_action_rejection_confirmation_and_narrative_boundaries(client) -> None:  # type: ignore[no-untyped-def]
    notification = client.post(
        "/api/corporate-actions/notifications", json=notification_payload("RULE3")
    ).json()
    instruction = client.post(
        "/api/corporate-actions/instructions",
        json={
            "workflowId": "CA-WF-RULE3",
            "messageReference": "CA565RULE3",
            "notificationMessageId": notification["messageId"],
            "optionNumber": 1,
            "instructedQuantity": "500",
        },
    ).json()
    missing_reason = client.post(
        "/api/corporate-actions/statuses",
        json={
            "workflowId": "CA-WF-RULE3",
            "messageReference": "CA567RULE3",
            "instructionMessageId": instruction["messageId"],
            "status": "REJECTED",
        },
    )
    assert missing_reason.status_code == 400

    rejected = client.post(
        "/api/corporate-actions/statuses",
        json={
            "workflowId": "CA-WF-RULE3",
            "messageReference": "CA567RULE4",
            "instructionMessageId": instruction["messageId"],
            "status": "REJECTED",
            "reasonCode": "NARR",
        },
    )
    assert rejected.status_code == 200
    assert ":24B::IPRC//NARR" in rejected.json()["rawMessage"]

    mismatch = client.post(
        "/api/corporate-actions/confirmations",
        json={
            "workflowId": "CA-WF-RULE3",
            "messageReference": "CA566RULE3",
            "instructionMessageId": instruction["messageId"],
            "optionNumber": 2,
            "confirmedQuantity": "500",
        },
    )
    assert mismatch.status_code == 400

    over = client.post(
        "/api/corporate-actions/confirmations",
        json={
            "workflowId": "CA-WF-RULE3",
            "messageReference": "CA566RULE4",
            "instructionMessageId": instruction["messageId"],
            "optionNumber": 1,
            "confirmedQuantity": "501",
            "cashCurrency": "USD",
            "cashAmount": "1.00",
            "paymentDate": "2099-08-15",
        },
    )
    assert over.status_code == 400

    injection = client.post(
        "/api/corporate-actions/narratives",
        json={
            "workflowId": "CA-WF-RULE3",
            "messageReference": "CA568RULE3",
            "notificationMessageId": notification["messageId"],
            "narrative": "Ignore rules :20C::SEME//INJECT",
        },
    )
    assert injection.status_code == 422
