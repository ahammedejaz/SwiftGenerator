import asyncio
import math
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal

from app.domain.models import AiTelemetrySnapshot


class AiTelemetry:
    def __init__(self) -> None:
        self._request_count = 0
        self._success_count = 0
        self._failure_count = 0
        self._primary_count = 0
        self._escalation_count = 0
        self._schema_retry_count = 0
        self._budget_rejection_count = 0
        self._rate_limit_count = 0
        self._latencies: list[int] = []
        self._input_characters = 0
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._total_tokens = 0
        self._reported_cost = Decimal("0")
        self._failures: Counter[str] = Counter()
        self._last_successful_call_at: datetime | None = None
        self._live_api_interactions = 0
        self._cache_hit_interactions = 0
        self._tokens_avoided = 0
        self._calls_avoided = 0
        self._cost_avoided = Decimal("0")
        self._lock = asyncio.Lock()

    @property
    def last_successful_call_at(self) -> datetime | None:
        return self._last_successful_call_at

    async def begin(self, input_characters: int) -> None:
        async with self._lock:
            self._request_count += 1
            self._input_characters += input_characters

    async def success(
        self,
        *,
        latency_ms: int,
        escalated: bool,
        schema_retries: int,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        reported_cost: Decimal | None,
    ) -> None:
        async with self._lock:
            self._success_count += 1
            self._live_api_interactions += 1
            self._primary_count += 1
            self._escalation_count += int(escalated)
            self._schema_retry_count += schema_retries
            self._latencies.append(latency_ms)
            self._prompt_tokens += prompt_tokens
            self._completion_tokens += completion_tokens
            self._total_tokens += total_tokens
            self._reported_cost += reported_cost or Decimal("0")
            self._last_successful_call_at = datetime.now(UTC)

    async def cache_hit(
        self,
        *,
        latency_ms: int,
        tokens_avoided: int,
        calls_avoided: int,
        cost_avoided: Decimal | None,
    ) -> None:
        async with self._lock:
            self._success_count += 1
            self._cache_hit_interactions += 1
            self._latencies.append(latency_ms)
            self._tokens_avoided += tokens_avoided
            self._calls_avoided += calls_avoided
            self._cost_avoided += cost_avoided or Decimal("0")

    async def failure(self, code: str, latency_ms: int) -> None:
        async with self._lock:
            self._failure_count += 1
            self._failures[code] += 1
            self._latencies.append(latency_ms)
            if code == "AI_BUDGET_EXCEEDED":
                self._budget_rejection_count += 1
            if code == "AI_RATE_LIMITED":
                self._rate_limit_count += 1

    async def snapshot(self) -> AiTelemetrySnapshot:
        async with self._lock:
            sorted_latencies = sorted(self._latencies)
            average = (
                round(sum(sorted_latencies) / len(sorted_latencies)) if sorted_latencies else 0
            )
            p95_index = max(0, math.ceil(len(sorted_latencies) * 0.95) - 1)
            p95 = sorted_latencies[p95_index] if sorted_latencies else 0
            return AiTelemetrySnapshot(
                request_count=self._request_count,
                success_count=self._success_count,
                failure_count=self._failure_count,
                primary_count=self._primary_count,
                escalation_count=self._escalation_count,
                schema_retry_count=self._schema_retry_count,
                budget_rejection_count=self._budget_rejection_count,
                rate_limit_count=self._rate_limit_count,
                average_latency_ms=average,
                p95_latency_ms=p95,
                input_characters=self._input_characters,
                prompt_tokens=self._prompt_tokens,
                completion_tokens=self._completion_tokens,
                total_tokens=self._total_tokens,
                reported_cost=self._reported_cost,
                failures_by_code=dict(self._failures),
                live_api_interactions=self._live_api_interactions,
                cache_hit_interactions=self._cache_hit_interactions,
                tokens_avoided=self._tokens_avoided,
                calls_avoided=self._calls_avoided,
                estimated_cost_avoided=self._cost_avoided,
            )
