import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from time import monotonic
from typing import Any
from uuid import uuid4

from app.agents.audit import AiAuditEvent, AiAuditSink, AiAuditWriteError
from app.agents.budgets import DailyUsageBudget
from app.agents.cache import (
    AiCacheEntry,
    AiCacheNamespace,
    AiCachePersistenceError,
    AiResultCache,
    CacheKeyContext,
    CacheStampedeTimeout,
    PlaceholderNormalisation,
    canonicalise_payload,
    normalise_placeholders,
    restore_payload,
)
from app.agents.circuit_breaker import CircuitBreaker
from app.agents.decision import AiCallDecision, AiOperation, ai_call_decision_pipeline
from app.agents.errors import AiServiceError, ai_error
from app.agents.interpretation import rehydrate_value, validate_model_payload
from app.agents.preprocessing import sanitize_user_text
from app.agents.providers.base import (
    InterpretationModelRequest,
    InterpretationModelResponse,
    ModelUsage,
    StructuredModelClient,
)
from app.agents.schemas import PROMPT_VERSION, SCHEMA_VERSION
from app.agents.telemetry import AiTelemetry
from app.agents.usage import (
    AiInteractionEvent,
    AiInteractionSink,
    AiInteractionWriteError,
)
from app.config import Settings
from app.domain.enums import (
    AiProcessingSource,
    AiSource,
    CanonicalFieldPath,
    Direction,
    Lifecycle,
    PaymentType,
)
from app.domain.models import (
    AiHealthResponse,
    AiMetadata,
    ExtractedBusinessField,
    InterpretationConflict,
    InterpretedIntent,
    InterpretScenarioRequest,
    MessageResolution,
    MessageResolutionRequest,
    ScenarioInterpretation,
    SettlementScenario,
)
from app.domain.resolver import resolve_message_type
from app.profiles.loader import profiles

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _AttemptResult:
    response: InterpretationModelResponse
    parsed: Any
    schema_retries: int


@dataclass(frozen=True)
class _LiveInterpretationResult:
    interpretation: ScenarioInterpretation
    parsed: Any
    usage: ModelUsage
    escalated: bool
    escalation_reason: str | None
    attempt_count: int
    schema_retries: int


