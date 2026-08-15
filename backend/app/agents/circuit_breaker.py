import asyncio
from datetime import UTC, datetime, timedelta

from app.agents.errors import ai_error
from app.domain.enums import AiCircuitState


class CircuitBreaker:
    def __init__(self, failure_threshold: int, cooldown_seconds: float) -> None:
        self._failure_threshold = failure_threshold
        self._cooldown = timedelta(seconds=cooldown_seconds)
        self._state = AiCircuitState.CLOSED
        self._failures = 0
        self._opened_at: datetime | None = None
        self._probe_in_flight = False
        self._lock = asyncio.Lock()

    @property
    def state(self) -> AiCircuitState:
        return self._state

    async def acquire(self, now: datetime | None = None) -> None:
        timestamp = now or datetime.now(UTC)
        async with self._lock:
            if self._state == AiCircuitState.OPEN:
                assert self._opened_at is not None
                if timestamp - self._opened_at < self._cooldown:
                    raise ai_error("AI_CIRCUIT_OPEN")
                self._state = AiCircuitState.HALF_OPEN
            if self._state == AiCircuitState.HALF_OPEN:
                if self._probe_in_flight:
                    raise ai_error("AI_CIRCUIT_OPEN")
                self._probe_in_flight = True

    async def success(self) -> None:
        async with self._lock:
            self._state = AiCircuitState.CLOSED
            self._failures = 0
            self._opened_at = None
            self._probe_in_flight = False

    async def failure(self, now: datetime | None = None) -> None:
        timestamp = now or datetime.now(UTC)
        async with self._lock:
            self._probe_in_flight = False
            self._failures += 1
            if self._state == AiCircuitState.HALF_OPEN or self._failures >= self._failure_threshold:
                self._state = AiCircuitState.OPEN
                self._opened_at = timestamp

    async def ignored_failure(self) -> None:
        """Release a half-open probe for failures that should not affect provider health."""
        async with self._lock:
            self._probe_in_flight = False
