"""Hybrid retrieval: metadata narrowing → BM25 → cosine → reciprocal rank fusion.

Deterministic from end to end. Ties break on the segment id so a rebuilt index returns the
same evidence in the same order, and no model takes part in ranking.
"""

from __future__ import annotations

import re
import sqlite3
import time
from collections.abc import Sequence
from dataclasses import dataclass

from app.knowledge_base import EMBEDDING_SCHEMA_VERSION
from app.knowledge_base.db import KnowledgeDatabase, segment_from_row
from app.knowledge_base.embeddings import EmbeddingError, EmbeddingProvider
from app.knowledge_base.models import (
    QueryType,
    RetrievalFilter,
    RetrievalHit,
    RetrievalMethod,
    RetrievalResult,
    SegmentRecord,
)
from app.knowledge_base.vector_store import SqliteNumpyVectorStore, filter_sql

RRF_K = 60
DEFAULT_K_LEXICAL = 20
DEFAULT_K_SEMANTIC = 20
MAX_PER_SECTION = 4
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")
#: Words that carry no retrieval signal for a standards corpus.
STOP = frozenset(
    "the a an of to in for and or is are be with on at by from this that as it its which "
    "what when where who how do does i we you my our need want please".split()
)


@dataclass
class RetrievalOptions:
    k_lexical: int = DEFAULT_K_LEXICAL
    k_semantic: int = DEFAULT_K_SEMANTIC
    max_per_section: int = MAX_PER_SECTION
    context_chars: int = 6_000
    #: False forces lexical-only retrieval even when embeddings exist.
    use_semantic: bool = True
    #: Nearest-neighbour search always answers; a cosine score below this is noise, not
    #: evidence, so such hits are dropped and an unrelated question gets no answer.
    min_semantic_score: float = 0.25


def fts_query(text: str) -> str | None:
    """A safe FTS5 MATCH expression: every token quoted, joined with OR.

    Quoting defeats the FTS5 operator grammar, so a tester's ``:95P::PSET`` or ``C6`` is a
    term and never a syntax error. Identifier-shaped tokens are also added as their bare
    four-letter / tag forms because that is how they were indexed.
    """
    terms: list[str] = []
    for token in TOKEN.findall(text):
        lowered = token.lower()
        if lowered in STOP or len(lowered) < 2:
            continue
        terms.append(token)
        if ":" in token or "//" in token:
            terms.extend(part for part in re.split(r"[:/]+", token) if len(part) >= 2)
    seen: dict[str, None] = {}
    for term in terms:
        seen.setdefault(term.replace('"', ""), None)
    if not seen:
        return None
    return " OR ".join(f'"{term}"' for term in list(seen)[:32])


