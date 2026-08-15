def test_validate_generated_raw_message(client, valid_mt541_payload) -> None:
    generated = client.post("/api/messages/generate", json={"scenario": valid_mt541_payload}).json()

    response = client.post(
        "/api/messages/validate-raw",
        json={
            "profileId": "BASE_DEMO_V1",
            "rawMessage": generated["rawMessage"],
        },
    )

    assert response.status_code == 200
    assert response.json()["messageType"] == "MT541"
    assert response.json()["validation"]["status"] == "VALID"


def test_validate_raw_rejects_unsupported_enum(client) -> None:
    response = client.post(
        "/api/messages/validate-raw",
        json={"profileId": "NOT_A_PROFILE", "rawMessage": "not a message"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
