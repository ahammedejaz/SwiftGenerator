"""What still works when the parts that can fail have failed.

The deterministic engine is the product; the model and the knowledge base are assistance.
An MVP that stops generating messages because an embedding endpoint returned 429, or
because the operator's knowledge database is not on this machine, would have the dependency
the architecture exists to avoid. Each case here breaks one thing and asserts the studio
still does its job — and says so in words a tester can act on, rather than a stack trace.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

CONFIGURED = [("MT", "MT541"), ("MT", "MT548"), ("MX", "sese.023.001.11")]


def _generate(client: TestClient, format_: str, message: str) -> dict:
    samples = client.get(f"/api/v1/messages/{message}/samples", params={"format": format_})
    assert samples.status_code == 200, samples.text
    variants = {item["variant"]: item for item in samples.json()}
    sample = variants.get("TYPICAL") or list(variants.values())[-1]
    body: dict[str, object] = {"format": format_, "messageType": message, "persist": False}
    if format_ == "MT":
        body["fields"] = [
            {"id": item["id"], "value": item["value"]} for item in sample["inputs"]
        ]
    else:
        body["elements"] = [
            {"path": item["path"], "occurrence": item.get("occurrence", 1), "value": item["value"]}
            for item in sample["elements"]
        ]
    response = client.post("/api/v1/messages/generate", json=body)
    assert response.status_code == 200, response.text
    return dict(response.json())


@pytest.mark.parametrize(("format_", "message"), CONFIGURED)
def test_generation_needs_no_model_and_no_knowledge_base(
    client: TestClient, format_: str, message: str
) -> None:
    """The ordinary suite already runs with ``AI_PROVIDER=disabled`` and no indexed corpus.

    Stating it as its own assertion is what makes the guarantee visible: this is the whole
    reason a tester can be given the product with no credential at all.
    """
    assert _generate(client, format_, message)["valid"] is True


def test_the_knowledge_status_endpoint_answers_whether_or_not_it_is_indexed(
    client: TestClient,
) -> None:
    """Whether an index exists depends on what else ran first, so assert the shape.

    An earlier version asserted ``indexed is False`` and passed alone but failed in the
    full run, because the session-scoped knowledge fixture had already synced the synthetic
    corpus. A test whose verdict depends on ordering says nothing about the product.
    """
    response = client.get("/api/v1/knowledge/status")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["indexed"], bool)
    # Not an error, and not silence: the page always has something true to render.
    assert payload["message"] or payload["mode"]


def test_knowledge_search_is_an_answer_and_never_a_crash(client: TestClient) -> None:
    response = client.post("/api/v1/knowledge/search", json={"query": "settlement"})

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["results"], list)
    if not payload["indexed"]:
        assert payload["results"] == []


def test_a_missing_knowledge_database_does_not_stop_the_studio(
    client: TestClient, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """The operator's database lives outside the repository and may simply not be here."""
    monkeypatch.setenv("KNOWLEDGE_DB_PATH", str(tmp_path / "absent" / "knowledge.sqlite3"))

    assert client.get("/api/v1/catalogue").status_code == 200
    assert _generate(client, "MT", "MT541")["valid"] is True
    assert client.get("/api/v1/knowledge/status").status_code == 200


def test_an_ai_operation_without_a_provider_answers_deterministically(
    client: TestClient,
) -> None:
    """``AI_PROVIDER=disabled`` is a supported configuration, not a broken one.

    Every AI operation computes a deterministic seed before it considers a model, so the
    answer with no provider is the seed — never an error the screen cannot render.
    """
    response = client.post(
        "/api/v1/ai/samples",
        json={"format": "MT", "messageType": "MT541", "sampleType": "TYPICAL"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["valid"] is True
    assert payload["inputs"], "a sample with no values is a dead screen"
    assert payload["synthetic"] is True


def test_an_ai_answer_without_a_provider_says_so_rather_than_inventing_one(
    client: TestClient,
) -> None:
    response = client.post("/api/v1/ai/ask", json={"question": "What is MT541?"})

    assert response.status_code == 200, response.text
    payload = response.json()
    # Whatever it answers, it never claims indexed evidence it does not have.
    assert payload["supported"] in {"SUPPORTED", "PARTIAL", "UNSUPPORTED_BY_EVIDENCE"}
    if payload["supported"] == "UNSUPPORTED_BY_EVIDENCE":
        assert not payload["citations"]


def test_an_embedding_failure_does_not_reach_a_deterministic_caller(
    client: TestClient, monkeypatch: MonkeyPatch
) -> None:
    """Retrieval is the only thing embeddings serve; generation must not notice."""
    from app.knowledge_base.service import knowledge_service

    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("embedding endpoint returned 429")

    monkeypatch.setattr(knowledge_service.embeddings, "embed", explode, raising=False)

    assert _generate(client, "MT", "MT541")["valid"] is True
    assert client.get("/api/v1/catalogue").status_code == 200
    assert client.post("/api/v1/messages/validate", json={
        "format": "MT", "messageType": "MT541", "fields": []
    }).status_code == 200


def test_every_error_is_an_envelope_and_never_a_stack_trace(client: TestClient) -> None:
    """A caller integrating against this needs a contract, not a traceback."""
    cases = [
        ("GET", "/api/v1/messages/MT999999/spec", None),
        ("POST", "/api/v1/messages/generate", {"format": "MT", "messageType": "NOPE"}),
        ("POST", "/api/v1/messages/import", {"text": "not a message"}),
        ("GET", "/api/v1/messages/id/00000000-0000-0000-0000-000000000000", None),
    ]
    for method, path, body in cases:
        response = (
            client.get(path) if method == "GET" else client.post(path, json=body)
        )
        assert response.status_code < 500, (path, response.status_code, response.text)
        payload = response.json()
        if response.status_code >= 400:
            assert "error" in payload, path
            assert payload["error"]["code"], path
            assert payload["error"]["message"], path
            assert "Traceback" not in response.text, path
