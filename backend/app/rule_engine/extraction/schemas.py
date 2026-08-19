"""What a model is allowed to return.

The model does **not** author a rule AST. It picks from a closed vocabulary of nine rule
shapes and names fields by copying identifiers out of the structure metadata it was given.
Deterministic code then translates the shape into the DSL, and refuses anything it cannot
translate faithfully.

That is a deliberate narrowing. Asking a model to emit an expression tree invites both
subtle logic errors and a much larger surface to smuggle something through; a closed
vocabulary makes every candidate mechanically checkable, canonicalisable and diffable.
Rules the vocabulary cannot express are reported as ambiguities rather than approximated.
"""

from __future__ import annotations

from copy import deepcopy
from enum import StrEnum
from functools import lru_cache
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from app.agents.schemas import ProviderSchemaError, normalise_provider_schema

CANDIDATE_SCHEMA_NAME = "rule_candidate_extraction"
REFUTER_SCHEMA_NAME = "rule_candidate_refutation"


class ExtractionDecision(StrEnum):
    #: A successful, unremarkable outcome. The source simply does not state a rule.
    NO_RULE_FOUND = "NO_RULE_FOUND"
    RULE_FOUND = "RULE_FOUND"


class CandidateRuleType(StrEnum):
    REQUIRED = "REQUIRED"
    FORBIDDEN = "FORBIDDEN"
    REQUIRED_IF = "REQUIRED_IF"
    FORBIDDEN_IF = "FORBIDDEN_IF"
    CODE_SUBSET = "CODE_SUBSET"
    DATE_ORDER = "DATE_ORDER"
    MUTUALLY_EXCLUSIVE = "MUTUALLY_EXCLUSIVE"
    AT_LEAST_ONE_OF = "AT_LEAST_ONE_OF"
    EXACTLY_ONE_OF = "EXACTLY_ONE_OF"


class ConditionOperator(StrEnum):
    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    IN = "IN"
    NOT_IN = "NOT_IN"
    EXISTS = "EXISTS"
    ABSENT = "ABSENT"
    NONE = "NONE"


class DateOrder(StrEnum):
    BEFORE = "BEFORE"
    ON_OR_BEFORE = "ON_OR_BEFORE"
    AFTER = "AFTER"
    ON_OR_AFTER = "ON_OR_AFTER"
    NONE = "NONE"


class CandidateSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class ExtractionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, frozen=True)


class CandidateRule(ExtractionModel):
    """One rule the source is claimed to establish."""

    rule_type: CandidateRuleType = Field(alias="ruleType")
    #: Field identifiers copied verbatim from the supplied structure metadata.
    targets: list[str] = Field(max_length=6)
    condition_field: str = Field(alias="conditionField", max_length=500)
    condition_operator: ConditionOperator = Field(alias="conditionOperator")
    condition_values: list[str] = Field(alias="conditionValues", max_length=24)
    #: For CODE_SUBSET: the codes the source permits.
    codes: list[str] = Field(max_length=48)
    date_order: DateOrder = Field(alias="dateOrder")
    severity: CandidateSeverity
    title: str = Field(max_length=140)
    message: str = Field(max_length=300)
    suggestion: str = Field(max_length=300)
    evidence_segment_ids: list[str] = Field(alias="evidenceSegmentIds", max_length=6)
    confidence: float = Field(ge=0, le=1)
    #: Anything the source leaves open, or that this vocabulary cannot express. A populated
    #: list is a good outcome, not a failure — it is what sends a reviewer to the source.
    ambiguities: list[str] = Field(max_length=8)


class CandidateExtraction(ExtractionModel):
    decision: ExtractionDecision
    candidates: list[CandidateRule] = Field(max_length=6)
    #: Why the source establishes nothing, when it establishes nothing.
    no_rule_reason: str = Field(alias="noRuleReason", max_length=300)


class ObjectionKind(StrEnum):
    UNSUPPORTED_CLAIM = "UNSUPPORTED_CLAIM"
    MISSING_CONDITION = "MISSING_CONDITION"
    MISSING_EXCEPTION = "MISSING_EXCEPTION"
    WRONG_FIELD = "WRONG_FIELD"
    OVER_BROAD = "OVER_BROAD"
    WRONG_CODE = "WRONG_CODE"
    SOURCE_AMBIGUOUS = "SOURCE_AMBIGUOUS"
    NOT_REPRESENTABLE = "NOT_REPRESENTABLE"


class RefuterVerdict(StrEnum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"


class RefuterRecommendation(StrEnum):
    #: The refuter's *best* possible answer. It criticises; it never approves.
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REJECT = "REJECT"


class Objection(ExtractionModel):
    kind: ObjectionKind
    detail: str = Field(max_length=300)


class Refutation(ExtractionModel):
    verdict: RefuterVerdict
    objections: list[Objection] = Field(max_length=10)
    recommendation: RefuterRecommendation


def _strict(model: type[BaseModel]) -> dict[str, Any]:
    normalised = normalise_provider_schema(model.model_json_schema(by_alias=True))
    if not isinstance(normalised, dict):
        raise ProviderSchemaError("schema normalisation did not produce an object")
    return cast(dict[str, Any], normalised)


@lru_cache(maxsize=1)
def _candidate_schema() -> dict[str, Any]:
    return _strict(CandidateExtraction)


@lru_cache(maxsize=1)
def _refutation_schema() -> dict[str, Any]:
    return _strict(Refutation)


def candidate_schema() -> dict[str, Any]:
    return deepcopy(_candidate_schema())


def refutation_schema() -> dict[str, Any]:
    return deepcopy(_refutation_schema())
