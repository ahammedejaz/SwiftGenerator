"""Shared value types for the knowledge base.

Plain dataclasses and enums: these cross the boundary between the sync command, the SQLite
store, the retrieval service and the HTTP layer, so they carry ids, hashes and counts — and
never an absolute path or a credential.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SourceType(StrEnum):
    MT_MESSAGE_REFERENCE_GUIDE = "MT_MESSAGE_REFERENCE_GUIDE"
    MT_DOCUMENT = "MT_DOCUMENT"
    ISO20022_XSD = "ISO20022_XSD"
    ISO20022_DOCUMENT = "ISO20022_DOCUMENT"
    TEXT_NOTE = "TEXT_NOTE"
    HTML_DOCUMENT = "HTML_DOCUMENT"
    UNKNOWN = "UNKNOWN"


class SourceFormat(StrEnum):
    MT = "MT"
    MX = "MX"
    UNKNOWN = "UNKNOWN"


class DocumentType(StrEnum):
    MRG = "MRG"
    XSD = "XSD"
    USAGE_GUIDE = "USAGE_GUIDE"
    NOTE = "NOTE"
    UNKNOWN = "UNKNOWN"


class SourceClassification(StrEnum):
    """A declaration about licensing, never a verification. Unknown means licensed."""

    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"
    OFFICIAL_SWIFT_MT_STANDARDS_MATERIAL = "OFFICIAL_SWIFT_MT_STANDARDS_MATERIAL"
    OPERATOR_SUPPLIED_XSD = "OPERATOR_SUPPLIED_XSD"
    OPERATOR_SUPPLIED_DOCUMENT = "OPERATOR_SUPPLIED_DOCUMENT"
    LICENSED_UNKNOWN = "LICENSED_UNKNOWN"


class ExternalPolicy(StrEnum):
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"


class IngestionState(StrEnum):
    DISCOVERED = "DISCOVERED"
    IDENTIFIED = "IDENTIFIED"
    PARSED = "PARSED"
    SEGMENTED = "SEGMENTED"
    INDEXED = "INDEXED"
    EMBEDDED = "EMBEDDED"
    EMBEDDING_BLOCKED = "EMBEDDING_BLOCKED"
    FAILED = "FAILED"
    UNSUPPORTED = "UNSUPPORTED"
    DELETED = "DELETED"


class Section(StrEnum):
    SCOPE = "SCOPE"
    FORMAT_SPECIFICATION = "FORMAT_SPECIFICATION"
    NETWORK_VALIDATED_RULE = "NETWORK_VALIDATED_RULE"
    USAGE_RULE = "USAGE_RULE"
    FIELD_SPECIFICATION = "FIELD_SPECIFICATION"
    EXAMPLE = "EXAMPLE"
    LEGAL_NOTICE = "LEGAL_NOTICE"
    MESSAGE_DEFINITION = "MESSAGE_DEFINITION"
    BUSINESS_RULES = "BUSINESS_RULES"
    ELEMENT_DEFINITION = "ELEMENT_DEFINITION"
    TABLE_OF_CONTENTS = "TABLE_OF_CONTENTS"
    COVER = "COVER"
    OTHER = "OTHER"


class TableState(StrEnum):
    NONE = "NONE"
    TABLE_EXTRACTED = "TABLE_EXTRACTED"
    TABLE_EXTRACTION_PARTIAL = "TABLE_EXTRACTION_PARTIAL"


class RetrievalMethod(StrEnum):
    LEXICAL = "LEXICAL"
    SEMANTIC = "SEMANTIC"
    HYBRID = "HYBRID"
    METADATA = "METADATA"


class QueryType(StrEnum):
    MESSAGE_SELECTION = "MESSAGE_SELECTION"
    FIELD_EXPLANATION = "FIELD_EXPLANATION"
    RULE_EXPLANATION = "RULE_EXPLANATION"
    SAMPLE_PREPARATION = "SAMPLE_PREPARATION"
    TEST_SCENARIO_PREPARATION = "TEST_SCENARIO_PREPARATION"
    MISSING_DATA_GUIDANCE = "MISSING_DATA_GUIDANCE"
    MESSAGE_COMPARISON = "MESSAGE_COMPARISON"
    FREE_TEXT = "FREE_TEXT"


class Lane(StrEnum):
    CONFIGURED = "CONFIGURED"
    KNOWLEDGE_PREVIEW = "KNOWLEDGE_PREVIEW"


class ReleaseLane(StrEnum):
    CURRENT_LIVE = "CURRENT_LIVE"
    FUTURE_TEST = "FUTURE_TEST"
    UNKNOWN = "UNKNOWN"


class Readiness(StrEnum):
    KNOWLEDGE_ONLY = "KNOWLEDGE_ONLY"
    STRUCTURE_AVAILABLE = "STRUCTURE_AVAILABLE"
    STRUCTURE_VERIFIED = "STRUCTURE_VERIFIED"
    GENERATION_READY = "GENERATION_READY"


#: Recorded, never computed from the clock: a release lane that moved on its own would be
#: a validation rule that changed overnight without a commit.
RELEASE_LANES: dict[str, ReleaseLane] = {
    "SR2024": ReleaseLane.CURRENT_LIVE,
    "SR2025": ReleaseLane.CURRENT_LIVE,
    "SR2026": ReleaseLane.FUTURE_TEST,
    "SR2027": ReleaseLane.FUTURE_TEST,
}


def release_lane(release: str | None) -> ReleaseLane:
    if not release:
        return ReleaseLane.UNKNOWN
    return RELEASE_LANES.get(release, ReleaseLane.UNKNOWN)


@dataclass(frozen=True)
class SourceIdentity:
    source_id: str
    source_type: SourceType
    format: SourceFormat
    document_type: DocumentType
    message_type: str | None = None
    message_version: str | None = None
    release: str | None = None
    publisher: str | None = None
    title: str | None = None
    problems: tuple[str, ...] = ()


@dataclass
class SourceRecord:
    checksum: str
    source_id: str
    relative_paths: list[str]
    byte_size: int
    source_type: SourceType
    format: SourceFormat
    document_type: DocumentType
    classification: SourceClassification
    message_type: str | None
    message_version: str | None
    release: str | None
    publisher: str | None
    title: str | None
    page_count: int | None
    embedding_policy: ExternalPolicy
    llm_policy: ExternalPolicy
    ingestion_state: IngestionState
    last_indexed_hash: str | None
    parser_version: str
    failure_code: str | None = None
    failure_detail: str | None = None
    segment_count: int = 0
    embedded_count: int = 0
    deleted: bool = False


@dataclass(frozen=True)
class SegmentRecord:
    segment_id: str
    source_id: str
    ordinal: int
    segment_hash: str
    text_hash: str
    section: Section
    page: int | None
    heading: str | None
    identifiers: tuple[str, ...]
    table_state: TableState
    text: str
    message_type: str | None
    message_version: str | None
    release: str | None
    format: SourceFormat


@dataclass(frozen=True)
class Citation:
    source_id: str
    document_title: str
    format: SourceFormat
    message_type: str | None
    message_version: str | None
    release: str | None
    document_type: DocumentType
    section: Section
    page: int | None
    heading: str | None
    segment_id: str
    segment_hash: str
    score: float
    method: RetrievalMethod
    snippet: str | None = None


@dataclass(frozen=True)
class RetrievalFilter:
    format: SourceFormat | None = None
    message_type: str | None = None
    message_version: str | None = None
    release: str | None = None
    sections: tuple[Section, ...] = ()
    #: Explicit comparison across releases of one message; never implicit.
    releases: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievalHit:
    segment: SegmentRecord
    score: float
    method: RetrievalMethod
    lexical_rank: int | None
    semantic_rank: int | None


@dataclass
class RetrievalResult:
    query_type: QueryType
    filter: RetrievalFilter
    hits: list[RetrievalHit]
    lexical_candidates: int
    semantic_candidates: int
    semantic_available: bool
    semantic_reason: str | None
    latency_ms: int
    context_chars: int
    corpus_version: str

    def citations(self, *, allow_snippets: bool) -> list[Citation]:
        return [
            Citation(
                source_id=hit.segment.source_id,
                document_title=_title(hit.segment),
                format=hit.segment.format,
                message_type=hit.segment.message_type,
                message_version=hit.segment.message_version,
                release=hit.segment.release,
                document_type=_document_type(hit.segment),
                section=hit.segment.section,
                page=hit.segment.page,
                heading=hit.segment.heading,
                segment_id=hit.segment.segment_id,
                segment_hash=hit.segment.segment_hash,
                score=round(hit.score, 6),
                method=hit.method,
                snippet=_snippet(hit.segment.text) if allow_snippets else None,
            )
            for hit in self.hits
        ]


def _title(segment: SegmentRecord) -> str:
    parts = [segment.message_version or segment.message_type or segment.source_id]
    if segment.release:
        parts.append(segment.release)
    if segment.format is SourceFormat.MT:
        parts.append("MRG" if segment.source_id.endswith("-MRG") else "document")
    elif segment.format is SourceFormat.MX:
        parts.append("XSD" if "-XSD-" in segment.source_id else "document")
    return " ".join(parts)


def _document_type(segment: SegmentRecord) -> DocumentType:
    if segment.source_id.endswith("-MRG"):
        return DocumentType.MRG
    if "-XSD-" in segment.source_id:
        return DocumentType.XSD
    return DocumentType.UNKNOWN


def _snippet(text: str, limit: int = 240) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


@dataclass
class SyncProgress:
    documents_discovered: int = 0
    documents_unchanged: int = 0
    documents_parsed: int = 0
    documents_failed: int = 0
    documents_unsupported: int = 0
    documents_deleted: int = 0
    segments_created: int = 0
    segments_reused: int = 0
    segments_embedded: int = 0
    embedding_cache_hits: int = 0
    embedding_requests: int = 0
    embedding_requests_avoided: int = 0
    embedding_blocked_segments: int = 0
    embedding_tokens: int | None = None
    embedding_latency_ms: int = 0
    structures_compiled: int = 0
    structures_reused: int = 0
    structures_failed: int = 0
    elapsed_ms: int = 0
    failures: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "documentsDiscovered": self.documents_discovered,
            "documentsUnchanged": self.documents_unchanged,
            "documentsParsed": self.documents_parsed,
            "documentsFailed": self.documents_failed,
            "documentsUnsupported": self.documents_unsupported,
            "documentsDeleted": self.documents_deleted,
            "segmentsCreated": self.segments_created,
            "segmentsReused": self.segments_reused,
            "segmentsEmbedded": self.segments_embedded,
            "embeddingCacheHits": self.embedding_cache_hits,
            "embeddingRequests": self.embedding_requests,
            "embeddingRequestsAvoided": self.embedding_requests_avoided,
            "embeddingBlockedSegments": self.embedding_blocked_segments,
            "embeddingTokens": self.embedding_tokens,
            "embeddingLatencyMs": self.embedding_latency_ms,
            "structuresCompiled": self.structures_compiled,
            "structuresReused": self.structures_reused,
            "structuresFailed": self.structures_failed,
            "elapsedMs": self.elapsed_ms,
            "failures": list(self.failures),
        }
