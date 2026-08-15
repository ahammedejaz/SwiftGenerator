from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    AiCircuitState,
    AiProcessingSource,
    AiSource,
    AmendmentClassification,
    AmendmentField,
    CanonicalFieldPath,
    Direction,
    GenerationMode,
    IdentifierType,
    Lifecycle,
    MessageFunction,
    MessageType,
    NegativeMutation,
    PaymentType,
    QuantityType,
    ResponseAction,
    SettlementCommandType,
    SettlementResult,
    Severity,
    StatusCategory,
    TransactionType,
    ValidationStatus,
)


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(word.capitalize() for word in rest)


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        use_enum_values=False,
    )


class Trade(ApiModel):
    transaction_type: TransactionType | None = None
    trade_date: date | None = None
    settlement_date: date | None = None


class Security(ApiModel):
    identifier_type: IdentifierType = IdentifierType.ISIN
    identifier: str | None = None
    description: str | None = None
    quantity_type: QuantityType = QuantityType.UNIT
    quantity: Decimal | None = None


class Account(ApiModel):
    safekeeping_account: str | None = None


class Settlement(ApiModel):
    currency: str | None = None
    amount: Decimal | None = None
    place_of_settlement: str | None = None
    delivering_agent: str | None = None
    receiving_agent: str | None = None


class Confirmation(ApiModel):
    confirmation_reference: str | None = None
    actual_settlement_date: date | None = None
    settled_quantity: Decimal | None = None
    settled_amount: Decimal | None = None
    settlement_result: SettlementResult | None = None


class StatusDetails(ApiModel):
    category: StatusCategory | None = None
    code: str | None = None
    reason_code: str | None = None
    narrative: str | None = None
    related_instruction_message_type: MessageType | None = None


class TestConfiguration(ApiModel):
    mode: GenerationMode = GenerationMode.VALID
    mutation: NegativeMutation | None = None
    expected_outcome: str | None = None


class SettlementCommandDetails(ApiModel):
    command_type: SettlementCommandType | None = None
    original_instruction_reference: str | None = None
    priority: int | None = Field(default=None, ge=1, le=9999)


class SettlementScenario(ApiModel):
    scenario_id: str
    profile_id: str = "BASE_DEMO_V1"
    lifecycle: Lifecycle = Lifecycle.INSTRUCTION
    direction: Direction | None = None
    payment_type: PaymentType | None = None
    message_type: MessageType | None = None
    function: MessageFunction | None = None
    sender_reference: str | None = None
    related_reference: str | None = None
    client_reference: str | None = None
    trade: Trade = Field(default_factory=Trade)
    security: Security = Field(default_factory=Security)
    account: Account = Field(default_factory=Account)
    settlement: Settlement = Field(default_factory=Settlement)
    confirmation: Confirmation = Field(default_factory=Confirmation)
    status: StatusDetails = Field(default_factory=StatusDetails)
    command: SettlementCommandDetails = Field(default_factory=SettlementCommandDetails)
    test_configuration: TestConfiguration = Field(default_factory=TestConfiguration)
    synthetic_data: bool = True


class MessageResolutionRequest(ApiModel):
    lifecycle: Lifecycle
    direction: Direction | None = None
    payment_type: PaymentType | None = None
    original_instruction_type: MessageType | None = None


class MessageResolution(ApiModel):
    resolved_message_type: MessageType | None
    explanation: str
    missing_decision_information: list[str] = Field(default_factory=list)
    confidence: str


class MissingField(ApiModel):
    field_path: str
    question: str
    explanation: str
    technical_mapping: str | None = None


class MissingFieldsResponse(ApiModel):
    message_type: MessageType
    profile_id: str
    profile_version: str
    missing_fields: list[MissingField]
    next_question: MissingField | None
    completion_percentage: int
    scenario_with_defaults: SettlementScenario


class ValidationFinding(ApiModel):
    rule_id: str
    severity: Severity
    field_path: str | None = None
    message: str
    technical_explanation: str
    current_value: Any = None
    expected_condition: str | None = None
    suggestion: str | None = None
    intentional: bool = False


class ValidationReport(ApiModel):
    status: ValidationStatus
    profile_id: str
    profile_version: str
    findings: list[ValidationFinding]
    error_count: int
    warning_count: int


class RenderedField(ApiModel):
    sequence: str
    tag: str
    qualifier: str | None = None
    value: str
    business_path: str
    business_meaning: str


class GeneratedMessage(ApiModel):
    message_id: str
    scenario: SettlementScenario
    resolved_message_type: MessageType
    raw_message: str
    field_map: list[RenderedField]
    profile_id: str
    profile_version: str
    validation: ValidationReport
    disclaimer: str
    intentional_invalid_notice: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ValidationScenarioRequest(ApiModel):
    scenario: SettlementScenario


