"""Segment → two isolated passes → deterministic diff → refuter → checks → candidate.

Every step after the two model calls is deterministic code. The model's part is to read a
paragraph and propose a shape from a closed vocabulary; everything that decides whether
that proposal is coherent, resolvable, type-correct and non-contradictory is done here,
and everything that decides whether it is *true* is done by a human reading the evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.agents.errors import AiServiceError
from app.agents.providers.base import (
    ModelUsage,
    StructuredCompletionClient,
    StructuredCompletionRequest,
)
from app.knowledge.models import RuleLayer
from app.rule_engine import DSL_VERSION, RULE_ENGINE_VERSION
from app.rule_engine.compiler import structure_compatibility_for
from app.rule_engine.diagnostics import RuleFinding, RuleFindingCode, RuleFindingLog
from app.rule_engine.extraction import PROMPT_VERSION, SCHEMA_VERSION
from app.rule_engine.extraction.cache import ExtractionCache
from app.rule_engine.extraction.canonical import CanonicalCandidate, canonicalise
from app.rule_engine.extraction.compare import ComparisonResult, compare
from app.rule_engine.extraction.prompts import (
    EXTRACTION_SYSTEM_INSTRUCTIONS,
    REFUTER_SYSTEM_INSTRUCTIONS,
    extraction_user_content,
    refuter_user_content,
)
from app.rule_engine.extraction.provider import ExtractionModels
from app.rule_engine.extraction.schemas import (
    CandidateExtraction,
    CandidateRuleType,
    ExtractionDecision,
    Refutation,
    candidate_schema,
    refutation_schema,
)
from app.rule_engine.extraction.translate import check_candidate, translate
from app.rule_engine.models import (
    CodeRestriction,
    ExtractionAgreement,
    Rule,
    RulePack,
    RuleReview,
    RuleReviewStatus,
)
from app.rule_engine.refs import StructureIndex
from app.rule_engine.sources import IngestedSource, Segment
from app.studio.models import MessageFormat

ROLE_EXTRACTOR_A = "EXTRACTOR_A"
ROLE_EXTRACTOR_B = "EXTRACTOR_B"
ROLE_REFUTER = "REFUTER"


def fields_block(
    index: StructureIndex, format_: MessageFormat, message_type: str, limit: int
) -> tuple[str, bool]:
    """The structure metadata a pass needs to resolve a reference — and nothing else.

    Capped rather than unbounded: a very large message would otherwise dominate the
    request. Truncation is reported, never silent, because a rule about a field the pass
    was never shown is a rule it cannot find.
    """
    fields = index.fields(format_, message_type)
    truncated = len(fields) > limit
    lines = [
        " | ".join(
            [
                item.key,
                item.display_name,
                item.kind.value,
                str(item.max_occurs),
                ",".join(item.codes) if item.codes else "-",
            ]
        )
        for item in fields[:limit]
    ]
    return "\n".join(lines), truncated


@dataclass
class SegmentOutcome:
    segment: Segment
    agreement: ExtractionAgreement
    comparison: ComparisonResult
    refutation: Refutation | None = None
    accepted: tuple[Rule | CodeRestriction, ...] = ()
    findings: tuple[RuleFinding, ...] = ()
    no_rule_reasons: tuple[str, ...] = ()
    live_calls: int = 0
    cache_hits: int = 0
    tokens: int = 0


@dataclass
class ExtractionRun:
    source: IngestedSource
    format: MessageFormat
    message_type: str
    layer: RuleLayer
    profile_id: str | None
    models: ExtractionModels
    outcomes: list[SegmentOutcome] = field(default_factory=list)
    structure_truncated: bool = False

    @property
    def accepted(self) -> list[Rule | CodeRestriction]:
        return [item for outcome in self.outcomes for item in outcome.accepted]

    @property
    def findings(self) -> list[RuleFinding]:
        return [item for outcome in self.outcomes for item in outcome.findings]

    def metrics(self) -> dict[str, Any]:
        return {
            "segmentsProcessed": len(self.outcomes),
            "liveCalls": sum(item.live_calls for item in self.outcomes),
            "cacheHits": sum(item.cache_hits for item in self.outcomes),
            "tokensUsed": sum(item.tokens for item in self.outcomes),
            "candidatesAccepted": len(self.accepted),
            "candidatesRejected": len(self.findings),
            "agreement": {
                value.value: sum(
                    1 for item in self.outcomes if item.agreement is value
                )
                for value in ExtractionAgreement
            },
        }

    def candidate_pack(self, index: StructureIndex, *, pack_version: str = "v1") -> RulePack | None:
        """Everything that survived the checks, as a pack a reviewer can read and edit.

        Its review status is REVIEW_REQUIRED and every rule inside it is MACHINE_CHECKED.
        The registry loads neither, so writing this file changes nothing about a running
        system — which is the point.
        """
        accepted = self.accepted
        if not accepted:
            return None
        version = index.version(self.format, self.message_type)
        identity = version or self.message_type
        parts = [self.format.value, identity, self.layer.value]
        if self.profile_id:
            parts.append(self.profile_id)
        parts.append(pack_version)
        return RulePack(
            pack_id=":".join(parts),
            format=self.format,
            message_type=self.message_type,
            message_version=version,
            layer=self.layer,
            profile_id=self.profile_id,
            pack_version=pack_version,
            title=f"Candidate rules for {identity} from {self.source.bundle.title}",
            engine_version=RULE_ENGINE_VERSION,
            dsl_version=DSL_VERSION,
            structure_compatibility=structure_compatibility_for(
                index, self.format, self.message_type
            ),
            review=RuleReview(status=RuleReviewStatus.REVIEW_REQUIRED),
            sources=(self.source.reference(),),
            limitations=(
                "Machine-extracted candidates. Nothing here has been reviewed against the "
                "source by a person, and this file is not loaded at runtime.",
                "Two isolated extraction passes are not independent authorities; their "
                "agreement reduces review effort and establishes nothing.",
            ),
            rules=tuple(item for item in accepted if isinstance(item, Rule)),
            code_restrictions=tuple(
                item for item in accepted if isinstance(item, CodeRestriction)
            ),
        )


class RuleExtractionPipeline:
    def __init__(
        self,
        client: StructuredCompletionClient,
        index: StructureIndex,
        *,
        models: ExtractionModels,
        cache: ExtractionCache,
        max_fields: int = 400,
    ) -> None:
        self._client = client
        self._index = index
        self._models = models
        self._cache = cache
        self._max_fields = max_fields

    async def _call(
        self,
        *,
        role: str,
        model: str,
        system_prompt: str,
        user_content: str,
        schema_name: str,
        json_schema: dict[str, Any],
        source_checksum: str,
        segment_hash: str,
        structure_checksum: str,
    ) -> tuple[dict[str, Any], ModelUsage, bool]:
        """One model call, cached. Returns (payload, usage, was_a_cache_hit)."""
        key = self._cache.key(
            role=role,
            model=model,
            provider=type(self._client).__name__,
            source_checksum=source_checksum,
            segment_hash=segment_hash,
            structure_checksum=structure_checksum,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
        )
        cached = self._cache.get(key)
        if cached is not None:
            payload, usage = cached
            return payload, usage, True
        response = await self._client.complete(
            StructuredCompletionRequest(
                role=role,
                model=model,
                system_prompt=system_prompt,
                user_content=user_content,
                schema_name=schema_name,
                json_schema=json_schema,
            )
        )
        self._cache.put(key, response.payload, response.usage)
        return response.payload, response.usage, False

    async def run(
        self,
        source: IngestedSource,
        *,
        format_: MessageFormat,
        message_type: str,
        layer: RuleLayer = RuleLayer.BASE_STANDARD,
        profile_id: str | None = None,
    ) -> ExtractionRun:
        block, truncated = fields_block(
            self._index, format_, message_type, self._max_fields
        )
        structure_checksum = self._index.structure_checksum(format_, message_type)
        identity = self._index.version(format_, message_type) or message_type
        run = ExtractionRun(
            source=source,
            format=format_,
            message_type=message_type,
            layer=layer,
            profile_id=profile_id,
            models=self._models,
            structure_truncated=truncated,
        )
        if not source.bundle.external_model_processing_allowed():
            for segment in source.segments:
                log = RuleFindingLog()
                log.error(
                    RuleFindingCode.RULE_EXTRACTION_PRIVACY_BLOCKED,
                    f"{source.bundle.source_id} is not approved for external model processing.",
                    "Record sourceAllowsExternalModelProcessing and "
                    "providerApprovedForSourceClassification only after the operator has "
                    "approved this source and provider combination. Local ingestion and "
                    "segmentation remain available.",
                    subject=source.bundle.source_id,
                    location=segment.segment_id,
                )
                run.outcomes.append(
                    SegmentOutcome(
                        segment=segment,
                        agreement=ExtractionAgreement.NO_RULE,
                        comparison=ComparisonResult(
                            agreement=ExtractionAgreement.NO_RULE,
                            pairs=(),
                        ),
                        findings=tuple(log.findings),
                    )
                )
            return run
        for segment in source.segments:
            run.outcomes.append(
                await self._run_segment(
                    segment,
                    source=source,
                    format_=format_,
                    message_type=message_type,
                    identity=identity,
                    block=block,
                    structure_checksum=structure_checksum,
                )
            )
        return run

    async def _extract(
        self,
        *,
        role: str,
        model: str,
        user_content: str,
        source_checksum: str,
        segment_hash: str,
        structure_checksum: str,
        log: RuleFindingLog,
        subject: str,
    ) -> tuple[CandidateExtraction | None, ModelUsage, bool]:
        try:
            payload, usage, hit = await self._call(
                role=role,
                model=model,
                system_prompt=EXTRACTION_SYSTEM_INSTRUCTIONS,
                user_content=user_content,
                schema_name="rule_candidate_extraction",
                json_schema=candidate_schema(),
                source_checksum=source_checksum,
                segment_hash=segment_hash,
                structure_checksum=structure_checksum,
            )
        except AiServiceError as error:
            log.error(
                RuleFindingCode.RULE_EXTRACTION_FAILED,
                f"{role} did not answer: {error.code}.",
                "Retry when the provider is available. No rule is derived from a failed "
                "extraction, and nothing already installed is affected.",
                subject=subject,
            )
            return None, ModelUsage(), False
        try:
            return CandidateExtraction.model_validate(payload), usage, hit
        except ValidationError as validation_error:
            log.error(
                RuleFindingCode.RULE_EXTRACTION_SCHEMA_INVALID,
                f"{role} returned output the candidate schema rejects: "
                f"{'; '.join(item['msg'] for item in validation_error.errors()[:3])}.",
                "The answer is discarded. A model that cannot meet the schema cannot "
                "propose a rule.",
                subject=subject,
            )
            return None, usage, hit

    async def _run_segment(
        self,
        segment: Segment,
        *,
        source: IngestedSource,
        format_: MessageFormat,
        message_type: str,
        identity: str,
        block: str,
        structure_checksum: str,
    ) -> SegmentOutcome:
        log = RuleFindingLog()
        user_content = extraction_user_content(
            message_identity=identity,
            fields_block=block,
            segment_id=segment.segment_id,
            segment_heading=segment.heading,
            segment_text=segment.text,
        )
        live_calls = 0
        cache_hits = 0
        tokens = 0
        extractions: list[CandidateExtraction | None] = []
        for role, model in (
            (ROLE_EXTRACTOR_A, self._models.extractor_a),
            (ROLE_EXTRACTOR_B, self._models.extractor_b),
        ):
            result, usage, hit = await self._extract(
                role=role,
                model=model,
                user_content=user_content,
                source_checksum=source.checksum,
                segment_hash=segment.segment_hash,
                structure_checksum=structure_checksum,
                log=log,
                subject=segment.segment_id,
            )
            extractions.append(result)
            tokens += usage.total_tokens
            if hit:
                cache_hits += 1
            else:
                live_calls += 1

        first, second = extractions
        reasons = tuple(
            item.no_rule_reason
            for item in (first, second)
            if item is not None
            and item.decision is ExtractionDecision.NO_RULE_FOUND
            and item.no_rule_reason.strip()
        )
        canonical_a = _canonical(first, format_)
        canonical_b = _canonical(second, format_)
        comparison = compare(canonical_a, canonical_b)

        refutation: Refutation | None = None
        if _needs_refutation(comparison):
            refutation, usage, hit = await self._refute(
                segment=segment,
                identity=identity,
                block=block,
                comparison=comparison,
                first=first,
                second=second,
                source_checksum=source.checksum,
                structure_checksum=structure_checksum,
                log=log,
            )
            tokens += usage.total_tokens
            if hit:
                cache_hits += 1
            else:
                live_calls += 1

        accepted: list[Rule | CodeRestriction] = []
        for ordinal, pair in enumerate(comparison.pairs, start=1):
            # Where the passes read the same rule differently, *both* readings go forward
            # as separate candidates. Emitting one of them with the difference noted
            # underneath would still be choosing a side, and the source is the authority.
            readings: list[tuple[CanonicalCandidate, str]] = (
                [(pair.in_a, "A"), (pair.in_b, "B")]  # type: ignore[list-item]
                if pair.matched and pair.differences
                else [(pair.candidate, "")]
            )
            for candidate, variant in readings:
                item, findings = translate(
                    candidate,
                    format_=format_,
                    segment=segment,
                    bundle=source.bundle,
                    ordinal=ordinal,
                    variant=variant,
                    agreement=comparison.agreement,
                    extractor_models=(self._models.extractor_a, self._models.extractor_b),
                    refuter_model=self._models.refuter if refutation is not None else None,
                    refutation=refutation,
                )
                log.findings.extend(findings)
                if item is None:
                    continue
                problems = check_candidate(
                    item,
                    index=self._index,
                    format_=format_,
                    message_type=message_type,
                    source_reference=source.reference(),
                )
                if problems:
                    log.findings.extend(problems)
                    continue
                accepted.append(
                    item.model_copy(
                        update={
                            "review": RuleReview(status=RuleReviewStatus.MACHINE_CHECKED)
                        }
                    )
                )

        return SegmentOutcome(
            segment=segment,
            agreement=comparison.agreement,
            comparison=comparison,
            refutation=refutation,
            accepted=tuple(accepted),
            findings=tuple(log.findings),
            no_rule_reasons=reasons,
            live_calls=live_calls,
            cache_hits=cache_hits,
            tokens=tokens,
        )

    async def _refute(
        self,
        *,
        segment: Segment,
        identity: str,
        block: str,
        comparison: ComparisonResult,
        first: CandidateExtraction | None,
        second: CandidateExtraction | None,
        source_checksum: str,
        structure_checksum: str,
        log: RuleFindingLog,
    ) -> tuple[Refutation | None, ModelUsage, bool]:
        content = refuter_user_content(
            message_identity=identity,
            fields_block=block,
            segment_id=segment.segment_id,
            segment_text=segment.text,
            candidate_a=_dump(first),
            candidate_b=_dump(second),
            differences=comparison.render(),
        )
        try:
            payload, usage, hit = await self._call(
                role=ROLE_REFUTER,
                model=self._models.refuter,
                system_prompt=REFUTER_SYSTEM_INSTRUCTIONS,
                user_content=content,
                schema_name="rule_candidate_refutation",
                json_schema=refutation_schema(),
                source_checksum=source_checksum,
                segment_hash=segment.segment_hash,
                structure_checksum=structure_checksum,
            )
        except AiServiceError as error:
            log.warning(
                RuleFindingCode.RULE_EXTRACTION_FAILED,
                f"The refuter did not answer: {error.code}.",
                "The candidate still goes to review; it simply arrives without adversarial "
                "criticism attached.",
                subject=segment.segment_id,
            )
            return None, ModelUsage(), False
        try:
            return Refutation.model_validate(payload), usage, hit
        except ValidationError:
            log.warning(
                RuleFindingCode.RULE_EXTRACTION_SCHEMA_INVALID,
                "The refuter returned output the schema rejects.",
                "The candidate still goes to review, without criticism attached.",
                subject=segment.segment_id,
            )
            return None, usage, hit


def _canonical(
    extraction: CandidateExtraction | None, format_: MessageFormat
) -> list[CanonicalCandidate]:
    if extraction is None or extraction.decision is ExtractionDecision.NO_RULE_FOUND:
        return []
    return [canonicalise(item, format_) for item in extraction.candidates]


def _needs_refutation(comparison: ComparisonResult) -> bool:
    """Every non-trivial candidate is attacked before a human spends time on it."""
    if comparison.agreement is ExtractionAgreement.NO_RULE:
        return False
    if comparison.agreement is not ExtractionAgreement.AGREE:
        return True
    if len(comparison.pairs) != 1:
        return True
    candidate = comparison.pairs[0].candidate
    trivial = candidate.rule_type in {
        CandidateRuleType.REQUIRED,
        CandidateRuleType.FORBIDDEN,
    }
    return not (trivial and candidate.condition_field is None)


def _dump(extraction: CandidateExtraction | None) -> str:
    if extraction is None:
        return json.dumps({"decision": "EXTRACTION_FAILED"})
    return extraction.model_dump_json(by_alias=True, indent=1)
