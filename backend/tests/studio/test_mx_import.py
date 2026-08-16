"""MX import and the round-trip property.

The property under test is::

    Compose(Parse(Compose(values))) == Compose(values)

Comparing the recomposed *document* rather than the parsed value list is deliberate. Two
value lists can differ harmlessly — a currency the composer upper-cases, an ordering the
composer normalises — while denoting the same message. The document is the artifact a
tester actually receives, so equality of documents is the guarantee worth making.

Every negative case here asserts that something was *reported*. An importer that silently
drops what it does not understand is worse than one that refuses, because the tester ships
a message they believe round-tripped.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.profiles.loader import profiles
from app.studio.models import ElementInput, MessageFormat, SampleVariant
from app.studio.mx.generator import mx_generator
from app.studio.mx.parser import MxImportError, parse_message
from app.studio.mx.registry import mx_registry
from app.studio.samples import available_variants, build_sample

# Derived from the registry, so a message added as YAML is covered by the round trip
# without anyone remembering to extend this list.
MX_TYPES = [spec.message_type for spec in mx_registry.all_specs()]
PROFILE = "BASE_DEMO_V1"
INSTRUCTION = "/Document/SctiesSttlmTxInstr"
CONDITION = f"{INSTRUCTION}/SttlmParams/SttlmTxCond/Cd"


def _profile():  # type: ignore[no-untyped-def]
    return profiles.get(PROFILE)


def _compose(message_type: str, elements: list[ElementInput], envelope=None):  # type: ignore[no-untyped-def]
    return mx_generator.build(message_type, _profile(), elements, envelope=envelope)


def _sample_elements(message_type: str, variant: SampleVariant) -> list[ElementInput]:
    return list(build_sample(MessageFormat.MX, message_type, variant).elements)


# --------------------------------------------------------------------------------------
# The round trip
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("message_type", MX_TYPES)
@pytest.mark.parametrize("variant", list(SampleVariant))
def test_every_sample_round_trips_to_an_identical_document(
    message_type: str, variant: SampleVariant
) -> None:
    if variant not in available_variants(MessageFormat.MX, message_type):
        pytest.skip(f"{message_type} has no {variant.value} sample")
    original = _compose(message_type, _sample_elements(message_type, variant))

    parsed = parse_message(original.xml)
    regenerated = _compose(
        parsed.specification.message_type, parsed.elements, envelope=parsed.envelope
    )

    assert parsed.errors == []
    assert regenerated.document == original.document


@pytest.mark.parametrize("message_type", MX_TYPES)
def test_import_recovers_every_value_that_was_composed(message_type: str) -> None:
    elements = _sample_elements(message_type, SampleVariant.FULL)
    original = _compose(message_type, elements)

    parsed = parse_message(original.xml)

    assert {(item.path, item.occurrence) for item in parsed.elements} == {
        (item.flat.path, item.occurrence) for item in original.resolved
    }


def test_repeated_blocks_keep_their_own_occurrence() -> None:
    """The composer threads one occurrence index down through a repeatable block.

    If the parser does not thread the same index back up, every repeat collapses onto the
    first one's values and the loss is invisible in the output.
    """
    elements = [
        *_sample_elements("sese.023", SampleVariant.TYPICAL),
        ElementInput(path=CONDITION, occurrence=1, value="NOMC"),
        ElementInput(path=CONDITION, occurrence=2, value="PART"),
        ElementInput(path=CONDITION, occurrence=3, value="CLEN"),
    ]
    original = _compose("sese.023", elements)

    parsed = parse_message(original.xml)

    conditions = sorted(
        (item.occurrence, item.value) for item in parsed.elements if item.path == CONDITION
    )
    assert conditions == [(1, "NOMC"), (2, "PART"), (3, "CLEN")]
    assert _compose("sese.023", parsed.elements).document == original.document


def test_amount_and_currency_attribute_are_rejoined() -> None:
    original = _compose("sese.023", _sample_elements("sese.023", SampleVariant.TYPICAL))
    assert 'Ccy="USD"' in original.document

    parsed = parse_message(original.xml)

    amount = next(item for item in parsed.elements if item.path.endswith("/SttlmAmt/Amt"))
    assert amount.value == "USD 25000.00"


# --------------------------------------------------------------------------------------
# Input shapes a tester can arrive with
# --------------------------------------------------------------------------------------


def test_a_bare_document_without_a_header_imports() -> None:
    original = _compose("sese.023", _sample_elements("sese.023", SampleVariant.MINIMAL))

    parsed = parse_message(original.document)

    assert parsed.app_hdr_present is False
    assert parsed.errors == []
    assert parsed.elements


def test_a_header_and_document_pasted_one_after_the_other_import() -> None:
    """Two sibling roots is not well-formed XML, but it is what downloading both gives."""
    original = _compose("sese.023", _sample_elements("sese.023", SampleVariant.TYPICAL))
    assert original.app_hdr is not None

    parsed = parse_message(f"{original.app_hdr}\n{original.document}")

    assert parsed.app_hdr_present is True
    assert parsed.errors == []
    assert parsed.envelope.sender is not None


def test_an_unknown_transport_wrapper_is_transparent() -> None:
    original = _compose("sese.023", _sample_elements("sese.023", SampleVariant.TYPICAL))
    wrapped = f"<SomeVendorEnvelope><Extra>ignored</Extra>{original.document}</SomeVendorEnvelope>"

    parsed = parse_message(wrapped)

    assert parsed.errors == []
    assert _compose("sese.023", parsed.elements).document == original.document


def test_the_xml_declaration_is_accepted() -> None:
    original = _compose("sese.023", _sample_elements("sese.023", SampleVariant.MINIMAL))

    parsed = parse_message(f'<?xml version="1.0" encoding="UTF-8"?>\n{original.document}')

    assert parsed.errors == []


# --------------------------------------------------------------------------------------
# The header
# --------------------------------------------------------------------------------------


def test_header_addresses_are_recovered_into_the_envelope() -> None:
    original = _compose("sese.023", _sample_elements("sese.023", SampleVariant.TYPICAL))

    parsed = parse_message(original.xml)

    configured = _profile().mx_envelope
    assert configured is not None
    assert parsed.envelope.sender == configured.from_bic
    assert parsed.envelope.receiver == configured.to_bic
    assert parsed.envelope.business_message_identifier is not None


def test_a_header_naming_a_different_message_is_reported() -> None:
    original = _compose("sese.023", _sample_elements("sese.023", SampleVariant.MINIMAL))
    tampered = original.xml.replace(
        "<MsgDefIdr>sese.023.001.11</MsgDefIdr>",
        "<MsgDefIdr>sese.025.001.12</MsgDefIdr>",
    )

    parsed = parse_message(tampered)

    assert "MX_IMPORT_APPHDR_MISMATCH" in {issue.rule_id for issue in parsed.errors}


def test_an_imported_signature_is_reported_and_not_reproduced() -> None:
    original = _compose("sese.023", _sample_elements("sese.023", SampleVariant.MINIMAL))
    signed = original.xml.replace("</AppHdr>", "  <Sgntr>SOMESIGNATURE</Sgntr>\n</AppHdr>")

    parsed = parse_message(signed)
    regenerated = _compose("sese.023", parsed.elements, envelope=parsed.envelope)

    assert "MX_IMPORT_SIGNATURE_DROPPED" in {issue.rule_id for issue in parsed.warnings}
    assert "Sgntr" not in (regenerated.app_hdr or "")


# --------------------------------------------------------------------------------------
# Nothing is silently dropped
# --------------------------------------------------------------------------------------


def test_an_element_outside_the_configured_subset_is_reported() -> None:
    original = _compose("sese.023", _sample_elements("sese.023", SampleVariant.MINIMAL))
    extended = original.document.replace(
        "<TxId>", "<NotInTheSubset>value</NotInTheSubset>\n    <TxId>"
    )

    parsed = parse_message(extended)

    issue = next(item for item in parsed.errors if item.rule_id == "MX_IMPORT_UNKNOWN_ELEMENT")
    assert "NotInTheSubset" in (issue.current_value or "")
    assert issue.suggestion is not None


def test_a_repeat_the_subset_does_not_allow_is_reported() -> None:
    original = _compose("sese.023", _sample_elements("sese.023", SampleVariant.MINIMAL))
    duplicated = original.document.replace(
        "<TxId>TESTREF001</TxId>", "<TxId>TESTREF001</TxId><TxId>TESTREF002</TxId>"
    )

    parsed = parse_message(duplicated)

    assert "MX_IMPORT_UNEXPECTED_REPEAT" in {issue.rule_id for issue in parsed.errors}


def test_an_empty_element_is_reported_rather_than_imported_as_blank() -> None:
    original = _compose("sese.023", _sample_elements("sese.023", SampleVariant.MINIMAL))
    emptied = original.document.replace("<TxId>TESTREF001</TxId>", "<TxId></TxId>")

    parsed = parse_message(emptied)

    assert "MX_IMPORT_EMPTY_ELEMENT" in {issue.rule_id for issue in parsed.errors}
    assert not any(item.path.endswith("/TxId") for item in parsed.elements)


def test_a_container_holding_text_is_reported() -> None:
    original = _compose("sese.023", _sample_elements("sese.023", SampleVariant.MINIMAL))
    corrupted = original.document.replace("<FinInstrmId>", "<FinInstrmId>stray text")

    parsed = parse_message(corrupted)

    assert "MX_IMPORT_TEXT_IN_CONTAINER" in {issue.rule_id for issue in parsed.errors}


def test_a_leaf_carrying_nested_elements_is_reported() -> None:
    original = _compose("sese.023", _sample_elements("sese.023", SampleVariant.MINIMAL))
    corrupted = original.document.replace(
        "<TxId>TESTREF001</TxId>", "<TxId><Deeper>TESTREF001</Deeper></TxId>"
    )

    parsed = parse_message(corrupted)

    assert "MX_IMPORT_UNEXPECTED_CHILDREN" in {issue.rule_id for issue in parsed.errors}


def test_out_of_order_children_are_read_but_flagged() -> None:
    """Regenerating fixes the order, so this is a warning — but a silent one would hide a
    document that no schema-checking receiver would have accepted."""
    parsed = parse_message(
        '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:sese.023.001.11">'
        "<SctiesSttlmTxInstr>"
        "<SttlmTpAndAddtlParams><SctiesMvmntTp>RECE</SctiesMvmntTp><Pmt>FREE</Pmt>"
        "</SttlmTpAndAddtlParams>"
        "<TxId>LATEREF001</TxId>"
        "</SctiesSttlmTxInstr></Document>"
    )

    assert "MX_IMPORT_ELEMENT_ORDER" in {issue.rule_id for issue in parsed.warnings}
    assert any(item.value == "LATEREF001" for item in parsed.elements)


# --------------------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("xml", "rule_id"),
    [
        ("   ", "MX_IMPORT_EMPTY"),
        ("this is not xml", "MX_IMPORT_NOT_WELL_FORMED"),
        ("<Document><Unclosed>", "MX_IMPORT_NOT_WELL_FORMED"),
        ("<Plain><Xml/></Plain>", "MX_IMPORT_NO_DOCUMENT"),
        (
            '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.10"><X>1</X></Document>',
            "MX_IMPORT_MESSAGE_NOT_CONFIGURED",
        ),
    ],
)
def test_unusable_input_is_refused_with_a_named_reason(xml: str, rule_id: str) -> None:
    with pytest.raises(MxImportError) as caught:
        parse_message(xml)

    assert caught.value.issue.rule_id == rule_id
    assert caught.value.issue.suggestion


def test_an_unconfigured_message_lists_what_is_supported() -> None:
    with pytest.raises(MxImportError) as caught:
        parse_message(
            '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.10">'
            "<X>1</X></Document>"
        )

    assert caught.value.issue.expected is not None
    for namespace in mx_registry.namespaces():
        assert namespace in caught.value.issue.expected


# --------------------------------------------------------------------------------------
# The endpoint
# --------------------------------------------------------------------------------------


def _generate_xml(client: TestClient, message_type: str) -> dict[str, object]:
    # Not every message offers every variant, so take whichever the catalogue advertises.
    sample = client.get(f"/api/v1/messages/{message_type}/samples?format=MX").json()[-1]
    response = client.post(
        "/api/v1/messages/generate",
        json={
            "format": "MX",
            "messageType": message_type,
            "elements": sample["elements"],
            "persist": False,
        },
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize("message_type", MX_TYPES)
def test_the_endpoint_round_trips_to_an_identical_document(
    client: TestClient, message_type: str
) -> None:
    generated = _generate_xml(client, message_type)

    response = client.post(
        "/api/v1/messages/import", json={"xml": generated["outputs"]["xml"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["importIssues"] == []
    assert body["result"]["valid"] is True
    assert body["result"]["outputs"]["document"] == generated["outputs"]["document"]


def test_imported_elements_are_accepted_by_generate_unchanged(client: TestClient) -> None:
    """The canonical form the importer returns is the canonical form the API takes.

    This is what closes the loop for a tester: import, edit a value, send it back.
    """
    generated = _generate_xml(client, "sese.023")
    imported = client.post(
        "/api/v1/messages/import", json={"xml": generated["outputs"]["xml"]}
    ).json()

    replayed = client.post(
        "/api/v1/messages/generate",
        json={
            "format": "MX",
            "messageType": imported["messageType"],
            "elements": imported["elements"],
            "envelope": imported["envelope"],
            "persist": False,
        },
    )

    assert replayed.status_code == 200
    assert replayed.json()["outputs"]["document"] == generated["outputs"]["document"]


def test_an_edited_value_regenerates(client: TestClient) -> None:
    generated = _generate_xml(client, "sese.023")
    imported = client.post(
        "/api/v1/messages/import", json={"xml": generated["outputs"]["xml"]}
    ).json()

    elements = [
        {**item, "value": "EDITEDREF99"} if item["path"].endswith("/TxId") else item
        for item in imported["elements"]
    ]
    replayed = client.post(
        "/api/v1/messages/generate",
        json={
            "format": "MX",
            "messageType": imported["messageType"],
            "elements": elements,
            "persist": False,
        },
    )

    assert replayed.status_code == 200
    assert "<TxId>EDITEDREF99</TxId>" in replayed.json()["outputs"]["document"]


def test_import_problems_reach_the_validation_the_ui_shows(client: TestClient) -> None:
    """Listing an import problem only in a side channel would let the message look clean."""
    generated = _generate_xml(client, "sese.023")
    tampered = generated["outputs"]["xml"].replace(
        "<TxId>", "<NotInTheSubset>x</NotInTheSubset><TxId>"
    )

    body = client.post("/api/v1/messages/import", json={"xml": tampered}).json()

    assert body["importIssues"]
    assert body["result"]["valid"] is False
    rule_ids = {issue["ruleId"] for issue in body["result"]["validation"]["errors"]}
    assert "MX_IMPORT_UNKNOWN_ELEMENT" in rule_ids
    assert "issue" in body["result"]["validation"]["summary"]


def test_import_keeps_nothing_by_default(client: TestClient) -> None:
    generated = _generate_xml(client, "sese.023")

    body = client.post(
        "/api/v1/messages/import", json={"xml": generated["outputs"]["xml"]}
    ).json()

    assert body["result"]["messageId"] is None


def test_import_refuses_an_unidentifiable_document(client: TestClient) -> None:
    response = client.post("/api/v1/messages/import", json={"xml": "<Nope/>"})

    assert response.status_code == 422
    assert response.json()["error"]["message"]


def test_import_rejects_an_oversized_paste(client: TestClient) -> None:
    response = client.post("/api/v1/messages/import", json={"xml": "<a/>" * 300_000})

    assert response.status_code == 422
