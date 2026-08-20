"""The declarative rule language, and its pure evaluation.

Rules are data, never code. Every node below is a closed pydantic model, so an unknown
operator or an unknown key fails validation before anything can run, and there is no code
path anywhere that interprets a string as an expression. No ``eval``, no ``exec``, no
templating, no shell.

Evaluation semantics are spelled out rather than left to intuition, because silence here
is how a rule engine becomes unpredictable. Over the values a message actually contains:

* ``EXISTS`` is true when at least one non-empty occurrence is present; ``ABSENT`` is its
  negation.
* **Positive** operators (``EQUALS``, ``IN``, ``MATCHES``, numeric and date comparisons)
  are true when *some* present value satisfies them. With no values present they are
  **false**.
* **Negative** operators (``NOT_EQUALS``, ``NOT_IN``) are true when *every* present value
  satisfies them. With no values present they are **true** — which is what makes
  "this field must not be X" behave correctly when the field is simply not there.
* ``subject: COUNT`` compares the number of occurrences, which is always defined.
* A value that cannot be read as the operator's type makes that one comparison false and
  reports nothing extra: the FORMAT layer already reports malformed values, and a business
  rule must not report them a second time.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from functools import lru_cache
from typing import Union

from pydantic import Field, model_validator

from app.rule_engine.occurrences import EvaluationContext, OccurrenceIdentity, as_context
from app.rule_engine.refs import FieldRef, ResolvedFieldRef, RuleModel

#: A resolved message: field key -> the values present, in occurrence order.
ValueBag = Mapping[str, Sequence[str]]
#: A plain resolved message or the occurrence-aware internal projection of one.
EvaluationInput = ValueBag | EvaluationContext
#: Canonical field reference -> what the structure says about it.
Bindings = Mapping[str, ResolvedFieldRef]

MAX_PATTERN_LENGTH = 200
MAX_EXPRESSION_DEPTH = 12


class Subject(StrEnum):
    """What the operator compares: the field's values, or how many there are."""

    VALUE = "VALUE"
    COUNT = "COUNT"


class Operator(StrEnum):
    EXISTS = "EXISTS"
    ABSENT = "ABSENT"
    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    IN = "IN"
    NOT_IN = "NOT_IN"
    MATCHES = "MATCHES"
    GREATER_THAN = "GREATER_THAN"
    GREATER_OR_EQUAL = "GREATER_OR_EQUAL"
    LESS_THAN = "LESS_THAN"
    LESS_OR_EQUAL = "LESS_OR_EQUAL"
    DATE_BEFORE = "DATE_BEFORE"
    DATE_AFTER = "DATE_AFTER"
    DATE_ON_OR_BEFORE = "DATE_ON_OR_BEFORE"
    DATE_ON_OR_AFTER = "DATE_ON_OR_AFTER"


PRESENCE_OPERATORS = frozenset({Operator.EXISTS, Operator.ABSENT})
MEMBERSHIP_OPERATORS = frozenset({Operator.IN, Operator.NOT_IN})
NUMERIC_OPERATORS = frozenset(
    {
        Operator.GREATER_THAN,
        Operator.GREATER_OR_EQUAL,
        Operator.LESS_THAN,
        Operator.LESS_OR_EQUAL,
    }
)
DATE_OPERATORS = frozenset(
    {
        Operator.DATE_BEFORE,
        Operator.DATE_AFTER,
        Operator.DATE_ON_OR_BEFORE,
        Operator.DATE_ON_OR_AFTER,
    }
)
#: Operators whose truth is decided by *every* present value rather than by any one of
#: them, and which are therefore vacuously true when the field is absent.
UNIVERSAL_OPERATORS = frozenset({Operator.NOT_EQUALS, Operator.NOT_IN})


