"""Optional development auto-sync at startup — incremental, in a worker thread, observable.

Never the default: a production-style process must not read arbitrary workstation files,
and startup must never wait thirty minutes for embeddings. When enabled, the existing index
serves requests immediately and the sync reports progress through the status endpoint.
"""

from __future__ import annotations

import asyncio
import logging

from app.config import get_settings

LOGGER = logging.getLogger("knowledge.sync")


async def run_background_sync() -> None:
    settings = get_settings()

    def work() -> None:
        from app.knowledge_base.index import KnowledgeIndexer, SyncOptions
        from app.knowledge_base.preview import reload_preview
        from app.knowledge_base.service import knowledge_service
        from app.studio.catalogue import invalidate_catalogue_cache, message_spec
        from app.studio.routes import invalidate_catalogue_response_cache

        indexer = KnowledgeIndexer(
            settings, knowledge_service.database, knowledge_service.embeddings
        )
        report = indexer.sync(SyncOptions())
        reload_preview(settings)
        message_spec.cache_clear()
        invalidate_catalogue_cache()
        invalidate_catalogue_response_cache()
        LOGGER.info(
            "knowledge auto-sync complete: %s discovered, %s unchanged, %s parsed, %s failed",
            report.documents_discovered,
            report.documents_unchanged,
            report.documents_parsed,
            report.documents_failed,
        )

    try:
        await asyncio.to_thread(work)
    except asyncio.CancelledError:
        raise
    except Exception as error:  # noqa: BLE001 - a failed auto-sync must never crash startup
        LOGGER.warning("knowledge auto-sync failed: %s", type(error).__name__)
