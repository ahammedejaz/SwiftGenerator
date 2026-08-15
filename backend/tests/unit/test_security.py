import logging

from app.security.http import SlidingWindowRateLimiter
from app.security.logging import configure_safe_logging, redact_log_text


def test_rate_limiter_uses_a_sliding_window() -> None:
    limiter = SlidingWindowRateLimiter(2)

    assert limiter.allow("client", now=100) is True
    assert limiter.allow("client", now=101) is True
    assert limiter.allow("client", now=102) is False
    assert limiter.allow("client", now=161) is True


def test_sensitive_log_values_are_redacted() -> None:
    text = "safekeepingAccount=SYNTHSAFE01 api_key=not-a-real-key"

    redacted = redact_log_text(text)

    assert "SYNTHSAFE01" not in redacted
    assert "not-a-real-key" not in redacted
    assert "***MASKED***" in redacted
    assert "***REDACTED***" in redacted


def test_authorization_header_and_raw_message_are_never_logged() -> None:
    authorization = redact_log_text("Authorization: Bearer test-openrouter-secret")
    assert "test-openrouter-secret" not in authorization
    assert "***REDACTED***" in authorization

    raw = redact_log_text("provider response {2:MT541}{4:\n:20C::SEME//SENSITIVE\n-}")
    assert raw == "***REDACTED_MT_CONTENT***"
    assert "SENSITIVE" not in raw


def test_global_log_record_factory_redacts_child_logger_content(caplog) -> None:
    configure_safe_logging()
    logger = logging.getLogger("app.child.security-test")
    logger.warning("Authorization: Bearer %s", "runtime-secret-value")
    assert "runtime-secret-value" not in caplog.text
    assert "***REDACTED***" in caplog.text


def test_global_log_record_factory_preserves_uvicorn_access_arguments() -> None:
    configure_safe_logging()
    logger = logging.getLogger("uvicorn.access")
    record = logger.makeRecord(
        logger.name,
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:12345", "GET", "/api/health", "1.1", 200),
        None,
    )

    assert record.args == ("127.0.0.1:12345", "GET", "/api/health", "1.1", 200)
