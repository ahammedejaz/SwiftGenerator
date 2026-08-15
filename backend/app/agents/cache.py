from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
from collections import OrderedDict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol, cast

from app.agents.preprocessing import SanitizedInput
from app.agents.providers.base import ModelUsage
from app.config import Settings

_TOKEN_PATTERN = re.compile(r"\[\[SMS_(?P<kind>[A-Z_]+)_(?P<id>[A-F0-9]{8})\]\]")


class AiCacheNamespace(StrEnum):
    INTENT_INTERPRETATION = "INTENT_INTERPRETATION"
    BEGINNER_EXPLANATION = "BEGINNER_EXPLANATION"
    TAG_COMPARISON = "TAG_COMPARISON"
    VALIDATION_EXPLANATION = "VALIDATION_EXPLANATION"
    KNOWLEDGE_TRANSLATION = "KNOWLEDGE_TRANSLATION"
    CORPORATE_ACTION_INTENT = "CORPORATE_ACTION_INTENT"
    PENALTY_INTENT = "PENALTY_INTENT"


@dataclass(frozen=True)
class CacheKeyContext:
    namespace: AiCacheNamespace
    sanitised_input: str
    canonical_context: dict[str, str]
    workflow_module: str
    message_type: str | None
    profile_id: str
    profile_version: str
    standards_release: str
    prompt_version: str
    schema_version: str
    knowledge_version: str
    taxonomy_version: str
    primary_model: str
    model_settings: dict[str, str | int | float | bool]
    language: str = "en"
    audience: str = "beginner"
    tenant_partition: str = "PUBLIC_GUIDED"


@dataclass(frozen=True)
class PlaceholderNormalisation:
    canonical_text: str
    current_to_canonical: dict[str, str]
    canonical_to_current: dict[str, str]
    current_id_to_canonical: dict[str, str]
    canonical_id_to_current: dict[str, str]


@dataclass(frozen=True)
class AiCacheEntry:
    cache_id: str
    namespace: AiCacheNamespace
    key_version: str
    prompt_version: str
    schema_version: str
    knowledge_version: str
    taxonomy_version: str
    model: str
    workflow_module: str
    profile_id: str
    profile_version: str
    standards_release: str
    result_payload: dict[str, Any]
    usage: ModelUsage
    escalated: bool
    escalation_reason: str | None
    attempt_count: int
    schema_retries: int
    created_at: datetime
    expires_at: datetime
    last_accessed_at: datetime
    hit_count: int = 0

    @property
    def age_seconds(self) -> int:
        created_at = _aware(self.created_at)
        return max(0, int((datetime.now(UTC) - created_at).total_seconds()))


class AiCacheRepository(Protocol):
    def get(self, cache_id: str) -> AiCacheEntry | None: ...

    def save(self, entry: AiCacheEntry) -> None: ...

    def touch(self, cache_id: str, accessed_at: datetime) -> None: ...

    def delete(self, cache_id: str) -> None: ...

    def stats(self) -> dict[str, int]: ...


@dataclass
class InMemoryAiCacheRepository:
    entries: dict[str, AiCacheEntry] = field(default_factory=dict)

    def get(self, cache_id: str) -> AiCacheEntry | None:
        return self.entries.get(cache_id)

    def save(self, entry: AiCacheEntry) -> None:
        self.entries[entry.cache_id] = entry

    def touch(self, cache_id: str, accessed_at: datetime) -> None:
        current = self.entries.get(cache_id)
        if current is None:
            return
        self.entries[cache_id] = AiCacheEntry(
            **{
                **current.__dict__,
                "last_accessed_at": accessed_at,
                "hit_count": current.hit_count + 1,
            }
        )

    def delete(self, cache_id: str) -> None:
        self.entries.pop(cache_id, None)

    def stats(self) -> dict[str, int]:
        now = datetime.now(UTC)
        return {
            "entries": len(self.entries),
            "activeEntries": sum(_aware(item.expires_at) > now for item in self.entries.values()),
            "totalHits": sum(item.hit_count for item in self.entries.values()),
        }


class CacheStampedeTimeout(RuntimeError):
    """Raised when a duplicate request cannot await the in-flight owner safely."""


class AiCachePersistenceError(RuntimeError):
    """Safe signal that cache persistence failed without exposing stored data."""


