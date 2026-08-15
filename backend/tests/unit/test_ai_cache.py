import asyncio
import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.agents.cache import (
    AiCacheNamespace,
    AiResultCache,
    CacheKeyContext,
    InMemoryAiCacheRepository,
    canonicalise_payload,
    normalise_placeholders,
    restore_payload,
)
from app.agents.preprocessing import sanitize_user_text
from app.agents.providers.base import (
    InterpretationModelRequest,
    InterpretationModelResponse,
    ModelUsage,
)
from app.agents.service import AgentInterpretationService
from app.agents.usage import AiInteractionEvent
from app.config import Settings
from app.domain.enums import AiProcessingSource
from app.domain.models import InterpretScenarioRequest

CACHE_SECRET = "synthetic-cache-hmac-secret-32-characters"


def cache_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "ai_provider": "openrouter",
        "openrouter_api_key": "unit-test-provider-secret",
        "openrouter_escalation_enabled": False,
        "openrouter_max_retries": 0,
        "ai_cache_hmac_secret": CACHE_SECRET,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def context(**overrides: Any) -> CacheKeyContext:
    values: dict[str, Any] = {
        "namespace": AiCacheNamespace.INTENT_INTERPRETATION,
        "sanitised_input": "Receive against payment.",
        "canonical_context": {"profileId": "BASE_DEMO_V1"},
        "workflow_module": "SETTLEMENT",
        "message_type": None,
        "profile_id": "BASE_DEMO_V1",
        "profile_version": "1.0.0",
        "standards_release": "DEMO_SR2026",
        "prompt_version": "settlement-intent-v2",
        "schema_version": "settlement-interpretation-v2",
        "knowledge_version": "KB_2026_08_05_V1",
        "taxonomy_version": "WORKFLOW_TAXONOMY_V1",
        "primary_model": "openai/gpt-5.4-mini",
        "model_settings": {"zdr": True},
    }
    values.update(overrides)
    return CacheKeyContext(**values)


def test_hmac_key_is_stable_and_versioned_without_exposing_input() -> None:
    first = AiResultCache(cache_settings(), InMemoryAiCacheRepository())
    second = AiResultCache(cache_settings(), InMemoryAiCacheRepository())
    cache_id = first.key(context())
    assert cache_id == second.key(context())
    assert len(cache_id) == 64
    assert "Receive" not in cache_id

    changed = AiResultCache(cache_settings(ai_cache_key_version="v2"), InMemoryAiCacheRepository())
    assert changed.key(context()) != cache_id


def test_tenant_partition_is_hmac_isolated_without_exposing_tenant_id() -> None:
    cache = AiResultCache(cache_settings(), InMemoryAiCacheRepository())
    first = cache.key(context(tenant_partition="TENANT_ALPHA"))
    second = cache.key(context(tenant_partition="TENANT_BETA"))
    assert first != second
    assert "TENANT_ALPHA" not in first
    assert "TENANT_BETA" not in second


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("prompt_version", "settlement-intent-v3"),
        ("schema_version", "settlement-interpretation-v3"),
        ("primary_model", "openai/gpt-5.4"),
        ("profile_version", "2.0.0"),
        ("knowledge_version", "KB_V2"),
        ("standards_release", "SR2027"),
        ("taxonomy_version", "WORKFLOW_TAXONOMY_V2"),
    ],
)
def test_context_versions_invalidate_keys(field: str, value: str) -> None:
    cache = AiResultCache(cache_settings(), InMemoryAiCacheRepository())
    assert cache.key(context(**{field: value})) != cache.key(context())


def test_sensitive_placeholders_are_normalised_and_rehydrated_per_request() -> None:
    first = sanitize_user_text(
        "Receive against payment for account SYNTHACCOUNT01.",
        6000,
        id_factory=lambda: "AAAAAAAA",
    )
    second = sanitize_user_text(
        "Receive against payment for account SYNTHACCOUNT99.",
        6000,
        id_factory=lambda: "BBBBBBBB",
    )
    first_normal = normalise_placeholders(first)
    second_normal = normalise_placeholders(second)
    assert first_normal.canonical_text == second_normal.canonical_text
    assert "SYNTHACCOUNT01" not in first_normal.canonical_text
    assert "SYNTHACCOUNT99" not in second_normal.canonical_text

    first_value = next(iter(first.placeholders.values()))
    payload = {
        "extractedFields": [
            {
                "fieldPath": "account.safekeepingAccount",
                "value": first_value.token,
                "source": "PLACEHOLDER",
                "evidenceStart": None,
                "evidenceEnd": None,
                "placeholderId": first_value.placeholder_id,
            }
        ]
    }
    cached = canonicalise_payload(payload, first_normal)
    restored = restore_payload(cached, second_normal)
    second_value = next(iter(second.placeholders.values()))
    extracted = restored["extractedFields"][0]
    assert extracted["value"] == second_value.token
    assert extracted["placeholderId"] == second_value.placeholder_id
    assert "SYNTHACCOUNT01" not in str(cached)
    assert "SYNTHACCOUNT99" not in str(cached)


