"""The embedding adapter and cache. No network: httpx's mock transport plays the provider."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.knowledge_base import EMBEDDING_SCHEMA_VERSION
from app.knowledge_base.db import KnowledgeDatabase, pack_vector, unpack_vector
from app.knowledge_base.embeddings import (
    DisabledEmbeddingProvider,
    EmbeddingError,
    FakeEmbeddingProvider,
    OpenAiCompatibleEmbeddingProvider,
    embedding_provider,
)
from app.knowledge_base.index import KnowledgeIndexer, SyncOptions
from app.knowledge_base.models import RetrievalFilter, SourceFormat
from app.knowledge_base.vector_store import SqliteNumpyVectorStore

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "knowledge"


def _settings(**overrides: object) -> Settings:
    base = {
        "ai_endpoint": "https://synthetic-resource.openai.azure.com/openai/responses?api-version=2025-04-01-preview",
        "ai_api_key": "not-a-real-key-synthetic",
        "embeddings_deployment": "text-embedding-synthetic",
        "embedding_batch_size": 3,
        "embedding_max_retries": 2,
        "app_env": "test",
        "ai_provider": "disabled",
        # Explicit: the session fixture exports EMBEDDING_PROVIDER=fake for other tests.
        "embedding_provider": "auto",
    }
    base.update(overrides)
    # No .env: the operator's deployment must never leak into a test.
    return Settings(_env_file=None, **base)  # type: ignore[arg-type, call-arg]


class _Server:
    """A scripted embedding server: records calls, can fail N times, returns hashed vectors."""

    def __init__(self, *, dimensions: int = 8, fail_statuses: list[int] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.dimensions = dimensions
        self.fail_statuses = list(fail_statuses or [])
        self.legacy_hits = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.calls.append(
            {
                "path": request.url.path,
                "query": dict(request.url.params),
                "n": len(body["input"]),
                "headers": dict(request.headers),
            }
        )
        if request.url.path.startswith("/openai/deployments/"):
            self.legacy_hits += 1
        if self.fail_statuses:
            status = self.fail_statuses.pop(0)
            headers = {"Retry-After": "0"} if status == 429 else {}
            return httpx.Response(status, json={"error": {"message": "simulated"}}, headers=headers)
        data = [
            {
                "index": i,
                "embedding": [float((hash(text) >> k) % 7) / 7 for k in range(self.dimensions)],
            }
            for i, text in enumerate(body["input"])
        ]
        return httpx.Response(
            200,
            json={
                "data": data,
                "model": "text-embedding-synthetic",
                "usage": {"prompt_tokens": 5 * len(data), "total_tokens": 5 * len(data)},
            },
        )


def _provider(server: _Server, **overrides: object) -> OpenAiCompatibleEmbeddingProvider:
    settings = _settings(**overrides)
    client = httpx.Client(
        base_url=settings.ai_endpoint_origin, transport=httpx.MockTransport(server.handler)
    )
    return OpenAiCompatibleEmbeddingProvider(settings, client=client, sleep=lambda _s: None)


def test_batches_never_one_request_per_chunk_and_usage_is_summed() -> None:
    server = _Server()
    provider = _provider(server)
    result = provider.embed([f"text {i}" for i in range(7)])
    assert [call["n"] for call in server.calls] == [3, 3, 1]
    assert len(result.vectors) == 7 and result.dimensions == 8
    assert result.usage.prompt_tokens == 35
    assert result.requests == 3


def test_azure_uses_the_api_key_header_and_the_v1_route_first_then_falls_back_to_legacy() -> None:
    server = _Server(fail_statuses=[404])
    provider = _provider(server)
    provider.embed(["one"])
    assert server.calls[0]["path"] == "/openai/v1/embeddings"
    assert server.calls[1]["path"].startswith("/openai/deployments/text-embedding-synthetic/")
    assert server.calls[1]["query"] == {"api-version": "2025-04-01-preview"}
    assert "api-key" in server.calls[0]["headers"]
    assert "authorization" not in server.calls[0]["headers"]
    server.calls.clear()
    provider.embed(["two"])
    assert server.calls[0]["path"].startswith("/openai/deployments/"), "legacy is remembered"


def test_rate_limit_and_server_errors_are_retried_then_succeed() -> None:
    server = _Server(fail_statuses=[429, 503])
    provider = _provider(server)
    result = provider.embed(["one"])
    assert len(result.vectors) == 1
    assert result.attempts == 3


def test_retries_are_bounded_and_the_error_is_named() -> None:
    server = _Server(fail_statuses=[429, 429, 429, 429])
    provider = _provider(server)
    with pytest.raises(EmbeddingError) as caught:
        provider.embed(["one"])
    assert caught.value.code == "EMBEDDING_RATE_LIMITED"


def test_authentication_failure_is_not_retried() -> None:
    server = _Server(fail_statuses=[401, 401])
    provider = _provider(server)
    with pytest.raises(EmbeddingError) as caught:
        provider.embed(["one"])
    assert caught.value.code == "EMBEDDING_AUTHENTICATION_FAILED"
    assert len(server.calls) == 1


def test_timeouts_surface_as_a_named_error() -> None:
    settings = _settings()

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    client = httpx.Client(
        base_url=settings.ai_endpoint_origin, transport=httpx.MockTransport(handler)
    )
    provider = OpenAiCompatibleEmbeddingProvider(settings, client=client, sleep=lambda _s: None)
    with pytest.raises(EmbeddingError) as caught:
        provider.embed(["one"])
    assert caught.value.code == "EMBEDDING_TIMEOUT"


def test_partial_failure_in_a_later_batch_fails_the_call_without_silent_truncation() -> None:
    server = _Server(fail_statuses=[])
    provider = _provider(server)
    # First batch succeeds, the second meets a hard 400.
    server.fail_statuses = []
    calls = {"n": 0}
    original = server.handler

    def flaky(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 2:
            return httpx.Response(400, json={"error": {"message": "bad"}})
        return original(request)

    settings = _settings()
    client = httpx.Client(
        base_url=settings.ai_endpoint_origin, transport=httpx.MockTransport(flaky)
    )
    provider = OpenAiCompatibleEmbeddingProvider(settings, client=client, sleep=lambda _s: None)
    with pytest.raises(EmbeddingError) as caught:
        provider.embed([f"t{i}" for i in range(5)])
    assert caught.value.code == "EMBEDDING_REQUEST_INVALID"


def test_provider_selection_respects_disabled_fake_and_auto() -> None:
    assert isinstance(
        embedding_provider(_settings(embedding_provider="disabled")), DisabledEmbeddingProvider
    )
    assert isinstance(
        embedding_provider(_settings(embedding_provider="fake")), FakeEmbeddingProvider
    )
    auto = embedding_provider(_settings())
    assert auto.name == "azure_openai"
    unconfigured = embedding_provider(_settings(ai_api_key=None))
    assert isinstance(unconfigured, DisabledEmbeddingProvider)
    with pytest.raises(EmbeddingError) as caught:
        unconfigured.embed(["x"])
    assert caught.value.code == "EMBEDDING_PROVIDER_UNAVAILABLE"


def test_vectors_round_trip_through_the_float32_blob() -> None:
    values = [0.25, -1.0, 3.5]
    assert list(unpack_vector(pack_vector(values))) == values


def _sync(tmp_path: Path, provider: FakeEmbeddingProvider, **overrides: object):  # type: ignore[no-untyped-def]
    settings = _settings(
        knowledge_mode="local",
        knowledge_db_path=str(tmp_path / "k.sqlite3"),
        knowledge_pack_dir=str(tmp_path / "packs"),
        knowledge_source_cache_dir=str(tmp_path / "cache"),
        embedding_provider="fake",
        **overrides,
    )
    database = KnowledgeDatabase(tmp_path / "k.sqlite3")
    indexer = KnowledgeIndexer(settings, database, provider, roots=[FIXTURES])
    return database, indexer.sync(SyncOptions(compile_structures=False, write_manifest=False))


def test_unchanged_chunks_are_never_embedded_twice(tmp_path: Path) -> None:
    provider = FakeEmbeddingProvider(dimensions=16)
    _database, first = _sync(tmp_path, provider)
    assert first.segments_embedded > 0
    first_calls = len(provider.calls)
    _database, second = _sync(tmp_path, provider)
    assert second.segments_embedded == 0
    assert second.embedding_requests == 0
    assert len(provider.calls) == first_calls


def test_identical_segments_in_two_sources_share_one_embedding() -> None:
    """The SR2026 and SR2027 guides share most pages; the cache is keyed by segment hash."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        provider = FakeEmbeddingProvider(dimensions=16)
        _database, report = _sync(Path(tmp), provider)
        assert report.embedding_cache_hits > 0
        assert report.embedding_requests_avoided > 0


