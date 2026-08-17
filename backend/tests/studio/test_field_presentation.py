"""The field presentation model the browser, the JSON API and Excel all read.

Guided mode, Expert mode, the automation API and the workbook may show different *amounts*
of this, but they must not disagree about any of it — which is only guaranteed while there
is one projection and no client works it out for itself.
"""

from __future__ import annotations

import pytest

from app.domain.enums import MessageType
from app.knowledge.code_lists import code_lists
from app.studio.catalogue import message_spec
from app.studio.models import (
    FieldInput,
    GenerateRequest,
    InputKind,
    MessageFormat,
    SampleVariant,
)
from app.studio.mx.registry import mx_registry
from app.studio.samples import build_sample
from app.studio.service import studio_service

MT_TYPES = [item.value for item in MessageType]
MX_TYPES = [item.message_type for item in mx_registry.all_specs()]


def all_mt_fields():  # type: ignore[no-untyped-def]
    for message_type in MT_TYPES:
        for field in message_spec(MessageFormat.MT, message_type).fields:
            yield message_type, field


# -- every controlled field is a controlled control ---------------------------------------


@pytest.mark.parametrize("message_type", MT_TYPES + MX_TYPES)
def test_every_field_declares_the_control_it_deserves(message_type: str) -> None:
    format_ = MessageFormat.MT if message_type.startswith("MT") else MessageFormat.MX

    for field in message_spec(format_, message_type).fields:
        assert isinstance(field.input_kind, InputKind)


def test_every_configured_code_list_renders_as_a_selector_with_labels() -> None:
    """No finite code list is left as a free-text box, and none shows bare codes.

    The control used to be inferred in the browser from whether one of the field's examples
    happened to appear in its code list, so a value outside the list silently turned a
    dropdown back into a text input.
    """
    checked = 0
    for message_type, field in all_mt_fields():
        if not field.allowed_codes:
            continue
        # A code that is only part of the value — a quantity type such as UNIT/1000, or a
        # page indicator such as 1/ONLY — is a composite, not an enumeration.
        if field.input_kind in {InputKind.QUANTITY, InputKind.TEXT}:
            continue
        assert field.input_kind in {InputKind.SELECT, InputKind.INDICATOR}, (
            message_type,
            field.id,
        )
        assert len(field.allowed_values) == len(field.allowed_codes), field.id
        assert [item.code for item in field.allowed_values] == field.allowed_codes
        assert all(item.label for item in field.allowed_values), field.id
        checked += 1
    assert checked > 20


def test_labels_come_from_configuration_and_not_from_a_component() -> None:
    field = next(
        item for item in message_spec(MessageFormat.MT, "MT541").fields if item.qualifier == "SETR"
    )

    assert field.code_list == "SETTLEMENT_TRANSACTION_TYPE"
    assert {item.code: item.label for item in field.allowed_values}["TRAD"] == "Trade"


def test_a_single_valued_code_list_is_still_a_selector() -> None:
    """One allowed value: the UI preselects it, so it is a select rather than a text box."""
    field = next(
        item
        for item in message_spec(MessageFormat.MT, "MT548").fields
        if item.tag == "23G"
    )

    assert field.input_kind is InputKind.SELECT
    assert len(field.allowed_values) == 1


@pytest.mark.parametrize(
    ("message_type", "tag", "expected"),
    [
        ("MT541", "98A", InputKind.DATE),
        ("MT541", "19A", InputKind.AMOUNT),
        ("MT541", "20C", InputKind.REFERENCE),
        ("MT541", "36B", InputKind.QUANTITY),
        ("MT541", "35B", InputKind.IDENTIFIER),
        ("MT541", "95P", InputKind.PARTY_BIC),
        ("MT541", "95R", InputKind.PARTY_PROPRIETARY),
        ("MT541", "23G", InputKind.SELECT),
        ("MT548", "70D", InputKind.NARRATIVE),
        ("MT537", "17B", InputKind.INDICATOR),
    ],
)
def test_a_field_gets_a_control_that_matches_what_it_holds(
    message_type: str, tag: str, expected: InputKind
) -> None:
    field = next(
        item for item in message_spec(MessageFormat.MT, message_type).fields if item.tag == tag
    )

    assert field.input_kind is expected


