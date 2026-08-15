from tests.api.test_authoring_api import login


def test_supported_sample_round_trips_through_secure_draft(client) -> None:
    sample = client.get("/api/knowledge/samples/MT541-SYNTHETIC-V1").json()
    headers = login(client, "author")
    imported = client.post(
        "/api/messages/import",
        json={"rawMessage": sample["rawMessage"], "profileId": "BASE_DEMO_V1"},
        headers=headers,
    )
    assert imported.status_code == 200, imported.text
    body = imported.json()
    assert body["roundTripEquivalent"] is True
    assert body["unsupportedFields"] == []
    assert all(item["source"] == "IMPORTED_API" for item in body["draft"]["fields"])


def test_unknown_field_is_displayed_and_not_silently_validated(client) -> None:
    sample = client.get("/api/knowledge/samples/MT541-SYNTHETIC-V1").json()
    raw = sample["rawMessage"].replace(":16S:SETDET", ":99Z::EVIL//UNSUPPORTED\n:16S:SETDET")
    headers = login(client, "author")
    imported = client.post(
        "/api/messages/import",
        json={"rawMessage": raw, "profileId": "BASE_DEMO_V1"},
        headers=headers,
    )
    assert imported.status_code == 200
    body = imported.json()
    assert body["roundTripEquivalent"] is False
    assert body["unsupportedFields"][0]["rawLine"] == ":99Z::EVIL//UNSUPPORTED"


def test_every_composer_generated_sample_is_parseable(client) -> None:
    headers = login(client, "author")
    samples = client.get("/api/knowledge/samples").json()
    for summary in samples:
        sample = client.get(f"/api/knowledge/samples/{summary['sampleId']}").json()
        imported = client.post(
            "/api/messages/import",
            json={"rawMessage": sample["rawMessage"], "profileId": "BASE_DEMO_V1"},
            headers=headers,
        )
        assert imported.status_code == 200, (summary["messageType"], imported.text)
        assert imported.json()["unsupportedFields"] == [], summary["messageType"]
        assert imported.json()["roundTripEquivalent"] is True, summary["messageType"]
