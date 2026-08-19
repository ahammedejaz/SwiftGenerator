"""Declarative ISO 20022 message-structure model.

An MX message specification is a nested tree of :class:`MxElement`. Document order is the
order elements appear in the YAML, which is also the order the composer writes them and
the order the derived XSD enforces — so there is exactly one place where element order is
defined.

Every specification declares ``authoritativeCompletenessKnown`` and a source. The subsets
shipped in ``config/mx`` are repository-configured and require authoritative verification
before any production claim; that fact is carried through the API into the UI.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.studio.models import BusinessArea, Presence


class MxDataType(StrEnum):
    """The ISO 20022 representation classes used by the configured subsets."""

    MAX16_TEXT = "Max16Text"
    MAX35_TEXT = "Max35Text"
    MAX70_TEXT = "Max70Text"
    MAX140_TEXT = "Max140Text"
    MAX350_TEXT = "Max350Text"
    EXACT4_ALPHANUMERIC = "Exact4AlphaNumericText"
    ISIN = "ISINOct2015Identifier"
    ANY_BIC = "AnyBICDec2014Identifier"
    LEI = "LEIIdentifier"
    ISO_DATE = "ISODate"
    ISO_DATE_TIME = "ISODateTime"
    DECIMAL = "DecimalNumber"
    AMOUNT = "ActiveCurrencyAndAmount"
    CODE = "Code"
    YES_NO = "YesNoIndicator"


#: Human-readable format guidance shown in the UI and in Message Intelligence.
DATA_TYPE_FORMATS: dict[MxDataType, str] = {
    MxDataType.MAX16_TEXT: "Up to 16 characters.",
    MxDataType.MAX35_TEXT: "Up to 35 characters.",
    MxDataType.MAX70_TEXT: "Up to 70 characters.",
    MxDataType.MAX140_TEXT: "Up to 140 characters.",
    MxDataType.MAX350_TEXT: "Up to 350 characters.",
    MxDataType.EXACT4_ALPHANUMERIC: "Exactly 4 uppercase letters or digits.",
    MxDataType.ISIN: "A 12-character ISIN: 2 letters, 9 alphanumerics and a check digit.",
    MxDataType.ANY_BIC: "An 8- or 11-character BIC.",
    MxDataType.LEI: "A 20-character Legal Entity Identifier.",
    MxDataType.ISO_DATE: "An ISO date, YYYY-MM-DD.",
    MxDataType.ISO_DATE_TIME: "An ISO date and time, YYYY-MM-DDThh:mm:ss with an optional zone.",
    MxDataType.DECIMAL: "A decimal number using a full stop as the decimal separator.",
    MxDataType.AMOUNT: "A decimal amount; the currency is written as the Ccy attribute.",
    MxDataType.CODE: "One of the listed codes.",
    MxDataType.YES_NO: "true or false.",
}


class MxRestrictionBase(StrEnum):
    """The XSD base kinds the compiler supports for generic simple types."""

    TEXT = "TEXT"
    DECIMAL = "DECIMAL"
    DATE = "DATE"
    DATE_TIME = "DATE_TIME"
    TIME = "TIME"
    YEAR = "YEAR"
    BINARY = "BINARY"
    BOOLEAN = "BOOLEAN"


class MxRestriction(BaseModel):
    """A simple type carried verbatim from a source schema.

    The closed :class:`MxDataType` enum names the representation classes the hand-authored
    subsets use; a compiled pack meets arbitrary ISO 20022 simple types, and inventing an
    enum member per type would put schema facts into code. The facts live here instead —
    base kind plus facets — and validation, the derived XSD, samples and Excel all read
    them. Exactly one of ``dataType`` and ``restriction`` is set on a leaf.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    base: MxRestrictionBase
    #: The source schema's own name for the type, e.g. ``Max4AlphaNumericText``. Display
    #: only; the facts below are what validate.
    type_name: str | None = Field(default=None, alias="typeName", max_length=128)
    pattern: str | None = Field(default=None, max_length=1024)
    min_length: int | None = Field(default=None, alias="minLength", ge=0)
    max_length: int | None = Field(default=None, alias="maxLength", ge=1)
    length: int | None = Field(default=None, ge=1)
    total_digits: int | None = Field(default=None, alias="totalDigits", ge=1)
    fraction_digits: int | None = Field(default=None, alias="fractionDigits", ge=0)
    min_inclusive: str | None = Field(default=None, alias="minInclusive", max_length=64)
    max_inclusive: str | None = Field(default=None, alias="maxInclusive", max_length=64)


class MxExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    explanation: str


class MxElement(BaseModel):
    """One node of the message tree: a container, a choice, or a leaf that holds a value."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(min_length=1, max_length=64)
    display_name: str = Field(alias="displayName", min_length=2, max_length=140)
    presence: Presence = Presence.OPTIONAL
    max_occurs: int = Field(default=1, alias="maxOccurs", ge=1, le=1_000)
    choice: bool = False
    data_type: MxDataType | None = Field(default=None, alias="dataType")
    #: Generic simple type from a source schema; mutually exclusive with ``dataType``.
    restriction: MxRestriction | None = None
    codes: list[str] = Field(default_factory=list)
    #: Optional name of a shared list in ``config/knowledge/code_lists.yaml``. Where an
    #: ISO 20022 element and an ISO 15022 field carry the same business code list, both
    #: name it, so the two formats offer one vocabulary rather than two.
    code_list: str | None = Field(default=None, alias="codeList")
    currency_attribute: bool = Field(default=False, alias="currencyAttribute")
    business_path: str | None = Field(default=None, alias="businessPath")

    business_meaning: str = Field(default="", alias="businessMeaning", max_length=600)
    technical_meaning: str = Field(default="", alias="technicalMeaning", max_length=600)
    why_used: str = Field(default="", alias="whyUsed", max_length=600)
    business_question: str = Field(default="", alias="businessQuestion", max_length=300)
    format_explanation: str | None = Field(default=None, alias="formatExplanation", max_length=400)
    condition_explanation: str | None = Field(
        default=None, alias="conditionExplanation", max_length=400
    )
    common_mistakes: list[str] = Field(default_factory=list, alias="commonMistakes")
    examples: list[MxExample] = Field(default_factory=list)
    search_terms: list[str] = Field(default_factory=list, alias="searchTerms")
    children: list[MxElement] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_leaf_or_branch(self) -> MxElement:
        if self.children and (self.data_type is not None or self.restriction is not None):
            raise ValueError(f"{self.name} cannot be both a container and a value element")
        if self.data_type is not None and self.restriction is not None:
            raise ValueError(f"{self.name} must declare a dataType or a restriction, not both")
        if not self.children and self.data_type is None and self.restriction is None:
            raise ValueError(f"{self.name} must declare a dataType, a restriction or children")
        if self.choice and not self.children:
            raise ValueError(f"{self.name} is a choice and must declare children")
        if self.data_type is MxDataType.CODE and not self.codes:
            raise ValueError(f"{self.name} is a code element and must list its codes")
        return self

    @property
    def is_leaf(self) -> bool:
        return not self.children

    @property
    def repeatable(self) -> bool:
        return self.max_occurs > 1

    def format_text(self) -> str:
        if self.format_explanation:
            return self.format_explanation
        if self.data_type is MxDataType.CODE:
            return "One of: " + ", ".join(self.codes)
        if self.data_type is not None:
            return DATA_TYPE_FORMATS[self.data_type]
        if self.restriction is not None:
            return restriction_format_text(self.restriction)
        return "Container element; supply values for its children."


def restriction_format_text(restriction: MxRestriction) -> str:
    """Format guidance derived from the facets themselves — never invented."""
    if restriction.base is MxRestrictionBase.DATE:
        return "An ISO date, YYYY-MM-DD."
    if restriction.base is MxRestrictionBase.DATE_TIME:
        return "An ISO date and time, YYYY-MM-DDThh:mm:ss with an optional zone."
    if restriction.base is MxRestrictionBase.TIME:
        return "An ISO time, hh:mm:ss with an optional zone."
    if restriction.base is MxRestrictionBase.YEAR:
        return "A four-digit ISO year."
    if restriction.base is MxRestrictionBase.BINARY:
        return "Base64-encoded binary content."
    if restriction.base is MxRestrictionBase.BOOLEAN:
        return "true or false."
    if restriction.base is MxRestrictionBase.DECIMAL:
        parts = ["A decimal number using a full stop as the decimal separator"]
        if restriction.total_digits is not None:
            parts.append(f"up to {restriction.total_digits} digits")
        if restriction.fraction_digits is not None:
            parts.append(f"{restriction.fraction_digits} after the separator")
        if restriction.min_inclusive is not None:
            parts.append(f"minimum {restriction.min_inclusive}")
        return ", ".join(parts) + "."
    parts = []
    if restriction.length is not None:
        parts.append(f"Exactly {restriction.length} characters")
    else:
        low, high = restriction.min_length, restriction.max_length
        if low is not None and high is not None:
            parts.append(f"{low} to {high} characters")
        elif high is not None:
            parts.append(f"Up to {high} characters")
        elif low is not None:
            parts.append(f"At least {low} characters")
        else:
            parts.append("Text")
    if restriction.pattern is not None:
        parts.append(f"matching the pattern {restriction.pattern}")
    return ", ".join(parts) + "."


MxElement.model_rebuild()


class MxSource(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source_type: str = Field(alias="sourceType")
    source_reference: str = Field(alias="sourceReference", min_length=8, max_length=256)
    reviewed_at: str = Field(alias="reviewedAt")
    reviewed_by: str = Field(alias="reviewedBy")
    # ---- provenance for compiled packs; optional so hand-authored YAML is untouched ----
    #: True when a compiler produced this specification from a source artifact. The
    #: capability model derives the structure dimension from this, so a generated pack
    #: cannot present itself as a hand-reviewed subset.
    generated: bool = False
    #: File name of the source artifact within its bundle (never a server path).
    source_location: str | None = Field(default=None, alias="sourceLocation")
    #: The source's own version string, e.g. the schema version.
    source_version: str | None = Field(default=None, alias="sourceVersion")
    #: sha256:<hex> of the exact source bytes the pack was compiled from.
    source_checksum: str | None = Field(default=None, alias="sourceChecksum")
    #: Identifies the compiler and its output contract, e.g. ``spec-engine/1``.
    compiler_version: str | None = Field(default=None, alias="compilerVersion")
    review_status: str | None = Field(default=None, alias="reviewStatus")


class MxMessageSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    message_type: str = Field(alias="messageType", min_length=6, max_length=16)
    version: str = Field(min_length=6, max_length=24)
    name: str
    short_description: str = Field(alias="shortDescription")
    business_area: BusinessArea = Field(alias="businessArea")
    namespace: str = Field(min_length=10)
    message_root: str = Field(alias="messageRoot", min_length=2, max_length=64)
    document_element: str = Field(default="Document", alias="documentElement")
    standards_release: str = Field(alias="standardsRelease")
    authoritative_completeness_known: bool = Field(alias="authoritativeCompletenessKnown")
    source: MxSource
    limitations: list[str] = Field(default_factory=list)
    #: Groups of sibling blocks where at least one must be present. Expressed as element
    #: names relative to the message root, e.g. [["PrcgSts", "MtchgSts", "SttlmSts"]].
    require_one_of: list[list[str]] = Field(default_factory=list, alias="requireOneOf")
    structure: list[MxElement] = Field(min_length=1)

    @model_validator(mode="after")
    def check_namespace_matches_version(self) -> MxMessageSpec:
        expected = f"urn:iso:std:iso:20022:tech:xsd:{self.version}"
        if self.namespace != expected:
            raise ValueError(
                f"{self.version} must use namespace {expected}, not {self.namespace}"
            )
        return self


class FlatElement(BaseModel):
    """A flattened view of one tree node, addressed by its absolute path."""

    model_config = ConfigDict(extra="forbid")

    path: str
    depth: int
    order: int
    element: MxElement
    parent_path: str | None
    ancestors: tuple[str, ...]
    choice_group: str | None
    choice_branch: str | None
    mandatory_chain: bool
