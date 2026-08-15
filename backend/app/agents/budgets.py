import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime

from app.agents.errors import ai_error


@dataclass(frozen=True)
class BudgetReservation:
    estimated_tokens: int


class DailyUsageBudget:
    def __init__(self, request_limit: int | None, token_limit: int | None) -> None:
        self._request_limit = request_limit
        self._token_limit = token_limit
        self._day: date = datetime.now(UTC).date()
        self._requests = 0
        self._tokens = 0
        self._lock = asyncio.Lock()

    async def reserve(
        self,
        estimated_tokens: int,
        now: datetime | None = None,
    ) -> BudgetReservation:
        timestamp = now or datetime.now(UTC)
        async with self._lock:
            self._roll_day(timestamp.date())
            if self._request_limit is not None and self._requests + 1 > self._request_limit:
                raise ai_error("AI_BUDGET_EXCEEDED", status=429)
            if (
                self._token_limit is not None
                and self._tokens + estimated_tokens > self._token_limit
            ):
                raise ai_error("AI_BUDGET_EXCEEDED", status=429)
            self._requests += 1
            self._tokens += estimated_tokens
            return BudgetReservation(estimated_tokens=estimated_tokens)

    async def reconcile(
        self,
        reservation: BudgetReservation,
        actual_tokens: int | None,
        now: datetime | None = None,
    ) -> None:
        timestamp = now or datetime.now(UTC)
        async with self._lock:
            self._roll_day(timestamp.date())
            if actual_tokens is not None:
                self._tokens = max(
                    0,
                    self._tokens - reservation.estimated_tokens + actual_tokens,
                )

    def _roll_day(self, current_day: date) -> None:
        if current_day != self._day:
            self._day = current_day
            self._requests = 0
            self._tokens = 0
