"""`/api/v1/ai` — AI-assisted authoring.

Every response that carries a message carries one produced by the deterministic composer
from canonical values the deterministic validator accepted. The model's own output never
reaches the caller as a message.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import Field

from app.ai_authoring.service import (
    AuthoringError,
    ai_sample,
    ask,
    compare_releases,
    enrich_presentation,
    identify,
    prepare,
    test_data,
)
from app.domain.models import ApiModel
from app.knowledge_base.models import QueryType
from app.studio.models import Lane, MessageFormat, OutputMode
from app.studio.security import AutomationCaller
from app.studio.service import UnknownMessageType

router = APIRouter(prefix="/api/v1/ai", tags=["AI Authoring"])


class IdentifyRequest(ApiModel):
    request: str = Field(min_length=3, max_length=2_000)
    format: MessageFormat | None = None
    limit: int = Field(default=5, ge=1, le=10)


class KnownValue(ApiModel):
    field_id: str = Field(max_length=160)
    occurrence: int = Field(default=1, ge=1, le=100)
    value: str = Field(min_length=1, max_length=2_000)


class PrepareRequest(ApiModel):
    scenario: str = Field(min_length=3, max_length=4_000)
    format: MessageFormat | None = None
    message_type: str | None = Field(default=None, max_length=32)
    release: str | None = Field(default=None, max_length=32)
    lane: Lane = Lane.CONFIGURED
    known_values: list[KnownValue] = Field(default_factory=list, max_length=500)
    profile_id: str = "BASE_DEMO_V1"


class SampleRequest(ApiModel):
    format: MessageFormat
    message_type: str = Field(min_length=3, max_length=32)
    release: str | None = Field(default=None, max_length=32)
    lane: Lane = Lane.CONFIGURED
    sample_type: str = Field(default="TYPICAL", pattern="^(?i:minimal|typical|full)$")
    profile_id: str = "BASE_DEMO_V1"
    scenario: str | None = Field(default=None, max_length=4_000)
    #: Bypass the validated-sample cache. The only way a repeat call reaches the model.
    refresh: bool = False


class TestDataRequest(ApiModel):
    format: MessageFormat
    message_type: str = Field(min_length=3, max_length=32)
    release: str | None = Field(default=None, max_length=32)
    lane: Lane = Lane.CONFIGURED
    scenario: str = Field(default="Typical synthetic scenario", max_length=4_000)
    count: int = Field(default=1, ge=1, le=100)
    sample_type: str = Field(default="TYPICAL", pattern="^(?i:minimal|typical|full)$")
    test_intent: str = Field(default="POSITIVE", pattern="^(?i:positive|negative)$")
    profile_id: str = "BASE_DEMO_V1"
    reviewer_mode: bool = False
    output_modes: list[OutputMode] | None = None


class PresentationRequest(ApiModel):
    format: MessageFormat
    message_type: str = Field(min_length=3, max_length=32)
    release: str | None = Field(default=None, max_length=32)
    lane: Lane = Lane.CONFIGURED
    field_id: str = Field(min_length=1, max_length=400)


class AskRequest(ApiModel):
    question: str = Field(min_length=3, max_length=2_000)
    format: MessageFormat | None = None
    message_type: str | None = Field(default=None, max_length=32)
    release: str | None = Field(default=None, max_length=32)
    query_type: str = Field(default="FIELD_EXPLANATION", max_length=40)


class CompareRequest(ApiModel):
    format: MessageFormat
    message_type: str = Field(min_length=3, max_length=32)
    release_a: str = Field(min_length=3, max_length=32)
    release_b: str = Field(min_length=3, max_length=32)
    focus: str | None = Field(default=None, max_length=1_000)


def _guard(call: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return call()
    except AuthoringError as error:
        raise HTTPException(
            status_code=error.status,
            detail={"code": error.code, "message": error.detail, **error.extra},
        ) from error
    except UnknownMessageType as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/messages/identify")
def identify_message(request: IdentifyRequest, caller: AutomationCaller) -> dict[str, Any]:
    """Which discovered message fits a business request. Candidates come only from the
    catalogue; the model cannot name one that does not exist."""
    del caller
    return _guard(lambda: identify(request.request, format_=request.format, limit=request.limit))


@router.post("/messages/prepare")
def prepare_message(request: PrepareRequest, caller: AutomationCaller) -> dict[str, Any]:
    """Turn a business scenario into canonical values for one message, validated."""
    del caller
    return _guard(
        lambda: prepare(
            request.scenario,
            format_=request.format,
            message_type=request.message_type,
            release=request.release,
            lane=request.lane,
            known_values=[
                item.model_dump(mode="json", by_alias=True) for item in request.known_values
            ],
            profile_id=request.profile_id,
        )
    )


@router.post("/samples")
def ai_sample_endpoint(request: SampleRequest, caller: AutomationCaller) -> dict[str, Any]:
    """An AI-prepared, deterministically validated synthetic sample. Cached by identity;
    a repeat call costs zero model calls unless ``refresh`` is set."""
    del caller
    return _guard(
        lambda: ai_sample(
            format_=request.format,
            message_type=request.message_type,
            release=request.release,
            lane=request.lane,
            sample_type=request.sample_type,
            profile_id=request.profile_id,
            refresh=request.refresh,
            scenario=request.scenario,
        )
    )


@router.post("/test-data/generate")
def ai_test_data(request: TestDataRequest, caller: AutomationCaller) -> dict[str, Any]:
    """Bulk synthetic scenarios, each independently validated and composed."""
    del caller
    return _guard(
        lambda: test_data(
            format_=request.format,
            message_type=request.message_type,
            release=request.release,
            lane=request.lane,
            scenario=request.scenario,
            count=request.count,
            sample_type=request.sample_type,
            test_intent=request.test_intent,
            profile_id=request.profile_id,
            reviewer_mode=request.reviewer_mode,
            output_modes=request.output_modes,
        )
    )


@router.post("/presentation")
def ai_presentation(request: PresentationRequest, caller: AutomationCaller) -> dict[str, Any]:
    """Plain-language metadata for one field. Zero validation authority."""
    del caller
    return _guard(
        lambda: enrich_presentation(
            format_=request.format,
            message_type=request.message_type,
            release=request.release,
            lane=request.lane,
            field_id=request.field_id,
        )
    )


@router.post("/ask")
def ai_ask(request: AskRequest, caller: AutomationCaller) -> dict[str, Any]:
    """A cited answer from indexed evidence, or a plain statement that the evidence does
    not establish it."""
    del caller
    try:
        query_type = QueryType(request.query_type.upper())
    except ValueError:
        query_type = QueryType.FIELD_EXPLANATION
    return _guard(
        lambda: ask(
            request.question,
            format_=request.format,
            message_type=request.message_type,
            release=request.release,
            query_type=query_type,
        )
    )


@router.post("/releases/compare")
def ai_compare(request: CompareRequest, caller: AutomationCaller) -> dict[str, Any]:
    """What changed between two releases of one message. Never promotes either."""
    del caller
    return _guard(
        lambda: compare_releases(
            format_=request.format,
            message_type=request.message_type,
            release_a=request.release_a,
            release_b=request.release_b,
            focus=request.focus,
        )
    )
