"""Layering: how base, market and client rules combine — and where they contradict.

Precedence orders the layers for *reporting and narrowing*, never for suppression. A
higher layer may add restrictions; it may not quietly erase a lower one. Where two layers
genuinely disagree the engine refuses to choose: it reports ``RULE_OVERLAY_CONFLICT`` with
both rule identifiers and both evidence origins, at installation time rather than when
some tester eventually trips over the impossible profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.knowledge.models import RuleLayer
from app.rule_engine.compiler import CompiledRestriction, CompiledRule, CompiledRulePack
from app.rule_engine.diagnostics import (
    RuleEngineError,
    RuleFinding,
    RuleFindingCode,
    RuleFindingLog,
)
from app.rule_engine.dsl import (
    DATE_OPERATORS,
    AllOf,
    AtLeastOne,
    ExactlyOne,
    Operator,
    Predicate,
    Subject,
    walk,
)
from app.rule_engine.models import Rule
from app.rule_engine.refs import ResolvedFieldRef
from app.studio.models import MessageFormat, ValidationLayer

#: Base first, then each overlay in the order it may narrow the one before it.
LAYER_ORDER: tuple[RuleLayer, ...] = (
    RuleLayer.BASE_STANDARD,
    RuleLayer.MARKET_PRACTICE,
    RuleLayer.CLIENT_PROFILE,
)

#: How a rule layer is reported in the existing validation contract.
VALIDATION_LAYER: dict[RuleLayer, ValidationLayer] = {
    RuleLayer.BASE_STANDARD: ValidationLayer.BUSINESS_RULES,
    RuleLayer.MARKET_PRACTICE: ValidationLayer.MARKET_PRACTICE,
    RuleLayer.CLIENT_PROFILE: ValidationLayer.CLIENT_PROFILE,
}

#: What a reader is told a layer is, in words rather than in enum spelling.
LAYER_LABEL: dict[RuleLayer, str] = {
    RuleLayer.BASE_STANDARD: "Base business rule",
    RuleLayer.MARKET_PRACTICE: "Market practice rule",
    RuleLayer.CLIENT_PROFILE: "Client rule",
}


class RuleIntent(StrEnum):
    """The two shapes that can contradict each other across layers."""

    REQUIRES = "REQUIRES"
    FORBIDS = "FORBIDS"


def rule_intent(rule: Rule) -> tuple[RuleIntent, str] | None:
    """Classify an unconditional presence rule by inspecting its shape.

    Deterministic AST inspection — never a guess from the rule's prose, which has no
    authority. Anything more complicated than "this field must be present" or "this field
    must be absent" is deliberately left unclassified rather than approximated.
    """
    if rule.when is not None:
        return None
    node = rule.assert_
    if isinstance(node, Predicate) and node.subject is Subject.VALUE:
        if node.operator is Operator.EXISTS:
            return RuleIntent.REQUIRES, node.field.canonical()
        if node.operator is Operator.ABSENT:
            return RuleIntent.FORBIDS, node.field.canonical()
    if isinstance(node, AtLeastOne) and len(node.at_least_one) == 1:
        return RuleIntent.REQUIRES, node.at_least_one[0].canonical()
    return None


@dataclass(frozen=True)
class LayeredRule:
    layer: RuleLayer
    pack_id: str
    compiled: CompiledRule

    @property
    def rule(self) -> Rule:
        return self.compiled.rule


@dataclass(frozen=True)
class LayeredRestriction:
    layer: RuleLayer
    pack_id: str
    compiled: CompiledRestriction

    @property
    def field(self) -> ResolvedFieldRef:
        return self.compiled.field


@dataclass(frozen=True)
class EffectiveRules:
    """Everything that will be evaluated for one message under one profile."""

    format: MessageFormat
    message_type: str
    profile_id: str | None
    rules: tuple[LayeredRule, ...] = ()
    restrictions: tuple[LayeredRestriction, ...] = ()
    warnings: tuple[RuleFinding, ...] = ()

    @property
    def empty(self) -> bool:
        return not self.rules and not self.restrictions

    def layers_present(self) -> tuple[RuleLayer, ...]:
        seen = {item.layer for item in self.rules} | {item.layer for item in self.restrictions}
        return tuple(layer for layer in LAYER_ORDER if layer in seen)


def _analyse_presence(
    rules: list[LayeredRule], log: RuleFindingLog, subject: str
) -> dict[str, list[LayeredRule]]:
    """REQUIRES vs FORBIDS on the same field, wherever the two layers sit."""
    requires: dict[str, list[LayeredRule]] = {}
    forbids: dict[str, list[LayeredRule]] = {}
    for item in rules:
        classified = rule_intent(item.rule)
        if classified is None:
            continue
        intent, canonical = classified
        target = requires if intent is RuleIntent.REQUIRES else forbids
        target.setdefault(canonical, []).append(item)
    for canonical, requiring in requires.items():
        for forbidding in forbids.get(canonical, []):
            for requirer in requiring:
                name = requirer.compiled.bindings[canonical].display_name
                log.error(
                    RuleFindingCode.RULE_OVERLAY_CONFLICT,
                    f"{name} is required by {requirer.rule.rule_id} "
                    f"({LAYER_LABEL[requirer.layer]}) and forbidden by "
                    f"{forbidding.rule.rule_id} ({LAYER_LABEL[forbidding.layer]}).",
                    "No message can satisfy both. Correct one of them, or record why the "
                    "profile does not apply.",
                    subject=subject,
                    location=canonical,
                    related=(requirer.rule.rule_id, forbidding.rule.rule_id),
                )
    return forbids


def _analyse_code_narrowing(
    restrictions: list[LayeredRestriction], log: RuleFindingLog, subject: str
) -> None:
    """Each layer must narrow the set the layers beneath it left, never widen it."""
    by_field: dict[str, list[LayeredRestriction]] = {}
    for item in restrictions:
        by_field.setdefault(item.compiled.restriction.field.canonical(), []).append(item)
    for canonical, items in by_field.items():
        ordered = sorted(items, key=lambda entry: LAYER_ORDER.index(entry.layer))
        effective = set(ordered[0].field.codes)
        for item in ordered:
            proposed = set(item.compiled.restriction.codes)
            identifier = item.compiled.restriction.restriction_id
            if proposed <= effective:
                effective = proposed
                continue
            if not (proposed & effective):
                log.error(
                    RuleFindingCode.RULE_OVERLAY_CONFLICT,
                    f"{identifier} ({LAYER_LABEL[item.layer]}) allows only "
                    f"{', '.join(sorted(proposed))} for {item.field.display_name}, and the "
                    f"layers beneath it allow only {', '.join(sorted(effective))}. No value "
                    "satisfies both.",
                    "Correct one of the layers; the engine does not choose a winner.",
                    subject=subject,
                    location=canonical,
                    related=(identifier,),
                )
                return
            log.error(
                RuleFindingCode.RULE_OVERLAY_WIDENING,
                f"{identifier} ({LAYER_LABEL[item.layer]}) would allow "
                f"{', '.join(sorted(proposed - effective))} for {item.field.display_name}, "
                f"which the layers beneath it do not allow.",
                "An overlay may narrow what a lower layer permits; it may not widen it.",
                subject=subject,
                location=canonical,
                related=(identifier,),
            )
            return


def _analyse_groups(
    rules: list[LayeredRule],
    forbidden: dict[str, list[LayeredRule]],
    log: RuleFindingLog,
    subject: str,
) -> None:
    """A group operator whose candidates another layer forbids can never be satisfied."""
    for item in rules:
        for node in walk(item.rule.assert_):
            fields = (
                node.exactly_one
                if isinstance(node, ExactlyOne)
                else node.at_least_one
                if isinstance(node, AtLeastOne)
                else ()
            )
            if not fields:
                continue
            blocked = [ref for ref in fields if ref.canonical() in forbidden]
            if len(blocked) < len(fields):
                continue
            culprits = tuple(
                sorted(
                    {
                        rule.rule.rule_id
                        for ref in blocked
                        for rule in forbidden[ref.canonical()]
                    }
                )
            )
            log.error(
                RuleFindingCode.RULE_OVERLAY_UNSATISFIABLE,
                f"{item.rule.rule_id} ({LAYER_LABEL[item.layer]}) needs one of "
                f"{', '.join(ref.describe() for ref in fields)}, and every one of them is "
                "forbidden by another layer.",
                "Correct the layers so at least one candidate remains available.",
                subject=subject,
                location=item.rule.rule_id,
                related=(item.rule.rule_id, *culprits),
            )


def _analyse_self_contradiction(
    rules: list[LayeredRule], log: RuleFindingLog, subject: str
) -> None:
    """Conditions and assertions that can never hold, so the rule is dead or fatal."""
    for item in rules:
        for label, expression in (("condition", item.rule.when), ("assertion", item.rule.assert_)):
            if expression is None:
                continue
            for node in walk(expression):
                if not isinstance(node, AllOf):
                    continue
                present: set[str] = set()
                absent: set[str] = set()
                equals: dict[str, set[str]] = {}
                for child in node.all_of:
                    if not isinstance(child, Predicate) or child.subject is not Subject.VALUE:
                        continue
                    canonical = child.field.canonical()
                    if child.operator is Operator.EXISTS:
                        present.add(canonical)
                    elif child.operator is Operator.ABSENT:
                        absent.add(canonical)
                    elif child.operator is Operator.EQUALS and child.value is not None:
                        equals.setdefault(canonical, set()).add(child.value)
                for canonical in sorted(present & absent):
                    log.error(
                        RuleFindingCode.RULE_OVERLAY_UNSATISFIABLE,
                        f"The {label} of {item.rule.rule_id} requires "
                        f"{canonical} to be both present and absent.",
                        "Correct the rule; as written it can never hold.",
                        subject=subject,
                        location=item.rule.rule_id,
                        related=(item.rule.rule_id,),
                    )
                for canonical, values in equals.items():
                    binding = item.compiled.bindings.get(canonical)
                    if len(values) > 1 and binding is not None and binding.max_occurs == 1:
                        log.error(
                            RuleFindingCode.RULE_OVERLAY_UNSATISFIABLE,
                            f"The {label} of {item.rule.rule_id} requires "
                            f"{binding.display_name} to equal {' and '.join(sorted(values))} "
                            "at the same time.",
                            "Correct the rule; a single-occurrence field holds one value.",
                            subject=subject,
                            location=item.rule.rule_id,
                            related=(item.rule.rule_id,),
                        )


def _analyse_date_cycles(
    rules: list[LayeredRule], log: RuleFindingLog, subject: str
) -> None:
    """``X before Y`` in one layer and ``Y before X`` in another is unsatisfiable."""
    ordered: dict[tuple[str, str], LayeredRule] = {}
    for item in rules:
        if item.rule.when is not None:
            continue
        node = item.rule.assert_
        if not isinstance(node, Predicate) or node.other_field is None:
            continue
        if node.operator not in DATE_OPERATORS:
            continue
        strict = node.operator in {Operator.DATE_BEFORE, Operator.DATE_AFTER}
        if not strict:
            continue
        left, right = node.field.canonical(), node.other_field.canonical()
        if node.operator is Operator.DATE_AFTER:
            left, right = right, left
        opposite = ordered.get((right, left))
        if opposite is not None:
            log.error(
                RuleFindingCode.RULE_OVERLAY_UNSATISFIABLE,
                f"{item.rule.rule_id} ({LAYER_LABEL[item.layer]}) and "
                f"{opposite.rule.rule_id} ({LAYER_LABEL[opposite.layer]}) require each of "
                "two dates to come strictly before the other.",
                "Correct one of them.",
                subject=subject,
                location=item.rule.rule_id,
                related=(item.rule.rule_id, opposite.rule.rule_id),
            )
        ordered[(left, right)] = item


def build_effective(
    packs: list[CompiledRulePack],
    *,
    format_: MessageFormat,
    message_type: str,
    profile_id: str | None,
) -> EffectiveRules:
    """Combine packs into the set that will be evaluated, refusing an impossible set."""
    log = RuleFindingLog()
    subject = f"{format_}:{message_type}" + (f":{profile_id}" if profile_id else "")

    ordered_packs = sorted(packs, key=lambda item: LAYER_ORDER.index(item.pack.layer))
    rules = [
        LayeredRule(layer=pack.pack.layer, pack_id=pack.pack_id, compiled=rule)
        for pack in ordered_packs
        for rule in pack.rules
    ]
    restrictions = [
        LayeredRestriction(layer=pack.pack.layer, pack_id=pack.pack_id, compiled=restriction)
        for pack in ordered_packs
        for restriction in pack.restrictions
    ]

    identifiers = [item.rule.rule_id for item in rules] + [
        item.compiled.restriction.restriction_id for item in restrictions
    ]
    for identifier in sorted({item for item in identifiers if identifiers.count(item) > 1}):
        log.error(
            RuleFindingCode.RULE_ID_DUPLICATE,
            f"{identifier} is declared by more than one installed pack.",
            "Rule identifiers are unique across the effective stack; rename one.",
            subject=subject,
            location=identifier,
        )

    forbidden = _analyse_presence(rules, log, subject)
    _analyse_code_narrowing(restrictions, log, subject)
    _analyse_groups(rules, forbidden, log, subject)
    _analyse_self_contradiction(rules, log, subject)
    _analyse_date_cycles(rules, log, subject)

    if log.blocked:
        raise RuleEngineError(log.findings)
    return EffectiveRules(
        format=format_,
        message_type=message_type,
        profile_id=profile_id,
        rules=tuple(rules),
        restrictions=tuple(restrictions),
        warnings=tuple(
            [*(finding for pack in ordered_packs for finding in pack.warnings), *log.findings]
        ),
    )
