import pytest

from app.agents.decision import (
    AiCallDecision,
    AiOperation,
    ai_call_decision_pipeline,
)


@pytest.mark.parametrize(
    "operation",
    [
        AiOperation.TAG_DETAILS,
        AiOperation.TAG_SEARCH,
        AiOperation.MESSAGE_RESOLUTION,
        AiOperation.MISSING_FIELDS,
        AiOperation.MESSAGE_GENERATION,
        AiOperation.MESSAGE_VALIDATION,
        AiOperation.LIFECYCLE_RESPONSE,
        AiOperation.REPORT_RETRIEVAL,
        AiOperation.RAW_SUBSET_PARSING,
    ],
)
def test_authoritative_operations_are_deterministic(operation: AiOperation) -> None:
    assert ai_call_decision_pipeline.decide(operation).decision == AiCallDecision.DETERMINISTIC


@pytest.mark.parametrize(
    "operation",
    [
        AiOperation.INTENT_INTERPRETATION,
        AiOperation.TAG_SIMPLIFICATION,
        AiOperation.TAG_COMPARISON,
        AiOperation.KNOWLEDGE_TRANSLATION,
    ],
)
def test_language_operations_check_cache_before_model(operation: AiOperation) -> None:
    assert ai_call_decision_pipeline.decide(operation).decision == AiCallDecision.CACHE_THEN_MODEL