def test_a_deployment_change_re_embeds_and_dimensions_are_never_mixed(tmp_path: Path) -> None:
    first = FakeEmbeddingProvider(dimensions=16, deployment="fake-a")
    database, _report = _sync(tmp_path, first)
    second = FakeEmbeddingProvider(dimensions=32, deployment="fake-b")
    _database, report = _sync(tmp_path, second)
    assert report.segments_embedded > 0, "a new deployment embeds again"
    store = SqliteNumpyVectorStore(database)
    filter_ = RetrievalFilter(format=SourceFormat.MT, message_type="MT999", release="SR2026")
    assert (
        store.count(
            provider="fake",
            deployment="fake-a",
            dimensions=16,
            schema_version=EMBEDDING_SCHEMA_VERSION,
            filter=filter_,
        )
        > 0
    )
    assert (
        store.count(
            provider="fake",
            deployment="fake-b",
            dimensions=32,
            schema_version=EMBEDDING_SCHEMA_VERSION,
            filter=filter_,
        )
        > 0
    )
    assert (
        store.count(
            provider="fake",
            deployment="fake-b",
            dimensions=16,
            schema_version=EMBEDDING_SCHEMA_VERSION,
            filter=filter_,
        )
        == 0
    )
    with pytest.raises(ValueError):
        store.search(
            [0.0] * 16,
            provider="fake",
            deployment="fake-b",
            dimensions=32,
            schema_version=EMBEDDING_SCHEMA_VERSION,
            filter=filter_,
            k=3,
        )


