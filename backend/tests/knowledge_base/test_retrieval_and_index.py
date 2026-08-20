"""Hybrid retrieval, and the index lifecycle: fresh, incremental, changed, deleted, failed,
interrupted, concurrent."""

from __future__ import annotations

import shutil
import threading
from pathlib import Path

import pytest

from app.config import Settings
from app.knowledge_base.db import KnowledgeDatabase
from app.knowledge_base.embeddings import FakeEmbeddingProvider
from app.knowledge_base.index import KnowledgeIndexer, SyncOptions
from app.knowledge_base.models import QueryType, RetrievalFilter, Section, SourceFormat
from app.knowledge_base.retrieval import HybridRetriever, RetrievalOptions, fts_query

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "knowledge"


def _settings(tmp_path: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        app_env="test",
        ai_provider="disabled",
        knowledge_mode="local",
        knowledge_db_path=str(tmp_path / "k.sqlite3"),
        knowledge_pack_dir=str(tmp_path / "packs"),
        knowledge_source_cache_dir=str(tmp_path / "cache"),
        embedding_provider="fake",
    )


@pytest.fixture
def corpus(tmp_path: Path) -> tuple[KnowledgeDatabase, HybridRetriever, Path]:
    root = tmp_path / "src"
    shutil.copytree(FIXTURES, root)
    settings = _settings(tmp_path)
    database = KnowledgeDatabase(tmp_path / "k.sqlite3")
    provider = FakeEmbeddingProvider(dimensions=64)
    KnowledgeIndexer(settings, database, provider, roots=[root]).sync(
        SyncOptions(compile_structures=False, write_manifest=False)
    )
    return database, HybridRetriever(database, provider, corpus_version="t"), root


def _retrieve(retriever: HybridRetriever, query: str, **filter_: object):  # type: ignore[no-untyped-def]
    return retriever.retrieve(
        query,
        query_type=QueryType.FREE_TEXT,
        filter=RetrievalFilter(**filter_),  # type: ignore[arg-type]
        options=RetrievalOptions(k_lexical=10, k_semantic=10, context_chars=50_000),
    )


def test_fts_queries_are_safe_and_identifier_aware() -> None:
    expression = fts_query(':95P::PSET "quoted" OR NOT (x)')
    assert expression is not None
    assert '"95P"' in expression and '"PSET"' in expression
    assert '"quoted"' in expression
    # Every term is quoted, so FTS5 operators in the text are data, not syntax.
    assert all(part.strip().startswith('"') for part in expression.split(" OR "))
    assert fts_query("the of and") is None


def test_lexical_exact_tag_lookup(corpus) -> None:  # type: ignore[no-untyped-def]
    _db, retriever, _root = corpus
    result = _retrieve(
        retriever, ":22F::DBNM", format=SourceFormat.MT, message_type="MT999", release="SR2026"
    )
    assert result.hits and "DBNM" in result.hits[0].segment.text


def test_semantic_phrase_finds_the_rule(corpus) -> None:  # type: ignore[no-untyped-def]
    _db, retriever, _root = corpus
    result = _retrieve(
        retriever,
        "cancellation needs one previous reference",
        format=SourceFormat.MT,
        message_type="MT999",
        release="SR2026",
    )
    assert any("C6" in h.segment.text for h in result.hits[:5])
    assert result.semantic_available


def test_message_and_release_isolation(corpus) -> None:  # type: ignore[no-untyped-def]
    _db, retriever, _root = corpus
    result = _retrieve(
        retriever,
        "synthetic reference amount",
        format=SourceFormat.MT,
        message_type="MT999",
        release="SR2027",
    )
    assert result.hits
    assert {h.segment.release for h in result.hits} == {"SR2027"}
    assert {h.segment.message_type for h in result.hits} == {"MT999"}
    other = _retrieve(
        retriever,
        "envelope sub-message",
        format=SourceFormat.MT,
        message_type="MT999",
        release="SR2026",
    )
    assert all(h.segment.message_type == "MT999" for h in other.hits)


def test_explicit_multi_release_comparison_is_the_only_way_to_mix(corpus) -> None:  # type: ignore[no-untyped-def]
    _db, retriever, _root = corpus
    result = _retrieve(
        retriever,
        "safekeeping account",
        format=SourceFormat.MT,
        message_type="MT999",
        releases=("SR2026", "SR2027"),
    )
    assert {h.segment.release for h in result.hits} == {"SR2026", "SR2027"}


