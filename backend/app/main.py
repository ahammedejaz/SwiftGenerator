from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.agents.cache import AiResultCache
from app.agents.errors import AiServiceError
from app.agents.providers.openrouter import OpenRouterClient
from app.agents.service import AgentInterpretationService
from app.api.errors import (
    ai_service_error_handler,
    domain_validation_handler,
    error_response,
    http_exception_handler,
    key_error_handler,
    value_error_handler,
)
from app.api.routes import router
from app.authoring.routes import router as authoring_router
from app.config import get_settings
from app.persistence.ai_audit import ai_audit_repository
from app.persistence.ai_cache import ai_cache_repository
from app.persistence.ai_usage import ai_usage_repository
from app.persistence.database import create_schema
from app.security.http import SlidingWindowRateLimiter
from app.security.logging import configure_safe_logging
from app.services.generation import DomainValidationError
from app.studio.routes import router as studio_router

settings = get_settings()
configure_safe_logging()
rate_limiter = SlidingWindowRateLimiter(settings.rate_limit_requests_per_minute)
ai_rate_limiter = SlidingWindowRateLimiter(settings.ai_rate_limit_requests_per_minute)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    create_schema()
    model_client = OpenRouterClient(settings) if settings.ai_provider == "openrouter" else None
    result_cache = AiResultCache(settings, ai_cache_repository)
    application.state.ai_service = AgentInterpretationService(
        settings,
        model_client,
        audit_sink=ai_audit_repository,
        cache=result_cache,
        interaction_sink=ai_usage_repository,
    )
    application.state.ai_cache = result_cache
    try:
        yield
    finally:
        await application.state.ai_service.aclose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Source-bounded deterministic ISO 15022 message authoring, validation, evidence, "
        "and controlled-operation API. No SWIFT certification is claimed."
    ),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=[
        "Content-Type",
        "X-Request-ID",
        "X-Demo-Reset-Key",
        "X-API-Key",
        settings.csrf_header_name,
    ],
)


@app.middleware("http")
async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
    request.state.request_id = request.headers.get("X-Request-ID", str(uuid4()))
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            request_bytes = int(content_length)
        except ValueError:
            return error_response(
                request,
                400,
                "INVALID_CONTENT_LENGTH",
                "The Content-Length header must be a non-negative integer.",
            )
        if request_bytes < 0:
            return error_response(
                request,
                400,
                "INVALID_CONTENT_LENGTH",
                "The Content-Length header must be a non-negative integer.",
            )
        if request_bytes > settings.max_request_bytes:
            return error_response(
                request,
                413,
                "REQUEST_TOO_LARGE",
                f"The request exceeds the {settings.max_request_bytes}-byte API limit.",
            )
    client_key = request.client.host if request.client else "unknown"
    if request.url.path.startswith("/api") and not rate_limiter.allow(client_key):
        response = error_response(
            request,
            429,
            "RATE_LIMIT_EXCEEDED",
            "The demonstration API request limit has been reached. Try again shortly.",
        )
        response.headers["Retry-After"] = "60"
        return response
    if request.url.path == "/api/agent/interpret" and not ai_rate_limiter.allow(client_key):
        response = error_response(
            request,
            429,
            "AI_RATE_LIMITED",
            "The AI interpretation request limit has been reached. Try again shortly.",
        )
        response.headers["Retry-After"] = "60"
        return response
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api"):
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response


@app.exception_handler(DomainValidationError)
async def handle_domain_validation(request: Request, exc: DomainValidationError):  # type: ignore[no-untyped-def]
    return await domain_validation_handler(request, exc)


@app.exception_handler(KeyError)
async def handle_key_error(request: Request, exc: KeyError):  # type: ignore[no-untyped-def]
    return await key_error_handler(request, exc)


@app.exception_handler(ValueError)
async def handle_value_error(request: Request, exc: ValueError):  # type: ignore[no-untyped-def]
    return await value_error_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def handle_request_validation(request: Request, exc: RequestValidationError):  # type: ignore[no-untyped-def]
    safe_details = [
        {
            "location": [str(part) for part in error["loc"]],
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    return error_response(
        request,
        422,
        "REQUEST_SCHEMA_INVALID",
        "The request does not match the required API schema.",
        safe_details,
    )


@app.exception_handler(HTTPException)
async def handle_http_exception(request: Request, exc: HTTPException):  # type: ignore[no-untyped-def]
    return await http_exception_handler(request, exc)


@app.exception_handler(AiServiceError)
async def handle_ai_service_error(request: Request, exc: AiServiceError):  # type: ignore[no-untyped-def]
    return await ai_service_error_handler(request, exc)


app.include_router(router)
app.include_router(authoring_router)
app.include_router(studio_router)
