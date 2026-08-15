import logging
import re
from typing import Any

ACCOUNT_PATTERN = re.compile(r"(?i)(safekeeping(?:Account)?|account)(\s*[=:]\s*)([A-Z0-9_-]{4,})")
SECRET_PATTERN = re.compile(r"(?i)(api[_-]?key|authorization|token)(\s*[=:]\s*)([^\s,;]+)")
AUTHORIZATION_BEARER_PATTERN = re.compile(r"(?i)(authorization\s*[=:]?\s*bearer\s+)([^\s,;]+)")
RAW_MT_SIGNAL = re.compile(r"(?:\{2:(?:MT|I|O)?54[0-8]|:\d{2}[A-Z]?:)", re.IGNORECASE)
_safe_record_factory_installed = False


def redact_log_text(value: str) -> str:
    if RAW_MT_SIGNAL.search(value):
        return "***REDACTED_MT_CONTENT***"
    value = AUTHORIZATION_BEARER_PATTERN.sub(r"\1***REDACTED***", value)
    value = ACCOUNT_PATTERN.sub(r"\1\2***MASKED***", value)
    return SECRET_PATTERN.sub(r"\1\2***REDACTED***", value)


class RedactingLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        _redact_record(record)
        return True


def _redact_record(record: logging.LogRecord) -> None:
    # Uvicorn's access formatter consumes a five-item argument tuple after the
    # LogRecord is created. Replacing that tuple would break the formatter.
    # Access records contain only the peer address, method, path, protocol and
    # status; request headers and bodies are never included in this channel.
    if record.name == "uvicorn.access":
        return
    try:
        rendered = record.getMessage()
    except (TypeError, ValueError):
        rendered = str(record.msg)
    record.msg = redact_log_text(rendered)
    record.args = ()


def configure_safe_logging() -> None:
    global _safe_record_factory_installed
    root = logging.getLogger()
    if not any(isinstance(item, RedactingLogFilter) for item in root.filters):
        root.addFilter(RedactingLogFilter())
    for handler in root.handlers:
        if not any(isinstance(item, RedactingLogFilter) for item in handler.filters):
            handler.addFilter(RedactingLogFilter())
    if not _safe_record_factory_installed:
        original_factory = logging.getLogRecordFactory()

        def safe_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            record = original_factory(*args, **kwargs)
            _redact_record(record)
            return record

        logging.setLogRecordFactory(safe_factory)
        _safe_record_factory_installed = True
