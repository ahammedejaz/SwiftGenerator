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
    #: A closed code table from source code to target code (an ``ENUM`` output).
    CODE_MAP = "CODE_MAP"
    CONDITIONAL = "CONDITIONAL"
    ONE_TO_MANY = "ONE_TO_MANY"
    MANY_TO_ONE = "MANY_TO_ONE"
    #: The source value is deliberately not carried (the reviewer decided so).
    OMIT = "OMIT"
    #: The target has no place for the source value; reported as data loss.
    NOT_REPRESENTED = "NOT_REPRESENTED"
    TARGET_REQUIRED_MISSING = "TARGET_REQUIRED_MISSING"


class TransformName(StrEnum):
    IDENTITY = "IDENTITY"
    CONSTANT = "CONSTANT"
    MT_DATE_TO_ISO = "MT_DATE_TO_ISO"
    MT_UNIT_QUANTITY = "MT_UNIT_QUANTITY"
    MT_AMOUNT_TO_ISO = "MT_AMOUNT_TO_ISO"
    #: ``6!n3!a15d`` (32A): the date part as an ISO date. SWIFT's two-digit year is read as
    #: 20YY — the deterministic convention, recorded as a limitation on every pack using it.
    MT_DATED_AMOUNT_DATE = "MT_DATED_AMOUNT_DATE"
    #: ``6!n3!a15d`` (32A): the currency and amount as ``CCY 1234.56``.
    MT_DATED_AMOUNT_TO_ISO = "MT_DATED_AMOUNT_TO_ISO"
    #: A party option-A value (``[/account]$BIC``): the BIC line alone.
    MT_PARTY_BIC = "MT_PARTY_BIC"
    ENUM = "ENUM"
    JOIN = "JOIN"


class MappingReviewState(StrEnum):
    #: Proposed, never executed.
    CANDIDATE = "CANDIDATE"
    #: Proposed with cited evidence; executes only behind the explicit preview opt-in and
    #: is labelled as a candidate in every response. Never production eligible.
    CANDIDATE_PREVIEW = "CANDIDATE_PREVIEW"
    REVIEWED = "REVIEWED"
    SYNTHETIC_TEST_ONLY = "SYNTHETIC_TEST_ONLY"


class MappingEvidenceClass(StrEnum):
    """How much of the pack the knowledge base actually supports.

    ``SOURCE_BACKED``: the target relationship and every field rule cite a document in the
    knowledge base. ``TARGET_RELATIONSHIP_ONLY``: a document establishes which MX message
    corresponds to the MT, and nothing in the knowledge base states the field mapping.
    ``NAME_CORRESPONDENCE``: the relationship rests on the two documents' own titles (an
    MT "Customer Credit Transfer" guide and an XSD named FIToFICustomerCreditTransfer) —
    evidence of correspondence, never of equivalence. ``SYNTHETIC``: a repository fixture.
    """

    SOURCE_BACKED = "SOURCE_BACKED"
    TARGET_RELATIONSHIP_ONLY = "TARGET_RELATIONSHIP_ONLY"
    NAME_CORRESPONDENCE = "NAME_CORRESPONDENCE"
    SYNTHETIC = "SYNTHETIC"


