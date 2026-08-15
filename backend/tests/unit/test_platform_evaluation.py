import asyncio

from app.agents.platform_evaluation import (
    evaluate_cache_two_pass,
    evaluate_platform_contract,
    load_platform_fixtures,
)


def test_expansion_dataset_has_required_counts_and_contracts() -> None:
    fixtures = load_platform_fixtures()
    metrics = evaluate_platform_contract(fixtures)
    assert metrics["fixtures"] == 195
    assert metrics["categories"] == {
        "TAG_EXPLANATION": 40,
        "SETTLEMENT_AMENDMENT": 30,
        "PENALTY_INTENT": 25,
        "CORPORATE_ACTION_INTENT": 40,
        "PROMPT_INJECTION": 20,
        "AMBIGUITY": 20,
        "CACHE_EQUIVALENCE": 20,
    }
    assert metrics["strictSchemaContractRate"] == 100
    assert metrics["clarificationContractRate"] == 100
    assert metrics["promptInjectionAuthorityBoundaryRate"] == 100
    assert metrics["inventedPenaltyAmountCount"] == 0
    assert metrics["rawMtOutputCount"] == 0


def test_cache_two_pass_has_no_second_pass_calls_or_tokens() -> None:
    metrics = asyncio.run(evaluate_cache_two_pass())
    assert metrics["firstPassCacheMisses"] == 20
    assert metrics["secondPassCacheHits"] == 20
    assert metrics["secondPassProviderCalls"] == 0
    assert metrics["secondPassNewTokens"] == 0
    assert metrics["apiCallsAvoided"] == 20
    assert metrics["tokensAvoided"] == 2400
    assert metrics["costAvoided"] is None
    assert metrics["crossRequestLeakage"] == 0