class Predicate(RuleModel):
    """One operator applied to one field."""

    field: FieldRef
    operator: Operator
    subject: Subject = Subject.VALUE
    value: str | None = Field(default=None, max_length=200)
    values: tuple[str, ...] = ()
    other_field: FieldRef | None = Field(default=None, alias="otherField")

    @model_validator(mode="after")
    def check_operands(self) -> Predicate:
        supplied = [
            name
            for name, present in (
                ("value", self.value is not None),
                ("values", bool(self.values)),
                ("otherField", self.other_field is not None),
            )
            if present
        ]
        if len(supplied) > 1:
            raise ValueError(f"{self.operator} takes one operand, not {', '.join(supplied)}")
        if self.operator in PRESENCE_OPERATORS:
            if supplied:
                raise ValueError(f"{self.operator} takes no operand")
            if self.subject is not Subject.VALUE:
                raise ValueError(f"{self.operator} does not apply to a count")
            return self
        if self.operator in MEMBERSHIP_OPERATORS:
            if not self.values:
                raise ValueError(f"{self.operator} needs a values list")
            if len(set(self.values)) != len(self.values):
                raise ValueError(f"{self.operator} lists a value twice")
            return self
        if self.values:
            raise ValueError(f"{self.operator} takes a single value, not a list")
        if self.operator is Operator.MATCHES:
            if self.value is None:
                raise ValueError("MATCHES needs a pattern")
            if self.other_field is not None:
                raise ValueError("MATCHES compares against a pattern, not another field")
            if len(self.value) > MAX_PATTERN_LENGTH:
                raise ValueError(f"A pattern may be at most {MAX_PATTERN_LENGTH} characters")
            return self
        if self.value is None and self.other_field is None:
            raise ValueError(f"{self.operator} needs a value or an otherField")
        if self.subject is Subject.COUNT and self.other_field is not None:
            raise ValueError("A count is compared against a number, not against a field")
        if self.subject is Subject.COUNT and self.value is not None:
            if not self.value.isdigit():
                raise ValueError("A count is compared against a whole number")
        return self

    def references(self) -> tuple[FieldRef, ...]:
        return (self.field, self.other_field) if self.other_field else (self.field,)


class AllOf(RuleModel):
    all_of: tuple[Expression, ...] = Field(alias="allOf", min_length=1)


class AnyOf(RuleModel):
    any_of: tuple[Expression, ...] = Field(alias="anyOf", min_length=1)


class Not(RuleModel):
    not_: Expression = Field(alias="not")


class Implication(RuleModel):
    if_: Expression = Field(alias="if")
    then: Expression


class Implies(RuleModel):
    implies: Implication


class OccurrenceAssertion(RuleModel):
    """Evaluate an assertion inside every occurrence of one structural scope."""

    sequence_path: str = Field(alias="sequencePath", min_length=1, max_length=80)
    assert_: Expression = Field(alias="assert")

    @model_validator(mode="after")
    def check_scope(self) -> OccurrenceAssertion:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*(/[A-Za-z][A-Za-z0-9]*)*", self.sequence_path):
            raise ValueError("An occurrence scope must be a slash-separated sequence path")
        return self


class ForEachOccurrence(RuleModel):
    for_each_occurrence: OccurrenceAssertion = Field(alias="forEachOccurrence")


class ExactlyOne(RuleModel):
    exactly_one: tuple[FieldRef, ...] = Field(alias="exactlyOne", min_length=2)


class AtLeastOne(RuleModel):
    at_least_one: tuple[FieldRef, ...] = Field(alias="atLeastOne", min_length=1)


class AtMostOne(RuleModel):
    at_most_one: tuple[FieldRef, ...] = Field(alias="atMostOne", min_length=2)


Expression = Union[  # noqa: UP007 - pydantic resolves the annotation at rebuild time
    Predicate,
    AllOf,
    AnyOf,
    Not,
    Implies,
    ForEachOccurrence,
    ExactlyOne,
    AtLeastOne,
    AtMostOne,
]

for _model in (AllOf, AnyOf, Not, Implication, Implies, OccurrenceAssertion, ForEachOccurrence):
    _model.model_rebuild()


# --------------------------------------------------------------------------------------
# Walking
# --------------------------------------------------------------------------------------


