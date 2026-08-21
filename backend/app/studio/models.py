"""Format-neutral request and response contracts for the Financial Message Studio.

These models are the single contract shared by the browser UI, the JSON automation API
and the Excel automation API. Nothing in the studio is reachable from the UI alone.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator, model_validator

from app.domain.models import ApiModel
from app.studio.capability import CapabilityDimensions


class MessageFormat(StrEnum):
    """Top-level standard family. MT never produces XML; MX never produces FIN blocks."""

    MT = "MT"
    MX = "MX"


class BusinessArea(StrEnum):
    PAYMENTS_CLEARING_SETTLEMENT = "PAYMENTS_CLEARING_SETTLEMENT"
    PAYMENT_INITIATION = "PAYMENT_INITIATION"
    CASH_MANAGEMENT = "CASH_MANAGEMENT"
    SECURITIES_SETTLEMENT = "SECURITIES_SETTLEMENT"
    SECURITIES_MANAGEMENT = "SECURITIES_MANAGEMENT"
    SECURITIES_EVENTS = "SECURITIES_EVENTS"
    SETTLEMENT_COMMANDS = "SETTLEMENT_COMMANDS"
    PENALTIES = "PENALTIES"
    CORPORATE_ACTIONS = "CORPORATE_ACTIONS"
    # MT categories, for packs compiled from source evidence. Catalogue buckets only.
    CUSTOMER_PAYMENTS = "CUSTOMER_PAYMENTS"
    FINANCIAL_INSTITUTION_TRANSFERS = "FINANCIAL_INSTITUTION_TRANSFERS"
    TREASURY_MARKETS = "TREASURY_MARKETS"
    COLLECTIONS_CASH_LETTERS = "COLLECTIONS_CASH_LETTERS"
    SECURITIES_MARKETS = "SECURITIES_MARKETS"
    PRECIOUS_METALS_SYNDICATIONS = "PRECIOUS_METALS_SYNDICATIONS"
    DOCUMENTARY_CREDITS_GUARANTEES = "DOCUMENTARY_CREDITS_GUARANTEES"
    TRAVELLERS_CHEQUES = "TRAVELLERS_CHEQUES"
    SYSTEM_MESSAGES = "SYSTEM_MESSAGES"
    COMMON_GROUP = "COMMON_GROUP"
    #: Compiled packs from families outside the four configured areas land here until a
    #: reviewer assigns them a real area. A catalogue bucket, never a capability claim.
    OTHER = "OTHER"


BUSINESS_AREA_LABELS: dict[BusinessArea, str] = {
    BusinessArea.PAYMENTS_CLEARING_SETTLEMENT: "Payments Clearing & Settlement",
    BusinessArea.PAYMENT_INITIATION: "Payment Initiation",
    BusinessArea.CASH_MANAGEMENT: "Cash Management",
    BusinessArea.SECURITIES_SETTLEMENT: "Securities Settlement",
    BusinessArea.SECURITIES_MANAGEMENT: "Securities Management",
    BusinessArea.SECURITIES_EVENTS: "Securities Events",
    BusinessArea.SETTLEMENT_COMMANDS: "Settlement Commands",
    BusinessArea.PENALTIES: "Penalties",
    BusinessArea.CORPORATE_ACTIONS: "Corporate Actions",
    BusinessArea.CUSTOMER_PAYMENTS: "Customer Payments & Cheques",
    BusinessArea.FINANCIAL_INSTITUTION_TRANSFERS: "Financial Institution Transfers",
    BusinessArea.TREASURY_MARKETS: "Treasury Markets",
    BusinessArea.COLLECTIONS_CASH_LETTERS: "Collections & Cash Letters",
    BusinessArea.SECURITIES_MARKETS: "Securities Markets",
    BusinessArea.PRECIOUS_METALS_SYNDICATIONS: "Precious Metals & Syndications",
    BusinessArea.DOCUMENTARY_CREDITS_GUARANTEES: "Documentary Credits & Guarantees",
    BusinessArea.TRAVELLERS_CHEQUES: "Travellers Cheques",
    BusinessArea.SYSTEM_MESSAGES: "System Messages",
    BusinessArea.COMMON_GROUP: "Common Group",
    BusinessArea.OTHER: "Other Configured Messages",
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
    #: Rules a market or infrastructure applies on top of the standard. Sits between the
    #: base rules and the client's own, because a client narrows a market, not the reverse.
    MARKET_PRACTICE = "MARKET_PRACTICE"
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


class InputKind(StrEnum):
    """The control a field deserves.

    Published so a client — the browser, an automation harness, a spreadsheet generator —
    can build the same safe form the studio does, instead of inferring it from whether a
    code list happens to be present.
    """

    TEXT = "TEXT"
    SELECT = "SELECT"
    DATE = "DATE"
    AMOUNT = "AMOUNT"
    QUANTITY = "QUANTITY"
    NARRATIVE = "NARRATIVE"
    REFERENCE = "REFERENCE"
    IDENTIFIER = "IDENTIFIER"
    PARTY_BIC = "PARTY_BIC"
    PARTY_PROPRIETARY = "PARTY_PROPRIETARY"
    INDICATOR = "INDICATOR"


class SampleVariant(StrEnum):
    MINIMAL = "MINIMAL"
    TYPICAL = "TYPICAL"
    FULL = "FULL"


# --------------------------------------------------------------------------------------
# Catalogue
# --------------------------------------------------------------------------------------


class Lane(StrEnum):
    """Which registry a message resolves from. Never implicit for the preview lane."""

    CONFIGURED = "CONFIGURED"
    KNOWLEDGE_PREVIEW = "KNOWLEDGE_PREVIEW"


class Readiness(StrEnum):
    KNOWLEDGE_ONLY = "KNOWLEDGE_ONLY"
    STRUCTURE_AVAILABLE = "STRUCTURE_AVAILABLE"
    STRUCTURE_VERIFIED = "STRUCTURE_VERIFIED"
    GENERATION_READY = "GENERATION_READY"


class LaneProvenance(ApiModel):
    """What a generated message in either lane rests on. Stated, never implied."""

    lane: Lane
    release: str | None = None
    release_lane: str | None = None
    structure_source: str
    rule_status: str
    validation_level: str
    capability_statement: str
    source_provenance: list[str] = Field(default_factory=list)


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
    #: What is actually established about this message, per authority layer, plus the
    #: one-sentence reading of it. Derived — see app/studio/capability.py.
    capability: CapabilityDimensions | None = None
    capability_summary: str = ""
    # -- Phase 6: lane, release and readiness. Configured entries report their defaults.
    lane: Lane = Lane.CONFIGURED
    release: str | None = None
    release_lane: str | None = None
    readiness: Readiness = Readiness.GENERATION_READY
    readiness_label: str = "Configured & validated"
    blockers: list[str] = Field(default_factory=list)
    structure_source: str | None = None
    rules_status: str = "CONFIGURED"
    knowledge_sources: int = 0
    ai_sample_ready: bool = False
    automation_ready: bool = True


class CatalogueBusinessArea(ApiModel):
    id: BusinessArea
    label: str
    message_count: int


class CatalogueFormat(ApiModel):
    id: MessageFormat
    label: str
    description: str
    business_areas: list[CatalogueBusinessArea]
    #: Every listed entry in this format, both lanes.
    message_count: int
    #: Entries served by the configured lane (reviewed packs); the rest are preview.
    configured_message_count: int = 0


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


class AllowedValue(ApiModel):
    """One controlled code, with the words a person uses for it.

    ``TRAD`` alone asks a tester to already know the standard. ``TRAD — Trade`` does not.
    The label and description come from the shared code-list configuration, so the browser,
    this API and the Excel workbook cannot offer different vocabularies.
    """

    code: str
    label: str
    description: str = ""


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
    #: Kept for existing clients. `allowed_values` carries the same codes with their words.
    allowed_codes: list[str] = Field(default_factory=list)
    allowed_values: list[AllowedValue] = Field(default_factory=list)
    #: Name of the shared code list the values came from, when one backs them.
    code_list: str | None = None
    input_kind: InputKind = InputKind.TEXT
    #: The literal the composer writes in front of the value, if any. When this is set,
    #: `user_enters_literal_prefix` is false: the caller supplies the value alone.
    literal_prefix: str | None = None
    user_enters_literal_prefix: bool = False
    identifier_types: list[str] = Field(default_factory=list)
    max_length: int | None = None
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
    #: 0 when the whole group may be absent; its mandatory fields are then owed only once
    #: the group is used.
    min_occurs: int = 1


class MessageSpec(ApiModel):
    format: MessageFormat
    message_type: str
    version: str | None = None
    name: str
    business_area: BusinessArea
    scope: str
    #: The catalogue one-liner. Owned by the specification (manifest / MX spec), not code.
    short_description: str = ""
    namespace: str | None = None
    groups: list[SpecGroup]
    fields: list[SpecField]
    output_modes: list[OutputMode]
    authoritative_completeness_known: bool
    source_reference: str
    standards_release: str
    limitations: list[str] = Field(default_factory=list)
    capability: CapabilityDimensions | None = None
    capability_summary: str = ""
    lane: Lane = Lane.CONFIGURED
    release: str | None = None
    capability_statement: str | None = None
    structure_source: str | None = None


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
    #: CONFIGURED unless the caller asks for the knowledge-preview lane by name.
    lane: Lane = Lane.CONFIGURED
    #: A standards release (MT) or message definition version (MX) within the lane.
    release: str | None = Field(default=None, max_length=32)


class ValidateRequest(GenerateRequest):
    persist: bool = False


# --------------------------------------------------------------------------------------
# Generation output
# --------------------------------------------------------------------------------------


class ValidationOccurrence(ApiModel):
    sequence_path: str
    occurrence: int = Field(ge=1)
    path: str
    lineage: list[str] = Field(default_factory=list)


class ValidationIssue(ApiModel):
    rule_id: str
    severity: IssueSeverity
    layer: ValidationLayer
    field: str | None = None
    location: str | None = None
    occurrence: ValidationOccurrence | None = None
    message: str
    expected: str | None = None
    current_value: str | None = None
    suggestion: str | None = None

    # ---- rule-pack provenance; absent on the platform's own built-in checks ------------
    #: Which authority layer produced this, in words — "Market practice rule".
    rule_layer: str | None = None
    #: The installed rule pack the rule came from.
    rule_pack_id: str | None = None
    #: The source identity and segment the rule was derived from. Identity and location
    #: only — never licensed prose, which is why this is a reference and not an excerpt.
    source_reference: str | None = None
    #: The rule's review state. Only ``REVIEWED`` rules are ever loaded, so this reads
    #: `REVIEWED` in practice; it is published so an automation caller can assert it.
    review_status: str | None = None


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
    lane: Lane = Lane.CONFIGURED
    provenance: LaneProvenance | None = None


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
    #: The lane the scenario was generated in and what that rests on (Phase 6). A failed
    #: scenario has no provenance because nothing was generated.
    lane: Lane = Lane.CONFIGURED
    provenance: LaneProvenance | None = None


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


class FieldRuleSummary(ApiModel):
    """One installed, reviewed rule that names a field.

    Candidate rules never appear here. A candidate is a reviewer's artifact; showing one
    to a tester would present a model's proposal as a property of the standard.
    """

    rule_id: str
    #: The authority layer in words — "Market practice rule".
    layer: str
    title: str
    #: What the rule asks for, in a sentence.
    meaning: str
    #: The source identity and location that established it. Never licensed prose.
    source_reference: str
    review_status: str


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
    #: Kept for existing clients. `allowed_values` carries the same codes with their words.
    allowed_codes: list[str] = Field(default_factory=list)
    allowed_values: list[AllowedValue] = Field(default_factory=list)
    #: Name of the shared code list the values came from, when one backs them.
    code_list: str | None = None
    input_kind: InputKind = InputKind.TEXT
    #: The literal the composer writes in front of the value, if any. When this is set,
    #: `user_enters_literal_prefix` is false: the caller supplies the value alone.
    literal_prefix: str | None = None
    user_enters_literal_prefix: bool = False
    identifier_types: list[str] = Field(default_factory=list)
    max_length: int | None = None
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
    #: Reviewed rules that name this field, in layer order. Empty when none are installed.
    rules: list[FieldRuleSummary] = Field(default_factory=list)


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


# --------------------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------------------


class DiffKind(StrEnum):
    UNCHANGED = "UNCHANGED"
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    CHANGED = "CHANGED"


class DiffReason(StrEnum):
    USER_EDIT = "USER_EDIT"
    NORMALISATION = "NORMALISATION"
    IMPORT_DROPPED = "IMPORT_DROPPED"
    NOT_REPRODUCED = "NOT_REPRODUCED"
    UNEXPLAINED = "UNEXPLAINED"


class DiffBasis(StrEnum):
    FIN_LINES = "FIN_LINES"
    CANONICAL_XML = "CANONICAL_XML"


class DiffLine(ApiModel):
    kind: DiffKind
    original_line: int | None = None
    regenerated_line: int | None = None
    original_text: str | None = None
    regenerated_text: str | None = None
    #: Absent on an unchanged line; always present otherwise.
    reason: DiffReason | None = None
    explanation: str | None = None
    #: The business field, where the line carries one.
    field: str | None = None
    location: str | None = None


class DiffSummary(ApiModel):
    identical: bool
    unchanged: int
    added: int
    removed: int
    changed: int
    #: Differences with a known, benign cause. Never a reason to investigate.
    expected: int
    #: Content the original held that the configured subset could not carry.
    dropped: int
    #: The only figure worth acting on.
    unexplained: int
    by_reason: dict[str, int]


class MessageDiff(ApiModel):
    format: MessageFormat
    basis: DiffBasis
    #: What was compared, in words — "the FIN message", "the Document without its header".
    compared: str
    #: False when the messages were too large, or too broken, to list the differences of.
    #: ``summary.identical`` still answers the question that matters; ``lines`` is empty.
    comparable: bool = True
    not_compared_reason: str | None = None
    summary: DiffSummary
    lines: list[DiffLine]
    #: One plain sentence per reason that actually occurs, in the order they occur.
    notes: list[str] = []


class ImportRequest(ApiModel):
    """Read an existing message back into canonical values.

    Normally only the raw text is supplied: the format and the message type are worked out
    from the message itself. An MX document names itself in its namespace, and a complete
    FIN message names itself in its application header — both are more trustworthy than a
    caller-supplied label, which would let a mislabelled file be parsed against the wrong
    specification.

    ``messageType`` exists for the one case that genuinely cannot name itself: a pasted MT
    text block. It is consulted only then. A header that disagrees with it is a refusal.
    """

    text: str = Field(default="", max_length=1_000_000)
    #: Accepted for callers written against the MX-only import. Prefer ``text``.
    xml: str | None = Field(default=None, max_length=1_000_000)
    message_type: str | None = Field(default=None, max_length=16)
    profile_id: str = "BASE_DEMO_V1"
    #: Read against a local Structure Pack instead of the configured registries.
    lane: Lane = Lane.CONFIGURED
    release: str | None = Field(default=None, max_length=32)
    scenario_id: str | None = Field(default=None, max_length=64)
    output_modes: list[OutputMode] | None = None
    #: Imports are a reading exercise by default; nothing is kept unless asked for.
    persist: bool = False

    @property
    def content(self) -> str:
        return self.text or self.xml or ""

    @model_validator(mode="after")
    def require_content(self) -> ImportRequest:
        if not self.content.strip():
            raise ValueError("Supply the message to import in 'text'")
        return self


class ImportResult(ApiModel):
    """What the document turned out to contain, and what it regenerates to.

    ``elements`` (MX) and ``fields`` (MT) are the canonical form — exactly the shapes
    accepted by ``POST /api/v1/messages/generate``, so the round trip is closed: edit the
    values, send them back, and the same composer that produced the original produces the
    new one.
    """

    format: MessageFormat
    message_type: str
    version: str | None
    namespace: str | None
    profile_id: str
    #: MX: whether the document carried a business application header.
    app_hdr_present: bool
    #: MT: which FIN blocks the text carried, in order. ``["4"]`` for a pasted text block.
    fin_blocks: list[str] = Field(default_factory=list)
    #: How many values were read, whichever format they came from.
    element_count: int
    elements: list[ElementInput] = Field(default_factory=list)
    fields: list[FieldInput] = Field(default_factory=list)
    envelope: EnvelopeOverride | None = None
    #: Anything the document contained that could not be imported. Never silently dropped.
    import_issues: list[ValidationIssue] = Field(default_factory=list)
    import_warnings: list[ValidationIssue] = Field(default_factory=list)
    #: The regenerated message, produced by the ordinary generation path.
    result: GenerateResult
    #: The imported message compared with the one just regenerated from it. At import time
    #: nothing has been edited yet, so every difference here is normalisation, content the
    #: configured subset could not carry, or something the studio deliberately never writes.
    diff: MessageDiff
    disclaimer: str


class DiffRequest(GenerateRequest):
    """Regenerate from these values and compare the result with a message you already have.

    Everything needed is in the request: ``original`` is re-read on the server to work out
    which values came from the message and which the caller changed, so a difference can be
    attributed without the caller having to remember what it imported.
    """

    original: str = Field(min_length=1, max_length=1_000_000)
    persist: bool = False

    def as_generate_request(self) -> GenerateRequest:
        """The generation half of this request, so the diff endpoint calls exactly the same
        path as `generate` rather than a lookalike of it."""
        return GenerateRequest(
            **self.model_dump(exclude={"original"}, by_alias=False),
        )


class DiffResult(ApiModel):
    format: MessageFormat
    message_type: str
    #: The regenerated message, produced by the ordinary generation path.
    result: GenerateResult
    diff: MessageDiff
    #: Anything the original held that could not be read back. Never silently dropped.
    import_issues: list[ValidationIssue] = Field(default_factory=list)
    import_warnings: list[ValidationIssue] = Field(default_factory=list)
    disclaimer: str
