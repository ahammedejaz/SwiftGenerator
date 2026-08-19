"""Base, market and client: what narrowing means, and what the engine refuses to resolve.

The two properties worth stating plainly. An overlay may only *narrow*: a higher layer
that permits something a lower one forbids is refused, not applied. And where two layers
genuinely contradict each other, the engine names both rules and stops — it never picks a
winner, because neither layer's authority is the engine's to weigh.
"""

from __future__ import annotations

import pytest

from app.knowledge.models import RuleLayer
from app.rule_engine.compiler import compile_pack
from app.rule_engine.diagnostics import RuleEngineError, RuleFindingCode
from app.rule_engine.dsl import (
    AllOf,
    AtLeastOne,
    ExactlyOne,
    Operator,
    Predicate,
)
from app.rule_engine.layers import (
    LAYER_ORDER,
    VALIDATION_LAYER,
    RuleIntent,
    build_effective,
    rule_intent,
)
from app.rule_engine.refs import StructureIndex
from app.studio.models import MessageFormat, ValidationLayer
from tests.rule_engine.conftest import (
    ACCT,
    AMT,
    CMONID,
    DESC,
    MESSAGE,
    PMT,
    STTLMDT,
    TRADDT,
    TXCOND,
    mx,
    pack,
    restriction,
    rule,
)


def effective(index: StructureIndex, *packs, profile: str = "TEST_PROFILE"):  # type: ignore[no-untyped-def]
    compiled = [compile_pack(item, index) for item in packs]
    return build_effective(
        compiled, format_=MessageFormat.MX, message_type=MESSAGE, profile_id=profile
    )


def codes_of(error: RuleEngineError) -> set[RuleFindingCode]:
    return {finding.code for finding in error.findings}


def market(index: StructureIndex, **kwargs):  # type: ignore[no-untyped-def]
    return pack(index, layer=RuleLayer.MARKET_PRACTICE, profile_id="TEST_MARKET", **kwargs)


def client(index: StructureIndex, **kwargs):  # type: ignore[no-untyped-def]
    return pack(index, layer=RuleLayer.CLIENT_PROFILE, profile_id="TEST_PROFILE", **kwargs)


# -- narrowing -----------------------------------------------------------------------------


def test_a_client_may_narrow_what_a_market_allows(index: StructureIndex) -> None:
    result = effective(
        index,
        market(index, restrictions=(restriction("MKT-COND", TXCOND, ("NOMC", "PART", "CLEN")),)),
        client(index, restrictions=(restriction("CLI-COND", TXCOND, ("NOMC",)),)),
    )
    assert len(result.restrictions) == 2
    assert result.layers_present() == (RuleLayer.MARKET_PRACTICE, RuleLayer.CLIENT_PROFILE)


def test_a_client_may_not_widen_what_a_market_allows(index: StructureIndex) -> None:
    with pytest.raises(RuleEngineError) as caught:
        effective(
            index,
            market(index, restrictions=(restriction("MKT-COND", TXCOND, ("NOMC", "PART")),)),
            client(
                index,
                restrictions=(restriction("CLI-COND", TXCOND, ("NOMC", "PART", "CLEN")),),
            ),
        )
    assert RuleFindingCode.RULE_OVERLAY_WIDENING in codes_of(caught.value)


def test_two_layers_that_allow_nothing_in_common_are_a_conflict(
    index: StructureIndex,
) -> None:
    with pytest.raises(RuleEngineError) as caught:
        effective(
            index,
            market(index, restrictions=(restriction("MKT-COND", TXCOND, ("NOMC", "PART")),)),
            client(index, restrictions=(restriction("CLI-COND", TXCOND, ("CLEN",)),)),
        )
    assert RuleFindingCode.RULE_OVERLAY_CONFLICT in codes_of(caught.value)


# -- presence conflicts ---------------------------------------------------------------------


def test_required_in_one_layer_and_forbidden_in_another_is_refused(
    index: StructureIndex,
) -> None:
    with pytest.raises(RuleEngineError) as caught:
        effective(
            index,
            market(
                index,
                rules=(rule("MKT-NEEDS", Predicate(field=mx(CMONID), operator=Operator.EXISTS)),),
            ),
            client(
                index,
                rules=(rule("CLI-BANS", Predicate(field=mx(CMONID), operator=Operator.ABSENT)),),
            ),
        )
    error = caught.value
    assert RuleFindingCode.RULE_OVERLAY_CONFLICT in codes_of(error)
    # Both rules are named. The engine does not choose between them.
    related = {name for finding in error.findings for name in finding.related}
    assert {"MKT-NEEDS", "CLI-BANS"} <= related


def test_rule_intent_classifies_only_the_shapes_it_can_be_sure_of() -> None:
    requires = rule("R", Predicate(field=mx(CMONID), operator=Operator.EXISTS))
    forbids = rule("F", Predicate(field=mx(CMONID), operator=Operator.ABSENT))
    conditional = rule(
        "C",
        Predicate(field=mx(CMONID), operator=Operator.EXISTS),
        when=Predicate(field=mx(PMT), operator=Operator.EQUALS, value="APMT"),
    )
    compound = rule(
        "X",
        AllOf(
            all_of=(
                Predicate(field=mx(CMONID), operator=Operator.EXISTS),
                Predicate(field=mx(DESC), operator=Operator.EXISTS),
            )
        ),
    )
    assert rule_intent(requires) == (RuleIntent.REQUIRES, mx(CMONID).canonical())
    assert rule_intent(forbids) == (RuleIntent.FORBIDS, mx(CMONID).canonical())
    # A rule that only sometimes applies is not a standing requirement, and a compound
    # assertion is not approximated into one.
    assert rule_intent(conditional) is None
    assert rule_intent(compound) is None


