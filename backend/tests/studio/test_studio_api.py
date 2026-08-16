"""The /api/v1 contract: discovery, generation, intelligence, downloads and auth."""

from __future__ import annotations

import json
from io import BytesIO
from zipfile import ZipFile

import pytest

from app.config import get_settings
from app.specifications.registry import specification_registry
from app.studio.mx.registry import mx_registry


def sample_request(client, format_: str, message_type: str, variant: str = "TYPICAL") -> dict:  # type: ignore[no-untyped-def]
    sample = client.get(f"/api/v1/messages/{message_type}/samples/{variant}").json()
    return {
        "format": format_,
        "messageType": message_type,
        "profileId": "BASE_DEMO_V1",
        "scenarioId": f"TC-{message_type}",
        "fields": sample["inputs"],
        "elements": sample["elements"],
    }


# -- discovery -------------------------------------------------------------------------


def test_catalogue_lists_both_formats(client) -> None:  # type: ignore[no-untyped-def]
    """Counts come from the registries, not from literals.

    A hardcoded count turns "someone added a YAML file" into a test failure that says
    nothing about whether the catalogue is correct. What matters is that the catalogue
    advertises exactly what is configured.
    """
    payload = client.get("/api/v1/catalogue").json()

    formats = {item["id"]: item for item in payload["formats"]}
    assert set(formats) == {"MT", "MX"}
    assert formats["MT"]["messageCount"] == len(specification_registry.list())
    assert formats["MX"]["messageCount"] == len(mx_registry.all_specs())
    assert formats["MX"]["messageCount"] > 0
    assert payload["defaultProfileId"] == "BASE_DEMO_V1"


def test_catalogue_declares_completeness_honestly(client) -> None:  # type: ignore[no-untyped-def]
    payload = client.get("/api/v1/catalogue").json()

    assert all(item["authoritativeCompletenessKnown"] is False for item in payload["messages"])
    assert all(item["limitations"] for item in payload["messages"])


def test_catalogue_only_offers_generatable_messages(client) -> None:  # type: ignore[no-untyped-def]
    payload = client.get("/api/v1/catalogue").json()

    assert all(item["generatable"] for item in payload["messages"])
    assert all(item["sampleVariants"] for item in payload["messages"])


def test_mt_and_mx_offer_different_output_modes(client) -> None:  # type: ignore[no-untyped-def]
    payload = client.get("/api/v1/catalogue").json()
    by_type = {item["messageType"]: item for item in payload["messages"]}

    assert "FIN" in by_type["MT541"]["outputModes"]
    assert "XML" not in by_type["MT541"]["outputModes"]
    assert "XML" in by_type["sese.023"]["outputModes"]
    assert "FIN" not in by_type["sese.023"]["outputModes"]


def test_spec_endpoint_infers_the_format(client) -> None:  # type: ignore[no-untyped-def]
    mt = client.get("/api/v1/messages/MT541/spec").json()
    mx = client.get("/api/v1/messages/sese.023/spec").json()

    assert mt["format"] == "MT"
    assert mx["format"] == "MX"
    assert mx["namespace"] == "urn:iso:std:iso:20022:tech:xsd:sese.023.001.11"


def test_spec_fields_carry_guidance_for_a_new_tester(client) -> None:  # type: ignore[no-untyped-def]
    spec = client.get("/api/v1/messages/MT541/spec").json()

    mandatory = [item for item in spec["fields"] if item["presence"] == "MANDATORY"]
    assert mandatory
    for field in mandatory:
        assert field["displayName"]
        assert field["businessMeaning"]
        assert field["formatExplanation"]


