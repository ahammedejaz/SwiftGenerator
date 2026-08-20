"""The rule language: every operator, and the semantics that are easy to get wrong.

The absent-field cases matter most. A rule engine that silently answers "false" to
everything about a field nobody supplied will quietly stop enforcing half its rules, and
one that answers "true" will fail every message. Each operator's answer is pinned here.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.rule_engine.dsl import (
    MAX_PATTERN_LENGTH,
    Operator,
    Subject,
    depth,
    evaluate,
    failing_occurrences,
    references,
)
from app.rule_engine.occurrences import EvaluationContext, OccurrenceIdentity, OccurrenceValue
from app.rule_engine.refs import FieldKind
from tests.rule_engine.conftest import (
    AMT,
    CMONID,
    PMT,
    STTLMDT,
    TRADDT,
    TXCOND,
    binding,
    bindings,
    node,
)

CODE = binding(PMT, FieldKind.CODE, codes=("APMT", "FREE"))
AMOUNT = binding(AMT, FieldKind.DECIMAL)
TRADE = binding(TRADDT, FieldKind.DATE)
SETTLE = binding(STTLMDT, FieldKind.DATE)
COMMON = binding(CMONID, FieldKind.TEXT, max_occurs=4)
COND = binding(TXCOND, FieldKind.CODE, codes=("NOMC", "PART", "CLEN"))
BAG_BINDINGS = bindings(CODE, AMOUNT, TRADE, SETTLE, COMMON, COND)


def check(payload: dict, bag: dict) -> bool:
    return evaluate(node(payload), bag, BAG_BINDINGS)


# -- presence ---------------------------------------------------------------------------


def test_exists_and_absent_are_exact_opposites() -> None:
    present = {AMT: ["100.00"]}
    assert check({"field": {"format": "MX", "path": AMT}, "operator": "EXISTS"}, present)
    assert not check({"field": {"format": "MX", "path": AMT}, "operator": "ABSENT"}, present)
    assert check({"field": {"format": "MX", "path": AMT}, "operator": "ABSENT"}, {})
    assert not check({"field": {"format": "MX", "path": AMT}, "operator": "EXISTS"}, {})


def test_a_blank_value_is_not_a_present_value() -> None:
    # A field carrying only whitespace is the same as a field nobody supplied. Treating it
    # as present would let an empty box satisfy a requirement.
    assert not check(
        {"field": {"format": "MX", "path": AMT}, "operator": "EXISTS"}, {AMT: ["   "]}
    )


# -- positive operators: some value satisfies; absent is false ---------------------------


@pytest.mark.parametrize(
    ("operator", "operand", "matching", "other"),
    [
        ("EQUALS", {"value": "APMT"}, "APMT", "FREE"),
        ("IN", {"values": ["APMT"]}, "APMT", "FREE"),
    ],
)
def test_positive_operators_need_a_matching_value(
    operator: str, operand: dict, matching: str, other: str
) -> None:
    predicate = {"field": {"format": "MX", "path": PMT}, "operator": operator, **operand}
    assert check(predicate, {PMT: [matching]})
    assert not check(predicate, {PMT: [other]})
    # Nothing present cannot satisfy a positive claim.
    assert not check(predicate, {})


def test_a_positive_operator_is_satisfied_by_any_one_occurrence() -> None:
    predicate = {"field": {"format": "MX", "path": CMONID}, "operator": "EQUALS", "value": "B"}
    assert check(predicate, {CMONID: ["A", "B", "C"]})


# -- negative operators: every value satisfies; absent is vacuously true -----------------


@pytest.mark.parametrize(
    ("operator", "operand"),
    [("NOT_EQUALS", {"value": "APMT"}), ("NOT_IN", {"values": ["APMT"]})],
)
def test_negative_operators_are_vacuously_true_when_the_field_is_absent(
    operator: str, operand: dict
) -> None:
    # "must not be APMT" is satisfied by a message that carries no payment type at all.
    # The opposite reading would fail every message that simply omits an optional field.
    predicate = {"field": {"format": "MX", "path": PMT}, "operator": operator, **operand}
    assert check(predicate, {})
    assert check(predicate, {PMT: ["FREE"]})
    assert not check(predicate, {PMT: ["APMT"]})


def test_a_negative_operator_needs_every_occurrence_to_satisfy_it() -> None:
    predicate = {
        "field": {"format": "MX", "path": CMONID},
        "operator": "NOT_IN",
        "values": ["X"],
    }
    assert check(predicate, {CMONID: ["A", "B"]})
    assert not check(predicate, {CMONID: ["A", "X"]})


# -- text, numbers, dates ---------------------------------------------------------------


def test_matches_anchors_the_whole_value() -> None:
    predicate = {
        "field": {"format": "MX", "path": CMONID},
        "operator": "MATCHES",
        "value": "[A-Z]{3}[0-9]{4}",
    }
    assert check(predicate, {CMONID: ["ABC1234"]})
    # A partial match is not a match: an unanchored pattern would accept a longer value.
    assert not check(predicate, {CMONID: ["ABC1234X"]})


@pytest.mark.parametrize(
    ("operator", "threshold", "value", "expected"),
    [
        ("GREATER_THAN", "100", "100.01", True),
        ("GREATER_THAN", "100", "100", False),
        ("GREATER_OR_EQUAL", "100", "100", True),
        ("LESS_THAN", "100", "99.99", True),
        ("LESS_OR_EQUAL", "100", "100", True),
        ("LESS_OR_EQUAL", "100", "100.01", False),
    ],
)
def test_numeric_comparisons(operator: str, threshold: str, value: str, expected: bool) -> None:
    predicate = {
        "field": {"format": "MX", "path": AMT},
        "operator": operator,
        "value": threshold,
    }
    assert check(predicate, {AMT: [value]}) is expected


def test_a_value_that_is_not_a_number_simply_fails_its_comparison() -> None:
    # The FORMAT layer already reports a malformed amount. A business rule reporting it a
    # second time would tell a tester the same thing twice in different words.
    predicate = {
        "field": {"format": "MX", "path": AMT},
        "operator": "GREATER_THAN",
        "value": "1",
    }
    assert not check(predicate, {AMT: ["not a number"]})


@pytest.mark.parametrize(
    ("operator", "trade", "settle", "expected"),
    [
        ("DATE_ON_OR_BEFORE", "2026-01-01", "2026-01-03", True),
        ("DATE_ON_OR_BEFORE", "2026-01-03", "2026-01-03", True),
        ("DATE_ON_OR_BEFORE", "2026-01-04", "2026-01-03", False),
        ("DATE_BEFORE", "2026-01-03", "2026-01-03", False),
        ("DATE_AFTER", "2026-01-04", "2026-01-03", True),
        ("DATE_ON_OR_AFTER", "2026-01-03", "2026-01-03", True),
    ],
)
def test_date_comparisons_against_another_field(
    operator: str, trade: str, settle: str, expected: bool
) -> None:
    predicate = {
        "field": {"format": "MX", "path": TRADDT},
        "operator": operator,
        "otherField": {"format": "MX", "path": STTLMDT},
    }
    assert check(predicate, {TRADDT: [trade], STTLMDT: [settle]}) is expected


def test_a_date_comparison_against_a_missing_partner_is_false() -> None:
    predicate = {
        "field": {"format": "MX", "path": TRADDT},
        "operator": "DATE_ON_OR_BEFORE",
        "otherField": {"format": "MX", "path": STTLMDT},
    }
    assert not check(predicate, {TRADDT: ["2026-01-01"]})


# -- counts -----------------------------------------------------------------------------


def test_count_compares_occurrences_not_values() -> None:
    predicate = {
        "field": {"format": "MX", "path": CMONID},
        "subject": "COUNT",
        "operator": "GREATER_OR_EQUAL",
        "value": "2",
    }
    assert check(predicate, {CMONID: ["A", "B"]})
    assert not check(predicate, {CMONID: ["A"]})
    assert not check(predicate, {})


def test_count_equals_zero_is_how_absence_is_counted() -> None:
    predicate = {
        "field": {"format": "MX", "path": CMONID},
        "subject": "COUNT",
        "operator": "EQUALS",
        "value": "0",
    }
    assert check(predicate, {})
    assert not check(predicate, {CMONID: ["A"]})


# -- occurrence scopes ------------------------------------------------------------------


def occurrence_value(key: str, value: str, identity: OccurrenceIdentity) -> OccurrenceValue:
    return OccurrenceValue(key=key, value=value, occurrence=identity)


def scoped_context(*items: OccurrenceValue) -> EvaluationContext:
    bag: dict[str, list[str]] = {}
    for item in items:
        bag.setdefault(item.key, []).append(item.value)
    return EvaluationContext(bag=bag, occurrence_values=items)


def same_occurrence_rule() -> dict:
    return {
        "forEachOccurrence": {
            "sequencePath": "E1",
            "assert": {
                "implies": {
                    "if": {"field": {"format": "MX", "path": PMT}, "operator": "EXISTS"},
                    "then": {"field": {"format": "MX", "path": AMT}, "operator": "ABSENT"},
                }
            },
        }
    }


def test_same_occurrence_scope_does_not_become_a_global_restriction() -> None:
    first = OccurrenceIdentity.one("E1", 1)
    second = OccurrenceIdentity.one("E1", 2)
    rule = node(same_occurrence_rule())
    context = scoped_context(
        occurrence_value(PMT, "PSET", first),
        occurrence_value(AMT, "SAFE-ACCOUNT", second),
    )
    assert evaluate(rule, context, BAG_BINDINGS)


def test_same_occurrence_scope_fails_only_the_matching_occurrence() -> None:
    first = OccurrenceIdentity.one("E1", 1)
    second = OccurrenceIdentity.one("E1", 2)
    rule = node(same_occurrence_rule())
    context = scoped_context(
        occurrence_value(CMONID, "unrelated", first),
        occurrence_value(PMT, "PSET", second),
        occurrence_value(AMT, "SAFE-ACCOUNT", second),
    )
    assert not evaluate(rule, context, BAG_BINDINGS)
    failed = failing_occurrences(rule, context, BAG_BINDINGS)
    assert [item.display_path for item in failed] == ["E1[2]"]


def test_scoped_count_counts_values_inside_one_occurrence() -> None:
    first = OccurrenceIdentity.one("E3", 1)
    second = OccurrenceIdentity.one("E3", 2)
    rule = node(
        {
            "forEachOccurrence": {
                "sequencePath": "E3",
                "assert": {
                    "field": {"format": "MX", "path": CMONID},
                    "subject": "COUNT",
                    "operator": "LESS_OR_EQUAL",
                    "value": "1",
                },
            }
        }
    )
    valid = scoped_context(
        occurrence_value(CMONID, "A", first),
        occurrence_value(CMONID, "B", second),
    )
    invalid = scoped_context(
        occurrence_value(CMONID, "A", first),
        occurrence_value(CMONID, "B", first),
    )
    assert evaluate(rule, valid, BAG_BINDINGS)
    assert not evaluate(rule, invalid, BAG_BINDINGS)


def test_nested_occurrence_lineage_keeps_equal_local_indexes_distinct() -> None:
    parent_one = OccurrenceIdentity.one("P", 1)
    parent_two = OccurrenceIdentity.one("P", 2)
    child_one = OccurrenceIdentity.one("C", 1, parent=parent_one)
    child_two = OccurrenceIdentity.one("C", 1, parent=parent_two)
    rule = node(
        {
            "forEachOccurrence": {
                "sequencePath": "P",
                "assert": {
                    "forEachOccurrence": {
                        "sequencePath": "C",
                        "assert": {
                            "implies": {
                                "if": {
                                    "field": {"format": "MX", "path": PMT},
                                    "operator": "EXISTS",
                                },
                                "then": {
                                    "field": {"format": "MX", "path": AMT},
                                    "operator": "ABSENT",
                                },
                            }
                        },
                    }
                },
            }
        }
    )
    context = scoped_context(
        occurrence_value("parent", "one", parent_one),
        occurrence_value("parent", "two", parent_two),
        occurrence_value(PMT, "PSET", child_one),
        occurrence_value(AMT, "SAFE-ACCOUNT", child_two),
    )
    assert evaluate(rule, context, BAG_BINDINGS)


# -- boolean and group ------------------------------------------------------------------


def test_all_of_any_of_and_not() -> None:
    present = {PMT: ["APMT"], AMT: ["100"]}
    exists_amt = {"field": {"format": "MX", "path": AMT}, "operator": "EXISTS"}
    is_free = {"field": {"format": "MX", "path": PMT}, "operator": "EQUALS", "value": "FREE"}
    assert check({"allOf": [exists_amt, {"not": is_free}]}, present)
    assert not check({"allOf": [exists_amt, is_free]}, present)
    assert check({"anyOf": [exists_amt, is_free]}, present)
    assert not check({"anyOf": [is_free]}, present)


def test_implies_is_true_whenever_its_condition_is_false() -> None:
    rule = {
        "implies": {
            "if": {
                "field": {"format": "MX", "path": PMT},
                "operator": "EQUALS",
                "value": "APMT",
            },
            "then": {"field": {"format": "MX", "path": AMT}, "operator": "EXISTS"},
        }
    }
    assert check(rule, {PMT: ["FREE"]})
    assert check(rule, {PMT: ["APMT"], AMT: ["100"]})
    assert not check(rule, {PMT: ["APMT"]})


@pytest.mark.parametrize(
    ("shape", "none", "one", "two"),
    [
        ("exactlyOne", False, True, False),
        ("atLeastOne", False, True, True),
        ("atMostOne", True, True, False),
    ],
)
def test_group_operators_count_present_fields(
    shape: str, none: bool, one: bool, two: bool
) -> None:
    rule = {shape: [{"format": "MX", "path": AMT}, {"format": "MX", "path": CMONID}]}
    assert check(rule, {}) is none
    assert check(rule, {AMT: ["1"]}) is one
    assert check(rule, {AMT: ["1"], CMONID: ["X"]}) is two


# -- the model is closed ----------------------------------------------------------------


def test_an_unknown_operator_is_a_validation_error_not_a_runtime_surprise() -> None:
    with pytest.raises(ValidationError):
        node({"field": {"format": "MX", "path": AMT}, "operator": "SOMEWHAT_EQUALS"})


def test_an_unknown_key_is_refused() -> None:
    with pytest.raises(ValidationError):
        node(
            {
                "field": {"format": "MX", "path": AMT},
                "operator": "EXISTS",
                "python": "os.system",
            }
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"field": {"format": "MX", "path": AMT}, "operator": "EXISTS", "value": "x"},
        {"field": {"format": "MX", "path": AMT}, "operator": "IN"},
        {"field": {"format": "MX", "path": AMT}, "operator": "EQUALS", "values": ["a", "b"]},
        {"field": {"format": "MX", "path": AMT}, "operator": "MATCHES"},
        {
            "field": {"format": "MX", "path": AMT},
            "operator": "EQUALS",
            "value": "1",
            "otherField": {"format": "MX", "path": CMONID},
        },
        {"field": {"format": "MX", "path": AMT}, "operator": "IN", "values": ["a", "a"]},
        {"exactlyOne": [{"format": "MX", "path": AMT}]},
        {
            "field": {"format": "MX", "path": AMT},
            "subject": "COUNT",
            "operator": "GREATER_THAN",
            "otherField": {"format": "MX", "path": CMONID},
        },
        {
            "field": {"format": "MX", "path": AMT},
            "operator": "MATCHES",
            "value": "x" * (MAX_PATTERN_LENGTH + 1),
        },
    ],
)
def test_malformed_predicates_are_refused_at_validation(payload: dict) -> None:
    with pytest.raises(ValidationError):
        node(payload)


def test_an_mx_reference_carries_a_path_and_an_mt_reference_does_not() -> None:
    with pytest.raises(ValidationError):
        node({"field": {"format": "MX", "fieldId": "MT541-A-20C-SEME"}, "operator": "EXISTS"})
    with pytest.raises(ValidationError):
        node({"field": {"format": "MT", "path": AMT}, "operator": "EXISTS"})


# -- walking ----------------------------------------------------------------------------


def test_references_and_depth_are_read_off_the_tree() -> None:
    rule = node(
        {
            "implies": {
                "if": {
                    "field": {"format": "MX", "path": PMT},
                    "operator": "EQUALS",
                    "value": "APMT",
                },
                "then": {
                    "allOf": [
                        {"field": {"format": "MX", "path": AMT}, "operator": "EXISTS"},
                        {
                            "exactlyOne": [
                                {"format": "MX", "path": CMONID},
                                {"format": "MX", "path": TXCOND},
                            ]
                        },
                    ]
                },
            }
        }
    )
    assert depth(rule) == 3
    assert [ref.path for ref in references(rule)] == [PMT, AMT, CMONID, TXCOND]


def test_operator_membership_sets_agree_with_the_enum() -> None:
    # A new operator that lands in no family would silently skip its type check.
    from app.rule_engine.dsl import (
        DATE_OPERATORS,
        MEMBERSHIP_OPERATORS,
        NUMERIC_OPERATORS,
        PRESENCE_OPERATORS,
    )

    classified = (
        PRESENCE_OPERATORS
        | MEMBERSHIP_OPERATORS
        | NUMERIC_OPERATORS
        | DATE_OPERATORS
        | {Operator.EQUALS, Operator.NOT_EQUALS, Operator.MATCHES}
    )
    assert set(Operator) == classified
    assert set(Subject) == {Subject.VALUE, Subject.COUNT}
