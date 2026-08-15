from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.agents.errors import AiServiceError
from app.domain.models import ValidationFinding, to_camel
from app.services.generation import DomainValidationError


class ErrorBody(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    code: str
    message: str
    details: list[Any] = Field(default_factory=list)
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: list[Any] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    envelope = ErrorEnvelope(
        error=ErrorBody(
            code=code,
            message=message,
            details=details or [],
            request_id=request_id,
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json", by_alias=True),
    )


async def domain_validation_handler(request: Request, exc: DomainValidationError) -> JSONResponse:
    details = [
        ValidationFinding.model_validate(item).model_dump(mode="json", by_alias=True)
        for item in exc.report.findings
    ]
    return error_response(
        request,
        422,
        "VALIDATION_FAILED",
        "The scenario contains blocking validation errors.",
        details,
    )


async def key_error_handler(request: Request, exc: KeyError) -> JSONResponse:
    return error_response(request, 404, "RESOURCE_NOT_FOUND", str(exc).strip("'"))


async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return error_response(request, 400, "INVALID_REQUEST", str(exc))


async def ai_service_error_handler(request: Request, exc: AiServiceError) -> JSONResponse:
    return error_response(
        request,
        exc.http_status,
        exc.code,
        exc.safe_message,
    )
