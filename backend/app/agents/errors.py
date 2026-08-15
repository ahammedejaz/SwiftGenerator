import re


class AiServiceError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int = 503,
        retryable: bool = False,
        attempt_count: int = 0,
        retry_after: str | None = None,
        provider_http_status: int | None = None,
        provider_error_type: str | None = None,
        provider_safe_message: str | None = None,
        failure_paths: tuple[str, ...] = (),
        affects_circuit: bool = False,
        escalatable: bool = True,
        primary_error_code: str | None = None,
        escalation_error_code: str | None = None,
        escalated: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.http_status = http_status
        self.retryable = retryable
        self.attempt_count = attempt_count
        self.retry_after = retry_after
        self.provider_http_status = provider_http_status
        self.provider_error_type = provider_error_type
        self.provider_safe_message = provider_safe_message
        self.failure_paths = failure_paths
        self.affects_circuit = affects_circuit
        self.escalatable = escalatable
        self.primary_error_code = primary_error_code
        self.escalation_error_code = escalation_error_code
        self.escalated = escalated

    @property
    def final_public_error_code(self) -> str:
        return self.code

    def with_attempt_count(self, attempt_count: int) -> "AiServiceError":
        return AiServiceError(
            self.code,
            self.safe_message,
            http_status=self.http_status,
            retryable=self.retryable,
            attempt_count=attempt_count,
            retry_after=self.retry_after,
            provider_http_status=self.provider_http_status,
            provider_error_type=self.provider_error_type,
            provider_safe_message=self.provider_safe_message,
            failure_paths=self.failure_paths,
            affects_circuit=self.affects_circuit,
            escalatable=self.escalatable,
            primary_error_code=self.primary_error_code,
            escalation_error_code=self.escalation_error_code,
            escalated=self.escalated,
        )

    @classmethod
    def escalation_failure(
        cls,
        primary: "AiServiceError | None",
        escalation: "AiServiceError",
        attempt_count: int,
    ) -> "AiServiceError":
        source = escalation if escalation.provider_http_status is not None else primary
        return cls(
            "AI_ESCALATION_FAILED",
            SAFE_AI_MESSAGES["AI_ESCALATION_FAILED"],
            http_status=503,
            retryable=False,
            attempt_count=attempt_count,
            provider_http_status=source.provider_http_status if source else None,
            provider_error_type=source.provider_error_type if source else None,
            provider_safe_message=source.provider_safe_message if source else None,
            failure_paths=escalation.failure_paths or (primary.failure_paths if primary else ()),
            affects_circuit=bool(
                escalation.affects_circuit or (primary and primary.affects_circuit)
            ),
            escalatable=False,
            primary_error_code=primary.code if primary else None,
            escalation_error_code=escalation.code,
            escalated=True,
        )


SAFE_AI_MESSAGES = {
    "AI_NOT_CONFIGURED": "AI interpretation is not configured. Use the deterministic form instead.",
    "AI_AUTHENTICATION_FAILED": "AI interpretation authentication failed.",
    "AI_PAYMENT_REQUIRED": "AI interpretation has no available provider credits.",
    "AI_RATE_LIMITED": "AI interpretation is temporarily rate limited. Retry later.",
    "AI_TIMEOUT": "AI interpretation timed out. Retry later or use the deterministic form.",
    "AI_PROVIDER_UNAVAILABLE": "AI interpretation is temporarily unavailable.",
    "AI_INVALID_REQUEST": "The AI provider rejected the structured interpretation request.",
    "AI_SCHEMA_REQUEST_INVALID": "The AI provider rejected the structured-output schema.",
    "AI_UNSUPPORTED_MODEL_OR_PARAMETERS": (
        "No AI endpoint supports all configured model parameters and privacy requirements."
    ),
    "AI_PRIVACY_REQUIREMENTS_UNAVAILABLE": (
        "No AI endpoint currently satisfies the configured privacy requirements."
    ),
    "AI_SCHEMA_VALIDATION_FAILED": "AI interpretation returned an invalid structured response.",
    "AI_ESCALATION_FAILED": "AI interpretation and its bounded escalation attempt failed.",
    "AI_BUDGET_EXCEEDED": "The configured AI usage budget has been reached.",
    "AI_INPUT_TOO_LARGE": "The business request exceeds the configured AI input limit.",
    "AI_CIRCUIT_OPEN": "AI interpretation is paused briefly after repeated provider failures.",
    "AI_UNSAFE_RESPONSE": "AI interpretation returned data that could not be safely grounded.",
    "AI_RAW_CONTENT_NOT_ACCEPTED": (
        "Raw MT content is handled only by the deterministic supported-subset parser."
    ),
}


def ai_error(
    code: str,
    *,
    retryable: bool = False,
    status: int = 503,
    provider_http_status: int | None = None,
    provider_error_type: str | None = None,
    provider_safe_message: str | None = None,
    failure_paths: tuple[str, ...] = (),
    affects_circuit: bool | None = None,
    escalatable: bool | None = None,
) -> AiServiceError:
    permanent_codes = {
        "AI_NOT_CONFIGURED",
        "AI_AUTHENTICATION_FAILED",
        "AI_PAYMENT_REQUIRED",
        "AI_PRIVACY_REQUIREMENTS_UNAVAILABLE",
        "AI_INVALID_REQUEST",
        "AI_SCHEMA_REQUEST_INVALID",
        "AI_UNSUPPORTED_MODEL_OR_PARAMETERS",
        "AI_BUDGET_EXCEEDED",
        "AI_INPUT_TOO_LARGE",
        "AI_CIRCUIT_OPEN",
        "AI_RAW_CONTENT_NOT_ACCEPTED",
    }
    transient_circuit_codes = {"AI_RATE_LIMITED", "AI_TIMEOUT", "AI_PROVIDER_UNAVAILABLE"}
    return AiServiceError(
        code,
        SAFE_AI_MESSAGES[code],
        http_status=status,
        retryable=retryable,
        provider_http_status=provider_http_status,
        provider_error_type=safe_provider_error_type(provider_error_type),
        provider_safe_message=provider_safe_message,
        failure_paths=failure_paths,
        affects_circuit=(
            code in transient_circuit_codes if affects_circuit is None else affects_circuit
        ),
        escalatable=code not in permanent_codes if escalatable is None else escalatable,
    )


def safe_provider_error_type(value: str | None) -> str | None:
    if value is None:
        return None
    normalised = value.strip()[:100]
    return normalised if re.fullmatch(r"[A-Za-z0-9_.:-]+", normalised) else None


def safe_provider_error_message(value: str) -> str:
    """Return a useful provider diagnostic without retaining arbitrary provider content."""
    lowered = value.casefold()
    if "no endpoints found" in lowered or "no endpoint" in lowered:
        return "No endpoint matched every required model parameter and privacy control."
    if "schema" in lowered or "response_format" in lowered:
        return "The provider rejected the structured-output schema."
    if "unsupported" in lowered or "not support" in lowered:
        return "The provider rejected an unsupported model or request parameter."
    if "rate" in lowered and "limit" in lowered:
        return "The provider reported a rate limit."
    if "timeout" in lowered or "timed out" in lowered:
        return "The provider reported a timeout."
    if "credit" in lowered or "payment" in lowered:
        return "The provider reported unavailable credits."
    if "auth" in lowered or "api key" in lowered:
        return "The provider reported an authentication failure."
    return "The provider returned an error without content-safe diagnostic text."
