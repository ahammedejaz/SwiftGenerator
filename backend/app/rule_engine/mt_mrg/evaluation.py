"""Proving a candidate rule behaves, without letting it anywhere near normal validation.

Candidate evaluation is a reviewer's bench, not a validation layer. It takes one compiled
candidate rule, a handful of synthetic values written the way the guide writes fields, and
reports whether the rule holds or is violated. Nothing here is reachable from the studio
service, the API or the browser: the runtime registry loads reviewed packs from the rules
directory, and a candidate is not in it.

The synthetic values are the point of the exercise. A rule that passes on a message the
source says is valid, and fails on one the source says is not, has been *demonstrated* —
which is still not the same as having been reviewed, but it is a great deal more than
having compiled.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.rule_engine.compiler import CompiledRule
from app.rule_engine.dsl import evaluate
from app.rule_engine.mt_mrg.pipeline import MrgReading
from app.rule_engine.mt_mrg.structure import MrgStructureIndex
from app.rule_engine.occurrences import (
    EvaluationContext,
    OccurrenceIdentity,
    OccurrenceLevel,
    OccurrenceValue,
)


class Expectation(StrEnum):
    #: The message satisfies the rule.
    HOLDS = "HOLDS"
    #: The message breaks the rule, and the rule is expected to say so.
    VIOLATED = "VIOLATED"


@dataclass(frozen=True)
class FieldValue:
    """One field written into a synthetic message, in the guide's own notation."""

    sequence_path: str
    tag: str
    qualifier: str | None
    value: str = "SYNTHETIC"
    #: Without ``occurrence``, how many consecutive occurrences carry it. With
    #: ``occurrence``, how many values are present inside that one occurrence.
    occurrences: int = 1
    #: Specific one-based local occurrence to place the value in.
    occurrence: int | None = None
    #: Optional parent lineage for nested-repeat tests, as ``(("E", 1),)``.
    parent_lineage: tuple[tuple[str, int], ...] = ()

    def describe(self) -> str:
        qualifier = f"::{self.qualifier}" if self.qualifier else ""
        suffix = f" ×{self.occurrences}" if self.occurrences != 1 else ""
        where = f" @{self.sequence_path}[{self.occurrence}]" if self.occurrence else ""
        return f"{self.sequence_path}:{self.tag}{qualifier}={self.value}{suffix}{where}"


@dataclass(frozen=True)
class CandidateCase:
    """One synthetic message, and what the source says should happen to it."""

    name: str
    message_type: str
    source_rule_id: str
    expectation: Expectation
    values: tuple[FieldValue, ...]
    #: Why the source says so, in the reviewer's words rather than the guide's.
    rationale: str = ""


@dataclass(frozen=True)
class CandidateResult:
    case: CandidateCase
    rule_id: str
    source_rule_id: str
    source_error_codes: tuple[str, ...]
    source_page: int
    standards_release: str
    observed: Expectation
    passed: bool
    detail: str = ""


def _matching_field_keys(index: MrgStructureIndex, item: FieldValue) -> tuple[str, ...]:
    keys: list[str] = []
    number = item.tag[:2]
    for field in index.mrg_fields:
        if field.sequence_path.upper() != item.sequence_path.upper():
            continue
        if field.tag not in {item.tag, number}:
            continue
        if field.qualifier not in {item.qualifier, None}:
            continue
        keys.append(field.key)
    return tuple(keys)


def _identity(index: MrgStructureIndex, item: FieldValue, occurrence: int) -> OccurrenceIdentity:
    supplied = {path.upper(): count for path, count in item.parent_lineage}
    ancestors: list[str] = []
    current = index.structure.sequence(item.sequence_path)
    while current is not None and current.parent_path:
        ancestors.append(current.parent_path)
        current = index.structure.sequence(current.parent_path)
    levels = [
        OccurrenceLevel(path, supplied.get(path.upper(), 1))
        for path in reversed(ancestors)
    ]
    levels.append(OccurrenceLevel(item.sequence_path, occurrence))
    return OccurrenceIdentity(tuple(levels))


def _expanded_occurrences(item: FieldValue) -> tuple[tuple[int, int], ...]:
    if item.occurrence is not None:
        return ((item.occurrence, item.occurrences),)
    return tuple((occurrence, 1) for occurrence in range(1, item.occurrences + 1))


