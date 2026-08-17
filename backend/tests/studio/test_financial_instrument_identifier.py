"""Field 35B across every path a value can arrive by.

The literal ``ISIN`` has exactly one owner — the composer — so the same canonical business
value must produce the same field whether it came from the browser, the JSON API, a
spreadsheet or an imported message, and must never be doubled or lost.
"""

from __future__ import annotations

import pytest

from app.domain.identifiers import synthetic_isin
from app.studio.excel import MT_HEADERS, build_template, parse_workbook
from app.studio.models import (
    FieldInput,
    GenerateRequest,
    InputKind,
    MessageFormat,
    SampleVariant,
)
from app.studio.mt.parser import parse_message
from app.studio.samples import build_sample
from app.studio.service import studio_service
from tests.studio.test_excel_api import workbook_bytes

VALID = synthetic_isin("XS000000000")


def generate_with_isin(value: str):  # type: ignore[no-untyped-def]
    sample = build_sample(MessageFormat.MT, "MT541", SampleVariant.TYPICAL)
    fields = [
        item.model_copy(update={"value": value}) if item.tag == "35B" else item
        for item in sample.inputs
    ]
    return studio_service.generate(
        GenerateRequest(
            format=MessageFormat.MT, message_type="MT541", fields=fields, persist=False
        )
    )


def issue_ids(result) -> set[str]:  # type: ignore[no-untyped-def]
    return {item.rule_id for item in result.validation.errors}


# -- what a caller supplies --------------------------------------------------------------


def test_the_identifier_alone_is_what_a_caller_supplies() -> None:
    result = generate_with_isin(VALID)

    assert result.valid, [item.message for item in result.validation.errors]
    assert f":35B:ISIN {VALID}" in (result.outputs.block4 or "")


@pytest.mark.parametrize(
    "entered",
    [VALID, f"ISIN {VALID}", VALID.lower(), f"  isin {VALID.lower()}  "],
)
def test_every_way_a_tester_might_type_it_produces_one_field(entered: str) -> None:
    """A pasted prefix is normalised, never doubled. No path yields ``ISIN ISIN``."""
    result = generate_with_isin(entered)

    block4 = result.outputs.block4 or ""
    assert result.valid, [item.message for item in result.validation.errors]
    assert block4.count("ISIN") == 1
    assert f":35B:ISIN {VALID}" in block4


def test_the_specification_says_who_writes_the_literal() -> None:
    from app.studio.catalogue import message_spec

    field = next(
        item for item in message_spec(MessageFormat.MT, "MT541").fields if item.tag == "35B"
    )

    assert field.input_kind is InputKind.IDENTIFIER
    assert field.literal_prefix == "ISIN "
    assert field.user_enters_literal_prefix is False
    assert field.identifier_types == ["ISIN"]
    assert field.max_length == 12


def test_the_example_a_tester_is_shown_is_the_value_the_platform_accepts() -> None:
    """The two used to contradict each other, which is what the reported defect was."""
    from app.studio.catalogue import message_spec

    field = next(
        item for item in message_spec(MessageFormat.MT, "MT541").fields if item.tag == "35B"
    )
    shown = field.examples[0].value

    assert generate_with_isin(shown).valid


# -- what is refused, and why ------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "rule_id"),
    [
        ("XS000000000", "MT_ISIN_LENGTH"),
        ("XS00000000099", "MT_ISIN_LENGTH"),
        ("1S0000000009", "MT_ISIN_PREFIX"),
        ("XS0000-000009"[:12], "MT_ISIN_CHARACTER"),
        # The reported value. Rejected for the specific reason, not a generic one.
        ("US9897778ABC", "MT_ISIN_CHECK_DIGIT_NOT_NUMERIC"),
        # Well shaped, wrong check digit — a different claim, in a different layer.
        ("XS0000000001", "MT_ISIN_CHECK_DIGIT_INVALID"),
    ],
)
def test_each_defect_is_reported_under_its_own_rule(value: str, rule_id: str) -> None:
    result = generate_with_isin(value)

    assert not result.valid
    assert rule_id in issue_ids(result)


def test_the_reported_message_now_fails_for_the_right_reason() -> None:
    result = generate_with_isin("US9897778ABC")

    issue = next(
        item
        for item in result.validation.errors
        if item.rule_id == "MT_ISIN_CHECK_DIGIT_NOT_NUMERIC"
    )
    assert issue.message == "The final ISIN character must be a numeric check digit."
    # Entered, expected, example and how to fix are all present.
    assert issue.current_value == "US9897778ABC"
    assert issue.expected
    assert issue.suggestion and "XS0000000009" in issue.suggestion


def test_a_tester_is_told_not_to_type_the_keyword() -> None:
    issue = next(
        item
        for item in generate_with_isin("XS000000000").validation.errors
        if item.rule_id == "MT_ISIN_LENGTH"
    )

    assert "You do not need to type" in (issue.suggestion or "")


