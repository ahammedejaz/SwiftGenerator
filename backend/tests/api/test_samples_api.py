def test_sample_catalogue_and_annotation_api(client) -> None:
    listing = client.get("/api/knowledge/samples")
    assert listing.status_code == 200
    assert len(listing.json()) == 16
    detail = client.get("/api/knowledge/samples/MT537-SYNTHETIC-V1")
    assert detail.status_code == 200
    body = detail.json()
    assert body["generatedByProductionComposer"] is True
    assert body["synthetic"] is True
    assert any(item["sequencePath"] == "D1a1" for item in body["annotations"])


def test_sample_load_preserves_repeatable_sequences_and_sample_provenance(client) -> None:
    from tests.api.test_authoring_api import login

    headers = login(client, "author")
    loaded = client.post("/api/knowledge/samples/MT564-SYNTHETIC-V1/load", headers=headers)
    assert loaded.status_code == 200, loaded.text
    body = loaded.json()
    options = [item for item in body["sequences"] if item["sequencePath"] == "E"]
    assert len(options) == 2
    assert all(item["source"] == "SAMPLE_DATA" for item in body["fields"])
    assert all(item["confirmed"] is False for item in body["fields"])
