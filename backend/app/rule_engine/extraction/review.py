"""The review package a person reads, and the four things they can do about it.

Deliberately a document and a command rather than an application. A reviewer UI — and the
review API that would come with it — is the first brick of the specification factory, and
this phase is not that phase. What a reviewer needs is the source location, both
extractions, what differed, what the refuter objected to, what the deterministic checks
said, and the rule as it would actually run.

Model reasoning is never shown, because it is never requested and never stored.
"""

from __future__ import annotations

from enum import StrEnum

import yaml

from app.rule_engine.extraction.pipeline import ExtractionRun, SegmentOutcome
from app.rule_engine.models import (
    CodeRestriction,
    Rule,
    RulePack,
    RuleReview,
    RuleReviewStatus,
)

#: The commit is the timestamp. A clock in a committed file makes byte-identical review of
#: the same decision impossible, which is the same reason compiled packs carry no dates.
REVIEWED_AT = "SOURCE_CONTROLLED"


class ReviewAction(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    DEFER = "DEFER"


def _reviewed(
    item: Rule | CodeRestriction, reviewer: str, candidate_hash: str | None
) -> RuleReview:
    return RuleReview(
        status=RuleReviewStatus.REVIEWED,
        reviewed_by=reviewer,
        reviewed_at=REVIEWED_AT,
        candidate_hash=candidate_hash or item.body_hash(),
        rule_hash=item.body_hash(),
    )


def apply_review(
    pack: RulePack,
    action: ReviewAction,
    *,
    reviewer: str = "",
    reason: str = "",
    candidate_hashes: dict[str, str] | None = None,
) -> RulePack:
    """The reviewed form of a candidate pack.

    ``candidate_hashes`` carries the hash of the candidate each rule came from, so an
    edit-and-approve records both what the model proposed and what the reviewer approved.
    When a rule was approved unchanged the two hashes are equal, which is itself the
    evidence that nothing was edited.
    """
    hashes = candidate_hashes or {}
    if action is ReviewAction.APPROVE:
        if not reviewer.strip():
            raise ValueError("Approving a rule records who approved it")
        return pack.model_copy(
            update={
                "review": RuleReview(
                    status=RuleReviewStatus.REVIEWED,
                    reviewed_by=reviewer,
                    reviewed_at=REVIEWED_AT,
                ),
                "rules": tuple(
                    item.model_copy(
                        update={
                            "review": _reviewed(
                                item, reviewer, hashes.get(item.rule_id)
                            )
                        }
                    )
                    for item in pack.rules
                ),
                "code_restrictions": tuple(
                    item.model_copy(
                        update={
                            "review": _reviewed(
                                item, reviewer, hashes.get(item.restriction_id)
                            )
                        }
                    )
                    for item in pack.code_restrictions
                ),
            }
        )
    status = (
        RuleReviewStatus.REJECTED
        if action is ReviewAction.REJECT
        else RuleReviewStatus.REVIEW_REQUIRED
    )
    review = RuleReview(
        status=status,
        reviewed_by=reviewer,
        reviewed_at=REVIEWED_AT if reviewer else "NOT_REVIEWED",
        rejection_reason=reason or None,
    )
    return pack.model_copy(
        update={
            "review": review,
            "rules": tuple(
                item.model_copy(update={"review": review}) for item in pack.rules
            ),
            "code_restrictions": tuple(
                item.model_copy(update={"review": review}) for item in pack.code_restrictions
            ),
        }
    )


def candidate_hashes(pack: RulePack) -> dict[str, str]:
    return {
        **{item.rule_id: item.body_hash() for item in pack.rules},
        **{item.restriction_id: item.body_hash() for item in pack.code_restrictions},
    }


def _prune_predicates(node: object) -> object:
    """Drop the noise from an expression node so a reviewer reads the rule, not the model.

    Only inside a predicate, and only where the value carries no information: a `subject`
    of VALUE and an empty `values` list say nothing an operator has not already said.
    Every field that could change behaviour is left exactly as it is.
    """
    if isinstance(node, list):
        return [_prune_predicates(item) for item in node]
    if not isinstance(node, dict):
        return node
    pruned = {key: _prune_predicates(value) for key, value in node.items()}
    if "operator" in pruned and "field" in pruned:
        if pruned.get("subject") == "VALUE":
            pruned.pop("subject")
        if pruned.get("values") == []:
            pruned.pop("values")
    return pruned


def _prune_sources(payload: dict[str, object]) -> None:
    sources = payload.get("sources")
    if not isinstance(sources, list):
        return
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in ("applicableMessageCategories", "messageIdentifiers"):
            if source.get(key) == []:
                source.pop(key)


def pack_yaml(pack: RulePack) -> str:
    """A pack as a reviewer reads and edits it: aliases, key order, no Python tags."""
    payload = pack.model_dump(mode="json", by_alias=True, exclude_none=True)
    _prune_sources(payload)
    for key in ("rules", "codeRestrictions"):
        if key in payload:
            payload[key] = _prune_predicates(payload[key])
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=96)


