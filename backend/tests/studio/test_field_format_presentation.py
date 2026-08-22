"""What the studio tells a caller about a field's format, and how it says it.

The studio's promise is that no SWIFT knowledge is required. A specification row compiled
from source evidence carries the guide's own notation, and putting that notation under the
box verbatim breaks the promise — while replacing it entirely breaks the sample generator,
which derives a structurally valid value from it. Both facts are asserted here, because the
second one was learned by breaking it.
"""

from __future__ import annotations

import pytest

from app.knowledge_base.structures.swift_format import (
    compile_format,
    currency_offsets,
    describe_format,
    input_kind_for,
    looks_like_notation,
    synthetic_value,
)
from app.studio.catalogue import message_spec
from app.studio.models import InputKind, Lane, MessageFormat


@pytest.mark.parametrize(
    ("notation", "expected"),
    [
        ("<DATE2><CUR><AMOUNT>15", "a date (YYMMDD)"),
        ("3!a15d", "a three-letter currency code"),
        ("16x", "Up to 16 characters of text."),
        ("6!n", "Exactly 6 digits."),
        ("1!a", "Exactly 1 capital letter."),
        ("[/34x$]<BIC>", "(optional)"),
    ],
)
def test_a_notation_is_described_in_words(notation: str, expected: str) -> None:
    described = describe_format(notation)

    assert expected in described
    # The notation itself stays: an expert reads it faster than the sentence, and a bug
    # report needs it.
    assert notation in described


def test_a_description_never_leaves_a_component_out() -> None:
    """A sentence that omits a token reads as if the field were simpler than it is."""
    # ``<?>`` is Prowide's explicit unknown. There is no honest sentence for it.
    assert describe_format("<?>") == "SWIFT format <?>."


@pytest.mark.parametrize("notation", ["/8c/<HHMM><SIGN><OFFSET>", "4!c//16x", "4!c//4!c/4!c"])
def test_punctuation_is_not_reported_as_something_to_supply(notation: str) -> None:
    described = describe_format(notation)

    assert described.startswith("In order:")
    assert "SWIFT format" in described


def test_three_letters_before_an_amount_are_a_currency_and_nothing_else_is() -> None:
    """71A Details of Charges is ``3!a`` and its codes are BEN, OUR and SHA.

    Reading every lone ``3!a`` as a currency put "a three-letter currency code" under that
    field and sampled ``USD`` for it — a value the field does not accept.
    """
    assert currency_offsets("3!a15d")
    assert currency_offsets("3!a<AMOUNT>15")
    assert currency_offsets("6!n3!a15d")
    assert not currency_offsets("3!a")
    assert not currency_offsets("3!a4!c")

    assert synthetic_value("3!a15d").startswith("USD")
    assert not synthetic_value("3!a").startswith("USD")
    assert "currency" not in describe_format("3!a")


def test_the_guides_own_spelling_of_an_amount_gets_the_amount_control() -> None:
    """Prowide writes ``<CUR><AMOUNT>``; a guide writes ``3!a15d``. Same field."""
    for notation in ("3!a15d", "3!a<AMOUNT>15", "<DATE2><CUR><AMOUNT>15"):
        assert input_kind_for(compile_format(notation), codes=False) == "AMOUNT"


def test_notation_and_prose_are_told_apart() -> None:
    assert looks_like_notation(":4!c//16x")
    assert looks_like_notation("<DATE2><CUR><AMOUNT>15")
    assert not looks_like_notation("Option C uses a four-character qualifier.")


def test_a_configured_row_keeps_the_sentence_someone_wrote_for_it() -> None:
    """The authored prose lives in the same slot a compiled row's notation does."""
    spec = message_spec(MessageFormat.MT, "MT541", Lane.CONFIGURED)
    row = next(item for item in spec.fields if item.id == "MT541-A-20C-SEME")

    assert row.format_explanation.startswith("Option C")
    assert "SWIFT format" not in row.format_explanation
    # There is no notation to publish for it, so none is claimed.
    assert row.format_notation is None


def test_every_field_of_every_configured_message_can_be_asked_about() -> None:
    """An empty question reaches the tester as a blank prompt — in the field editor, and in
    the conversion screen's list of what the source could not supply."""
    for format_, message in (
        (MessageFormat.MT, "MT541"),
        (MessageFormat.MX, "sese.023.001.11"),
    ):
        spec = message_spec(format_, message, Lane.CONFIGURED)
        blank = [item.id for item in spec.fields if not item.business_question.strip()]
        assert blank == [], blank


def test_the_two_derived_input_kinds_exist_at_runtime() -> None:
    """The pack compiler has derived CURRENCY and DATETIME since the preview lane existed.

    Without the members here the loader fell back to TEXT and several hundred rows lost a
    control the source had already identified. A silent downgrade is the failure mode this
    guards.
    """
    assert InputKind("CURRENCY") is InputKind.CURRENCY
    assert InputKind("DATETIME") is InputKind.DATETIME
    assert input_kind_for(compile_format("<CUR>"), codes=False) == InputKind.CURRENCY.value
    assert (
        input_kind_for(compile_format("<DATE4><TIME2>"), codes=False)
        == InputKind.DATETIME.value
    )
