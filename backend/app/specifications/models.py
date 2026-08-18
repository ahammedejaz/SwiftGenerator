from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import ConfigDict, Field

from app.domain.models import ApiModel
from app.knowledge.models import (
    InputKind,
    PresenceRule,
    RuleLayer,
    SourceType,
    WorkflowModuleId,
)


class CapabilityState(StrEnum):
    PRODUCTION_CAPABLE = "PRODUCTION_CAPABLE"
    UAT_READY = "UAT_READY"
    PARTIAL = "PARTIAL"
    CATALOGUE_ONLY = "CATALOGUE_ONLY"
    DISABLED = "DISABLED"
    UNSUPPORTED = "UNSUPPORTED"


class VerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    CLIENT_VERIFIED = "CLIENT_VERIFIED"
    EXTERNAL_VALIDATION_REQUIRED = "EXTERNAL_VALIDATION_REQUIRED"
    UNVERIFIED = "UNVERIFIED"
    DEPRECATED = "DEPRECATED"


class VerificationMethod(StrEnum):
    SOURCE_IMPORT = "SOURCE_IMPORT"
    APPROVED_REVIEW = "APPROVED_REVIEW"
    APPROVED_REPOSITORY_REVIEW = "APPROVED_REPOSITORY_REVIEW"


class SpecificationSource(ApiModel):
    source_type: SourceType
    source_reference: str
    standards_release: str
    profile_id: str | None = None
    profile_version: str | None = None
    verification_status: VerificationStatus
    verified_at: datetime
    verification_method: VerificationMethod


class SequenceSpecification(ApiModel):
    path: str
    code: str
    parent_path: str | None = None
    order: int = Field(ge=1)
    min_occurs: int = Field(ge=0)
    max_occurs: int = Field(ge=1, le=10_000)
    insert_after_tag: str | None = None


class FieldSpecification(ApiModel):
    row_id: str
    row_number: int
    message_type: str
    workflow_module: WorkflowModuleId
    sequence_path: str
    sequence_code: str
    tag: str
    option: str
    qualifier: str | None = None
    business_path: str
    business_name: str
    technical_name: str
    presence: PresenceRule
    min_occurs: int
    max_occurs: int
    repeatable: bool
    format: str
    allowed_options: list[str]
    allowed_codes: list[str]
    code_list: str | None = None
    input_kind: InputKind = InputKind.TEXT
    #: The literal the composer writes in front of the value. Callers never supply it.
    literal_prefix: str | None = None
    identifier_types: list[str] = Field(default_factory=list)
    #: Rows sharing a group are alternative field options for the same business value.
    choice_group: str | None = None
    max_length: int | None = None
    condition_expression: str | None = None
    condition_explanation: str | None = None
    rule_layer: RuleLayer
    knowledge_id: str
    source: SpecificationSource
    form_supported: bool = True
    composer_supported: bool = True
    parser_supported: bool = True
    validator_supported: bool = True


class MessageSpecification(ApiModel):
    message_type: str
    name: str
    scope: str
    #: The catalogue one-liner, owned by the manifest rather than a dict in code.
    short_description: str = ""
    capability: CapabilityState
    capability_explanation: str
    workflow_module: WorkflowModuleId
    standards_release: str
    registry_version: str
    authoritative_completeness_known: bool
    sequences: list[SequenceSpecification]
    fields: list[FieldSpecification]
    source: SpecificationSource


class CatalogueMessage(ApiModel):
    message_type: str
    name: str
    capability: CapabilityState = CapabilityState.CATALOGUE_ONLY
    message: str = "Specification visible; generation not implemented."
    source_reference: str


class MessageCatalogue(ApiModel):
    supported: list[MessageSpecification]
    catalogue_only: list[CatalogueMessage]
    registry_version: str


class CoverageMetric(ApiModel):
    covered: int
    configured: int
    percentage: float


class MessageCoverage(ApiModel):
    message_type: str
    capability: CapabilityState
    authoritative_completeness_known: bool
    configured_format_rows: int
    knowledge_records: CoverageMetric
    form_supported_fields: CoverageMetric
    composer_supported_fields: CoverageMetric
    parser_supported_fields: CoverageMetric
    validator_supported_fields: CoverageMetric
    sample_covered_fields: CoverageMetric
    golden_tested_fields: CoverageMetric
    production_gate_passed: bool
    gaps: list[str]


class CoverageReport(ApiModel):
    registry_version: str
    generated_at: datetime
    messages: list[MessageCoverage]
    total_configured_rows: int
    authoritative_completeness_known: bool


class SpecificationManifest(ApiModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    registry_version: str
    standards_release: str
    authoritative_completeness_known: bool
    source: SpecificationSource
    messages: list[dict[str, object]]
    catalogue_only: list[CatalogueMessage] = Field(default_factory=list)
