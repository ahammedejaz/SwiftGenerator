def test_ai_health_is_safe_and_does_not_probe_provider(client) -> None:
    response = client.get("/api/ai/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "disabled"
    assert payload["primaryModel"] == "openai/gpt-5.4-mini"
    assert payload["escalationModel"] == "openai/gpt-5.4"
    assert payload["configured"] is False
    assert payload["privacyEnforcementEnabled"] is True
    serialized = response.text.casefold()
    assert "api_key" not in serialized
    assert "authorization" not in serialized


def test_required_ai_without_key_returns_controlled_503(client) -> None:
    response = client.post(
        "/api/agent/interpret",
        json={"text": "Receive securities against payment."},
    )
    assert response.status_code == 503
    payload = response.json()
    assert payload["error"]["code"] == "AI_NOT_CONFIGURED"
    assert "stack" not in response.text.casefold()


def test_explicit_deterministic_non_ai_path_remains_available(client) -> None:
    response = client.post(
        "/api/agent/interpret-deterministic",
        json={"text": "Receive securities against payment."},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["resolution"]["resolvedMessageType"] == "MT541"
    assert payload["ai"]["used"] is False
    assert payload["ai"]["provider"] == "deterministic_non_ai"


def test_model_slug_cannot_be_injected_through_interpretation_api(client) -> None:
    response = client.post(
        "/api/agent/interpret",
        json={
            "text": "Receive securities against payment.",
            "model": "attacker/arbitrary-model",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_SCHEMA_INVALID"


def test_ai_usage_and_cache_diagnostics_are_content_free(client) -> None:
    phrase = "Receive securities against payment for synthetic testing."
    interpreted = client.post(
        "/api/agent/interpret-deterministic",
        json={"text": phrase, "profileId": "BASE_DEMO_V1"},
    )
    assert interpreted.status_code == 200

    last = client.get("/api/ai/usage/last-interaction")
    assert last.status_code == 200
    assert last.json()["source"] == "DETERMINISTIC"
    assert last.json()["liveApiCallCount"] == 0
    assert phrase.casefold() not in last.text.casefold()

    summary = client.get("/api/ai/usage/summary", params={"days": 30})
    assert summary.status_code == 200
    assert summary.json()["deterministicInteractions"] >= 1

    stats = client.get("/api/ai/cache/stats")
    assert stats.status_code == 200
    assert stats.json()["enabled"] is False

    diagnosis = client.post("/api/ai/cache/diagnose")
    assert diagnosis.status_code == 200
    assert diagnosis.json()["storesPromptContent"] is False
    assert diagnosis.json()["storesPlaceholderMappings"] is False
    assert "cacheid" not in diagnosis.text.casefold()
