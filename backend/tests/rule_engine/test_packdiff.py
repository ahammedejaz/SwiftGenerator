"""Deterministic pack diff — what a standards-release upgrade will be read through."""

from __future__ import annotations

from app.rule_engine.dsl import Operator, Predicate
from app.rule_engine.models import RuleReview, RuleReviewStatus
from app.rule_engine.packdiff import PackChangeKind, diff_packs
from app.rule_engine.refs import StructureIndex
from app.studio.models import IssueSeverity
from tests.rule_engine.conftest import AMT, CMONID, TXCOND, mx, node, pack, restriction, rule


def kinds(before, after) -> set[PackChangeKind]:  # type: ignore[no-untyped-def]
    return {change.kind for change in diff_packs(before, after).changes}


def base(index: StructureIndex):  # type: ignore[no-untyped-def]
    return pack(
        index,
        rules=(rule("R-ONE", Predicate(field=mx(AMT), operator=Operator.EXISTS)),),
        restrictions=(restriction("C-ONE", TXCOND, ("NOMC", "PART")),),
    )


def test_an_unchanged_pack_diffs_to_nothing(index: StructureIndex) -> None:
    assert diff_packs(base(index), base(index)).identical
    assert "identical" in diff_packs(base(index), base(index)).render()


def test_added_and_removed_rules(index: StructureIndex) -> None:
    before = base(index)
    after = before.model_copy(
        update={
            "rules": (
                *before.rules,
                rule("R-TWO", Predicate(field=mx(CMONID), operator=Operator.EXISTS)),
            )
        }
    )
    assert kinds(before, after) == {PackChangeKind.RULE_ADDED}
    assert kinds(after, before) == {PackChangeKind.RULE_REMOVED}


def test_a_changed_assertion_condition_or_severity_is_named(index: StructureIndex) -> None:
    before = base(index)
    changed = rule(
        "R-ONE",
        Predicate(field=mx(AMT), operator=Operator.ABSENT),
        when=Predicate(field=mx(CMONID), operator=Operator.EXISTS),
        severity=IssueSeverity.WARNING,
    )
    after = before.model_copy(update={"rules": (changed,)})
    assert kinds(before, after) == {
        PackChangeKind.ASSERTION_CHANGED,
        PackChangeKind.CONDITION_CHANGED,
        PackChangeKind.SEVERITY_CHANGED,
    }


def test_occurrence_scope_changes_are_visible_in_the_assertion_diff(
    index: StructureIndex,
) -> None:
    before = base(index)
    scoped = rule(
        "R-ONE",
        node(
            {
                "forEachOccurrence": {
                    "sequencePath": "E1",
                    "assert": {"field": {"format": "MX", "path": AMT}, "operator": "EXISTS"},
                }
            }
        ),
    )
    after = before.model_copy(update={"rules": (scoped,)})
    diff = diff_packs(before, after)
    assert kinds(before, after) == {PackChangeKind.ASSERTION_CHANGED}
    assert "forEachOccurrence" in diff.render()


def test_narrowing_a_code_set_is_reported(index: StructureIndex) -> None:
    before = base(index)
    after = before.model_copy(
        update={"code_restrictions": (restriction("C-ONE", TXCOND, ("NOMC",)),)}
    )
    assert PackChangeKind.ALLOWED_CODES_CHANGED in kinds(before, after)


def test_a_review_state_change_is_visible(index: StructureIndex) -> None:
    before = base(index)
    deferred = before.rules[0].model_copy(
        update={"review": RuleReview(status=RuleReviewStatus.REVIEW_REQUIRED)}
    )
    after = before.model_copy(update={"rules": (deferred,)})
    assert PackChangeKind.REVIEW_STATE_CHANGED in kinds(before, after)


def test_a_different_structure_target_is_visible(index: StructureIndex) -> None:
    before = base(index)
    after = pack(
        index,
        rules=before.rules,
        restrictions=before.code_restrictions,
        structure_checksum="sha256:" + "1" * 64,
    )
    assert PackChangeKind.STRUCTURE_TARGET_CHANGED in kinds(before, after)


def test_reworded_prose_is_reported_but_never_confused_with_a_behaviour_change(
    index: StructureIndex,
) -> None:
    from app.rule_engine.models import RuleFindingText

    before = base(index)
    reworded = before.rules[0].model_copy(
        update={
            "finding": RuleFindingText(
                message="Reworded, and carrying exactly the same authority as before: none.",
                suggestion="Correct the message and try again.",
            )
        }
    )
    after = before.model_copy(update={"rules": (reworded,)})
    changes = kinds(before, after)
    assert changes == {PackChangeKind.FINDING_TEXT_CHANGED}
    # The rule's identity is unchanged, because prose does not decide what a rule means.
    assert before.rules[0].body_hash() == reworded.body_hash()
