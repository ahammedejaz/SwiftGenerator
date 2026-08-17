from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import MessageType
from app.domain.models import ApiModel


class WorkflowModuleId(StrEnum):
    SETTLEMENT = "SETTLEMENT"
    SETTLEMENT_COMMAND = "SETTLEMENT_COMMAND"
    PENALTIES = "PENALTIES"
    CORPORATE_ACTIONS = "CORPORATE_ACTIONS"


class PresenceRule(StrEnum):
    MANDATORY = "MANDATORY"
    OPTIONAL = "OPTIONAL"
    CONDITIONAL = "CONDITIONAL"


class RuleLayer(StrEnum):
    BASE_STANDARD = "BASE_STANDARD"
    MARKET_PRACTICE = "MARKET_PRACTICE"
    CLIENT_PROFILE = "CLIENT_PROFILE"
    INTERNAL_RULE_PACK = "INTERNAL_RULE_PACK"


class InputKind(StrEnum):
    """The control a field deserves, decided by configuration rather than by the browser.

    Kept here so the browser, the JSON API and the Excel template all read one answer. The
    previous arrangement inferred it in React from whether an example happened to appear in
    the code list, which is why a quantity such as ``UNIT/1000`` silently became a free-text
    box while ``NEWM`` became a dropdown.
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


class SourceType(StrEnum):
    OFFICIAL_ISO_15022 = "OFFICIAL_ISO_15022"
    AUTHORISED_SWIFT = "AUTHORISED_SWIFT"
    APPROVED_CLIENT_GUIDE = "APPROVED_CLIENT_GUIDE"
    APPROVED_INTERNAL_RULE_PACK = "APPROVED_INTERNAL_RULE_PACK"


class ReviewStatus(StrEnum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"


class KnowledgeSource(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source_type: SourceType = Field(alias="sourceType")
    source_reference: str = Field(alias="sourceReference", min_length=8, max_length=512)
    review_status: ReviewStatus = Field(alias="reviewStatus")
    reviewed_at: date = Field(alias="reviewedAt")
    reviewed_by: str = Field(alias="reviewedBy", min_length=3, max_length=80)


class TagExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1, max_length=120)
    synthetic: bool
    explanation: str = Field(min_length=3, max_length=300)

    @field_validator("synthetic")
    @classmethod
    def require_synthetic(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Tag knowledge examples must be synthetic")
        return value


class TagKnowledgeDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    message_types: list[MessageType] = Field(alias="messageTypes", min_length=1)
    workflow_module: WorkflowModuleId = Field(alias="workflowModule")
    sequence_path: str = Field(alias="sequencePath", min_length=1, max_length=80)
    field_tag: str = Field(alias="fieldTag", pattern=r"^[0-9]{2}[A-Z]$")
    qualifier: str | None = Field(default=None, pattern=r"^[A-Z0-9]{4}$")
    business_path: str = Field(alias="businessPath", min_length=1, max_length=120)
    display_name: str = Field(alias="displayName", min_length=2, max_length=120)
    business_meaning: str = Field(alias="businessMeaning", min_length=10, max_length=600)
    technical_meaning: str = Field(alias="technicalMeaning", min_length=10, max_length=600)
    why_used: str = Field(alias="whyUsed", min_length=10, max_length=600)
    business_question: str = Field(alias="businessQuestion", min_length=5, max_length=300)
    missing_impact: str = Field(alias="missingImpact", min_length=5, max_length=400)
    presence: PresenceRule
    condition_expression: str | None = Field(
        default=None, alias="conditionExpression", max_length=120
    )
    condition_explanation: str | None = Field(
        default=None, alias="conditionExplanation", max_length=500
    )
    supported_options: list[str] = Field(alias="supportedOptions", min_length=1)
    allowed_codes: list[str] = Field(default_factory=list, alias="allowedCodes")
    #: Name of a shared list in ``code_lists.yaml``. Supplies both the codes and the words
    #: for them, so a code list is never restated per field.
    code_list: str | None = Field(default=None, alias="codeList", max_length=64)
    input_kind: InputKind = Field(default=InputKind.TEXT, alias="inputKind")
    #: A literal the **composer** writes in front of the value, such as ``ISIN ``. The
    #: caller supplies the value alone; exactly one component adds this.
    literal_prefix: str | None = Field(default=None, alias="literalPrefix", max_length=12)
    identifier_types: list[str] = Field(default_factory=list, alias="identifierTypes")
    #: Rows sharing a group are alternatives — different field options carrying the same
    #: business party. Exactly one of them satisfies the group.
    choice_group: str | None = Field(default=None, alias="choiceGroup", max_length=64)
    max_length: int | None = Field(default=None, alias="maxLength", ge=1, le=2000)
    format_explanation: str = Field(alias="formatExplanation", min_length=5, max_length=500)
    example_values: list[TagExample] = Field(default_factory=list, alias="exampleValues")
    common_mistakes: list[str] = Field(default_factory=list, alias="commonMistakes")
    depends_on: list[str] = Field(default_factory=list, alias="dependsOn")
    required_with: list[str] = Field(default_factory=list, alias="requiredWith")
    conflicts_with: list[str] = Field(default_factory=list, alias="conflictsWith")
    related_fields: list[str] = Field(default_factory=list, alias="relatedFields")
    lifecycle_impact: str = Field(alias="lifecycleImpact", min_length=5, max_length=500)
    rule_layer: RuleLayer = Field(alias="ruleLayer")
    standards_release: str = Field(alias="standardsRelease", min_length=3, max_length=64)
    knowledge_version: str = Field(alias="knowledgeVersion", min_length=3, max_length=64)
    source: KnowledgeSource
    search_terms: list[str] = Field(default_factory=list, alias="searchTerms")

    @field_validator("supported_options")
    @classmethod
    def validate_options(cls, values: list[str]) -> list[str]:
        if any(len(item) != 1 or not item.isalpha() or not item.isupper() for item in values):
            raise ValueError("Field options must be single uppercase letters")
        return list(dict.fromkeys(values))


class TagKnowledge(ApiModel):
    knowledge_id: str
    message_type: MessageType
    workflow_module: WorkflowModuleId
    sequence_path: str
    field_tag: str
    qualifier: str | None = None
    business_path: str
    display_name: str
    business_meaning: str
    technical_meaning: str
    why_used: str
    business_question: str
    missing_impact: str
    presence: PresenceRule
    condition_expression: str | None = None
    condition_explanation: str | None = None
    supported_options: list[str]
    allowed_codes: list[str]
    code_list: str | None = None
    input_kind: InputKind = InputKind.TEXT
    literal_prefix: str | None = None
    identifier_types: list[str] = Field(default_factory=list)
    choice_group: str | None = None
    max_length: int | None = None
    format_explanation: str
    example_values: list[TagExample]
    common_mistakes: list[str]
    depends_on: list[str]
    required_with: list[str]
    conflicts_with: list[str]
    related_fields: list[str]
    lifecycle_impact: str
    rule_layer: RuleLayer
    standards_release: str
    knowledge_version: str
    source: KnowledgeSource
    search_terms: list[str]


class ProfileKnowledgeOverlay(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    profile_id: str = Field(alias="profileId")
    profile_version: str = Field(alias="profileVersion")
    knowledge_id: str = Field(alias="knowledgeId")
    presence: PresenceRule | None = None
    allowed_options: list[str] | None = Field(default=None, alias="allowedOptions")
    allowed_codes: list[str] | None = Field(default=None, alias="allowedCodes")
    client_explanation: str | None = Field(default=None, alias="clientExplanation")
    business_question: str | None = Field(default=None, alias="businessQuestion")
    common_mistakes: list[str] = Field(default_factory=list, alias="commonMistakes")
    source: KnowledgeSource


class EffectiveTagKnowledge(ApiModel):
    record: TagKnowledge
    profile_id: str
    profile_version: str
    effective_presence: PresenceRule
    effective_options: list[str]
    effective_codes: list[str]
    client_explanation: str | None = None
    effective_business_question: str
    profile_common_mistakes: list[str] = Field(default_factory=list)
    profile_override_applied: bool = False


class KnowledgeMessageSummary(ApiModel):
    message_type: MessageType
    workflow_module: WorkflowModuleId
    record_count: int
    knowledge_version: str


class KnowledgeExplainRequest(ApiModel):
    knowledge_id: str
    profile_id: str = "BASE_DEMO_V1"


class KnowledgeSearchResponse(ApiModel):
    query: str
    results: list[EffectiveTagKnowledge]
    deterministic: bool = True
    llm_used: bool = False


class KnowledgeDependencyResponse(ApiModel):
    knowledge_id: str
    depends_on: list[EffectiveTagKnowledge]
    required_with: list[EffectiveTagKnowledge]
    conflicts_with: list[EffectiveTagKnowledge]
    related_fields: list[EffectiveTagKnowledge]
    verified_only: bool = True