class ValidateRawRequest(ApiModel):
    raw_message: str = Field(min_length=1, max_length=50_000)
    profile_id: str = "BASE_DEMO_V1"


class RawParsedField(ApiModel):
    sequence: str
    tag: str
    qualifier: str | None = None
    value: str
    line_number: int


class RawValidationResponse(ApiModel):
    message_type: MessageType | None
    supported_subset: bool
    parsed_fields: list[RawParsedField]
    validation: ValidationReport
    disclaimer: str


class MissingFieldsRequest(ApiModel):
    scenario: SettlementScenario


class GenerateMessageRequest(ApiModel):
    scenario: SettlementScenario


class ProfileSummary(ApiModel):
    profile_id: str
    name: str
    version: str
    standards_release: str
    status: str
    supported_message_types: list[MessageType]


class ProfileDetail(ProfileSummary):
    defaults: dict[str, Any]
    allowed_currencies: list[str]
    required_fields: dict[str, list[str]]
    client_required_fields: dict[str, list[str]]
    enabled_negative_mutations: list[NegativeMutation]
    sender_reference_max_length: int
    sender_reference_uppercase: bool


class StatusOption(ApiModel):
    category: StatusCategory
    code: str
    reasons: list[str]


class LifecycleResponseRequest(ApiModel):
    action: ResponseAction
    response_reference: str | None = None
    reason_code: str | None = None
    reason_narrative: str | None = None
    actual_settlement_date: date | None = None
    settled_quantity: Decimal | None = None
    settled_amount: Decimal | None = None
    generation_mode: GenerationMode = GenerationMode.VALID
    negative_mutation: NegativeMutation | None = None


class LifecycleEntry(ApiModel):
    message_id: str
    message_type: MessageType
    related_message_id: str | None = None
    sender_reference: str
    related_reference: str | None = None
    lifecycle: Lifecycle
    business_status: str
    profile_id: str
    profile_version: str
    validation_status: ValidationStatus
    created_at: datetime


class LifecycleTimeline(ApiModel):
    root_message_id: str
    entries: list[LifecycleEntry]
    correlation_valid: bool
    correlation_findings: list[ValidationFinding] = Field(default_factory=list)


class SettlementCancellationRequest(ApiModel):
    original_instruction_id: str
    cancellation_reference: str | None = None


class AmendmentChange(ApiModel):
    field_path: AmendmentField
    proposed_value: str | None = None


class AmendmentDecisionRequest(ApiModel):
    original_instruction_id: str
    changes: list[AmendmentChange] = Field(min_length=1, max_length=12)


class AmendmentDecisionResponse(ApiModel):
    classification: AmendmentClassification
    method: str
    explanation: str
    direct_amendment_supported: bool
    requires_cancel_rebook: bool
    affected_fields: list[AmendmentField]
    source_reference: str
    profile_id: str
    profile_version: str


class SettlementCommandRequest(ApiModel):
    original_instruction_id: str
    command_reference: str
    command_type: SettlementCommandType
    priority: int = Field(ge=1, le=9999)


class CancelRebookRequest(ApiModel):
    original_instruction_id: str
    cancellation_reference: str
    replacement_reference: str
    changes: list[AmendmentChange] = Field(min_length=1, max_length=12)


class CancelRebookResponse(ApiModel):
    decision: AmendmentDecisionResponse
    cancellation: GeneratedMessage
    cancellation_status: GeneratedMessage
    replacement: GeneratedMessage
    before_values: dict[str, Any]
    after_values: dict[str, Any]


class InterpretScenarioRequest(ApiModel):
    text: str = Field(min_length=1, max_length=50_000)
    profile_id: str = "BASE_DEMO_V1"
    current_scenario: SettlementScenario | None = None
    confirmed_fields: list[CanonicalFieldPath] = Field(default_factory=list)


class InterpretedIntent(ApiModel):
    lifecycle: Lifecycle | None = None
    direction: Direction | None = None
    payment_type: PaymentType | None = None
    transaction_type: TransactionType | None = None
    function: MessageFunction | None = None
    response_action: ResponseAction | None = None
    inferred_fields: list[str] = Field(default_factory=list)


class ExtractedBusinessField(ApiModel):
    field_path: CanonicalFieldPath
    value: str
    source: str
    evidence_start: int | None = None
    evidence_end: int | None = None
    placeholder_id: str | None = None


class InterpretationConflict(ApiModel):
    field_path: CanonicalFieldPath
    existing_value: str
    proposed_value: str
    message: str


