import asyncio
import json

import pytest

from app.agents.evaluation import evaluate_live, load_dataset
from app.config import Settings


@pytest.mark.live
def test_live_openrouter_structured_output_and_evaluation() -> None:
    settings = Settings(ai_provider="openrouter")
    if not settings.openrouter_api_key or not settings.openrouter_api_key.get_secret_value():
        pytest.skip("OPENROUTER_API_KEY is absent; live provider verification not executed")
    dataset = load_dataset()
    metrics = asyncio.run(evaluate_live(settings, dataset["fixtures"]))
    assert metrics["status"] == "passed", json.dumps(metrics, sort_keys=True)
