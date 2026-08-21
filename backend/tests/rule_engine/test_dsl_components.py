"""``rule-dsl/3``: component extraction on a predicate, and ``allEqual``.

The semantics under test: a component is a named group of a pattern derived from the
field's own format; a value without the component satisfies no existential comparison and
is skipped by the universal ones; ``allEqual`` holds when every present value (every
occurrence) of every listed field agrees, and vacuously with fewer than two values.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.knowledge_base.structures.swift_format import component_pattern
from app.rule_engine.dsl import evaluate
from app.rule_engine.refs import FieldKind
from tests.rule_engine.conftest import AMT, CMONID, binding, bindings, node

AMOUNT = binding(AMT, FieldKind.TEXT, max_occurs=4)
OTHER = binding(CMONID, FieldKind.TEXT, max_occurs=4)
BINDINGS = bindings(AMOUNT, OTHER)
CURRENCY = {"pattern": r"^(?P<value>[A-Z]{3})", "group": "value"}
DATED_CURRENCY = {"pattern": r"^\d{6}(?P<value>[A-Z]{3})", "group": "value"}


def check(payload: dict, bag: dict) -> bool:
    return evaluate(node(payload), bag, BINDINGS)


def test_extract_compares_the_component_not_the_value() -> None:
    payload = {
        "field": {"format": "MX", "path": AMT},
        "operator": "EQUALS",
        "value": "EUR",
        "extract": CURRENCY,
    }
    assert check(payload, {AMT: ["EUR1234,56"]})
    assert not check(payload, {AMT: ["USD1234,56"]})


def test_extract_on_both_sides_compares_components_with_different_formats() -> None:
    """MT103 C1: the currency of 33B (``3!a15d``) against that of 32A (``6!n3!a15d``)."""
    payload = {
        "field": {"format": "MX", "path": AMT},
        "operator": "NOT_EQUALS",
        "otherField": {"format": "MX", "path": CMONID},
        "extract": CURRENCY,
        "otherExtract": DATED_CURRENCY,
    }
    assert check(payload, {AMT: ["EUR12,5"], CMONID: ["260818USD12,5"]})
    assert not check(payload, {AMT: ["EUR12,5"], CMONID: ["260818EUR12,5"]})


def test_a_value_without_the_component_satisfies_no_existential_comparison() -> None:
    payload = {
        "field": {"format": "MX", "path": AMT},
        "operator": "EQUALS",
        "value": "EUR",
        "extract": CURRENCY,
    }
    assert not check(payload, {AMT: ["12,5"]})
    universal = dict(payload, operator="NOT_EQUALS")
    assert check(universal, {AMT: ["12,5"]})  # nothing to compare: vacuously true


def test_all_equal_holds_across_fields_and_occurrences() -> None:
    payload = {
        "allEqual": [
            {"field": {"format": "MX", "path": AMT}, "extract": CURRENCY},
            {"field": {"format": "MX", "path": CMONID}, "extract": DATED_CURRENCY},
        ]
    }
    assert check(payload, {AMT: ["EUR1,", "EUR2,"], CMONID: ["260818EUR3,"]})
    assert not check(payload, {AMT: ["EUR1,", "USD2,"], CMONID: ["260818EUR3,"]})
    assert check(payload, {})  # vacuous
    assert check(payload, {AMT: ["EUR1,"]})


def test_extract_needs_a_value_comparison_and_a_named_group() -> None:
    with pytest.raises(ValidationError):
        node(
            {
                "field": {"format": "MX", "path": AMT},
                "operator": "EXISTS",
                "extract": CURRENCY,
            }
        )
    with pytest.raises(ValidationError):
        node(
            {
                "field": {"format": "MX", "path": AMT},
                "operator": "EQUALS",
                "value": "EUR",
                "extract": {"pattern": r"^[A-Z]{3}", "group": "value"},
            }
        )
    with pytest.raises(ValidationError):
        node({"allEqual": []})


@pytest.mark.parametrize(
    ("notation", "component", "value", "expected"),
    [
        ("6!n3!a15d", "CURRENCY", "260818EUR1234,56", "EUR"),
        ("[N]3!a15d", "CURRENCY", "NEUR12,5", "EUR"),
        (":4!c//[N]3!a15d", "CURRENCY", "EUR12,5", "EUR"),
        ("1!a6!n3!a15d", "CURRENCY", "C260818GBP1,", "GBP"),
        ("3!a15d", "AMOUNT", "EUR12,5", "12,5"),
    ],
)
def test_component_patterns_come_from_the_format_notation(
    notation: str, component: str, value: str, expected: str
) -> None:
    import re

    pattern = component_pattern(notation, component)
    assert pattern is not None
    match = re.match(pattern, value)
    assert match is not None and match.group("value") == expected


def test_a_format_without_the_component_yields_no_pattern() -> None:
    assert component_pattern("16x", "CURRENCY") is None
    assert component_pattern("<PARTYFLD-J>", "CURRENCY") is None
