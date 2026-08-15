import asyncio
import json
from decimal import Decimal

from app.agents.errors import ai_error
from app.agents.evaluation import evaluate_live
from app.agents.probe import probe_live_ai
from app.agents.providers.base import (
    InterpretationModelRequest,
    InterpretationModelResponse,
    ModelUsage,
)
from app.config import Settings


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        ai_provider="openrouter",
        openrouter_api_key="synthetic-probe-secret",
        openrouter_escalation_enabled=True,
    )


def _payload() -> dict[str, object]:
    return {
        "intent": {
            "lifecycle": "INSTRUCTION",
            "direction": "RECEIVE",
            "paymentType": "AGAINST_PAYMENT",
            "transactionType": None,
            "function": "NEWM",
            "responseAction": None,
            "inferredFields": [],
        },
        "extractedFields": [],
        "ambiguities": [],
        "missingDecisions": [],
        "interpretationSummary": "You are receiving securities against payment.",
        "confidence": 0.98,
        "requiresClarification": False,
    }


class ProbeClient:
    configured = True

    def __init__(self, result: InterpretationModelResponse | Exception) -> None:
        self.result = result
        self.requests: list[InterpretationModelRequest] = []
        self.closed = False

    async def interpret(self, request: InterpretationModelRequest) -> InterpretationModelResponse:
        self.requests.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    async def aclose(self) -> None:
        self.closed = True


def test_production_schema_probe_uses_only_primary_and_resolves_deterministically() -> None:
    client = ProbeClient(
        InterpretationModelResponse(
            payload=_payload(),
            model="openai/gpt-5.4-mini",
            attempt_count=1,
            latency_ms=42,
            usage=ModelUsage(100, 20, 120, Decimal("0.001")),
            provider="Azure",
        )
    )

    result = asyncio.run(probe_live_ai(_settings(), client))

    assert result["status"] == "passed"
    assert result["deterministicMessageType"] == "MT541"
    assert result["provider"] == "Azure"
    assert [request.model for request in client.requests] == ["openai/gpt-5.4-mini"]
    assert client.closed is False


def test_probe_failure_contains_safe_diagnostics_without_secret_or_prompt() -> None:
    client = ProbeClient(
        ai_error(
            "AI_UNSUPPORTED_MODEL_OR_PARAMETERS",
            provider_http_status=404,
            provider_error_type="invalid_request_error",
            provider_safe_message=(
                "No endpoint matched every required model parameter and privacy control."
            ),
            escalatable=False,
        )
    )

    result = asyncio.run(probe_live_ai(_settings(), client))
    serialised = json.dumps(result)

    assert result["status"] == "failed"
    assert result["httpStatus"] == 404
    assert result["providerErrorType"] == "invalid_request_error"
    assert "synthetic-probe-secret" not in serialised
    assert "I want to receive" not in serialised


def test_preflight_failure_stops_dataset_and_quality_metrics_are_null(monkeypatch) -> None:
    async def failed_probe(_settings: Settings):
        return {
            "status": "failed",
            "applicationErrorCode": "AI_SCHEMA_REQUEST_INVALID",
            "schemaValidationFailurePaths": ["#/$defs/ModelIntent"],
        }

    monkeypatch.setattr("app.agents.evaluation.probe_live_ai", failed_probe)
    fixtures = [{"id": "SHOULD-NOT-RUN", "text": "synthetic", "expected": {}}]

    metrics = asyncio.run(evaluate_live(_settings(), fixtures))

    assert metrics["status"] == "live_preflight_failed"
    assert metrics["rootCauseCode"] == "AI_SCHEMA_REQUEST_INVALID"
    assert metrics["evaluatedFixtures"] == 0
    assert metrics["qualityMetricsAvailable"] is False
    assert metrics["intentAccuracy"] is None
    assert metrics["clarificationAccuracy"] is None
    assert metrics["promptTokens"] == 0
    assert metrics["completionTokens"] == 0
