"""Mapping Packs disclose authority and loss before ordinary target generation."""

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.mapping.models import MappingReviewState
from app.mapping.service import mapping_service
from app.studio.models import MessageFormat, SampleVariant
from app.studio.samples import build_sample


def _request(*, allow: bool = False) -> dict[str, object]:
    sample = build_sample(MessageFormat.MT, "MT541", SampleVariant.TYPICAL)
    return {
        "sourceFormat": "MT",
        "sourceMessage": "MT541",
        "fields": [item.model_dump(by_alias=True, mode="json") for item in sample.inputs],
        "targetFormat": "MX",
        "targetMessage": "sese.023",
        "targetVersion": "sese.023.001.11",
        "allowSyntheticPreview": allow,
    }


def test_target_discovery_labels_synthetic_authority(client: TestClient) -> None:
    response = client.get("/api/v1/messages/MT541/conversion-targets")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["targets"]) == 1
    target = payload["targets"][0]
    assert target["target"]["release"] == "sese.023.001.11"
    assert target["reviewState"] == "SYNTHETIC_TEST_ONLY"
    assert target["productionEligible"] is False
    assert target["previewOnly"] is True
    assert "No production-eligible" in payload["authorityNote"]


def test_conversion_fails_closed_without_mapping_authority(client: TestClient) -> None:
    payload = client.post("/api/v1/messages/convert", json=_request()).json()

    assert payload["status"] == "BLOCKED_BY_MAPPING_EVIDENCE"
    assert payload["targetValues"] == []
    assert payload["outputXml"] is None


def test_synthetic_preview_maps_reports_loss_and_uses_normal_mx_validation(
    client: TestClient,
) -> None:
    before = client.get("/api/ai/usage/summary").json()["interactions"]
    response = client.post("/api/v1/messages/convert", json=_request(allow=True))

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "READY"
    assert payload["validation"]["valid"] is True
    assert payload["generation"]["format"] == "MX"
    assert payload["generation"]["version"] == "sese.023.001.11"
    assert payload["outputXml"].startswith("<?xml")
    assert payload["report"]["provenance"]["productionEligible"] is False
    assert "MT541-A-23G-NONE" in payload["report"]["sourceFieldsNotRepresented"]
    assert payload["report"]["targetRequiredMissing"] == []
    assert payload["report"]["transformationsApplied"]
    assert client.get("/api/ai/usage/summary").json()["interactions"] == before


def test_required_target_data_is_requested_and_never_invented(client: TestClient) -> None:
    request = _request(allow=True)
    request["fields"] = [
        item
        for item in request["fields"]  # type: ignore[union-attr]
        if item["id"] != "MT541-B-98A-SETT"
    ]

    payload = client.post("/api/v1/messages/convert", json=request).json()

    assert payload["status"] == "NEEDS_INPUT"
    missing = payload["report"]["targetRequiredMissing"]
    assert [item["fieldId"] for item in missing] == [
        "/Document/SctiesSttlmTxInstr/TradDtls/SttlmDt/Dt/Dt"
    ]
    assert payload["generation"] is None
    assert payload["outputXml"] is None


def test_wrong_target_version_has_no_fallback(client: TestClient) -> None:
    request = _request(allow=True)
    request["targetVersion"] = "sese.023.001.10"

    payload = client.post("/api/v1/messages/convert", json=request).json()

    assert payload["status"] == "BLOCKED_BY_MAPPING_EVIDENCE"
    assert "No exact Mapping Pack" in payload["message"]


def test_mapping_structure_checksum_mismatch_is_refused(
    client: TestClient, monkeypatch: MonkeyPatch
) -> None:
    pack = mapping_service._registry._packs[0]
    monkeypatch.setattr(
        mapping_service._registry,
        "_packs",
        (pack.model_copy(update={"target_structure_checksum": "0" * 64}),),
    )

    response = client.post("/api/v1/messages/convert", json=_request(allow=True))

    assert response.status_code == 422
    assert "target structure checksum does not match" in response.json()["error"]["message"]


def test_mapping_evidence_checksum_mismatch_is_refused(
    client: TestClient, monkeypatch: MonkeyPatch
) -> None:
    pack = mapping_service._registry._packs[0]
    provenance = pack.provenance.model_copy(update={"source_checksum": "0" * 64})
    monkeypatch.setattr(
        mapping_service._registry,
        "_packs",
        (pack.model_copy(update={"provenance": provenance}),),
    )

    response = client.post("/api/v1/messages/convert", json=_request(allow=True))

    assert response.status_code == 422
    assert "evidence checksum does not match" in response.json()["error"]["message"]


def test_candidate_mapping_pack_never_executes(
    client: TestClient, monkeypatch: MonkeyPatch
) -> None:
    pack = mapping_service._registry._packs[0]
    provenance = pack.provenance.model_copy(
        update={"review_state": MappingReviewState.CANDIDATE}
    )
    monkeypatch.setattr(
        mapping_service._registry,
        "_packs",
        (pack.model_copy(update={"provenance": provenance}),),
    )

    payload = client.post(
        "/api/v1/messages/convert", json=_request(allow=True)
    ).json()

    assert payload["status"] == "BLOCKED_BY_MAPPING_EVIDENCE"
    assert "unreviewed candidate" in payload["message"]