def test_policy_blocks_licensed_sources_even_with_a_provider(tmp_path: Path) -> None:
    """Strip the synthetic declaration from a guide: it becomes licensed and is not embedded."""
    root = tmp_path / "src"
    root.mkdir()
    text = (FIXTURES / "guides" / "mt999-synthetic-guide-sr2026.txt").read_text()
    (root / "licensed.txt").write_text(
        text.replace("KNOWLEDGE-SOURCE-CLASSIFICATION: SYNTHETIC_FIXTURE\n", "")
    )
    provider = FakeEmbeddingProvider(dimensions=16)
    settings = _settings(
        knowledge_mode="local",
        knowledge_db_path=str(tmp_path / "k.sqlite3"),
        knowledge_pack_dir=str(tmp_path / "packs"),
        knowledge_source_cache_dir=str(tmp_path / "cache"),
        embedding_provider="fake",
    )
    database = KnowledgeDatabase(tmp_path / "k.sqlite3")
    report = KnowledgeIndexer(settings, database, provider, roots=[root]).sync(
        SyncOptions(compile_structures=False, write_manifest=False)
    )
    assert report.embedding_blocked_segments > 0
    assert report.segments_embedded == 0
    assert provider.calls == []
    source = database.sources()[0]
    assert source.embedding_policy.value == "BLOCKED"
    assert source.ingestion_state.value == "EMBEDDING_BLOCKED"


def test_provider_disabled_still_indexes_for_lexical_search(tmp_path: Path) -> None:
    database, report = _sync(tmp_path, DisabledEmbeddingProvider())  # type: ignore[arg-type]
    assert report.segments_created > 0
    assert report.segments_embedded == 0
    assert database.counts()["embeddings"] == 0
