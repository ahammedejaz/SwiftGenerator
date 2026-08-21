import hmac
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Header, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import text

from app.agents.cache import AiCacheNamespace
from app.agents.fallback import interpret_scenario
from app.agents.schemas import PROMPT_VERSION, SCHEMA_VERSION
from app.agents.service import AgentInterpretationService
from app.agents.usage import AiInteractionEvent
from app.authoring.models import SessionUser
from app.bulk.service import BulkService
from app.bulk.workflow_service import WorkflowBulkService
from app.config import Settings, get_settings
from app.demo.service import DemoService
from app.domain.enums import AiProcessingSource, MessageType, NegativeMutation
from app.domain.missing_fields import find_missing_fields
from app.domain.models import (
    AiCacheDiagnosisResponse,
    AiCacheStatsResponse,
    AiHealthResponse,
    AiUsageInteractionResponse,
    AiUsageSummaryResponse,
    AmendmentDecisionRequest,
    AmendmentDecisionResponse,
    BulkGenerateResponse,
    CancelRebookRequest,
    CancelRebookResponse,
    DemoResetResponse,
    GeneratedMessage,
    GenerateMessageRequest,
    InterpretScenarioRequest,
    LifecycleResponseRequest,
    LifecycleTimeline,
    MessageResolution,
    MessageResolutionRequest,
    MissingFieldsRequest,
    MissingFieldsResponse,
    ProfileDetail,
    ProfileSummary,
    RawValidationResponse,
    ReportMetadataResponse,
    ScenarioInterpretation,
    SettlementCancellationRequest,
    SettlementCommandRequest,
    StatusOption,
    ValidateRawRequest,
    ValidationReport,
    ValidationScenarioRequest,
)
from app.domain.resolver import resolve_message_type
from app.domain.statuses import statuses
from app.event_profiles.registry import CorporateActionEventProfile, event_profile_registry
from app.knowledge.loader import knowledge_repository
from app.knowledge.models import (
    EffectiveTagKnowledge,
    KnowledgeDependencyResponse,
    KnowledgeExplainRequest,
    KnowledgeMessageSummary,
    KnowledgeSearchResponse,
    PresenceRule,
    WorkflowModuleId,
)
from app.persistence.ai_usage import ai_usage_repository, interaction_response
from app.persistence.database import engine
from app.persistence.reports import report_repository
from app.persistence.repository import message_repository
from app.persistence.workflow_messages import workflow_message_repository
from app.profiles.loader import profiles
from app.raw.validator import validate_raw_message
from app.samples.models import SampleDetail, SampleSummary
from app.samples.service import sample_service
from app.security.auth import get_optional_user
from app.services.generation import GenerationService
from app.services.lifecycle import LifecycleService
from app.specifications.models import (
    CoverageReport,
    MessageCatalogue,
    MessageCoverage,
    MessageSpecification,
)
from app.specifications.registry import specification_registry
from app.studio.mx.registry import mx_registry
from app.workflows.corporate_actions import (
    CorporateActionConfirmationRequest,
    CorporateActionInstructionRequest,
    CorporateActionNarrativeRequest,
    CorporateActionNotificationRequest,
    CorporateActionStatusRequest,
    CorporateActionWorkflowService,
)
from app.workflows.models import WorkflowGeneratedMessage, WorkflowLifecycle
from app.workflows.penalties import (
    PenaltyGenerateRequest,
    PenaltyValidateRequest,
    PenaltyWorkflowService,
)
from app.workflows.registry import CapabilityCatalogue, workflow_registry
from app.workflows.reporting import WorkflowExecutionReport, WorkflowReportingService
from app.workflows.settlement_processing import SettlementProcessingService

