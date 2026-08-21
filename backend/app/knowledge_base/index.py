"""`make knowledge-sync`: discover → hash → identify → segment → index → embed → compile.

Incremental and interrupt-safe: every source is one transaction, an unchanged checksum is
skipped before its bytes are read, an unchanged segment hash never reaches the embedding
provider again, and a rerun after an interruption simply continues with what has not been
indexed. One broken document is recorded and the run goes on.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.knowledge_base import CHUNKER_VERSION, EMBEDDING_SCHEMA_VERSION
from app.knowledge_base.chunking import segment_source
from app.knowledge_base.db import KnowledgeDatabase, unpack_vector
from app.knowledge_base.discovery import DiscoveredFile, Discovery, discover, sha256_of_file
from app.knowledge_base.embeddings import EmbeddingError, EmbeddingProvider
from app.knowledge_base.identify import (
    PARSER_VERSION,
    ParsedSource,
    SourceUnreadable,
    parse_and_identify,
)
from app.knowledge_base.models import (
    DocumentType,
    ExternalPolicy,
    IngestionState,
    SegmentRecord,
    SourceClassification,
    SourceFormat,
    SourceIdentity,
    SourceRecord,
    SourceType,
    SyncProgress,
)
from app.knowledge_base.paths import knowledge_roots, resolve_project_path
from app.knowledge_base.policy import policy_for
from app.knowledge_base.structures.mrg import MrgStructureArtifact
from app.knowledge_base.vector_store import store_vector

Progress = Callable[[str, SyncProgress], None]


@dataclass
class SyncOptions:
    reindex: bool = False
    embed: bool = True
    compile_structures: bool = True
    write_manifest: bool = True
    #: Compile the committed Prowide evidence as well as discovered sources. Tests that only
    #: care about their own fixtures switch it off; the operator's sync keeps it on.
    include_prowide: bool = True
    #: Restrict Prowide compilation to these message types (tests); None means all.
    prowide_filter: tuple[str, ...] | None = None


class KnowledgeIndexer:
    def __init__(
        self,
        settings: Settings,
        database: KnowledgeDatabase,
        embeddings: EmbeddingProvider,
        *,
        roots: list[Path] | None = None,
    ) -> None:
        self._settings = settings
        self._database = database
        self._embeddings = embeddings
        self._roots = roots if roots is not None else knowledge_roots(settings)
        self._cache_dir = resolve_project_path(settings.knowledge_source_cache_dir)
        self._pack_dir = resolve_project_path(settings.knowledge_pack_dir)

    # -- entry point ------------------------------------------------------------------------

    def sync(
        self, options: SyncOptions | None = None, *, progress: Progress | None = None
    ) -> SyncProgress:
        opts = options or SyncOptions()
        report = SyncProgress()
        started = time.monotonic()
        self._database.initialise()
        run_id = uuid.uuid4().hex
        self._database.start_run(run_id)
        state = "COMPLETED"
        try:
            discovery = discover(
                self._roots,
                cache_dir=self._cache_dir,
                max_source_bytes=self._settings.knowledge_max_source_bytes,
                max_zip_member_bytes=self._settings.knowledge_max_zip_member_bytes,
                max_zip_total_bytes=self._settings.knowledge_max_zip_total_bytes,
            )
            report.documents_discovered = len(discovery.files)
            report.documents_unsupported = len(discovery.skipped)
            for skipped in discovery.skipped:
                report.failures.append(
                    {
                        "path": skipped.relative_path,
                        "code": skipped.reason,
                        "detail": skipped.detail,
                    }
                )
            for item in discovery.files:
                self._sync_one(item, run_id, opts, report)
                if progress:
                    progress(item.relative_path, report)
            self._tombstone_missing(run_id, report)
            if opts.compile_structures:
                from app.knowledge_base.structures import compile_all

                compile_all(
                    self._settings,
                    self._database,
                    self._pack_dir,
                    report,
                    include_prowide=opts.include_prowide,
                    prowide_filter=opts.prowide_filter,
                )
            self._write_corpus_version()
            if opts.write_manifest:
                self._write_manifest(discovery, report)
        except BaseException:
            state = "INTERRUPTED"
            raise
        finally:
            report.elapsed_ms = round((time.monotonic() - started) * 1000)
            self._database.finish_run(run_id, state, report.as_dict())
        return report

    # -- one source ------------------------------------------------------------------------

    def _sync_one(
        self, item: DiscoveredFile, run_id: str, opts: SyncOptions, report: SyncProgress
    ) -> None:
        try:
            checksum = sha256_of_file(item.absolute_path)
        except OSError as error:
            report.documents_failed += 1
            report.failures.append(
                {
                    "path": item.relative_path,
                    "code": "KNOWLEDGE_SOURCE_UNREADABLE",
                    "detail": type(error).__name__,
                }
            )
            return
        existing = self._database.source_by_checksum(checksum)
        unchanged = (
            existing is not None
            and not existing.deleted
            and existing.last_indexed_hash == checksum
            and existing.parser_version == PARSER_VERSION
            and existing.ingestion_state not in {IngestionState.FAILED, IngestionState.UNSUPPORTED}
            and not opts.reindex
        )
        if unchanged and existing is not None:
            report.documents_unchanged += 1
            with self._database.write() as connection:
                self._database.record_path(connection, item.relative_path, checksum, run_id)
            if opts.embed:
                self._embed_source(existing, checksum, report, reuse_only=False)
            return
        try:
            cached_text: str | None = None
            if item.suffix == ".pdf":
                from app.knowledge_base.structures.mrg import cached_text_path

                text_path = cached_text_path(self._cache_dir, checksum)
                if text_path.exists():
                    cached_text = text_path.read_text(encoding="utf-8")
            parsed = parse_and_identify(
                item, item.absolute_path.read_bytes(), cached_text=cached_text
            )
        except SourceUnreadable as error:
            report.documents_failed += 1
            report.failures.append(
                {"path": item.relative_path, "code": error.code, "detail": error.detail}
            )
            with self._database.write() as connection:
                self._database.delete_segments(connection, checksum)
                self._database.upsert_source(
                    connection,
                    _failed_record(item, checksum, error.code, error.detail),
                )
                self._database.record_path(connection, item.relative_path, checksum, run_id)
            return
        except Exception as error:  # noqa: BLE001 - one broken file must not stop the corpus
            report.documents_failed += 1
            report.failures.append(
                {
                    "path": item.relative_path,
                    "code": "KNOWLEDGE_SOURCE_UNREADABLE",
                    "detail": type(error).__name__,
                }
            )
            with self._database.write() as connection:
                self._database.upsert_source(
                    connection,
                    _failed_record(
                        item, checksum, "KNOWLEDGE_SOURCE_UNREADABLE", type(error).__name__
                    ),
                )
                self._database.record_path(connection, item.relative_path, checksum, run_id)
            return

        report.documents_parsed += 1
        if parsed.identity.source_type is SourceType.ISO20022_XSD:
            # The compiler reads a file path; keeping a checksum-named copy in the ignored
            # cache means a rebuild never touches the operator's folder again.
            from app.knowledge_base.structures.mx_pack import cached_xsd_path

            cached = cached_xsd_path(self._cache_dir, checksum)
            if not cached.exists():
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(item.absolute_path.read_bytes())
        if item.suffix == ".pdf" and cached_text is None:
            # The page-marked text is what the offline semantic-rule reader consumes and
            # what a re-index re-reads; kept once per checksum in the ignored cache so a
            # PDF is parsed a single time.
            from app.knowledge_base.structures.mrg import cached_text_path

            text_path = cached_text_path(self._cache_dir, checksum)
            text_path.parent.mkdir(parents=True, exist_ok=True)
            text_path.write_text(parsed.text, encoding="utf-8")
        artifact, partial_pages, artifact_problem = self._mrg_artifact(parsed)
        segments = segment_source(parsed.identity, parsed.text, partial_table_pages=partial_pages)
        policy = policy_for(parsed.classification, self._settings)
        record = SourceRecord(
            checksum=checksum,
            source_id=parsed.identity.source_id,
            relative_paths=[item.relative_path],
            byte_size=item.byte_size,
            source_type=parsed.identity.source_type,
            format=parsed.identity.format,
            document_type=parsed.identity.document_type,
            classification=parsed.classification,
            message_type=parsed.identity.message_type,
            message_version=parsed.identity.message_version,
            release=parsed.identity.release,
            publisher=parsed.identity.publisher,
            title=parsed.identity.title,
            page_count=parsed.page_count,
            embedding_policy=policy.embedding,
            llm_policy=policy.llm,
            ingestion_state=IngestionState.INDEXED,
            last_indexed_hash=checksum,
            parser_version=PARSER_VERSION,
            failure_code=(
                "KNOWLEDGE_IDENTITY_AMBIGUOUS"
                if "KNOWLEDGE_IDENTITY_AMBIGUOUS" in parsed.identity.problems
                else None
            ),
            failure_detail=", ".join(parsed.identity.problems) or None,
            segment_count=len(segments),
        )
        with self._database.write() as connection:
            previous = self._database.segment_hashes_for(connection, checksum)
            reused = sum(
                1
                for segment in segments
                if previous.get(segment.segment_id) == segment.segment_hash
            )
            report.segments_reused += reused
            report.segments_created += len(segments) - reused
            self._database.delete_segments(connection, checksum)
            self._database.delete_segments_for_source_id(connection, record.source_id)
            self._database.insert_segments(connection, checksum, segments)
            if artifact_problem and not record.failure_detail:
                record.failure_detail = artifact_problem
            self._database.upsert_source(connection, record)
            orphaned = self._database.record_path(connection, item.relative_path, checksum, run_id)
            if orphaned is not None and orphaned != checksum:
                # The previous bytes of this document: no path holds them any more.
                self._database.tombstone_source(connection, orphaned)
            if artifact is not None:
                from app.knowledge_base.structures.mrg import MRG_STRUCTURE_KIND

                self._database.put_artifact(
                    connection,
                    MRG_STRUCTURE_KIND,
                    f"{artifact.message_type}:{artifact.release}",
                    checksum,
                    artifact.as_payload(),
                )
        if opts.embed:
            self._embed_source(record, checksum, report, reuse_only=False)

    def rebuild_structures(self, *, progress: Progress | None = None) -> SyncProgress:
        """Re-read every guide's structural artifact from the cached page text and recompile
        every Structure Pack — segments and embeddings untouched.

        This is the development loop for the structure compiler and the guide reader: a
        change to either is applied to the whole corpus in seconds, without re-parsing a
        PDF or sending a segment anywhere.
        """
        from app.knowledge_base.structures import compile_all
        from app.knowledge_base.structures.mrg import (
            MRG_STRUCTURE_KIND,
            cached_text_path,
        )

        report = SyncProgress()
        started = time.monotonic()
        self._database.initialise()
        run_id = uuid.uuid4().hex
        self._database.start_run(run_id)
        state = "COMPLETED"
        try:
            for record in self._database.sources():
                if (
                    record.deleted
                    or record.source_type is not SourceType.MT_MESSAGE_REFERENCE_GUIDE
                ):
                    continue
                text_path = cached_text_path(self._cache_dir, record.checksum)
                if not text_path.exists():
                    report.failures.append(
                        {
                            "path": record.source_id,
                            "code": "KNOWLEDGE_TEXT_CACHE_MISSING",
                            "detail": "run `make knowledge-sync` to parse the source again",
                        }
                    )
                    continue
                parsed = ParsedSource(
                    text_path.read_text(encoding="utf-8"),
                    record.page_count,
                    SourceIdentity(
                        source_id=record.source_id,
                        source_type=record.source_type,
                        format=record.format,
                        document_type=record.document_type,
                        message_type=record.message_type,
                        release=record.release,
                    ),
                    record.classification,
                )
                artifact, _pages, problem = self._mrg_artifact(parsed)
                report.documents_parsed += 1
                if artifact is None:
                    report.failures.append(
                        {
                            "path": record.source_id,
                            "code": "MRG_STRUCTURE_UNREADABLE",
                            "detail": problem or "",
                        }
                    )
                    continue
                with self._database.write() as connection:
                    self._database.put_artifact(
                        connection,
                        MRG_STRUCTURE_KIND,
                        f"{artifact.message_type}:{artifact.release}",
                        record.checksum,
                        artifact.as_payload(),
                    )
                if progress:
                    progress(record.source_id, report)
            compile_all(self._settings, self._database, self._pack_dir, report)
            self._write_corpus_version()
        except BaseException:
            state = "INTERRUPTED"
            raise
        finally:
            report.elapsed_ms = round((time.monotonic() - started) * 1000)
            self._database.finish_run(run_id, state, report.as_dict())
        return report

    def _mrg_artifact(
        self, parsed: ParsedSource
    ) -> tuple[MrgStructureArtifact | None, frozenset[int], str | None]:
        """The guide's structure, read once here and kept as an artifact; never at runtime."""
        if parsed.identity.source_type is not SourceType.MT_MESSAGE_REFERENCE_GUIDE:
            return None, frozenset(), None
        from app.knowledge_base.structures.mrg import read_structure, table_problem_pages

        try:
            artifact = read_structure(parsed)
        except Exception as error:  # noqa: BLE001 - an unreadable table is a fact to record
            return None, frozenset(), f"STRUCTURE_READ_FAILED: {type(error).__name__}"
        return artifact, table_problem_pages(parsed, artifact), None

    # -- embeddings ------------------------------------------------------------------------

    def _embed_source(
        self, record: SourceRecord, checksum: str, report: SyncProgress, *, reuse_only: bool
    ) -> None:
        segments = self._database.segments_for_source(record.source_id)
        if not segments:
            return
        if record.embedding_policy is ExternalPolicy.BLOCKED:
            report.embedding_blocked_segments += len(segments)
            if record.ingestion_state is not IngestionState.EMBEDDING_BLOCKED:
                record.ingestion_state = IngestionState.EMBEDDING_BLOCKED
                with self._database.write() as connection:
                    self._database.upsert_source(connection, record)
            return
        if not self._embeddings.available:
            return
        provider = self._embeddings.name
        deployment = self._embeddings.deployment
        dimensions = self._settings.embedding_dimensions
        pending: list[SegmentRecord] = []
        with self._database.write() as connection:
            for segment in segments:
                if dimensions is not None:
                    cached = self._database.embedding_for_hash(
                        connection,
                        segment.segment_hash,
                        provider,
                        deployment,
                        dimensions,
                        EMBEDDING_SCHEMA_VERSION,
                    )
                else:
                    cached = self._any_dimension_cached(
                        connection, segment.segment_hash, provider, deployment
                    )
                already = connection.execute(
                    "SELECT 1 FROM knowledge_embedding WHERE segment_id = ? AND segment_hash = ? "
                    "AND provider = ? AND deployment = ? AND schema_version = ?",
                    (
                        segment.segment_id,
                        segment.segment_hash,
                        provider,
                        deployment,
                        EMBEDDING_SCHEMA_VERSION,
                    ),
                ).fetchone()
                if already:
                    report.embedding_cache_hits += 1
                    continue
                if cached is not None:
                    report.embedding_cache_hits += 1
                    report.embedding_requests_avoided += 1
                    store_vector(
                        connection,
                        self._database,
                        segment_id=segment.segment_id,
                        segment_hash=segment.segment_hash,
                        provider=provider,
                        deployment=deployment,
                        schema_version=EMBEDDING_SCHEMA_VERSION,
                        vector=unpack_vector(cached),
                    )
                    continue
                pending.append(segment)
        if reuse_only or not pending:
            self._finish_embedding(record, len(segments))
            return
        try:
            result = self._embeddings.embed([segment.text for segment in pending])
        except EmbeddingError as error:
            report.failures.append(
                {"path": record.source_id, "code": error.code, "detail": error.detail}
            )
            return
        report.embedding_requests += result.requests
        report.segments_embedded += len(pending)
        report.embedding_latency_ms += result.latency_ms
        if result.usage.prompt_tokens is not None:
            report.embedding_tokens = (report.embedding_tokens or 0) + result.usage.prompt_tokens
        with self._database.write() as connection:
            for segment, vector in zip(pending, result.vectors, strict=True):
                store_vector(
                    connection,
                    self._database,
                    segment_id=segment.segment_id,
                    segment_hash=segment.segment_hash,
                    provider=provider,
                    deployment=deployment,
                    schema_version=EMBEDDING_SCHEMA_VERSION,
                    vector=vector,
                )
        self._finish_embedding(record, len(segments))

    def _any_dimension_cached(
        self, connection: object, segment_hash: str, provider: str, deployment: str
    ) -> bytes | None:
        import sqlite3

        assert isinstance(connection, sqlite3.Connection)
        row = connection.execute(
            "SELECT vector FROM knowledge_embedding WHERE segment_hash = ? AND provider = ? "
            "AND deployment = ? AND schema_version = ? LIMIT 1",
            (segment_hash, provider, deployment, EMBEDDING_SCHEMA_VERSION),
        ).fetchone()
        return bytes(row["vector"]) if row else None

    def _finish_embedding(self, record: SourceRecord, total: int) -> None:
        with self._database.write() as connection:
            row = connection.execute(
                "SELECT COUNT(DISTINCT e.segment_id) FROM knowledge_embedding e "
                "JOIN knowledge_segment s ON s.segment_id = e.segment_id WHERE s.source_id = ? "
                "AND e.provider = ? AND e.deployment = ?",
                (record.source_id, self._embeddings.name, self._embeddings.deployment),
            ).fetchone()
            embedded = int(row[0]) if row else 0
            record.embedded_count = embedded
            record.ingestion_state = (
                IngestionState.EMBEDDED if embedded >= total else IngestionState.INDEXED
            )
            self._database.upsert_source(connection, record)

    # -- deletions -------------------------------------------------------------------------

    def _tombstone_missing(self, run_id: str, report: SyncProgress) -> None:
        with self._database.write() as connection:
            for relative_path in self._database.paths_not_seen(connection, run_id):
                orphaned = self._database.forget_path(connection, relative_path)
                if orphaned is not None:
                    self._database.tombstone_source(connection, orphaned)
                    report.documents_deleted += 1

    # -- corpus identity ----------------------------------------------------------------------

    def _write_corpus_version(self) -> None:
        with self._database.write() as connection:
            rows = connection.execute(
                "SELECT source_id, checksum, message_type, message_version, release, format "
                "FROM knowledge_source WHERE deleted = 0 ORDER BY source_id, checksum"
            ).fetchall()
            digest = hashlib.sha256(CHUNKER_VERSION.encode())
            for row in rows:
                digest.update(f"{row['source_id']}|{row['checksum']}|".encode())
            self._database.set_meta(connection, "corpus_version", digest.hexdigest())
            self._database.set_meta(connection, "chunker_version", CHUNKER_VERSION)

    # -- manifest ---------------------------------------------------------------------------

    def _write_manifest(self, discovery: Discovery, report: SyncProgress) -> None:
        manifest_path = self._database.path.parent / "source-manifest.json"
        sources = [
            {
                "sourceId": source.source_id,
                "checksum": f"sha256:{source.checksum}",
                "relativePaths": source.relative_paths,
                "sourceType": source.source_type.value,
                "format": source.format.value,
                "messageType": source.message_type,
                "messageVersion": source.message_version,
                "release": source.release,
                "classification": source.classification.value,
                "embeddingPolicy": source.embedding_policy.value,
                "llmPolicy": source.llm_policy.value,
                "state": source.ingestion_state.value,
                "pageCount": source.page_count,
                "segments": source.segment_count,
                "embedded": source.embedded_count,
                "failureCode": source.failure_code,
                "failureDetail": source.failure_detail,
                "deleted": source.deleted,
            }
            for source in self._database.sources(include_deleted=True)
        ]
        payload = {
            "generatedBy": "make knowledge-sync",
            "roots": [root.name for root in self._roots],
            "rootsMissing": discovery.roots_missing,
            "skipped": [
                {"path": item.relative_path, "reason": item.reason, "detail": item.detail}
                for item in discovery.skipped
            ],
            "sources": sources,
            "run": report.as_dict(),
            "corpusVersion": self._database.get_meta("corpus_version"),
        }
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def _failed_record(item: DiscoveredFile, checksum: str, code: str, detail: str) -> SourceRecord:
    state = (
        IngestionState.UNSUPPORTED
        if code == "KNOWLEDGE_SOURCE_UNSUPPORTED"
        else IngestionState.FAILED
    )
    return SourceRecord(
        checksum=checksum,
        source_id=f"UNREADABLE-{checksum[:12]}",
        relative_paths=[item.relative_path],
        byte_size=item.byte_size,
        source_type=SourceType.UNKNOWN,
        format=SourceFormat.UNKNOWN,
        document_type=DocumentType.UNKNOWN,
        classification=SourceClassification.LICENSED_UNKNOWN,
        message_type=None,
        message_version=None,
        release=None,
        publisher=None,
        title=None,
        page_count=None,
        embedding_policy=ExternalPolicy.BLOCKED,
        llm_policy=ExternalPolicy.BLOCKED,
        ingestion_state=state,
        last_indexed_hash=None,
        parser_version=PARSER_VERSION,
        failure_code=code,
        failure_detail=detail[:200],
    )
