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


@dataclass(frozen=True)
class StructuredCompletionRequest:
    """One structured-output call with a caller-supplied prompt and schema.

    ``InterpretationModelRequest`` above is shaped around one operation — settlement-intent
    interpretation — and hardcodes that prompt and that schema. Offline work such as
    rule extraction needs the same transport, the same provider policy and the same error
    handling with a *different* prompt and schema, so it gets a second request shape rather
    than a second provider.
    """

    #: What the call is for — EXTRACTOR_A, EXTRACTOR_B, REFUTER. Used in telemetry and in
    #: the cache key, never sent to the provider.
    role: str
    model: str
    system_prompt: str
    user_content: str
    schema_name: str
    json_schema: dict[str, Any]
    max_output_tokens: int = 1_500


@dataclass(frozen=True)
class StructuredCompletionResponse:
    payload: dict[str, Any]
    model: str
    attempt_count: int
    latency_ms: int
    usage: ModelUsage
    provider: str = ""
    http_status: int = 200


class StructuredCompletionClient(Protocol):
    """A provider that can answer an arbitrary strict-JSON-schema request."""

    async def complete(
        self,
        request: StructuredCompletionRequest,
    ) -> StructuredCompletionResponse: ...

    async def aclose(self) -> None: ...
