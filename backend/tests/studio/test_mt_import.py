"""MT import and the round-trip property.

The property under test is::

    Compose(Parse(Compose(values))) == Compose(values)

Comparing the recomposed *message* rather than the parsed value list is deliberate: two
value lists can differ harmlessly while denoting the same message, and the message is what
a tester actually receives.

Every negative case asserts that something was *reported*. An importer that silently drops
what it does not understand is worse than one that refuses, because the tester ships a
message they believe round-tripped.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.domain.enums import MessageType
from app.profiles.loader import profiles
from app.specifications.registry import specification_registry
from app.studio.models import FieldInput, GenerateRequest, MessageFormat, SampleVariant
from app.studio.mt.generator import mt_generator
from app.studio.mt.parser import MtImportError, parse_message
from app.studio.samples import available_variants, build_sample
from app.studio.service import studio_service

# Derived from the registry, so a message added as configuration is covered by the round
# trip without anyone remembering to extend this list.
MT_TYPES = [spec.message_type.value for spec in specification_registry.list()]
PROFILE = "BASE_DEMO_V1"
GOLDEN = sorted((Path(__file__).resolve().parents[1] / "golden" / "expected").glob("*.txt"))


def _profile():  # type: ignore[no-untyped-def]
    return profiles.get(PROFILE)


def _compose(message_type: str, fields: list[FieldInput], envelope=None):  # type: ignore[no-untyped-def]
    return mt_generator.build(message_type, _profile(), fields, envelope=envelope)


def _sample_fields(message_type: str, variant: SampleVariant) -> list[FieldInput]:
    return list(build_sample(MessageFormat.MT, message_type, variant).inputs)


# --------------------------------------------------------------------------------------
# The round trip
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("message_type", MT_TYPES)
@pytest.mark.parametrize("variant", list(SampleVariant))
def test_every_sample_round_trips_to_an_identical_message(
    message_type: str, variant: SampleVariant
) -> None:
    if variant not in available_variants(MessageFormat.MT, message_type):
        pytest.skip(f"{message_type} has no {variant.value} sample")
    original = _compose(message_type, _sample_fields(message_type, variant))

    parsed = parse_message(original.fin or original.block_4)
    regenerated = _compose(
        parsed.specification.message_type.value, parsed.fields, envelope=parsed.envelope
    )

    assert parsed.errors == []
    assert regenerated.block_4 == original.block_4
    assert regenerated.fin == original.fin


@pytest.mark.parametrize("fixture", GOLDEN, ids=lambda path: path.stem)
def test_every_golden_fixture_imports_and_recomposes(fixture: Path) -> None:
    """The golden files are the messages this repository has committed to producing.

    They also use the repository's own demonstration envelope rather than a FIN one, which
    is exactly what a tester pastes when they copy a message out of the samples screen.
    """
    parsed = parse_message(fixture.read_text(encoding="utf-8"))
    assert parsed.errors == []
    assert parsed.fields

    message_type = parsed.specification.message_type.value
    first = _compose(message_type, parsed.fields)
    again = parse_message(first.block_4, message_type=message_type)
    second = _compose(message_type, again.fields)

    assert second.block_4 == first.block_4


def test_a_pasted_text_block_needs_no_envelope() -> None:
    original = _compose("MT541", _sample_fields("MT541", SampleVariant.TYPICAL))

    parsed = parse_message(original.block_4, message_type="MT541")

    assert parsed.blocks == ["4"]
    assert parsed.errors == []
    assert _compose("MT541", parsed.fields).block_4 == original.block_4


def test_the_envelope_the_message_arrived_with_is_carried_over() -> None:
    original = _compose("MT541", _sample_fields("MT541", SampleVariant.TYPICAL))
    assert original.fin is not None

    parsed = parse_message(original.fin)

    assert parsed.envelope.sender
    assert parsed.envelope.receiver
    assert parsed.envelope.session_number
    assert parsed.envelope.sequence_number
    assert _compose("MT541", parsed.fields, envelope=parsed.envelope).fin == original.fin


def test_a_user_header_reference_survives() -> None:
    text = (
        "{1:F01DEMOGB2LAXXX0001000001}\n{2:I541DEMOUS33XXXXN}\n{3:{108:CASEREF01}}\n"
        "{4:\n:16R:GENL\n:20C::SEME//ABC\n:16S:GENL\n-}"
    )

    parsed = parse_message(text)

    assert parsed.envelope.message_user_reference == "CASEREF01"
    assert parsed.blocks == ["1", "2", "3", "4"]


def test_a_continuation_line_stays_part_of_its_field() -> None:
    text = (
        "{2:MT548}\n{4:\n:16R:GENL\n:20C::SEME//ABC\n:16S:GENL\n"
        ":16R:STAT\n:25D::SETT//PEND\n:70D::REAS//First line\nSecond line\n:16S:STAT\n-}"
    )

    parsed = parse_message(text)

    reason = [item for item in parsed.fields if (item.id or "").endswith("70D-REAS")]
    assert parsed.errors == []
    assert reason and reason[0].value == "First line\nSecond line"


def test_a_repeated_block_keeps_each_repeat_separate() -> None:
    """Without occurrence numbering every repeat collapses onto the first one's values,
    and the loss is invisible in the output."""
    fields = [
        FieldInput(id="MT537-A-20C-SEME", value="STATEMENT1"),
        FieldInput(id="MT537-D1a1-20C-PREF", occurrence=1, value="PENALTY001"),
        FieldInput(id="MT537-D1a1-20C-PREF", occurrence=2, value="PENALTY002"),
    ]
    original = _compose("MT537", fields)

    parsed = parse_message(original.block_4, message_type="MT537")

    references = sorted(
        (item.occurrence, item.value)
        for item in parsed.fields
        if item.id == "MT537-D1a1-20C-PREF"
    )
    assert references == [(1, "PENALTY001"), (2, "PENALTY002")]
    assert _compose("MT537", parsed.fields).block_4 == original.block_4


def test_a_repeated_block_inside_a_repeated_block_is_refused_not_reshaped() -> None:
    """The occurrence address has one index, so this nesting cannot be expressed. Reporting
    it is the point: values that come back in a different block are worse than values that
    do not come back."""
    text = (
        "{2:MT537}\n{4:\n:16R:GENL\n:20C::SEME//A\n:16S:GENL\n"
        ":16R:PENA\n:16R:PENACUR\n"
        ":16R:PENACOUNT\n:16R:PENDET\n:20C::PREF//P1\n:16S:PENDET\n:16S:PENACOUNT\n"
        ":16R:PENACOUNT\n:16R:PENDET\n:20C::PREF//P2\n:16S:PENDET\n:16S:PENACOUNT\n"
        ":16S:PENACUR\n:16S:PENA\n-}"
    )

    parsed = parse_message(text)

    assert [issue.rule_id for issue in parsed.errors] == [
        "MT_IMPORT_NESTED_REPEAT_UNSUPPORTED"
    ]
    assert "PENACOUNT" in parsed.errors[0].message


# --------------------------------------------------------------------------------------
# Identifying the message
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("message_type", MT_TYPES)
def test_the_application_header_identifies_the_message(message_type: str) -> None:
    original = _compose(message_type, _sample_fields(message_type, SampleVariant.MINIMAL))
    assert original.fin is not None

    assert parse_message(original.fin).specification.message_type.value == message_type


@pytest.mark.parametrize("message_type", MT_TYPES)
def test_the_demonstration_envelope_identifies_the_message(message_type: str) -> None:
    """`{1:DEMONSTRATION}{2:MT541}` is what this repository's own sample exporter writes,
    so it is what a tester pastes; refusing it would refuse our own output."""
    original = _compose(message_type, _sample_fields(message_type, SampleVariant.MINIMAL))
    text = f"{{1:DEMONSTRATION}}\n{{2:{message_type}}}\n{original.block_4}"

    parsed = parse_message(text)

    assert parsed.specification.message_type.value == message_type
    assert [issue.rule_id for issue in parsed.warnings] == ["MT_IMPORT_DEMONSTRATION_HEADER"]


def test_a_text_block_that_fits_only_one_message_is_identified_without_a_header() -> None:
    original = _compose("MT530", _sample_fields("MT530", SampleVariant.TYPICAL))

    parsed = parse_message(original.block_4)

    assert parsed.specification.message_type is MessageType.MT530


def test_a_text_block_that_fits_several_messages_is_refused_rather_than_guessed() -> None:
    original = _compose("MT541", _sample_fields("MT541", SampleVariant.MINIMAL))

    with pytest.raises(MtImportError) as refusal:
        parse_message(original.block_4)

    assert refusal.value.issue.rule_id == "MT_IMPORT_TYPE_AMBIGUOUS"
    assert "MT540" in (refusal.value.issue.expected or "")
    assert refusal.value.issue.suggestion


def test_a_header_that_contradicts_the_requested_type_is_refused() -> None:
    original = _compose("MT541", _sample_fields("MT541", SampleVariant.MINIMAL))
    assert original.fin is not None

    with pytest.raises(MtImportError) as refusal:
        parse_message(original.fin, message_type="MT540")

    assert refusal.value.issue.rule_id == "MT_IMPORT_TYPE_MISMATCH"


def test_a_message_this_repository_does_not_configure_says_so() -> None:
    with pytest.raises(MtImportError) as refusal:
        parse_message("{2:MT202}\n{4:\n:16R:GENL\n:16S:GENL\n-}")

    assert refusal.value.issue.rule_id == "MT_IMPORT_TYPE_NOT_CONFIGURED"
    assert "MT541" in (refusal.value.issue.expected or "")


def test_an_output_header_does_not_become_a_receiver_address() -> None:
    """A delivered message's header names the network, not a receiver. Reusing any of it
    would be inventing an address."""
    text = (
        "{1:F01DEMOGB2LAXXX0001000001}\n"
        "{2:O5411200260805DEMOUS33XXXX00010000012608051200N}\n"
        "{4:\n:16R:GENL\n:20C::SEME//ABC\n:16S:GENL\n-}"
    )

    parsed = parse_message(text)

    assert parsed.specification.message_type is MessageType.MT541
    assert parsed.envelope.receiver is None
    assert "MT_IMPORT_OUTPUT_HEADER" in [issue.rule_id for issue in parsed.warnings]


# --------------------------------------------------------------------------------------
# Nothing is silently dropped
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "rule_id"),
    [
        ("   ", "MT_IMPORT_EMPTY"),
        ("{2:MT541}\n{4:\n:16R:GENL\n:20C::SEME//A\n", "MT_IMPORT_TEXT_BLOCK_NOT_CLOSED"),
        ("{1:F01DEMOGB2LAXXX0001000001}\n{2:I541DEMOUS33XXXXN}", "MT_IMPORT_NO_TEXT_BLOCK"),
        ("nothing here that looks like a message", "MT_IMPORT_TYPE_UNKNOWN"),
    ],
)
def test_a_message_that_cannot_be_read_at_all_is_refused_by_name(
    text: str, rule_id: str
) -> None:
    with pytest.raises(MtImportError) as refusal:
        parse_message(text)

    assert refusal.value.issue.rule_id == rule_id
    assert refusal.value.issue.suggestion


def test_an_oversized_paste_is_refused() -> None:
    with pytest.raises(MtImportError) as refusal:
        parse_message("{2:MT541}\n{4:\n" + ":16R:GENL\n" * 200_000 + "-}")

    assert refusal.value.issue.rule_id == "MT_IMPORT_TOO_LARGE"


@pytest.mark.parametrize(
    ("body", "rule_id"),
    [
        (":16R:BOGUS\n:16S:BOGUS", "MT_IMPORT_UNKNOWN_SEQUENCE"),
        (":16R:GENL\n:16S:TRADDET", "MT_IMPORT_SEQUENCE_MISMATCHED_END"),
        (":16R:GENL\n:20C::SEME//A", "MT_IMPORT_SEQUENCE_NOT_CLOSED"),
        (":16S:GENL", "MT_IMPORT_SEQUENCE_NOT_OPENED"),
        (":20C::SEME//A", "MT_IMPORT_FIELD_OUTSIDE_SEQUENCE"),
        (":16R:GENL\n:99Z::ZZZZ//A\n:16S:GENL", "MT_IMPORT_UNKNOWN_FIELD"),
        (":16R:GENL\nplain text\n:16S:GENL", "MT_IMPORT_UNPARSABLE_LINE"),
        (":16R:GENL\n:20C::SEME//\n:16S:GENL", "MT_IMPORT_EMPTY_VALUE"),
        (":16R:GENL\n:20C::SEME//A\n:20C::SEME//B\n:16S:GENL", "MT_IMPORT_DUPLICATE_FIELD"),
    ],
)
def test_what_cannot_be_imported_is_reported_not_dropped(body: str, rule_id: str) -> None:
    parsed = parse_message(f"{{2:MT541}}\n{{4:\n{body}\n-}}")

    reported = [issue.rule_id for issue in parsed.errors]
    assert rule_id in reported
    named = next(issue for issue in parsed.errors if issue.rule_id == rule_id)
    assert named.suggestion
    assert named.message.endswith(".")


def test_a_trailer_is_read_and_deliberately_not_reproduced() -> None:
    """Authentication and checksum trailers are added by the interface and the network.
    The studio refuses to generate them, so it must say it dropped one."""
    text = (
        "{2:MT541}\n{4:\n:16R:GENL\n:20C::SEME//A\n:16S:GENL\n-}\n{5:{MAC:00000000}{CHK:123}}"
    )

    parsed = parse_message(text)

    assert "5" in parsed.blocks
    assert "MT_IMPORT_TRAILER_DROPPED" in [issue.rule_id for issue in parsed.warnings]


def test_a_user_header_field_the_studio_cannot_write_is_reported() -> None:
    text = "{2:MT541}\n{3:{108:REF}{119:STP}}\n{4:\n:16R:GENL\n:20C::SEME//A\n:16S:GENL\n-}"

    parsed = parse_message(text)

    dropped = next(
        issue
        for issue in parsed.warnings
        if issue.rule_id == "MT_IMPORT_USER_HEADER_FIELD_DROPPED"
    )
    assert "119" in dropped.message


def test_fields_written_out_of_specification_order_are_flagged_not_silently_reordered() -> None:
    text = "{2:MT541}\n{4:\n:16R:GENL\n:23G:NEWM\n:20C::SEME//A\n:16S:GENL\n-}"

    parsed = parse_message(text)

    assert "MT_IMPORT_FIELD_ORDER" in [issue.rule_id for issue in parsed.warnings]
    assert parsed.errors == []


def test_sequences_written_out_of_order_are_flagged() -> None:
    text = (
        "{2:MT541}\n{4:\n:16R:TRADDET\n:98A::TRAD//20260805\n:16S:TRADDET\n"
        ":16R:GENL\n:20C::SEME//A\n:16S:GENL\n-}"
    )

    parsed = parse_message(text)

    assert "MT_IMPORT_SEQUENCE_ORDER" in [issue.rule_id for issue in parsed.warnings]


def test_a_value_the_canonical_model_refuses_is_named_rather_than_crashing() -> None:
    text = "{2:MT541}\n{4:\n:16R:GENL\n:20C::SEME//{1:FAKEBLOCK}\n:16S:GENL\n-}"

    parsed = parse_message(text)

    rejected = next(
        issue for issue in parsed.errors if issue.rule_id == "MT_IMPORT_VALUE_REJECTED"
    )
    assert rejected.field == "Sender's Message Reference"


# --------------------------------------------------------------------------------------
# Over the API — the same values the JSON caller and the browser use
# --------------------------------------------------------------------------------------


def _generate(client: TestClient, message_type: str) -> dict:  # type: ignore[type-arg]
    samples = client.get(f"/api/v1/messages/{message_type}/samples?format=MT").json()
    return client.post(
        "/api/v1/messages/generate",
        json={
            "format": "MT",
            "messageType": message_type,
            "fields": samples[-1]["inputs"],
            "persist": False,
        },
    ).json()


@pytest.mark.parametrize("message_type", MT_TYPES)
def test_the_endpoint_round_trips_to_an_identical_message(
    client: TestClient, message_type: str
) -> None:
    generated = _generate(client, message_type)

    body = client.post(
        "/api/v1/messages/import", json={"text": generated["outputs"]["fin"]}
    ).json()

    assert body["format"] == "MT"
    assert body["messageType"] == message_type
    assert body["importIssues"] == []
    assert body["result"]["outputs"]["fin"] == generated["outputs"]["fin"]


def test_imported_fields_are_accepted_by_generate_unchanged(client: TestClient) -> None:
    """The whole point of a canonical import: what comes back out is what goes back in."""
    generated = _generate(client, "MT541")
    body = client.post(
        "/api/v1/messages/import", json={"text": generated["outputs"]["fin"]}
    ).json()

    again = client.post(
        "/api/v1/messages/generate",
        json={
            "format": "MT",
            "messageType": body["messageType"],
            "fields": body["fields"],
            "envelope": body["envelope"],
            "persist": False,
        },
    ).json()

    assert again["outputs"]["fin"] == generated["outputs"]["fin"]


def test_an_edited_value_regenerates(client: TestClient) -> None:
    generated = _generate(client, "MT541")
    body = client.post(
        "/api/v1/messages/import", json={"text": generated["outputs"]["fin"]}
    ).json()
    edited = [
        {**item, "value": "EDITEDREF001"} if item["id"].endswith("20C-SEME") else item
        for item in body["fields"]
    ]

    again = client.post(
        "/api/v1/messages/generate",
        json={
            "format": "MT",
            "messageType": "MT541",
            "fields": edited,
            "envelope": body["envelope"],
            "persist": False,
        },
    ).json()

    assert "EDITEDREF001" in again["outputs"]["fin"]
    assert again["valid"] is True


def test_import_problems_reach_the_validation_the_ui_shows(client: TestClient) -> None:
    text = "{2:MT541}\n{4:\n:16R:GENL\n:99Z::ZZZZ//A\n:16S:GENL\n-}"

    body = client.post("/api/v1/messages/import", json={"text": text}).json()

    assert body["importIssues"]
    reported = [issue["ruleId"] for issue in body["result"]["validation"]["errors"]]
    assert "MT_IMPORT_UNKNOWN_FIELD" in reported
    assert body["result"]["valid"] is False


def test_a_text_block_can_be_imported_by_naming_the_message(client: TestClient) -> None:
    generated = _generate(client, "MT541")

    body = client.post(
        "/api/v1/messages/import",
        json={"text": generated["outputs"]["block4"], "messageType": "MT541"},
    ).json()

    assert body["finBlocks"] == ["4"]
    assert body["elementCount"] > 0


def test_the_endpoint_refuses_text_that_is_not_a_message(client: TestClient) -> None:
    response = client.post("/api/v1/messages/import", json={"text": "hello"})

    assert response.status_code == 422
    assert "ISO 20022" in response.json()["error"]["message"]


def test_the_older_xml_field_still_works(client: TestClient) -> None:
    """`xml` was the field name when only MX could be imported. Callers written against it
    keep working; `text` is what the contract documents now."""
    generated = _generate(client, "MT541")

    body = client.post(
        "/api/v1/messages/import", json={"xml": generated["outputs"]["fin"]}
    ).json()

    assert body["messageType"] == "MT541"


def test_import_keeps_nothing_by_default(client: TestClient) -> None:
    generated = _generate(client, "MT541")

    body = client.post(
        "/api/v1/messages/import", json={"text": generated["outputs"]["fin"]}
    ).json()

    assert body["result"]["messageId"] is None


# --------------------------------------------------------------------------------------
# The generation defect import uncovered
# --------------------------------------------------------------------------------------


def test_a_repeated_sub_block_does_not_duplicate_its_parent() -> None:
    """Asking for two penalty details used to emit two whole PENA sequences, breaking
    PENA's own 1..1 cardinality: the occurrence index was carried up the parent chain, so
    every ancestor repeated too. A child repeats inside its parent, not beside it."""
    fields = [
        FieldInput(id="MT537-A-20C-SEME", value="STATEMENT1"),
        FieldInput(id="MT537-D1a1-20C-PREF", occurrence=1, value="PENALTY001"),
        FieldInput(id="MT537-D1a1-20C-PREF", occurrence=2, value="PENALTY002"),
    ]

    result = studio_service.generate(
        GenerateRequest(format=MessageFormat.MT, message_type="MT537", fields=fields)
    )

    assert result.outputs.block4 is not None
    assert result.outputs.block4.count(":16R:PENA\n") == 1
    assert result.outputs.block4.count(":16R:PENDET") == 2
    assert "MT_COMPOSITION_FINDING" not in [
        issue.rule_id for issue in result.validation.errors
    ]