def test_no_field_is_left_as_a_generic_text_box_by_accident() -> None:
    """A plain text box is now the exception, and each remaining one is deliberate.

    A tag that *could* carry codes but has none configured is honestly a text box.
    """
    generic = {
        field.tag
        for _, field in all_mt_fields()
        if field.input_kind is InputKind.TEXT and not field.allowed_codes
    }

    # 97A is an account number, 28E a page-and-continuation composite, 99A a day count,
    # 11A a currency with no configured list, 13A a linkage number, and 22F/22H/24B where
    # this configuration declares no codes for the qualifier.
    assert generic <= {"97A", "28E", "99A", "11A", "13A", "22F", "22H", "24B"}
    # What would be wrong is a field that has a code list and still renders as free text.
    # 28E is exempt: its code is the second half of a page-and-continuation value, so a
    # whole-cell dropdown would drop the page number.
    from app.knowledge.presentation import COMPOSITE_TAGS

    assert not [
        field.id
        for _, field in all_mt_fields()
        if field.allowed_codes
        and field.input_kind is InputKind.TEXT
        and field.tag not in COMPOSITE_TAGS
    ]


# -- the server is still the authority ----------------------------------------------------


def test_a_code_outside_the_list_is_rejected_even_when_posted_straight_to_the_api() -> None:
    """Client-side controls are usability. They are never the enforcement."""
    sample = build_sample(MessageFormat.MT, "MT541", SampleVariant.TYPICAL)
    fields = [
        item.model_copy(update={"value": "ZZZZ"}) if item.tag == "23G" else item
        for item in sample.inputs
    ]

    result = studio_service.generate(
        GenerateRequest(
            format=MessageFormat.MT, message_type="MT541", fields=fields, persist=False
        )
    )

    assert not result.valid
    assert any(item.rule_id == "MT_CODE_NOT_ALLOWED" for item in result.validation.errors)


def test_an_arbitrary_string_in_a_controlled_field_is_rejected() -> None:
    result = studio_service.generate(
        GenerateRequest(
            format=MessageFormat.MT,
            message_type="MT541",
            fields=[FieldInput(sequence="SETDET", tag="22F", qualifier="SETR", value="TYPE")],
            persist=False,
        )
    )

    assert any(item.rule_id == "MT_CODE_NOT_ALLOWED" for item in result.validation.errors)


# -- one vocabulary, everywhere ------------------------------------------------------------


def test_the_catalogue_and_the_excel_reference_read_the_same_projection() -> None:
    from app.studio.excel import reference_rows

    rows = reference_rows(MessageFormat.MT, ["MT541"])
    spec = message_spec(MessageFormat.MT, "MT541")

    assert [item.field.id for item in rows] == [item.id for item in spec.fields]
    assert all(
        item.field.allowed_values == expected.allowed_values
        for item, expected in zip(rows, spec.fields, strict=True)
    )


def test_message_intelligence_shows_the_same_codes_as_the_form() -> None:
    from app.studio.intelligence import detail as field_detail

    detail = field_detail("MT541-E-22F-SETR")
    field = next(
        item for item in message_spec(MessageFormat.MT, "MT541").fields if item.qualifier == "SETR"
    )

    assert detail.allowed_values == field.allowed_values
    assert detail.input_kind is field.input_kind


def test_every_named_code_list_is_actually_used() -> None:
    """An unused list is either a mistake or dead configuration; say so at test time."""
    used = {field.code_list for _, field in all_mt_fields() if field.code_list}
    for spec in mx_registry.all_specs():
        for flat in mx_registry.flat(spec.message_type):
            if flat.element.code_list:
                used.add(flat.element.code_list)

    declared = {item.id for item in code_lists.all()}
    # PARTY_IDENTIFICATION_METHOD describes the choice between field options rather than a
    # field's own value, so it is read by the form rather than by a record.
    assert declared - used == {"PARTY_IDENTIFICATION_METHOD"}


def test_a_code_list_never_leaks_onto_an_unrelated_field() -> None:
    """A YAML merge key copies every value, including a code list.

    That is how a payment date came to declare the code list of a voluntary-event
    indicator, and how an account number came to declare `VOLU` as its only allowed value.
    A list may legitimately be shared — by the same tag across qualifiers, or the same
    qualifier across tags — but never by a field that has neither in common with the others.
    """
    users: dict[str, set[tuple[str, str | None]]] = {}
    for _, field in all_mt_fields():
        if field.code_list:
            users.setdefault(field.code_list, set()).add((field.tag or "", field.qualifier))

    for list_id, addresses in users.items():
        tags = {tag for tag, _ in addresses}
        qualifiers = {qualifier for _, qualifier in addresses}
        assert len(tags) == 1 or len(qualifiers) == 1, (list_id, sorted(addresses))
