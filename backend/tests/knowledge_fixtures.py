"""A synthetic knowledge base the knowledge and authoring tests share.

The root conftest keeps KNOWLEDGE_MODE disabled so every pre-existing test sees the
configured product unchanged. These tests switch the process-wide services to a temporary
knowledge base built from ``tests/fixtures/knowledge`` with the fake embedding provider and
the scripted authoring provider, and switch everything back afterwards.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.config import get_settings

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "knowledge"
KNOWLEDGE_ENV = {
    "KNOWLEDGE_MODE": "local_uat",
    "KNOWLEDGE_SOURCE_DIR": str(FIXTURES),
    "EMBEDDING_PROVIDER": "fake",
    "KNOWLEDGE_AI_PROVIDER": "scripted",
    "KNOWLEDGE_EXTERNAL_EMBEDDING_ALLOWED": "false",
    "KNOWLEDGE_EXTERNAL_LLM_ALLOWED": "false",
}
#: Prowide models compiled for the tests: one unbracketed Category 1 message, a message
#: whose sequences have no block codes, a Category 9 statement, and one with value-less
#: markers — the constructs the generic compiler had to learn — plus MT541, whose Prowide
#: evidence alone stays STRUCTURE_AVAILABLE (qualifiers need the guide).
PROWIDE_SUBSET = ("MT103", "MT101", "MT202", "MT940", "MT300", "MT104", "MT204", "MT935", "MT541")


def _rewire(settings_env: dict[str, str]) -> None:
    from app.ai_authoring.provider import authoring_provider
    from app.knowledge_base.preview import reload_preview
    from app.knowledge_base.service import knowledge_service
    from app.studio.catalogue import message_spec
    from app.studio.samples import available_variants, build_sample

    for key, value in settings_env.items():
        os.environ[key] = value
    get_settings.cache_clear()
    settings = get_settings()
    knowledge_service.reconfigure(settings)
    authoring_provider.__init__(settings)  # type: ignore[misc]
    reload_preview(settings)
    message_spec.cache_clear()
    build_sample.cache_clear()
    available_variants.cache_clear()


@pytest.fixture(scope="session")
def knowledge_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("knowledge")


@pytest.fixture(scope="session")
def knowledge_env(knowledge_root: Path) -> Iterator[dict[str, str]]:
    """The shared synthetic knowledge base, synced once per session."""
    env = {
        **KNOWLEDGE_ENV,
        "KNOWLEDGE_DB_PATH": str(knowledge_root / "knowledge.sqlite3"),
        "KNOWLEDGE_PACK_DIR": str(knowledge_root / "packs"),
        "KNOWLEDGE_SOURCE_CACHE_DIR": str(knowledge_root / "cache"),
    }
    previous = {key: os.environ.get(key) for key in env}
    _rewire(env)
    from app.knowledge_base.index import KnowledgeIndexer, SyncOptions
    from app.knowledge_base.service import knowledge_service

    indexer = KnowledgeIndexer(
        knowledge_service.settings, knowledge_service.database, knowledge_service.embeddings
    )
    indexer.sync(SyncOptions(prowide_filter=PROWIDE_SUBSET))
    _rewire({})
    yield env
    restore: dict[str, str] = {}
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            restore[key] = value
    _rewire(restore)


@pytest.fixture
def knowledge_client(knowledge_env: dict[str, str]):  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient

    from app.main import app

    del knowledge_env
    with TestClient(app) as client:
        yield client