class MappingCitation(ApiModel):
    """Where in the knowledge base a statement comes from — identity, page, hash; no text."""

    source_id: str
    source_checksum: str | None = None
    page: int | None = None
    section: str | None = None
    note: str | None = Field(default=None, max_length=300)


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
    evidence_class: MappingEvidenceClass = MappingEvidenceClass.SYNTHETIC
    #: Documents in the knowledge base that establish the target relationship.
    relationship_citations: list[MappingCitation] = Field(default_factory=list)
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
    #: Where the source field's meaning and the target element's meaning are stated. A rule
    #: without a citation is ``UNCITED``: it may run in a preview, never in a SOURCE_BACKED pack.
    citations: list[MappingCitation] = Field(default_factory=list)

    @property
    def cited(self) -> bool:
        return bool(self.citations)

    @model_validator(mode="after")
    def shape_matches_kind(self) -> MappingRule:
        if self.kind in {MappingKind.NOT_REPRESENTED, MappingKind.OMIT}:
            if not self.source_refs or self.outputs:
                raise ValueError(f"{self.kind.value} requires source refs and no outputs")
            return self
        if not self.outputs:
            raise ValueError(f"{self.kind.value} requires at least one output")
        if self.kind is MappingKind.CONDITIONAL and self.condition is None:
            raise ValueError("CONDITIONAL requires a condition")
        if self.kind is MappingKind.CODE_MAP and not all(
            output.transform is TransformName.ENUM for output in self.outputs
        ):
            raise ValueError("CODE_MAP outputs must be ENUM tables")
        if self.kind is MappingKind.DIRECT and any(
            output.transform is not TransformName.IDENTITY for output in self.outputs
        ):
            raise ValueError("DIRECT carries the value unchanged; use TRANSFORM or CODE_MAP")
        if self.kind is MappingKind.ONE_TO_MANY and len(self.outputs) < 2:
            raise ValueError("ONE_TO_MANY needs at least two outputs")
        if self.kind is MappingKind.MANY_TO_ONE and len(self.source_refs) < 2:
            raise ValueError("MANY_TO_ONE needs at least two source refs")
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
        evidence = self.provenance.evidence_class
        if evidence is MappingEvidenceClass.SOURCE_BACKED:
            if not self.provenance.relationship_citations:
                raise ValueError("A SOURCE_BACKED pack must cite its target relationship")
            uncited = [
                rule.id
                for rule in self.rules
                if rule.kind is not MappingKind.OMIT and not rule.cited
            ]
            if uncited:
                raise ValueError(f"A SOURCE_BACKED pack must cite every rule: {uncited}")
        if (
            evidence in {MappingEvidenceClass.NAME_CORRESPONDENCE, MappingEvidenceClass.SYNTHETIC}
            and self.provenance.review_state is MappingReviewState.REVIEWED
        ):
            raise ValueError(f"A {evidence.value} pack cannot be REVIEWED")
        if (
            self.provenance.review_state is MappingReviewState.CANDIDATE_PREVIEW
            and self.provenance.production_eligible
        ):
            raise ValueError("A candidate preview is never production eligible")
        return self

    @property
    def cited_rule_count(self) -> int:
        return sum(1 for rule in self.rules if rule.cited)


class MappingRelationship(ApiModel):
    """A candidate MT → MX correspondence the knowledge base supports, with its class and
    citations — listed whether or not a Mapping Pack exists for it."""

    relationship_id: str
    source: MappingIdentity
    target: MappingIdentity
    evidence_class: MappingEvidenceClass
    citations: list[MappingCitation] = Field(default_factory=list)
    statement: str = Field(max_length=400)
    #: Messages the same statement covers (MT205's scope names MT200/201/202/203/205).
    also_covers: list[str] = Field(default_factory=list)
    #: Why no pack can be built where that is the case (target XSD absent from the KB, …).
    blocker: str | None = None


class MappingCoverage(ApiModel):
    mandatory_target_total: int
    mandatory_target_mapped: int
    source_rows_total: int
    source_rows_represented: int
    rules_total: int
    rules_cited: int


class ConversionTarget(ApiModel):
    pack_id: str | None
    pack_version: str | None
    target: MappingIdentity
    review_state: str
    production_eligible: bool
    preview_only: bool
    evidence_class: MappingEvidenceClass
    convertible: bool
    provenance: MappingProvenance | None = None
    relationship: MappingRelationship | None = None


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
    #: Runs a pack that is not production eligible — synthetic or candidate preview — and
    #: acknowledges that its output is not an authoritative business mapping.
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
    evidence_class: MappingEvidenceClass = MappingEvidenceClass.SYNTHETIC
    coverage: MappingCoverage | None = None
    relationship_citations: list[MappingCitation] = Field(default_factory=list)


class ConversionResponse(ApiModel):
    status: str
    target_values: list[ElementInput]
    report: ConversionReport | None
    validation: ValidationResult | None = None
    generation: GenerateResult | None = None
    output_xml: str | None = None
    message: str
