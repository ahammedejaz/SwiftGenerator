"""The extraction cache: deterministic, inspectable, and free of source text.

Sources rarely change, so re-running extraction over an unchanged document should cost
nothing. The key is built entirely from hashes and version identifiers — the source
checksum, the segment hash, the prompt and schema versions, the model and provider, the
structure digest and the call's role — so no confidential text ever reaches a file name or
a key, and any change to an authority input invalidates the entry by construction.

This is a separate store rather than a namespace in ``AiResultCache`` on purpose: that
cache is HMAC-keyed to protect *raw text* it holds in its keys and is disabled without a
secret, and its key context is shaped around workflow module, profile and audience — none
of which are extraction inputs. Here there is no raw text to protect, and a developer
should be able to read the cache beside the candidates it produced.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.agents.providers.base import ModelUsage

CACHE_KEY_VERSION = "rule-extraction-key-v1"


@dataclass
class ExtractionCacheStats:
    hits: int = 0
    misses: int = 0
    writes: int = 0
    #: Tokens a hit avoided spending, as reported by the provider when the entry was made.
    tokens_avoided: int = 0


@dataclass
class ExtractionCache:
    """A file per entry. Absent directory means "no cache", not an error."""

    directory: Path
    enabled: bool = True
    stats: ExtractionCacheStats = field(default_factory=ExtractionCacheStats)

    def key(
        self,
        *,
        role: str,
        model: str,
        provider: str,
        source_checksum: str,
        segment_hash: str,
        structure_checksum: str,
        prompt_version: str,
        schema_version: str,
    ) -> str:
        payload = {
            "keyVersion": CACHE_KEY_VERSION,
            "role": role,
            "model": model,
            "provider": provider,
            "sourceChecksum": source_checksum,
            "segmentHash": segment_hash,
            "structureChecksum": structure_checksum,
            "promptVersion": prompt_version,
            "schemaVersion": schema_version,
        }
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _path(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, key: str) -> tuple[dict[str, Any], ModelUsage] | None:
        if not self.enabled:
            return None
        path = self._path(key)
        if not path.is_file():
            self.stats.misses += 1
            return None
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.stats.misses += 1
            return None
        usage = ModelUsage(
            prompt_tokens=int(stored.get("promptTokens", 0)),
            completion_tokens=int(stored.get("completionTokens", 0)),
            total_tokens=int(stored.get("totalTokens", 0)),
        )
        self.stats.hits += 1
        self.stats.tokens_avoided += usage.total_tokens
        payload = stored.get("payload")
        if not isinstance(payload, dict):
            return None
        return payload, usage

    def put(self, key: str, payload: dict[str, Any], usage: ModelUsage) -> None:
        if not self.enabled:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        record = {
            "keyVersion": CACHE_KEY_VERSION,
            "payload": payload,
            "promptTokens": usage.prompt_tokens,
            "completionTokens": usage.completion_tokens,
            "totalTokens": usage.total_tokens,
        }
        self._path(key).write_text(
            json.dumps(record, sort_keys=True, indent=1) + "\n", encoding="utf-8"
        )
        self.stats.writes += 1