router = APIRouter(prefix="/api")
generation_service = GenerationService(profiles, message_repository)
lifecycle_service = LifecycleService(profiles, message_repository)
bulk_service = BulkService(get_settings(), generation_service, lifecycle_service, report_repository)
demo_service = DemoService(generation_service, lifecycle_service, message_repository)
settlement_processing_service = SettlementProcessingService(
    profiles,
    message_repository,
    generation_service,
    lifecycle_service,
)
penalty_workflow_service = PenaltyWorkflowService(
    profiles, workflow_message_repository, message_repository
)
corporate_action_service = CorporateActionWorkflowService(profiles, workflow_message_repository)
workflow_bulk_service = WorkflowBulkService(
    get_settings(),
    report_repository,
    settlement_processing_service,
    penalty_workflow_service,
    corporate_action_service,
)
workflow_reporting_service = WorkflowReportingService(
    workflow_message_repository, profiles, knowledge_repository
)


@router.get("/health")
def health() -> dict[str, str]:
    settings: Settings = get_settings()
    return {
        "status": "ok",
        "application": settings.app_name,
        "environment": settings.app_env,
        "messageStandardScope": "Configured source-bounded Category 5 subset",
    }


@router.get("/health/live")
def liveness() -> dict[str, str]:
    """A process-only probe. It deliberately touches no optional dependency."""
    return {"status": "alive"}


@router.get("/health/ready")
def readiness() -> dict[str, Any]:
    """Required runtime readiness, with optional AI and knowledge states kept separate."""
    settings = get_settings()
    database_ready = False
    database_error: str | None = None
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        database_ready = True
    except Exception as error:  # pragma: no cover - exercised by deployment probes
        database_error = type(error).__name__
    mt_count = len(specification_registry.list())
    mx_count = len(mx_registry.all_specs())
    registry_ready = mt_count > 0 and mx_count > 0

    from app.knowledge_base.service import knowledge_service

    knowledge_state = (
        "OPTIONAL_DISABLED"
        if not settings.knowledge_enabled
        else "READY"
        if knowledge_service.indexed
        else "OPTIONAL_NOT_INDEXED"
    )
    ai_configured = settings.ai_provider not in {"disabled", "mock"} and bool(
        settings.openrouter_api_key or settings.ai_api_key
    )
    ready = database_ready and registry_ready
    return {
        "status": "ready" if ready else "not_ready",
        "required": {
            "database": {"ready": database_ready, "error": database_error},
            "registries": {
                "ready": registry_ready,
                "configuredMt": mt_count,
                "configuredMx": mx_count,
            },
        },
        "optional": {
            "knowledge": {"state": knowledge_state},
            "ai": {
                "state": "CONFIGURED" if ai_configured else "OPTIONAL_DISABLED",
                "provider": settings.ai_provider,
            },
            "embeddings": {
                "state": (
                    "CONFIGURED"
                    if settings.embedding_provider_effective != "disabled"
                    else "OPTIONAL_DISABLED"
                ),
                "provider": settings.embedding_provider_effective,
            },
        },
    }


@router.get("/capabilities", response_model=CapabilityCatalogue)
def get_capabilities(
    profile_id: str | None = Query(default=None, alias="profileId"),
) -> CapabilityCatalogue:
    profile = profiles.get(profile_id) if profile_id else None
    return workflow_registry.catalogue(profile)


@router.get("/specifications/messages", response_model=MessageCatalogue)
def list_message_specifications() -> MessageCatalogue:
    """Return the source-bounded configured catalogue; no completeness claim is implied."""
    return specification_registry.catalogue()


@router.get(
    "/specifications/event-profiles",
    response_model=list[CorporateActionEventProfile],
)
def list_event_profiles() -> list[CorporateActionEventProfile]:
    return event_profile_registry.list()


@router.get("/specifications/messages/{message_type}", response_model=MessageSpecification)
def get_message_specification(message_type: MessageType) -> MessageSpecification:
    return specification_registry.get(message_type)


@router.get("/specifications/messages/{message_type}/coverage", response_model=MessageCoverage)
def get_message_specification_coverage(message_type: MessageType) -> MessageCoverage:
    covered = sample_service.coverage().get(message_type, set())
    return specification_registry.coverage(message_type, sample_rows=covered, golden_rows=covered)


@router.get("/specifications/coverage", response_model=CoverageReport)
def get_message_specification_coverage_report() -> CoverageReport:
    covered = sample_service.coverage()
    return specification_registry.report(covered, covered)


