import hashlib

from app.agents.evaluation import evaluate_offline_contract, load_dataset
from app.agents.prompts import INTENT_SYSTEM_INSTRUCTIONS
from app.agents.schemas import PROMPT_VERSION


def test_evaluation_dataset_has_required_coverage_and_contract() -> None:
    dataset = load_dataset()
    fixtures = dataset["fixtures"]
    assert dataset["syntheticOnly"] is True
    assert len(fixtures) >= 60
    assert len({fixture["id"] for fixture in fixtures}) == len(fixtures)
    categories = {fixture["category"] for fixture in fixtures}
    assert {
        "MT540",
        "MT541",
        "MT542",
        "MT543",
        "MT544",
        "MT545",
        "MT546",
        "MT547",
        "MT548_PENDING",
        "MT548_REJECTED",
        "MT548_MATCHED",
        "MT548_UNMATCHED",
        "AMBIGUOUS",
        "CONTRADICTORY",
        "INJECTION",
        "RAW_INJECTION",
        "LONG_VALID",
    }.issubset(categories)
    required = {
        "lifecycle",
        "direction",
        "paymentType",
        "transactionType",
        "extractedFields",
        "missingDecisions",
        "requiresClarification",
        "escalationExpected",
        "forbiddenInventedFields",
    }
    assert all(required.issubset(fixture["expected"]) for fixture in fixtures)
    assert all(fixture["expected"]["forbiddenInventedFields"] for fixture in fixtures)
    metrics = evaluate_offline_contract(fixtures)
    assert metrics["datasetContractRate"] == 100
    assert metrics["deterministicResolverAgreement"] == 100
    assert metrics["promptInjectionFixtures"] >= 7


def test_prompt_version_and_review_hash_are_explicit() -> None:
    assert PROMPT_VERSION == "settlement-intent-v2"
    digest = hashlib.sha256(INTENT_SYSTEM_INSTRUCTIONS.encode()).hexdigest()
    assert digest == "dccc7c866bbc395eadc24674026088b77d6a82917699598c316799289f3e4072"