class HybridRetriever:
    def __init__(
        self,
        database: KnowledgeDatabase,
        embeddings: EmbeddingProvider,
        *,
        corpus_version: str = "",
    ) -> None:
        self._database = database
        self._embeddings = embeddings
        self._vectors = SqliteNumpyVectorStore(database)
        self._corpus_version = corpus_version

    def retrieve(
        self,
        query: str,
        *,
        query_type: QueryType,
        filter: RetrievalFilter,
        options: RetrievalOptions | None = None,
    ) -> RetrievalResult:
        opts = options or RetrievalOptions()
        started = time.monotonic()
        lexical = self._lexical(query, filter, opts.k_lexical)
        semantic: list[tuple[SegmentRecord, float]] = []
        semantic_available = False
        semantic_reason: str | None = None
        if opts.use_semantic and self._embeddings.available:
            dimensions = self._stored_dimensions()
            if dimensions is None:
                semantic_reason = "no embeddings are stored for this deployment"
            else:
                covered = self._vectors.count(
                    provider=self._embeddings.name,
                    deployment=self._embeddings.deployment,
                    dimensions=dimensions,
                    schema_version=EMBEDDING_SCHEMA_VERSION,
                    filter=filter,
                )
                if covered == 0:
                    semantic_reason = "EMBEDDING_BLOCKED_BY_POLICY or not indexed for this filter"
                else:
                    try:
                        query_vector = self._embeddings.embed([query]).vectors[0]
                        hits = self._vectors.search(
                            query_vector,
                            provider=self._embeddings.name,
                            deployment=self._embeddings.deployment,
                            dimensions=dimensions,
                            schema_version=EMBEDDING_SCHEMA_VERSION,
                            filter=filter,
                            k=opts.k_semantic,
                        )
                        by_id = self._segments([hit.segment_id for hit in hits])
                        semantic = [
                            (by_id[hit.segment_id], hit.score)
                            for hit in hits
                            if hit.segment_id in by_id and hit.score >= opts.min_semantic_score
                        ]
                        semantic_available = True
                    except (EmbeddingError, ValueError) as error:
                        semantic_reason = getattr(error, "code", "EMBEDDING_PROVIDER_UNAVAILABLE")
        elif not self._embeddings.available:
            semantic_reason = "EMBEDDING_PROVIDER_UNAVAILABLE"
        fused = _fuse(lexical, semantic)
        diversified = _diversify(fused, opts.max_per_section)
        budgeted, context_chars = _budget(diversified, opts.context_chars)
        result = RetrievalResult(
            query_type=query_type,
            filter=filter,
            hits=budgeted,
            lexical_candidates=len(lexical),
            semantic_candidates=len(semantic),
            semantic_available=semantic_available,
            semantic_reason=semantic_reason,
            latency_ms=round((time.monotonic() - started) * 1000),
            context_chars=context_chars,
            corpus_version=self._corpus_version,
        )
        self._record(result)
        return result

    # -- lexical ------------------------------------------------------------------------

    def _lexical(
        self, query: str, filter: RetrievalFilter, k: int
    ) -> list[tuple[SegmentRecord, float]]:
        expression = fts_query(query)
        if expression is None:
            return []
        where, params = filter_sql(filter)
        sql = (
            "SELECT s.*, bm25(knowledge_fts, 0.0, 2.0, 2.0, 1.0, 4.0, 6.0, 1.0) AS rank "
            "FROM knowledge_fts JOIN knowledge_segment s "
            "ON s.segment_id = knowledge_fts.segment_id "
            f"WHERE knowledge_fts MATCH ? AND {where} ORDER BY rank, s.segment_id LIMIT ?"
        )
        with self._database.read() as connection:
            try:
                rows = connection.execute(sql, [expression, *params, k]).fetchall()
            except sqlite3.OperationalError:
                return []
        return [(segment_from_row(row), -float(row["rank"])) for row in rows]

    # -- semantic -----------------------------------------------------------------------

    def _stored_dimensions(self) -> int | None:
        with self._database.read() as connection:
            row = connection.execute(
                "SELECT dimensions FROM knowledge_embedding WHERE provider = ? AND deployment = ? "
                "AND schema_version = ? LIMIT 1",
                (self._embeddings.name, self._embeddings.deployment, EMBEDDING_SCHEMA_VERSION),
            ).fetchone()
            return int(row["dimensions"]) if row else None

    def _segments(self, ids: Sequence[str]) -> dict[str, SegmentRecord]:
        if not ids:
            return {}
        with self._database.read() as connection:
            rows = connection.execute(
                "SELECT * FROM knowledge_segment WHERE segment_id IN ("
                + ",".join("?" for _ in ids)
                + ")",
                list(ids),
            ).fetchall()
        return {str(row["segment_id"]): segment_from_row(row) for row in rows}

    # -- telemetry ------------------------------------------------------------------------

    def _record(self, result: RetrievalResult) -> None:
        method = (
            RetrievalMethod.HYBRID
            if result.semantic_candidates and result.lexical_candidates
            else RetrievalMethod.SEMANTIC
            if result.semantic_candidates
            else RetrievalMethod.LEXICAL
        )
        try:
            with self._database.write() as connection:
                connection.execute(
                    "INSERT INTO knowledge_retrieval_metric(at, query_type, format, message_type, "
                    "release, method, lexical_candidates, semantic_candidates, hits, latency_ms, "
                    "context_chars) VALUES (datetime('now'),?,?,?,?,?,?,?,?,?,?)",
                    (
                        result.query_type.value,
                        result.filter.format.value if result.filter.format else None,
                        result.filter.message_version or result.filter.message_type,
                        result.filter.release,
                        method.value,
                        result.lexical_candidates,
                        result.semantic_candidates,
                        len(result.hits),
                        result.latency_ms,
                        result.context_chars,
                    ),
                )
        except sqlite3.Error:
            # Telemetry must never fail a retrieval.
            return


def _fuse(
    lexical: list[tuple[SegmentRecord, float]],
    semantic: list[tuple[SegmentRecord, float]],
) -> list[RetrievalHit]:
    scores: dict[str, float] = {}
    segments: dict[str, SegmentRecord] = {}
    lexical_rank: dict[str, int] = {}
    semantic_rank: dict[str, int] = {}
    for rank, (segment, _score) in enumerate(lexical, start=1):
        segments[segment.segment_id] = segment
        lexical_rank[segment.segment_id] = rank
        scores[segment.segment_id] = scores.get(segment.segment_id, 0.0) + 1.0 / (RRF_K + rank)
    for rank, (segment, _score) in enumerate(semantic, start=1):
        segments[segment.segment_id] = segment
        semantic_rank[segment.segment_id] = rank
        scores[segment.segment_id] = scores.get(segment.segment_id, 0.0) + 1.0 / (RRF_K + rank)
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    hits: list[RetrievalHit] = []
    for segment_id, score in ordered:
        in_lex = segment_id in lexical_rank
        in_sem = segment_id in semantic_rank
        method = (
            RetrievalMethod.HYBRID
            if in_lex and in_sem
            else RetrievalMethod.SEMANTIC
            if in_sem
            else RetrievalMethod.LEXICAL
        )
        hits.append(
            RetrievalHit(
                segment=segments[segment_id],
                score=score,
                method=method,
                lexical_rank=lexical_rank.get(segment_id),
                semantic_rank=semantic_rank.get(segment_id),
            )
        )
    return hits


def _diversify(hits: list[RetrievalHit], max_per_section: int) -> list[RetrievalHit]:
    """Keep the top results, but no more than N per section before the remainder follows."""
    per_section: dict[str, int] = {}
    first: list[RetrievalHit] = []
    rest: list[RetrievalHit] = []
    for hit in hits:
        key = hit.segment.section.value
        if per_section.get(key, 0) < max_per_section:
            per_section[key] = per_section.get(key, 0) + 1
            first.append(hit)
        else:
            rest.append(hit)
    return [*first, *rest]


def _budget(hits: list[RetrievalHit], context_chars: int) -> tuple[list[RetrievalHit], int]:
    selected: list[RetrievalHit] = []
    used = 0
    for hit in hits:
        length = len(hit.segment.text)
        if selected and used + length > context_chars:
            continue
        selected.append(hit)
        used += length
    return selected, used
