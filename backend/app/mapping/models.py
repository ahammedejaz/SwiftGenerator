from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from app.domain.models import ApiModel
from app.studio.models import (
    ElementInput,
    FieldInput,
    GenerateResult,
    Lane,
    MessageFormat,
    ValidationResult,
)


class MappingKind(StrEnum):
    DIRECT = "DIRECT"
    TRANSFORM = "TRANSFORM"
    CONDITIONAL = "CONDITIONAL"
    ONE_TO_MANY = "ONE_TO_MANY"
    MANY_TO_ONE = "MANY_TO_ONE"
    NOT_REPRESENTED = "NOT_REPRESENTED"
    TARGET_REQUIRED_MISSING = "TARGET_REQUIRED_MISSING"


class TransformName(StrEnum):
    IDENTITY = "IDENTITY"
    CONSTANT = "CONSTANT"
    MT_DATE_TO_ISO = "MT_DATE_TO_ISO"
    MT_UNIT_QUANTITY = "MT_UNIT_QUANTITY"
    MT_AMOUNT_TO_ISO = "MT_AMOUNT_TO_ISO"
    ENUM = "ENUM"
    JOIN = "JOIN"


class MappingReviewState(StrEnum):
    CANDIDATE = "CANDIDATE"
    REVIEWED = "REVIEWED"
    SYNTHETIC_TEST_ONLY = "SYNTHETIC_TEST_ONLY"


class BusinessSemantic(StrEnum):
    TRANSACTION_REFERENCE = "transaction_reference"
    TRADE_DATE = "trade_date"
    SETTLEMENT_DATE = "settlement_date"
    INSTRUMENT_IDENTIFIER = "instrument_identifier"
    QUANTITY = "quantity"
    PLACE_OF_SETTLEMENT = "place_of_settlement"
    DELIVERING_AGENT = "delivering_agent"
    RECEIVING_AGENT = "receiving_agent"
    SETTLEMENT_AMOUNT = "settlement_amount"
    CURRENCY = "currency"
    PAYMENT_TYPE = "payment_type"
    SECURITIES_MOVEMENT = "securities_movement"
    TRANSACTION_TYPE = "transaction_type"
    SAFEKEEPING_ACCOUNT = "safekeeping_account"
    MESSAGE_FUNCTION = "message_function"


class MappingIdentity(ApiModel):
    format: MessageFormat
    message_type: str
    release: str | None = None
    lane: Lane = Lane.CONFIGURED


class MappingProvenance(ApiModel):
    source_type: str
    source_reference: str
    source_checksum: str
    review_state: MappingReviewState
    reviewed_by: str | None = None
    production_eligible: bool = False
    limitations: list[str] = Field(default_factory=list)


class MappingCondition(ApiModel):
    source_ref: str
    operator: str = Field(pattern="^(PRESENT|EQUALS|NOT_EQUALS)$")
    value: str | None = None


class MappingOutput(ApiModel):
    target_ref: str
    transform: TransformName = TransformName.IDENTITY
    constant: str | None = None
    enum: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def transform_configuration(self) -> MappingOutput:
        if self.transform is TransformName.CONSTANT and self.constant is None:
            raise ValueError("A CONSTANT mapping output requires a constant")
        if self.transform is TransformName.ENUM and not self.enum:
            raise ValueError("An ENUM mapping output requires an enum table")
        return self


class MappingRule(ApiModel):
    id: str
    kind: MappingKind
    semantic: BusinessSemantic | None = None
    source_refs: list[str] = Field(default_factory=list)
    outputs: list[MappingOutput] = Field(default_factory=list)
    condition: MappingCondition | None = None
    delimiter: str = " "
    note: str | None = None

    @model_validator(mode="after")
    def shape_matches_kind(self) -> MappingRule:
        if self.kind is MappingKind.NOT_REPRESENTED:
            if not self.source_refs or self.outputs:
                raise ValueError("NOT_REPRESENTED requires source refs and no outputs")
        elif not self.outputs:
            raise ValueError(f"{self.kind.value} requires at least one output")
        if self.kind is MappingKind.CONDITIONAL and self.condition is None:
            raise ValueError("CONDITIONAL requires a condition")
        return self


class MappingPack(ApiModel):
    pack_id: str
    version: str
    source: MappingIdentity
    target: MappingIdentity
    source_structure_checksum: str = Field(pattern="^[a-f0-9]{64}$")
    target_structure_checksum: str = Field(pattern="^[a-f0-9]{64}$")
    provenance: MappingProvenance
    rules: list[MappingRule]

    @model_validator(mode="after")
    def unique_rules(self) -> MappingPack:
        ids = [rule.id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("Mapping rule IDs must be unique")
        if (
            self.provenance.production_eligible
            and self.provenance.review_state is not MappingReviewState.REVIEWED
        ):
            raise ValueError("Only a reviewed Mapping Pack may be production eligible")
        return self


class ConversionTarget(ApiModel):
    pack_id: str
    pack_version: str
    target: MappingIdentity
    review_state: str
    production_eligible: bool
    preview_only: bool
    provenance: MappingProvenance


class ConversionTargetsResponse(ApiModel):
    source: MappingIdentity
    targets: list[ConversionTarget]
    authority_note: str


class ConvertRequest(ApiModel):
    source_format: MessageFormat = MessageFormat.MT
    source_message: str | None = Field(default=None, max_length=32)
    source_release: str | None = Field(default=None, max_length=32)
    source_lane: Lane = Lane.CONFIGURED
    raw_message: str | None = Field(default=None, max_length=2_000_000)
    fields: list[FieldInput] = Field(default_factory=list, max_length=500)
    target_format: MessageFormat = MessageFormat.MX
    target_message: str = Field(max_length=32)
    target_version: str = Field(max_length=32)
    target_lane: Lane = Lane.CONFIGURED
    target_values: list[ElementInput] = Field(default_factory=list, max_length=500)
    profile_id: str = "BASE_DEMO_V1"
    mapping_pack_id: str | None = None
    allow_synthetic_preview: bool = False

    @model_validator(mode="after")
    def source_is_present(self) -> ConvertRequest:
        if not self.raw_message and (not self.source_message or not self.fields):
            raise ValueError("Supply rawMessage or sourceMessage with canonical fields")
        return self


class AppliedMapping(ApiModel):
    rule_id: str
    kind: MappingKind
    semantic: BusinessSemantic | None
    source_refs: list[str]
    target_refs: list[str]
    transform: str


class MissingTarget(ApiModel):
    field_id: str
    display_name: str
    question: str
    reason: str


class ConversionReport(ApiModel):
    source: MappingIdentity
    target: MappingIdentity
    mapping_pack_id: str
    mapping_pack_version: str
    provenance: MappingProvenance
    mapped_source_fields: list[str]
    source_fields_not_represented: list[str]
    mapped_target_fields: list[str]
    derived_target_fields: list[str]
    user_supplied_target_fields: list[str]
    target_required_missing: list[MissingTarget]
    transformations_applied: list[AppliedMapping]
    limitations: list[str]


class ConversionResponse(ApiModel):
    status: str
    target_values: list[ElementInput]
    report: ConversionReport | None
    validation: ValidationResult | None = None
    generation: GenerateResult | None = None
    output_xml: str | None = None
    message: str
