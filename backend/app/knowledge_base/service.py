"""The one runtime door onto the knowledge base.

Everything the API, the catalogue and the AI authoring paths need — status, retrieval,
message listings, the validated-sample and presentation caches, telemetry — goes through
here, so there is one place that knows the database may not exist yet and answers
``NOT_INDEXED`` instead of failing. Generation never calls this module.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from dataclasses import dataclass
from typing import Any

from app.config import Settings, get_settings
from app.knowledge_base import CHUNKER_VERSION
from app.knowledge_base.db import KnowledgeDatabase
from app.knowledge_base.embeddings import EmbeddingProvider, embedding_provider
from app.knowledge_base.models import (
    Citation,
    ExternalPolicy,
    QueryType,
    RetrievalFilter,
    RetrievalResult,
    Section,
    SourceFormat,
    SourceRecord,
)
from app.knowledge_base.paths import knowledge_db_path, knowledge_roots
from app.knowledge_base.policy import policy_statement
from app.knowledge_base.retrieval import HybridRetriever, RetrievalOptions


@dataclass(frozen=True)
class KnowledgeStatus:
    mode: str
    enabled: bool
    indexed: bool
    admin_enabled: bool
    db_present: bool
    roots: list[str]
    roots_missing: list[str]
    counts: dict[str, int]
    last_run: dict[str, Any] | None
    corpus_version: str | None
    embedding_provider: str
    embedding_deployment_configured: bool
    embedding_dimensions: int | None
    embedding_policy_statement: str | None
    llm_provider: str
    sources_embedding_blocked: int
    sources_embedding_allowed: int
    load_errors: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "enabled": self.enabled,
            "indexed": self.indexed,
            "adminEnabled": self.admin_enabled,
            "databasePresent": self.db_present,
            "roots": self.roots,
            "rootsMissing": self.roots_missing,
            "counts": self.counts,
            "lastRun": self.last_run,
            "corpusVersion": self.corpus_version,
            "embeddingProvider": self.embedding_provider,
            "embeddingDeploymentConfigured": self.embedding_deployment_configured,
            "embeddingDimensions": self.embedding_dimensions,
            "embeddingPolicyStatement": self.embedding_policy_statement,
            "llmProvider": self.llm_provider,
            "sourcesEmbeddingBlocked": self.sources_embedding_blocked,
            "sourcesEmbeddingAllowed": self.sources_embedding_allowed,
            "loadErrors": self.load_errors,
            "message": (
                None
                if self.indexed
                else "Knowledge Base has not been indexed yet. Run `make knowledge-sync`."
                if self.enabled
                else "Knowledge Base is disabled (KNOWLEDGE_MODE=disabled)."
            ),
        }


class KnowledgeService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._database = KnowledgeDatabase(knowledge_db_path(self._settings))
        self._embeddings: EmbeddingProvider | None = None
        self._lock = threading.Lock()

    # -- wiring ----------------------------------------------------------------------------

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def database(self) -> KnowledgeDatabase:
        return self._database

    @property
    def enabled(self) -> bool:
        return self._settings.knowledge_enabled

    @property
    def indexed(self) -> bool:
        return self.enabled and self._database.exists

    @property
    def embeddings(self) -> EmbeddingProvider:
        with self._lock:
            if self._embeddings is None:
                self._embeddings = embedding_provider(self._settings)
            return self._embeddings

    def corpus_version(self) -> str | None:
        if not self.indexed:
            return None
        try:
            return self._database.get_meta("corpus_version")
        except sqlite3.Error:
            return None

    def message_corpus_version(self, format_: str, message_type: str, release: str | None) -> str:
        """A corpus identity scoped to one message, so an unrelated source change does not
        invalidate every cached sample."""
        if not self.indexed:
            return "no-index"
        with self._database.read() as connection:
            rows = connection.execute(
                "SELECT source_id, checksum FROM knowledge_source WHERE deleted = 0 AND format = ? "
                "AND (message_type = ? OR message_version = ?) AND (release IS ? OR release = ?) "
                "ORDER BY source_id",
                (format_, message_type, message_type, release, release),
            ).fetchall()
        digest = hashlib.sha256(CHUNKER_VERSION.encode())
        for row in rows:
            digest.update(f"{row['source_id']}|{row['checksum']}|".encode())
        return digest.hexdigest()

    # -- status ----------------------------------------------------------------------------

    def status(self) -> KnowledgeStatus:
        roots = knowledge_roots(self._settings)
        counts: dict[str, int] = {}
        last_run = None
        corpus = None
        blocked = allowed = 0
        dimensions: int | None = None
        load_errors: list[str] = []
        if self.indexed:
            try:
                counts = self._database.counts()
                last_run = self._database.last_run()
                corpus = self._database.get_meta("corpus_version")
                with self._database.read() as connection:
                    for row in connection.execute(
                        "SELECT embedding_policy, COUNT(*) AS n FROM knowledge_source "
                        "WHERE deleted = 0 GROUP BY embedding_policy"
                    ):
                        if row["embedding_policy"] == ExternalPolicy.BLOCKED.value:
                            blocked = int(row["n"])
                        else:
                            allowed = int(row["n"])
                    dim_row = connection.execute(
                        "SELECT dimensions FROM knowledge_embedding LIMIT 1"
                    ).fetchone()
                    dimensions = int(dim_row["dimensions"]) if dim_row else None
            except sqlite3.Error as error:
                load_errors.append(f"knowledge database: {type(error).__name__}")
        if self.enabled:
            from app.knowledge_base.preview import preview_registries

            load_errors.extend(preview_registries().load_errors)
        return KnowledgeStatus(
            mode=self._settings.knowledge_mode,
            enabled=self.enabled,
            indexed=self.indexed and bool(counts),
            admin_enabled=self._settings.knowledge_mode == "local_uat",
            db_present=self._database.exists,
            roots=[root.name for root in roots],
            roots_missing=[root.name for root in roots if not root.exists()],
            counts=counts,
            last_run=last_run,
            corpus_version=corpus,
            embedding_provider=self._settings.embedding_provider_effective,
            embedding_deployment_configured=bool(self._settings.embeddings_deployment)
            and self._settings.embedding_provider_effective not in {"disabled"},
            embedding_dimensions=dimensions or self._settings.embedding_dimensions,
            embedding_policy_statement=policy_statement(blocked, blocked + allowed),
            llm_provider=self._settings.structured_ai_provider_effective,
            sources_embedding_blocked=blocked,
            sources_embedding_allowed=allowed,
            load_errors=load_errors,
        )

    # -- sources and messages ----------------------------------------------------------------

    def sources(self) -> list[SourceRecord]:
        if not self.indexed:
            return []
        return self._database.sources(include_deleted=True)

    def source_counts(self) -> dict[tuple[str, str, str], int]:
        """``(format, messageType, release-or-version) -> indexed source count``."""
        if not self.indexed:
            return {}
        counts: dict[tuple[str, str, str], int] = {}
        for source in self._database.sources():
            if source.format is SourceFormat.UNKNOWN or not source.message_type:
                continue
            if source.format is SourceFormat.MX:
                key = (
                    "MX",
                    source.message_type,
                    source.message_version or "",
                )
            else:
                key = ("MT", source.message_type, source.release or "")
            counts[key] = counts.get(key, 0) + 1
        return counts

    def messages(self) -> list[dict[str, Any]]:
        """Every message identity the knowledge base knows, with its source and structure
        state. The catalogue projection is richer; this is the raw knowledge view."""
        if not self.indexed:
            return []
        from app.knowledge_base.preview import preview_registries

        registries = preview_registries()
        by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
        for source in self._database.sources():
            if source.format is SourceFormat.UNKNOWN or not source.message_type:
                continue
            release = (
                source.message_version if source.format is SourceFormat.MX else source.release
            ) or ""
            key = (source.format.value, source.message_type, release)
            entry = by_key.setdefault(
                key,
                {
                    "format": source.format.value,
                    "messageType": source.message_type,
                    "messageVersion": source.message_version,
                    "release": source.release,
                    "title": source.title,
                    "sources": [],
                    "segments": 0,
                    "embedded": 0,
                    "embeddingPolicy": source.embedding_policy.value,
                    "llmPolicy": source.llm_policy.value,
                    "readiness": "KNOWLEDGE_ONLY",
                    "blockers": ["STRUCTURE_SOURCE_MISSING"],
                    "structureSource": None,
                },
            )
            entry["sources"].append(
                {
                    "sourceId": source.source_id,
                    "documentType": source.document_type.value,
                    "pages": source.page_count,
                    "state": source.ingestion_state.value,
                    "checksum": f"sha256:{source.checksum[:16]}…",
                }
            )
            entry["segments"] += source.segment_count
            entry["embedded"] += source.embedded_count
        for (format_name, message_type, release), status in registries.structures.items():
            entry = by_key.setdefault(
                (format_name, message_type, release),
                {
                    "format": format_name,
                    "messageType": message_type,
                    "messageVersion": release if format_name == "MX" else None,
                    "release": release if format_name == "MT" else None,
                    "title": status.name,
                    "sources": [],
                    "segments": 0,
                    "embedded": 0,
                    "embeddingPolicy": None,
                    "llmPolicy": None,
                    "readiness": status.readiness.value,
                    "blockers": list(status.blockers),
                    "structureSource": status.structure_source,
                },
            )
            entry["readiness"] = status.readiness.value
            entry["blockers"] = list(status.blockers)
            entry["structureSource"] = status.structure_source
            entry["gates"] = status.gates
        return [by_key[key] for key in sorted(by_key)]

    def message_status(self, message: str) -> dict[str, Any] | None:
        wanted = message.strip()
        matches = [
            item
            for item in self.messages()
            if item["messageType"].lower() == wanted.lower()
            or (item.get("messageVersion") or "").lower() == wanted.lower()
        ]
        if not matches:
            return None
        return {"message": wanted, "entries": matches}

    # -- retrieval ---------------------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        *,
        query_type: QueryType,
        filter: RetrievalFilter,
        options: RetrievalOptions | None = None,
    ) -> RetrievalResult:
        if not self.indexed:
            return RetrievalResult(
                query_type=query_type,
                filter=filter,
                hits=[],
                lexical_candidates=0,
                semantic_candidates=0,
                semantic_available=False,
                semantic_reason="KNOWLEDGE_NOT_INDEXED",
                latency_ms=0,
                context_chars=0,
                corpus_version="",
            )
        retriever = HybridRetriever(
            self._database, self.embeddings, corpus_version=self.corpus_version() or ""
        )
        opts = options or RetrievalOptions(context_chars=self._settings.knowledge_context_chars)
        return retriever.retrieve(query, query_type=query_type, filter=filter, options=opts)

    def snippets_allowed(self, source_ids: set[str]) -> bool:
        """Excerpts may be quoted only when every cited source permits it (synthetic
        fixtures). Licensed material is cited by location."""
        if not source_ids or not self.indexed:
            return False
        with self._database.read() as connection:
            rows = connection.execute(
                "SELECT DISTINCT classification FROM knowledge_source WHERE source_id IN ("
                + ",".join("?" for _ in source_ids)
                + ")",
                list(source_ids),
            ).fetchall()
        return bool(rows) and all(row["classification"] == "SYNTHETIC_FIXTURE" for row in rows)

    def llm_allowed(self, source_ids: set[str]) -> bool:
        """May the text of these sources be sent to the configured model?"""
        if not source_ids or not self.indexed:
            return False
        with self._database.read() as connection:
            rows = connection.execute(
                "SELECT DISTINCT llm_policy FROM knowledge_source WHERE source_id IN ("
                + ",".join("?" for _ in source_ids)
                + ")",
                list(source_ids),
            ).fetchall()
        return bool(rows) and all(row["llm_policy"] == ExternalPolicy.ALLOWED.value for row in rows)

    def citations(self, result: RetrievalResult) -> list[Citation]:
        allow = self.snippets_allowed({hit.segment.source_id for hit in result.hits})
        return result.citations(allow_snippets=allow)

    # -- caches ------------------------------------------------------------------------------

    def sample_cache_get(self, cache_key: str) -> dict[str, Any] | None:
        if not self.indexed:
            return None
        with self._database.write() as connection:
            row = connection.execute(
                "SELECT payload FROM knowledge_sample_cache WHERE cache_key = ?", (cache_key,)
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE knowledge_sample_cache SET hits = hits + 1 WHERE cache_key = ?",
                (cache_key,),
            )
            payload = json.loads(row["payload"])
            assert isinstance(payload, dict)
            return payload

    def sample_cache_put(
        self,
        cache_key: str,
        *,
        format_: str,
        message_type: str,
        release: str,
        lane: str,
        sample_type: str,
        payload: dict[str, Any],
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        llm_calls: int,
    ) -> None:
        if not self.enabled:
            return
        self._database.initialise()
        with self._database.write() as connection:
            connection.execute(
                """
                INSERT INTO knowledge_sample_cache(cache_key, format, message_type, release, lane,
                    sample_type, payload, provider, model, prompt_tokens, completion_tokens,
                    llm_calls, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?, datetime('now'))
                ON CONFLICT(cache_key) DO UPDATE SET payload = excluded.payload,
                    provider = excluded.provider, model = excluded.model,
                    prompt_tokens = excluded.prompt_tokens,
                    completion_tokens = excluded.completion_tokens,
                    llm_calls = excluded.llm_calls, created_at = excluded.created_at
                """,
                (
                    cache_key,
                    format_,
                    message_type,
                    release,
                    lane,
                    sample_type,
                    json.dumps(payload, sort_keys=True),
                    provider,
                    model,
                    prompt_tokens,
                    completion_tokens,
                    llm_calls,
                ),
            )

    def sample_cached(self, format_: str, message_type: str, release: str) -> bool:
        if not self.indexed:
            return False
        try:
            with self._database.read() as connection:
                row = connection.execute(
                    "SELECT 1 FROM knowledge_sample_cache WHERE format = ? AND message_type = ? "
                    "AND release = ? LIMIT 1",
                    (format_, message_type, release),
                ).fetchone()
            return row is not None
        except sqlite3.Error:
            return False

    def presentation_get(self, cache_key: str) -> dict[str, Any] | None:
        if not self.indexed:
            return None
        with self._database.read() as connection:
            row = connection.execute(
                "SELECT payload FROM knowledge_presentation_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload"])
        assert isinstance(payload, dict)
        return payload

    def presentation_put(
        self,
        cache_key: str,
        *,
        format_: str,
        message_type: str,
        release: str,
        field_id: str,
        payload: dict[str, Any],
        provider: str,
        model: str,
    ) -> None:
        if not self.enabled:
            return
        self._database.initialise()
        with self._database.write() as connection:
            connection.execute(
                "INSERT INTO knowledge_presentation_cache(cache_key, format, message_type, "
                "release, field_id, payload, provider, model, created_at) "
                "VALUES (?,?,?,?,?,?,?,?, datetime('now')) "
                "ON CONFLICT(cache_key) DO UPDATE SET payload = excluded.payload, "
                "provider = excluded.provider, model = excluded.model, "
                "created_at = excluded.created_at",
                (
                    cache_key,
                    format_,
                    message_type,
                    release,
                    field_id,
                    json.dumps(payload, sort_keys=True),
                    provider,
                    model,
                ),
            )

    # -- telemetry ---------------------------------------------------------------------------

    def record_ai_metric(
        self,
        *,
        operation: str,
        provider: str,
        model: str,
        llm_calls: int,
        prompt_tokens: int,
        completion_tokens: int,
        cache_hit: bool,
        calls_avoided: int,
        tokens_avoided: int,
        latency_ms: int,
        outcome: str,
    ) -> None:
        if not self.enabled:
            return
        try:
            self._database.initialise()
            with self._database.write() as connection:
                connection.execute(
                    "INSERT INTO knowledge_ai_metric(at, operation, provider, model, llm_calls, "
                    "prompt_tokens, completion_tokens, cache_hit, calls_avoided, tokens_avoided, "
                    "latency_ms, outcome) VALUES (datetime('now'),?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        operation,
                        provider,
                        model,
                        llm_calls,
                        prompt_tokens,
                        completion_tokens,
                        1 if cache_hit else 0,
                        calls_avoided,
                        tokens_avoided,
                        latency_ms,
                        outcome,
                    ),
                )
        except sqlite3.Error:
            return

    def telemetry(self) -> dict[str, Any]:
        if not self.indexed:
            return {
                "indexed": False,
                "llm": {},
                "embeddings": {},
                "retrieval": {},
                "costAvailable": False,
                "costNote": "cost unavailable: the configured provider does not report cost",
            }
        with self._database.read() as connection:
            llm = connection.execute(
                "SELECT COUNT(*) AS operations, COALESCE(SUM(llm_calls),0) AS calls, "
                "COALESCE(SUM(prompt_tokens),0) AS prompt_tokens, "
                "COALESCE(SUM(completion_tokens),0) AS completion_tokens, "
                "COALESCE(SUM(cache_hit),0) AS cache_hits, "
                "COALESCE(SUM(calls_avoided),0) AS calls_avoided, "
                "COALESCE(SUM(tokens_avoided),0) AS tokens_avoided, "
                "COALESCE(AVG(latency_ms),0) AS avg_latency_ms FROM knowledge_ai_metric"
            ).fetchone()
            retrieval = connection.execute(
                "SELECT COUNT(*) AS queries, COALESCE(AVG(latency_ms),0) AS avg_latency_ms, "
                "COALESCE(AVG(hits),0) AS avg_hits, "
                "SUM(CASE WHEN method = 'HYBRID' THEN 1 ELSE 0 END) AS hybrid, "
                "SUM(CASE WHEN method = 'LEXICAL' THEN 1 ELSE 0 END) AS lexical, "
                "SUM(CASE WHEN method = 'SEMANTIC' THEN 1 ELSE 0 END) AS semantic "
                "FROM knowledge_retrieval_metric"
            ).fetchone()
            last_run = self._database.last_run()
            embeddings = connection.execute(
                "SELECT COUNT(*) AS vectors, COUNT(DISTINCT segment_id) AS segments "
                "FROM knowledge_embedding"
            ).fetchone()
            samples = connection.execute(
                "SELECT COUNT(*) AS cached, COALESCE(SUM(hits),0) AS hits "
                "FROM knowledge_sample_cache"
            ).fetchone()
        stats = (last_run or {}).get("stats", {}) if last_run else {}
        return {
            "indexed": True,
            "llm": {
                "operations": int(llm["operations"]),
                "calls": int(llm["calls"]),
                "promptTokens": int(llm["prompt_tokens"]),
                "completionTokens": int(llm["completion_tokens"]),
                "cacheHits": int(llm["cache_hits"]),
                "callsAvoided": int(llm["calls_avoided"]),
                "tokensAvoided": int(llm["tokens_avoided"]),
                "averageLatencyMs": round(float(llm["avg_latency_ms"])),
            },
            "embeddings": {
                "vectorsStored": int(embeddings["vectors"]),
                "segmentsEmbedded": int(embeddings["segments"]),
                "lastRunRequests": stats.get("embeddingRequests", 0),
                "lastRunCacheHits": stats.get("embeddingCacheHits", 0),
                "lastRunRequestsAvoided": stats.get("embeddingRequestsAvoided", 0),
                "lastRunTokens": stats.get("embeddingTokens"),
                "lastRunBlockedSegments": stats.get("embeddingBlockedSegments", 0),
                "provider": self._settings.embedding_provider_effective,
            },
            "retrieval": {
                "queries": int(retrieval["queries"]),
                "averageLatencyMs": round(float(retrieval["avg_latency_ms"])),
                "averageSegments": round(float(retrieval["avg_hits"]), 1),
                "hybrid": int(retrieval["hybrid"] or 0),
                "lexical": int(retrieval["lexical"] or 0),
                "semantic": int(retrieval["semantic"] or 0),
            },
            "samples": {"cached": int(samples["cached"]), "cacheHits": int(samples["hits"])},
            "costAvailable": False,
            "costNote": "cost unavailable: the configured provider does not report cost",
        }


def section_filter(names: list[str] | None) -> tuple[Section, ...]:
    if not names:
        return ()
    result: list[Section] = []
    for name in names:
        try:
            result.append(Section(name.strip().upper()))
        except ValueError:
            continue
    return tuple(result)


knowledge_service = KnowledgeService()
