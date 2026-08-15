import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.agents.budgets import DailyUsageBudget
from app.agents.circuit_breaker import CircuitBreaker
from app.agents.errors import AiServiceError
from app.domain.enums import AiCircuitState


def test_circuit_breaker_opens_cools_down_and_recovers() -> None:
    async def run() -> None:
        circuit = CircuitBreaker(failure_threshold=2, cooldown_seconds=10)
        now = datetime.now(UTC)
        await circuit.acquire(now)
        await circuit.failure(now)
        assert circuit.state == AiCircuitState.CLOSED
        await circuit.acquire(now)
        await circuit.failure(now)
        assert circuit.state == AiCircuitState.OPEN
        with pytest.raises(AiServiceError) as caught:
            await circuit.acquire(now + timedelta(seconds=5))
        assert caught.value.code == "AI_CIRCUIT_OPEN"
        await circuit.acquire(now + timedelta(seconds=11))
        assert circuit.state == AiCircuitState.HALF_OPEN
        await circuit.success()
        assert circuit.state == AiCircuitState.CLOSED

    asyncio.run(run())


def test_daily_request_and_token_budgets_fail_closed() -> None:
    async def run() -> None:
        request_budget = DailyUsageBudget(request_limit=1, token_limit=None)
        await request_budget.reserve(10)
        with pytest.raises(AiServiceError) as request_error:
            await request_budget.reserve(10)
        assert request_error.value.code == "AI_BUDGET_EXCEEDED"

        token_budget = DailyUsageBudget(request_limit=None, token_limit=20)
        reservation = await token_budget.reserve(15)
        await token_budget.reconcile(reservation, 19)
        with pytest.raises(AiServiceError):
            await token_budget.reserve(2)

    asyncio.run(run())
