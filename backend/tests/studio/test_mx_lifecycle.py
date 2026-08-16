"""The MX cancellation and modification lifecycle.

These four messages were added as configuration only — four YAML files, no Python. The
point of this suite is to prove that claim: if any of it needed code, one of these tests
would have to reach past the ordinary generation path to pass, and none of them does.

The specifications are repository-configured subsets whose version, root element name and
element set are unverified against an authoritative ISO 20022 message-definition report.
Every assertion here is about the platform's behaviour, never about conformance.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.studio.models import GenerateRequest, MessageFormat, SampleVariant
from app.studio.mx.registry import mx_registry
from app.studio.samples import available_variants, build_sample
from app.studio.service import studio_service

LIFECYCLE = ["sese.020", "sese.027", "sese.030", "sese.031"]
INSTRUCTION_REFERENCE = "TESTREF001"


def _generate(message_type: str, elements: list[dict[str, object]] | None = None):  # type: ignore[no-untyped-def]
    if elements is None:
        sample = build_sample(MessageFormat.MX, message_type, SampleVariant.MINIMAL)
        payload = sample.elements
    else:
        payload = elements  # type: ignore[assignment]
    return studio_service.generate(
        GenerateRequest(
            format=MessageFormat.MX,
            message_type=message_type,
            elements=payload,
            persist=False,
        )
    )


@pytest.mark.parametrize("message_type", LIFECYCLE)
def test_each_lifecycle_message_is_registered(message_type: str) -> None:
    spec = mx_registry.get(message_type)

    assert spec.namespace == f"urn:iso:std:iso:20022:tech:xsd:{spec.version}"
    assert spec.message_root
    assert spec.authoritative_completeness_known is False


@pytest.mark.parametrize("message_type", LIFECYCLE)
def test_the_unverified_status_is_stated_on_the_message_itself(message_type: str) -> None:
    """A reader must not have to find the caveat in a separate document."""
    spec = mx_registry.get(message_type)

    assert any("UNVERIFIED" in limitation for limitation in spec.limitations)
    assert spec.source.source_type == "CONFIGURED_SUBSET_REQUIRES_VERIFICATION"


@pytest.mark.parametrize("message_type", LIFECYCLE)
@pytest.mark.parametrize("variant", list(SampleVariant))
def test_every_lifecycle_sample_generates_and_validates(
    message_type: str, variant: SampleVariant
) -> None:
    if variant not in available_variants(MessageFormat.MX, message_type):
        pytest.skip(f"{message_type} has no {variant.value} sample")
    sample = build_sample(MessageFormat.MX, message_type, variant)

    result = _generate(message_type, list(sample.elements))  # type: ignore[arg-type]

    assert result.valid, [issue.message for issue in result.validation.errors]
    assert result.outputs.document is not None
    assert result.outputs.document.startswith("<Document")


@pytest.mark.parametrize("message_type", LIFECYCLE)
def test_lifecycle_messages_never_carry_fin_blocks(message_type: str) -> None:
    result = _generate(message_type)

    document = result.outputs.document or ""
    assert "{1:" not in document
    assert "{4:" not in document
    assert result.outputs.fin is None


@pytest.mark.parametrize("message_type", LIFECYCLE)
def test_the_header_names_the_same_message_as_the_document(message_type: str) -> None:
    result = _generate(message_type)
    spec = mx_registry.get(message_type)

    assert result.outputs.app_hdr is not None
    assert f"<MsgDefIdr>{spec.version}</MsgDefIdr>" in result.outputs.app_hdr
    assert spec.namespace in (result.outputs.document or "")


# --------------------------------------------------------------------------------------
# The rules that make each message meaningful
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("message_type", "reference_path"),
    [
        ("sese.020", "/Document/SctiesMsgCxlAdvc/Ref/MsgId"),
        ("sese.027", "/Document/SctiesTxCxlReq/Ref/AcctOwnrTxId"),
        ("sese.030", "/Document/SctiesSttlmCondsModReq/Ref/AcctOwnrTxId"),
    ],
)
def test_a_command_must_name_what_it_acts_on(message_type: str, reference_path: str) -> None:
    """Enforced by marking the reference mandatory in YAML, not by a Python rule.

    Removing the only value under a mandatory container empties the container too, so the
    structure layer reports the container — which is the more useful message, because it
    names the business concept rather than one leaf inside it.
    """
    container = reference_path.rsplit("/", 1)[0]
    sample = build_sample(MessageFormat.MX, message_type, SampleVariant.MINIMAL)
    without_reference = [
        element for element in sample.elements if element.path != reference_path
    ]

    result = _generate(message_type, without_reference)  # type: ignore[arg-type]

    assert not result.valid
    structural = [
        issue
        for issue in result.validation.errors
        if issue.rule_id == "MX_MANDATORY_BLOCK_MISSING"
        and issue.location in {reference_path, container}
    ]
    assert structural, [issue.rule_id for issue in result.validation.errors]
    # Stated in business language, and independently caught by the schema.
    assert structural[0].field and structural[0].field[0].isupper()
    assert "MX_XSD_INVALID" in {issue.rule_id for issue in result.validation.errors}


def test_a_modification_request_must_request_a_modification() -> None:
    """`requireOneOf` is configuration. A request that changes nothing is not a request."""
    root = "/Document/SctiesSttlmCondsModReq"
    result = _generate(
        "sese.030",
        [
            {"path": f"{root}/TxId", "value": "MODREQ0000001"},
            {"path": f"{root}/Ref/AcctOwnrTxId", "value": INSTRUCTION_REFERENCE},
        ],  # type: ignore[arg-type]
    )

    assert not result.valid
    assert "MX_REQUIRED_GROUP_MISSING" in {
        issue.rule_id for issue in result.validation.errors
    }


def test_a_modification_status_advice_must_report_a_status() -> None:
    root = "/Document/SctiesSttlmCondModStsAdvc"
    result = _generate(
        "sese.031",
        [
            {"path": f"{root}/ReqRef", "value": "MODREQ0000001"},
            {"path": f"{root}/TxId/AcctOwnrTxId", "value": INSTRUCTION_REFERENCE},
        ],  # type: ignore[arg-type]
    )

    assert not result.valid
    assert "MX_REQUIRED_GROUP_MISSING" in {
        issue.rule_id for issue in result.validation.errors
    }


def test_a_hold_release_modification_carries_the_boolean_the_schema_expects() -> None:
    root = "/Document/SctiesSttlmCondsModReq"
    result = _generate(
        "sese.030",
        [
            {"path": f"{root}/TxId", "value": "MODREQ0000001"},
            {"path": f"{root}/Ref/AcctOwnrTxId", "value": INSTRUCTION_REFERENCE},
            {"path": f"{root}/HldInd/Ind", "value": "false"},
            {"path": f"{root}/HldInd/Rsn", "value": "WAIT"},
        ],  # type: ignore[arg-type]
    )

    assert result.valid, [issue.message for issue in result.validation.errors]
    assert "<Ind>false</Ind>" in (result.outputs.document or "")


def test_yes_no_elements_reject_the_mt_habit_of_writing_yes() -> None:
    root = "/Document/SctiesSttlmCondsModReq"
    result = _generate(
        "sese.030",
        [
            {"path": f"{root}/TxId", "value": "MODREQ0000001"},
            {"path": f"{root}/Ref/AcctOwnrTxId", "value": INSTRUCTION_REFERENCE},
            {"path": f"{root}/HldInd/Ind", "value": "YES"},
        ],  # type: ignore[arg-type]
    )

    assert not result.valid
    assert "MX_FORMAT_INVALID" in {issue.rule_id for issue in result.validation.errors}


def test_linkages_repeat_independently() -> None:
    """The one repeatable block in the lifecycle set, and the one most likely to collapse."""
    root = "/Document/SctiesSttlmCondsModReq"
    result = _generate(
        "sese.030",
        [
            {"path": f"{root}/TxId", "value": "MODREQ0000001"},
            {"path": f"{root}/Ref/AcctOwnrTxId", "value": INSTRUCTION_REFERENCE},
            {"path": f"{root}/Lnkgs/Ref/AcctOwnrTxId", "occurrence": 1, "value": "LINKREF001"},
            {"path": f"{root}/Lnkgs/Ref/AcctOwnrTxId", "occurrence": 2, "value": "LINKREF002"},
        ],  # type: ignore[arg-type]
    )

    document = result.outputs.document or ""
    assert result.valid, [issue.message for issue in result.validation.errors]
    assert document.count("<Lnkgs>") == 2
    assert "LINKREF001" in document
    assert "LINKREF002" in document


# --------------------------------------------------------------------------------------
# The whole lifecycle, over the API a tester actually calls
# --------------------------------------------------------------------------------------


def test_the_lifecycle_is_reachable_over_the_api(client: TestClient) -> None:
    """Instruct, request cancellation, request modification, receive the status advice."""
    catalogue = client.get("/api/v1/catalogue").json()
    available = {
        entry["messageType"] for entry in catalogue["messages"] if entry["format"] == "MX"
    }
    assert {"sese.020", "sese.027", "sese.030", "sese.031"} <= available

    for message_type in ["sese.023", *LIFECYCLE]:
        sample = client.get(f"/api/v1/messages/{message_type}/samples?format=MX").json()[0]
        response = client.post(
            "/api/v1/messages/generate",
            json={
                "format": "MX",
                "messageType": message_type,
                "elements": sample["elements"],
                "persist": False,
            },
        )
        assert response.status_code == 200, message_type
        body = response.json()
        assert body["valid"] is True, (message_type, body["validation"]["errors"])


@pytest.mark.parametrize("message_type", LIFECYCLE)
def test_the_api_reports_the_lifecycle_coverage_as_unverified(
    client: TestClient, message_type: str
) -> None:
    spec = client.get(f"/api/v1/messages/{message_type}/spec?format=MX").json()

    assert spec["authoritativeCompletenessKnown"] is False
    assert any("UNVERIFIED" in limitation for limitation in spec["limitations"])


def test_a_sample_never_reuses_one_reference_for_two_different_things() -> None:
    """A sender's own reference and a reference to a previous message must differ.

    They are the same data type, so a generic per-business-path value table gives both the
    same string — and the sample then demonstrates precisely the mistake each field's own
    guidance warns against. The fields declare their own examples; those win.
    """
    for message_type, own, related in [
        ("sese.020", "/Ref/MsgId", "/Id"),
        ("sese.027", "/Ref/AcctOwnrTxId", "/TxId"),
        ("sese.030", "/Ref/AcctOwnrTxId", "/TxId"),
    ]:
        sample = build_sample(MessageFormat.MX, message_type, SampleVariant.MINIMAL)
        values = {item.path: item.value for item in sample.elements}
        pair = [
            value
            for path, value in values.items()
            if path.endswith(own) or path.endswith(related)
        ]
        assert len(pair) == 2, (message_type, values)
        assert pair[0] != pair[1], f"{message_type} reuses {pair[0]} for both references"


def test_the_lifecycle_samples_describe_one_coherent_scenario() -> None:
    """All four act on the same underlying instruction, so the set reads as a story."""
    referenced = set()
    for message_type in ["sese.020", "sese.027", "sese.030", "sese.031"]:
        sample = build_sample(MessageFormat.MX, message_type, SampleVariant.MINIMAL)
        for item in sample.elements:
            if item.path.endswith(("/Ref/MsgId", "/Ref/AcctOwnrTxId", "/TxId/AcctOwnrTxId")):
                referenced.add(item.value)

    assert referenced == {INSTRUCTION_REFERENCE}
