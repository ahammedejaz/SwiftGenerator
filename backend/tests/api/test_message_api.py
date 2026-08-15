def test_health(client) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["messageStandardScope"] == (
        "Configured source-bounded Category 5 subset"
    )


def test_profile_detail_and_controlled_statuses(client) -> None:
    profile = client.get("/api/profiles/BFS_CLIENT_DEMO_V1")
    status_options = client.get("/api/statuses")

    assert profile.status_code == 200
    assert profile.json()["senderReferenceMaxLength"] == 12
    assert "client_reference" in profile.json()["clientRequiredFields"]["MT541"]
    assert status_options.status_code == 200
    assert {item["category"] for item in status_options.json()} >= {
        "PENDING",
        "REJECTED",
        "MATCHED",
    }


def test_resolve_mt541(client) -> None:
    response = client.post(
        "/api/messages/resolve",
        json={
            "lifecycle": "INSTRUCTION",
            "direction": "RECEIVE",
            "paymentType": "AGAINST_PAYMENT",
        },
    )
    assert response.status_code == 200
    assert response.json()["resolvedMessageType"] == "MT541"


def test_generate_valid_mt541(client, valid_mt541_payload) -> None:
    response = client.post("/api/messages/generate", json={"scenario": valid_mt541_payload})
    assert response.status_code == 200
    payload = response.json()
    assert payload["resolvedMessageType"] == "MT541"
    assert payload["validation"]["status"] == "VALID"
    assert payload["rawMessage"].startswith("{1:DEMONSTRATION}\n{2:MT541}")
    assert "not transmitted through or certified by the Swift network" in payload["disclaimer"]


def test_generate_blocks_missing_amount(client, valid_mt541_payload) -> None:
    valid_mt541_payload["settlement"]["amount"] = None
    response = client.post("/api/messages/generate", json={"scenario": valid_mt541_payload})
    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_FAILED"
    assert any(
        item["ruleId"] == "MT541-SETTLEMENT-AMOUNT-REQUIRED" for item in payload["error"]["details"]
    )


def test_request_schema_rejects_unknown_enum_without_echoing_body(client) -> None:
    response = client.post(
        "/api/messages/resolve",
        json={
            "lifecycle": "INSTRUCTION",
            "direction": "BUY_THE_THING",
            "paymentType": "AGAINST_PAYMENT",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_SCHEMA_INVALID"
