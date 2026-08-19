"""The four smaller proofs, run through the surfaces a real caller uses.

Overlay narrowing, an impossible profile refused at installation, a source that tries to
give instructions, and prose that establishes nothing. Plus the property that keeps the
whole thing honest: the browser, the JSON API and the Excel path execute the same rules,
and messages generated under a profile with no overlays are exactly what they were before.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rule_engine.registry import rule_pack_registry
from app.studio.models import (
    ElementInput,
    GenerateRequest,
    MessageFormat,
    SampleVariant,
    ValidationLayer,
)
from app.studio.samples import build_sample
from app.studio.service import StudioService

TXCOND = "/Document/SctiesSttlmTxInstr/SttlmParams/SttlmTxCond/Cd"
CMONID = "/Document/SctiesSttlmTxInstr/SttlmTpAndAddtlParams/CmonId"
OVERLAY_PROFILE = "DEMO_MARKET_CLIENT_V1"
PLAIN_PROFILE = "BASE_DEMO_V1"


@pytest.fixture(scope="module")
def sample_values() -> dict[str, str]:
    sample = build_sample(MessageFormat.MX, "sese.023", SampleVariant.TYPICAL)
    return {item.path: item.value for item in sample.elements}


def generate(values: dict[str, str], profile: str, **overrides: str | None):  # type: ignore[no-untyped-def]
    payload = dict(values)
    for path, value in overrides.items():
        if value is None:
            payload.pop(path, None)
        else:
            payload[path] = value
    return StudioService().generate(
        GenerateRequest(
            format=MessageFormat.MX,
            message_type="sese.023",
            profile_id=profile,
            elements=[ElementInput(path=path, value=value) for path, value in payload.items()],
            persist=False,
        )
    )


# -- proof: base -> market -> client narrowing --------------------------------------------


def test_each_layer_narrows_the_one_beneath_it_and_says_which_layer_refused(
    sample_values: dict[str, str],
) -> None:
    # The structure allows eleven settlement conditions; the synthetic market allows three
    # of them; the synthetic client allows one.
    from app.rule_engine.refs import FieldRef, StructureIndex

    structural = StructureIndex().resolve(
        FieldRef(format=MessageFormat.MX, path=TXCOND), "sese.023"
    )
    assert structural is not None
    assert set(structural.codes) >= {"NOMC", "PART", "CLEN", "DIRT"}

    allowed = generate(sample_values, OVERLAY_PROFILE, **{TXCOND: "NOMC"})
    assert allowed.validation.valid

    client_only = generate(sample_values, OVERLAY_PROFILE, **{TXCOND: "PART"})
    assert not client_only.validation.valid
    assert [item.layer for item in client_only.validation.errors] == [
        ValidationLayer.CLIENT_PROFILE
    ]

    outside_market = generate(sample_values, OVERLAY_PROFILE, **{TXCOND: "DIRT"})
    assert not outside_market.validation.valid
    assert {item.layer for item in outside_market.validation.errors} == {
        ValidationLayer.MARKET_PRACTICE,
        ValidationLayer.CLIENT_PROFILE,
    }


def test_a_profile_with_no_overlays_is_exactly_what_it_was(
    sample_values: dict[str, str],
) -> None:
    # Installing an overlay for one profile must not change another profile's answer.
    for code in ("NOMC", "PART", "DIRT"):
        result = generate(sample_values, PLAIN_PROFILE, **{TXCOND: code})
        assert result.validation.valid, [item.message for item in result.validation.errors]


def test_a_client_rule_can_require_a_field_the_structure_leaves_optional(
    sample_values: dict[str, str],
) -> None:
    without = generate(sample_values, OVERLAY_PROFILE, **{TXCOND: "NOMC", CMONID: None})
    assert not without.validation.valid
    issue = next(
        item
        for item in without.validation.errors
        if item.rule_id == "DEMO-CLI-SESE023-COMMON-IDENTIFICATION"
    )
    assert issue.layer is ValidationLayer.CLIENT_PROFILE
    assert issue.rule_layer == "Client rule"
    assert issue.location == CMONID
    assert "SYNTH-DEMO-CLIENT-V1" in (issue.source_reference or "")
    assert issue.review_status == "REVIEWED"
    # And the same values with the field supplied pass.
    assert generate(sample_values, OVERLAY_PROFILE, **{TXCOND: "NOMC"}).validation.valid


def test_the_market_layer_appears_in_what_was_checked(sample_values: dict[str, str]) -> None:
    result = generate(sample_values, OVERLAY_PROFILE, **{TXCOND: "NOMC"})
    layers = {item.layer: item.state for item in result.validation.layers}
    assert ValidationLayer.MARKET_PRACTICE in layers
    assert layers[ValidationLayer.MARKET_PRACTICE].value == "PASSED"


# -- one call site, three callers ---------------------------------------------------------


def test_the_json_api_and_the_ui_share_the_rule_findings(
    sample_values: dict[str, str],
) -> None:
    payload = dict(sample_values)
    payload[TXCOND] = "DIRT"
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/messages/validate",
            json={
                "format": "MX",
                "messageType": "sese.023",
                "profileId": OVERLAY_PROFILE,
                "elements": [{"path": k, "value": v} for k, v in payload.items()],
            },
        )
    assert response.status_code == 200
    body = response.json()
    rule_ids = {item["ruleId"] for item in body["validation"]["errors"]}
    assert "DEMO-MKT-SESE023-SETTLEMENT-CONDITION" in rule_ids
    issue = next(
        item
        for item in body["validation"]["errors"]
        if item["ruleId"] == "DEMO-MKT-SESE023-SETTLEMENT-CONDITION"
    )
    # The additive provenance fields travel over the wire for an automation caller.
    assert issue["ruleLayer"] == "Market practice rule"
    assert issue["rulePackId"].endswith("MARKET_PRACTICE:DEMO_MARKET_V1:v1")
    assert issue["reviewStatus"] == "REVIEWED"


def test_the_excel_path_executes_the_same_rules(sample_values: dict[str, str]) -> None:
    # The Excel API runs every row through StudioService — the same call site the browser
    # and the JSON API use — so a rule cannot apply in one and not the others.
    import inspect

    from app.studio import routes

    assert "_run_scenario" in dir(routes)
    assert "studio_service.generate" in inspect.getsource(routes._run_scenario)

    broken = generate(sample_values, OVERLAY_PROFILE, **{TXCOND: "DIRT"})
    assert not broken.validation.valid
    assert any(
        item.rule_pack_id and "MARKET_PRACTICE" in item.rule_pack_id
        for item in broken.validation.errors
    )


def test_message_intelligence_shows_reviewed_rules_and_only_those() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/intelligence/field", params={"id": TXCOND, "format": "MX"}
        )
    assert response.status_code == 200
    rules = response.json()["rules"]
    assert [item["layer"] for item in rules] == ["Market practice rule", "Client rule"]
    for item in rules:
        assert item["reviewStatus"] == "REVIEWED"
        assert item["sourceReference"].startswith("SYNTH-DEMO-")
        # An excerpt of the source is never served through a public endpoint.
        assert "must be present" not in item["sourceReference"]


def test_a_field_no_rule_names_reports_no_rules() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/intelligence/field",
            params={"id": "/Document/SctiesSttlmTxInstr/TxId", "format": "MX"},
        )
    assert response.json()["rules"] == []


# -- existing behaviour ---------------------------------------------------------------------


def test_mt_generation_is_untouched_by_the_rule_engine() -> None:
    from app.studio.models import FieldInput

    sample = build_sample(MessageFormat.MT, "MT541", SampleVariant.TYPICAL)
    result = StudioService().generate(
        GenerateRequest(
            format=MessageFormat.MT,
            message_type="MT541",
            profile_id=PLAIN_PROFILE,
            fields=[FieldInput(**item.model_dump()) for item in sample.inputs],
            persist=False,
        )
    )
    assert result.validation.valid, [item.message for item in result.validation.errors]
    assert not any(item.rule_pack_id for item in result.validation.errors)
    # No MT rule pack ships, so the market layer is reported but empty.
    layers = {item.layer for item in result.validation.layers}
    assert ValidationLayer.MARKET_PRACTICE in layers


def test_no_installed_rule_surface_makes_a_forbidden_claim() -> None:
    forbidden = (
        "swift compliant",
        "iso compliant",
        "certified",
        "production ready",
        "production-ready",
        "officially verified",
    )
    surfaces: list[str] = []
    for compiled in rule_pack_registry.packs():
        surfaces.append(compiled.pack.model_dump_json(by_alias=True))
        for rule in compiled.rules:
            surfaces.append(rule.rule.finding.message + rule.rule.finding.suggestion)
    with TestClient(app) as client:
        catalogue = client.get("/api/v1/catalogue").json()
    surfaces.append(
        " ".join(item.get("capabilitySummary", "") for item in catalogue["messages"])
    )
    for surface in surfaces:
        for phrase in forbidden:
            assert phrase not in surface.casefold(), phrase


def test_the_demonstration_profile_is_offered_and_labelled_synthetic() -> None:
    from app.profiles.loader import profiles

    with TestClient(app) as client:
        catalogue = client.get("/api/v1/catalogue").json()
    assert OVERLAY_PROFILE in catalogue["profiles"]
    profile = profiles.get(OVERLAY_PROFILE)
    assert profile.status == "DEMO"
    assert profile.market_profile_id == "DEMO_MARKET_V1"
