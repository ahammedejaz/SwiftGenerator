"""The deterministic bridge from a model's candidate to a rule the engine can run.

Nothing a model returns is trusted here. Every field identifier is resolved against the
installed structure, every shape is turned into the DSL by code, and the result is then
compiled by exactly the same compiler that guards an installed pack — so a candidate is
checked by the same rules a reviewed pack is, before a human ever reads it.
"""

from __future__ import annotations

from app.knowledge.models import RuleLayer
from app.rule_engine import DSL_VERSION, RULE_ENGINE_VERSION
from app.rule_engine.compiler import compile_pack, structure_compatibility_for
from app.rule_engine.diagnostics import (
    RuleEngineError,
    RuleFinding,
    RuleFindingCode,
    RuleFindingLog,
)
from app.rule_engine.dsl import (
    AllOf,
    AtLeastOne,
    AtMostOne,
    ExactlyOne,
    Expression,
    Operator,
    Predicate,
)
from app.rule_engine.extraction.canonical import CanonicalCandidate, parse_identifier
from app.rule_engine.extraction.schemas import (
    CandidateRuleType,
    CandidateSeverity,
    ConditionOperator,
    DateOrder,
    Refutation,
)
from app.rule_engine.models import (
    MAX_EXCERPT_CHARS,
    CodeRestriction,
    Evidence,
    ExtractionAgreement,
    ExtractionMetadata,
    ExtractionMethod,
    Rule,
    RuleFindingText,
    RulePack,
    RuleReview,
    RuleReviewStatus,
)
from app.rule_engine.refs import FieldRef, StructureIndex
from app.rule_engine.sources import Segment, SourceBundle
from app.studio.models import IssueSeverity, MessageFormat

_DATE_OPERATOR = {
    DateOrder.BEFORE: Operator.DATE_BEFORE,
    DateOrder.ON_OR_BEFORE: Operator.DATE_ON_OR_BEFORE,
    DateOrder.AFTER: Operator.DATE_AFTER,
    DateOrder.ON_OR_AFTER: Operator.DATE_ON_OR_AFTER,
}

_CONDITION_OPERATOR = {
    ConditionOperator.EQUALS: Operator.EQUALS,
    ConditionOperator.NOT_EQUALS: Operator.NOT_EQUALS,
    ConditionOperator.IN: Operator.IN,
    ConditionOperator.NOT_IN: Operator.NOT_IN,
    ConditionOperator.EXISTS: Operator.EXISTS,
    ConditionOperator.ABSENT: Operator.ABSENT,
}

#: How many targets each shape needs. A shape given the wrong number is a malformed
#: candidate, not something to be quietly repaired.
_TARGET_COUNT: dict[CandidateRuleType, tuple[int, int]] = {
    CandidateRuleType.REQUIRED: (1, 1),
    CandidateRuleType.FORBIDDEN: (1, 1),
    CandidateRuleType.REQUIRED_IF: (1, 6),
    CandidateRuleType.FORBIDDEN_IF: (1, 6),
    CandidateRuleType.CODE_SUBSET: (1, 1),
    CandidateRuleType.DATE_ORDER: (2, 2),
    CandidateRuleType.MUTUALLY_EXCLUSIVE: (2, 6),
    CandidateRuleType.AT_LEAST_ONE_OF: (1, 6),
    CandidateRuleType.EXACTLY_ONE_OF: (2, 6),
}


def rule_identifier(
    candidate: CanonicalCandidate, segment: Segment, ordinal: int, variant: str = ""
) -> str:
    """Deterministic, readable, and stable for the same source and segment.

    ``variant`` distinguishes the two readings of a pair the passes disagreed about, so
    both can go to review side by side instead of one being silently chosen.
    """
    tail = segment.segment_id.split("#", 1)[1]
    shape = candidate.rule_type.value.replace("_", "")
    suffix = f"-{variant}" if variant else ""
    return f"{segment.source_id}-{tail}-{shape}-{ordinal}{suffix}"


def _sentence(text: str, fallback: str) -> str:
    cleaned = " ".join(text.split())
    return cleaned if len(cleaned) >= 8 else fallback


def _title(text: str, fallback: str) -> str:
    cleaned = " ".join(text.split())
    return cleaned[:140] if len(cleaned) >= 4 else fallback


def _refs(
    identifiers: tuple[str, ...], format_: MessageFormat
) -> list[FieldRef] | None:
    refs: list[FieldRef] = []
    for canonical in identifiers:
        raw = canonical.split("|", 1)[1] if "|" in canonical else canonical
        ref = parse_identifier(raw, format_)
        if ref is None:
            return None
        refs.append(ref)
    return refs


