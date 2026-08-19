"""Everything checkable about a pack, checked before anybody trusts it.

The compiler is the boundary a candidate and an installed pack both cross, so each check
here is doing double duty: it stops a bad rule reaching a reviewer looking valid, and it
stops a pack edited by hand after review being loaded.
"""

from __future__ import annotations

import pytest

from app.knowledge.models import RuleLayer
from app.rule_engine import DSL_VERSION
from app.rule_engine.compiler import EXECUTABLE_MARKERS, compile_pack
from app.rule_engine.diagnostics import RuleEngineError, RuleFindingCode
from app.rule_engine.dsl import (
    AllOf,
    AtLeastOne,
    ExactlyOne,
    Operator,
    Predicate,
    Subject,
)
from app.rule_engine.refs import StructureIndex
from tests.rule_engine.conftest import (
    ACCT,
    AMT,
    CMONID,
    PMT,
    STTLMDT,
    TRADDT,
    TXCOND,
    TXID,
    mx,
    pack,
    restriction,
    rule,
)


def codes_of(error: RuleEngineError) -> set[RuleFindingCode]:
    return {finding.code for finding in error.findings}


def compile_one(index: StructureIndex, item, **kwargs):  # type: ignore[no-untyped-def]
    if hasattr(item, "restriction_id"):
        return compile_pack(pack(index, restrictions=(item,), **kwargs), index)
    return compile_pack(pack(index, rules=(item,), **kwargs), index)


# -- references --------------------------------------------------------------------------


def test_a_rule_naming_a_missing_element_does_not_compile(index: StructureIndex) -> None:
    bad = rule(
        "TEST-MISSING",
        Predicate(field=mx("/Document/SctiesSttlmTxInstr/Nope"), operator=Operator.EXISTS),
    )
    with pytest.raises(RuleEngineError) as caught:
        compile_one(index, bad)
    assert RuleFindingCode.RULE_REFERENCE_INVALID in codes_of(caught.value)


def test_a_pack_for_an_uninstalled_message_does_not_compile(index: StructureIndex) -> None:
    with pytest.raises(RuleEngineError) as caught:
        compile_pack(
            pack(
                index,
                message_type="sese.023",
                rules=(rule("TEST-A", Predicate(field=mx(AMT), operator=Operator.EXISTS)),),
            ).model_copy(update={"message_type": "pacs.008"}),
            index,
        )
    assert RuleFindingCode.RULE_MESSAGE_UNKNOWN in codes_of(caught.value)


# -- types -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("predicate", "expected"),
    [
        (
            Predicate(field=mx(ACCT), operator=Operator.GREATER_THAN, value="1"),
            RuleFindingCode.RULE_TYPE_MISMATCH,
        ),
        (
            Predicate(field=mx(ACCT), operator=Operator.DATE_BEFORE, value="2026-01-01"),
            RuleFindingCode.RULE_TYPE_MISMATCH,
        ),
        (
            Predicate(field=mx(AMT), operator=Operator.MATCHES, value="[0-9]+"),
            RuleFindingCode.RULE_TYPE_MISMATCH,
        ),
        (
            Predicate(field=mx(AMT), operator=Operator.GREATER_THAN, value="not a number"),
            RuleFindingCode.RULE_TYPE_MISMATCH,
        ),
        (
            Predicate(
                field=mx(TRADDT),
                operator=Operator.DATE_BEFORE,
                other_field=mx(ACCT),
            ),
            RuleFindingCode.RULE_TYPE_MISMATCH,
        ),
        (
            Predicate(field=mx(PMT), operator=Operator.EQUALS, value="NOTACODE"),
            RuleFindingCode.RULE_CODE_UNKNOWN,
        ),
        (
            Predicate(field=mx(TXCOND), operator=Operator.IN, values=("NOMC", "ZZZZ")),
            RuleFindingCode.RULE_CODE_UNKNOWN,
        ),
    ],
)
def test_operand_and_operator_compatibility(
    index: StructureIndex, predicate: Predicate, expected: RuleFindingCode
) -> None:
    with pytest.raises(RuleEngineError) as caught:
        compile_one(index, rule("TEST-TYPES", predicate))
    assert expected in codes_of(caught.value)


def test_a_well_typed_rule_compiles(index: StructureIndex) -> None:
    compiled = compile_one(
        index,
        rule(
            "TEST-GOOD",
            Predicate(
                field=mx(TRADDT),
                operator=Operator.DATE_ON_OR_BEFORE,
                other_field=mx(STTLMDT),
            ),
            when=Predicate(field=mx(PMT), operator=Operator.EQUALS, value="APMT"),
        ),
    )
    assert len(compiled.rules) == 1
    # The finding points at the field the assertion is about — the one a tester has to
    # change — not at whichever field the condition happened to mention.
    assert compiled.rules[0].primary.key == TRADDT


# -- counts ------------------------------------------------------------------------------