def evaluation_context(
    index: MrgStructureIndex, values: tuple[FieldValue, ...]
) -> EvaluationContext:
    bag: dict[str, list[str]] = {}
    scoped: list[OccurrenceValue] = []
    for item in values:
        for local_occurrence, repeat_count in _expanded_occurrences(item):
            identity = _identity(index, item, local_occurrence)
            for key in _matching_field_keys(index, item):
                bag.setdefault(key, []).extend([item.value] * repeat_count)
                scoped.extend(
                    OccurrenceValue(key=key, value=item.value, occurrence=identity)
                    for _ in range(repeat_count)
                )
    return EvaluationContext(bag=bag, occurrence_values=tuple(scoped))


def value_bag(index: MrgStructureIndex, values: tuple[FieldValue, ...]) -> dict[str, list[str]]:
    """Turn fields written the guide's way into the bag the evaluator reads.

    Writing ``:95P::DEAG`` into E1 makes several references true at once: the field with
    that option, the field without one, and the field named with no qualifier at all. They
    are separate entries in the index precisely so a rule can be as narrow as the guide
    was, so a value has to reach every entry it genuinely satisfies — otherwise a rule
    would appear to fail on a message that does contain what it asks for.
    """
    return {key: list(values) for key, values in evaluation_context(index, values).bag.items()}


def evaluate_case(
    reading: MrgReading, case: CandidateCase
) -> CandidateResult | None:
    """Evaluate one case against the compiled candidate for its source rule."""
    if reading.compiled is None or reading.index is None:
        return None
    translation = reading.translation(case.source_rule_id)
    if translation is None:
        return None
    rule_id = translation.rule.canonical_rule_id
    compiled: CompiledRule | None = next(
        (item for item in reading.compiled.rules if item.rule.rule_id == rule_id), None
    )
    if compiled is None:
        return None
    context = evaluation_context(reading.index, case.values)
    rule = compiled.rule
    if rule.when is not None and not evaluate(rule.when, context, compiled.bindings):
        observed = Expectation.HOLDS
        detail = "The rule's condition is not met, so it imposes nothing."
    elif evaluate(rule.assert_, context, compiled.bindings):
        observed = Expectation.HOLDS
        detail = "The message satisfies the rule."
    else:
        observed = Expectation.VIOLATED
        detail = rule.finding.message
    return CandidateResult(
        case=case,
        rule_id=rule_id,
        source_rule_id=translation.rule.source_rule_id,
        source_error_codes=translation.rule.error_codes,
        source_page=translation.rule.first_page,
        standards_release=translation.rule.standards_release,
        observed=observed,
        passed=observed is case.expectation,
        detail=detail,
    )


@dataclass
class CandidateEvaluation:
    results: list[CandidateResult]
    skipped: list[CandidateCase]

    @property
    def passed(self) -> bool:
        return not self.skipped and all(item.passed for item in self.results)

    def render(self) -> str:
        lines = [
            "Candidate rule evaluation — reviewer mode, future-test release",
            "",
            "These rules are not installed and take no part in normal validation. The run",
            "proves behaviour against synthetic values; it does not review the rules.",
            "",
            f"{'Rule':34} {'Src':5} {'Err':6} {'Pg':4} {'Case':44} {'Expect':9} {'Got':9} Result",
        ]
        for item in self.results:
            lines.append(
                f"{item.rule_id:34.34} {item.source_rule_id:5.5} "
                f"{','.join(item.source_error_codes)[:6]:6} {item.source_page:<4} "
                f"{item.case.name:44.44} {item.case.expectation.value:9} "
                f"{item.observed.value:9} {'PASS' if item.passed else 'FAIL'}"
            )
        for case in self.skipped:
            lines.append(
                f"{'-':34} {case.source_rule_id:5.5} {'-':6} {'-':4} "
                f"{case.name:44.44} {case.expectation.value:9} {'SKIPPED':9} "
                "NO CANDIDATE"
            )
        passed = sum(1 for item in self.results if item.passed)
        lines += [
            "",
            f"  cases: {len(self.results)}   passed: {passed}   "
            f"failed: {len(self.results) - passed}   skipped: {len(self.skipped)}",
        ]
        return "\n".join(lines)


