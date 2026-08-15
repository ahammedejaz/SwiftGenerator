"""Format-neutral request and response contracts for the Financial Message Studio.

These models are the single contract shared by the browser UI, the JSON automation API
and the Excel automation API. Nothing in the studio is reachable from the UI alone.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator

from app.domain.models import ApiModel


class MessageFormat(StrEnum):
    """Top-level standard family. MT never produces XML; MX never produces FIN blocks."""

    MT = "MT"
    MX = "MX"


class BusinessArea(StrEnum):
    SECURITIES_SETTLEMENT = "SECURITIES_SETTLEMENT"
    SETTLEMENT_COMMANDS = "SETTLEMENT_COMMANDS"
    PENALTIES = "PENALTIES"
    CORPORATE_ACTIONS = "CORPORATE_ACTIONS"


BUSINESS_AREA_LABELS: dict[BusinessArea, str] = {
    BusinessArea.SECURITIES_SETTLEMENT: "Securities Settlement",
    BusinessArea.SETTLEMENT_COMMANDS: "Settlement Commands",
    BusinessArea.PENALTIES: "Penalties",
    BusinessArea.CORPORATE_ACTIONS: "Corporate Actions",
}


class FieldOrigin(StrEnum):
    """Who is accountable for a value appearing in the generated message.

    The platform only ever produces the first three. INTERFACE_GENERATED and
    NETWORK_GENERATED values are declared so that consumers can see what is deliberately
    absent; they are never fabricated.
    """

    USER_ENTERED = "USER_ENTERED"
    PROFILE_CONFIGURED = "PROFILE_CONFIGURED"
    APPLICATION_GENERATED = "APPLICATION_GENERATED"
    INTERFACE_GENERATED = "INTERFACE_GENERATED"
    NETWORK_GENERATED = "NETWORK_GENERATED"


class OutputMode(StrEnum):
    BLOCK4 = "BLOCK4"
    FIN = "FIN"
    TXT = "TXT"
    CANONICAL_JSON = "CANONICAL_JSON"
    XML = "XML"
    APPHDR = "APPHDR"
    DOCUMENT = "DOCUMENT"


MT_OUTPUT_MODES = [
    OutputMode.BLOCK4,
    OutputMode.FIN,
    OutputMode.TXT,
    OutputMode.CANONICAL_JSON,
]
MX_OUTPUT_MODES = [
    OutputMode.XML,
    OutputMode.APPHDR,
    OutputMode.DOCUMENT,
    OutputMode.CANONICAL_JSON,
]


class Presence(StrEnum):
    MANDATORY = "MANDATORY"
    CONDITIONAL = "CONDITIONAL"
    OPTIONAL = "OPTIONAL"


class IssueSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class ValidationLayer(StrEnum):
    """Ordered validation layers. Reported individually so nothing is hidden behind a bool."""

    CANONICAL = "CANONICAL"
    STRUCTURE = "STRUCTURE"
    FORMAT = "FORMAT"
    BUSINESS_RULES = "BUSINESS_RULES"
    CLIENT_PROFILE = "CLIENT_PROFILE"
    FIN_ENVELOPE = "FIN_ENVELOPE"
    XML_WELL_FORMED = "XML_WELL_FORMED"
    XSD = "XSD"
    APPHDR_CONSISTENCY = "APPHDR_CONSISTENCY"


class LayerState(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    SKIPPED = "SKIPPED"


class SampleVariant(StrEnum):
    MINIMAL = "MINIMAL"
    TYPICAL = "TYPICAL"
    FULL = "FULL"


# --------------------------------------------------------------------------------------
# Catalogue
# --------------------------------------------------------------------------------------


class CatalogueEntry(ApiModel):
    format: MessageFormat
    message_type: str
    version: str | None = None
    name: str
    short_description: str
    business_area: BusinessArea
    business_area_label: str
    generatable: bool
    output_modes: list[OutputMode]
    field_count: int
    mandatory_field_count: int
    sample_variants: list[SampleVariant]
    authoritative_completeness_known: bool
    source_reference: str
    limitations: list[str] = Field(default_factory=list)


class CatalogueBusinessArea(ApiModel):
    id: BusinessArea
    label: str
    message_count: int


class CatalogueFormat(ApiModel):
    id: MessageFormat
    label: str
    description: str
    business_areas: list[CatalogueBusinessArea]
    message_count: int


class StudioCatalogue(ApiModel):
    formats: list[CatalogueFormat]
    messages: list[CatalogueEntry]
    profiles: list[str]
    default_profile_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# --------------------------------------------------------------------------------------
# Specification (format-neutral projection used by the builder UI and Excel templates)
# --------------------------------------------------------------------------------------


class FieldExample(ApiModel):
    value: str
    explanation: str


class SpecField(ApiModel):
    """One addressable input slot: an MT format row or an MX leaf element."""

    id: str
    format: MessageFormat
    group_id: str
    group_label: str
    group_order: int
    order: int
    presence: Presence
    repeatable: bool = False
    max_occurs: int = 1

    display_name: str
    business_meaning: str
    technical_meaning: str
    why_used: str
    business_question: str
    missing_impact: str | None = None
    format_explanation: str
    allowed_codes: list[str] = Field(default_factory=list)
    examples: list[FieldExample] = Field(default_factory=list)
    common_mistakes: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    condition_explanation: str | None = None
    business_path: str | None = None

    # MT addressing
    sequence: str | None = None
    sequence_code: str | None = None
    tag: str | None = None
    qualifier: str | None = None
    option: str | None = None

    # MX addressing
    xpath: str | None = None
    data_type: str | None = None
    choice_group: str | None = None

    source_reference: str
    standards_release: str


class SpecGroup(ApiModel):
    id: str
    label: str
    description: str
    order: int
    repeatable: bool = False
    max_occurs: int = 1
    parent_id: str | None = None


class MessageSpec(ApiModel):
    format: MessageFormat
    message_type: str
    version: str | None = None
    name: str
    business_area: BusinessArea
    scope: str
    namespace: str | None = None
    groups: list[SpecGroup]
    fields: list[SpecField]
    output_modes: list[OutputMode]
    authoritative_completeness_known: bool
    source_reference: str
    standards_release: str
    limitations: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------------------
# Generation input
# --------------------------------------------------------------------------------------


class FieldInput(ApiModel):
    """An MT tag-level value.

    Addressable either by `id` (the specification row id, e.g. `MT541-A-20C-SEME`) or by
    the `sequence` / `tag` / `qualifier` triple that automation testers keep in Excel.
    """

    id: str | None = None
    sequence: str | None = None
    occurrence: int = Field(default=1, ge=1, le=100)
    tag: str | None = None
    qualifier: str | None = None
    option: str | None = None
    value: str = Field(min_length=1, max_length=2_000)

    @field_validator("value")
    @classmethod
    def reject_unsafe_values(cls, value: str) -> str:
        if any(ord(character) < 32 and character not in "\r\n" for character in value):
            raise ValueError("Field values cannot contain control characters")
        if "{1:" in value or "{2:" in value or "{4:" in value:
            raise ValueError("Field values cannot contain FIN block fragments")
        return value


class ElementInput(ApiModel):
    """An MX element-level value addressed by its absolute element path."""

    path: str = Field(min_length=2, max_length=500)
    occurrence: int = Field(default=1, ge=1, le=100)
    value: str = Field(min_length=1, max_length=2_000)

    @field_validator("value")
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        if any(ord(character) < 32 and character not in "\t\r\n" for character in value):
            raise ValueError("Element values cannot contain control characters")
        return value


class EnvelopeOverride(ApiModel):
    """Per-request envelope values.

    Anything not supplied falls back to the client profile. Nothing is invented: if a
    required envelope value is neither supplied nor profile-configured, FIN or AppHdr
    output fails closed with a named error.
    """

    sender: str | None = Field(default=None, max_length=12)
    receiver: str | None = Field(default=None, max_length=12)
    session_number: str | None = Field(default=None, pattern=r"^\d{4}$")
    sequence_number: str | None = Field(default=None, pattern=r"^\d{6}$")
    priority: str | None = Field(default=None, pattern=r"^[NU]$")
    message_user_reference: str | None = Field(default=None, max_length=16)
    business_message_identifier: str | None = Field(default=None, max_length=35)
    creation_date: str | None = Field(default=None, max_length=32)


class GenerateRequest(ApiModel):
    format: MessageFormat
    message_type: str = Field(min_length=3, max_length=32)
    profile_id: str = "BASE_DEMO_V1"
    scenario_id: str | None = Field(default=None, max_length=64)
    fields: list[FieldInput] = Field(default_factory=list, max_length=500)
    elements: list[ElementInput] = Field(default_factory=list, max_length=500)
    output_modes: list[OutputMode] | None = None
    envelope: EnvelopeOverride | None = None
    persist: bool = True


class ValidateRequest(GenerateRequest):
    persist: bool = False


# --------------------------------------------------------------------------------------
# Generation output
# --------------------------------------------------------------------------------------


class ValidationIssue(ApiModel):
    rule_id: str
    severity: IssueSeverity
    layer: ValidationLayer
    field: str | None = None
    location: str | None = None
    message: str
    expected: str | None = None
    current_value: str | None = None
    suggestion: str | None = None


class LayerResult(ApiModel):
    layer: ValidationLayer
    state: LayerState
    detail: str | None = None


class ValidationResult(ApiModel):
    valid: bool
    summary: str
    layers: list[LayerResult]
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)

    @property
    def error_count(self) -> int:
        return len(self.errors)


class EnvelopeField(ApiModel):
    """One envelope value with an explicit accountability classification."""

    block: str
    name: str
    value: str | None
    origin: FieldOrigin
    explanation: str


class MessageOutputs(ApiModel):
    block4: str | None = None
    fin: str | None = None
    txt: str | None = None
    app_hdr: str | None = None
    document: str | None = None
    xml: str | None = None
    canonical_json: dict[str, Any] | None = None


class RenderedLine(ApiModel):
    line_number: int
    text: str
    field_id: str | None = None
    display_name: str | None = None
    origin: FieldOrigin = FieldOrigin.USER_ENTERED


class GenerateResult(ApiModel):
    message_id: str | None = None
    correlation_id: str
    scenario_id: str | None = None
    format: MessageFormat
    message_type: str
    version: str | None = None
    profile_id: str
    profile_version: str
    valid: bool
    validation: ValidationResult
    outputs: MessageOutputs
    envelope_fields: list[EnvelopeField] = Field(default_factory=list)
    rendered_lines: list[RenderedLine] = Field(default_factory=list)
    checksum: str
    available_output_modes: list[OutputMode]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    disclaimer: str


class ExcelScenarioResult(ApiModel):
    scenario_id: str
    row_numbers: list[int]
    format: MessageFormat | None = None
    message_type: str | None = None
    status: str
    valid: bool = False
    validation: ValidationResult | None = None
    outputs: MessageOutputs | None = None
    message_id: str | None = None
    checksum: str | None = None


class ExcelGenerateResponse(ApiModel):
    request_id: str
    format: MessageFormat
    total_scenarios: int
    generated: int
    failed: int
    results: list[ExcelScenarioResult]
    report_id: str | None = None
    download_path: str | None = None
    disclaimer: str


class RecentMessage(ApiModel):
    message_id: str
    correlation_id: str
    scenario_id: str | None
    format: MessageFormat
    message_type: str
    profile_id: str
    valid: bool
    error_count: int
    warning_count: int
    checksum: str
    source: str
    created_at: datetime


class IntelligenceHit(ApiModel):
    id: str
    format: MessageFormat
    message_types: list[str]
    label: str
    address: str
    presence: Presence
    summary: str
    score: int = 0


class IntelligenceSearchResponse(ApiModel):
    query: str
    total: int
    results: list[IntelligenceHit]
    deterministic: bool = True
    llm_used: bool = False


class IntelligenceDetail(ApiModel):
    id: str
    format: MessageFormat
    label: str
    address: str
    message_types: list[str]
    presence: Presence
    business_meaning: str
    technical_meaning: str
    why_used: str
    format_explanation: str
    allowed_codes: list[str] = Field(default_factory=list)
    examples: list[FieldExample] = Field(default_factory=list)
    common_mistakes: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    condition_explanation: str | None = None
    data_type: str | None = None
    cardinality: str | None = None
    parent: str | None = None
    source_reference: str
    standards_release: str
    sample_lines: list[str] = Field(default_factory=list)


class SampleMessage(ApiModel):
    sample_id: str
    format: MessageFormat
    message_type: str
    variant: SampleVariant
    title: str
    description: str
    field_count: int
    inputs: list[FieldInput] = Field(default_factory=list)
    elements: list[ElementInput] = Field(default_factory=list)