def _segment_section(outcome: SegmentOutcome, *, show_excerpt: bool) -> list[str]:
    segment = outcome.segment
    lines = [
        f"### {segment.segment_id}",
        "",
        f"- Heading: {segment.heading or '(none)'}",
        f"- Lines {segment.line_start}–{segment.line_end}"
        + (f", page {segment.page}" if segment.page else ""),
        f"- Segment hash: `{segment.segment_hash}`",
        f"- Agreement: **{outcome.agreement.value}**",
        "",
    ]
    if show_excerpt:
        lines += ["Evidence:", "", "> " + segment.text.replace("\n", "\n> "), ""]
    else:
        lines += [
            "Evidence is not reproduced here: the operator has not declared excerpts of "
            "this source redistributable. Open your own copy at the location above.",
            "",
        ]
    lines += ["Deterministic comparison:", "", "```", outcome.comparison.render(), "```", ""]
    if outcome.refutation is not None:
        lines += [
            f"Refuter verdict: **{outcome.refutation.verdict.value}** "
            f"(recommendation: {outcome.refutation.recommendation.value})",
            "",
        ]
        if outcome.refutation.objections:
            lines += [
                *(
                    f"- {item.kind.value}: {item.detail}"
                    for item in outcome.refutation.objections
                ),
                "",
            ]
        else:
            lines += ["- No objection raised.", ""]
    else:
        lines += ["Refuter: not invoked for this segment.", ""]
    if outcome.no_rule_reasons:
        lines += ["Reported as establishing no rule:", ""]
        lines += [f"- {reason}" for reason in outcome.no_rule_reasons]
        lines += [""]
    if outcome.findings:
        lines += ["Deterministic checks rejected:", ""]
        lines += [f"- {finding.render()}" for finding in outcome.findings]
        lines += [""]
    if outcome.accepted:
        lines += ["Candidate rules that passed every deterministic check:", ""]
        for item in outcome.accepted:
            identifier = (
                item.rule_id if isinstance(item, Rule) else item.restriction_id
            )
            lines += [f"- `{identifier}` — {item.finding.message}"]
        lines += [""]
    return lines


def review_package(run: ExtractionRun) -> str:
    """A deterministic Markdown artifact. Same run, same bytes."""
    bundle = run.source.bundle
    show_excerpt = bundle.redistribution.excerpts_may_be_committed
    metrics = run.metrics()
    lines = [
        f"# Candidate review — {run.message_type} from {bundle.source_id}",
        "",
        "Machine-extracted candidates. Nothing here is installed, nothing here affects "
        "validation, and nothing becomes a rule until a person approves it and the "
        "reviewed pack is merged.",
        "",
        "## Source",
        "",
        f"- Source: `{bundle.source_id}` — {bundle.title} ({bundle.version})",
        f"- Declared type: `{bundle.source_type.value}` — an operator declaration, not "
        "something the platform verified",
        f"- Location: `{bundle.source_location}`",
        f"- Checksum: `{run.source.checksum}`",
        f"- Excerpts may be committed: {show_excerpt}",
        "",
        "## Target",
        "",
        f"- Message: {run.format.value} {run.message_type}",
        f"- Layer: {run.layer.value}"
        + (f" · profile {run.profile_id}" if run.profile_id else ""),
        f"- Extractor A: `{run.models.extractor_a}`",
        f"- Extractor B: `{run.models.extractor_b}`",
        f"- Refuter: `{run.models.refuter}`",
        "",
        "The two extraction passes are **isolated calls**, not independent authorities: "
        "they may share a provider, a model family and training data. Their agreement "
        "reduces how much attention a candidate needs and establishes nothing.",
        "",
    ]
    if run.structure_truncated:
        lines += [
            "> The field list supplied to the passes was truncated, so a rule about a "
            "field beyond the cap could not have been found.",
            "",
        ]
    lines += [
        "## Run",
        "",
        f"- Segments processed: {metrics['segmentsProcessed']}",
        f"- Live model calls: {metrics['liveCalls']} · cache hits: {metrics['cacheHits']}",
        f"- Tokens reported by the provider: {metrics['tokensUsed']}",
        f"- Candidates accepted for review: {metrics['candidatesAccepted']} · "
        f"rejected by deterministic checks: {metrics['candidatesRejected']}",
        "",
        "## Segments",
        "",
    ]
    for outcome in run.outcomes:
        lines.extend(_segment_section(outcome, show_excerpt=show_excerpt))
    return "\n".join(lines).rstrip() + "\n"
