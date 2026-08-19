import asyncio
import json
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from time import monotonic
from typing import Any, TypedDict

import httpx

from app.agents.errors import (
    AiServiceError,
    ai_error,
    safe_provider_error_message,
    safe_provider_error_type,
)
from app.agents.prompts import CORRECTION_INSTRUCTIONS, INTENT_SYSTEM_INSTRUCTIONS
from app.agents.providers.base import (
    InterpretationModelRequest,
    InterpretationModelResponse,
    ModelUsage,
    StructuredCompletionRequest,
    StructuredCompletionResponse,
)
from app.agents.schemas import SCHEMA_NAME, ProviderSchemaError, strict_interpretation_schema
from app.config import Settings

Sleep = Callable[[float], Awaitable[None]]


class _ProviderErrorDetails(TypedDict):
    provider_http_status: int
    provider_error_type: str | None
    provider_safe_message: str


class OpenRouterClient:
    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
        sleep: Sleep = asyncio.sleep,
        random_source: Callable[[], float] = random.random,
    ) -> None:
        self._settings = settings
        self._sleep = sleep
        self._random = random_source
        self._owns_client = http_client is None
        timeout = httpx.Timeout(
            settings.openrouter_timeout_seconds,
            connect=settings.openrouter_connect_timeout_seconds,
        )
        self._client = http_client or httpx.AsyncClient(
            base_url=settings.openrouter_base_url,
            timeout=timeout,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    @property
    def configured(self) -> bool:
        return bool(
            self._settings.openrouter_api_key
            and self._settings.openrouter_api_key.get_secret_value()
        )

    def build_headers(self) -> dict[str, str]:
        if not self.configured:
            raise ai_error("AI_NOT_CONFIGURED")
        assert self._settings.openrouter_api_key is not None
        headers = {
            "Authorization": (f"Bearer {self._settings.openrouter_api_key.get_secret_value()}"),
            "Content-Type": "application/json",
        }
        if self._settings.openrouter_http_referer:
            headers["HTTP-Referer"] = self._settings.openrouter_http_referer
        if self._settings.openrouter_app_title:
            headers["X-OpenRouter-Title"] = self._settings.openrouter_app_title
        return headers

    def build_payload(self, request: InterpretationModelRequest) -> dict[str, Any]:
        context = json.dumps(request.minimal_context, separators=(",", ":"), sort_keys=True)
        user_content = (
            "Minimal confirmed non-sensitive context:\n"
            f"{context}\n"
            "BEGIN_UNTRUSTED_USER_TEXT\n"
            f"{request.sanitised_text}\n"
            "END_UNTRUSTED_USER_TEXT"
        )
        messages = [{"role": "system", "content": INTENT_SYSTEM_INSTRUCTIONS}]
        if request.correction:
            messages.append({"role": "system", "content": CORRECTION_INSTRUCTIONS})
        messages.append({"role": "user", "content": user_content})
        return {
            "model": request.model,
            "messages": messages,
            # Azure's endpoint for the pinned models advertises
            # max_completion_tokens, not the legacy max_tokens parameter.
            # Sending either max_tokens or temperature with parameter
            # enforcement enabled excludes that otherwise compatible route.
            "max_completion_tokens": self._settings.openrouter_max_output_tokens,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": SCHEMA_NAME,
                    "strict": True,
                    "schema": strict_interpretation_schema(),
                },
            },
            "provider": {
                "require_parameters": self._settings.openrouter_require_parameters,
                "allow_fallbacks": self._settings.openrouter_allow_provider_fallbacks,
                "data_collection": self._settings.openrouter_data_collection,
                "zdr": self._settings.openrouter_zdr_required,
            },
        }

    async def interpret(
        self,
        request: InterpretationModelRequest,
    ) -> InterpretationModelResponse:
        if not self.configured:
            raise ai_error("AI_NOT_CONFIGURED")
        started = monotonic()
        last_error: AiServiceError | None = None
        max_attempts = self._settings.openrouter_max_retries + 1
        for attempt in range(1, max_attempts + 1):
            try:
                try:
                    payload = self.build_payload(request)
                except ProviderSchemaError as exc:
                    raise ai_error(
                        "AI_SCHEMA_REQUEST_INVALID",
                        failure_paths=(str(exc),),
                        escalatable=False,
                    ) from exc
                response = await self._client.post(
                    "chat/completions",
                    headers=self.build_headers(),
                    json=payload,
                )
                parsed = self._parse_response(response, attempt, started)
                return parsed
            except httpx.TimeoutException as exc:
                del exc
                last_error = ai_error(
                    "AI_TIMEOUT",
                    retryable=True,
                    affects_circuit=True,
                ).with_attempt_count(attempt)
            except httpx.NetworkError as exc:
                del exc
                last_error = ai_error(
                    "AI_PROVIDER_UNAVAILABLE",
                    retryable=True,
                    affects_circuit=True,
                ).with_attempt_count(attempt)
            except AiServiceError as exc:
                last_error = exc.with_attempt_count(attempt)
            if last_error is None or not last_error.retryable or attempt >= max_attempts:
                assert last_error is not None
                raise last_error
            delay = self._retry_delay(attempt, last_error.retry_after)
            await self._sleep(delay)
        assert last_error is not None
        raise last_error

    def _parse_response(
        self,
        response: httpx.Response,
        attempt: int,
        started: float,
    ) -> InterpretationModelResponse:
        try:
            body = response.json()
        except ValueError as exc:
            if response.status_code >= 400:
                raise self._http_error(
                    response.status_code,
                    {},
                    retry_after=response.headers.get("Retry-After"),
                ) from exc
            raise ai_error(
                "AI_SCHEMA_VALIDATION_FAILED",
                provider_http_status=response.status_code,
                failure_paths=("$.providerResponse",),
            ).with_attempt_count(attempt) from exc
        if response.status_code >= 400:
            raise self._http_error(
                response.status_code,
                body,
                retry_after=response.headers.get("Retry-After"),
            )
        if not isinstance(body, dict):
            raise ai_error("AI_SCHEMA_VALIDATION_FAILED")
        embedded_error = body.get("error")
        if embedded_error:
            code = embedded_error.get("code", 502) if isinstance(embedded_error, dict) else 502
            raise self._http_error(
                int(code) if str(code).isdigit() else 502,
                body,
                retry_after=response.headers.get("Retry-After"),
            )
        try:
            choice = body["choices"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise ai_error(
                "AI_SCHEMA_VALIDATION_FAILED",
                provider_http_status=response.status_code,
                failure_paths=("$.choices[0]",),
            ) from exc
        if isinstance(choice, dict) and choice.get("error"):
            choice_error = choice["error"]
            code = choice_error.get("code", 502) if isinstance(choice_error, dict) else 502
            error_body = {"error": choice_error}
            raise self._http_error(
                int(code) if str(code).isdigit() else 502,
                error_body,
                retry_after=response.headers.get("Retry-After"),
            )
        if isinstance(choice, dict) and choice.get("finish_reason") == "error":
            raise ai_error(
                "AI_PROVIDER_UNAVAILABLE",
                provider_http_status=response.status_code,
                provider_safe_message="The provider reported a generation failure.",
                retryable=True,
                affects_circuit=True,
            )
        try:
            content = choice["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise ai_error(
                "AI_SCHEMA_VALIDATION_FAILED",
                provider_http_status=response.status_code,
                failure_paths=("$.choices[0].message.content",),
            ) from exc
        if not isinstance(content, str):
            raise ai_error(
                "AI_SCHEMA_VALIDATION_FAILED",
                provider_http_status=response.status_code,
                failure_paths=("$.choices[0].message.content",),
            )
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ai_error(
                "AI_SCHEMA_VALIDATION_FAILED",
                provider_http_status=response.status_code,
                failure_paths=("$.choices[0].message.content",),
            ) from exc
        if not isinstance(payload, dict):
            raise ai_error(
                "AI_SCHEMA_VALIDATION_FAILED",
                provider_http_status=response.status_code,
                failure_paths=("$",),
            )
        usage = self._parse_usage(body.get("usage"))
        returned_model = body.get("model")
        routed_provider = body.get("provider")
        return InterpretationModelResponse(
            payload=payload,
            model=returned_model if isinstance(returned_model, str) else "",
            attempt_count=attempt,
            latency_ms=round((monotonic() - started) * 1000),
            usage=usage,
            provider=routed_provider if isinstance(routed_provider, str) else "",
            http_status=response.status_code,
        )

    # -- generic structured completion ---------------------------------------------------

    def build_completion_payload(
        self, request: StructuredCompletionRequest
    ) -> dict[str, Any]:
        """The same transport and the same provider policy, with a caller's prompt.

        Every privacy control the interpretation path relies on is applied here too —
        parameter enforcement, data-collection denial and zero-data-retention routing come
        from one settings object, so an offline operation cannot accidentally be laxer than
        the runtime one.
        """
        return {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_content},
            ],
            "max_completion_tokens": request.max_output_tokens,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": request.schema_name,
                    "strict": True,
                    "schema": request.json_schema,
                },
            },
            "provider": {
                "require_parameters": self._settings.openrouter_require_parameters,
                "allow_fallbacks": self._settings.openrouter_allow_provider_fallbacks,
                "data_collection": self._settings.openrouter_data_collection,
                "zdr": self._settings.openrouter_zdr_required,
            },
        }

    async def complete(
        self, request: StructuredCompletionRequest
    ) -> StructuredCompletionResponse:
        if not self.configured:
            raise ai_error("AI_NOT_CONFIGURED")
        started = monotonic()
        last_error: AiServiceError | None = None
        max_attempts = self._settings.openrouter_max_retries + 1
        for attempt in range(1, max_attempts + 1):
            try:
                response = await self._client.post(
                    "chat/completions",
                    headers=self.build_headers(),
                    json=self.build_completion_payload(request),
                )
                parsed = self._parse_response(response, attempt, started)
                return StructuredCompletionResponse(
                    payload=parsed.payload,
                    model=parsed.model,
                    attempt_count=parsed.attempt_count,
                    latency_ms=parsed.latency_ms,
                    usage=parsed.usage,
                    provider=parsed.provider,
                    http_status=parsed.http_status,
                )
            except httpx.TimeoutException:
                last_error = ai_error(
                    "AI_TIMEOUT", retryable=True, affects_circuit=True
                ).with_attempt_count(attempt)
            except httpx.NetworkError:
                last_error = ai_error(
                    "AI_PROVIDER_UNAVAILABLE", retryable=True, affects_circuit=True
                ).with_attempt_count(attempt)
            except AiServiceError as exc:
                last_error = exc.with_attempt_count(attempt)
            if last_error is None or not last_error.retryable or attempt >= max_attempts:
                assert last_error is not None
                raise last_error
            await self._sleep(self._retry_delay(attempt, last_error.retry_after))
        assert last_error is not None
        raise last_error

    def _http_error(
        self,
        status: int,
        body: object,
        *,
        retry_after: str | None = None,
    ) -> AiServiceError:
        error_type = ""
        provider_message = ""
        if isinstance(body, dict) and isinstance(body.get("error"), dict):
            error = body["error"]
            provider_message = str(error.get("message", ""))
            metadata = error.get("metadata")
            if isinstance(metadata, dict):
                error_type = str(metadata.get("error_type", ""))
        lowered_message = provider_message.casefold()
        lowered_type = error_type.casefold()
        safe_message = safe_provider_error_message(provider_message)
        details: _ProviderErrorDetails = {
            "provider_http_status": status,
            "provider_error_type": safe_provider_error_type(error_type),
            "provider_safe_message": safe_message,
        }
        if status in {401, 403}:
            return ai_error(
                "AI_AUTHENTICATION_FAILED",
                status=503,
                escalatable=False,
                **details,
            )
        if status == 402:
            return ai_error(
                "AI_PAYMENT_REQUIRED",
                status=503,
                escalatable=False,
                **details,
            )
        if status == 429 or lowered_type == "rate_limit_exceeded":
            error = ai_error(
                "AI_RATE_LIMITED",
                retryable=True,
                status=429,
                affects_circuit=True,
                **details,
            )
            error.retry_after = retry_after
            return error
        if status in {408, 504} or lowered_type == "timeout":
            error = ai_error(
                "AI_TIMEOUT",
                retryable=True,
                affects_circuit=True,
                **details,
            )
            error.retry_after = retry_after
            return error
        privacy_terms = ("zdr", "data policy", "privacy", "routing requirements")
        if (
            status in {404, 503}
            and self._settings.openrouter_zdr_required
            and any(term in lowered_message for term in privacy_terms)
        ):
            return ai_error(
                "AI_PRIVACY_REQUIREMENTS_UNAVAILABLE",
                escalatable=False,
                **details,
            )
        if status == 404:
            return ai_error(
                "AI_UNSUPPORTED_MODEL_OR_PARAMETERS",
                escalatable=False,
                **details,
            )
        if status in {400, 409, 412, 413, 422}:
            if "schema" in lowered_message or "response_format" in lowered_message:
                return ai_error(
                    "AI_SCHEMA_REQUEST_INVALID",
                    status=400,
                    escalatable=False,
                    **details,
                )
            return ai_error(
                "AI_INVALID_REQUEST",
                status=400,
                escalatable=False,
                **details,
            )
        if status in {500, 502, 503}:
            error = ai_error(
                "AI_PROVIDER_UNAVAILABLE",
                retryable=True,
                affects_circuit=True,
                **details,
            )
            error.retry_after = retry_after
            return error
        return ai_error(
            "AI_PROVIDER_UNAVAILABLE",
            escalatable=False,
            **details,
        )

    def retry_after_delay(self, response: httpx.Response, attempt: int) -> float:
        return self._retry_delay(attempt, response.headers.get("Retry-After"))

    def _retry_delay(self, attempt: int, retry_after: str | None) -> float:
        maximum = self._settings.openrouter_retry_max_seconds
        if retry_after:
            try:
                seconds = float(retry_after)
            except ValueError:
                try:
                    parsed = parsedate_to_datetime(retry_after)
                    seconds = max(0.0, (parsed - datetime.now(UTC)).total_seconds())
                except (TypeError, ValueError, OverflowError):
                    seconds = 0.0
            if seconds > 0:
                return min(seconds, maximum)
        exponential = self._settings.openrouter_retry_base_seconds * (2 ** (attempt - 1))
        jitter = self._random() * self._settings.openrouter_retry_base_seconds
        return float(min(exponential + jitter, maximum))

    @staticmethod
    def _parse_usage(raw: object) -> ModelUsage:
        if not isinstance(raw, dict):
            return ModelUsage()
        cost: Decimal | None = None
        if raw.get("cost") is not None:
            try:
                cost = Decimal(str(raw["cost"]))
            except (InvalidOperation, ValueError):
                cost = None
        return ModelUsage(
            prompt_tokens=_safe_non_negative_int(raw.get("prompt_tokens")),
            completion_tokens=_safe_non_negative_int(raw.get("completion_tokens")),
            total_tokens=_safe_non_negative_int(raw.get("total_tokens")),
            reported_cost=cost,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def _safe_non_negative_int(value: object) -> int:
    if isinstance(value, int) and value >= 0:
        return value
    return 0