def test_section_filter_and_no_result(corpus) -> None:  # type: ignore[no-untyped-def]
    _db, retriever, _root = corpus
    rules = _retrieve(
        retriever,
        "amount",
        format=SourceFormat.MT,
        message_type="MT999",
        release="SR2026",
        sections=(Section.NETWORK_VALIDATED_RULE,),
    )
    assert rules.hits and all(
        h.segment.section is Section.NETWORK_VALIDATED_RULE for h in rules.hits
    )
    nothing = _retrieve(
        retriever, "quantum widget reconciliation", format=SourceFormat.MX, message_type="test.001"
    )
    assert nothing.hits == []


def test_ranking_is_deterministic_with_stable_tie_breaks(corpus) -> None:  # type: ignore[no-untyped-def]
    _db, retriever, _root = corpus
    first = _retrieve(
        retriever, "party", format=SourceFormat.MT, message_type="MT999", release="SR2026"
    )
    second = _retrieve(
        retriever, "party", format=SourceFormat.MT, message_type="MT999", release="SR2026"
    )
    assert [h.segment.segment_id for h in first.hits] == [h.segment.segment_id for h in second.hits]


def test_vector_disabled_falls_back_to_lexical(corpus) -> None:  # type: ignore[no-untyped-def]
    database, _retriever, _root = corpus
    from app.knowledge_base.embeddings import DisabledEmbeddingProvider

    lexical_only = HybridRetriever(database, DisabledEmbeddingProvider())  # type: ignore[arg-type]
    result = _retrieve(
        lexical_only, "SETT", format=SourceFormat.MT, message_type="MT999", release="SR2026"
    )
    assert result.hits and not result.semantic_available
    assert result.semantic_reason == "EMBEDDING_PROVIDER_UNAVAILABLE"
    assert all(h.method.value == "LEXICAL" for h in result.hits)


# -- index lifecycle ----------------------------------------------------------------------------


def test_incremental_changed_deleted_failed_and_resumed(tmp_path: Path) -> None:
    root = tmp_path / "src"
    shutil.copytree(FIXTURES, root)
    settings = _settings(tmp_path)
    database = KnowledgeDatabase(tmp_path / "k.sqlite3")
    provider = FakeEmbeddingProvider(dimensions=32)
    indexer = KnowledgeIndexer(settings, database, provider, roots=[root])
    opts = SyncOptions(compile_structures=False, write_manifest=False)

    fresh = indexer.sync(opts)
    assert fresh.documents_parsed == 5 and fresh.documents_unchanged == 0
    assert database.counts()["sources"] == 5

    unchanged = indexer.sync(opts)
    assert unchanged.documents_unchanged == 5 and unchanged.documents_parsed == 0
    assert unchanged.embedding_requests == 0

    # Change one file: only it is re-parsed; its old segments are replaced.
    note = root / "notes" / "mt998-usage-note.md"
    note.write_text(note.read_text() + "\n\nAn added paragraph about MT998 envelopes.\n")
    changed = indexer.sync(opts)
    assert changed.documents_parsed == 1 and changed.documents_unchanged == 4
    assert database.counts()["sources"] == 5  # the old bytes were tombstoned, not kept live
    assert database.counts()["sourcesDeleted"] == 1

    # Delete one: tombstoned, segments gone, nothing else touched.
    (root / "schemas" / "test.001.001.01.xsd").unlink()
    deleted = indexer.sync(opts)
    assert deleted.documents_deleted == 1
    assert database.counts()["sources"] == 4
    retriever = HybridRetriever(database, provider)
    assert (
        _retrieve(retriever, "SttlmAmt", format=SourceFormat.MX, message_type="test.001").hits == []
    )

    # A broken file is recorded and does not stop the corpus.
    (root / "broken.pdf").write_bytes(b"%PDF-1.7 not really")
    failed = indexer.sync(opts)
    assert failed.documents_failed == 1
    assert any(
        item["code"] in {"KNOWLEDGE_SOURCE_UNREADABLE", "KNOWLEDGE_SOURCE_UNSUPPORTED"}
        for item in failed.failures
    )
    assert database.counts()["sources"] == 5

    # Resume: a run interrupted mid-way continues where it stopped.
    class Stop(Exception):
        pass

    seen: list[str] = []

    def interrupt(path: str, _report: object) -> None:
        seen.append(path)
        if len(seen) == 2:
            raise Stop()

    (root / "notes" / "second-mt998.md").write_text("# MT998 second note\nMT998 MT998 MT998\n")
    (root / "notes" / "third-mt998.md").write_text("# MT998 third note\nMT998 MT998 MT998\n")
    with pytest.raises(Stop):
        indexer.sync(opts, progress=interrupt)
    run = database.last_run()
    assert run is not None and run["state"] == "INTERRUPTED"
    resumed = indexer.sync(opts)
    assert resumed.documents_failed == 1  # the broken pdf is retried and fails again
    assert resumed.documents_parsed >= 1
    assert database.last_run() is not None and database.last_run()["state"] == "COMPLETED"  # type: ignore[index]