def test_a_group_whose_every_candidate_is_forbidden_can_never_be_satisfied(
    index: StructureIndex,
) -> None:
    with pytest.raises(RuleEngineError) as caught:
        effective(
            index,
            market(
                index,
                rules=(rule("MKT-ONEOF", AtLeastOne(at_least_one=(mx(CMONID), mx(DESC)))),),
            ),
            client(
                index,
                rules=(
                    rule("CLI-NO-CMON", Predicate(field=mx(CMONID), operator=Operator.ABSENT)),
                    rule("CLI-NO-DESC", Predicate(field=mx(DESC), operator=Operator.ABSENT)),
                ),
            ),
        )
    assert RuleFindingCode.RULE_OVERLAY_UNSATISFIABLE in codes_of(caught.value)


def test_a_group_with_one_candidate_left_is_still_satisfiable(index: StructureIndex) -> None:
    result = effective(
        index,
        market(
            index, rules=(rule("MKT-ONEOF", ExactlyOne(exactly_one=(mx(CMONID), mx(DESC)))),)
        ),
        client(
            index, rules=(rule("CLI-NO-DESC", Predicate(field=mx(DESC), operator=Operator.ABSENT)),)
        ),
    )
    assert len(result.rules) == 2


# -- self-contradiction ------------------------------------------------------------------------


def test_a_rule_that_needs_a_field_present_and_absent_is_refused(
    index: StructureIndex,
) -> None:
    with pytest.raises(RuleEngineError) as caught:
        effective(
            index,
            pack(
                index,
                rules=(
                    rule(
                        "SELF-CONTRA",
                        Predicate(field=mx(AMT), operator=Operator.EXISTS),
                        when=AllOf(
                            all_of=(
                                Predicate(field=mx(CMONID), operator=Operator.EXISTS),
                                Predicate(field=mx(CMONID), operator=Operator.ABSENT),
                            )
                        ),
                    ),
                ),
            ),
        )
    assert RuleFindingCode.RULE_OVERLAY_UNSATISFIABLE in codes_of(caught.value)


def test_a_single_occurrence_field_cannot_equal_two_things_at_once(
    index: StructureIndex,
) -> None:
    with pytest.raises(RuleEngineError) as caught:
        effective(
            index,
            pack(
                index,
                rules=(
                    rule(
                        "TWO-VALUES",
                        AllOf(
                            all_of=(
                                Predicate(field=mx(PMT), operator=Operator.EQUALS, value="APMT"),
                                Predicate(field=mx(PMT), operator=Operator.EQUALS, value="FREE"),
                            )
                        ),
                    ),
                ),
            ),
        )
    assert RuleFindingCode.RULE_OVERLAY_UNSATISFIABLE in codes_of(caught.value)


def test_two_dates_cannot_each_come_strictly_first(index: StructureIndex) -> None:
    with pytest.raises(RuleEngineError) as caught:
        effective(
            index,
            market(
                index,
                rules=(
                    rule(
                        "MKT-ORDER",
                        Predicate(
                            field=mx(TRADDT),
                            operator=Operator.DATE_BEFORE,
                            other_field=mx(STTLMDT),
                        ),
                    ),
                ),
            ),
            client(
                index,
                rules=(
                    rule(
                        "CLI-ORDER",
                        Predicate(
                            field=mx(STTLMDT),
                            operator=Operator.DATE_BEFORE,
                            other_field=mx(TRADDT),
                        ),
                    ),
                ),
            ),
        )
    assert RuleFindingCode.RULE_OVERLAY_UNSATISFIABLE in codes_of(caught.value)


# -- identity and ordering ----------------------------------------------------------------------


def test_two_installed_packs_may_not_declare_the_same_rule_identifier(
    index: StructureIndex,
) -> None:
    with pytest.raises(RuleEngineError) as caught:
        effective(
            index,
            market(
                index,
                rules=(rule("SHARED-ID", Predicate(field=mx(AMT), operator=Operator.EXISTS)),),
            ),
            client(
                index,
                rules=(rule("SHARED-ID", Predicate(field=mx(ACCT), operator=Operator.EXISTS)),),
            ),
        )
    assert RuleFindingCode.RULE_ID_DUPLICATE in codes_of(caught.value)


def test_layers_evaluate_in_order_and_none_suppresses_another(
    index: StructureIndex,
) -> None:
    result = effective(
        index,
        pack(index, rules=(rule("BASE-R", Predicate(field=mx(AMT), operator=Operator.EXISTS)),)),
        market(index, rules=(rule("MKT-R", Predicate(field=mx(ACCT), operator=Operator.EXISTS)),)),
        client(
            index, rules=(rule("CLI-R", Predicate(field=mx(CMONID), operator=Operator.EXISTS)),)
        ),
    )
    assert [item.layer for item in result.rules] == list(LAYER_ORDER)
    assert [item.rule.rule_id for item in result.rules] == ["BASE-R", "MKT-R", "CLI-R"]


def test_each_rule_layer_maps_to_a_validation_layer() -> None:
    assert set(VALIDATION_LAYER) == set(LAYER_ORDER)
    assert VALIDATION_LAYER[RuleLayer.BASE_STANDARD] is ValidationLayer.BUSINESS_RULES
    assert VALIDATION_LAYER[RuleLayer.MARKET_PRACTICE] is ValidationLayer.MARKET_PRACTICE
    assert VALIDATION_LAYER[RuleLayer.CLIENT_PROFILE] is ValidationLayer.CLIENT_PROFILE
