from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol


@dataclass(frozen=True)
class InterpretationModelRequest:
    request_id: str
    model: str
    sanitised_text: str
    minimal_context: dict[str, str]
    correction: bool = False


@dataclass(frozen=True)
class ModelUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    reported_cost: Decimal | None = None


@dataclass(frozen=True)
class InterpretationModelResponse:
    payload: dict[str, Any]
    model: str
    attempt_count: int
    latency_ms: int
    usage: ModelUsage
    provider: str = ""
    http_status: int = 200


class StructuredModelClient(Protocol):
    async def interpret(
        self,
        request: InterpretationModelRequest,
    ) -> InterpretationModelResponse: ...

    async def aclose(self) -> None: ...