class AiMetadata(ApiModel):
    used: bool = False
    provider: AiSource = AiSource.DETERMINISTIC_NON_AI
    model: str | None = None
    primary_model: str | None = None
    escalated: bool = False
    escalation_reason: str | None = None
    prompt_version: str = "settlement-intent-v2"
    schema_version: str = "settlement-interpretation-v2"
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    latency_ms: int = 0
    attempt_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    reported_cost: Decimal | None = None
    outcome_code: str = "DETERMINISTIC_NON_AI"
    processing_source: AiProcessingSource = AiProcessingSource.DETERMINISTIC
    api_calls: int = 0
    cache_hit: bool = False
    cache_namespace: str | None = None
    cache_age_seconds: int | None = None
    original_cached_total_tokens: int = 0
    tokens_avoided: int = 0
    calls_avoided: int = 0
    cost_avoided: Decimal | None = None
    knowledge_version: str = "KB_2026_08_05_V2"


class ScenarioInterpretation(ApiModel):
    scenario: SettlementScenario
    resolution: MessageResolution
    detected_fields: list[str]
    explanation: str
    requires_business_confirmation: bool
    intent: InterpretedIntent | None = None
    extracted_fields: list[ExtractedBusinessField] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    missing_decisions: list[str] = Field(default_factory=list)
    conflicts: list[InterpretationConflict] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    requires_clarification: bool = False
    ai: AiMetadata = Field(default_factory=AiMetadata)


class AiTelemetrySnapshot(ApiModel):
    request_count: int
    success_count: int
    failure_count: int
    primary_count: int
    escalation_count: int
    schema_retry_count: int
    budget_rejection_count: int
    rate_limit_count: int
    average_latency_ms: int
    p95_latency_ms: int
    input_characters: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    reported_cost: Decimal
    failures_by_code: dict[str, int]
    live_api_interactions: int = 0
    cache_hit_interactions: int = 0
    deterministic_interactions: int = 0
    tokens_avoided: int = 0
    calls_avoided: int = 0
    estimated_cost_avoided: Decimal = Decimal("0")


class AiHealthResponse(ApiModel):
    configured: bool
    mode: str
    provider: str
    primary_model: str
    escalation_model: str
    escalation_enabled: bool
    circuit_state: AiCircuitState
    last_successful_call_at: datetime | None = None
    privacy_enforcement_enabled: bool
    require_parameters: bool
    data_collection: str
    zdr_required: bool
    prompt_version: str
    schema_version: str
    telemetry: AiTelemetrySnapshot
    cache_enabled: bool = False
    cache_key_version: str = "v1"
    knowledge_version: str = "KB_2026_08_05_V2"


class AiUsageInteractionResponse(ApiModel):
    interaction_id: str
    operation_type: str
    source: AiProcessingSource
    provider: str | None = None
    model: str | None = None
    escalated: bool
    cache_hit: bool
    cache_namespace: str | None = None
    cache_entry_age_seconds: int | None = None
    live_api_call_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    provider_reported_cost: Decimal | None = None
    latency_ms: int
    tokens_avoided: int
    calls_avoided: int
    estimated_cost_avoided: Decimal | None = None
    prompt_version: str
    schema_version: str
    knowledge_version: str
    profile_version: str | None = None
    outcome_code: str
    created_at: datetime


class AiUsageSummaryResponse(ApiModel):
    period_days: int
    interactions: int
    deterministic_interactions: int
    live_api_calls: int
    cache_hits: int
    cache_hit_rate: float
    tokens_consumed: int
    tokens_avoided: int
    api_calls_avoided: int
    provider_reported_cost: Decimal
    estimated_cost_avoided: Decimal
    average_latency_ms: int


class AiCacheStatsResponse(ApiModel):
    enabled: bool
    key_version: str
    l1_entries: int
    l1_maximum: int
    entries: int
    active_entries: int
    total_hits: int
    privacy_safe: bool = True


class AiCacheDiagnosisResponse(ApiModel):
    enabled: bool
    securely_configured: bool
    persistent_store_available: bool
    key_version: str
    namespaces: list[str]
    stores_prompt_content: bool = False
    stores_placeholder_mappings: bool = False
    status: str


class BulkRowResult(ApiModel):
    row_number: int
    scenario_id: str | None = None
    status: str
    resolved_message_type: MessageType | None = None
    message_id: str | None = None
    generated_filename: str | None = None
    profile_id: str | None = None
    profile_version: str | None = None
    validation_status: ValidationStatus | None = None
    error_count: int = 0
    warning_count: int = 0
    expected_negative_failure: bool = False
    findings: list[ValidationFinding] = Field(default_factory=list)


class BulkGenerateResponse(ApiModel):
    report_id: str
    total_rows: int
    generated_rows: int
    failed_rows: int
    row_results: list[BulkRowResult]
    download_path: str
    disclaimer: str


class DemoResetResponse(ApiModel):
    removed_messages: int
    seeded_messages: int
    root_instruction_id: str
    lifecycle_path: str


class ReportMetadataResponse(ApiModel):
    report_id: str
    report_payload: dict[str, Any]
    download_path: str