class EchoPlaceholderClient:
    configured = True

    def __init__(self, delay: float = 0) -> None:
        self.calls = 0
        self.delay = delay

    async def interpret(self, request: InterpretationModelRequest) -> InterpretationModelResponse:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        match = re.search(r"\[\[SMS_SAFEKEEPING_ACCOUNT_([A-F0-9]{8})\]\]", request.sanitised_text)
        assert match is not None
        token = match.group(0)
        return InterpretationModelResponse(
            payload={
                "intent": {
                    "lifecycle": "INSTRUCTION",
                    "direction": "RECEIVE",
                    "paymentType": "AGAINST_PAYMENT",
                    "transactionType": None,
                    "function": "NEWM",
                    "responseAction": None,
                    "inferredFields": [],
                },
                "extractedFields": [
                    {
                        "fieldPath": "account.safekeepingAccount",
                        "value": token,
                        "source": "PLACEHOLDER",
                        "evidenceStart": None,
                        "evidenceEnd": None,
                        "placeholderId": match.group(1),
                    }
                ],
                "ambiguities": [],
                "missingDecisions": [],
                "interpretationSummary": "Receive securities against payment.",
                "confidence": 0.97,
                "requiresClarification": False,
            },
            model=request.model,
            attempt_count=1,
            latency_ms=8,
            usage=ModelUsage(100, 20, 120, Decimal("0.0012")),
        )

    async def aclose(self) -> None:
        return None


class InteractionCollector:
    def __init__(self) -> None:
        self.events: list[AiInteractionEvent] = []

    def save_interaction(self, event: AiInteractionEvent) -> None:
        self.events.append(event)


def test_first_request_is_live_second_is_cache_and_values_do_not_leak() -> None:
    async def scenario() -> None:
        repository = InMemoryAiCacheRepository()
        client = EchoPlaceholderClient()
        collector = InteractionCollector()
        settings = cache_settings()
        service = AgentInterpretationService(
            settings,
            client,
            cache=AiResultCache(settings, repository),
            interaction_sink=collector,
        )
        first = await service.interpret(
            InterpretScenarioRequest(
                text="Receive securities against payment for account SYNTHACCOUNT01."
            )
        )
        second = await service.interpret(
            InterpretScenarioRequest(
                text="Receive securities against payment for account SYNTHACCOUNT99."
            )
        )

        assert client.calls == 1
        assert first.scenario.account.safekeeping_account == "SYNTHACCOUNT01"
        assert second.scenario.account.safekeeping_account == "SYNTHACCOUNT99"
        assert first.ai.processing_source == AiProcessingSource.LIVE_API
        assert first.ai.api_calls == 1
        assert first.ai.total_tokens == 120
        assert second.ai.processing_source == AiProcessingSource.CACHE
        assert second.ai.api_calls == 0
        assert second.ai.total_tokens == 0
        assert second.ai.tokens_avoided == 120
        assert second.ai.cost_avoided == Decimal("0.0012")
        assert [event.source for event in collector.events] == [
            AiProcessingSource.LIVE_API,
            AiProcessingSource.CACHE,
        ]
        cached_payload = next(iter(repository.entries.values())).result_payload
        assert "SYNTHACCOUNT01" not in str(cached_payload)
        assert "SYNTHACCOUNT99" not in str(cached_payload)

    asyncio.run(scenario())


def test_concurrent_identical_requests_make_at_most_one_provider_call() -> None:
    async def scenario() -> None:
        settings = cache_settings(ai_cache_stampede_wait_seconds=2)
        client = EchoPlaceholderClient(delay=0.05)
        service = AgentInterpretationService(
            settings,
            client,
            cache=AiResultCache(settings, InMemoryAiCacheRepository()),
        )
        request = InterpretScenarioRequest(
            text="Receive securities against payment for account SYNTHACCOUNT01."
        )
        results = await asyncio.gather(service.interpret(request), service.interpret(request))
        assert client.calls == 1
        assert {item.ai.processing_source for item in results} == {
            AiProcessingSource.LIVE_API,
            AiProcessingSource.CACHE,
        }

    asyncio.run(scenario())


def test_expired_and_corrupt_entries_are_not_reused() -> None:
    async def scenario() -> None:
        settings = cache_settings()
        repository = InMemoryAiCacheRepository()
        cache = AiResultCache(settings, repository)
        key_context = context()
        entry = cache.make_entry(
            cache_id=cache.key(key_context),
            context=key_context,
            result_payload={"invalid": True},
            usage=ModelUsage(1, 1, 2),
            final_model=settings.openrouter_primary_model,
            escalated=False,
            escalation_reason=None,
            attempt_count=1,
            schema_retries=0,
        )
        repository.save(replace(entry, expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        assert await cache.get(entry.cache_id, key_context) is None
        assert repository.entries == {}

    asyncio.run(scenario())


def test_l1_cache_is_bounded() -> None:
    async def scenario() -> None:
        settings = cache_settings(ai_cache_l1_max_entries=2)
        cache = AiResultCache(settings, InMemoryAiCacheRepository())
        for index in range(3):
            key_context = context(sanitised_input=f"request-{index}")
            await cache.save(
                cache.make_entry(
                    cache_id=cache.key(key_context),
                    context=key_context,
                    result_payload={"fixture": index},
                    usage=ModelUsage(),
                    final_model=settings.openrouter_primary_model,
                    escalated=False,
                    escalation_reason=None,
                    attempt_count=1,
                    schema_retries=0,
                )
            )
        assert (await cache.stats())["l1Entries"] == 2

    asyncio.run(scenario())
