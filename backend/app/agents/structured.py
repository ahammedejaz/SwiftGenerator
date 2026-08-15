from typing import Any, Protocol

from pydantic import ValidationError

from app.agents.prompts import CORRECTION_INSTRUCTIONS, INTENT_SYSTEM_INSTRUCTIONS
from app.domain.models import InterpretScenarioRequest, ScenarioInterpretation


class StructuredIntentTransport(Protocol):
    """Provider-neutral boundary for an optional structured-output model client."""

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class StructuredIntentAdapter:
    """Schema-validating adapter that can wrap an institution-approved AI transport.

    No network transport is included in the prototype. The core application therefore never
    needs an API key, while this boundary documents and tests rejection/retry behavior.
    """

    def __init__(self, transport: StructuredIntentTransport, max_attempts: int = 2) -> None:
        self._transport = transport
        self._max_attempts = max_attempts

    def interpret(self, request: InterpretScenarioRequest) -> ScenarioInterpretation:
        error: ValidationError | None = None
        for attempt in range(self._max_attempts):
            payload: dict[str, Any] = {
                "systemInstructions": INTENT_SYSTEM_INSTRUCTIONS,
                "input": {"text": request.text, "profileId": request.profile_id},
                "responseSchema": ScenarioInterpretation.model_json_schema(),
                "strict": True,
                "temperature": 0,
            }
            if attempt:
                payload["correctionInstructions"] = CORRECTION_INSTRUCTIONS
                payload["schemaError"] = str(error)
            try:
                result = ScenarioInterpretation.model_validate(self._transport(payload))
            except ValidationError as exc:
                error = exc
                continue
            if result.scenario.synthetic_data is not True:
                raise ValueError("AI interpretation must remain explicitly synthetic")
            return result
        raise ValueError("Structured intent provider returned malformed output after retry")
