"""Evaluation produces the platform's own findings, with the rule's provenance attached."""

from __future__ import annotations

from app.knowledge.models import RuleLayer
from app.rule_engine.binding import value_bag
from app.rule_engine.compiler import compile_pack
from app.rule_engine.dsl import Operator, Predicate
from app.rule_engine.evaluator import evaluate_rules, source_reference
from app.rule_engine.layers import build_effective
from app.rule_engine.refs import StructureIndex
from app.studio.models import IssueSeverity, MessageFormat, ValidationLayer
from tests.rule_engine.conftest import (
    AMT,
    CMONID,
    MESSAGE,
    PMT,
    TXCOND,
    mx,
    pack,
    restriction,
    rule,
)


def effective(index: StructureIndex, *packs):  # type: ignore[no-untyped-def]
    return build_effective(
        [compile_pack(item, index) for item in packs],
        format_=MessageFormat.MX,
        message_type=MESSAGE,
        profile_id="TEST_PROFILE",
    )


def test_a_satisfied_rule_says_nothing(index: StructureIndex) -> None:
    rules = effective(
        index,
        pack(
            index,
            rules=(
                rule(
                    "AMT-FOR-APMT",
                    Predicate(field=mx(AMT), operator=Operator.EXISTS),
                    when=Predicate(field=mx(PMT), operator=Operator.EQUALS, value="APMT"),
                ),
            ),
        ),
    )
    assert evaluate_rules(rules, value_bag([(PMT, "APMT"), (AMT, "100.00")])) == []
    # And a rule whose condition does not hold is not evaluated at all.
    assert evaluate_rules(rules, value_bag([(PMT, "FREE")])) == []


def test_a_broken_rule_produces_the_platforms_own_issue_shape(index: StructureIndex) -> None:
    rules = effective(
        index,
        pack(
            index,
            rules=(
                rule(
                    "AMT-FOR-APMT",
                    Predicate(field=mx(AMT), operator=Operator.EXISTS),
                    when=Predicate(field=mx(PMT), operator=Operator.EQUALS, value="APMT"),
                ),
            ),
        ),
    )
    issues = evaluate_rules(rules, value_bag([(PMT, "APMT")]))
    assert len(issues) == 1
    issue = issues[0]
    assert issue.rule_id == "AMT-FOR-APMT"
    assert issue.severity is IssueSeverity.ERROR
    assert issue.layer is ValidationLayer.BUSINESS_RULES
    # The finding names the field a tester must change, not the one that triggered it.
    assert issue.field == "Amount"
    assert issue.location == AMT
    assert issue.suggestion
    # The provenance a reviewer needs, on the platform's existing contract.
    assert issue.rule_layer == "Base business rule"
    assert issue.rule_pack_id.startswith("MX:sese.023")  # type: ignore[union-attr]
    assert issue.source_reference and "SYNTH-TEST-SOURCE" in issue.source_reference
    assert issue.review_status == "REVIEWED"


def test_every_layer_reports_and_none_suppresses_another(index: StructureIndex) -> None:
    rules = effective(
        index,
        pack(
            index,
            layer=RuleLayer.MARKET_PRACTICE,
            profile_id="TEST_MARKET",
            restrictions=(restriction("MKT-COND", TXCOND, ("NOMC", "PART")),),
        ),
        pack(
            index,
            layer=RuleLayer.CLIENT_PROFILE,
            profile_id="TEST_PROFILE",
            restrictions=(restriction("CLI-COND", TXCOND, ("NOMC",)),),
        ),
    )
    issues = evaluate_rules(rules, value_bag([(TXCOND, "CLEN")]))
    assert {issue.layer for issue in issues} == {
        ValidationLayer.MARKET_PRACTICE,
        ValidationLayer.CLIENT_PROFILE,
    }
    assert {issue.rule_layer for issue in issues} == {
        "Market practice rule",
        "Client rule",
    }
    # A value the market allows but the client does not is reported by the client alone.
    narrowed = evaluate_rules(rules, value_bag([(TXCOND, "PART")]))
    assert [issue.layer for issue in narrowed] == [ValidationLayer.CLIENT_PROFILE]


def test_a_restriction_reports_the_value_and_what_was_allowed(index: StructureIndex) -> None:
    rules = effective(
        index,
        pack(
            index,
            layer=RuleLayer.MARKET_PRACTICE,
            profile_id="TEST_MARKET",
            restrictions=(restriction("MKT-COND", TXCOND, ("NOMC", "PART")),),
        ),
    )
    issue = evaluate_rules(rules, value_bag([(TXCOND, "DIRT")]))[0]
    assert issue.current_value == "DIRT"
    assert issue.expected == "One of: NOMC, PART"
    assert issue.location == TXCOND


def test_severity_decides_whether_a_finding_is_an_error(index: StructureIndex) -> None:
    rules = effective(
        index,
        pack(
            index,
            rules=(
                rule(
                    "SOFT",
                    Predicate(field=mx(CMONID), operator=Operator.EXISTS),
                    severity=IssueSeverity.WARNING,
                ),
            ),
        ),
    )
    assert evaluate_rules(rules, value_bag([]))[0].severity is IssueSeverity.WARNING


def test_an_empty_effective_set_evaluates_to_nothing(index: StructureIndex) -> None:
    rules = build_effective(
        [], format_=MessageFormat.MX, message_type=MESSAGE, profile_id=None
    )
    assert rules.empty
    assert evaluate_rules(rules, value_bag([(AMT, "1")])) == []


def test_the_source_reference_names_identity_and_location_never_prose() -> None:
    from tests.rule_engine.conftest import evidence

    text = source_reference([evidence()])
    assert text is not None
    assert "SYNTH-TEST-SOURCE" in text
    assert "#S0001" in text
    assert "Test section" in text
    assert source_reference([]) is None


def test_evaluation_is_pure_and_repeatable(index: StructureIndex) -> None:
    rules = effective(
        index,
        pack(index, rules=(rule("R", Predicate(field=mx(AMT), operator=Operator.EXISTS)),)),
    )
    bag = value_bag([])
    first = evaluate_rules(rules, bag)
    second = evaluate_rules(rules, bag)
    assert [item.model_dump() for item in first] == [item.model_dump() for item in second]


def test_the_value_bag_keeps_occurrence_order() -> None:
    assert value_bag([("a", "1"), ("b", "x"), ("a", "2")]) == {"a": ["1", "2"], "b": ["x"]}