def _condition(
    candidate: CanonicalCandidate, format_: MessageFormat, log: RuleFindingLog, subject: str
) -> Expression | None:
    if candidate.condition_field is None:
        return None
    operator = _CONDITION_OPERATOR.get(candidate.condition_operator)
    if operator is None:
        return None
    refs = _refs((candidate.condition_field,), format_)
    if refs is None:
        log.error(
            RuleFindingCode.RULE_REFERENCE_INVALID,
            f"The condition names {candidate.condition_field}, which is not a field "
            "identifier of this message.",
            "A candidate may only name fields supplied with the request.",
            subject=subject,
        )
        return None
    field = refs[0]
    if operator in {Operator.EXISTS, Operator.ABSENT}:
        return Predicate(field=field, operator=operator)
    values = candidate.condition_values
    if not values:
        log.error(
            RuleFindingCode.RULE_EXTRACTION_SCHEMA_INVALID,
            f"The condition uses {candidate.condition_operator} with no value.",
            "Supply the value the source states, or use EXISTS/ABSENT.",
            subject=subject,
        )
        return None
    if operator in {Operator.EQUALS, Operator.NOT_EQUALS}:
        if len(values) != 1:
            log.error(
                RuleFindingCode.RULE_EXTRACTION_SCHEMA_INVALID,
                f"The condition uses {candidate.condition_operator} with "
                f"{len(values)} values, so what the source means is not determined.",
                "Use IN or NOT_IN for a set of values. The candidate is not repaired "
                "automatically, because guessing which was meant would change the rule.",
                subject=subject,
            )
            return None
        return Predicate(field=field, operator=operator, value=values[0])
    return Predicate(field=field, operator=operator, values=values)


def _assertion(
    candidate: CanonicalCandidate,
    refs: list[FieldRef],
    log: RuleFindingLog,
    subject: str,
) -> Expression | None:
    match candidate.rule_type:
        case CandidateRuleType.REQUIRED:
            return Predicate(field=refs[0], operator=Operator.EXISTS)
        case CandidateRuleType.FORBIDDEN:
            return Predicate(field=refs[0], operator=Operator.ABSENT)
        case CandidateRuleType.REQUIRED_IF:
            parts = [Predicate(field=ref, operator=Operator.EXISTS) for ref in refs]
            return parts[0] if len(parts) == 1 else AllOf(all_of=tuple(parts))
        case CandidateRuleType.FORBIDDEN_IF:
            parts = [Predicate(field=ref, operator=Operator.ABSENT) for ref in refs]
            return parts[0] if len(parts) == 1 else AllOf(all_of=tuple(parts))
        case CandidateRuleType.DATE_ORDER:
            operator = _DATE_OPERATOR.get(candidate.date_order)
            if operator is None:
                log.error(
                    RuleFindingCode.RULE_EXTRACTION_SCHEMA_INVALID,
                    "A date-order rule was returned without an order.",
                    "State which date must come first.",
                    subject=subject,
                )
                return None
            return Predicate(field=refs[0], operator=operator, other_field=refs[1])
        case CandidateRuleType.MUTUALLY_EXCLUSIVE:
            return AtMostOne(at_most_one=tuple(refs))
        case CandidateRuleType.AT_LEAST_ONE_OF:
            return AtLeastOne(at_least_one=tuple(refs))
        case CandidateRuleType.EXACTLY_ONE_OF:
            return ExactlyOne(exactly_one=tuple(refs))
        case _:
            return None