def test_concurrent_retrieval_during_a_sync_is_safe(tmp_path: Path) -> None:
    root = tmp_path / "src"
    shutil.copytree(FIXTURES, root)
    settings = _settings(tmp_path)
    database = KnowledgeDatabase(tmp_path / "k.sqlite3")
    provider = FakeEmbeddingProvider(dimensions=32)
    indexer = KnowledgeIndexer(settings, database, provider, roots=[root])
    opts = SyncOptions(compile_structures=False, write_manifest=False)
    indexer.sync(opts)
    retriever = HybridRetriever(database, provider)
    errors: list[BaseException] = []
    counts: list[int] = []

    def reader() -> None:
        try:
            for _ in range(30):
                counts.append(
                    len(
                        _retrieve(
                            retriever,
                            "amount",
                            format=SourceFormat.MT,
                            message_type="MT999",
                            release="SR2026",
                        ).hits
                    )
                )
        except BaseException as error:  # noqa: BLE001 - collected for the assertion
            errors.append(error)

    def writer() -> None:
        try:
            for index in range(3):
                (root / "notes" / f"extra-{index}.md").write_text(
                    f"# MT998 extra {index}\nMT998 MT998\n"
                )
                indexer.sync(opts)
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    threads = [threading.Thread(target=reader) for _ in range(4)] + [
        threading.Thread(target=writer)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert counts and min(counts) > 0


def test_corpus_version_changes_only_when_sources_change(tmp_path: Path) -> None:
    root = tmp_path / "src"
    shutil.copytree(FIXTURES, root)
    settings = _settings(tmp_path)
    database = KnowledgeDatabase(tmp_path / "k.sqlite3")
    indexer = KnowledgeIndexer(
        settings, database, FakeEmbeddingProvider(dimensions=16), roots=[root]
    )
    opts = SyncOptions(compile_structures=False, write_manifest=False)
    indexer.sync(opts)
    first = database.get_meta("corpus_version")
    indexer.sync(opts)
    assert database.get_meta("corpus_version") == first
    (root / "notes" / "new.md").write_text("# MT998 new\nMT998\n")
    indexer.sync(opts)
    assert database.get_meta("corpus_version") != first


def test_licensed_citations_carry_locators_not_excerpts(tmp_path: Path) -> None:
    """Strip the synthetic marker from the guide: its citations keep source, page and
    section but a rule heading shrinks to the rule id and no snippet is returned."""
    root = tmp_path / "src"
    root.mkdir()
    text = (FIXTURES / "guides" / "mt999-synthetic-guide-sr2026.txt").read_text()
    (root / "licensed.txt").write_text(
        text.replace("KNOWLEDGE-SOURCE-CLASSIFICATION: SYNTHETIC_FIXTURE\n", "")
    )
    settings = _settings(tmp_path)
    database = KnowledgeDatabase(tmp_path / "k.sqlite3")
    provider = FakeEmbeddingProvider(dimensions=32)
    KnowledgeIndexer(settings, database, provider, roots=[root]).sync(
        SyncOptions(compile_structures=False, write_manifest=False)
    )
    retriever = HybridRetriever(database, provider)
    result = _retrieve(
        retriever,
        "cancellation previous reference",
        format=SourceFormat.MT,
        message_type="MT999",
        release="SR2026",
        sections=(Section.NETWORK_VALIDATED_RULE,),
    )
    assert result.hits
    guarded = result.citations(allow_snippets=False)
    assert all(c.snippet is None for c in guarded)
    assert all(c.page is not None and c.section is not None for c in guarded)
    rule_headings = [c.heading for c in guarded if c.heading and c.heading.startswith("C")]
    assert rule_headings and all(len(h) <= 4 for h in rule_headings), rule_headings
    open_ = result.citations(allow_snippets=True)
    assert any(c.snippet for c in open_)
    assert any(len(c.heading or "") > 4 for c in open_)
