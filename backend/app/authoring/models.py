from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, field_validator

from app.domain.enums import MessageType
from app.domain.models import ApiModel
from app.specifications.models import CapabilityState


class PlatformRole(StrEnum):
    VIEWER = "VIEWER"
    AUTHOR = "AUTHOR"
    REVIEWER = "REVIEWER"
    APPROVER = "APPROVER"
    SUBMITTER = "SUBMITTER"
    PROFILE_ADMIN = "PROFILE_ADMIN"
    SECURITY_ADMIN = "SECURITY_ADMIN"
    AUDITOR = "AUDITOR"


class DataClassification(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    FINANCIAL_SENSITIVE = "FINANCIAL_SENSITIVE"
    SECRET = "SECRET"


class FieldValueSource(StrEnum):
    USER_ENTERED = "USER_ENTERED"
    PROFILE_DEFAULT = "PROFILE_DEFAULT"
    SYSTEM_DERIVED = "SYSTEM_DERIVED"
    IMPORTED_EXCEL = "IMPORTED_EXCEL"
    IMPORTED_API = "IMPORTED_API"
    SAMPLE_DATA = "SAMPLE_DATA"


class DraftStatus(StrEnum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    REVIEW_REQUESTED = "REVIEW_REQUESTED"
    APPROVED = "APPROVED"
    QUEUED = "QUEUED"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    REJECTED = "REJECTED"
    NACKED = "NACKED"
    FAILED = "FAILED"
    RETRY_PENDING = "RETRY_PENDING"
    CANCELLED = "CANCELLED"


class ValidationLevel(StrEnum):
    CANONICAL_VALID = "CANONICAL_VALID"
    STRUCTURE_VALID = "STRUCTURE_VALID"
    FORMAT_VALID = "FORMAT_VALID"
    NETWORK_RULES_LOCALLY_VALID = "NETWORK_RULES_LOCALLY_VALID"
    USAGE_RULES_LOCALLY_VALID = "USAGE_RULES_LOCALLY_VALID"
    CLIENT_PROFILE_VALID = "CLIENT_PROFILE_VALID"
    MARKET_PROFILE_VALID = "MARKET_PROFILE_VALID"
    EXTERNAL_VALIDATION_PASSED = "EXTERNAL_VALIDATION_PASSED"
    APPROVED_FOR_SUBMISSION = "APPROVED_FOR_SUBMISSION"


class ValidationLevelState(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    NOT_EVALUATED = "NOT_EVALUATED"
    EXTERNAL_EVIDENCE_REQUIRED = "EXTERNAL_EVIDENCE_REQUIRED"


class OutputMode(StrEnum):
    TEXT_BLOCK_ONLY = "TEXT_BLOCK_ONLY"
    FIN_APPLICATION_MESSAGE = "FIN_APPLICATION_MESSAGE"
    RJE_SINGLE = "RJE_SINGLE"
    RJE_BATCH = "RJE_BATCH"
    CLIENT_CONNECTOR_PAYLOAD = "CLIENT_CONNECTOR_PAYLOAD"


class ConnectorType(StrEnum):
    DOWNLOAD_ONLY = "DOWNLOAD_ONLY"
    HTTPS_UAT = "HTTPS_UAT"
    SFTP_FILE_DROP = "SFTP_FILE_DROP"
    LOCAL_SECURE_FILE_DROP = "LOCAL_SECURE_FILE_DROP"
    MQ_ADAPTER = "MQ_ADAPTER"
    ALLIANCE_ACCESS_FILE_ADAPTER = "ALLIANCE_ACCESS_FILE_ADAPTER"
    ALLIANCE_ACCESS_MQ_ADAPTER = "ALLIANCE_ACCESS_MQ_ADAPTER"
    ALLIANCE_ACCESS_SOAP_ADAPTER = "ALLIANCE_ACCESS_SOAP_ADAPTER"
    ALLIANCE_LITE2_AUTOCLIENT_FILE_ADAPTER = "ALLIANCE_LITE2_AUTOCLIENT_FILE_ADAPTER"
    CLIENT_CUSTOM_ADAPTER = "CLIENT_CUSTOM_ADAPTER"
    MOCK_UAT = "MOCK_UAT"


class ConnectorEnvironment(StrEnum):
    DOWNLOAD = "DOWNLOAD"
    UAT = "UAT"
    PRODUCTION = "PRODUCTION"


class SessionUser(ApiModel):
    user_id: str
    tenant_id: str
    display_name: str
    roles: set[PlatformRole]


class SessionResponse(ApiModel):
    authenticated: bool
    user: SessionUser | None = None
    auth_mode: str
    expires_at: datetime | None = None


class DevelopmentLoginRequest(ApiModel):
    identity: str = Field(min_length=2, max_length=40)


class DraftCreateRequest(ApiModel):
    message_type: MessageType
    profile_id: str = "BASE_DEMO_V1"


class DraftUpdateRequest(ApiModel):
    profile_id: str = Field(min_length=3, max_length=80)


class SequenceCreateRequest(ApiModel):
    sequence_path: str = Field(min_length=1, max_length=96)
    parent_sequence_id: str | None = None


class FieldUpsertRequest(ApiModel):
    row_id: str = Field(min_length=3, max_length=160)
    sequence_id: str
    value: str = Field(min_length=1, max_length=2_000)
    source: FieldValueSource = FieldValueSource.USER_ENTERED
    confirmed: bool = True

    @field_validator("value")
    @classmethod
    def reject_control_and_formula_payloads(cls, value: str) -> str:
        if any(ord(character) < 32 and character not in "\r\n" for character in value):
            raise ValueError("Field values cannot contain control characters")
        if value.startswith(("=", "+", "-", "@")):
            raise ValueError("Formula-like field values are rejected")
        if "{1:" in value or "{2:" in value or "{4:" in value:
            raise ValueError("Field values cannot contain FIN block fragments")
        return value


class DraftSequence(ApiModel):
    sequence_id: str
    sequence_path: str
    parent_sequence_id: str | None
    occurrence: int


class DraftField(ApiModel):
    field_id: str
    sequence_id: str
    row_id: str
    value: str
    masked: bool
    source: FieldValueSource
    confirmed: bool
    classification: DataClassification


class DraftResponse(ApiModel):
    draft_id: str
    message_type: MessageType
    profile_id: str
    profile_version: str
    standards_release: str
    capability: CapabilityState
    status: DraftStatus
    revision: int
    created_by: str
    sequences: list[DraftSequence]
    fields: list[DraftField]
    current_checksum: str | None = None
    validation_levels: dict[ValidationLevel, ValidationLevelState] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class LineMapping(ApiModel):
    line_number: int
    sequence_path: str
    row_id: str | None = None
    tag: str
    qualifier: str | None = None
    value_source: FieldValueSource | None = None
    classification: DataClassification | None = None


class ComposeResponse(ApiModel):
    draft_id: str
    revision: int
    message_type: MessageType
    block_4: str
    checksum: str
    line_mappings: list[LineMapping]
    validation_levels: dict[ValidationLevel, ValidationLevelState]
    findings: list[str]
    capability: CapabilityState
    disclaimer: str


class FinEnvelopeRequest(ApiModel):
    output_mode: OutputMode
    sender_logical_terminal: str | None = Field(default=None, max_length=12)
    receiver_address: str | None = Field(default=None, max_length=12)
    session_number: str | None = Field(default=None, pattern=r"^\d{4}$")
    sequence_number: str | None = Field(default=None, pattern=r"^\d{6}$")
    priority: str = Field(default="N", pattern=r"^[NU]$")
    message_user_reference: str | None = Field(default=None, max_length=16)


class DownloadFormat(StrEnum):
    BLOCK4 = "block4"
    FIN = "fin"
    TXT = "txt"
    RJE = "rje"
    CANONICAL_JSON = "canonical-json"
    VALIDATION_JSON = "validation-json"
    VALIDATION_HTML = "validation-html"
    EVIDENCE_ZIP = "evidence-zip"


class ReviewResponse(ApiModel):
    draft_id: str
    status: DraftStatus
    revision: int


class ApprovalResponse(ApiModel):
    draft_id: str
    status: DraftStatus
    revision: int
    approved_by: str
    checksum: str


class ConnectorSummary(ApiModel):
    connector_id: str
    name: str
    connector_type: ConnectorType
    environment: ConnectorEnvironment
    capability: CapabilityState
    destination_alias: str
    active: bool


class SubmissionRequest(ApiModel):
    connector_id: str
    idempotency_key: str = Field(min_length=16, max_length=128)
    confirm_production: bool = False


class SubmissionResponse(ApiModel):
    submission_id: str
    draft_id: str
    revision: int
    status: DraftStatus
    connector: ConnectorSummary
    checksum: str
    attempt_count: int
    provider_message_id: str | None = None
    client_correlation_id: str | None = None
    safe_response_code: str | None = None
    acknowledgement_reference: str | None = None


class ExternalValidationImportRequest(ApiModel):
    message_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider_type: str = Field(min_length=3, max_length=64)
    profile_id: str
    standards_release: str
    passed: bool
    validated_at: datetime
    safe_findings: list[dict[str, str]] = Field(default_factory=list, max_length=500)


class AuditEventResponse(ApiModel):
    event_id: str
    action: str
    resource_type: str
    resource_id: str
    actor_id: str | None
    safe_metadata: dict[str, object]
    created_at: datetime


class MessageImportRequest(ApiModel):
    raw_message: str = Field(min_length=1, max_length=100_000)
    profile_id: str = "BASE_DEMO_V1"


class UnsupportedImportField(ApiModel):
    line_number: int
    raw_line: str
    reason: str


class MessageImportResponse(ApiModel):
    draft: DraftResponse
    composition: ComposeResponse
    unsupported_fields: list[UnsupportedImportField]
    original_checksum: str
    round_trip_equivalent: bool
