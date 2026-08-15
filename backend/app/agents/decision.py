from dataclasses import dataclass
from enum import StrEnum


class AiOperation(StrEnum):
    INTENT_INTERPRETATION = "INTENT_INTERPRETATION"
    TAG_DETAILS = "TAG_DETAILS"
    TAG_SEARCH = "TAG_SEARCH"
    TAG_SIMPLIFICATION = "TAG_SIMPLIFICATION"
    TAG_COMPARISON = "TAG_COMPARISON"
    KNOWLEDGE_TRANSLATION = "KNOWLEDGE_TRANSLATION"
    MESSAGE_RESOLUTION = "MESSAGE_RESOLUTION"
    MISSING_FIELDS = "MISSING_FIELDS"
    MESSAGE_GENERATION = "MESSAGE_GENERATION"
    MESSAGE_VALIDATION = "MESSAGE_VALIDATION"
    LIFECYCLE_RESPONSE = "LIFECYCLE_RESPONSE"
    REPORT_RETRIEVAL = "REPORT_RETRIEVAL"
    RAW_SUBSET_PARSING = "RAW_SUBSET_PARSING"


class AiCallDecision(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    CACHE_THEN_MODEL = "CACHE_THEN_MODEL"


@dataclass(frozen=True)
class AiCallDecisionResult:
    operation: AiOperation
    decision: AiCallDecision
    reason: str


class AiCallDecisionPipeline:
    """Explicitly limits model use to operations where wording assistance adds value."""

    _MODEL_ELIGIBLE = {
        AiOperation.INTENT_INTERPRETATION,
        AiOperation.TAG_SIMPLIFICATION,
        AiOperation.TAG_COMPARISON,
        AiOperation.KNOWLEDGE_TRANSLATION,
    }

    def decide(self, operation: AiOperation) -> AiCallDecisionResult:
        if operation in self._MODEL_ELIGIBLE:
            return AiCallDecisionResult(
                operation=operation,
                decision=AiCallDecision.CACHE_THEN_MODEL,
                reason="No authoritative deterministic wording fully answers this operation.",
            )
        return AiCallDecisionResult(
            operation=operation,
            decision=AiCallDecision.DETERMINISTIC,
            reason="The workflow registry or verified knowledge base answers this operation.",
        )


ai_call_decision_pipeline = AiCallDecisionPipeline()
