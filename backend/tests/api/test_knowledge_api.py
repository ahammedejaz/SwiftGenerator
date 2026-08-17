def test_knowledge_endpoints_return_verified_deterministic_pset(client) -> None:  # type: ignore[no-untyped-def]
    messages = client.get("/api/knowledge/messages")
    assert messages.status_code == 200
    assert {item["messageType"] for item in messages.json()} == {
        "MT530",
        "MT537",
        *(f"MT{number}" for number in range(540, 549)),
        *(f"MT{number}" for number in range(564, 569)),
    }

    response = client.get(
        "/api/knowledge/tags/MT541-E-95R-PSET",
        params={"profileId": "BFS_CLIENT_DEMO_V1"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["record"]["displayName"] == "Place of Settlement"
    assert result["profileOverrideApplied"] is True
    assert result["record"]["source"]["reviewStatus"] == "VERIFIED"

    search = client.get("/api/knowledge/search", params={"q": "settlement venue"})
    assert search.status_code == 200
    assert search.json()["deterministic"] is True
    assert search.json()["llmUsed"] is False

    explain = client.post(
        "/api/knowledge/explain",
        json={"knowledgeId": "MT541-E-95R-PSET", "profileId": "BASE_DEMO_V1"},
    )
    assert explain.status_code == 200
    assert explain.json()["record"]["qualifier"] == "PSET"


def test_knowledge_filters_and_safe_errors(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get(
        "/api/knowledge/tags",
        params={"messageType": "MT541", "qualifier": "PSET"},
    )
    assert response.status_code == 200
    # One business party, two ways to identify it: a BIC under option P and a proprietary
    # scheme identifier under option R.
    assert {item["record"]["fieldTag"] for item in response.json()} == {"95P", "95R"}

    dependencies = client.get("/api/knowledge/dependencies/MT541-E-95R-PSET")
    assert dependencies.status_code == 200
    assert {item["record"]["qualifier"] for item in dependencies.json()["relatedFields"]} == {
        "DEAG",
        "REAG",
    }

    missing = client.get("/api/knowledge/tags/MT541-E-95R-UNKNOWN")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
