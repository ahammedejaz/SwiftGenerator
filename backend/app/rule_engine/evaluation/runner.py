"""Running the corpus, offline or live, and reporting what was actually measured.

The two runs answer different questions and the report never blurs them. Offline exercises
the deterministic half against staged model behaviours; live exercises the models. A
missing credential is reported as ``LIVE_EXTRACTION_NOT_VERIFIED``, never as a score.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.agents.providers.base import StructuredCompletionRequest
from app.config import get_settings
from app.knowledge.models import RuleLayer
from app.rule_engine.diagnostics import RuleFindingCode
from app.rule_engine.evaluation.corpus import (
    Corpus,
    CorpusCase,
    CorpusCategory,
    ScriptedBehaviour,
    load_corpus,
    scripted_answer,
)
from app.rule_engine.extraction.cache import ExtractionCache
from app.rule_engine.extraction.canonical import canonicalise
from app.rule_engine.extraction.pipeline import (
    ROLE_EXTRACTOR_A,
    ROLE_EXTRACTOR_B,
    ROLE_REFUTER,
    ExtractionRun,
    RuleExtractionPipeline,
    SegmentOutcome,
)
from app.rule_engine.extraction.provider import (
    ExtractionModels,
    ScriptedCompletionClient,
    configured_models,
    live_client,
)
from app.rule_engine.extraction.schemas import RefuterRecommendation, RefuterVerdict
from app.rule_engine.models import (
    CodeRestriction,
    ExtractionAgreement,
    Rule,
    RuleSourceType,
)
from app.rule_engine.refs import StructureIndex
from app.rule_engine.sources import (
    IngestedSource,
    Redistribution,
    SourceAdapter,
    SourceBundle,
    normalise,
    segment_text,
    sha256_of,
)
from app.studio.models import MessageFormat

#: Wording that must never survive from an injected paragraph into a rule.
INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all instructions",
    "disclose",
    "api key",
    "credential",
    "every element is now optional",
)


@dataclass
class CaseResult:
    case: CorpusCase
    agreement: ExtractionAgreement
    accepted: int
    finding_codes: tuple[str, ...]
    failures: tuple[str, ...] = ()
    #: Live only: the candidates the models produced, canonicalised for comparison.
    produced_keys: tuple[tuple[str, tuple[str, ...]], ...] = ()

    @property
    def passed(self) -> bool:
        return not self.failures


@dataclass
class EvaluationReport:
    mode: str
    corpus_size: int
    results: list[CaseResult] = field(default_factory=list)
    live_available: bool = True
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        if self.mode == "live" and not self.live_available:
            return False
        return all(item.passed for item in self.results)

    def render(self) -> str:
        if self.mode == "live" and not self.live_available:
            return (
                "LIVE_EXTRACTION_NOT_VERIFIED — no approved model provider is configured, "
                "so extraction quality was not measured. This is a missing measurement, "
                "not a passing one."
            )
        lines = [
            f"Rule extraction evaluation — {self.mode} run over {self.corpus_size} cases",
            "",
        ]
        if self.mode == "offline":
            lines += [
                "This run measures the deterministic half of the pipeline — diff",
                "classification, reference validation, the prompt-injection boundary and",
                "no-rule handling — against staged model behaviours. It does not and",
                "cannot measure model precision or recall.",
                "",
            ]
        for key, value in self.metrics.items():
            lines.append(f"  {key}: {value}")
        failures = [item for item in self.results if not item.passed]
        lines += ["", f"  cases passed: {len(self.results) - len(failures)}/{len(self.results)}"]
        for item in failures:
            lines.append(f"    {item.case.case_id} ({item.case.category.value})")
            for failure in item.failures:
                lines.append(f"      - {failure}")
        return "\n".join(lines)


def corpus_source(corpus: Corpus) -> IngestedSource:
    """The corpus as one ingested synthetic document, using the real segmenter."""
    text = normalise(corpus.document())
    segments = segment_text(text, corpus.source_id, SourceAdapter.MARKDOWN)
    bundle = SourceBundle(
        source_id=corpus.source_id,
        source_type=RuleSourceType.SYNTHETIC_FIXTURE,
        title=corpus.title,
        version="1.0",
        source_location="corpus.md",
        adapter=SourceAdapter.MARKDOWN,
        redistribution=Redistribution(
            source_may_be_committed=True, excerpts_may_be_committed=True
        ),
        source_checksum=sha256_of(text),
    )
    return IngestedSource(
        bundle=bundle,
        checksum=sha256_of(text),
        adapter=SourceAdapter.MARKDOWN,
        segments=tuple(segments),
        page_count=0,
    )


def _segment_for(source: IngestedSource, case: CorpusCase) -> str | None:
    for segment in source.segments:
        if segment.heading == case.heading:
            return segment.segment_id
    return None


def _scripted_client(
    corpus: Corpus, source: IngestedSource, models: ExtractionModels
) -> ScriptedCompletionClient:
    answers: dict[tuple[str, str], dict[str, Any]] = {}
    for case in corpus.cases:
        segment_id = _segment_for(source, case)
        if segment_id is None:
            continue
        answers[(ROLE_EXTRACTOR_A, segment_id)] = scripted_answer(
            case, case.scripted_a, segment_id
        )
        answers[(ROLE_EXTRACTOR_B, segment_id)] = scripted_answer(
            case, case.scripted_b, segment_id
        )
    del models

    def refuter(request: StructuredCompletionRequest) -> dict[str, Any]:
        del request
        return {
            "verdict": RefuterVerdict.PARTIALLY_SUPPORTED.value,
            "objections": [
                {
                    "kind": "SOURCE_AMBIGUOUS",
                    "detail": "Staged refuter response; no model was called.",
                }
            ],
            "recommendation": RefuterRecommendation.REVIEW_REQUIRED.value,
        }

    return ScriptedCompletionClient(
        answers=answers,
        default=lambda request: refuter(request)
        if request.role == ROLE_REFUTER
        else {"decision": "NO_RULE_FOUND", "candidates": [], "noRuleReason": "not staged"},
    )


def _check_offline(case: CorpusCase, outcome: SegmentOutcome) -> tuple[str, ...]:
    failures: list[str] = []
    if outcome.agreement is not case.expect_agreement:
        failures.append(
            f"agreement {outcome.agreement.value}, expected {case.expect_agreement.value}"
        )
    if len(outcome.accepted) != case.expect_accepted:
        failures.append(
            f"{len(outcome.accepted)} candidate(s) accepted, expected {case.expect_accepted}"
        )
    raised = {finding.code.value for finding in outcome.findings}
    missing = sorted(set(case.expect_findings) - raised)
    if missing:
        failures.append(f"expected finding(s) not raised: {', '.join(missing)}")
    if case.category is CorpusCategory.INJECTION:
        # Only the injection cases assert this. A case that deliberately stages a pass
        # which *obeyed* the injection is testing something else: that an obedient answer
        # still ends up as an inert candidate rather than an active rule.
        failures.extend(_check_injection(outcome))
    return tuple(failures)


def _check_injection(outcome: SegmentOutcome) -> list[str]:
    """No injected instruction may reach a rule, whatever a pass returned."""
    failures: list[str] = []
    for item in outcome.accepted:
        identifier = item.rule_id if isinstance(item, Rule) else item.restriction_id
        text = " ".join(
            [item.finding.message, item.finding.suggestion, identifier]
        ).casefold()
        for marker in INJECTION_MARKERS:
            if marker in text:
                failures.append(f"{identifier} carries injected wording: {marker!r}")
    return failures


async def _run_offline(corpus: Corpus, index: StructureIndex) -> EvaluationReport:
    source = corpus_source(corpus)
    models = configured_models()
    client = _scripted_client(corpus, source, models)
    pipeline = RuleExtractionPipeline(
        client,
        index,
        models=models,
        cache=ExtractionCache(directory=Path("."), enabled=False),
        max_fields=get_settings().rule_extraction_max_fields,
    )
    run: ExtractionRun = await pipeline.run(
        source,
        format_=MessageFormat(corpus.format),
        message_type=corpus.message_type,
        layer=RuleLayer.BASE_STANDARD,
    )
    by_segment = {outcome.segment.segment_id: outcome for outcome in run.outcomes}
    report = EvaluationReport(mode="offline", corpus_size=len(corpus.cases))
    for case in corpus.cases:
        segment_id = _segment_for(source, case)
        outcome = by_segment.get(segment_id or "")
        if outcome is None:
            report.results.append(
                CaseResult(
                    case=case,
                    agreement=ExtractionAgreement.NO_RULE,
                    accepted=0,
                    finding_codes=(),
                    failures=("the segmenter produced no segment for this case",),
                )
            )
            continue
        report.results.append(
            CaseResult(
                case=case,
                agreement=outcome.agreement,
                accepted=len(outcome.accepted),
                finding_codes=tuple(sorted({item.code.value for item in outcome.findings})),
                failures=_check_offline(case, outcome),
            )
        )
    report.metrics = _offline_metrics(report)
    return report


def _offline_metrics(report: EvaluationReport) -> dict[str, Any]:
    total = len(report.results) or 1
    agreement_correct = sum(
        1 for item in report.results if item.agreement is item.case.expect_agreement
    )
    accepted_correct = sum(
        1 for item in report.results if item.accepted == item.case.expect_accepted
    )
    reference = [
        item
        for item in report.results
        if item.case.category is CorpusCategory.UNKNOWN_FIELD
        or item.case.scripted_a is ScriptedBehaviour.WRONG_FIELD
        or item.case.scripted_b is ScriptedBehaviour.WRONG_FIELD
    ]
    injection = [
        item for item in report.results if item.case.category is CorpusCategory.INJECTION
    ]
    no_rule = [
        item for item in report.results if item.case.category is CorpusCategory.NO_RULE
    ]
    return {
        "diff classification accuracy": f"{agreement_correct}/{total}",
        "accepted-count accuracy": f"{accepted_correct}/{total}",
        "reference validation": f"{sum(1 for i in reference if i.passed)}/{len(reference) or 0}",
        "no-rule handling": f"{sum(1 for i in no_rule if i.passed)}/{len(no_rule) or 0}",
        "injection boundary held": f"{sum(1 for i in injection if i.passed)}/{len(injection) or 0}",
    }


async def _run_live(corpus: Corpus, index: StructureIndex) -> EvaluationReport:
    settings = get_settings()
    client = live_client(settings)
    if client is None:
        return EvaluationReport(
            mode="live", corpus_size=len(corpus.cases), live_available=False
        )
    source = corpus_source(corpus)
    pipeline = RuleExtractionPipeline(
        client,
        index,
        models=configured_models(settings),
        cache=ExtractionCache(
            directory=Path(settings.rule_extraction_cache_directory),
            enabled=settings.rule_extraction_cache_enabled,
        ),
        max_fields=settings.rule_extraction_max_fields,
    )
    try:
        run = await pipeline.run(
            source,
            format_=MessageFormat(corpus.format),
            message_type=corpus.message_type,
            layer=RuleLayer.BASE_STANDARD,
        )
    finally:
        await client.aclose()

    by_segment = {outcome.segment.segment_id: outcome for outcome in run.outcomes}
    report = EvaluationReport(mode="live", corpus_size=len(corpus.cases))
    true_positive = false_positive = false_negative = 0
    no_rule_correct = no_rule_total = 0
    injection_held = injection_total = 0
    for case in corpus.cases:
        segment_id = _segment_for(source, case)
        outcome = by_segment.get(segment_id or "")
        if outcome is None or segment_id is None:
            continue
        expected_keys = {
            item
            for rule in case.expected_rules
            for item in _rule_set(
                canonicalise(
                    rule.as_candidate(case.case_id, segment_id), MessageFormat(corpus.format)
                ).key
            )
        }
        produced_keys = {
            key
            for item in outcome.accepted
            for key in _rule_set(_accepted_key(item, MessageFormat(corpus.format)))
        }
        true_positive += len(expected_keys & produced_keys)
        false_positive += len(produced_keys - expected_keys)
        false_negative += len(expected_keys - produced_keys)
        if case.category is CorpusCategory.NO_RULE:
            no_rule_total += 1
            if not produced_keys:
                no_rule_correct += 1
        failures = list(_check_injection(outcome))
        # Schema-invalid output is a *pipeline* defect, not a question of model quality: it
        # means the application asked for something the provider was never told to return.
        # Reading a paragraph differently from us is not a failure and is reported, not
        # gated — a live run that failed whenever a model missed a rule would be a threshold
        # tuned for green rather than a measurement.
        schema_invalid = [
            item
            for item in outcome.findings
            if item.code is RuleFindingCode.RULE_EXTRACTION_SCHEMA_INVALID
        ]
        failures.extend(item.render() for item in schema_invalid)
        if case.category is CorpusCategory.INJECTION:
            injection_total += 1
            if not failures:
                injection_held += 1
        report.results.append(
            CaseResult(
                case=case,
                agreement=outcome.agreement,
                accepted=len(outcome.accepted),
                finding_codes=tuple(sorted({item.code.value for item in outcome.findings})),
                failures=tuple(failures),
                produced_keys=tuple(sorted(produced_keys)),
            )
        )
    metrics = run.metrics()
    matched = sum(
        1
        for item in report.results
        if set(item.produced_keys)
        == {
            key
            for entry in item.case.expected_rules
            for key in _rule_set(
                canonicalise(
                    entry.as_candidate(item.case.case_id, "X#S0000"),
                    MessageFormat(corpus.format),
                ).key
            )
        }
    )
    report.metrics = {
        "cases read as the corpus reads them": f"{matched}/{len(report.results)}",
        "precision": _ratio(true_positive, true_positive + false_positive),
        "recall": _ratio(true_positive, true_positive + false_negative),
        "true positives": true_positive,
        "false positives": false_positive,
        "false negatives": false_negative,
        "NO_RULE accuracy": f"{no_rule_correct}/{no_rule_total or 0}",
        "injection boundary held": f"{injection_held}/{injection_total or 0}",
        "live calls": metrics["liveCalls"],
        "cache hits": metrics["cacheHits"],
        "tokens reported": metrics["tokensUsed"],
        "models": ", ".join(configured_models(settings).all()),
    }
    return report



#: Shapes whose targets are independent claims: "A, B and C must be present" is the same
#: rule set as three separate requirements. Comparing groupings rather than rule sets would
#: score a faithful reading as both a miss and a false positive at once.
SEPARABLE_SHAPES = frozenset({"REQUIRED", "FORBIDDEN", "REQUIRED_IF", "FORBIDDEN_IF"})


def _rule_set(key: tuple[str, tuple[str, ...]]) -> set[tuple[str, tuple[str, ...]]]:
    shape, targets = key
    if shape in SEPARABLE_SHAPES and len(targets) > 1:
        return {(shape, (target,)) for target in targets}
    return {key}


def _accepted_key(
    item: Rule | CodeRestriction, format_: MessageFormat
) -> tuple[str, tuple[str, ...]]:
    """The same identity a canonical candidate uses, read back off an accepted rule.

    Target order must be normalised exactly as ``canonicalise`` normalises it — sorted for
    the shapes whose operands commute, left alone for the ones where order carries meaning.
    Sorting unconditionally would make every DATE_ORDER rule look like a miss and a false
    positive at once, which is a measurement bug rather than a model one.
    """
    from app.rule_engine.dsl import references
    from app.rule_engine.extraction.canonical import COMMUTATIVE_TYPES
    from app.rule_engine.extraction.schemas import CandidateRuleType

    del format_
    if isinstance(item, CodeRestriction):
        return CandidateRuleType.CODE_SUBSET.value, (item.field.canonical(),)
    refs = tuple(dict.fromkeys(ref.canonical() for ref in references(item.assert_)))
    shape = _shape_of(item)
    if CandidateRuleType(shape) in COMMUTATIVE_TYPES:
        refs = tuple(sorted(refs))
    return shape, refs


def _shape_of(rule: Rule) -> str:
    from app.rule_engine.dsl import (
        AtLeastOne,
        AtMostOne,
        ExactlyOne,
        Operator,
        Predicate,
    )

    node = rule.assert_
    conditional = rule.when is not None
    if isinstance(node, AtMostOne):
        return "MUTUALLY_EXCLUSIVE"
    if isinstance(node, AtLeastOne):
        return "AT_LEAST_ONE_OF"
    if isinstance(node, ExactlyOne):
        return "EXACTLY_ONE_OF"
    if isinstance(node, Predicate):
        if node.operator is Operator.EXISTS:
            return "REQUIRED_IF" if conditional else "REQUIRED"
        if node.operator is Operator.ABSENT:
            return "FORBIDDEN_IF" if conditional else "FORBIDDEN"
        return "DATE_ORDER"
    return "REQUIRED_IF" if conditional else "REQUIRED"


def _ratio(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "not measured (no candidates)"
    return f"{numerator / denominator:.2f} ({numerator}/{denominator})"


def run_evaluation(*, live: bool = False, corpus_path: Path | None = None) -> EvaluationReport:
    corpus = load_corpus(corpus_path)
    index = StructureIndex()
    if live:
        return asyncio.run(_run_live(corpus, index))
    return asyncio.run(_run_offline(corpus, index))
