"""Tag-level MT generation: addressing, validation, output modes and repeated sequences."""

from __future__ import annotations

import pytest

from app.studio.models import (
    FieldInput,
    GenerateRequest,
    MessageFormat,
    OutputMode,
    SampleVariant,
    ValidationLayer,
)
from app.studio.samples import build_sample
from app.studio.service import studio_service


def generate(message_type: str, fields: list[FieldInput], **kwargs: object):  # type: ignore[no-untyped-def]
    return studio_service.generate(
        GenerateRequest(
            format=MessageFormat.MT,
            message_type=message_type,
            fields=fields,
            persist=False,
            **kwargs,  # type: ignore[arg-type]
        )
    )


@pytest.fixture
def mt541_fields() -> list[FieldInput]:
    return list(build_sample(MessageFormat.MT, "MT541", SampleVariant.TYPICAL).inputs)


def replace(fields: list[FieldInput], qualifier: str, value: str) -> list[FieldInput]:
    return [
        item.model_copy(update={"value": value}) if item.qualifier == qualifier else item
        for item in fields
    ]


def drop(fields: list[FieldInput], qualifier: str) -> list[FieldInput]:
    return [item for item in fields if item.qualifier != qualifier]


# -- addressing ------------------------------------------------------------------------


def test_fields_can_be_addressed_by_row_id(mt541_fields: list[FieldInput]) -> None:
    by_id = [FieldInput(id=item.id, value=item.value) for item in mt541_fields]

    result = generate("MT541", by_id)

    assert result.valid, [item.message for item in result.validation.errors]


def test_fields_can_be_addressed_by_sequence_tag_and_qualifier() -> None:
    result = generate(
        "MT548",
        [
            FieldInput(sequence="GENL", tag="20C", qualifier="SEME", value="STATUS0001"),
            FieldInput(sequence="GENL", tag="23G", value="INST"),
            FieldInput(sequence="LINK", tag="20C", qualifier="RELA", value="TESTREF001"),
            FieldInput(sequence="LINK", tag="13A", qualifier="LINK", value="541"),
            FieldInput(sequence="STAT", tag="25D", qualifier="SETT", value="PEND"),
            FieldInput(sequence="STAT", tag="24B", qualifier="PEND", value="AWMO"),
        ],
    )

    assert ":20C::SEME//STATUS0001" in (result.outputs.block4 or "")


def test_sequence_may_be_given_as_a_path_or_a_code(mt541_fields: list[FieldInput]) -> None:
    by_path = [
        item.model_copy(update={"sequence": {"GENL": "A", "TRADDET": "B", "FIAC": "C",
                                             "SETDET": "E"}.get(item.sequence or "")})
        for item in mt541_fields
    ]

    assert generate("MT541", by_path).valid


def test_unknown_tag_names_the_field_and_suggests_a_next_step(
    mt541_fields: list[FieldInput],
) -> None:
    fields = [*mt541_fields, FieldInput(sequence="GENL", tag="99Z", value="X")]

    result = generate("MT541", fields)

    issue = next(item for item in result.validation.errors if item.rule_id == "MT_UNKNOWN_FIELD")
    assert "99Z" in issue.message
    assert issue.suggestion


def test_unknown_sequence_lists_the_valid_ones(mt541_fields: list[FieldInput]) -> None:
    fields = [*mt541_fields, FieldInput(sequence="NOPE", tag="20C", qualifier="SEME", value="X")]

    result = generate("MT541", fields)

    issue = next(
        item for item in result.validation.errors if item.rule_id == "MT_UNKNOWN_SEQUENCE"
    )
    assert "GENL" in (issue.expected or "")


def test_ambiguous_tag_without_a_sequence_is_reported() -> None:
    """A tag that appears in two sequences of one message cannot be addressed by tag alone.

    The message and tag are derived from the registry rather than named, so this keeps
    testing the behaviour rather than a particular configuration. It used to use MT541's
    22F/SETR, which appeared in both Trade Details and Settlement Details — an ambiguity
    that only existed because the field was configured twice, and one of the two was not a
    settlement transaction type at all.
    """
    from collections import Counter

    from app.specifications.registry import specification_registry

    ambiguous = next(
        (spec.message_type, tag, qualifier)
        for spec in specification_registry.list()
        for (tag, qualifier), count in Counter(
            (item.tag, item.qualifier) for item in spec.fields
        ).items()
        if count > 1
    )
    message_type, tag, qualifier = ambiguous

    result = generate(message_type, [FieldInput(tag=tag, qualifier=qualifier, value="TRAD")])

    assert any(item.rule_id == "MT_AMBIGUOUS_FIELD" for item in result.validation.errors)


def test_duplicate_field_is_reported(mt541_fields: list[FieldInput]) -> None:
    fields = [*mt541_fields, mt541_fields[0]]

    result = generate("MT541", fields)

    assert any(item.rule_id == "MT_DUPLICATE_FIELD" for item in result.validation.errors)


def test_wrong_option_is_reported(mt541_fields: list[FieldInput]) -> None:
    fields = [
        item.model_copy(update={"option": "Z"}) if item.tag == "20C" else item
        for item in mt541_fields
    ]

    result = generate("MT541", fields)

    issue = next(item for item in result.validation.errors if item.rule_id == "MT_OPTION_MISMATCH")
    assert issue.expected == "C"


# -- validation ------------------------------------------------------------------------


def test_missing_mandatory_field_names_the_business_field(
    mt541_fields: list[FieldInput],
) -> None:
    result = generate("MT541", drop(mt541_fields, "SETT"))

    issue = next(
        item
        for item in result.validation.errors
        if item.rule_id == "MT_MANDATORY_FIELD_MISSING"
    )
    assert issue.field
    assert not issue.field.startswith(":")


