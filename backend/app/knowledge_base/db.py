"""The knowledge database: one SQLite file, normal tables, FTS5 and float32 vectors.

Why SQLite and not a vector service: the metadata filter normally narrows a query to one
message and one release — a few hundred segments — so a BLOB column and a NumPy dot product
are faster than a network round trip, and a clean clone needs nothing installed. The
:class:`VectorStore` seam in ``vector_store.py`` is where pgvector would go later.

Concurrency: FastAPI runs sync endpoints in a threadpool and the sync command may run in
another process, so every call opens its own connection (WAL, busy timeout) and writers in
this process serialise on one lock. No connection is ever shared between threads — the
repository learnt that lesson from ``StaticPool`` (AGENTS.md §13.14).
"""

from __future__ import annotations

import json
import sqlite3
import struct
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.knowledge_base import KNOWLEDGE_SCHEMA_VERSION
from app.knowledge_base.models import (
    DocumentType,
    ExternalPolicy,
    IngestionState,
    Section,
    SegmentRecord,
    SourceClassification,
    SourceFormat,
    SourceRecord,
    SourceType,
    TableState,
)

_WRITE_LOCK = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_source (
    checksum TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    byte_size INTEGER NOT NULL,
    source_type TEXT NOT NULL,
    format TEXT NOT NULL,
    document_type TEXT NOT NULL,
    classification TEXT NOT NULL,
    message_type TEXT,
    message_version TEXT,
    release TEXT,
    publisher TEXT,
    title TEXT,
    page_count INTEGER,
    embedding_policy TEXT NOT NULL,
    llm_policy TEXT NOT NULL,
    ingestion_state TEXT NOT NULL,
    last_indexed_hash TEXT,
    parser_version TEXT NOT NULL,
    failure_code TEXT,
    failure_detail TEXT,
    segment_count INTEGER NOT NULL DEFAULT 0,
    embedded_count INTEGER NOT NULL DEFAULT 0,
    deleted INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_source_identity
    ON knowledge_source(format, message_type, release, deleted);
CREATE TABLE IF NOT EXISTS knowledge_source_path (
    relative_path TEXT PRIMARY KEY,
    checksum TEXT NOT NULL,
    seen_run TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_segment (
    segment_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    checksum TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    segment_hash TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    section TEXT NOT NULL,
    page INTEGER,
    heading TEXT,
    identifiers TEXT NOT NULL,
    table_state TEXT NOT NULL,
    chars INTEGER NOT NULL,
    text TEXT NOT NULL,
    format TEXT NOT NULL,
    message_type TEXT,
    message_version TEXT,
    release TEXT
);
CREATE INDEX IF NOT EXISTS ix_segment_source ON knowledge_segment(source_id);
CREATE INDEX IF NOT EXISTS ix_segment_identity
    ON knowledge_segment(format, message_type, release, section);
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
    segment_id UNINDEXED,
    message_type,
    release,
    section,
    heading,
    identifiers,
    body,
    tokenize = 'unicode61 remove_diacritics 2'
);
CREATE TABLE IF NOT EXISTS knowledge_embedding (
    segment_id TEXT NOT NULL,
    segment_hash TEXT NOT NULL,
    provider TEXT NOT NULL,
    deployment TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    schema_version TEXT NOT NULL,
    vector BLOB NOT NULL,
    norm REAL NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (segment_id, provider, deployment, dimensions, schema_version)
);
CREATE INDEX IF NOT EXISTS ix_embedding_hash ON knowledge_embedding(segment_hash);
CREATE TABLE IF NOT EXISTS knowledge_index_run (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    state TEXT NOT NULL,
    stats TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_structure (
    format TEXT NOT NULL,
    message_type TEXT NOT NULL,
    release TEXT NOT NULL,
    lane TEXT NOT NULL,
    pack_path TEXT,
    pack_checksum TEXT,
    structure_source TEXT NOT NULL,
    readiness TEXT NOT NULL,
    blockers TEXT NOT NULL,
    gates TEXT NOT NULL,
    compiler_version TEXT NOT NULL,
    source_ids TEXT NOT NULL,
    source_checksums TEXT NOT NULL,
    detail TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (format, message_type, release, lane)
);
CREATE TABLE IF NOT EXISTS knowledge_sample_cache (
    cache_key TEXT PRIMARY KEY,
    format TEXT NOT NULL,
    message_type TEXT NOT NULL,
    release TEXT NOT NULL,
    lane TEXT NOT NULL,
    sample_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    llm_calls INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    hits INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS knowledge_presentation_cache (
    cache_key TEXT PRIMARY KEY,
    format TEXT NOT NULL,
    message_type TEXT NOT NULL,
    release TEXT NOT NULL,
    field_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_artifact (
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    checksum TEXT NOT NULL,
    payload TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (kind, key)
);
CREATE TABLE IF NOT EXISTS knowledge_retrieval_metric (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    query_type TEXT NOT NULL,
    format TEXT,
    message_type TEXT,
    release TEXT,
    method TEXT NOT NULL,
    lexical_candidates INTEGER NOT NULL,
    semantic_candidates INTEGER NOT NULL,
    hits INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL,
    context_chars INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_ai_metric (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    operation TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    llm_calls INTEGER NOT NULL,
    prompt_tokens INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    cache_hit INTEGER NOT NULL,
    calls_avoided INTEGER NOT NULL,
    tokens_avoided INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL,
    outcome TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class KnowledgeDatabase:
    """All reads and writes against one knowledge SQLite file."""

    def __init__(self, path: Path) -> None:
        self.path = path

    # -- lifecycle ---------------------------------------------------------------------

    @property
    def exists(self) -> bool:
        return self.path.exists()

    def initialise(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # executescript commits on its own, so it runs outside the transaction wrapper —
        # still under the writer lock.
        with _WRITE_LOCK:
            connection = self._connect()
            try:
                connection.executescript(SCHEMA)
                connection.execute(
                    "INSERT OR IGNORE INTO knowledge_meta(key, value) VALUES ('schema_version', ?)",
                    (str(KNOWLEDGE_SCHEMA_VERSION),),
                )
            finally:
                connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self.path), timeout=30.0, isolation_level=None, check_same_thread=True
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def write(self) -> Iterator[sqlite3.Connection]:
        """One bounded transaction per unit of work, serialised within the process."""
        with _WRITE_LOCK:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
            finally:
                connection.close()

    # -- meta ------------------------------------------------------------------------

    def get_meta(self, key: str, connection: sqlite3.Connection | None = None) -> str | None:
        if connection is None:
            with self.read() as own:
                return self.get_meta(key, own)
        row = connection.execute(
            "SELECT value FROM knowledge_meta WHERE key = ?", (key,)
        ).fetchone()
        return str(row["value"]) if row else None

    def set_meta(self, connection: sqlite3.Connection, key: str, value: str) -> None:
        connection.execute(
            "INSERT INTO knowledge_meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    # -- sources -----------------------------------------------------------------------

    def upsert_source(self, connection: sqlite3.Connection, record: SourceRecord) -> None:
        connection.execute(
            """
            INSERT INTO knowledge_source(
                checksum, source_id, byte_size, source_type, format, document_type,
                classification, message_type, message_version, release, publisher, title,
                page_count, embedding_policy, llm_policy, ingestion_state, last_indexed_hash,
                parser_version, failure_code, failure_detail, segment_count, embedded_count,
                deleted, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(checksum) DO UPDATE SET
                source_id = excluded.source_id,
                byte_size = excluded.byte_size,
                source_type = excluded.source_type,
                format = excluded.format,
                document_type = excluded.document_type,
                classification = excluded.classification,
                message_type = excluded.message_type,
                message_version = excluded.message_version,
                release = excluded.release,
                publisher = excluded.publisher,
                title = excluded.title,
                page_count = excluded.page_count,
                embedding_policy = excluded.embedding_policy,
                llm_policy = excluded.llm_policy,
                ingestion_state = excluded.ingestion_state,
                last_indexed_hash = excluded.last_indexed_hash,
                parser_version = excluded.parser_version,
                failure_code = excluded.failure_code,
                failure_detail = excluded.failure_detail,
                segment_count = excluded.segment_count,
                embedded_count = excluded.embedded_count,
                deleted = excluded.deleted,
                updated_at = excluded.updated_at
            """,
            (
                record.checksum,
                record.source_id,
                record.byte_size,
                record.source_type.value,
                record.format.value,
                record.document_type.value,
                record.classification.value,
                record.message_type,
                record.message_version,
                record.release,
                record.publisher,
                record.title,
                record.page_count,
                record.embedding_policy.value,
                record.llm_policy.value,
                record.ingestion_state.value,
                record.last_indexed_hash,
                record.parser_version,
                record.failure_code,
                record.failure_detail,
                record.segment_count,
                record.embedded_count,
                1 if record.deleted else 0,
                _now(),
            ),
        )

    def record_path(
        self, connection: sqlite3.Connection, relative_path: str, checksum: str, run_id: str
    ) -> str | None:
        """Record that a path now holds these bytes.

        Returns the checksum the path held before when no other path still holds it — the
        previous version of a changed document, which the caller tombstones so its segments
        and embeddings do not linger beside the new ones.
        """
        previous = connection.execute(
            "SELECT checksum FROM knowledge_source_path WHERE relative_path = ?",
            (relative_path,),
        ).fetchone()
        connection.execute(
            "INSERT INTO knowledge_source_path(relative_path, checksum, seen_run) "
            "VALUES (?, ?, ?) ON CONFLICT(relative_path) DO UPDATE SET "
            "checksum = excluded.checksum, seen_run = excluded.seen_run",
            (relative_path, checksum, run_id),
        )
        if previous is None or previous["checksum"] == checksum:
            return None
        remaining = connection.execute(
            "SELECT COUNT(*) AS n FROM knowledge_source_path WHERE checksum = ?",
            (previous["checksum"],),
        ).fetchone()
        return None if remaining and remaining["n"] else str(previous["checksum"])

    def delete_segments_for_source_id(self, connection: sqlite3.Connection, source_id: str) -> None:
        """Segment ids are derived from the source id, so a re-parsed document must shed the
        segments of every earlier byte version before its new ones are written."""
        checksums = [
            str(row["checksum"])
            for row in connection.execute(
                "SELECT DISTINCT checksum FROM knowledge_segment WHERE source_id = ?",
                (source_id,),
            ).fetchall()
        ]
        for checksum in checksums:
            self.delete_segments(connection, checksum)

    def paths_not_seen(self, connection: sqlite3.Connection, run_id: str) -> list[str]:
        rows = connection.execute(
            "SELECT relative_path FROM knowledge_source_path WHERE seen_run <> ?", (run_id,)
        ).fetchall()
        return [str(row["relative_path"]) for row in rows]

    def forget_path(self, connection: sqlite3.Connection, relative_path: str) -> str | None:
        row = connection.execute(
            "SELECT checksum FROM knowledge_source_path WHERE relative_path = ?",
            (relative_path,),
        ).fetchone()
        if row is None:
            return None
        connection.execute(
            "DELETE FROM knowledge_source_path WHERE relative_path = ?", (relative_path,)
        )
        remaining = connection.execute(
            "SELECT COUNT(*) AS n FROM knowledge_source_path WHERE checksum = ?",
            (row["checksum"],),
        ).fetchone()
        return None if remaining and remaining["n"] else str(row["checksum"])

    def tombstone_source(self, connection: sqlite3.Connection, checksum: str) -> None:
        """A deleted source keeps its row (for the report) and loses its index content."""
        source = connection.execute(
            "SELECT source_id FROM knowledge_source WHERE checksum = ?", (checksum,)
        ).fetchone()
        if source is None:
            return
        self.delete_segments(connection, checksum)
        self.delete_artifacts_for_checksum(connection, checksum)
        connection.execute(
            "UPDATE knowledge_source SET deleted = 1, ingestion_state = ?, segment_count = 0, "
            "embedded_count = 0, updated_at = ? WHERE checksum = ?",
            (IngestionState.DELETED.value, _now(), checksum),
        )
        connection.execute(
            "DELETE FROM knowledge_structure WHERE source_checksums LIKE ?",
            (f"%{checksum}%",),
        )

    def source_by_checksum(
        self, checksum: str, connection: sqlite3.Connection | None = None
    ) -> SourceRecord | None:
        if connection is None:
            with self.read() as own:
                return self.source_by_checksum(checksum, own)
        row = connection.execute(
            "SELECT * FROM knowledge_source WHERE checksum = ?", (checksum,)
        ).fetchone()
        return self._source_from_row(connection, row) if row else None

    def sources(self, *, include_deleted: bool = False) -> list[SourceRecord]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT * FROM knowledge_source"
                + ("" if include_deleted else " WHERE deleted = 0")
                + " ORDER BY format, message_type, release, source_id"
            ).fetchall()
            return [self._source_from_row(connection, row) for row in rows]

    def _source_from_row(self, connection: sqlite3.Connection, row: sqlite3.Row) -> SourceRecord:
        paths = [
            str(item["relative_path"])
            for item in connection.execute(
                "SELECT relative_path FROM knowledge_source_path WHERE checksum = ? "
                "ORDER BY relative_path",
                (row["checksum"],),
            ).fetchall()
        ]
        return SourceRecord(
            checksum=str(row["checksum"]),
            source_id=str(row["source_id"]),
            relative_paths=paths,
            byte_size=int(row["byte_size"]),
            source_type=SourceType(row["source_type"]),
            format=SourceFormat(row["format"]),
            document_type=DocumentType(row["document_type"]),
            classification=SourceClassification(row["classification"]),
            message_type=row["message_type"],
            message_version=row["message_version"],
            release=row["release"],
            publisher=row["publisher"],
            title=row["title"],
            page_count=row["page_count"],
            embedding_policy=ExternalPolicy(row["embedding_policy"]),
            llm_policy=ExternalPolicy(row["llm_policy"]),
            ingestion_state=IngestionState(row["ingestion_state"]),
            last_indexed_hash=row["last_indexed_hash"],
            parser_version=str(row["parser_version"]),
            failure_code=row["failure_code"],
            failure_detail=row["failure_detail"],
            segment_count=int(row["segment_count"]),
            embedded_count=int(row["embedded_count"]),
            deleted=bool(row["deleted"]),
        )

    # -- segments and FTS -------------------------------------------------------------

    def delete_segments(self, connection: sqlite3.Connection, checksum: str) -> None:
        ids = [
            str(row["segment_id"])
            for row in connection.execute(
                "SELECT segment_id FROM knowledge_segment WHERE checksum = ?", (checksum,)
            ).fetchall()
        ]
        for segment_id in ids:
            connection.execute("DELETE FROM knowledge_fts WHERE segment_id = ?", (segment_id,))
            connection.execute(
                "DELETE FROM knowledge_embedding WHERE segment_id = ?", (segment_id,)
            )
        connection.execute("DELETE FROM knowledge_segment WHERE checksum = ?", (checksum,))

    def insert_segments(
        self, connection: sqlite3.Connection, checksum: str, segments: Sequence[SegmentRecord]
    ) -> None:
        for segment in segments:
            connection.execute(
                """
                INSERT INTO knowledge_segment(
                    segment_id, source_id, checksum, ordinal, segment_hash, text_hash,
                    section, page, heading, identifiers, table_state, chars, text, format,
                    message_type, message_version, release
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    segment.segment_id,
                    segment.source_id,
                    checksum,
                    segment.ordinal,
                    segment.segment_hash,
                    segment.text_hash,
                    segment.section.value,
                    segment.page,
                    segment.heading,
                    json.dumps(list(segment.identifiers)),
                    segment.table_state.value,
                    len(segment.text),
                    segment.text,
                    segment.format.value,
                    segment.message_type,
                    segment.message_version,
                    segment.release,
                ),
            )
            connection.execute(
                "INSERT INTO knowledge_fts(segment_id, message_type, release, section, heading, "
                "identifiers, body) VALUES (?,?,?,?,?,?,?)",
                (
                    segment.segment_id,
                    segment.message_type or "",
                    segment.release or "",
                    segment.section.value,
                    segment.heading or "",
                    " ".join(segment.identifiers),
                    segment.text,
                ),
            )

    def segment_hashes_for(self, connection: sqlite3.Connection, checksum: str) -> dict[str, str]:
        return {
            str(row["segment_id"]): str(row["segment_hash"])
            for row in connection.execute(
                "SELECT segment_id, segment_hash FROM knowledge_segment WHERE checksum = ?",
                (checksum,),
            ).fetchall()
        }

    def segments_for_source(self, source_id: str) -> list[SegmentRecord]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT * FROM knowledge_segment WHERE source_id = ? ORDER BY ordinal",
                (source_id,),
            ).fetchall()
            return [segment_from_row(row) for row in rows]

    def segment(self, segment_id: str) -> SegmentRecord | None:
        with self.read() as connection:
            row = connection.execute(
                "SELECT * FROM knowledge_segment WHERE segment_id = ?", (segment_id,)
            ).fetchone()
            return segment_from_row(row) if row else None

    # -- embeddings ---------------------------------------------------------------------

    def embedding_for_hash(
        self,
        connection: sqlite3.Connection,
        segment_hash: str,
        provider: str,
        deployment: str,
        dimensions: int,
        schema_version: str,
    ) -> bytes | None:
        row = connection.execute(
            "SELECT vector FROM knowledge_embedding WHERE segment_hash = ? AND provider = ? "
            "AND deployment = ? AND dimensions = ? AND schema_version = ? LIMIT 1",
            (segment_hash, provider, deployment, dimensions, schema_version),
        ).fetchone()
        return bytes(row["vector"]) if row else None

    def upsert_embedding(
        self,
        connection: sqlite3.Connection,
        *,
        segment_id: str,
        segment_hash: str,
        provider: str,
        deployment: str,
        dimensions: int,
        schema_version: str,
        vector: bytes,
        norm: float,
    ) -> None:
        connection.execute(
            """
            INSERT INTO knowledge_embedding(segment_id, segment_hash, provider, deployment,
                dimensions, schema_version, vector, norm, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(segment_id, provider, deployment, dimensions, schema_version)
            DO UPDATE SET segment_hash = excluded.segment_hash, vector = excluded.vector,
                norm = excluded.norm, created_at = excluded.created_at
            """,
            (
                segment_id,
                segment_hash,
                provider,
                deployment,
                dimensions,
                schema_version,
                vector,
                norm,
                _now(),
            ),
        )

    # -- derived artifacts (MRG structures, reconciliation) ---------------------------------

    def put_artifact(
        self, connection: sqlite3.Connection, kind: str, key: str, checksum: str, payload: object
    ) -> None:
        connection.execute(
            "INSERT INTO knowledge_artifact(kind, key, checksum, payload, updated_at) "
            "VALUES (?,?,?,?,?) ON CONFLICT(kind, key) DO UPDATE SET checksum = excluded.checksum, "
            "payload = excluded.payload, updated_at = excluded.updated_at",
            (kind, key, checksum, json.dumps(payload, sort_keys=True), _now()),
        )

    def get_artifact(self, kind: str, key: str) -> tuple[str, Any] | None:
        with self.read() as connection:
            row = connection.execute(
                "SELECT checksum, payload FROM knowledge_artifact WHERE kind = ? AND key = ?",
                (kind, key),
            ).fetchone()
            return (str(row["checksum"]), json.loads(row["payload"])) if row else None

    def artifacts(self, kind: str) -> list[tuple[str, str, Any]]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT key, checksum, payload FROM knowledge_artifact WHERE kind = ? ORDER BY key",
                (kind,),
            ).fetchall()
            return [(str(r["key"]), str(r["checksum"]), json.loads(r["payload"])) for r in rows]

    def delete_artifacts_for_checksum(self, connection: sqlite3.Connection, checksum: str) -> None:
        connection.execute("DELETE FROM knowledge_artifact WHERE checksum = ?", (checksum,))

    # -- runs --------------------------------------------------------------------------

    def start_run(self, run_id: str) -> None:
        with self.write() as connection:
            connection.execute(
                "INSERT INTO knowledge_index_run(run_id, started_at, state, stats) "
                "VALUES (?, ?, 'RUNNING', '{}')",
                (run_id, _now()),
            )

    def finish_run(self, run_id: str, state: str, stats: dict[str, object]) -> None:
        with self.write() as connection:
            connection.execute(
                "UPDATE knowledge_index_run SET finished_at = ?, state = ?, stats = ? "
                "WHERE run_id = ?",
                (_now(), state, json.dumps(stats, sort_keys=True), run_id),
            )

    def last_run(self) -> dict[str, Any] | None:
        with self.read() as connection:
            row = connection.execute(
                "SELECT * FROM knowledge_index_run ORDER BY started_at DESC, rowid DESC LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            return {
                "runId": row["run_id"],
                "startedAt": row["started_at"],
                "finishedAt": row["finished_at"],
                "state": row["state"],
                "stats": json.loads(row["stats"]),
            }

    # -- counts for status ------------------------------------------------------------

    def counts(self) -> dict[str, int]:
        with self.read() as connection:

            def one(sql: str) -> int:
                row = connection.execute(sql).fetchone()
                return int(row[0]) if row else 0

            return {
                "sources": one("SELECT COUNT(*) FROM knowledge_source WHERE deleted = 0"),
                "sourcesDeleted": one("SELECT COUNT(*) FROM knowledge_source WHERE deleted = 1"),
                "segments": one("SELECT COUNT(*) FROM knowledge_segment"),
                "embeddings": one("SELECT COUNT(*) FROM knowledge_embedding"),
                "messages": one(
                    "SELECT COUNT(DISTINCT format || ':' || COALESCE(message_version, "
                    "message_type) || ':' || COALESCE(release, '')) FROM knowledge_source "
                    "WHERE deleted = 0 AND message_type IS NOT NULL"
                ),
                "structures": one("SELECT COUNT(*) FROM knowledge_structure"),
                "samplesCached": one("SELECT COUNT(*) FROM knowledge_sample_cache"),
            }


def segment_from_row(row: sqlite3.Row) -> SegmentRecord:
    return SegmentRecord(
        segment_id=str(row["segment_id"]),
        source_id=str(row["source_id"]),
        ordinal=int(row["ordinal"]),
        segment_hash=str(row["segment_hash"]),
        text_hash=str(row["text_hash"]),
        section=Section(row["section"]),
        page=row["page"],
        heading=row["heading"],
        identifiers=tuple(json.loads(row["identifiers"])),
        table_state=TableState(row["table_state"]),
        text=str(row["text"]),
        message_type=row["message_type"],
        message_version=row["message_version"],
        release=row["release"],
        format=SourceFormat(row["format"]),
    )


def pack_vector(values: Sequence[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


def unpack_vector(blob: bytes) -> tuple[float, ...]:
    count = len(blob) // 4
    return struct.unpack(f"<{count}f", blob)
