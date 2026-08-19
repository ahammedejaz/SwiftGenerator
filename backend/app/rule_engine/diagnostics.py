"""Structured rule-engine findings. A stack trace is never the interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class RuleFindingCode(StrEnum):
    # -- source ingestion --------------------------------------------------------------
    SOURCE_UNREADABLE = "SOURCE_UNREADABLE"
    SOURCE_TOO_LARGE = "SOURCE_TOO_LARGE"
    SOURCE_HASH_MISMATCH = "SOURCE_HASH_MISMATCH"
    SOURCE_FORMAT_UNSUPPORTED = "SOURCE_FORMAT_UNSUPPORTED"
    SOURCE_EXTRACTION_UNUSABLE = "SOURCE_EXTRACTION_UNUSABLE"
    SOURCE_OUTSIDE_DROP_DIRECTORY = "SOURCE_OUTSIDE_DROP_DIRECTORY"
    SOURCE_REDISTRIBUTION_UNKNOWN = "SOURCE_REDISTRIBUTION_UNKNOWN"
    SOURCE_NOT_DECLARED = "SOURCE_NOT_DECLARED"

    # -- extraction --------------------------------------------------------------------
    RULE_EXTRACTION_FAILED = "RULE_EXTRACTION_FAILED"
    RULE_EXTRACTION_SCHEMA_INVALID = "RULE_EXTRACTION_SCHEMA_INVALID"
    RULE_EXTRACTION_DISAGREEMENT = "RULE_EXTRACTION_DISAGREEMENT"
    RULE_EXTRACTION_UNAVAILABLE = "RULE_EXTRACTION_UNAVAILABLE"

    # -- compilation -------------------------------------------------------------------
    RULE_PACK_ID_INVALID = "RULE_PACK_ID_INVALID"
    RULE_ID_DUPLICATE = "RULE_ID_DUPLICATE"
    RULE_MESSAGE_UNKNOWN = "RULE_MESSAGE_UNKNOWN"
    RULE_REFERENCE_INVALID = "RULE_REFERENCE_INVALID"
    RULE_OPERATOR_INVALID = "RULE_OPERATOR_INVALID"
    RULE_TYPE_MISMATCH = "RULE_TYPE_MISMATCH"
    RULE_CODE_UNKNOWN = "RULE_CODE_UNKNOWN"
    RULE_COUNT_NOT_REPEATABLE = "RULE_COUNT_NOT_REPEATABLE"
    RULE_REGEX_REJECTED = "RULE_REGEX_REJECTED"
    RULE_EVIDENCE_MISSING = "RULE_EVIDENCE_MISSING"
    RULE_EXECUTABLE_CONTENT_REJECTED = "RULE_EXECUTABLE_CONTENT_REJECTED"
    RULE_STRUCTURE_VERSION_MISMATCH = "RULE_STRUCTURE_VERSION_MISMATCH"
    RULE_REVIEW_REQUIRED = "RULE_REVIEW_REQUIRED"
    RULE_PROFILE_UNKNOWN = "RULE_PROFILE_UNKNOWN"

    # -- overlay analysis --------------------------------------------------------------
    RULE_OVERLAY_CONFLICT = "RULE_OVERLAY_CONFLICT"
    RULE_OVERLAY_WIDENING = "RULE_OVERLAY_WIDENING"
    RULE_OVERLAY_UNSATISFIABLE = "RULE_OVERLAY_UNSATISFIABLE"


class RuleSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass(frozen=True)
class RuleFinding:
    code: RuleFindingCode
    severity: RuleSeverity
    message: str
    suggestion: str
    #: The pack, source or candidate the finding is about — a name, never a server path.
    subject: str | None = None
    #: Rule id, field reference or segment id, where one applies.
    location: str | None = None
    #: Every rule involved, for findings about a relationship between two rules.
    related: tuple[str, ...] = ()

    def render(self) -> str:
        where = f" [{self.subject or ''}{' ' + self.location if self.location else ''}]".rstrip()
        where = "" if where == " []" else where
        related = f" (rules: {', '.join(self.related)})" if self.related else ""
        return f"{self.severity}: {self.code}{where} — {self.message} {self.suggestion}{related}"


@dataclass
class RuleFindingLog:
    findings: list[RuleFinding] = field(default_factory=list)

    def error(
        self,
        code: RuleFindingCode,
        message: str,
        suggestion: str,
        *,
        subject: str | None = None,
        location: str | None = None,
        related: tuple[str, ...] = (),
    ) -> None:
        self.findings.append(
            RuleFinding(code, RuleSeverity.ERROR, message, suggestion, subject, location, related)
        )

    def warning(
        self,
        code: RuleFindingCode,
        message: str,
        suggestion: str,
        *,
        subject: str | None = None,
        location: str | None = None,
        related: tuple[str, ...] = (),
    ) -> None:
        self.findings.append(
            RuleFinding(
                code, RuleSeverity.WARNING, message, suggestion, subject, location, related
            )
        )

    @property
    def errors(self) -> list[RuleFinding]:
        return [item for item in self.findings if item.severity is RuleSeverity.ERROR]

    @property
    def blocked(self) -> bool:
        return bool(self.errors)

    def extend(self, other: RuleFindingLog) -> None:
        self.findings.extend(other.findings)


class RuleEngineError(Exception):
    """Raised when a pack cannot be compiled or installed; carries the findings."""

    def __init__(self, findings: list[RuleFinding]) -> None:
        self.findings = findings
        super().__init__("; ".join(item.render() for item in findings) or "rule engine failure")