def walk(node: Expression) -> list[Expression]:
    """Every node of an expression, this one first."""
    found: list[Expression] = [node]
    match node:
        case AllOf():
            for child in node.all_of:
                found.extend(walk(child))
        case AnyOf():
            for child in node.any_of:
                found.extend(walk(child))
        case Not():
            found.extend(walk(node.not_))
        case Implies():
            found.extend(walk(node.implies.if_))
            found.extend(walk(node.implies.then))
        case ForEachOccurrence():
            found.extend(walk(node.for_each_occurrence.assert_))
        case _:
            pass
    return found


def depth(node: Expression) -> int:
    match node:
        case AllOf():
            return 1 + max(depth(child) for child in node.all_of)
        case AnyOf():
            return 1 + max(depth(child) for child in node.any_of)
        case Not():
            return 1 + depth(node.not_)
        case Implies():
            return 1 + max(depth(node.implies.if_), depth(node.implies.then))
        case ForEachOccurrence():
            return 1 + depth(node.for_each_occurrence.assert_)
        case _:
            return 1


def references(node: Expression) -> list[FieldRef]:
    """Every field an expression names, in document order, duplicates kept."""
    found: list[FieldRef] = []
    for item in walk(node):
        match item:
            case Predicate():
                found.extend(item.references())
            case ExactlyOne():
                found.extend(item.exactly_one)
            case AtLeastOne():
                found.extend(item.at_least_one)
            case AtMostOne():
                found.extend(item.at_most_one)
            case _:
                pass
    return found


# --------------------------------------------------------------------------------------
# Evaluation — pure: no clock, no randomness, no I/O, no model
# --------------------------------------------------------------------------------------


