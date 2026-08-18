"""Comparing an imported message with the one regenerated from it.

The comparison exists to answer one question a tester cannot answer by eye: *these two
messages differ — should I care?* So the tests here are mostly about **attribution**, not
about whether `difflib` works. A diff that reports a Block 5 trailer as a problem, or that
labels an unexplained difference as harmless normalisation, is worse than no diff at all:
the first trains the tester to ignore it, and the second hides the one case it exists for.

Determinism is asserted too. A diff a tester is expected to trust has to be reproducible,
and no model may be involved in producing it.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.specifications.registry import specification_registry
from app.studio.diff import MAX_ATTRIBUTED_ISSUES, MAX_DIFF_LINES, canonical_xml
from app.studio.models import DiffKind, DiffReason, MessageFormat, SampleVariant
from app.studio.mx.registry import mx_registry
from app.studio.samples import build_sample

MT_TYPES = [spec.message_type for spec in specification_registry.list()]
MX_TYPES = [spec.message_type for spec in mx_registry.all_specs()]


def _generate(client: TestClient, format_: str, message_type: str) -> dict:  # type: ignore[type-arg]
    sample = build_sample(MessageFormat(format_), message_type, SampleVariant.TYPICAL)
    body = {"format": format_, "messageType": message_type, "persist": False}
    if format_ == "MT":
        body["fields"] = [item.model_dump(by_alias=True) for item in sample.inputs]
    else:
        body["elements"] = [item.model_dump(by_alias=True) for item in sample.elements]
    return client.post("/api/v1/messages/generate", json=body).json()


def _import(client: TestClient, text: str) -> dict:  # type: ignore[type-arg]
    response = client.post("/api/v1/messages/import", json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()


def _changes(diff: dict) -> list[dict]:  # type: ignore[type-arg]
    return [line for line in diff["lines"] if line["kind"] != DiffKind.UNCHANGED.value]


def _reasons(diff: dict) -> set[str]:  # type: ignore[type-arg]
    return {line["reason"] for line in _changes(diff)}


# --------------------------------------------------------------------------------------
# A faithful round trip shows nothing
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("message_type", MT_TYPES)
def test_an_unedited_mt_message_comes_back_identical(
    client: TestClient, message_type: str
) -> None:
    """The property the suite already asserts, shown to the tester rather than claimed."""
    generated = _generate(client, "MT", message_type)

    diff = _import(client, generated["outputs"]["fin"])["diff"]

    assert diff["summary"]["identical"] is True
    assert _changes(diff) == []
    assert diff["basis"] == "FIN_LINES"


@pytest.mark.parametrize("message_type", MX_TYPES)
def test_an_unedited_mx_message_comes_back_identical(
    client: TestClient, message_type: str
) -> None:
    generated = _generate(client, "MX", message_type)

    diff = _import(client, generated["outputs"]["xml"])["diff"]

    assert diff["summary"]["identical"] is True
    assert diff["basis"] == "CANONICAL_XML"


# --------------------------------------------------------------------------------------
# MX is compared on meaning, MT on lines
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "mangle"),
    [
        ("collapsed to one line", lambda xml: "".join(x.strip() for x in xml.splitlines())),
        ("re-indented", lambda xml: xml.replace("\n", "\n\t   ")),
        ("blank lines inserted", lambda xml: xml.replace("\n", "\n\n")),
        ("trailing whitespace", lambda xml: "\n".join(f"{x}   " for x in xml.splitlines())),
    ],
)
def test_formatting_alone_is_never_a_difference_for_mx(
    client: TestClient, label: str, mangle  # type: ignore[no-untyped-def]
) -> None:
    """`compare canonical XML meaning rather than formatting-only whitespace differences`.

    Layout is decided by the canonical form for both sides at once, so it cannot survive
    into the diff.
    """
    generated = _generate(client, "MX", "sese.023")

    diff = _import(client, mangle(generated["outputs"]["xml"]))["diff"]

    assert diff["summary"]["identical"] is True, f"{label} produced a difference"


def test_mt_keeps_its_line_structure(client: TestClient) -> None:
    """FIN line structure *is* the message, so nothing is normalised away before comparing."""
    generated = _generate(client, "MT", "MT541")
    fin = generated["outputs"]["fin"]

    diff = _import(client, fin)["diff"]

    rendered = [line["originalText"] for line in diff["lines"]]
    assert rendered == fin.strip().splitlines()
    assert any(line.startswith("{1:") for line in rendered if line)
    assert any(line.startswith(":16R:") for line in rendered if line)


def test_the_canonical_form_declares_a_namespace_only_where_it_changes() -> None:
    """Repeating xmlns on every element buries the value the reader is looking for."""
    lines = canonical_xml(
        '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:sese.023.001.11">'
        "<SctiesSttlmTxInstr><TxId>ABC</TxId></SctiesSttlmTxInstr></Document>"
    )

    texts = [item.text.strip() for item in lines]
    assert texts[0].startswith('<Document xmlns="urn:iso')
    assert "<TxId>ABC</TxId>" in texts
    assert sum("xmlns" in text for text in texts) == 1


def test_the_canonical_form_keeps_the_element_path() -> None:
    """The path is how a difference is later named in business language."""
    lines = canonical_xml(
        '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:sese.023.001.11">'
        "<SctiesSttlmTxInstr><TxId>ABC</TxId></SctiesSttlmTxInstr></Document>"
    )

    paths = {item.path for item in lines}
    assert "/Document/SctiesSttlmTxInstr/TxId" in paths


def test_unparseable_xml_still_produces_a_comparison() -> None:
    """An empty panel tells the tester nothing; the raw lines at least tell them something."""
    lines = canonical_xml("<Document><Unclosed>")

    assert lines
    assert all(item.path == "" for item in lines)


# --------------------------------------------------------------------------------------
# Why the two messages differ
# --------------------------------------------------------------------------------------


def test_a_value_you_changed_is_attributed_to_you(client: TestClient) -> None:
    generated = _generate(client, "MT", "MT541")
    fin = generated["outputs"]["fin"]
    imported = _import(client, fin)
    edited = [
        {**item, "value": "EDITEDREF01"} if item["id"].endswith("20C-SEME") else item
        for item in imported["fields"]
    ]

    body = client.post(
        "/api/v1/messages/diff",
        json={
            "format": "MT",
            "messageType": "MT541",
            "original": fin,
            "fields": edited,
            "envelope": imported["envelope"],
        },
    ).json()

    changes = _changes(body["diff"])
    assert len(changes) == 1
    assert changes[0]["kind"] == DiffKind.CHANGED.value
    assert changes[0]["reason"] == DiffReason.USER_EDIT.value
    # Named in business language, not as MT541-A-20C-SEME.
    assert changes[0]["field"] == "Sender's Message Reference"
    assert "TESTREF001" in changes[0]["originalText"]
    assert "EDITEDREF01" in changes[0]["regeneratedText"]


def test_an_mx_value_you_changed_names_its_business_field(client: TestClient) -> None:
    generated = _generate(client, "MX", "sese.023")
    xml = generated["outputs"]["xml"]
    imported = _import(client, xml)
    edited = [
        {**item, "value": "EDITEDTX0001"} if item["path"].endswith("/TxId") else item
        for item in imported["elements"]
    ]

    body = client.post(
        "/api/v1/messages/diff",
        json={
            "format": "MX",
            "messageType": "sese.023",
            "original": xml,
            "elements": edited,
            "envelope": imported["envelope"],
        },
    ).json()

    changes = _changes(body["diff"])
    assert [item["reason"] for item in changes] == [DiffReason.USER_EDIT.value]
    assert changes[0]["field"] == "Transaction Identification"
    assert changes[0]["location"] == "/Document/SctiesSttlmTxInstr/TxId"


def test_fields_written_back_in_specification_order_are_normalisation(
    client: TestClient,
) -> None:
    generated = _generate(client, "MT", "MT541")
    fin = generated["outputs"]["fin"]
    # Swap the first two field lines of the first sequence, whatever they happen to be, so
    # the fixture keeps working when the sample changes.
    lines = fin.splitlines()
    first = next(
        index
        for index, line in enumerate(lines)
        if line.startswith(":") and not line.startswith(":16")
    )
    lines[first], lines[first + 1] = lines[first + 1], lines[first]
    swapped = "\n".join(lines)
    assert swapped != fin, "the fixture must actually be reordered"

    diff = _import(client, swapped)["diff"]

    assert _reasons(diff) == {DiffReason.NORMALISATION.value}
    assert diff["summary"]["unexplained"] == 0
    assert diff["summary"]["dropped"] == 0


def test_content_outside_the_configured_subset_is_reported_as_dropped(
    client: TestClient,
) -> None:
    generated = _generate(client, "MT", "MT541")
    tampered = generated["outputs"]["fin"].replace(
        ":23G:NEWM", ":23G:NEWM\n:99Z::ZZZZ//SOMETHING"
    )

    diff = _import(client, tampered)["diff"]

    dropped = [
        line for line in _changes(diff) if line["reason"] == DiffReason.IMPORT_DROPPED.value
    ]
    assert len(dropped) == 1
    assert "99Z" in dropped[0]["originalText"]
    assert diff["summary"]["dropped"] == 1
    assert diff["summary"]["unexplained"] == 0


def test_an_mx_element_outside_the_subset_is_reported_as_dropped(
    client: TestClient,
) -> None:
    generated = _generate(client, "MX", "sese.023")
    tampered = generated["outputs"]["xml"].replace(
        "<TxId>", "<NotInTheSubset>x</NotInTheSubset><TxId>"
    )

    diff = _import(client, tampered)["diff"]

    assert DiffReason.IMPORT_DROPPED.value in _reasons(diff)
    assert diff["summary"]["dropped"] >= 1


# --------------------------------------------------------------------------------------
# Interface and network values are never an application error
# --------------------------------------------------------------------------------------


def test_a_missing_trailer_is_expected_and_never_counted_as_a_problem(
    client: TestClient,
) -> None:
    """MAC and CHK are added by the messaging interface and the network. The studio refuses
    to invent them, so their absence is the correct outcome — not a finding."""
    generated = _generate(client, "MT", "MT541")
    with_trailer = generated["outputs"]["fin"] + "\n{5:{MAC:00000000}{CHK:123456789ABC}}"

    diff = _import(client, with_trailer)["diff"]

    changes = _changes(diff)
    assert [item["reason"] for item in changes] == [DiffReason.NOT_REPRODUCED.value]
    assert diff["summary"]["unexplained"] == 0
    assert diff["summary"]["dropped"] == 0
    assert diff["summary"]["expected"] == 1


def test_a_user_header_field_the_studio_cannot_write_is_expected_not_dropped(
    client: TestClient,
) -> None:
    generated = _generate(client, "MT", "MT541")
    with_header = generated["outputs"]["fin"].replace(
        "{4:", "{3:{108:MYREF}{119:STP}}\n{4:", 1
    )

    diff = _import(client, with_header)["diff"]

    assert _reasons(diff) == {DiffReason.NOT_REPRODUCED.value}
    assert diff["summary"]["dropped"] == 0


def test_an_mx_signature_is_expected_not_dropped(client: TestClient) -> None:
    generated = _generate(client, "MX", "sese.023")
    signed = generated["outputs"]["xml"].replace(
        "</Document>", "<Sgntr>signature</Sgntr></Document>"
    )

    diff = _import(client, signed)["diff"]

    assert DiffReason.NOT_REPRODUCED.value in _reasons(diff)
    assert diff["summary"]["dropped"] == 0
    assert diff["summary"]["unexplained"] == 0


def test_every_difference_carries_a_reason_and_an_explanation(client: TestClient) -> None:
    """An unlabelled difference makes the tester guess, which is the thing being replaced."""
    generated = _generate(client, "MT", "MT541")
    messy = (
        generated["outputs"]["fin"].replace(":23G:NEWM", ":23G:NEWM\n:99Z::ZZZZ//X")
        + "\n{5:{CHK:123456789ABC}}"
    )

    diff = _import(client, messy)["diff"]

    for line in _changes(diff):
        assert line["reason"], line
        assert line["explanation"], line
    assert diff["notes"]
    assert len(diff["notes"]) == len({line["reason"] for line in _changes(diff)})


# --------------------------------------------------------------------------------------
# Comparing like with like
# --------------------------------------------------------------------------------------


def test_a_pasted_text_block_is_not_told_it_lost_its_envelope(client: TestClient) -> None:
    """Somebody who pasted Block 4 has not removed Blocks 1 and 2, and saying so would bury
    the real differences under the wrapper."""
    generated = _generate(client, "MT", "MT541")
    block4 = generated["outputs"]["block4"]

    body = client.post(
        "/api/v1/messages/import", json={"text": block4, "messageType": "MT541"}
    ).json()

    assert body["diff"]["summary"]["identical"] is True
    assert body["diff"]["compared"] == "the text block"


def test_a_pasted_document_is_not_told_it_lost_its_header(client: TestClient) -> None:
    generated = _generate(client, "MX", "sese.023")

    body = _import(client, generated["outputs"]["document"])

    assert body["diff"]["summary"]["identical"] is True
    assert "without its business application header" in body["diff"]["compared"]


# --------------------------------------------------------------------------------------
# Bounded work
# --------------------------------------------------------------------------------------


def test_a_huge_paste_is_answered_quickly_instead_of_compared_line_by_line(
    client: TestClient,
) -> None:
    """Attribution costs lines x reported issues, so an unbounded comparison is a way to
    spend the server's time: a 1 MB paste of unmatched lines took over two minutes. The
    verdict a tester actually needs — are these the same message? — is still answered."""
    body = "\n".join(f":20C::SEME//REF{index:09d}" for index in range(35_000))
    huge = "{2:MT541}\n{4:\n:16R:GENL\n" + body + "\n:16S:GENL\n-}"

    started = time.perf_counter()
    diff = _import(client, huge)["diff"]
    elapsed = time.perf_counter() - started

    assert elapsed < 10, f"took {elapsed:.1f}s"
    assert diff["comparable"] is False
    assert diff["lines"] == []
    assert "too many to compare line by line" in diff["notComparedReason"]
    # Still answers the only question that matters at this size.
    assert diff["summary"]["identical"] is False


def test_a_message_with_hundreds_of_import_problems_is_not_compared_line_by_line(
    client: TestClient,
) -> None:
    """A message this broken is read from its issue list, not from chips on every line."""
    body = "\n".join(
        f":99Z::ZZZ{index % 10}//X{index}"
        for index in range(MAX_ATTRIBUTED_ISSUES + 50)
    )
    broken = "{2:MT541}\n{4:\n:16R:GENL\n" + body + "\n:16S:GENL\n-}"

    diff = _import(client, broken)["diff"]

    assert diff["comparable"] is False
    assert "could not be imported" in diff["notComparedReason"]


def test_the_largest_message_the_studio_can_produce_is_still_compared_in_full(
    client: TestClient,
) -> None:
    """The bound must sit above anything the studio itself generates, or a legitimate
    message would stop being comparable. FieldInput.occurrence caps at 100, so this is it."""
    fields = [{"id": "MT537-A-20C-SEME", "value": "S1"}] + [
        {"id": "MT537-D1a1-20C-PREF", "occurrence": index, "value": f"PEN{index:05d}"}
        for index in range(1, 101)
    ]
    generated = client.post(
        "/api/v1/messages/generate",
        json={"format": "MT", "messageType": "MT537", "fields": fields, "persist": False},
    ).json()

    diff = _import(client, generated["outputs"]["fin"])["diff"]

    assert diff["comparable"] is True
    assert diff["summary"]["identical"] is True
    assert len(diff["lines"]) < MAX_DIFF_LINES


# --------------------------------------------------------------------------------------
# The contract
# --------------------------------------------------------------------------------------


def test_the_diff_is_deterministic(client: TestClient) -> None:
    """No model is involved, and none could be: a tester has to be able to re-run this."""
    generated = _generate(client, "MT", "MT541")
    fin = generated["outputs"]["fin"]

    first = _import(client, fin)["diff"]
    second = _import(client, fin)["diff"]

    assert first == second


def test_diffing_does_not_keep_the_message(client: TestClient) -> None:
    generated = _generate(client, "MT", "MT541")
    fin = generated["outputs"]["fin"]

    body = client.post(
        "/api/v1/messages/diff",
        json={"format": "MT", "messageType": "MT541", "original": fin, "fields": []},
    ).json()

    assert body["result"]["messageId"] is None


def test_comparing_a_message_against_the_wrong_format_is_refused(
    client: TestClient,
) -> None:
    generated = _generate(client, "MX", "sese.023")

    response = client.post(
        "/api/v1/messages/diff",
        json={
            "format": "MT",
            "messageType": "MT541",
            "original": generated["outputs"]["xml"],
            "fields": [],
        },
    )

    assert response.status_code == 422
    assert "MX" in response.json()["error"]["message"]


def test_the_diff_endpoint_regenerates_through_the_ordinary_path(
    client: TestClient,
) -> None:
    """Not a lookalike of `generate` — the same call, so the two cannot drift."""
    generated = _generate(client, "MT", "MT541")
    fin = generated["outputs"]["fin"]
    imported = _import(client, fin)

    body = client.post(
        "/api/v1/messages/diff",
        json={
            "format": "MT",
            "messageType": "MT541",
            "original": fin,
            "fields": imported["fields"],
            "envelope": imported["envelope"],
        },
    ).json()

    assert body["result"]["outputs"]["fin"] == fin
    assert body["result"]["checksum"] == generated["checksum"]


def test_import_problems_reach_the_diff_and_the_validation(client: TestClient) -> None:
    generated = _generate(client, "MT", "MT541")
    tampered = generated["outputs"]["fin"].replace(
        ":23G:NEWM", ":23G:NEWM\n:99Z::ZZZZ//X"
    )

    body = client.post(
        "/api/v1/messages/diff",
        json={
            "format": "MT",
            "messageType": "MT541",
            "original": tampered,
            "fields": _import(client, tampered)["fields"],
        },
    ).json()

    assert body["importIssues"]
    assert "MT_IMPORT_UNKNOWN_FIELD" in [
        issue["ruleId"] for issue in body["result"]["validation"]["errors"]
    ]
    assert body["diff"]["summary"]["dropped"] >= 1