def test_format_and_check_digit_are_reported_in_different_layers() -> None:
    """Kept honest: the FIN network checks the field format, not the ISO 6166 arithmetic."""
    shape = next(
        item
        for item in generate_with_isin("US9897778ABC").validation.errors
        if item.rule_id.startswith("MT_ISIN")
    )
    checksum = next(
        item
        for item in generate_with_isin("XS0000000001").validation.errors
        if item.rule_id.startswith("MT_ISIN")
    )

    assert shape.layer.value == "FORMAT"
    assert checksum.layer.value == "CLIENT_PROFILE"
    assert "not a SWIFT field-format rule" in (checksum.suggestion or "")


def test_the_check_digit_error_names_the_digit_it_expected() -> None:
    issue = next(
        item
        for item in generate_with_isin("XS0000000001").validation.errors
        if item.rule_id == "MT_ISIN_CHECK_DIGIT_INVALID"
    )

    assert "XS0000000009" in (issue.suggestion or "")


# -- every path agrees --------------------------------------------------------------------


def test_import_returns_the_canonical_value_and_regeneration_writes_one_literal() -> None:
    composed = generate_with_isin(VALID).outputs.fin or ""

    imported = parse_message(composed)
    value = next(item.value for item in imported.fields if item.id and "35B" in item.id)

    assert value == VALID

    regenerated = studio_service.generate(
        GenerateRequest(
            format=MessageFormat.MT,
            message_type="MT541",
            fields=list(imported.fields),
            persist=False,
        )
    )
    block4 = regenerated.outputs.block4 or ""
    assert block4.count("ISIN") == 1
    assert "ISIN ISIN" not in block4
    assert f":35B:ISIN {VALID}" in block4


def test_a_message_pasted_with_the_literal_round_trips_byte_for_byte() -> None:
    original = generate_with_isin(VALID).outputs.block4 or ""

    # A bare text block fits MT540..MT543, so it is named — the documented behaviour when
    # the message does not identify itself.
    parsed = parse_message(original, message_type="MT541")
    regenerated = studio_service.generate(
        GenerateRequest(
            format=MessageFormat.MT,
            message_type="MT541",
            fields=list(parsed.fields),
            persist=False,
        )
    )

    assert regenerated.outputs.block4 == original


def test_the_excel_template_carries_the_canonical_value_not_the_rendered_one() -> None:
    parsed = parse_workbook(build_template(MessageFormat.MT), format_=MessageFormat.MT)
    scenario = next(item for item in parsed.scenarios if item.message_type == "MT541")
    value = next(item.value for item in scenario.fields if item.tag == "35B")

    assert value == VALID
    assert "ISIN" not in value


def test_a_legacy_spreadsheet_that_still_carries_the_prefix_keeps_working() -> None:
    """Backward compatibility, stated as a test rather than as an intention."""
    sample = build_sample(MessageFormat.MT, "MT541", SampleVariant.TYPICAL)
    rows = [
        [
            "TC1",
            "MT541",
            "BASE_DEMO_V1",
            item.sequence,
            item.occurrence,
            item.tag,
            item.qualifier,
            item.option,
            f"ISIN {VALID}" if item.tag == "35B" else item.value,
        ]
        for item in sample.inputs
    ]

    parsed = parse_workbook(workbook_bytes(MT_HEADERS, rows))
    result = studio_service.generate(
        GenerateRequest(
            format=MessageFormat.MT,
            message_type="MT541",
            fields=parsed.scenarios[0].fields,
            persist=False,
        )
    )

    assert result.valid, [item.message for item in result.validation.errors]
    assert (result.outputs.block4 or "").count("ISIN") == 1


def test_json_and_excel_produce_byte_identical_block_four() -> None:
    sample = build_sample(MessageFormat.MT, "MT541", SampleVariant.TYPICAL)
    from_json = studio_service.generate(
        GenerateRequest(
            format=MessageFormat.MT,
            message_type="MT541",
            fields=list(sample.inputs),
            persist=False,
        )
    )
    parsed = parse_workbook(build_template(MessageFormat.MT), format_=MessageFormat.MT)
    scenario = next(item for item in parsed.scenarios if item.message_type == "MT541")
    from_excel = studio_service.generate(
        GenerateRequest(
            format=MessageFormat.MT,
            message_type="MT541",
            fields=scenario.fields,
            persist=False,
        )
    )

    assert from_excel.outputs.block4 == from_json.outputs.block4


def test_the_api_still_rejects_an_invalid_identifier_posted_directly() -> None:
    """Client-side help is usability only. The server decides."""
    result = studio_service.generate(
        GenerateRequest(
            format=MessageFormat.MT,
            message_type="MT541",
            fields=[FieldInput(sequence="TRADDET", tag="35B", value="NOTANISIN123")],
            persist=False,
        )
    )

    assert not result.valid
    assert any(item.rule_id.startswith("MT_ISIN") for item in result.validation.errors)


def test_every_sample_of_every_message_carries_a_checksum_valid_identifier() -> None:
    from app.domain.enums import MessageType
    from app.domain.identifiers import validate_isin

    for message_type in MessageType:
        for variant in SampleVariant:
            sample = build_sample(MessageFormat.MT, message_type.value, variant)
            for item in sample.inputs:
                if item.tag == "35B":
                    verdict = validate_isin(item.value)
                    assert verdict.format_valid, (message_type, item.value)
                    assert verdict.check_digit_valid, (message_type, item.value)