def test_a_count_beyond_the_structures_cardinality_can_never_be_satisfied(
    index: StructureIndex,
) -> None:
    with pytest.raises(RuleEngineError) as caught:
        compile_one(
            index,
            rule(
                "TEST-COUNT",
                Predicate(
                    field=mx(CMONID),
                    subject=Subject.COUNT,
                    operator=Operator.GREATER_OR_EQUAL,
                    value="2",
                ),
            ),
        )
    assert RuleFindingCode.RULE_COUNT_NOT_REPEATABLE in codes_of(caught.value)


# -- regexes -----------------------------------------------------------------------------


@pytest.mark.parametrize("pattern", ["(a+)+", "([0-9]*)*", r"(\w)\1"])
def test_dangerous_or_unsupported_patterns_are_refused(
    index: StructureIndex, pattern: str
) -> None:
    with pytest.raises(RuleEngineError) as caught:
        compile_one(
            index,
            rule(
                "TEST-REGEX",
                Predicate(field=mx(ACCT), operator=Operator.MATCHES, value=pattern),
            ),
        )
    assert RuleFindingCode.RULE_REGEX_REJECTED in codes_of(caught.value)


def test_a_plain_pattern_is_accepted(index: StructureIndex) -> None:
    compile_one(
        index,
        rule(
            "TEST-REGEX-OK",
            Predicate(field=mx(ACCT), operator=Operator.MATCHES, value="[A-Z]{2}[0-9]{6}"),
        ),
    )


# -- executable content -------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "eval(open('/etc/passwd').read())",
        "__import__('os').system('rm -rf /')",
        "{{ 7 * 7 }}",
        "<script>fetch('https://x')</script>",
        "$(whoami) must be present",
        "See https://example.invalid/guide for the rule",
        "'; DROP TABLE messages; --;",
    ],
)
def test_anything_that_looks_executable_is_refused_anywhere_in_a_pack(
    index: StructureIndex, text: str
) -> None:
    from app.rule_engine.models import RuleFindingText

    hostile = rule("TEST-EXEC", Predicate(field=mx(AMT), operator=Operator.EXISTS)).model_copy(
        update={
            "finding": RuleFindingText(message=text.ljust(8, "."), suggestion="Do the thing.")
        }
    )
    with pytest.raises(RuleEngineError) as caught:
        compile_one(index, hostile)
    assert RuleFindingCode.RULE_EXECUTABLE_CONTENT_REJECTED in codes_of(caught.value)


def test_the_marker_list_covers_each_family_the_brief_names() -> None:
    joined = " ".join(EXECUTABLE_MARKERS)
    for family in ("eval(", "exec(", "__import__", "{{", "<script", "$(", "://", "drop table"):
        assert family in joined


# -- identity and structure compatibility --------------------------------------------------


def test_two_rules_may_not_share_an_identifier(index: StructureIndex) -> None:
    duplicate = rule("TEST-SAME", Predicate(field=mx(AMT), operator=Operator.EXISTS))
    other = rule("TEST-SAME", Predicate(field=mx(ACCT), operator=Operator.EXISTS))
    with pytest.raises(RuleEngineError) as caught:
        compile_pack(pack(index, rules=(duplicate, other)), index)
    assert RuleFindingCode.RULE_ID_DUPLICATE in codes_of(caught.value)


def test_a_rule_and_a_restriction_share_one_identifier_namespace(
    index: StructureIndex,
) -> None:
    with pytest.raises(RuleEngineError) as caught:
        compile_pack(
            pack(
                index,
                rules=(rule("TEST-CLASH", Predicate(field=mx(AMT), operator=Operator.EXISTS)),),
                restrictions=(restriction("TEST-CLASH", TXCOND, ("NOMC",)),),
            ),
            index,
        )
    assert RuleFindingCode.RULE_ID_DUPLICATE in codes_of(caught.value)


def test_a_pack_written_against_a_different_structure_does_not_load(
    index: StructureIndex,
) -> None:
    stale = pack(
        index,
        rules=(rule("TEST-STALE", Predicate(field=mx(AMT), operator=Operator.EXISTS)),),
        structure_checksum="sha256:" + "0" * 64,
    )
    with pytest.raises(RuleEngineError) as caught:
        compile_pack(stale, index)
    assert RuleFindingCode.RULE_STRUCTURE_VERSION_MISMATCH in codes_of(caught.value)


def test_a_pack_from_a_different_engine_version_does_not_load(index: StructureIndex) -> None:
    other = pack(
        index, rules=(rule("TEST-ENGINE", Predicate(field=mx(AMT), operator=Operator.EXISTS)),)
    ).model_copy(update={"dsl_version": DSL_VERSION + "-next"})
    with pytest.raises(RuleEngineError) as caught:
        compile_pack(other, index)
    assert RuleFindingCode.RULE_PACK_ID_INVALID in codes_of(caught.value)


# -- review ---------------------------------------------------------------------------------


def test_require_reviewed_refuses_a_candidate(index: StructureIndex) -> None:
    candidate = pack(
        index,
        rules=(
            rule("TEST-CAND", Predicate(field=mx(AMT), operator=Operator.EXISTS), reviewed=False),
        ),
        reviewed=False,
    )
    compile_pack(candidate, index)  # a candidate still has to be well formed
    with pytest.raises(RuleEngineError) as caught:
        compile_pack(candidate, index, require_reviewed=True)
    assert RuleFindingCode.RULE_REVIEW_REQUIRED in codes_of(caught.value)