def translate(
    candidate: CanonicalCandidate,
    *,
    format_: MessageFormat,
    segment: Segment,
    bundle: SourceBundle,
    ordinal: int,
    agreement: ExtractionAgreement,
    variant: str = "",
    extractor_models: tuple[str, ...] = (),
    refuter_model: str | None = None,
    refutation: Refutation | None = None,
) -> tuple[Rule | CodeRestriction | None, list[RuleFinding]]:
    """One candidate as a rule the engine could run, or nothing plus the reason."""
    log = RuleFindingLog()
    identifier = rule_identifier(candidate, segment, ordinal, variant)

    low, high = _TARGET_COUNT[candidate.rule_type]
    if not low <= len(candidate.targets) <= high:
        log.error(
            RuleFindingCode.RULE_EXTRACTION_SCHEMA_INVALID,
            f"{candidate.rule_type} names {len(candidate.targets)} field(s); it needs "
            f"between {low} and {high}.",
            "The candidate is rejected rather than repaired.",
            subject=identifier,
        )
        return None, log.findings

    refs = _refs(candidate.targets, format_)
    if refs is None:
        log.error(
            RuleFindingCode.RULE_REFERENCE_INVALID,
            f"{identifier} names a field identifier this message does not use: "
            f"{', '.join(candidate.targets)}.",
            "A candidate may only name fields supplied with the request.",
            subject=identifier,
        )
        return None, log.findings

    evidence = tuple(
        [segment.evidence(bundle, excerpt_limit=MAX_EXCERPT_CHARS)]
        + _extra_evidence(candidate, segment, bundle)
    )
    metadata = ExtractionMetadata(
        method=ExtractionMethod.ISOLATED_DUAL_EXTRACTION,
        agreement=agreement,
        extractor_models=extractor_models,
        refuter_model=refuter_model,
        prompt_version=_prompt_version(),
        schema_version=_schema_version(),
        refuter_objections=tuple(
            f"{item.kind.value}: {item.detail}"
            for item in (refutation.objections if refutation else ())
        ),
    )
    review = RuleReview(status=RuleReviewStatus.AI_CANDIDATE)
    severity = (
        IssueSeverity.ERROR
        if candidate.severity is CandidateSeverity.ERROR
        else IssueSeverity.WARNING
    )
    finding_text = RuleFindingText(
        message=_sentence(
            candidate.original.message,
            f"{identifier} was not satisfied by this message.",
        ),
        suggestion=_sentence(
            candidate.original.suggestion,
            "Read the cited source location and correct the message.",
        ),
    )

    if candidate.rule_type is CandidateRuleType.CODE_SUBSET:
        if not candidate.codes:
            log.error(
                RuleFindingCode.RULE_EXTRACTION_SCHEMA_INVALID,
                f"{identifier} restricts the codes of a field but lists none.",
                "List the codes the source permits.",
                subject=identifier,
            )
            return None, log.findings
        return (
            CodeRestriction(
                restriction_id=identifier,
                field=refs[0],
                codes=candidate.codes,
                finding=finding_text,
                evidence=evidence,
                review=review,
                severity=severity,
                extraction=metadata,
            ),
            log.findings,
        )

    condition = _condition(candidate, format_, log, identifier)
    if log.blocked:
        return None, log.findings
    if candidate.rule_type in {
        CandidateRuleType.REQUIRED_IF,
        CandidateRuleType.FORBIDDEN_IF,
    } and condition is None:
        log.error(
            RuleFindingCode.RULE_EXTRACTION_SCHEMA_INVALID,
            f"{identifier} is a conditional rule with no condition.",
            "State the condition the source gives, or use REQUIRED / FORBIDDEN.",
            subject=identifier,
        )
        return None, log.findings

    assertion = _assertion(candidate, refs, log, identifier)
    if assertion is None:
        return None, log.findings

    return (
        Rule(
            rule_id=identifier,
            title=_title(candidate.original.title, f"{candidate.rule_type} rule"),
            severity=severity,
            when=condition,
            assert_=assertion,
            finding=finding_text,
            evidence=evidence,
            review=review,
            extraction=metadata,
        ),
        log.findings,
    )


def _extra_evidence(
    candidate: CanonicalCandidate, segment: Segment, bundle: SourceBundle
) -> list[Evidence]:
    """Additional segments the pass cited. Only ones it was actually shown count."""
    del candidate, segment, bundle
    return []


def _prompt_version() -> str:
    from app.rule_engine.extraction import PROMPT_VERSION

    return PROMPT_VERSION


def _schema_version() -> str:
    from app.rule_engine.extraction import SCHEMA_VERSION

    return SCHEMA_VERSION


def check_candidate(
    item: Rule | CodeRestriction,
    *,
    index: StructureIndex,
    format_: MessageFormat,
    message_type: str,
    source_reference: object,
) -> list[RuleFinding]:
    """Run the real compiler over one candidate, in a pack of its own.

    Using the same compiler a reviewed pack goes through is the point: a candidate cannot
    look valid to a reviewer under weaker checks than the ones that will guard it later.
    """
    from app.rule_engine.models import SourceReference

    assert isinstance(source_reference, SourceReference)
    version = index.version(format_, message_type)
    pack = RulePack(
        pack_id=f"{format_.value}:{version or message_type}:BASE_STANDARD:v1",
        format=format_,
        message_type=message_type,
        message_version=version,
        layer=RuleLayer.BASE_STANDARD,
        pack_version="v1",
        title=f"Candidate check for {message_type}",
        engine_version=RULE_ENGINE_VERSION,
        dsl_version=DSL_VERSION,
        structure_compatibility=structure_compatibility_for(index, format_, message_type),
        review=RuleReview(status=RuleReviewStatus.AI_CANDIDATE),
        sources=(source_reference,),
        rules=(item,) if isinstance(item, Rule) else (),
        code_restrictions=(item,) if isinstance(item, CodeRestriction) else (),
    )
    try:
        compile_pack(pack, index, require_reviewed=False)
    except RuleEngineError as error:
        return error.findings
    return []
