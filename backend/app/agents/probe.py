import asyncio
import json
from typing import Any

from app.agents.errors import AiServiceError, ai_error
from app.agents.interpretation import validate_model_payload
from app.agents.preprocessing import sanitize_user_text
from app.agents.providers.base import InterpretationModelRequest, StructuredModelClient
from app.agents.providers.openrouter import OpenRouterClient
from app.agents.schemas import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    lint_provider_schema,
    strict_interpretation_schema,
)
from app.config import Settings
from app.domain.models import MessageResolutionRequest
from app.domain.resolver import resolve_message_type

PROBE_TEXT = "I want to receive securities against payment."


async def probe_live_ai(
    settings: Settings,
    client: StructuredModelClient | None = None,
) -> dict[str, Any]:
    """Exercise one primary production-schema request without service circuit state."""
    if not settings.openrouter_api_key or not settings.openrouter_api_key.get_secret_value():
        return _failure(ai_error("AI_NOT_CONFIGURED", escalatable=False))

    owned_client = client is None
    model_client = client or OpenRouterClient(settings)
    sanitised = sanitize_user_text(PROBE_TEXT, settings.openrouter_max_input_chars)
    try:
        lint_provider_schema(strict_interpretation_schema())
        response = await model_client.interpret(
            InterpretationModelRequest(
                request_id="production-schema-live-probe",
                model=settings.openrouter_primary_model,
                sanitised_text=sanitised.text,
                minimal_context={"profileId": "BASE_DEMO_V1"},
            )
        )
        parsed = validate_model_payload(response.payload, sanitised)
        if response.usage.total_tokens <= 0:
            return {
                "status": "failed",
                "applicationErrorCode": "AI_USAGE_METADATA_MISSING",
                "finalPublicErrorCode": "AI_USAGE_METADATA_MISSING",
                "safeErrorMessage": "The provider response omitted required usage metadata.",
                "httpStatus": response.http_status,
                "model": response.model or settings.openrouter_primary_model,
                "provider": response.provider or None,
                "promptVersion": PROMPT_VERSION,
                "schemaVersion": SCHEMA_VERSION,
                "schemaValidationFailurePaths": [],
            }
        resolution = None
        if parsed.intent.lifecycle is not None:
            resolution = resolve_message_type(
                MessageResolutionRequest(
                    lifecycle=parsed.intent.lifecycle,
                    direction=parsed.intent.direction,
                    payment_type=parsed.intent.payment_type,
                )
            )
        resolved = resolution.resolved_message_type if resolution is not None else None
        if resolved is None or resolved.value != "MT541":
            return {
                "status": "failed",
                "applicationErrorCode": "AI_DETERMINISTIC_RESOLUTION_MISMATCH",
                "finalPublicErrorCode": "AI_DETERMINISTIC_RESOLUTION_MISMATCH",
                "safeErrorMessage": (
                    "The probe interpretation did not resolve to the expected deterministic type."
                ),
                "httpStatus": response.http_status,
                "model": response.model or settings.openrouter_primary_model,
                "provider": response.provider or None,
                "promptVersion": PROMPT_VERSION,
                "schemaVersion": SCHEMA_VERSION,
                "schemaValidationFailurePaths": [],
            }
        return {
            "status": "passed",
            "applicationErrorCode": None,
            "finalPublicErrorCode": None,
            "safeErrorMessage": None,
            "httpStatus": response.http_status,
            "model": response.model or settings.openrouter_primary_model,
            "provider": response.provider or None,
            "promptVersion": PROMPT_VERSION,
            "schemaVersion": SCHEMA_VERSION,
            "schemaValidationFailurePaths": [],
            "deterministicMessageType": resolved.value,
            "promptTokens": response.usage.prompt_tokens,
            "completionTokens": response.usage.completion_tokens,
            "totalTokens": response.usage.total_tokens,
            "reportedCost": (
                str(response.usage.reported_cost)
                if response.usage.reported_cost is not None
                else None
            ),
            "latencyMs": response.latency_ms,
        }
    except AiServiceError as exc:
        return _failure(exc)
    finally:
        sanitised.clear()
        if owned_client:
            await model_client.aclose()


def _failure(error: AiServiceError) -> dict[str, Any]:
    return {
        "status": "failed",
        "applicationErrorCode": error.code,
        "primaryErrorCode": error.primary_error_code or error.code,
        "escalationErrorCode": error.escalation_error_code,
        "finalPublicErrorCode": error.final_public_error_code,
        "safeErrorMessage": error.provider_safe_message or error.safe_message,
        "httpStatus": error.provider_http_status,
        "providerErrorType": error.provider_error_type,
        "retryable": error.retryable,
        "escalated": error.escalated,
        "schemaValidationFailurePaths": list(error.failure_paths),
        "model": None,
        "provider": None,
        "promptVersion": PROMPT_VERSION,
        "schemaVersion": SCHEMA_VERSION,
    }


async def _main() -> int:
    result = await probe_live_ai(Settings())
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
