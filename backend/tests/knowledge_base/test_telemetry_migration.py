from __future__ import annotations

import sqlite3
from pathlib import Path

from app.knowledge_base.db import KnowledgeDatabase


def test_existing_operation_ledger_receives_additive_privacy_safe_columns(
    tmp_path: Path,
) -> None:
    path = tmp_path / "knowledge.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE knowledge_operation_metric ("
            "request_id TEXT PRIMARY KEY, at TEXT NOT NULL, operation TEXT NOT NULL, "
            "message_type TEXT, release TEXT, provider TEXT NOT NULL, model TEXT NOT NULL, "
            "llm_calls INTEGER NOT NULL, prompt_tokens INTEGER NOT NULL, "
            "completion_tokens INTEGER NOT NULL, cache_hit INTEGER NOT NULL, "
            "calls_avoided INTEGER NOT NULL, tokens_avoided INTEGER NOT NULL, "
            "latency_ms INTEGER NOT NULL, rag_used INTEGER NOT NULL, rag_mode TEXT, "
            "query_type TEXT, evidence_count INTEGER NOT NULL, "
            "retrieval_latency_ms INTEGER NOT NULL, embedding_calls INTEGER NOT NULL, "
            "corpus_version TEXT, outcome TEXT NOT NULL)"
        )

    KnowledgeDatabase(path).initialise()

    with sqlite3.connect(path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(knowledge_operation_metric)")
        }
        version = connection.execute(
            "SELECT value FROM knowledge_meta WHERE key = 'schema_version'"
        ).fetchone()
    assert {
        "format_filter",
        "lexical_candidates",
        "semantic_candidates",
        "context_chars",
        "embedding_tokens",
        "embedding_cache_hits",
        "embedding_latency_ms",
    } <= columns
    assert version == ("3",)