def test_bad_format_is_reported_with_an_example(mt541_fields: list[FieldInput]) -> None:
    result = generate("MT541", replace(mt541_fields, "TRAD", "14-08-2026"))

    issue = next(item for item in result.validation.errors if item.rule_id == "MT_FORMAT_INVALID")
    assert issue.expected
    assert issue.suggestion


def test_settlement_before_trade_is_reported(mt541_fields: list[FieldInput]) -> None:
    result = generate("MT541", replace(mt541_fields, "SETT", "20260101"))

    assert any(
        item.rule_id == "SETTLEMENT_DATE_BEFORE_TRADE_DATE"
        for item in result.validation.errors
    )


def test_cancellation_requires_a_previous_reference(mt541_fields: list[FieldInput]) -> None:
    fields = [
        item.model_copy(update={"value": "CANC"}) if item.tag == "23G" else item
        for item in mt541_fields
    ]

    result = generate("MT541", fields)

    assert any(
        item.rule_id == "CANCELLATION_REQUIRES_PREVIOUS_REFERENCE"
        for item in result.validation.errors
    )


def test_currency_outside_the_profile_is_rejected(mt541_fields: list[FieldInput]) -> None:
    result = generate("MT541", replace(mt541_fields, "SETT", "JPY25000,00"))

    assert any(
        item.rule_id == "PROFILE_CURRENCY_NOT_ALLOWED" for item in result.validation.errors
    )


def test_profile_reference_length_is_enforced(mt541_fields: list[FieldInput]) -> None:
    fields = replace(mt541_fields, "SEME", "REFERENCE12345")

    permissive = generate("MT541", fields)
    strict = generate("MT541", fields, profile_id="BFS_CLIENT_DEMO_V1")

    assert permissive.valid
    assert any(
        item.rule_id == "PROFILE_SENDER_REFERENCE_TOO_LONG"
        for item in strict.validation.errors
    )


def test_validation_summary_reads_as_plain_english(mt541_fields: list[FieldInput]) -> None:
    good = generate("MT541", mt541_fields)
    one_missing = generate("MT541", drop(mt541_fields, "SETT"))

    assert good.validation.summary == "Ready to generate"
    assert one_missing.validation.summary.endswith("need attention") or (
        one_missing.validation.summary.endswith("needs attention")
    )


def test_every_layer_is_reported(mt541_fields: list[FieldInput]) -> None:
    result = generate("MT541", mt541_fields)

    reported = {item.layer for item in result.validation.layers}
    assert ValidationLayer.FIN_ENVELOPE in reported
    assert ValidationLayer.XSD in reported
    xsd = next(item for item in result.validation.layers if item.layer is ValidationLayer.XSD)
    assert xsd.state.value == "NOT_APPLICABLE"


# -- output ----------------------------------------------------------------------------


def test_block4_and_fin_are_both_available(mt541_fields: list[FieldInput]) -> None:
    result = generate("MT541", mt541_fields)

    assert result.outputs.block4 is not None
    assert result.outputs.block4.startswith("{4:")
    assert result.outputs.block4.endswith("-}")
    assert result.outputs.fin is not None
    assert result.outputs.fin.startswith("{1:F01")


def test_fin_contains_the_block_4_verbatim(mt541_fields: list[FieldInput]) -> None:
    result = generate("MT541", mt541_fields)

    assert result.outputs.block4 in (result.outputs.fin or "")


def test_mt_never_emits_xml(mt541_fields: list[FieldInput]) -> None:
    result = generate("MT541", mt541_fields)

    assert result.outputs.xml is None
    assert result.outputs.document is None
    assert result.outputs.app_hdr is None


def test_output_modes_are_honoured(mt541_fields: list[FieldInput]) -> None:
    result = studio_service.generate(
        GenerateRequest(
            format=MessageFormat.MT,
            message_type="MT541",
            fields=mt541_fields,
            output_modes=[OutputMode.BLOCK4],
            persist=False,
        )
    )

    assert result.outputs.block4 is not None
    assert result.outputs.fin is None


def test_canonical_json_lists_every_supplied_field(mt541_fields: list[FieldInput]) -> None:
    result = generate("MT541", mt541_fields)

    payload = result.outputs.canonical_json
    assert payload is not None
    assert len(payload["fields"]) == len(mt541_fields)
    assert {item["origin"] for item in payload["fields"]} == {"USER_ENTERED"}


def test_checksum_is_stable_for_the_same_input(mt541_fields: list[FieldInput]) -> None:
    first = generate("MT541", mt541_fields)
    second = generate("MT541", mt541_fields)

    assert first.checksum == second.checksum


def test_rendered_lines_map_back_to_fields(mt541_fields: list[FieldInput]) -> None:
    result = generate("MT541", mt541_fields)

    mapped = [line for line in result.rendered_lines if line.field_id]
    assert len(mapped) == len(mt541_fields)
    assert all(line.display_name for line in mapped)


def test_every_mt_message_generates_from_its_samples() -> None:
    from app.domain.enums import MessageType
    from app.studio.samples import available_variants

    for message_type in MessageType:
        for variant in available_variants(MessageFormat.MT, message_type.value):
            sample = build_sample(MessageFormat.MT, message_type.value, variant)
            result = generate(message_type.value, list(sample.inputs))
            assert result.valid, (
                message_type.value,
                variant,
                [item.message for item in result.validation.errors],
            )
            assert result.outputs.fin is not None
