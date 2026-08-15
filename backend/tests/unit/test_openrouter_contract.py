import asyncio
import json
from collections.abc import Callable

import httpx
import pytest

from app.agents.errors import AiServiceError
from app.agents.providers.base import InterpretationModelRequest
from app.agents.providers.openrouter import OpenRouterClient
from app.config import Settings


def settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "ai_provider": "openrouter",
        "openrouter_api_key": "contract-test-secret",
        "openrouter_max_retries": 1,
        "openrouter_retry_base_seconds": 0.01,
        "openrouter_retry_max_seconds": 1.0,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def model_request(model: str = "openai/gpt-5.4-mini") -> InterpretationModelRequest:
    return InterpretationModelRequest(
        request_id="safe-request-id",
        model=model,
        sanitised_text="Receive securities against payment.",
        minimal_context={"profileId": "BASE_DEMO_V1"},
    )


def valid_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
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
    payload.update(overrides)
    return payload


def provider_response(
    payload: object,
    *,
    model: str = "openai/gpt-5.4-mini",
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "safe-provider-id",
            "model": model,
            "provider": "Azure",
            "choices": [{"message": {"role": "assistant", "content": json.dumps(payload)}}],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 30,
                "total_tokens": 130,
                "cost": 0.0002,
            },
        },
    )


def run_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    configured: Settings | None = None,
    sleep: Callable[[float], object] | None = None,
):
    async def execute():
        async_client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://openrouter.test/api/v1",
        )

        async def no_sleep(delay: float) -> None:
            if sleep:
                sleep(delay)

        client = OpenRouterClient(
            configured or settings(), http_client=async_client, sleep=no_sleep
        )
        try:
            return await client.interpret(model_request())
        finally:
            await async_client.aclose()

    return asyncio.run(execute())


def test_request_uses_strict_schema_privacy_and_parameter_enforcement() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/chat/completions"
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content)
        return provider_response(valid_payload())

    result = run_client(handler)
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "openai/gpt-5.4-mini"
    assert payload["max_completion_tokens"] == 1200
    assert "temperature" not in payload
    assert "max_tokens" not in payload
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True
    schema = payload["response_format"]["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert payload["provider"] == {
        "require_parameters": True,
        "allow_fallbacks": True,
        "data_collection": "deny",
        "zdr": True,
    }
    serialized = json.dumps(payload)
    assert "contract-test-secret" not in serialized
    assert result.usage.total_tokens == 130
    assert result.provider == "Azure"
    assert str(result.usage.reported_cost) == "0.0002"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, "AI_AUTHENTICATION_FAILED"),
        (402, "AI_PAYMENT_REQUIRED"),
        (408, "AI_TIMEOUT"),
        (429, "AI_RATE_LIMITED"),
        (500, "AI_PROVIDER_UNAVAILABLE"),
        (404, "AI_UNSUPPORTED_MODEL_OR_PARAMETERS"),
    ],
)
def test_http_errors_map_to_safe_codes(status: int, expected: str) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": "provider detail"}})

    with pytest.raises(AiServiceError) as caught:
        run_client(handler, configured=settings(openrouter_max_retries=0))
    assert caught.value.code == expected
    assert "provider detail" not in str(caught.value)
    assert "contract-test-secret" not in str(caught.value)


def test_permanent_request_error_is_not_retried_and_keeps_safe_diagnostics() -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            404,
            json={
                "error": {
                    "message": "No endpoints found that can handle the requested parameters.",
                    "metadata": {"error_type": "invalid_request_error"},
                }
            },
        )

    with pytest.raises(AiServiceError) as caught:
        run_client(handler, configured=settings(openrouter_max_retries=2))

    assert attempts == 1
    assert caught.value.code == "AI_UNSUPPORTED_MODEL_OR_PARAMETERS"
    assert caught.value.provider_http_status == 404
    assert caught.value.provider_error_type == "invalid_request_error"
    assert caught.value.provider_safe_message == (
        "No endpoint matched every required model parameter and privacy control."
    )
    assert caught.value.retryable is False
    assert caught.value.escalatable is False
    assert caught.value.affects_circuit is False


def test_retry_after_is_honoured_and_retry_is_bounded() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "0.5"},
                json={"error": {"message": "limited"}},
            )
        return provider_response(valid_payload())

    run_client(handler, sleep=delays.append)
    assert attempts == 2
    assert delays == [0.5]


def test_zdr_incompatibility_never_weakens_privacy() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["provider"]["zdr"] is True
        assert payload["provider"]["data_collection"] == "deny"
        return httpx.Response(
            503,
            json={"error": {"message": "No endpoints meet ZDR routing requirements"}},
        )

    with pytest.raises(AiServiceError) as caught:
        run_client(handler)
    assert caught.value.code == "AI_PRIVACY_REQUIREMENTS_UNAVAILABLE"


def test_timeout_retries_then_returns_controlled_error() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("sensitive timeout detail", request=request)

    with pytest.raises(AiServiceError) as caught:
        run_client(handler)
    assert attempts == 2
    assert caught.value.code == "AI_TIMEOUT"
    assert "sensitive" not in str(caught.value)


@pytest.mark.parametrize(
    "body",
    [
        httpx.Response(200, text="not-json"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": {"content": "not-json"}}]}),
    ],
)
def test_malformed_provider_responses_are_rejected(body: httpx.Response) -> None:
    with pytest.raises(AiServiceError) as caught:
        run_client(lambda _: body)
    assert caught.value.code == "AI_SCHEMA_VALIDATION_FAILED"


def test_retryable_http_status_with_non_json_body_is_still_retried() -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(500, text="upstream unavailable")
        return provider_response(valid_payload())

    run_client(handler)
    assert attempts == 2


def test_embedded_provider_error_is_rejected() -> None:
    with pytest.raises(AiServiceError) as caught:
        run_client(
            lambda _: httpx.Response(
                200,
                json={"error": {"code": 429, "message": "rate limit"}},
            ),
            configured=settings(openrouter_max_retries=0),
        )
    assert caught.value.code == "AI_RATE_LIMITED"


def test_choice_level_generation_error_is_classified_safely() -> None:
    with pytest.raises(AiServiceError) as caught:
        run_client(
            lambda _: httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "error": {
                                "code": 503,
                                "message": "temporary provider generation failure",
                                "metadata": {"error_type": "provider_unavailable"},
                            }
                        }
                    ]
                },
            ),
            configured=settings(openrouter_max_retries=0),
        )
    assert caught.value.code == "AI_PROVIDER_UNAVAILABLE"
    assert caught.value.provider_http_status == 503
    assert caught.value.provider_error_type == "provider_unavailable"