def run_cases(
    readings: dict[str, MrgReading], cases: tuple[CandidateCase, ...]
) -> CandidateEvaluation:
    results: list[CandidateResult] = []
    skipped: list[CandidateCase] = []
    for case in cases:
        reading = readings.get(case.message_type)
        result = evaluate_case(reading, case) if reading else None
        if result is None:
            skipped.append(case)
            continue
        results.append(result)
    return CandidateEvaluation(results=results, skipped=skipped)


# --------------------------------------------------------------------------------------
# The anchor proofs
# --------------------------------------------------------------------------------------

_DBNM = FieldValue("E", "22F", "DBNM", "VEND")
_DEAG = FieldValue("E1", "95P", "DEAG", "DEAGGB2LXXX")
_PSET = FieldValue("E1", "95P", "PSET", "PSETGB2LXXX")
_SETT_AMOUNT = FieldValue("E3", "19A", "SETT", "EUR1000,00")
_SETR_TRAD = FieldValue("E", "22F", "SETR", "TRAD")

#: Proofs for rules this reader translated, written from the source rules confirmed in the
#: MT540 and MT541 guides. Each case says what the *source* requires, so a case that fails
#: is either a defect in the translation or a change in the guide — both worth stopping for.
ANCHOR_CASES: tuple[CandidateCase, ...] = (
    # -- MT541 C2 (E92): a receive against payment must carry a settlement amount --------
    CandidateCase(
        name="settlement amount absent",
        message_type="MT541",
        source_rule_id="C2",
        expectation=Expectation.VIOLATED,
        values=(_SETR_TRAD, _DEAG, _PSET),
        rationale="C2 makes :19A::SETT mandatory in one occurrence of E3.",
    ),
    CandidateCase(
        name="settlement amount present",
        message_type="MT541",
        source_rule_id="C2",
        expectation=Expectation.HOLDS,
        values=(_SETR_TRAD, _DEAG, _PSET, _SETT_AMOUNT),
        rationale="One occurrence of E3 carries :19A::SETT.",
    ),
    # -- MT541 C6 / MT540 C5 (E91): no settlement database means naming both parties ------
    CandidateCase(
        name="DBNM absent, delivering agent missing",
        message_type="MT541",
        source_rule_id="C6",
        expectation=Expectation.VIOLATED,
        values=(_SETR_TRAD, _PSET, _SETT_AMOUNT),
        rationale="C6 requires :95a::DEAG when :22F::DBNM is absent.",
    ),
    CandidateCase(
        name="DBNM absent, place of settlement missing",
        message_type="MT541",
        source_rule_id="C6",
        expectation=Expectation.VIOLATED,
        values=(_SETR_TRAD, _DEAG, _SETT_AMOUNT),
        rationale="C6 requires :95a::PSET when :22F::DBNM is absent.",
    ),
    CandidateCase(
        name="DBNM absent, both parties present",
        message_type="MT541",
        source_rule_id="C6",
        expectation=Expectation.HOLDS,
        values=(_SETR_TRAD, _DEAG, _PSET, _SETT_AMOUNT),
        rationale="Both parties are named, which is what C6 asks for.",
    ),
    CandidateCase(
        name="DBNM present, rule does not apply",
        message_type="MT541",
        source_rule_id="C6",
        expectation=Expectation.HOLDS,
        values=(_SETR_TRAD, _DBNM, _SETT_AMOUNT),
        rationale="C6 is conditional on :22F::DBNM being absent.",
    ),
    CandidateCase(
        name="DBNM absent, delivering agent missing",
        message_type="MT540",
        source_rule_id="C5",
        expectation=Expectation.VIOLATED,
        values=(_SETR_TRAD, _PSET),
        rationale="MT540 C5 is the same requirement under its own number.",
    ),
    CandidateCase(
        name="DBNM absent, place of settlement missing",
        message_type="MT540",
        source_rule_id="C5",
        expectation=Expectation.VIOLATED,
        values=(_SETR_TRAD, _DEAG),
        rationale="MT540 C5 requires :95a::PSET when :22F::DBNM is absent.",
    ),
    CandidateCase(
        name="DBNM absent, both parties present",
        message_type="MT540",
        source_rule_id="C5",
        expectation=Expectation.HOLDS,
        values=(_SETR_TRAD, _DEAG, _PSET),
        rationale="Both parties are named.",
    ),
    # -- MT541 C11 / MT540 C10 (E70): a settlement database means naming the seller -------
    CandidateCase(
        name="DBNM present, seller missing",
        message_type="MT541",
        source_rule_id="C11",
        expectation=Expectation.VIOLATED,
        values=(_SETR_TRAD, _DBNM, _SETT_AMOUNT),
        rationale="C11 requires :95a::SELL when :22F::DBNM is present.",
    ),
    CandidateCase(
        name="DBNM present, seller named",
        message_type="MT541",
        source_rule_id="C11",
        expectation=Expectation.HOLDS,
        values=(
            _SETR_TRAD,
            _DBNM,
            _SETT_AMOUNT,
            FieldValue("E1", "95P", "SELL", "SELLGB2LXXX"),
        ),
        rationale="The seller is named.",
    ),
    # -- MT540 C18 / MT541 C20 (E73): the two network-fee fields exclude each other -------
    CandidateCase(
        name="network fee in both E3 and E4",
        message_type="MT540",
        source_rule_id="C18",
        expectation=Expectation.VIOLATED,
        values=(
            FieldValue("E3", "19A", "NTWK", "EUR5,00"),
            FieldValue("E4", "36D", "NTWK", "UNIT/5,"),
        ),
        rationale="C18 forbids :36D::NTWK in E4 when :19A::NTWK is in E3.",
    ),
    CandidateCase(
        name="network fee in E3 only",
        message_type="MT540",
        source_rule_id="C18",
        expectation=Expectation.HOLDS,
        values=(FieldValue("E3", "19A", "NTWK", "EUR5,00"),),
        rationale="Only one of the two fields is present.",
    ),
    CandidateCase(
        name="network fee in both E3 and E4",
        message_type="MT541",
        source_rule_id="C20",
        expectation=Expectation.VIOLATED,
        values=(
            FieldValue("E3", "19A", "NTWK", "EUR5,00"),
            FieldValue("E4", "36D", "NTWK", "UNIT/5,"),
        ),
        rationale="MT541 C20 is the same rule under its own number.",
    ),
    # -- MT541 C3 / MT540 C2 (E90): a linked total needs the current number ---------------
    CandidateCase(
        name="linked total without current number",
        message_type="MT541",
        source_rule_id="C3",
        expectation=Expectation.VIOLATED,
        values=(FieldValue("A", "99B", "TOSE", "3"),),
        rationale="C3 requires :99a::SETT once :99a::TOSE is present.",
    ),
    CandidateCase(
        name="linked total with current number",
        message_type="MT541",
        source_rule_id="C3",
        expectation=Expectation.HOLDS,
        values=(
            FieldValue("A", "99B", "TOSE", "3"),
            FieldValue("A", "99B", "SETT", "1"),
        ),
        rationale="Both counts are present.",
    ),
    # -- MT541 C8 / MT540 C7 (E08): a cancellation names exactly one previous reference ---
    CandidateCase(
        name="cancellation without a previous reference",
        message_type="MT541",
        source_rule_id="C8",
        expectation=Expectation.VIOLATED,
        values=(FieldValue("A", "23G", None, "CANC"),),
        rationale="C8 requires exactly one :20C::PREV when the function is CANC.",
    ),
    CandidateCase(
        name="cancellation with one previous reference",
        message_type="MT541",
        source_rule_id="C8",
        expectation=Expectation.HOLDS,
        values=(
            FieldValue("A", "23G", None, "CANC"),
            FieldValue("A1", "20C", "PREV", "PREVREF1"),
        ),
        rationale="Exactly one previous reference is present.",
    ),
    CandidateCase(
        name="cancellation with two previous references",
        message_type="MT541",
        source_rule_id="C8",
        expectation=Expectation.VIOLATED,
        values=(
            FieldValue("A", "23G", None, "CANC"),
            FieldValue("A1", "20C", "PREV", "PREVREF1", occurrences=2),
        ),
        rationale="C8 allows the reference in one and only one occurrence of A1.",
    ),
    CandidateCase(
        name="new message needs no previous reference",
        message_type="MT541",
        source_rule_id="C8",
        expectation=Expectation.HOLDS,
        values=(FieldValue("A", "23G", None, "NEWM"),),
        rationale="C8 applies only to a cancellation.",
    ),
    CandidateCase(
        name="cancellation with a subfunction still applies",
        message_type="MT541",
        source_rule_id="C8",
        expectation=Expectation.VIOLATED,
        values=(FieldValue("A", "23G", None, "CANC/DUPL"),),
        rationale=(
            "The function field carries an optional subfunction; the rule turns on the "
            "function, so CANC/DUPL is still a cancellation."
        ),
    ),
    # -- MT540 C1 / MT541 C1 (E87): an amount qualifier appears at most once ---------------
    CandidateCase(
        name="settlement amount repeated across E3 occurrences",
        message_type="MT541",
        source_rule_id="C1",
        expectation=Expectation.VIOLATED,
        values=(FieldValue("E3", "19A", "SETT", "EUR1000,00", occurrences=2),),
        rationale="C1 allows each listed amount in at most one occurrence of E3.",
    ),
    CandidateCase(
        name="settlement amount once",
        message_type="MT541",
        source_rule_id="C1",
        expectation=Expectation.HOLDS,
        values=(_SETT_AMOUNT,),
        rationale="One occurrence carries the amount.",
    ),
    # -- MT540 only: the book-value amount MT541 does not list ----------------------------
    CandidateCase(
        name="book value repeated across E3 occurrences",
        message_type="MT540",
        source_rule_id="C1",
        expectation=Expectation.VIOLATED,
        values=(FieldValue("E3", "19A", "BOOK", "EUR900,00", occurrences=2),),
        rationale=(
            "MT540 C1 lists :19A::BOOK among the amounts it constrains; the MT541 guide "
            "does not list it at all."
        ),
    ),
    # -- MT540 C8 / MT541 C9 (E52): PSET excludes account in the same E1 occurrence -----
    CandidateCase(
        name="PSET and account in different E1 occurrences",
        message_type="MT541",
        source_rule_id="C9",
        expectation=Expectation.HOLDS,
        values=(
            FieldValue("E1", "95P", "PSET", "PSETGB2LXXX", occurrence=1),
            FieldValue("E1", "97A", "SAFE", "SAFE-ACCOUNT", occurrence=2),
        ),
        rationale="The account is not in the E1 occurrence that carries PSET.",
    ),
    CandidateCase(
        name="PSET and account in same E1 occurrence",
        message_type="MT541",
        source_rule_id="C9",
        expectation=Expectation.VIOLATED,
        values=(
            FieldValue("E1", "95P", "PSET", "PSETGB2LXXX", occurrence=1),
            FieldValue("E1", "97A", "SAFE", "SAFE-ACCOUNT", occurrence=1),
        ),
        rationale="The same E1 occurrence carries both fields.",
    ),
    CandidateCase(
        name="only the PSET occurrence fails",
        message_type="MT541",
        source_rule_id="C9",
        expectation=Expectation.VIOLATED,
        values=(
            FieldValue("E1", "95P", "DEAG", "DEAGGB2LXXX", occurrence=1),
            FieldValue("E1", "95P", "PSET", "PSETGB2LXXX", occurrence=2),
            FieldValue("E1", "97A", "SAFE", "SAFE-ACCOUNT", occurrence=2),
        ),
        rationale="The unrelated E1 occurrence does not affect the failing PSET one.",
    ),
    CandidateCase(
        name="MT540 PSET and account in different E1 occurrences",
        message_type="MT540",
        source_rule_id="C8",
        expectation=Expectation.HOLDS,
        values=(
            FieldValue("E1", "95P", "PSET", "PSETGB2LXXX", occurrence=1),
            FieldValue("E1", "97A", "SAFE", "SAFE-ACCOUNT", occurrence=2),
        ),
        rationale="MT540 C8 is the same E52 same-occurrence rule under its own number.",
    ),
    CandidateCase(
        name="MT540 PSET and account in same E1 occurrence",
        message_type="MT540",
        source_rule_id="C8",
        expectation=Expectation.VIOLATED,
        values=(
            FieldValue("E1", "95P", "PSET", "PSETGB2LXXX", occurrence=1),
            FieldValue("E1", "97A", "SAFE", "SAFE-ACCOUNT", occurrence=1),
        ),
        rationale="MT540 C8 fails only when both fields share the same E1 occurrence.",
    ),
)