@router.get("/knowledge/samples", response_model=list[SampleSummary])
def list_annotated_samples() -> list[SampleSummary]:
    return sample_service.list()


@router.get("/knowledge/samples/{sample_id}", response_model=SampleDetail)
def get_annotated_sample(sample_id: str) -> SampleDetail:
    return sample_service.get(sample_id)


@router.get("/profiles", response_model=list[ProfileSummary])
def list_profiles() -> list[ProfileSummary]:
    return [profile.summary() for profile in profiles.list()]


@router.get("/profiles/{profile_id}", response_model=ProfileDetail)
def get_profile(profile_id: str) -> ProfileDetail:
    return profiles.get(profile_id).detail()


@router.get("/statuses", response_model=list[StatusOption])
def list_statuses() -> list[StatusOption]:
    return statuses.list()


@router.get("/negative-tests", response_model=list[NegativeMutation])
def list_negative_tests(
    profile_id: str = Query(default="BASE_DEMO_V1", alias="profileId"),
) -> list[NegativeMutation]:
    return profiles.get(profile_id).enabled_negative_mutations


@router.get("/knowledge/messages", response_model=list[KnowledgeMessageSummary])
def list_knowledge_messages() -> list[KnowledgeMessageSummary]:
    return knowledge_repository.list_messages()


@router.get(
    "/knowledge/messages/{message_type}",
    response_model=list[EffectiveTagKnowledge],
)
def list_message_knowledge(
    message_type: MessageType,
    profile_id: str = Query(default="BASE_DEMO_V1", alias="profileId"),
) -> list[EffectiveTagKnowledge]:
    profiles.get(profile_id)
    return knowledge_repository.list_records(message_type=message_type, profile_id=profile_id)


@router.get("/knowledge/tags", response_model=list[EffectiveTagKnowledge])
def list_tag_knowledge(
    message_type: Annotated[MessageType | None, Query(alias="messageType")] = None,
    sequence: str | None = None,
    tag: str | None = None,
    qualifier: str | None = None,
    workflow_module: Annotated[WorkflowModuleId | None, Query(alias="workflowModule")] = None,
    presence: PresenceRule | None = None,
    profile_id: str = Query(default="BASE_DEMO_V1", alias="profileId"),
) -> list[EffectiveTagKnowledge]:
    profiles.get(profile_id)
    return knowledge_repository.list_records(
        message_type=message_type,
        sequence=sequence,
        tag=tag,
        qualifier=qualifier,
        workflow_module=workflow_module,
        presence=presence,
        profile_id=profile_id,
    )


@router.get("/knowledge/tags/{knowledge_id}", response_model=EffectiveTagKnowledge)
def get_tag_knowledge(
    knowledge_id: str,
    profile_id: str = Query(default="BASE_DEMO_V1", alias="profileId"),
) -> EffectiveTagKnowledge:
    return knowledge_repository.effective(knowledge_id, profile_id)


@router.get("/knowledge/search", response_model=KnowledgeSearchResponse)
def search_tag_knowledge(
    query: str = Query(alias="q", min_length=1, max_length=120),
    profile_id: str = Query(default="BASE_DEMO_V1", alias="profileId"),
) -> KnowledgeSearchResponse:
    profiles.get(profile_id)
    return KnowledgeSearchResponse(
        query=query,
        results=knowledge_repository.search(query, profile_id=profile_id),
    )


@router.post("/knowledge/explain", response_model=EffectiveTagKnowledge)
def explain_tag_knowledge(payload: KnowledgeExplainRequest) -> EffectiveTagKnowledge:
    """Return verified deterministic knowledge without an LLM call."""
    return knowledge_repository.effective(payload.knowledge_id, payload.profile_id)


@router.get(
    "/knowledge/dependencies/{knowledge_id}",
    response_model=KnowledgeDependencyResponse,
)
def get_tag_dependencies(
    knowledge_id: str,
    profile_id: str = Query(default="BASE_DEMO_V1", alias="profileId"),
) -> KnowledgeDependencyResponse:
    return knowledge_repository.dependencies(knowledge_id, profile_id)


