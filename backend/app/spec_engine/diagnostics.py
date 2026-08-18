"""Structured compiler findings. A stack trace is never the interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class FindingCode(StrEnum):
    XSD_SOURCE_NOT_FOUND = "XSD_SOURCE_NOT_FOUND"
    XSD_SOURCE_TOO_LARGE = "XSD_SOURCE_TOO_LARGE"
    XSD_BUNDLE_TOO_LARGE = "XSD_BUNDLE_TOO_LARGE"
    XSD_NOT_WELL_FORMED = "XSD_NOT_WELL_FORMED"
    XSD_DOCTYPE_FORBIDDEN = "XSD_DOCTYPE_FORBIDDEN"
    XSD_REMOTE_FETCH_BLOCKED = "XSD_REMOTE_FETCH_BLOCKED"
    XSD_IMPORT_OUTSIDE_BUNDLE = "XSD_IMPORT_OUTSIDE_BUNDLE"
    XSD_IMPORT_NOT_FOUND = "XSD_IMPORT_NOT_FOUND"
    XSD_NAMESPACE_UNSUPPORTED = "XSD_NAMESPACE_UNSUPPORTED"
    XSD_NAMESPACE_CONFLICT = "XSD_NAMESPACE_CONFLICT"
    XSD_ROOT_AMBIGUOUS = "XSD_ROOT_AMBIGUOUS"
    XSD_ROOT_NOT_FOUND = "XSD_ROOT_NOT_FOUND"
    XSD_TYPE_UNRESOLVED = "XSD_TYPE_UNRESOLVED"
    XSD_RECURSION_LIMIT = "XSD_RECURSION_LIMIT"
    XSD_UNSUPPORTED_CONSTRUCT = "XSD_UNSUPPORTED_CONSTRUCT"
    XSD_OCCURRENCE_CAPPED = "XSD_OCCURRENCE_CAPPED"
    SAMPLE_VALUE_UNDERIVABLE = "SAMPLE_VALUE_UNDERIVABLE"
    PACK_ID_CONFLICT = "PACK_ID_CONFLICT"
    PACK_VALIDATION_FAILED = "PACK_VALIDATION_FAILED"


class FindingSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass(frozen=True)
class CompilerFinding:
    code: FindingCode
    severity: FindingSeverity
    message: str
    suggestion: str
    #: The source file the finding is about — a name within the bundle, never a server path.
    source: str | None = None
    #: Element path or line reference where one exists.
    location: str | None = None

    def render(self) -> str:
        where = f" [{self.source or ''}{' ' + self.location if self.location else ''}]".rstrip()
        where = where if where != " []" else ""
        return f"{self.severity}: {self.code}{where} — {self.message} {self.suggestion}"


@dataclass
class FindingLog:
    findings: list[CompilerFinding] = field(default_factory=list)

    def error(
        self,
        code: FindingCode,
        message: str,
        suggestion: str,
        *,
        source: str | None = None,
        location: str | None = None,
    ) -> None:
        self.findings.append(
            CompilerFinding(code, FindingSeverity.ERROR, message, suggestion, source, location)
        )

    def warning(
        self,
        code: FindingCode,
        message: str,
        suggestion: str,
        *,
        source: str | None = None,
        location: str | None = None,
    ) -> None:
        self.findings.append(
            CompilerFinding(code, FindingSeverity.WARNING, message, suggestion, source, location)
        )

    @property
    def errors(self) -> list[CompilerFinding]:
        return [item for item in self.findings if item.severity is FindingSeverity.ERROR]

    @property
    def blocked(self) -> bool:
        return bool(self.errors)


class CompilationError(Exception):
    """Raised when compilation cannot continue; carries the structured findings."""

    def __init__(self, findings: list[CompilerFinding]) -> None:
        self.findings = findings
        super().__init__("; ".join(item.render() for item in findings) or "compilation failed")
