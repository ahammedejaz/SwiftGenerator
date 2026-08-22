"""A conversion that says what it needs must be completable by supplying exactly that.

The loop is the point. A conversion that reports missing data and then still cannot be
completed is a dead end, and MT103 to pacs.008 was one: the exchange rate reached
``XchgRate`` carrying its SWIFT decimal comma, which the MX FORMAT layer rejects and which
no caller input can repair. The recorded proof said READY because it only ever sent the
minimal sample, which omits field 36 altogether.

The candidate packs address the knowledge-preview lane and need the operator's indexed
corpus, so those cases skip where it is absent — the committed proofs in
``config/mappings/conversion-proofs.json`` and ``make mt-mx-mapping-check`` are the gate
that covers them on a machine that holds the sources.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.mapping.evidence import run_proofs
from app.mapping.registry import mapping_registry

#: What a caller would type for a target element the source message cannot supply, keyed by
#: the element's own name so a case does not have to restate the whole path.
ANSWERS = {
    "EndToEndId": "E2E-TEST-0001",
    "CreDtTm": "2026-08-22T10:00:00",
    "SttlmMtd": "INDA",
    "Nm": "ACME CORPORATION",
    "BICFI": "DEMOGB2LXXX",
    "AnyBIC": "DEMOGB2LXXX",
}


def _widest_fin(client: TestClient, message: str, lane: str, release: str | None) -> str:
    params: dict[str, str] = {"format": "MT", "lane": lane}
    if release:
        params["release"] = release
    listing = client.get(f"/api/v1/messages/{message}/samples", params=params)
    if listing.status_code != 200 or not listing.json():
        pytest.skip(f"{message} {release or lane} is not available on this machine")
    samples = listing.json()
    by_variant = {item["variant"]: item for item in samples}
    variant = by_variant.get("FULL") or by_variant.get("TYPICAL") or samples[-1]
    body: dict[str, object] = {
        "format": "MT",
        "messageType": message,
        "outputModes": ["FIN"],
        "fields": [{"id": item["id"], "value": item["value"]} for item in variant["inputs"]],
        "persist": False,
        "lane": lane,
    }
    if release:
        body["release"] = release
    generated = client.post("/api/v1/messages/generate", json=body)
    assert generated.status_code == 200, generated.text
    return str(generated.json()["outputs"]["fin"])


@pytest.mark.parametrize(
    ("source", "release", "target", "version", "target_lane"),
    [
        ("MT541", None, "sese.023", "sese.023.001.11", "CONFIGURED"),
        ("MT103", "SR2026", "pacs.008", "pacs.008.001.14", "KNOWLEDGE_PREVIEW"),
        ("MT202", "SR2026", "pacs.009", "pacs.009.001.13", "KNOWLEDGE_PREVIEW"),
    ],
)
def test_a_conversion_proof_can_actually_be_completed(
    client: TestClient,
    source: str,
    release: str | None,
    target: str,
    version: str,
    target_lane: str,
) -> None:
    source_lane = "KNOWLEDGE_PREVIEW" if release else "CONFIGURED"
    body: dict[str, object] = {
        "sourceFormat": "MT",
        "sourceMessage": source,
        "sourceRelease": release,
        "sourceLane": source_lane,
        "rawMessage": _widest_fin(client, source, source_lane, release),
        "targetFormat": "MX",
        "targetMessage": target,
        "targetVersion": version,
        "targetLane": target_lane,
        "allowSyntheticPreview": True,
        "targetValues": [],
    }
    asked: set[str] = set()
    payload: dict = {}
    for _ in range(6):
        response = client.post("/api/v1/messages/convert", json=body)
        assert response.status_code == 200, response.text
        payload = response.json()
        if payload["status"] != "NEEDS_INPUT":
            break
        missing = payload["report"]["targetRequiredMissing"]
        assert missing, "NEEDS_INPUT naming nothing is a dead end"
        for item in missing:
            # Every prompt is answerable: it says in words what it wants.
            assert item["question"].strip(), item["fieldId"]
            assert item["fieldId"] not in asked, f"asked twice for {item['fieldId']}"
            asked.add(item["fieldId"])
            leaf = item["fieldId"].rsplit("/", 1)[-1]
            body["targetValues"].append(  # type: ignore[union-attr]
                {
                    "path": item["fieldId"],
                    "occurrence": 1,
                    "value": ANSWERS.get(leaf, "TESTVALUE"),
                }
            )
    else:  # pragma: no cover - reached only if the loop never converges
        pytest.fail(f"{source} to {target} never stopped asking for data")

    assert payload["status"] == "READY", payload.get("validation")
    assert payload["validation"]["valid"] is True
    layers = {item["layer"]: item["state"] for item in payload["validation"]["layers"]}
    assert layers["XSD"] == "PASSED"
    assert layers["XML_WELL_FORMED"] == "PASSED"
    assert str(payload["outputXml"]).startswith("<?xml")


def test_a_swift_decimal_never_reaches_an_iso_decimal_element(client: TestClient) -> None:
    """MT ``d`` writes ``1000,``; an ISO 20022 decimal writes ``1000``."""
    body = {
        "sourceFormat": "MT",
        "sourceMessage": "MT103",
        "sourceRelease": "SR2026",
        "sourceLane": "KNOWLEDGE_PREVIEW",
        "rawMessage": _widest_fin(client, "MT103", "KNOWLEDGE_PREVIEW", "SR2026"),
        "targetFormat": "MX",
        "targetMessage": "pacs.008",
        "targetVersion": "pacs.008.001.14",
        "targetLane": "KNOWLEDGE_PREVIEW",
        "allowSyntheticPreview": True,
    }
    payload = client.post("/api/v1/messages/convert", json=body).json()
    decimals = [
        item["value"]
        for item in payload["targetValues"]
        if item["path"].endswith(("XchgRate", "IntrBkSttlmAmt", "InstdAmt"))
    ]
    assert decimals, payload["targetValues"]
    assert not any("," in value for value in decimals), decimals


def test_the_target_lane_decides_which_pack_resolves(client: TestClient) -> None:
    """Both candidate packs address the preview lane.

    A convert request that leaves the lane out resolves against CONFIGURED and is refused —
    which, behind a screen that has just listed the pack and had the user tick the preview
    opt-in, reads as a dead button rather than as a refusal. The browser sends the lane the
    target itself declares; this is the contract that lets it.
    """
    listing = client.get(
        "/api/v1/messages/MT103/conversion-targets",
        params={"sourceLane": "KNOWLEDGE_PREVIEW", "sourceRelease": "SR2026"},
    ).json()["targets"]
    if not listing:
        pytest.skip("the MT103 candidate pack is not resolvable on this machine")
    assert listing[0]["target"]["lane"] == "KNOWLEDGE_PREVIEW"

    body = {
        "sourceFormat": "MT",
        "sourceMessage": "MT103",
        "sourceRelease": "SR2026",
        "sourceLane": "KNOWLEDGE_PREVIEW",
        "rawMessage": _widest_fin(client, "MT103", "KNOWLEDGE_PREVIEW", "SR2026"),
        "targetFormat": "MX",
        "targetMessage": "pacs.008",
        "targetVersion": "pacs.008.001.14",
        "allowSyntheticPreview": True,
    }
    assert client.post("/api/v1/messages/convert", json=body).json()["status"] == (
        "BLOCKED_BY_MAPPING_EVIDENCE"
    )
    with_lane = client.post(
        "/api/v1/messages/convert", json={**body, "targetLane": "KNOWLEDGE_PREVIEW"}
    ).json()
    assert with_lane["status"] in {"NEEDS_INPUT", "READY"}


def test_every_recorded_proof_uses_the_widest_sample_and_still_passes() -> None:
    """A proof that only ever sends the mandatory rows never exercises an optional
    transform, and that is precisely where the defect this file exists for lived."""
    proofs = {item["packId"]: item for item in run_proofs()}
    assert set(proofs) == {pack.pack_id for pack in mapping_registry().packs}
    for pack_id, proof in proofs.items():
        if str(proof["status"]).startswith("NOT_RUN"):
            continue  # the pack's lane is not available on this machine
        assert proof["xsd"] == "accepted", (pack_id, proof)
        assert proof["missing"] == "none", (pack_id, proof)
        assert "READY" in str(proof["status"]), (pack_id, proof)