def test_unknown_message_type_is_a_404(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/api/v1/messages/MT999/spec?format=MT")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_samples_are_listed_per_message(client) -> None:  # type: ignore[no-untyped-def]
    payload = client.get("/api/v1/messages/sese.023/samples").json()

    assert {item["variant"] for item in payload} == {"MINIMAL", "TYPICAL", "FULL"}
    assert all(item["elements"] for item in payload)


# -- generation ------------------------------------------------------------------------


def test_mt_generation_returns_a_real_fin_message(client) -> None:  # type: ignore[no-untyped-def]
    response = client.post(
        "/api/v1/messages/generate", json=sample_request(client, "MT", "MT541")
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["valid"] is True
    assert payload["outputs"]["fin"].startswith("{1:F01")
    assert "{2:I541" in payload["outputs"]["fin"]
    assert "DEMONSTRATION" not in payload["outputs"]["fin"]


def test_mx_generation_returns_apphdr_and_document(client) -> None:  # type: ignore[no-untyped-def]
    payload = client.post(
        "/api/v1/messages/generate", json=sample_request(client, "MX", "sese.023")
    ).json()

    assert payload["valid"] is True
    assert payload["outputs"]["appHdr"].lstrip().startswith("<AppHdr")
    assert payload["outputs"]["document"].lstrip().startswith("<Document")
    assert payload["outputs"]["xml"].startswith('<?xml version="1.0"')


def test_response_carries_the_metadata_automation_needs(client) -> None:  # type: ignore[no-untyped-def]
    payload = client.post(
        "/api/v1/messages/generate", json=sample_request(client, "MT", "MT541")
    ).json()

    for key in ("messageId", "correlationId", "checksum", "profileId", "profileVersion"):
        assert payload[key]
    assert payload["scenarioId"] == "TC-MT541"
    assert payload["disclaimer"]


def test_validation_reports_actionable_errors_not_just_a_boolean(client) -> None:  # type: ignore[no-untyped-def]
    request = sample_request(client, "MT", "MT541")
    request["fields"] = [item for item in request["fields"] if item["qualifier"] != "SETT"]

    payload = client.post("/api/v1/messages/generate", json=request).json()

    assert payload["valid"] is False
    assert payload["validation"]["errors"]
    for issue in payload["validation"]["errors"]:
        assert issue["ruleId"]
        assert issue["severity"] == "ERROR"
        assert issue["message"]
        assert issue["suggestion"]


def test_validate_endpoint_does_not_persist(client) -> None:  # type: ignore[no-untyped-def]
    before = len(client.get("/api/v1/messages/recent?limit=200").json())

    client.post("/api/v1/messages/validate", json=sample_request(client, "MT", "MT541"))

    after = len(client.get("/api/v1/messages/recent?limit=200").json())
    assert after == before


def test_unknown_message_type_on_generate_is_a_404(client) -> None:  # type: ignore[no-untyped-def]
    response = client.post(
        "/api/v1/messages/generate",
        json={"format": "MX", "messageType": "pacs.008", "elements": []},
    )

    assert response.status_code == 404


def test_a_field_value_cannot_smuggle_fin_blocks(client) -> None:  # type: ignore[no-untyped-def]
    response = client.post(
        "/api/v1/messages/generate",
        json={
            "format": "MT",
            "messageType": "MT541",
            "fields": [{"sequence": "GENL", "tag": "20C", "qualifier": "SEME",
                        "value": "{1:F01HACK}"}],
        },
    )

    assert response.status_code == 422


# -- intelligence ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "expected_label"),
    [
        ("PSET", "Place of Settlement"),
        ("SttlmDt", "Intended Settlement Date"),
        ("settlement amount", "Settlement Amount"),
        ("DEAG", "Delivering Agent"),
    ],
)
def test_search_finds_the_obvious_answer_first(client, query: str, expected_label: str) -> None:  # type: ignore[no-untyped-def]
    payload = client.get("/api/v1/intelligence/search", params={"q": query}).json()

    assert payload["results"][0]["label"] == expected_label
    assert payload["llmUsed"] is False
    assert payload["deterministic"] is True


def test_search_spans_both_formats(client) -> None:  # type: ignore[no-untyped-def]
    payload = client.get("/api/v1/intelligence/search", params={"q": "PSET"}).json()

    assert {item["format"] for item in payload["results"]} == {"MT", "MX"}


def test_search_can_be_filtered_by_format(client) -> None:  # type: ignore[no-untyped-def]
    payload = client.get(
        "/api/v1/intelligence/search", params={"q": "PSET", "format": "MX"}
    ).json()

    assert {item["format"] for item in payload["results"]} == {"MX"}


def test_search_is_precise_rather_than_returning_everything(client) -> None:  # type: ignore[no-untyped-def]
    payload = client.get("/api/v1/intelligence/search", params={"q": "PSET"}).json()

    assert 0 < payload["total"] < 15


def test_search_for_nonsense_returns_nothing(client) -> None:  # type: ignore[no-untyped-def]
    payload = client.get("/api/v1/intelligence/search", params={"q": "zzzqqqxxx"}).json()

    assert payload["total"] == 0


def test_detail_explains_an_mt_tag_completely(client) -> None:  # type: ignore[no-untyped-def]
    hit = client.get(
        "/api/v1/intelligence/search", params={"q": "PSET", "format": "MT"}
    ).json()["results"][0]

    detail = client.get("/api/v1/intelligence/field", params={"id": hit["id"]}).json()

    assert detail["businessMeaning"]
    assert detail["whyUsed"]
    assert detail["formatExplanation"]
    assert detail["cardinality"]
    assert detail["sourceReference"]
    assert detail["messageTypes"]
    assert detail["sampleLines"]


def test_detail_explains_an_mx_element_completely(client) -> None:  # type: ignore[no-untyped-def]
    path = "/Document/SctiesSttlmTxInstr/TradDtls/SttlmDt/Dt/Dt"

    detail = client.get("/api/v1/intelligence/field", params={"id": path}).json()

    assert detail["address"] == path
    assert detail["dataType"] == "ISODate"
    assert detail["parent"] == "/Document/SctiesSttlmTxInstr/TradDtls/SttlmDt/Dt"
    assert detail["cardinality"] == "1..1"
    assert detail["sampleLines"]


def test_detail_for_an_unknown_field_is_a_404(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/api/v1/intelligence/field", params={"id": "/nope"})

    assert response.status_code == 404


def test_intelligence_makes_no_model_call(client) -> None:  # type: ignore[no-untyped-def]
    before = client.get("/api/ai/usage/summary").json()["interactions"]

    client.get("/api/v1/intelligence/search", params={"q": "PSET"})
    client.get(
        "/api/v1/intelligence/field",
        params={"id": "/Document/SctiesSttlmTxInstr/TxId"},
    )

    assert client.get("/api/ai/usage/summary").json()["interactions"] == before


# -- recent messages and downloads -----------------------------------------------------


def test_generated_message_appears_in_recent(client) -> None:  # type: ignore[no-untyped-def]
    generated = client.post(
        "/api/v1/messages/generate", json=sample_request(client, "MX", "sese.025")
    ).json()

    recent = client.get("/api/v1/messages/recent?limit=50").json()

    assert generated["messageId"] in {item["messageId"] for item in recent}


def test_recent_can_be_filtered_by_format(client) -> None:  # type: ignore[no-untyped-def]
    client.post("/api/v1/messages/generate", json=sample_request(client, "MT", "MT541"))
    client.post("/api/v1/messages/generate", json=sample_request(client, "MX", "sese.023"))

    assert {item["format"] for item in client.get("/api/v1/messages/recent?format=MT").json()} == {
        "MT"
    }


def test_message_can_be_fetched_by_id(client) -> None:  # type: ignore[no-untyped-def]
    generated = client.post(
        "/api/v1/messages/generate", json=sample_request(client, "MT", "MT541")
    ).json()

    payload = client.get(f"/api/v1/messages/id/{generated['messageId']}").json()

    assert payload["outputs"]["fin"] == generated["outputs"]["fin"]
    assert payload["inputs"]["messageType"] == "MT541"


@pytest.mark.parametrize("output", ["BLOCK4", "FIN", "TXT", "CANONICAL_JSON"])
def test_mt_downloads_preserve_the_exact_output(client, output: str) -> None:  # type: ignore[no-untyped-def]
    generated = client.post(
        "/api/v1/messages/generate", json=sample_request(client, "MT", "MT541")
    ).json()

    response = client.get(
        f"/api/v1/messages/id/{generated['messageId']}/download/{output}"
    )

    assert response.status_code == 200
    assert "attachment;" in response.headers["content-disposition"]
    if output == "FIN":
        assert response.text == generated["outputs"]["fin"]
    if output == "CANONICAL_JSON":
        assert json.loads(response.text)["messageType"] == "MT541"


@pytest.mark.parametrize("output", ["XML", "APPHDR", "DOCUMENT"])
def test_mx_downloads_preserve_encoding(client, output: str) -> None:  # type: ignore[no-untyped-def]
    generated = client.post(
        "/api/v1/messages/generate", json=sample_request(client, "MX", "sese.023")
    ).json()

    response = client.get(f"/api/v1/messages/id/{generated['messageId']}/download/{output}")

    assert response.status_code == 200
    assert "xml" in response.headers["content-type"]


def test_download_of_an_unproduced_output_is_a_404(client) -> None:  # type: ignore[no-untyped-def]
    generated = client.post(
        "/api/v1/messages/generate", json=sample_request(client, "MT", "MT541")
    ).json()

    response = client.get(f"/api/v1/messages/id/{generated['messageId']}/download/XML")

    assert response.status_code == 404


def test_evidence_zip_contains_every_output_and_the_metadata(client) -> None:  # type: ignore[no-untyped-def]
    generated = client.post(
        "/api/v1/messages/generate", json=sample_request(client, "MX", "sese.023")
    ).json()

    response = client.get(f"/api/v1/messages/id/{generated['messageId']}/evidence.zip")

    with ZipFile(BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert any(name.endswith(".xml") for name in names)
        assert any(name.endswith(".apphdr.xml") for name in names)
        assert any(name.endswith(".metadata.json") for name in names)
        metadata = json.loads(
            archive.read(next(n for n in names if n.endswith(".metadata.json")))
        )
    assert metadata["checksum"] == generated["checksum"]


def test_unknown_message_id_is_a_404(client) -> None:  # type: ignore[no-untyped-def]
    assert client.get("/api/v1/messages/id/not-a-real-id").status_code == 404


# -- automation authentication ---------------------------------------------------------


def test_development_leaves_the_api_open(client) -> None:  # type: ignore[no-untyped-def]
    assert client.get("/api/v1/catalogue").status_code == 200


def test_a_configured_key_is_required_once_keys_exist(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from pydantic import SecretStr

    settings = get_settings()
    monkeypatch.setattr(
        settings, "automation_api_keys", SecretStr("a" * 24 + ",b" * 24), raising=False
    )

    assert client.get("/api/v1/catalogue").status_code == 401
    assert (
        client.get("/api/v1/catalogue", headers={"X-API-Key": "a" * 24}).status_code == 200
    )
    assert (
        client.get("/api/v1/catalogue", headers={"X-API-Key": "wrong"}).status_code == 401
    )


def test_rejection_never_hints_at_the_key(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from pydantic import SecretStr

    secret = "s" * 32
    monkeypatch.setattr(get_settings(), "automation_api_keys", SecretStr(secret), raising=False)

    body = client.get("/api/v1/catalogue", headers={"X-API-Key": "nope"}).text

    assert secret not in body
    assert secret[:8] not in body


def test_production_without_keys_closes_the_api(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production", raising=False)
    monkeypatch.setattr(settings, "automation_api_keys", None, raising=False)

    assert client.get("/api/v1/catalogue").status_code == 503


# -- openapi ---------------------------------------------------------------------------


def test_openapi_documents_the_automation_api(client) -> None:  # type: ignore[no-untyped-def]
    schema = client.get("/openapi.json").json()

    assert "/api/v1/messages/generate" in schema["paths"]
    assert "/api/v1/messages/generate-from-excel" in schema["paths"]
    assert "/api/v1/catalogue" in schema["paths"]
    assert "/api/v1/intelligence/search" in schema["paths"]