@lru_cache(maxsize=512)
def compiled_pattern(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


def _present(bag: ValueBag, key: str) -> list[str]:
    return [value for value in bag.get(key, ()) if value.strip()]


def _as_decimal(value: str) -> Decimal | None:
    try:
        return Decimal(value.replace(",", ""))
    except (InvalidOperation, ValueError, ArithmeticError):
        return None


def _as_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _as_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError:
        return None


def _compare_numbers(left: str, operator: Operator, right: str) -> bool:
    first, second = _as_decimal(left), _as_decimal(right)
    if first is None or second is None:
        return False
    match operator:
        case Operator.GREATER_THAN:
            return first > second
        case Operator.GREATER_OR_EQUAL:
            return first >= second
        case Operator.LESS_THAN:
            return first < second
        case _:
            return first <= second


def _order(first: date, second: date, operator: Operator) -> bool:
    match operator:
        case Operator.DATE_BEFORE:
            return first < second
        case Operator.DATE_AFTER:
            return first > second
        case Operator.DATE_ON_OR_BEFORE:
            return first <= second
        case _:
            return first >= second


def _compare_moments(left: str, operator: Operator, right: str, *, as_date: bool) -> bool:
    if as_date:
        first_day, second_day = _as_date(left), _as_date(right)
        if first_day is None or second_day is None:
            return False
        return _order(first_day, second_day, operator)
    first, second = _as_datetime(left), _as_datetime(right)
    if first is None or second is None:
        return False
    if (first.tzinfo is None) != (second.tzinfo is None):
        # Comparing an offset-aware moment with a naive one is not meaningful; the FORMAT
        # layer owns the malformed value, so this comparison simply fails.
        return False
    return _order(first, second, operator)


def _operand_values(
    predicate: Predicate, bag: ValueBag, bindings: Bindings
) -> list[str] | None:
    """The right-hand side, whether it is a literal or another field's values."""
    if predicate.other_field is not None:
        other = bindings.get(predicate.other_field.canonical())
        if other is None:
            return None
        return _present(bag, other.key)
    return [predicate.value] if predicate.value is not None else []


def _evaluate_predicate(predicate: Predicate, bag: ValueBag, bindings: Bindings) -> bool:
    binding = bindings.get(predicate.field.canonical())
    if binding is None:
        # Compilation refuses unresolved references, so this can only be a rule evaluated
        # against a message it does not target. Silence is the safe answer.
        return False
    present = _present(bag, binding.key)

    if predicate.operator is Operator.EXISTS:
        return bool(present)
    if predicate.operator is Operator.ABSENT:
        return not present

    if predicate.subject is Subject.COUNT:
        count = str(len(present))
        target = predicate.value or "0"
        match predicate.operator:
            case Operator.EQUALS:
                return len(present) == int(target)
            case Operator.NOT_EQUALS:
                return len(present) != int(target)
            case Operator.IN:
                return count in predicate.values
            case Operator.NOT_IN:
                return count not in predicate.values
            case op if op in NUMERIC_OPERATORS:
                return _compare_numbers(count, op, target)
            case _:
                return False

    operands = _operand_values(predicate, bag, bindings)
    if operands is None:
        return False

    universal = predicate.operator in UNIVERSAL_OPERATORS
    if not present:
        return universal

    def satisfied(value: str) -> bool:
        match predicate.operator:
            case Operator.EQUALS:
                return any(value == operand for operand in operands)
            case Operator.NOT_EQUALS:
                return all(value != operand for operand in operands)
            case Operator.IN:
                return value in predicate.values
            case Operator.NOT_IN:
                return value not in predicate.values
            case Operator.MATCHES:
                return bool(compiled_pattern(operands[0]).fullmatch(value)) if operands else False
            case op if op in NUMERIC_OPERATORS:
                return any(_compare_numbers(value, op, operand) for operand in operands)
            case op if op in DATE_OPERATORS:
                as_date = binding.kind.value == "DATE"
                return any(
                    _compare_moments(value, op, operand, as_date=as_date)
                    for operand in operands
                )
            case _:
                return False

    if universal:
        return all(satisfied(value) for value in present)
    return any(satisfied(value) for value in present)


def _present_count(fields: Sequence[FieldRef], bag: ValueBag, bindings: Bindings) -> int:
    total = 0
    for ref in fields:
        binding = bindings.get(ref.canonical())
        if binding is not None and _present(bag, binding.key):
            total += 1
    return total


def evaluate(node: Expression, bag: EvaluationInput, bindings: Bindings) -> bool:
    """Whether an expression holds for a resolved message. Pure and total."""
    context = as_context(bag)
    match node:
        case Predicate():
            return _evaluate_predicate(node, context.bag, bindings)
        case AllOf():
            return all(evaluate(child, context, bindings) for child in node.all_of)
        case AnyOf():
            return any(evaluate(child, context, bindings) for child in node.any_of)
        case Not():
            return not evaluate(node.not_, context, bindings)
        case Implies():
            if not evaluate(node.implies.if_, context, bindings):
                return True
            return evaluate(node.implies.then, context, bindings)
        case ForEachOccurrence():
            scope = node.for_each_occurrence.sequence_path
            return all(
                evaluate(
                    node.for_each_occurrence.assert_,
                    context.for_occurrence(occurrence),
                    bindings,
                )
                for occurrence in context.occurrences(scope)
            )
        case ExactlyOne():
            return _present_count(node.exactly_one, context.bag, bindings) == 1
        case AtLeastOne():
            return _present_count(node.at_least_one, context.bag, bindings) >= 1
        case AtMostOne():
            return _present_count(node.at_most_one, context.bag, bindings) <= 1
    raise TypeError(f"Unknown expression node: {type(node).__name__}")


def failing_occurrences(
    node: Expression, bag: EvaluationInput, bindings: Bindings
) -> tuple[OccurrenceIdentity, ...]:
    """Occurrence identities that make a scoped assertion fail.

    This is used only for finding metadata. Truth still comes from ``evaluate``.
    """
    context = as_context(bag)
    match node:
        case ForEachOccurrence():
            scope = node.for_each_occurrence.sequence_path
            return tuple(
                occurrence
                for occurrence in context.occurrences(scope)
                if not evaluate(
                    node.for_each_occurrence.assert_,
                    context.for_occurrence(occurrence),
                    bindings,
                )
            )
        case AllOf():
            found: list[OccurrenceIdentity] = []
            for child in node.all_of:
                found.extend(failing_occurrences(child, context, bindings))
            return tuple(dict.fromkeys(found))
        case Implies():
            if not evaluate(node.implies.if_, context, bindings):
                return ()
            return failing_occurrences(node.implies.then, context, bindings)
        case _:
            return ()
