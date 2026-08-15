def test_oversized_request_is_rejected_before_body_parsing(client) -> None:
    response = client.post(
        "/api/messages/validate-raw",
        content=b"{}",
        headers={"Content-Length": "99999999", "Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "REQUEST_TOO_LARGE"


def test_malformed_json_does_not_expose_a_stack_trace(client) -> None:
    response = client.post(
        "/api/messages/generate",
        content=b'{"scenario":',
        headers={"Content-Type": "application/json"},
    )

    payload = response.json()
    assert response.status_code == 422
    assert payload["error"]["code"] == "REQUEST_SCHEMA_INVALID"
    assert "traceback" not in str(payload).lower()
