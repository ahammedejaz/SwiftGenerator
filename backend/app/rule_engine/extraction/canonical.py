"""Deterministic canonicalisation of extracted candidates.

Two passes can describe the same rule in different words. Before anything is compared,
every candidate is reduced to a normal form: field identifiers become the canonical
reference the structure resolves them to, commutative operand lists are sorted, codes and
condition values are sorted and de-duplicated, and prose is dropped from the comparison
entirely — the words a rule is explained in have no authority over what it means.

No model is used to compare candidates. Comparing two structures is what code is for.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.rule_engine.extraction.schemas import (
    CandidateRule,
    CandidateRuleType,
    CandidateSeverity,
    ConditionOperator,
    DateOrder,
)
from app.rule_engine.refs import FieldRef
from app.studio.models import MessageFormat

#: Rule shapes whose targets have no meaningful order, so the order must not make two
#: identical readings look like a disagreement.
COMMUTATIVE_TYPES = frozenset(
    {
        CandidateRuleType.MUTUALLY_EXCLUSIVE,
        CandidateRuleType.AT_LEAST_ONE_OF,
        CandidateRuleType.EXACTLY_ONE_OF,
        CandidateRuleType.REQUIRED_IF,
        CandidateRuleType.FORBIDDEN_IF,
    }
)


def parse_identifier(identifier: str, format_: MessageFormat) -> FieldRef | None:
    """Read one field identifier as the format already spells it. Never a new scheme."""
    text = identifier.strip()
    if not text:
        return None
    try:
        if format_ is MessageFormat.MX:
            return FieldRef(format=MessageFormat.MX, path=text)
        return FieldRef(format=MessageFormat.MT, field_id=text.upper())
    except ValueError:
        return None


def canonical_identifier(identifier: str, format_: MessageFormat) -> str:
    ref = parse_identifier(identifier, format_)
    return ref.canonical() if ref is not None else f"?|{identifier.strip()}"


@dataclass(frozen=True)
class CanonicalCandidate:
    """One candidate reduced to what actually decides its behaviour."""

    rule_type: CandidateRuleType
    targets: tuple[str, ...]
    condition_field: str | None
    condition_operator: ConditionOperator
    condition_values: tuple[str, ...]
    codes: tuple[str, ...]
    date_order: DateOrder
    severity: CandidateSeverity
    evidence_segment_ids: tuple[str, ...]
    #: The candidate as the model returned it, kept for the review package.
    original: CandidateRule

    @property
    def key(self) -> tuple[str, tuple[str, ...]]:
        """What makes two candidates the *same rule* rather than an agreeing pair."""
        return self.rule_type.value, self.targets

    def facets(self) -> dict[str, str]:
        """The comparable facets, named the way the diff reports them."""
        return {
            "ruleType": self.rule_type.value,
            "targets": ", ".join(self.targets),
            "condition": (
                f"{self.condition_field or '-'} {self.condition_operator.value}"
                f" {', '.join(self.condition_values)}".strip()
            ),
            "codes": ", ".join(self.codes),
            "dateOrder": self.date_order.value,
            "severity": self.severity.value,
            "evidence": ", ".join(self.evidence_segment_ids),
        }


def canonicalise(candidate: CandidateRule, format_: MessageFormat) -> CanonicalCandidate:
    targets = tuple(
        canonical_identifier(item, format_) for item in candidate.targets if item.strip()
    )
    if candidate.rule_type in COMMUTATIVE_TYPES:
        targets = tuple(sorted(dict.fromkeys(targets)))
    else:
        targets = tuple(dict.fromkeys(targets))
    condition_field = (
        canonical_identifier(candidate.condition_field, format_)
        if candidate.condition_field.strip()
        else None
    )
    operator = candidate.condition_operator
    if condition_field is None:
        operator = ConditionOperator.NONE
    values: tuple[str, ...] = ()
    if operator in {
        ConditionOperator.EQUALS,
        ConditionOperator.NOT_EQUALS,
        ConditionOperator.IN,
        ConditionOperator.NOT_IN,
    }:
        values = tuple(
            sorted({item.strip() for item in candidate.condition_values if item.strip()})
        )
    codes: tuple[str, ...] = ()
    if candidate.rule_type is CandidateRuleType.CODE_SUBSET:
        codes = tuple(sorted({item.strip() for item in candidate.codes if item.strip()}))
    order = (
        candidate.date_order
        if candidate.rule_type is CandidateRuleType.DATE_ORDER
        else DateOrder.NONE
    )
    return CanonicalCandidate(
        rule_type=candidate.rule_type,
        targets=targets,
        condition_field=condition_field,
        condition_operator=operator,
        condition_values=values,
        codes=codes,
        date_order=order,
        severity=candidate.severity,
        evidence_segment_ids=tuple(
            sorted({item.strip() for item in candidate.evidence_segment_ids if item.strip()})
        ),
        original=candidate,
    )