# -- the structure keeps the last word --------------------------------------------------------


def test_a_rule_cannot_forbid_something_the_structure_always_requires(
    index: StructureIndex,
) -> None:
    with pytest.raises(RuleEngineError) as caught:
        compile_one(
            index, rule("TEST-IMPOSSIBLE", Predicate(field=mx(TXID), operator=Operator.ABSENT))
        )
    assert RuleFindingCode.RULE_OVERLAY_UNSATISFIABLE in codes_of(caught.value)


def test_a_conditional_rule_may_forbid_a_required_field_because_it_may_never_fire(
    index: StructureIndex,
) -> None:
    # The check is deliberately narrow: only an *unconditional* prohibition is impossible.
    compile_one(
        index,
        rule(
            "TEST-CONDITIONAL",
            Predicate(field=mx(TXID), operator=Operator.ABSENT),
            when=Predicate(field=mx(CMONID), operator=Operator.EXISTS),
        ),
    )


# -- code restrictions -------------------------------------------------------------------------


def test_a_restriction_may_only_name_codes_the_structure_declares(
    index: StructureIndex,
) -> None:
    with pytest.raises(RuleEngineError) as caught:
        compile_one(index, restriction("TEST-INVENT", TXCOND, ("NOMC", "ZZZZ")))
    assert RuleFindingCode.RULE_CODE_UNKNOWN in codes_of(caught.value)


def test_a_restriction_on_a_non_code_field_is_refused(index: StructureIndex) -> None:
    with pytest.raises(RuleEngineError) as caught:
        compile_one(index, restriction("TEST-NOTCODE", ACCT, ("ANY",)))
    assert RuleFindingCode.RULE_TYPE_MISMATCH in codes_of(caught.value)


def test_a_restriction_that_restricts_nothing_is_a_warning_not_an_error(
    index: StructureIndex,
) -> None:
    every = index.resolve(mx(TXCOND), "sese.023")
    assert every is not None
    compiled = compile_one(index, restriction("TEST-NOOP", TXCOND, every.codes))
    assert any(
        item.code is RuleFindingCode.RULE_OVERLAY_WIDENING for item in compiled.warnings
    )


# -- pack shape --------------------------------------------------------------------------------


def test_an_overlay_pack_must_name_its_profile_and_a_base_pack_must_not(
    index: StructureIndex,
) -> None:
    body = (rule("TEST-P", Predicate(field=mx(AMT), operator=Operator.EXISTS)),)
    with pytest.raises(ValueError):
        pack(index, layer=RuleLayer.MARKET_PRACTICE, rules=body)
    with pytest.raises(ValueError):
        pack(index, layer=RuleLayer.BASE_STANDARD, profile_id="SOME_PROFILE", rules=body)


def test_a_pack_may_never_claim_authoritative_completeness(index: StructureIndex) -> None:
    # A pack establishes what its evidence says. Whether the evidence covers the standard
    # is a different claim, and one nothing here can support.
    from app.rule_engine.models import RulePack

    good = pack(index, rules=(rule("TEST-C", Predicate(field=mx(AMT), operator=Operator.EXISTS)),))
    payload = good.model_dump(mode="json", by_alias=True, exclude_none=True)
    payload["authoritativeCompletenessKnown"] = True
    with pytest.raises(ValueError, match="authoritativeCompletenessKnown"):
        RulePack.model_validate(payload)


def test_evidence_must_name_a_source_the_pack_declares(index: StructureIndex) -> None:
    with pytest.raises(ValueError):
        pack(
            index,
            rules=(
                rule(
                    "TEST-EV",
                    Predicate(field=mx(AMT), operator=Operator.EXISTS),
                    source_id="SYNTH-OTHER-SOURCE",
                ),
            ),
        )


def test_group_operators_must_name_distinct_fields(index: StructureIndex) -> None:
    with pytest.raises(RuleEngineError) as caught:
        compile_one(
            index,
            rule("TEST-DUPFIELD", ExactlyOne(exactly_one=(mx(AMT), mx(AMT)))),
        )
    assert RuleFindingCode.RULE_OPERATOR_INVALID in codes_of(caught.value)


def test_a_nested_expression_compiles_and_binds_every_reference(
    index: StructureIndex,
) -> None:
    compiled = compile_one(
        index,
        rule(
            "TEST-NESTED",
            AllOf(
                all_of=(
                    Predicate(field=mx(AMT), operator=Operator.EXISTS),
                    AtLeastOne(at_least_one=(mx(CMONID), mx(TXCOND))),
                )
            ),
            when=Predicate(field=mx(PMT), operator=Operator.EQUALS, value="APMT"),
        ),
    )
    bound = compiled.rules[0].bindings
    assert {PMT, AMT, CMONID, TXCOND} <= {item.key for item in bound.values()}
