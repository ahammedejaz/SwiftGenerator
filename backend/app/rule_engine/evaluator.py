"""Deterministic evaluation of effective rules against a resolved message.

Pure by construction: no clock, no randomness, no I/O, no network, no model. The input is
the same resolved value set the composer writes, so a rule can never see something the
message does not contain, and the output is the platform's existing
:class:`ValidationIssue` — extended with rule provenance, never replaced by a parallel
error system.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.rule_engine.dsl import EvaluationInput, ValueBag, evaluate, failing_occurrences
from app.rule_engine.layers import (
    LAYER_LABEL,
    VALIDATION_LAYER,
    EffectiveRules,
    LayeredRestriction,
    LayeredRule,
)
from app.rule_engine.models import Evidence
from app.rule_engine.occurrences import OccurrenceIdentity, as_context
from app.studio.models import ValidationIssue, ValidationOccurrence


def source_reference(evidence: Sequence[Evidence]) -> str | None:
    """Identity and location of the evidence — never its text."""
    if not evidence:
        return None
    first = evidence[0]
    parts = [f"{first.source_id} {first.source_version}", first.segment_id]
    if first.heading:
        parts.append(first.heading)
    if first.page is not None:
        parts.append(f"page {first.page}")
    return " · ".join(parts)


def _occurrence_payload(
    occurrence: OccurrenceIdentity | None,
) -> ValidationOccurrence | None:
    if occurrence is None:
        return None
    return ValidationOccurrence(
        sequence_path=occurrence.sequence_path,
        occurrence=occurrence.occurrence,
        path=occurrence.display_path,
        lineage=list(occurrence.lineage),
    )


def _issue_from_rule(
    item: LayeredRule, bag: ValueBag, occurrence: OccurrenceIdentity | None = None
) -> ValidationIssue:
    rule = item.rule
    primary = item.compiled.primary
    current = next(iter(bag.get(primary.key, ())), None)
    return ValidationIssue(
        rule_id=rule.rule_id,
        severity=rule.severity,
        layer=VALIDATION_LAYER[item.layer],
        field=primary.display_name,
        location=primary.location,
        occurrence=_occurrence_payload(occurrence),
        message=rule.finding.message,
        suggestion=rule.finding.suggestion,
        current_value=current,
        rule_layer=LAYER_LABEL[item.layer],
        rule_pack_id=item.pack_id,
        source_reference=source_reference(rule.evidence),
        review_status=rule.review.status.value,
    )


def _issues_from_restriction(
    item: LayeredRestriction, bag: ValueBag
) -> list[ValidationIssue]:
    restriction = item.compiled.restriction
    allowed = set(restriction.codes)
    issues: list[ValidationIssue] = []
    for value in bag.get(item.field.key, ()):
        if not value.strip() or value in allowed:
            continue
        issues.append(
            ValidationIssue(
                rule_id=restriction.restriction_id,
                severity=restriction.severity,
                layer=VALIDATION_LAYER[item.layer],
                field=item.field.display_name,
                location=item.field.location,
                message=restriction.finding.message,
                suggestion=restriction.finding.suggestion,
                expected="One of: " + ", ".join(restriction.codes),
                current_value=value,
                rule_layer=LAYER_LABEL[item.layer],
                rule_pack_id=item.pack_id,
                source_reference=source_reference(restriction.evidence),
                review_status=restriction.review.status.value,
            )
        )
    return issues


def evaluate_rules(effective: EffectiveRules, bag: EvaluationInput) -> list[ValidationIssue]:
    """Every finding the installed rules produce, in layer order.

    Every layer's rules run. A higher layer never suppresses a lower one — it can only add
    findings — so a message that breaks both a market rule and a client rule is told about
    both, each naming the layer that produced it.
    """
    issues: list[ValidationIssue] = []
    context = as_context(bag)
    for item in effective.rules:
        rule = item.rule
        bindings = item.compiled.bindings
        if rule.when is not None and not evaluate(rule.when, context, bindings):
            continue
        if evaluate(rule.assert_, context, bindings):
            continue
        failed = failing_occurrences(rule.assert_, context, bindings)
        issues.append(_issue_from_rule(item, context.bag, failed[0] if failed else None))
    for restriction in effective.restrictions:
        issues.extend(_issues_from_restriction(restriction, context.bag))
    return issues
