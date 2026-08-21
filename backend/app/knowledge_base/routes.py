"""`/api/v1/knowledge` — safe, read-mostly access to the knowledge base.

What is never returned: a full document, full segment text of licensed material, an
absolute path, a credential. Citations carry ids, titles, pages and sections; snippets only
where the source's policy permits. The sync endpoint exists in ``local_uat`` mode alone.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

from app.config import get_settings
from app.domain.models import ApiModel
from app.knowledge_base.models import QueryType, RetrievalFilter, SourceFormat
from app.knowledge_base.service import knowledge_service, section_filter
from app.studio.security import AutomationCaller

router = APIRouter(prefix="/api/v1/knowledge", tags=["Knowledge Base"])


class KnowledgeSearchRequest(ApiModel):
    query: str = Field(min_length=1, max_length=2_000)
    format: str | None = Field(default=None, max_length=2)
    message_type: str | None = Field(default=None, max_length=32)
    release: str | None = Field(default=None, max_length=32)
    sections: list[str] | None = None
    limit: int = Field(default=8, ge=1, le=40)
    #: Lexical only, even when embeddings exist.
    lexical_only: bool = False


class KnowledgeCitation(ApiModel):
    source_id: str
    document_title: str
    format: str
    message_type: str | None
    message_version: str | None
    release: str | None
    document_type: str
    section: str
    page: int | None
    heading: str | None
    segment_id: str
    segment_hash: str
    score: float
    method: str
    snippet: str | None = None


class KnowledgeSearchResponse(ApiModel):
    query: str
    query_type: str
    indexed: bool
    results: list[KnowledgeCitation]
    lexical_candidates: int
    semantic_candidates: int
    semantic_available: bool
    semantic_reason: str | None
    latency_ms: int
    context_chars: int
    corpus_version: str | None
    policy_statement: str | None
    message: str | None = None


def _filter(request: KnowledgeSearchRequest) -> RetrievalFilter:
    format_: SourceFormat | None = None
    if request.format:
        try:
            format_ = SourceFormat(request.format.upper())
        except ValueError as error:
            raise HTTPException(status_code=422, detail="format must be MT or MX") from error
    message_type = request.message_type.strip() if request.message_type else None
    message_version = None
    if message_type and format_ is None:
        format_ = SourceFormat.MT if message_type.upper().startswith("MT") else SourceFormat.MX
    if format_ is SourceFormat.MX and message_type and message_type.count(".") >= 3:
        message_version = message_type.lower()
        message_type = ".".join(message_version.split(".")[:2])
    elif format_ is SourceFormat.MX and message_type:
        message_type = message_type.lower()
    elif message_type:
        message_type = message_type.upper()
    return RetrievalFilter(
        format=format_,
        message_type=message_type,
        message_version=message_version,
        release=request.release.strip().upper() if request.release else None,
        sections=section_filter(request.sections),
    )


def search_knowledge(
    request: KnowledgeSearchRequest, query_type: QueryType = QueryType.FREE_TEXT
) -> KnowledgeSearchResponse:
    from app.knowledge_base.retrieval import RetrievalOptions

    status = knowledge_service.status()
    if not status.indexed:
        return KnowledgeSearchResponse(
            query=request.query,
            query_type=query_type.value,
            indexed=False,
            results=[],
            lexical_candidates=0,
            semantic_candidates=0,
            semantic_available=False,
            semantic_reason="KNOWLEDGE_NOT_INDEXED",
            latency_ms=0,
            context_chars=0,
            corpus_version=None,
            policy_statement=None,
            message=status.as_dict()["message"],
        )
    result = knowledge_service.retrieve(
        request.query,
        query_type=query_type,
        filter=_filter(request),
        options=RetrievalOptions(
            k_lexical=max(request.limit, 10),
            k_semantic=max(request.limit, 10),
            context_chars=get_settings().knowledge_context_chars,
            use_semantic=not request.lexical_only,
        ),
    )
    citations = knowledge_service.citations(result)[: request.limit]
    return KnowledgeSearchResponse(
        query=request.query,
        query_type=query_type.value,
        indexed=True,
        results=[
            KnowledgeCitation(
                source_id=item.source_id,
                document_title=item.document_title,
                format=item.format.value,
                message_type=item.message_type,
                message_version=item.message_version,
                release=item.release,
                document_type=item.document_type.value,
                section=item.section.value,
                page=item.page,
                heading=item.heading,
                segment_id=item.segment_id,
                segment_hash=item.segment_hash,
                score=item.score,
                method=item.method.value,
                snippet=item.snippet,
            )
            for item in citations
        ],
        lexical_candidates=result.lexical_candidates,
        semantic_candidates=result.semantic_candidates,
        semantic_available=result.semantic_available,
        semantic_reason=result.semantic_reason,
        latency_ms=result.latency_ms,
        context_chars=result.context_chars,
        corpus_version=result.corpus_version or None,
        policy_statement=status.embedding_policy_statement,
        message=None if citations else "RAG_NO_RELEVANT_EVIDENCE",
    )


@router.get("/status")
def knowledge_status(caller: AutomationCaller) -> dict[str, Any]:
    """Whether a knowledge base exists, what it holds, and how it may be used.

    Reports that an embedding deployment is configured — never what it is.
    """
    del caller
    return knowledge_service.status().as_dict()


@router.get("/messages")
def knowledge_messages(caller: AutomationCaller) -> dict[str, Any]:
    """Every message identity the knowledge base knows, with source and structure state."""
    del caller
    status = knowledge_service.status()
    return {
        "indexed": status.indexed,
        "messages": knowledge_service.messages(),
        "message": status.as_dict()["message"],
    }


@router.get("/messages/{message}/status")
def knowledge_message_status(message: str, caller: AutomationCaller) -> dict[str, Any]:
    del caller
    found = knowledge_service.message_status(message)
    if found is None:
        raise HTTPException(
            status_code=404,
            detail=f"KNOWLEDGE_SOURCE_NOT_FOUND: the knowledge base holds nothing for {message}.",
        )
    return found


@router.post("/search", response_model=KnowledgeSearchResponse)
def knowledge_search(
    request: KnowledgeSearchRequest, caller: AutomationCaller
) -> KnowledgeSearchResponse:
    """Hybrid retrieval over the indexed sources, narrowed by message and release."""
    del caller
    return search_knowledge(request)


@router.get("/telemetry")
def knowledge_telemetry(caller: AutomationCaller) -> dict[str, Any]:
    """LLM calls, tokens, cache hits, embedding and retrieval counters. No cost is invented."""
    del caller
    return knowledge_service.telemetry()


@router.get("/sources")
def knowledge_sources(
    caller: AutomationCaller,
    include_deleted: Annotated[bool, Query(alias="includeDeleted")] = False,
) -> dict[str, Any]:
    """Every discovered source with its identity, policy and index state. Relative paths
    only; the knowledge root is never disclosed."""
    del caller
    status = knowledge_service.status()
    sources = [
        {
            "sourceId": item.source_id,
            "checksum": f"sha256:{item.checksum}",
            "relativePaths": item.relative_paths,
            "sourceType": item.source_type.value,
            "format": item.format.value,
            "documentType": item.document_type.value,
            "classification": item.classification.value,
            "messageType": item.message_type,
            "messageVersion": item.message_version,
            "release": item.release,
            "title": item.title,
            "pageCount": item.page_count,
            "embeddingPolicy": item.embedding_policy.value,
            "llmPolicy": item.llm_policy.value,
            "state": item.ingestion_state.value,
            "segments": item.segment_count,
            "embedded": item.embedded_count,
            "failureCode": item.failure_code,
            "failureDetail": item.failure_detail,
            "deleted": item.deleted,
        }
        for item in knowledge_service.sources()
        if include_deleted or not item.deleted
    ]
    return {"indexed": status.indexed, "sources": sources, "message": status.as_dict()["message"]}


@router.post("/sync")
def knowledge_sync(caller: AutomationCaller) -> dict[str, Any]:
    """Run an incremental sync. Local UAT mode only; never exposed elsewhere."""
    del caller
    settings = get_settings()
    if settings.knowledge_mode != "local_uat":
        raise HTTPException(
            status_code=404,
            detail="The sync endpoint exists only when KNOWLEDGE_MODE=local_uat.",
        )
    from app.knowledge_base.index import KnowledgeIndexer, SyncOptions
    from app.knowledge_base.preview import reload_preview
    from app.studio.catalogue import invalidate_catalogue_cache, message_spec
    from app.studio.routes import invalidate_catalogue_response_cache

    indexer = KnowledgeIndexer(settings, knowledge_service.database, knowledge_service.embeddings)
    report = indexer.sync(SyncOptions())
    reload_preview(settings)
    message_spec.cache_clear()
    invalidate_catalogue_cache()
    invalidate_catalogue_response_cache()
    return {"run": report.as_dict(), "status": knowledge_service.status().as_dict()}
