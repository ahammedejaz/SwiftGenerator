from __future__ import annotations

import base64
import json
import os
import statistics
import time
from collections.abc import Callable

os.environ["APP_ENV"] = "development"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["AI_PROVIDER"] = "disabled"
os.environ["REAL_DATA_MODE_ENABLED"] = "true"
os.environ["AUTH_MODE"] = "development"
os.environ["SESSION_HMAC_SECRET"] = "benchmark-session-secret-at-least-thirty-two"
os.environ["DATA_ENCRYPTION_KEY"] = base64.b64encode(b"B" * 32).decode()
os.environ["MOCK_UAT_CONNECTOR_ENABLED"] = "true"
os.environ["SUBMISSION_MODE"] = "uat"
os.environ["EXTERNAL_VALIDATION_REQUIRED_FOR_SUBMISSION"] = "false"

from fastapi.testclient import TestClient  # noqa: E402
from httpx import Response  # noqa: E402

from app.main import app  # noqa: E402


def _measure(operation: Callable[[], Response], iterations: int = 30) -> float:
    durations: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter()
        response = operation()
        elapsed = (time.perf_counter() - started) * 1_000
        if response.status_code >= 400:
            raise RuntimeError(f"Benchmark operation failed with HTTP {response.status_code}")
        durations.append(elapsed)
    return round(statistics.mean(durations), 3)


def _login(client: TestClient, identity: str) -> dict[str, str]:
    response = client.post("/api/auth/development-login", json={"identity": identity})
    response.raise_for_status()
    return {"X-CSRF-Token": client.cookies.get("swift_platform_csrf") or ""}


def main() -> int:
    with TestClient(app) as client:
        public = {
            "formSchemaLoadAverageMs": _measure(
                lambda: client.get("/api/specifications/messages/MT541")
            ),
            "tagSearchAverageMs": _measure(
                lambda: client.get("/api/knowledge/search", params={"q": "PSET"})
            ),
            "sampleLoadAverageMs": _measure(
                lambda: client.get("/api/knowledge/samples/MT541-SYNTHETIC-V1")
            ),
        }
        author_headers = _login(client, "author")
        loaded = client.post(
            "/api/knowledge/samples/MT541-SYNTHETIC-V1/load", headers=author_headers
        )
        loaded.raise_for_status()
        draft_id = loaded.json()["draftId"]
        authoring = {
            "compositionAverageMs": _measure(
                lambda: client.post(f"/api/messages/{draft_id}/compose", headers=author_headers),
                20,
            ),
            "validationAverageMs": _measure(
                lambda: client.post(f"/api/messages/{draft_id}/validate", headers=author_headers),
                20,
            ),
            "block4DownloadAverageMs": _measure(
                lambda: client.get(f"/api/messages/{draft_id}/downloads/block4"), 20
            ),
        }
        review = client.post(f"/api/messages/{draft_id}/review", headers=author_headers)
        review.raise_for_status()
        approver_headers = _login(client, "approver")
        client.post(
            f"/api/messages/{draft_id}/approve", headers=approver_headers
        ).raise_for_status()
        submitter_headers = _login(client, "submitter")
        started = time.perf_counter()
        submission = client.post(
            f"/api/messages/{draft_id}/submit",
            json={
                "connectorId": "MOCK-UAT",
                "idempotencyKey": "benchmark-idempotency-0001",
            },
            headers=submitter_headers,
        )
        submission.raise_for_status()
        connector_queue_ms = round((time.perf_counter() - started) * 1_000, 3)
    print(
        json.dumps(
            {
                "syntheticOnly": True,
                **public,
                **authoring,
                "mockConnectorQueueAverageMs": connector_queue_ms,
                "productionLoadTest": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