class AgentInterpretationService:
    def __init__(
        self,
        settings: Settings,
        client: StructuredModelClient | None,
        *,
        circuit: CircuitBreaker | None = None,
        budget: DailyUsageBudget | None = None,
        telemetry: AiTelemetry | None = None,
        audit_sink: AiAuditSink | None = None,
        cache: AiResultCache | None = None,
        interaction_sink: AiInteractionSink | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._circuit = circuit or CircuitBreaker(
            settings.openrouter_circuit_failure_threshold,
            settings.openrouter_circuit_cooldown_seconds,
        )
        self._budget = budget or DailyUsageBudget(
            settings.openrouter_daily_request_budget,
            settings.openrouter_daily_token_budget,
        )
        self._telemetry = telemetry or AiTelemetry()
        self._audit_sink = audit_sink
        self._cache = cache
        self._interaction_sink = interaction_sink

    @property
    def configured(self) -> bool:
        return self._client is not None and bool(getattr(self._client, "configured", True))

    async def interpret(
        self,
        request: InterpretScenarioRequest,
        *,
        tenant_partition: str = "PUBLIC_GUIDED",
    ) -> ScenarioInterpretation:
        request_id = str(uuid4())
        started = monotonic()
        await self._telemetry.begin(len(request.text))
        sanitised = None
        try:
            decision = ai_call_decision_pipeline.decide(AiOperation.INTENT_INTERPRETATION)
            if decision.decision != AiCallDecision.CACHE_THEN_MODEL:
                raise RuntimeError("Intent interpretation decision policy is misconfigured")
            if self._settings.ai_provider != "openrouter" or not self.configured:
                raise ai_error("AI_NOT_CONFIGURED", escalatable=False)
            sanitised = sanitize_user_text(
                request.text,
                self._settings.openrouter_max_input_chars,
            )
            normalisation = normalise_placeholders(sanitised)
            cache_context = self._cache_context(
                request, normalisation.canonical_text, tenant_partition
            )
            cache_id = (
                self._cache.key(cache_context)
                if self._cache is not None and self._cache.enabled
                else None
            )
            if cache_id is not None and self._cache is not None:
                try:
                    async with self._cache.singleflight(cache_id):
                        entry = await self._cache.get(cache_id, cache_context)
                        if entry is not None:
                            cached = await self._interpret_from_cache(
                                request_id,
                                request,
                                sanitised,
                                normalisation,
                                entry,
                                started,
                            )
                            if cached is not None:
                                return cached
                        live = await self._interpret_live(
                            request_id,
                            request,
                            sanitised,
                            started,
                        )
                        await self._store_cache_entry(
                            cache_id,
                            cache_context,
                            normalisation,
                            live,
                        )
                        return live.interpretation
                except CacheStampedeTimeout as exc:
                    raise ai_error("AI_PROVIDER_UNAVAILABLE", escalatable=False) from exc
                except AiCachePersistenceError:
                    logger.error("AI cache persistence unavailable; using live interpretation")
            live = await self._interpret_live(
                request_id,
                request,
                sanitised,
                started,
            )
            return live.interpretation
        except TimeoutError as exc:
            error = ai_error("AI_TIMEOUT", affects_circuit=True)
            await self._circuit.failure()
            await self._record_failure(error, started)
            await self._save_failure_audit(request_id, request, error, started)
            raise error from exc
        except AiServiceError as exc:
            if exc.affects_circuit:
                await self._circuit.failure()
            else:
                await self._circuit.ignored_failure()
            await self._record_failure(exc, started)
            await self._save_failure_audit(request_id, request, exc, started)
            raise
        finally:
            if sanitised is not None:
                sanitised.clear()

    async def _interpret_live(
        self,
        request_id: str,
        request: InterpretScenarioRequest,
        sanitised: Any,
        started: float,
    ) -> _LiveInterpretationResult:
        estimated_tokens_per_call = (
            len(sanitised.text) // 4 + self._settings.openrouter_max_output_tokens
        )
        maximum_model_calls = 2 + int(self._settings.openrouter_escalation_enabled)
        reservation = await self._budget.reserve(estimated_tokens_per_call * maximum_model_calls)
        await self._circuit.acquire()
        result = await asyncio.wait_for(
            self._interpret_with_escalation(request_id, request, sanitised),
            timeout=self._settings.openrouter_operation_timeout_seconds,
        )
        usage = result[1]
        await self._circuit.success()
        elapsed = round((monotonic() - started) * 1000)
        interpretation = self._to_interpretation(
            request,
            result[0],
            request_id=request_id,
            latency_ms=elapsed,
            usage=usage,
            escalated=result[2],
            escalation_reason=result[3],
            attempt_count=result[4],
            schema_retries=result[5],
            sanitised=sanitised,
            processing_source=AiProcessingSource.LIVE_API,
        )
        await self._budget.reconcile(reservation, usage.total_tokens)
        await self._telemetry.success(
            latency_ms=elapsed,
            escalated=result[2],
            schema_retries=result[5],
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            reported_cost=usage.reported_cost,
        )
        await self._save_audit(
            AiAuditEvent(
                request_id=request_id,
                scenario_id=interpretation.scenario.scenario_id,
                provider="openrouter",
                primary_model=self._settings.openrouter_primary_model,
                final_model=interpretation.ai.model,
                escalated=interpretation.ai.escalated,
                escalation_reason=interpretation.ai.escalation_reason,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                attempt_count=interpretation.ai.attempt_count,
                latency_ms=elapsed,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                reported_cost=usage.reported_cost,
                outcome_code="SUCCESS",
            )
        )
        await self._save_interaction(
            AiInteractionEvent(
                interaction_id=request_id,
                operation_type="INTENT_INTERPRETATION",
                source=AiProcessingSource.LIVE_API,
                provider="openrouter",
                model=interpretation.ai.model,
                escalated=interpretation.ai.escalated,
                cache_hit=False,
                cache_namespace=AiCacheNamespace.INTENT_INTERPRETATION.value,
                cache_entry_age_seconds=None,
                live_api_call_count=result[4],
                primary_call_count=max(1, result[4] - int(result[2])),
                escalation_call_count=int(result[2]),
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                reported_cost=usage.reported_cost,
                latency_ms=elapsed,
                tokens_avoided=0,
                calls_avoided=0,
                cost_avoided=None,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                knowledge_version=self._settings.ai_cache_knowledge_version,
                profile_version=profiles.get(request.profile_id).version,
                outcome_code="SUCCESS",
            )
        )
        return _LiveInterpretationResult(
            interpretation=interpretation,
            parsed=result[0],
            usage=usage,
            escalated=result[2],
            escalation_reason=result[3],
            attempt_count=result[4],
            schema_retries=result[5],
        )

    def _cache_context(
        self,
        request: InterpretScenarioRequest,
        canonical_text: str,
        tenant_partition: str,
    ) -> CacheKeyContext:
        profile = profiles.get(request.profile_id)
        scenario = request.current_scenario
        return CacheKeyContext(
            namespace=AiCacheNamespace.INTENT_INTERPRETATION,
            sanitised_input=canonical_text,
            canonical_context=_minimal_context(request),
            workflow_module="SETTLEMENT",
            message_type=(
                scenario.message_type.value
                if scenario is not None and scenario.message_type is not None
                else None
            ),
            profile_id=profile.profile_id,
            profile_version=profile.version,
            standards_release=profile.standards_release,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            knowledge_version=self._settings.ai_cache_knowledge_version,
            taxonomy_version=self._settings.ai_cache_taxonomy_version,
            primary_model=self._settings.openrouter_primary_model,
            model_settings={
                "maxOutputTokens": self._settings.openrouter_max_output_tokens,
                "confidenceThreshold": self._settings.openrouter_confidence_threshold,
                "requireParameters": self._settings.openrouter_require_parameters,
                "dataCollection": self._settings.openrouter_data_collection,
                "zdr": self._settings.openrouter_zdr_required,
            },
            tenant_partition=tenant_partition,
        )

    async def _interpret_from_cache(
        self,
        request_id: str,
        request: InterpretScenarioRequest,
        sanitised: Any,
        normalisation: PlaceholderNormalisation,
        entry: AiCacheEntry,
        started: float,
    ) -> ScenarioInterpretation | None:
        assert self._cache is not None
        try:
            restored = restore_payload(entry.result_payload, normalisation)
            parsed = validate_model_payload(restored, sanitised)
        except AiServiceError:
            await self._cache.invalidate(entry.cache_id)
            logger.warning("Rejected a corrupted or stale AI cache entry")
            return None
        elapsed = round((monotonic() - started) * 1000)
        interpretation = self._to_interpretation(
            request,
            parsed,
            request_id=request_id,
            latency_ms=elapsed,
            usage=ModelUsage(),
            escalated=entry.escalated,
            escalation_reason=entry.escalation_reason,
            attempt_count=0,
            schema_retries=0,
            sanitised=sanitised,
            processing_source=AiProcessingSource.CACHE,
            model_override=entry.model,
            cache_entry=entry,
        )
        await self._telemetry.cache_hit(
            latency_ms=elapsed,
            tokens_avoided=entry.usage.total_tokens,
            calls_avoided=1,
            cost_avoided=entry.usage.reported_cost,
        )
        await self._save_interaction(
            AiInteractionEvent(
                interaction_id=request_id,
                operation_type="INTENT_INTERPRETATION",
                source=AiProcessingSource.CACHE,
                provider="openrouter",
                model=entry.model,
                escalated=entry.escalated,
                cache_hit=True,
                cache_namespace=entry.namespace.value,
                cache_entry_age_seconds=entry.age_seconds,
                live_api_call_count=0,
                primary_call_count=0,
                escalation_call_count=0,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                reported_cost=None,
                latency_ms=elapsed,
                tokens_avoided=entry.usage.total_tokens,
                calls_avoided=1,
                cost_avoided=entry.usage.reported_cost,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                knowledge_version=self._settings.ai_cache_knowledge_version,
                profile_version=entry.profile_version,
                outcome_code="CACHE_HIT",
            )
        )
        return interpretation

    async def _store_cache_entry(
        self,
        cache_id: str,
        context: CacheKeyContext,
        normalisation: PlaceholderNormalisation,
        live: _LiveInterpretationResult,
    ) -> None:
        assert self._cache is not None
        payload = live.parsed.model_dump(mode="json", by_alias=True)
        entry = self._cache.make_entry(
            cache_id=cache_id,
            context=context,
            result_payload=canonicalise_payload(payload, normalisation),
            usage=live.usage,
            final_model=live.interpretation.ai.model or self._settings.openrouter_primary_model,
            escalated=live.escalated,
            escalation_reason=live.escalation_reason,
            attempt_count=live.attempt_count,
            schema_retries=live.schema_retries,
        )
        try:
            await self._cache.save(entry)
        except AiCachePersistenceError:
            logger.error("AI cache write failed; validated live result was not cached")

    async def _interpret_with_escalation(
        self,
        request_id: str,
        request: InterpretScenarioRequest,
        sanitised: Any,
    ) -> tuple[Any, ModelUsage, bool, str | None, int, int]:
        assert self._client is not None
        total_usage = ModelUsage()
        attempts = 0
        schema_retries = 0
        escalation_reason: str | None = None
        primary: _AttemptResult | None = None
        primary_error: AiServiceError | None = None
        try:
            primary = await self._call_and_validate(
                request_id,
                self._settings.openrouter_primary_model,
                request,
                sanitised,
            )
            attempts += primary.response.attempt_count
            total_usage = _add_usage(total_usage, primary.response.usage)
        except AiServiceError as exc:
            primary_error = exc
            attempts += max(1, exc.attempt_count)
            if not exc.escalatable:
                raise
            if exc.code == "AI_SCHEMA_VALIDATION_FAILED":
                schema_retries += 1
                try:
                    primary = await self._call_and_validate(
                        request_id,
                        self._settings.openrouter_primary_model,
                        request,
                        sanitised,
                        correction=True,
                    )
                    attempts += primary.response.attempt_count
                    total_usage = _add_usage(total_usage, primary.response.usage)
                except AiServiceError as retry_error:
                    primary_error = retry_error
                    attempts += max(1, retry_error.attempt_count)

        if primary_error is not None and not primary_error.escalatable:
            raise primary_error

        if primary is not None:
            escalation_reason = self._escalation_reason(primary.parsed, request, sanitised.text)
            if escalation_reason is None:
                return primary.parsed, total_usage, False, None, attempts, schema_retries
        elif primary_error is not None:
            escalation_reason = _primary_error_escalation_reason(primary_error)

        if not self._settings.openrouter_escalation_enabled:
            if primary_error is not None:
                raise primary_error
            assert primary is not None
            return primary.parsed, total_usage, False, None, attempts, schema_retries

        try:
            escalated = await self._call_and_validate(
                request_id,
                self._settings.openrouter_escalation_model,
                request,
                sanitised,
            )
        except AiServiceError as exc:
            raise AiServiceError.escalation_failure(
                primary_error,
                exc,
                attempts + max(1, exc.attempt_count),
            ) from exc
        attempts += escalated.response.attempt_count
        total_usage = _add_usage(total_usage, escalated.response.usage)
        if (
            _deterministic_conflict(escalated.parsed, sanitised.text)
            or (
                _has_mutually_contradictory_intent(sanitised.text)
                and not escalated.parsed.requires_clarification
            )
            or (
                escalated.parsed.confidence < self._settings.openrouter_confidence_threshold
                and not escalated.parsed.requires_clarification
                and not _deterministically_complete(escalated.parsed)
            )
        ):
            unsafe = ai_error(
                "AI_UNSAFE_RESPONSE",
                failure_paths=("$:escalationSemanticValidation",),
            )
            raise AiServiceError.escalation_failure(primary_error, unsafe, attempts)
        return (
            escalated.parsed,
            total_usage,
            True,
            escalation_reason,
            attempts,
            schema_retries,
        )

    async def _call_and_validate(
        self,
        request_id: str,
        model: str,
        request: InterpretScenarioRequest,
        sanitised: Any,
        *,
        correction: bool = False,
    ) -> _AttemptResult:
        assert self._client is not None
        response = await self._client.interpret(
            InterpretationModelRequest(
                request_id=request_id,
                model=model,
                sanitised_text=sanitised.text,
                minimal_context=_minimal_context(request),
                correction=correction,
            )
        )
        parsed = validate_model_payload(response.payload, sanitised)
        return _AttemptResult(response=response, parsed=parsed, schema_retries=int(correction))

    def _escalation_reason(
        self, parsed: Any, request: InterpretScenarioRequest, text: str
    ) -> str | None:
        if parsed.confidence < self._settings.openrouter_confidence_threshold:
            return "LOW_CONFIDENCE"
        if _has_mutually_contradictory_intent(text) or len(parsed.ambiguities) > 1:
            return "CONTRADICTORY_INTENT"
        if _is_complex_lifecycle(text):
            return "COMPLEX_LIFECYCLE_INTENT"
        conflict = _deterministic_conflict(parsed, text)
        if conflict:
            return "DETERMINISTIC_INTERPRETER_CONFLICT"
        return None

    def _to_interpretation(
        self,
        request: InterpretScenarioRequest,
        parsed: Any,
        *,
        request_id: str,
        latency_ms: int,
        usage: ModelUsage,
        escalated: bool,
        escalation_reason: str | None,
        attempt_count: int,
        schema_retries: int,
        sanitised: Any,
        processing_source: AiProcessingSource = AiProcessingSource.LIVE_API,
        model_override: str | None = None,
        cache_entry: AiCacheEntry | None = None,
    ) -> ScenarioInterpretation:
        scenario = (
            request.current_scenario.model_copy(deep=True)
            if request.current_scenario
            else SettlementScenario(
                scenario_id=f"GUIDED-{uuid4().hex[:8].upper()}",
                profile_id=request.profile_id,
                synthetic_data=True,
            )
        )
        scenario.profile_id = request.profile_id
        conflicts: list[InterpretationConflict] = []
        confirmed = set(request.confirmed_fields)
        intent_values = {
            CanonicalFieldPath.LIFECYCLE: parsed.intent.lifecycle,
            CanonicalFieldPath.DIRECTION: parsed.intent.direction,
            CanonicalFieldPath.PAYMENT_TYPE: parsed.intent.payment_type,
            CanonicalFieldPath.FUNCTION: parsed.intent.function,
            CanonicalFieldPath.TRANSACTION_TYPE: parsed.intent.transaction_type,
        }
        for path, value in intent_values.items():
            if value is not None:
                _merge_value(scenario, path, value, confirmed, conflicts)

        extracted_models: list[ExtractedBusinessField] = []
        for extracted in parsed.extracted_fields:
            value = rehydrate_value(extracted, sanitised)
            canonical_path = CanonicalFieldPath(extracted.field_path.value)
            typed_value = _typed_value(canonical_path, value)
            _merge_value(scenario, canonical_path, typed_value, confirmed, conflicts)
            extracted_models.append(
                ExtractedBusinessField(
                    field_path=canonical_path,
                    value=value,
                    source=extracted.source.value,
                    evidence_start=extracted.evidence_start,
                    evidence_end=extracted.evidence_end,
                    placeholder_id=extracted.placeholder_id,
                )
            )

        if request.current_scenario is None and parsed.intent.lifecycle is None:
            resolution = MessageResolution(
                resolved_message_type=None,
                explanation=(
                    "Instruction, confirmation, or status intent is needed before choosing "
                    "a message type."
                ),
                missing_decision_information=["lifecycle"],
                confidence="INCOMPLETE",
            )
        else:
            resolution = resolve_message_type(
                MessageResolutionRequest(
                    lifecycle=scenario.lifecycle,
                    direction=scenario.direction,
                    payment_type=scenario.payment_type,
                )
            )
        scenario.message_type = resolution.resolved_message_type
        inferred = {item.value for item in parsed.intent.inferred_fields}
        requires_confirmation = bool(inferred or conflicts or parsed.requires_clarification)
        missing_decisions = list(
            dict.fromkeys(
                [
                    *[item.value for item in parsed.missing_decisions],
                    *resolution.missing_decision_information,
                ]
            )
        )
        return ScenarioInterpretation(
            scenario=scenario,
            resolution=resolution,
            detected_fields=[
                *[path.value for path, value in intent_values.items() if value is not None],
                *[item.field_path.value for item in parsed.extracted_fields],
            ],
            explanation=parsed.interpretation_summary,
            requires_business_confirmation=requires_confirmation,
            intent=InterpretedIntent(
                lifecycle=parsed.intent.lifecycle,
                direction=parsed.intent.direction,
                payment_type=parsed.intent.payment_type,
                transaction_type=parsed.intent.transaction_type,
                function=parsed.intent.function,
                response_action=parsed.intent.response_action,
                inferred_fields=sorted(inferred),
            ),
            extracted_fields=extracted_models,
            ambiguities=parsed.ambiguities,
            missing_decisions=missing_decisions,
            conflicts=conflicts,
            confidence=parsed.confidence,
            requires_clarification=(requires_confirmation or bool(missing_decisions)),
            ai=AiMetadata(
                used=True,
                provider=AiSource.OPENROUTER,
                model=(
                    model_override
                    or (
                        self._settings.openrouter_escalation_model
                        if escalated
                        else self._settings.openrouter_primary_model
                    )
                ),
                primary_model=self._settings.openrouter_primary_model,
                escalated=escalated,
                escalation_reason=escalation_reason,
                request_id=request_id,
                latency_ms=latency_ms,
                attempt_count=attempt_count,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                reported_cost=usage.reported_cost,
                outcome_code="SUCCESS",
                processing_source=processing_source,
                api_calls=(
                    attempt_count if processing_source == AiProcessingSource.LIVE_API else 0
                ),
                cache_hit=processing_source == AiProcessingSource.CACHE,
                cache_namespace=(cache_entry.namespace.value if cache_entry is not None else None),
                cache_age_seconds=(cache_entry.age_seconds if cache_entry is not None else None),
                original_cached_total_tokens=(
                    cache_entry.usage.total_tokens if cache_entry is not None else 0
                ),
                tokens_avoided=(cache_entry.usage.total_tokens if cache_entry is not None else 0),
                calls_avoided=1 if cache_entry is not None else 0,
                cost_avoided=(cache_entry.usage.reported_cost if cache_entry is not None else None),
                knowledge_version=self._settings.ai_cache_knowledge_version,
            ),
        )

    async def health(self) -> AiHealthResponse:
        return AiHealthResponse(
            configured=self.configured,
            mode=self._settings.ai_mode,
            provider=self._settings.ai_provider,
            primary_model=self._settings.openrouter_primary_model,
            escalation_model=self._settings.openrouter_escalation_model,
            escalation_enabled=self._settings.openrouter_escalation_enabled,
            circuit_state=self._circuit.state,
            last_successful_call_at=self._telemetry.last_successful_call_at,
            privacy_enforcement_enabled=(
                self._settings.openrouter_require_parameters
                and self._settings.openrouter_data_collection == "deny"
                and self._settings.openrouter_zdr_required
            ),
            require_parameters=self._settings.openrouter_require_parameters,
            data_collection=self._settings.openrouter_data_collection,
            zdr_required=self._settings.openrouter_zdr_required,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            telemetry=await self._telemetry.snapshot(),
            cache_enabled=bool(self._cache and self._cache.enabled),
            cache_key_version=self._settings.ai_cache_key_version,
            knowledge_version=self._settings.ai_cache_knowledge_version,
        )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def _record_failure(self, error: AiServiceError, started: float) -> None:
        await self._telemetry.failure(
            error.code,
            round((monotonic() - started) * 1000),
        )

    async def _save_failure_audit(
        self,
        request_id: str,
        request: InterpretScenarioRequest,
        error: AiServiceError,
        started: float,
    ) -> None:
        latency_ms = round((monotonic() - started) * 1000)
        await self._save_audit(
            AiAuditEvent(
                request_id=request_id,
                scenario_id=(
                    request.current_scenario.scenario_id
                    if request.current_scenario is not None
                    else None
                ),
                provider="openrouter",
                primary_model=self._settings.openrouter_primary_model,
                final_model=None,
                escalated=error.code == "AI_ESCALATION_FAILED",
                escalation_reason=(
                    "ESCALATION_FAILED" if error.code == "AI_ESCALATION_FAILED" else None
                ),
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                attempt_count=error.attempt_count,
                latency_ms=latency_ms,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                reported_cost=None,
                outcome_code=error.code,
            )
        )
        await self._save_interaction(
            AiInteractionEvent(
                interaction_id=request_id,
                operation_type="INTENT_INTERPRETATION",
                source=AiProcessingSource.AI_UNAVAILABLE,
                provider="openrouter",
                model=None,
                escalated=error.code == "AI_ESCALATION_FAILED",
                cache_hit=False,
                cache_namespace=AiCacheNamespace.INTENT_INTERPRETATION.value,
                cache_entry_age_seconds=None,
                live_api_call_count=error.attempt_count,
                primary_call_count=error.attempt_count,
                escalation_call_count=int(error.code == "AI_ESCALATION_FAILED"),
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                reported_cost=None,
                latency_ms=latency_ms,
                tokens_avoided=0,
                calls_avoided=0,
                cost_avoided=None,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                knowledge_version=self._settings.ai_cache_knowledge_version,
                profile_version=profiles.get(request.profile_id).version,
                outcome_code=error.code,
            )
        )

    async def _save_audit(self, event: AiAuditEvent) -> None:
        if self._audit_sink is not None:
            try:
                await asyncio.to_thread(self._audit_sink.save, event)
            except AiAuditWriteError:
                logger.error(
                    "AI audit metadata persistence failed for request_id=%s",
                    event.request_id,
                )

    async def _save_interaction(self, event: AiInteractionEvent) -> None:
        if self._interaction_sink is not None:
            try:
                await asyncio.to_thread(
                    self._interaction_sink.save_interaction,
                    event,
                )
            except AiInteractionWriteError:
                logger.error(
                    "AI interaction metadata persistence failed for interaction_id=%s",
                    event.interaction_id,
                )


def _minimal_context(request: InterpretScenarioRequest) -> dict[str, str]:
    if request.current_scenario is None:
        return {"profileId": request.profile_id}
    scenario = request.current_scenario
    context = {"profileId": request.profile_id, "lifecycle": scenario.lifecycle.value}
    confirmed = set(request.confirmed_fields)
    if scenario.direction and CanonicalFieldPath.DIRECTION in confirmed:
        context["confirmedDirection"] = scenario.direction.value
    if scenario.payment_type and CanonicalFieldPath.PAYMENT_TYPE in confirmed:
        context["confirmedPaymentType"] = scenario.payment_type.value
    if scenario.trade.transaction_type and CanonicalFieldPath.TRANSACTION_TYPE in confirmed:
        context["confirmedTransactionType"] = scenario.trade.transaction_type.value
    return context


def _primary_error_escalation_reason(error: AiServiceError) -> str:
    if error.code == "AI_SCHEMA_VALIDATION_FAILED":
        return "PRIMARY_SCHEMA_INVALID"
    return "PRIMARY_ENDPOINT_FAILURE"


def _has_mutually_contradictory_intent(text: str) -> bool:
    lowered = text.casefold()
    receives = bool(
        re.search(
            r"\b(?:receive|receiving|recieve|incoming|receipt|rvp)\b"
            r"(?!\s+(?:payment|agent|party))",
            lowered,
        )
    )
    delivers = bool(
        re.search(r"\b(?:deliver|delivery|delivered|outgoing)\b", lowered)
        or re.search(r"\bdelivering\b(?!\s+(?:agent|party))", lowered)
        or re.search(r"\b(?:shares?|securities|position)\s+out\b", lowered)
        or re.search(r"\bsend\s+(?:the\s+)?securities\s+out\b", lowered)
    )
    directions = receives and delivers
    payments = bool(
        re.search(r"\b(?:fop|free[- ]of[- ]payment|without payment)\b", lowered)
    ) and bool(re.search(r"\b(?:dvp|rvp|against[- ]payment|with payment)\b", lowered))
    return directions or payments


def _is_complex_lifecycle(text: str) -> bool:
    lowered = text.casefold()
    hits = sum(
        bool(re.search(pattern, lowered))
        for pattern in (
            r"\bcancell?",
            r"\bpartial",
            r"\bconfirm",
            r"\b(?:pending|rejected|matched|unmatched)\b",
        )
    )
    return hits >= 3


def _deterministic_conflict(parsed: Any, text: str) -> bool:
    lowered = text.casefold()
    receives = bool(
        re.search(
            r"\b(?:receive|receiving|recieve|incoming|receipt|rvp)\b"
            r"(?!\s+(?:payment|agent|party))",
            lowered,
        )
    )
    delivers = bool(
        re.search(r"\b(?:deliver|delivery|delivered|outgoing)\b", lowered)
        or re.search(r"\bdelivering\b(?!\s+(?:agent|party))", lowered)
        or re.search(r"\b(?:shares?|securities|position)\s+out\b", lowered)
        or re.search(r"\bsend\s+(?:the\s+)?securities\s+out\b", lowered)
    )
    explicit_direction = None
    if receives and not delivers:
        explicit_direction = Direction.RECEIVE
    elif delivers and not receives:
        explicit_direction = Direction.DELIVER
    elif receives and delivers:
        return parsed.intent.direction is not None
    free = bool(re.search(r"\b(?:fop|free[- ]of[- ]payment|without payment|no cash)\b", lowered))
    against = bool(
        re.search(r"\b(?:dvp|rvp|against[- ]payment|aganst[- ]payment|with payment)\b", lowered)
    )
    explicit_payment = None
    if free and not against:
        explicit_payment = PaymentType.FREE_OF_PAYMENT
    elif against and not free:
        explicit_payment = PaymentType.AGAINST_PAYMENT
    elif free and against:
        return parsed.intent.payment_type is not None
    return bool(
        (explicit_direction and parsed.intent.direction != explicit_direction)
        or (explicit_payment and parsed.intent.payment_type != explicit_payment)
    )


def _deterministically_complete(parsed: Any) -> bool:
    intent = parsed.intent
    if intent.inferred_fields:
        return False
    if intent.lifecycle in {Lifecycle.INSTRUCTION, Lifecycle.CONFIRMATION}:
        return intent.direction is not None and intent.payment_type is not None
    if intent.lifecycle == Lifecycle.STATUS:
        return intent.response_action is not None
    return False


def _typed_value(path: CanonicalFieldPath, value: str) -> Any:
    if path in {
        CanonicalFieldPath.SECURITY_QUANTITY,
        CanonicalFieldPath.SETTLEMENT_AMOUNT,
        CanonicalFieldPath.SETTLED_QUANTITY,
        CanonicalFieldPath.SETTLED_AMOUNT,
    }:
        return Decimal(value.replace(",", ""))
    if path in {
        CanonicalFieldPath.TRADE_DATE,
        CanonicalFieldPath.SETTLEMENT_DATE,
        CanonicalFieldPath.ACTUAL_SETTLEMENT_DATE,
    }:
        return date.fromisoformat(value)
    if path == CanonicalFieldPath.SETTLEMENT_CURRENCY:
        if not re.fullmatch(r"[A-Z]{3}", value):
            raise ai_error("AI_UNSAFE_RESPONSE")
        return value
    return value


def _get_path(scenario: SettlementScenario, path: CanonicalFieldPath) -> Any:
    value: Any = scenario
    for part in _python_path(path).split("."):
        value = getattr(value, part)
    return value


def _set_path(scenario: SettlementScenario, path: CanonicalFieldPath, value: Any) -> None:
    parts = _python_path(path).split(".")
    target: Any = scenario
    for part in parts[:-1]:
        target = getattr(target, part)
    setattr(target, parts[-1], value)


def _python_path(path: CanonicalFieldPath) -> str:
    return {
        CanonicalFieldPath.PAYMENT_TYPE: "payment_type",
        CanonicalFieldPath.TRANSACTION_TYPE: "trade.transaction_type",
        CanonicalFieldPath.SENDER_REFERENCE: "sender_reference",
        CanonicalFieldPath.RELATED_REFERENCE: "related_reference",
        CanonicalFieldPath.CLIENT_REFERENCE: "client_reference",
        CanonicalFieldPath.TRADE_DATE: "trade.trade_date",
        CanonicalFieldPath.SETTLEMENT_DATE: "trade.settlement_date",
        CanonicalFieldPath.SECURITY_IDENTIFIER: "security.identifier",
        CanonicalFieldPath.SECURITY_QUANTITY: "security.quantity",
        CanonicalFieldPath.SAFEKEEPING_ACCOUNT: "account.safekeeping_account",
        CanonicalFieldPath.SETTLEMENT_CURRENCY: "settlement.currency",
        CanonicalFieldPath.SETTLEMENT_AMOUNT: "settlement.amount",
        CanonicalFieldPath.PLACE_OF_SETTLEMENT: "settlement.place_of_settlement",
        CanonicalFieldPath.DELIVERING_AGENT: "settlement.delivering_agent",
        CanonicalFieldPath.RECEIVING_AGENT: "settlement.receiving_agent",
        CanonicalFieldPath.ACTUAL_SETTLEMENT_DATE: "confirmation.actual_settlement_date",
        CanonicalFieldPath.SETTLED_QUANTITY: "confirmation.settled_quantity",
        CanonicalFieldPath.SETTLED_AMOUNT: "confirmation.settled_amount",
        CanonicalFieldPath.REASON_NARRATIVE: "status.narrative",
    }.get(path, path.value)


def _merge_value(
    scenario: SettlementScenario,
    path: CanonicalFieldPath,
    value: Any,
    confirmed: set[CanonicalFieldPath],
    conflicts: list[InterpretationConflict],
) -> None:
    existing = _get_path(scenario, path)
    if path in confirmed and existing is not None and existing != value:
        conflicts.append(
            InterpretationConflict(
                field_path=path,
                existing_value=str(existing),
                proposed_value=str(value),
                message="The new request conflicts with a confirmed value; no overwrite occurred.",
            )
        )
        return
    _set_path(scenario, path, value)


def _add_usage(first: ModelUsage, second: ModelUsage) -> ModelUsage:
    costs = [value for value in (first.reported_cost, second.reported_cost) if value is not None]
    return ModelUsage(
        prompt_tokens=first.prompt_tokens + second.prompt_tokens,
        completion_tokens=first.completion_tokens + second.completion_tokens,
        total_tokens=first.total_tokens + second.total_tokens,
        reported_cost=sum(costs, Decimal("0")) if costs else None,
    )
