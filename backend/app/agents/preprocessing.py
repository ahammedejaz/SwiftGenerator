import re
import secrets
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field

from app.agents.errors import ai_error

PLACEHOLDER_PATTERN = re.compile(r"^\[\[SMS_(?P<kind>[A-Z_]+)_(?P<id>[A-F0-9]{8})\]\]$")
RAW_MT_INPUT_PATTERN = re.compile(r"(?:\{2:(?:MT|I|O)?54[0-8]|:\d{2}[A-Z]?:)", re.IGNORECASE)


@dataclass(frozen=True)
class PlaceholderValue:
    placeholder_id: str
    kind: str
    token: str
    original: str


@dataclass
class SanitizedInput:
    text: str
    placeholders: dict[str, PlaceholderValue] = field(default_factory=dict)
    injection_detected: bool = False

    def clear(self) -> None:
        self.placeholders.clear()


@dataclass(frozen=True)
class _Candidate:
    start: int
    end: int
    kind: str
    value: str


def _token(kind: str, identifier: str) -> str:
    return f"[[SMS_{kind}_{identifier}]]"


def sanitize_user_text(
    text: str,
    max_chars: int,
    *,
    id_factory: Callable[[], str] | None = None,
) -> SanitizedInput:
    if len(text) > max_chars:
        raise ai_error("AI_INPUT_TOO_LARGE", status=413)
    if RAW_MT_INPUT_PATTERN.search(text):
        raise ai_error("AI_RAW_CONTENT_NOT_ACCEPTED", status=400)
    if any(
        unicodedata.category(character) in {"Cc", "Cf"} and character not in {"\n", "\r", "\t"}
        for character in text
    ):
        raise ai_error("AI_UNSAFE_RESPONSE", status=400)

    normalized = " ".join(text.strip().split())
    if not normalized:
        raise ai_error("AI_UNSAFE_RESPONSE", status=400)
    identifiers = id_factory or (lambda: secrets.token_hex(4).upper())
    candidates: list[_Candidate] = []

    patterns: list[tuple[str, re.Pattern[str], int]] = [
        (
            "ISIN",
            re.compile(r"\b[A-Z]{2}[A-Z0-9]{9}[0-9]\b", re.IGNORECASE),
            0,
        ),
        (
            "SAFEKEEPING_ACCOUNT",
            re.compile(
                r"(?i)\b(?:safekeeping\s+account|account)\s*(?:number|id|is|:|=)?\s*"
                r"(?P<value>[A-Z0-9][A-Z0-9_-]{4,})"
            ),
            1,
        ),
        (
            "SENDER_REFERENCE",
            re.compile(
                r"(?i)\bsender\s+reference\s*(?:number|id|is|:|=)?\s*"
                r"(?P<value>[A-Z0-9][A-Z0-9_-]{4,})"
            ),
            1,
        ),
        (
            "CLIENT_REFERENCE",
            re.compile(
                r"(?i)\bclient\s+reference\s*(?:number|id|is|:|=)?\s*"
                r"(?P<value>[A-Z0-9][A-Z0-9_-]{4,})"
            ),
            1,
        ),
        (
            "RELATED_REFERENCE",
            re.compile(
                r"(?i)\b(?:related|original|instruction)\s+reference\s*"
                r"(?:number|id|is|:|=)?\s*(?P<value>[A-Z0-9][A-Z0-9_-]{4,})"
            ),
            1,
        ),
        (
            "BUSINESS_REFERENCE",
            re.compile(
                r"(?i)\b(?:transaction|business)\s+reference\s*"
                r"(?:number|id|is|:|=)?\s*(?P<value>[A-Z0-9][A-Z0-9_-]{4,})"
            ),
            1,
        ),
        (
            "RELATED_REFERENCE",
            re.compile(
                r"(?i)\b(?:message|instruction)\s+id\s*(?:is|:|=)?\s*"
                r"(?P<value>[A-Z0-9][A-Z0-9_-]{4,})"
            ),
            1,
        ),
        (
            "PARTY_ID",
            re.compile(
                r"(?i)\b(?:delivering|receiving|settlement|counterparty)\s+"
                r"(?:agent|party|place|identifier|bic)\s*(?:is|:|=)?\s*"
                r"(?P<value>[A-Z0-9][A-Z0-9_-]{5,})"
            ),
            1,
        ),
        (
            "PARTY_NAME",
            re.compile(
                r"(?i)\b(?:customer|counterparty|delivering party|receiving party)\s+"
                r"(?:is|named|:|=)?\s*"
                r"(?P<value>[A-Z][A-Za-z&.'-]+(?:\s+(?!against\b|free\b|dvp\b|"
                r"fop\b|for\b|on\b|with\b)[A-Z][A-Za-z&.'-]+){0,2})"
            ),
            1,
        ),
        (
            "BIC",
            re.compile(r"\b[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b"),
            0,
        ),
    ]
    for kind, pattern, group in patterns:
        for match in pattern.finditer(normalized):
            start, end = match.span(group) if group else match.span()
            candidates.append(_Candidate(start, end, kind, normalized[start:end]))

    selected: list[_Candidate] = []
    occupied: set[int] = set()
    for candidate in sorted(candidates, key=lambda item: (item.start, -(item.end - item.start))):
        span = set(range(candidate.start, candidate.end))
        if occupied.intersection(span):
            continue
        selected.append(candidate)
        occupied.update(span)

    placeholders: dict[str, PlaceholderValue] = {}
    sanitised = normalized
    for candidate in sorted(selected, key=lambda item: item.start, reverse=True):
        identifier = identifiers()
        token = _token(candidate.kind, identifier)
        placeholders[identifier] = PlaceholderValue(
            placeholder_id=identifier,
            kind=candidate.kind,
            token=token,
            original=candidate.value,
        )
        sanitised = sanitised[: candidate.start] + token + sanitised[candidate.end :]
    sanitised, injection_detected = _neutralise_prompt_injection(sanitised)
    return SanitizedInput(
        text=sanitised,
        placeholders=placeholders,
        injection_detected=injection_detected,
    )


def resolve_placeholder(
    token: str,
    placeholder_id: str | None,
    placeholders: dict[str, PlaceholderValue],
) -> PlaceholderValue:
    match = PLACEHOLDER_PATTERN.fullmatch(token)
    if not match or not placeholder_id or match.group("id") != placeholder_id:
        raise ai_error("AI_UNSAFE_RESPONSE")
    issued = placeholders.get(placeholder_id)
    if issued is None or issued.token != token or issued.kind != match.group("kind"):
        raise ai_error("AI_UNSAFE_RESPONSE")
    return issued


def _neutralise_prompt_injection(text: str) -> tuple[str, bool]:
    marker = "[UNTRUSTED_DIRECTIVE_REMOVED]"
    patterns = (
        re.compile(r"```.*?```", re.DOTALL),
        re.compile(r"(?i)\bmark this valid\b.*?:"),
        re.compile(r"(?i)\buse this hidden BIC\b.*?:"),
        re.compile(r"(?i)\bignore (?:the schema|all rules|all prior rules)\b[^.:;]*(?:[.:;]|$)"),
        re.compile(r"(?i)\breveal (?:your )?(?:system|hidden)[^.:;]*(?:[.:;]|$)"),
        re.compile(r"(?i)\bcall (?:the )?message-generation tool\b[^.:;]*(?:[.:;]|$)"),
        re.compile(r"(?i)\bdo not use JSON\b[.]?"),
    )
    result = text
    detected = False
    for pattern in patterns:
        result, count = pattern.subn(marker, result)
        detected = detected or count > 0
    return " ".join(result.split()), detected
