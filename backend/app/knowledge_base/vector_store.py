"""Vector search over the metadata-filtered subset, in SQLite + NumPy.

The interface is the seam for a pgvector implementation later; the SQLite implementation
is deliberately small because the metadata filter has already reduced the search to one
message and one release. Vectors of a different deployment or dimension are never mixed
into one similarity computation — the query names both, and the row filter enforces it.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.knowledge_base.db import KnowledgeDatabase, pack_vector
from app.knowledge_base.models import RetrievalFilter


@dataclass(frozen=True)
class VectorHit:
    segment_id: str
    score: float


class VectorStore(Protocol):
    def search(
        self,
        query_vector: Sequence[float],
        *,
        provider: str,
        deployment: str,
        dimensions: int,
        schema_version: str,
        filter: RetrievalFilter,
        k: int,
    ) -> list[VectorHit]: ...

    def count(
        self,
        *,
        provider: str,
        deployment: str,
        dimensions: int,
        schema_version: str,
        filter: RetrievalFilter,
    ) -> int: ...


def filter_sql(filter: RetrievalFilter, alias: str = "s") -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if filter.format is not None:
        clauses.append(f"{alias}.format = ?")
        params.append(filter.format.value)
    if filter.message_version:
        clauses.append(f"{alias}.message_version = ?")
        params.append(filter.message_version)
    elif filter.message_type:
        clauses.append(f"{alias}.message_type = ?")
        params.append(
            filter.message_type.upper()
            if filter.format and filter.format.value == "MT"
            else filter.message_type
        )
    if filter.releases:
        clauses.append(f"{alias}.release IN (" + ",".join("?" for _ in filter.releases) + ")")
        params.extend(filter.releases)
    elif filter.release:
        clauses.append(f"{alias}.release = ?")
        params.append(filter.release)
    if filter.sections:
        clauses.append(f"{alias}.section IN (" + ",".join("?" for _ in filter.sections) + ")")
        params.extend(section.value for section in filter.sections)
    return (" AND ".join(clauses) if clauses else "1 = 1"), params


class SqliteNumpyVectorStore:
    def __init__(self, database: KnowledgeDatabase) -> None:
        self._database = database

    def count(
        self,
        *,
        provider: str,
        deployment: str,
        dimensions: int,
        schema_version: str,
        filter: RetrievalFilter,
    ) -> int:
        where, params = filter_sql(filter)
        with self._database.read() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM knowledge_embedding e JOIN knowledge_segment s "
                "ON s.segment_id = e.segment_id WHERE e.provider = ? AND e.deployment = ? "
                f"AND e.dimensions = ? AND e.schema_version = ? AND {where}",
                [provider, deployment, dimensions, schema_version, *params],
            ).fetchone()
            return int(row[0]) if row else 0

    def search(
        self,
        query_vector: Sequence[float],
        *,
        provider: str,
        deployment: str,
        dimensions: int,
        schema_version: str,
        filter: RetrievalFilter,
        k: int,
    ) -> list[VectorHit]:
        import numpy as np

        if len(query_vector) != dimensions:
            raise ValueError("query vector dimension does not match the stored embeddings")
        where, params = filter_sql(filter)
        with self._database.read() as connection:
            rows = connection.execute(
                "SELECT e.segment_id, e.vector, e.norm FROM knowledge_embedding e "
                "JOIN knowledge_segment s ON s.segment_id = e.segment_id "
                "WHERE e.provider = ? AND e.deployment = ? AND e.dimensions = ? "
                f"AND e.schema_version = ? AND {where} ORDER BY e.segment_id",
                [provider, deployment, dimensions, schema_version, *params],
            ).fetchall()
        if not rows:
            return []
        matrix = np.frombuffer(b"".join(bytes(row["vector"]) for row in rows), dtype="<f4").reshape(
            len(rows), -1
        )
        if matrix.shape[1] != dimensions:
            raise ValueError("stored vector width does not match the declared dimension")
        query = np.asarray(query_vector, dtype=np.float32)
        query_norm = float(np.linalg.norm(query)) or 1.0
        norms = np.asarray([float(row["norm"]) or 1.0 for row in rows], dtype=np.float32)
        scores = (matrix @ query) / (norms * query_norm)
        order = sorted(
            range(len(rows)),
            key=lambda index: (-float(scores[index]), str(rows[index]["segment_id"])),
        )
        return [
            VectorHit(segment_id=str(rows[index]["segment_id"]), score=float(scores[index]))
            for index in order[:k]
        ]


def store_vector(
    connection: sqlite3.Connection,
    database: KnowledgeDatabase,
    *,
    segment_id: str,
    segment_hash: str,
    provider: str,
    deployment: str,
    schema_version: str,
    vector: Sequence[float],
) -> None:
    import math

    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    database.upsert_embedding(
        connection,
        segment_id=segment_id,
        segment_hash=segment_hash,
        provider=provider,
        deployment=deployment,
        dimensions=len(vector),
        schema_version=schema_version,
        vector=pack_vector(vector),
        norm=norm,
    )
