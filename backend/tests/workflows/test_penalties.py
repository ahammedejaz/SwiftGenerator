from copy import deepcopy


def penalty_payload(reference: str = "PENASTMT0001") -> dict[str, object]:
    return {
        "statement": {
            "workflowId": f"WF-{reference}",
            "profileId": "BASE_DEMO_V1",
            "statementReference": reference,
            "statementDate": "2026-08-05",
            "safekeepingAccount": "SYNTHSAFE01",
            "accountServicer": "SYNTHSERVICER",
            "relatedParty": "SYNTHPARTY",
            "listType": "NEW_ONLY",
            "penalties": [
                {
                    "penaltyReference": f"P-{reference}"[:16],
                    "commonReference": "COMMON0001",
                    "relatedInstructionReference": "ORIGSETTLE001",
                    "penaltyType": "SETTLEMENT_FAIL",
                    "action": "NEW",
                    "status": "ACTIVE",
                    "currency": "EUR",
                    "amount": "25.00",
                    "amountDirection": "PAYABLE",
                    "detectionDate": "2026-08-04",
                    "numberOfDays": 1,
                }
            ],
            "syntheticData": True,
        }
    }


def test_mt537_new_settlement_fail_generates_and_parses(client) -> None:  # type: ignore[no-untyped-def]
    response = client.post("/api/penalties/generate", json=penalty_payload())
    assert response.status_code == 200, response.text
    generated = response.json()
    assert generated["resolvedMessageType"] == "MT537"
    assert generated["validation"]["status"] == "VALID"
    assert ":22F::CODE//FWIS" in generated["rawMessage"]
    assert ":22H::PNTP//SEFP" in generated["rawMessage"]
    assert ":19A::AMCO//NEUR25,00" in generated["rawMessage"]

    parsed = client.post(
        "/api/messages/validate-raw",
        json={"rawMessage": generated["rawMessage"], "profileId": "BASE_DEMO_V1"},
    )
    assert parsed.status_code == 200
    assert parsed.json()["supportedSubset"] is True
    assert parsed.json()["messageType"] == "MT537"

    lifecycle = client.get("/api/workflows/WF-PENASTMT0001/lifecycle")
    assert lifecycle.status_code == 200
    assert lifecycle.json()["entries"][0]["messageType"] == "MT537"

    report = client.get(f"/api/workflows/messages/{generated['messageId']}/report")
    assert report.status_code == 200, report.text
    assert report.json()["workflowModule"] == "PENALTIES"
    assert all(tag["reviewStatus"] == "VERIFIED" for tag in report.json()["tags"])


def test_mt537_updated_removed_active_and_not_computed_controls(client) -> None:  # type: ignore[no-untyped-def]
    updated = penalty_payload("PENAUPD0001")
    statement = updated["statement"]
    assert isinstance(statement, dict)
    statement["listType"] = "UPDATED_OR_REMOVED"
    penalties = statement["penalties"]
    assert isinstance(penalties, list)
    penalties[0]["action"] = "UPDATED"
    penalties[0]["status"] = "NOT_COMPUTED"
    penalties[0]["penaltyType"] = "LATE_MATCHING_FAIL"
    penalties[0]["amountDirection"] = "RECEIVABLE"
    response = client.post("/api/penalties/generate", json=updated)
    assert response.status_code == 200, response.text
    assert ":22F::CODE//FWAM" in response.json()["rawMessage"]
    assert ":22H::PNTP//LMFP" in response.json()["rawMessage"]
    assert ":25D::PNST//NCOM" in response.json()["rawMessage"]

    removed = deepcopy(updated)
    removed["statement"]["statementReference"] = "PENAREM0001"
    removed["statement"]["workflowId"] = "WF-PENAREM0001"
    removed["statement"]["penalties"][0]["penaltyReference"] = "PENAREMDETAIL01"
    removed["statement"]["penalties"][0]["action"] = "REMOVED"
    removed["statement"]["penalties"][0]["status"] = "REMOVED"
    response = client.post("/api/penalties/generate", json=removed)
    assert response.status_code == 200, response.text
    assert ":25D::PNST//REMO" in response.json()["rawMessage"]


def test_mt537_rejects_action_status_amount_currency_duplicates_and_missing_reference(
    client,
) -> None:  # type: ignore[no-untyped-def]
    invalid_status = penalty_payload("PENABAD0001")
    invalid_status["statement"]["penalties"][0]["action"] = "REMOVED"
    response = client.post("/api/penalties/generate", json=invalid_status)
    assert response.status_code == 422

    invalid_amount = penalty_payload("PENABAD0002")
    invalid_amount["statement"]["penalties"][0]["amount"] = "-1"
    assert client.post("/api/penalties/generate", json=invalid_amount).status_code == 422

    invalid_currency = penalty_payload("PENABAD0003")
    invalid_currency["statement"]["penalties"][0]["currency"] = "JPY"
    response = client.post("/api/penalties/validate", json=invalid_currency)
    assert response.status_code == 200
    assert response.json()["status"] == "INVALID"

    duplicate = penalty_payload("PENABAD0004")
    duplicate["statement"]["penalties"].append(deepcopy(duplicate["statement"]["penalties"][0]))
    assert client.post("/api/penalties/generate", json=duplicate).status_code == 422

    missing_reference = penalty_payload("PENABAD0005")
    missing_reference["statement"]["penalties"][0]["penaltyReference"] = ""
    assert client.post("/api/penalties/generate", json=missing_reference).status_code == 422


def test_mt537_correlates_to_persisted_settlement(client, valid_mt541_payload) -> None:  # type: ignore[no-untyped-def]
    scenario = deepcopy(valid_mt541_payload)
    scenario["senderReference"] = "PENALINK0001"
    generated_instruction = client.post(
        "/api/messages/generate", json={"scenario": scenario}
    ).json()
    payload = penalty_payload("PENALINKSTMT01")
    payload["relatedSettlementMessageId"] = generated_instruction["messageId"]
    payload["statement"]["penalties"][0]["relatedInstructionReference"] = "PENALINK0001"
    response = client.post("/api/penalties/generate", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["relatedSettlementMessageId"] == generated_instruction["messageId"]

    bad = penalty_payload("PENALINKSTMT02")
    bad["relatedSettlementMessageId"] = generated_instruction["messageId"]
    response = client.post("/api/penalties/validate", json=bad)
    assert response.json()["status"] == "INVALID"
    assert response.json()["findings"][0]["ruleId"] == "MT537-REFERENCE-CORRELATION"