@router.post("/agent/interpret", response_model=ScenarioInterpretation)
async def interpret_business_scenario(
    payload: InterpretScenarioRequest,
    request: Request,
    user: Annotated[SessionUser | None, Depends(get_optional_user)],
) -> ScenarioInterpretation:
    profiles.get(payload.profile_id)
    service: AgentInterpretationService = request.app.state.ai_service
    return await service.interpret(
        payload,
        tenant_partition=user.tenant_id if user else "PUBLIC_GUIDED",
    )


@router.post("/agent/interpret-deterministic", response_model=ScenarioInterpretation)
def interpret_business_scenario_without_ai(
    payload: InterpretScenarioRequest,
) -> ScenarioInterpretation:
    """Explicit non-AI resilience path; never represented as a model response."""
    profiles.get(payload.profile_id)
    result = interpret_scenario(payload)
    profile = profiles.get(payload.profile_id)
    ai_usage_repository.save_interaction(
        AiInteractionEvent(
            interaction_id=result.ai.request_id,
            operation_type="INTENT_INTERPRETATION",
            source=AiProcessingSource.DETERMINISTIC,
            provider="deterministic_non_ai",
            model=None,
            escalated=False,
            cache_hit=False,
            cache_namespace=None,
            cache_entry_age_seconds=None,
            live_api_call_count=0,
            primary_call_count=0,
            escalation_call_count=0,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            reported_cost=None,
            latency_ms=0,
            tokens_avoided=0,
            calls_avoided=1,
            cost_avoided=None,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            knowledge_version=get_settings().ai_cache_knowledge_version,
            profile_version=profile.version,
            outcome_code="DETERMINISTIC_NON_AI",
        )
    )
    return result


@router.get("/ai/health", response_model=AiHealthResponse)
async def ai_health(request: Request) -> AiHealthResponse:
    service: AgentInterpretationService = request.app.state.ai_service
    return await service.health()


@router.get(
    "/ai/usage/last-interaction",
    response_model=AiUsageInteractionResponse | None,
)
def ai_last_interaction() -> AiUsageInteractionResponse | None:
    record = ai_usage_repository.last_interaction()
    return interaction_response(record) if record is not None else None


@router.get(
    "/ai/usage/last-provider-call",
    response_model=AiUsageInteractionResponse | None,
)
def ai_last_provider_call() -> AiUsageInteractionResponse | None:
    record = ai_usage_repository.last_provider_call()
    return interaction_response(record) if record is not None else None