class AiResultCache:
    def __init__(
        self,
        settings: Settings,
        repository: AiCacheRepository,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._secret = (
            settings.ai_cache_hmac_secret.get_secret_value().encode("utf-8")
            if settings.ai_cache_hmac_secret
            else None
        )
        self._l1: OrderedDict[str, AiCacheEntry] = OrderedDict()
        self._l1_lock = asyncio.Lock()
        self._singleflight_lock = asyncio.Lock()
        self._singleflight: dict[str, asyncio.Lock] = {}
        self._singleflight_users: dict[str, int] = {}

    @property
    def enabled(self) -> bool:
        return self._settings.ai_cache_enabled and self._secret is not None

    def key(self, context: CacheKeyContext) -> str:
        if self._secret is None:
            raise RuntimeError("AI cache is not securely configured")
        payload = {
            "keyVersion": self._settings.ai_cache_key_version,
            "namespace": context.namespace.value,
            "input": context.sanitised_input,
            "context": context.canonical_context,
            "workflowModule": context.workflow_module,
            "messageType": context.message_type,
            "profileId": context.profile_id,
            "profileVersion": context.profile_version,
            "standardsRelease": context.standards_release,
            "promptVersion": context.prompt_version,
            "schemaVersion": context.schema_version,
            "knowledgeVersion": context.knowledge_version,
            "taxonomyVersion": context.taxonomy_version,
            "primaryModel": context.primary_model,
            "modelSettings": context.model_settings,
            "language": context.language,
            "audience": context.audience,
            "tenantPartition": context.tenant_partition,
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return hmac.new(self._secret, encoded, hashlib.sha256).hexdigest()

    async def get(self, cache_id: str, context: CacheKeyContext) -> AiCacheEntry | None:
        if not self.enabled:
            return None
        now = datetime.now(UTC)
        async with self._l1_lock:
            entry = self._l1.get(cache_id)
            if entry is not None:
                if self._valid_entry(entry, context, now):
                    self._l1.move_to_end(cache_id)
                    await asyncio.to_thread(self._repository.touch, cache_id, now)
                    return _with_hit(entry, now)
                self._l1.pop(cache_id, None)
        entry = await asyncio.to_thread(self._repository.get, cache_id)
        if entry is None:
            return None
        if not self._valid_entry(entry, context, now):
            await asyncio.to_thread(self._repository.delete, cache_id)
            return None
        await asyncio.to_thread(self._repository.touch, cache_id, now)
        touched = _with_hit(entry, now)
        await self._put_l1(touched)
        return touched

    async def save(self, entry: AiCacheEntry) -> None:
        if not self.enabled:
            return
        await asyncio.to_thread(self._repository.save, entry)
        await self._put_l1(entry)

    async def invalidate(self, cache_id: str) -> None:
        async with self._l1_lock:
            self._l1.pop(cache_id, None)
        await asyncio.to_thread(self._repository.delete, cache_id)

    async def stats(self) -> dict[str, int | bool | str]:
        persistent = await asyncio.to_thread(self._repository.stats)
        async with self._l1_lock:
            l1_entries = len(self._l1)
        return {
            "enabled": self.enabled,
            "keyVersion": self._settings.ai_cache_key_version,
            "l1Entries": l1_entries,
            "l1Maximum": self._settings.ai_cache_l1_max_entries,
            **persistent,
        }

    @asynccontextmanager
    async def singleflight(self, cache_id: str) -> AsyncIterator[None]:
        async with self._singleflight_lock:
            lock = self._singleflight.setdefault(cache_id, asyncio.Lock())
            self._singleflight_users[cache_id] = self._singleflight_users.get(cache_id, 0) + 1
        acquired = False
        try:
            await asyncio.wait_for(
                lock.acquire(), timeout=self._settings.ai_cache_stampede_wait_seconds
            )
            acquired = True
            yield
        except TimeoutError as exc:
            raise CacheStampedeTimeout("AI cache in-flight wait timed out") from exc
        finally:
            if acquired:
                lock.release()
            async with self._singleflight_lock:
                remaining = self._singleflight_users.get(cache_id, 1) - 1
                if remaining <= 0:
                    self._singleflight_users.pop(cache_id, None)
                    self._singleflight.pop(cache_id, None)
                else:
                    self._singleflight_users[cache_id] = remaining

    async def _put_l1(self, entry: AiCacheEntry) -> None:
        async with self._l1_lock:
            self._l1[entry.cache_id] = entry
            self._l1.move_to_end(entry.cache_id)
            while len(self._l1) > self._settings.ai_cache_l1_max_entries:
                self._l1.popitem(last=False)

    def _valid_entry(
        self,
        entry: AiCacheEntry,
        context: CacheKeyContext,
        now: datetime,
    ) -> bool:
        return bool(
            _aware(entry.expires_at) > now
            and entry.key_version == self._settings.ai_cache_key_version
            and entry.namespace == context.namespace
            and entry.prompt_version == context.prompt_version
            and entry.schema_version == context.schema_version
            and entry.knowledge_version == context.knowledge_version
            and entry.taxonomy_version == context.taxonomy_version
            and entry.profile_id == context.profile_id
            and entry.profile_version == context.profile_version
            and entry.standards_release == context.standards_release
            and entry.model
            in {
                self._settings.openrouter_primary_model,
                self._settings.openrouter_escalation_model,
            }
        )

    def make_entry(
        self,
        *,
        cache_id: str,
        context: CacheKeyContext,
        result_payload: dict[str, Any],
        usage: ModelUsage,
        final_model: str,
        escalated: bool,
        escalation_reason: str | None,
        attempt_count: int,
        schema_retries: int,
    ) -> AiCacheEntry:
        now = datetime.now(UTC)
        ttl = self._ttl(context.namespace)
        return AiCacheEntry(
            cache_id=cache_id,
            namespace=context.namespace,
            key_version=self._settings.ai_cache_key_version,
            prompt_version=context.prompt_version,
            schema_version=context.schema_version,
            knowledge_version=context.knowledge_version,
            taxonomy_version=context.taxonomy_version,
            model=final_model,
            workflow_module=context.workflow_module,
            profile_id=context.profile_id,
            profile_version=context.profile_version,
            standards_release=context.standards_release,
            result_payload=result_payload,
            usage=usage,
            escalated=escalated,
            escalation_reason=escalation_reason,
            attempt_count=attempt_count,
            schema_retries=schema_retries,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl),
            last_accessed_at=now,
        )

    def _ttl(self, namespace: AiCacheNamespace) -> int:
        if namespace in {
            AiCacheNamespace.BEGINNER_EXPLANATION,
            AiCacheNamespace.TAG_COMPARISON,
            AiCacheNamespace.KNOWLEDGE_TRANSLATION,
        }:
            return self._settings.ai_cache_explanation_ttl_seconds
        if namespace == AiCacheNamespace.VALIDATION_EXPLANATION:
            return self._settings.ai_cache_validation_ttl_seconds
        return self._settings.ai_cache_intent_ttl_seconds


def normalise_placeholders(sanitised: SanitizedInput) -> PlaceholderNormalisation:
    values = sorted(
        sanitised.placeholders.values(),
        key=lambda value: sanitised.text.find(value.token),
    )
    current_to_canonical: dict[str, str] = {}
    canonical_to_current: dict[str, str] = {}
    current_id_to_canonical: dict[str, str] = {}
    canonical_id_to_current: dict[str, str] = {}
    canonical_text = sanitised.text
    for index, value in enumerate(values, start=1):
        canonical_id = f"{index:08X}"
        canonical_token = f"[[SMS_{value.kind}_{canonical_id}]]"
        current_to_canonical[value.token] = canonical_token
        canonical_to_current[canonical_token] = value.token
        current_id_to_canonical[value.placeholder_id] = canonical_id
        canonical_id_to_current[canonical_id] = value.placeholder_id
        canonical_text = canonical_text.replace(value.token, canonical_token)
    return PlaceholderNormalisation(
        canonical_text=canonical_text,
        current_to_canonical=current_to_canonical,
        canonical_to_current=canonical_to_current,
        current_id_to_canonical=current_id_to_canonical,
        canonical_id_to_current=canonical_id_to_current,
    )


def canonicalise_payload(
    payload: dict[str, Any], normalisation: PlaceholderNormalisation
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _transform_payload(
            payload,
            normalisation.current_to_canonical,
            normalisation.current_id_to_canonical,
        ),
    )


def restore_payload(
    payload: dict[str, Any], normalisation: PlaceholderNormalisation
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _transform_payload(
            payload,
            normalisation.canonical_to_current,
            normalisation.canonical_id_to_current,
        ),
    )


def _transform_payload(
    value: Any,
    token_mapping: dict[str, str],
    id_mapping: dict[str, str],
) -> Any:
    if isinstance(value, list):
        return [_transform_payload(item, token_mapping, id_mapping) for item in value]
    if isinstance(value, dict):
        return {
            key: (
                id_mapping.get(item, item)
                if key == "placeholderId" and isinstance(item, str)
                else _transform_payload(item, token_mapping, id_mapping)
            )
            for key, item in value.items()
        }
    if isinstance(value, str):
        transformed = value
        for before, after in token_mapping.items():
            transformed = transformed.replace(before, after)
        return transformed
    return value


def _with_hit(entry: AiCacheEntry, accessed_at: datetime) -> AiCacheEntry:
    return AiCacheEntry(
        **{
            **entry.__dict__,
            "last_accessed_at": accessed_at,
            "hit_count": entry.hit_count + 1,
        }
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
