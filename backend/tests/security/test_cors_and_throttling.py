"""Every response the browser can receive must be readable by the browser.

These tests exist because of a real defect: the request-context middleware was registered
*outside* CORSMiddleware, so its short-circuit responses (400, 413, 429) reached the browser
with no Access-Control-Allow-Origin header. fetch() rejects such a response with a bare
network error, so a throttled tester was told "the backend is not running". The middleware
order is the entire fix, and nothing else in the suite would notice if it regressed.
"""

from __future__ import annotations

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app import main
from app.security.http import SlidingWindowRateLimiter

ORIGIN = "http://localhost:3000"


@pytest.fixture
def throttled(monkeypatch: pytest.MonkeyPatch):
    """An app whose general request budget is three per minute."""
    monkeypatch.setattr(main, "rate_limiter", SlidingWindowRateLimiter(3))
    with TestClient(main.app) as client:
        yield client


def test_cors_middleware_is_outermost() -> None:
    # Starlette inserts each registration at the front, so index 0 runs first.
    assert main.app.user_middleware[0].cls is CORSMiddleware


def test_throttled_response_is_readable_by_the_browser(throttled: TestClient) -> None:
    for _ in range(3):
        assert throttled.get("/api/v1/catalogue", headers={"Origin": ORIGIN}).status_code == 200

    limited = throttled.get("/api/v1/catalogue", headers={"Origin": ORIGIN})

    assert limited.status_code == 429
    # Without this header the browser discards the response and reports a network failure,
    # which is indistinguishable from the API being down.
    assert limited.headers["access-control-allow-origin"] == ORIGIN
    assert limited.headers["Retry-After"] == "60"
    assert limited.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"


def test_oversized_request_is_readable_by_the_browser(client: TestClient) -> None:
    response = client.post(
        "/api/v1/messages/generate",
        headers={"Origin": ORIGIN, "content-length": str(10**9)},
        content=b"{}",
    )

    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.json()["error"]["code"] == "REQUEST_TOO_LARGE"


def test_malformed_content_length_is_readable_by_the_browser(client: TestClient) -> None:
    response = client.post(
        "/api/v1/messages/generate",
        headers={"Origin": ORIGIN, "content-length": "-1"},
        content=b"{}",
    )

    assert response.status_code == 400
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.json()["error"]["code"] == "INVALID_CONTENT_LENGTH"


def test_cors_preflight_is_not_throttled(throttled: TestClient) -> None:
    """A preflight is browser overhead the caller never chose to send.

    Throttling it fails the real request that follows with an unexplainable CORS error,
    and it defends nothing: a non-browser client never sends a preflight at all.
    """
    preflight = {"Origin": ORIGIN, "Access-Control-Request-Method": "POST"}
    for _ in range(10):
        response = throttled.options("/api/v1/messages/generate", headers=preflight)
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == ORIGIN

    # The budget was untouched, so real requests still get through.
    assert throttled.get("/api/v1/catalogue", headers={"Origin": ORIGIN}).status_code == 200


def test_a_bare_options_request_still_counts(throttled: TestClient) -> None:
    """Only genuine preflights are exempt; an OPTIONS without the preflight headers is not."""
    for _ in range(3):
        throttled.options("/api/v1/catalogue")

    assert throttled.get("/api/v1/catalogue", headers={"Origin": ORIGIN}).status_code == 429


def test_both_spellings_of_the_local_origin_are_allowed(client: TestClient) -> None:
    """A tester who opened 127.0.0.1:3000 sends a different Origin from one who opened
    localhost:3000. Refusing either is unexplainable from the browser, which reports only a
    bare network error."""
    for origin in ("http://localhost:3000", "http://127.0.0.1:3000"):
        response = client.get("/api/v1/catalogue", headers={"Origin": origin})

        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == origin