@router.get("/ai/usage/summary", response_model=AiUsageSummaryResponse)
def ai_usage_summary(
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> AiUsageSummaryResponse:
    raw = ai_usage_repository.summary(days)
    interactions = int(raw["interactions"])
    cache_hits = int(raw["cacheHits"])
    return AiUsageSummaryResponse(
        period_days=days,
        interactions=interactions,
        deterministic_interactions=int(raw["deterministicInteractions"]),
        live_api_calls=int(raw["liveApiCalls"]),
        cache_hits=cache_hits,
        cache_hit_rate=(cache_hits / interactions if interactions else 0),
        tokens_consumed=int(raw["tokensConsumed"]),
        tokens_avoided=int(raw["tokensAvoided"]),
        api_calls_avoided=int(raw["apiCallsAvoided"]),
        provider_reported_cost=str(raw["providerReportedCost"]),
        estimated_cost_avoided=str(raw["estimatedCostAvoided"]),
        average_latency_ms=int(raw["averageLatencyMs"]),
    )


@router.get("/ai/cache/stats", response_model=AiCacheStatsResponse)
async def ai_cache_stats(request: Request) -> AiCacheStatsResponse:
    return AiCacheStatsResponse.model_validate(await request.app.state.ai_cache.stats())


@router.post("/ai/cache/diagnose", response_model=AiCacheDiagnosisResponse)
async def ai_cache_diagnose(request: Request) -> AiCacheDiagnosisResponse:
    cache = request.app.state.ai_cache
    stats = await cache.stats()
    enabled = bool(stats["enabled"])
    return AiCacheDiagnosisResponse(
        enabled=enabled,
        securely_configured=enabled,
        persistent_store_available=True,
        key_version=str(stats["keyVersion"]),
        namespaces=[item.value for item in AiCacheNamespace],
        status="READY" if enabled else "DISABLED_OR_SECRET_NOT_CONFIGURED",
    )


@router.post("/messages/resolve", response_model=MessageResolution)
def resolve_message(request: MessageResolutionRequest) -> MessageResolution:
    return resolve_message_type(request)


@router.post("/messages/missing-fields", response_model=MissingFieldsResponse)
def missing_fields(request: MissingFieldsRequest) -> MissingFieldsResponse:
    prepared = generation_service.prepare(request.scenario)
    if prepared.message_type is None:
        raise ValueError(
            "Direction and payment type are required before identifying message fields"
        )
    profile = profiles.get(prepared.profile_id)
    return find_missing_fields(prepared, prepared.message_type, profile)


@router.post("/messages/validate-scenario", response_model=ValidationReport)
def validate_message_scenario(request: ValidationScenarioRequest) -> ValidationReport:
    _, report = generation_service.validate(request.scenario)
    return report


@router.post("/messages/validate-raw", response_model=RawValidationResponse)
def validate_raw_message_subset(request: ValidateRawRequest) -> RawValidationResponse:
    return validate_raw_message(request.raw_message, profiles.get(request.profile_id))


@router.post("/messages/generate", response_model=GeneratedMessage)
def generate_message(request: GenerateMessageRequest) -> GeneratedMessage:
    return generation_service.generate(request.scenario)


@router.post("/messages/{instruction_id}/responses", response_model=GeneratedMessage)
def generate_lifecycle_response(
    instruction_id: str,
    request: LifecycleResponseRequest,
) -> GeneratedMessage:
    return lifecycle_service.generate_response(instruction_id, request)


@router.get("/messages/{message_id}", response_model=GeneratedMessage)
def retrieve_message(message_id: str) -> GeneratedMessage:
    return message_repository.get(message_id)


@router.get("/messages/{message_id}/lifecycle", response_model=LifecycleTimeline)
def retrieve_lifecycle(message_id: str) -> LifecycleTimeline:
    return message_repository.lifecycle(message_id)


@router.post("/settlement/cancellations", response_model=GeneratedMessage)
def create_settlement_cancellation(
    payload: SettlementCancellationRequest,
) -> GeneratedMessage:
    return settlement_processing_service.cancellation(payload)


@router.post(
    "/settlement/amendment-decision",
    response_model=AmendmentDecisionResponse,
)
def decide_settlement_amendment(
    payload: AmendmentDecisionRequest,
) -> AmendmentDecisionResponse:
    return settlement_processing_service.amendment_decision(payload)


@router.post("/settlement/commands", response_model=GeneratedMessage)
def create_settlement_command(payload: SettlementCommandRequest) -> GeneratedMessage:
    return settlement_processing_service.command(payload)


@router.post("/settlement/cancel-rebook", response_model=CancelRebookResponse)
def cancel_and_rebook_settlement(payload: CancelRebookRequest) -> CancelRebookResponse:
    return settlement_processing_service.cancel_and_rebook(payload)


@router.post("/penalties/generate", response_model=WorkflowGeneratedMessage)
def generate_penalty_statement(payload: PenaltyGenerateRequest) -> WorkflowGeneratedMessage:
    return penalty_workflow_service.generate(payload)


@router.post("/penalties/validate", response_model=ValidationReport)
def validate_penalty_statement(payload: PenaltyValidateRequest) -> ValidationReport:
    return penalty_workflow_service.validate(
        payload.statement, payload.related_settlement_message_id
    )


@router.post("/corporate-actions/notifications", response_model=WorkflowGeneratedMessage)
def create_corporate_action_notification(
    payload: CorporateActionNotificationRequest,
) -> WorkflowGeneratedMessage:
    return corporate_action_service.notification(payload)


@router.post("/corporate-actions/instructions", response_model=WorkflowGeneratedMessage)
def create_corporate_action_instruction(
    payload: CorporateActionInstructionRequest,
) -> WorkflowGeneratedMessage:
    return corporate_action_service.instruction(payload)


@router.post("/corporate-actions/statuses", response_model=WorkflowGeneratedMessage)
def create_corporate_action_status(
    payload: CorporateActionStatusRequest,
) -> WorkflowGeneratedMessage:
    return corporate_action_service.status(payload)


@router.post("/corporate-actions/confirmations", response_model=WorkflowGeneratedMessage)
def create_corporate_action_confirmation(
    payload: CorporateActionConfirmationRequest,
) -> WorkflowGeneratedMessage:
    return corporate_action_service.confirmation(payload)


@router.post("/corporate-actions/narratives", response_model=WorkflowGeneratedMessage)
def create_corporate_action_narrative(
    payload: CorporateActionNarrativeRequest,
) -> WorkflowGeneratedMessage:
    return corporate_action_service.narrative(payload)


@router.get(
    "/workflows/{workflow_id}/lifecycle",
    response_model=LifecycleTimeline | WorkflowLifecycle,
)
def retrieve_workflow_lifecycle(
    workflow_id: str,
) -> LifecycleTimeline | WorkflowLifecycle:
    try:
        return message_repository.lifecycle(workflow_id)
    except KeyError:
        return workflow_message_repository.lifecycle(workflow_id)


@router.get(
    "/workflows/messages/{message_id}/report",
    response_model=WorkflowExecutionReport,
)
def retrieve_workflow_report(message_id: str) -> WorkflowExecutionReport:
    return workflow_reporting_service.report(message_id)


@router.get("/bulk/template")
def download_bulk_template() -> Response:
    return Response(
        content=bulk_service.template(),
        media_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        headers={
            "Content-Disposition": (
                'attachment; filename="securities-message-studio-template.xlsx"'
            )
        },
    )


@router.post("/bulk/generate", response_model=BulkGenerateResponse)
async def generate_bulk(file: Annotated[UploadFile, File()]) -> BulkGenerateResponse:
    if file.content_type not in {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
    }:
        raise ValueError("Unsupported upload content type")
    content = await file.read(get_settings().max_upload_bytes + 1)
    await file.close()
    return bulk_service.generate(content, file.filename or "")


@router.get("/bulk/workflow-template")
def download_workflow_bulk_template() -> Response:
    return Response(
        content=workflow_bulk_service.template(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": ('attachment; filename="swift-platform-workflow-template.xlsx"')
        },
    )


@router.post("/bulk/workflow-generate", response_model=BulkGenerateResponse)
async def generate_workflow_bulk(
    file: Annotated[UploadFile, File()],
) -> BulkGenerateResponse:
    if file.content_type not in {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
    }:
        raise ValueError("Unsupported upload content type")
    content = await file.read(get_settings().max_upload_bytes + 1)
    await file.close()
    return workflow_bulk_service.generate(content, file.filename or "")


@router.get("/reports/{report_id}")
def download_report(report_id: str) -> FileResponse:
    path = report_repository.get_path(report_id)
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"securities-message-studio-report-{report_id}.zip",
    )


@router.get("/reports/{report_id}/metadata", response_model=ReportMetadataResponse)
def retrieve_report_metadata(report_id: str) -> ReportMetadataResponse:
    return ReportMetadataResponse(
        report_id=report_id,
        report_payload=report_repository.get_payload(report_id),
        download_path=f"/api/reports/{report_id}",
    )


@router.post("/demo/reset", response_model=DemoResetResponse)
def reset_demo_data(
    request: Request,
    reset_key: Annotated[str | None, Header(alias="X-Demo-Reset-Key")] = None,
) -> DemoResetResponse:
    settings = get_settings()
    if not settings.demo_reset_enabled:
        raise ValueError("Demo reset is disabled")
    if settings.demo_reset_key:
        if not reset_key or not hmac.compare_digest(reset_key, settings.demo_reset_key):
            raise ValueError("A valid demo reset key is required")
    else:
        client_host = request.client.host if request.client else ""
        if settings.app_env != "development" or client_host not in {
            "127.0.0.1",
            "::1",
            "testclient",
        }:
            raise ValueError("Unkeyed demo reset is allowed only from local development")
    return demo_service.reset()
