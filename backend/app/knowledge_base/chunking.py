"""Segment a source into retrieval units that respect what the document is.

A Message Reference Guide is cut at rule, field-specification and page boundaries and every
segment knows its section; a schema summary is cut per type; a note is cut at headings. A
segment never crosses a page, a section, or — because a source carries one identity — two
messages. Ids and hashes are deterministic for unchanged bytes, so a rescan reuses them.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.knowledge_base import CHUNKER_VERSION
from app.knowledge_base.models import (
    Section,
    SegmentRecord,
    SourceFormat,
    SourceIdentity,
    SourceType,
    TableState,
)

MAX_SEGMENT_CHARS = 1_800
MIN_SEGMENT_CHARS = 40
PAGE_MARKER = re.compile(r"^\s*\[\[PAGE (\d+)\]\]\s*$")
RULE_START = re.compile(r"^C(\d{1,2})\s+\S")
FIELD_HEADING = re.compile(r"^\d{1,3}\. Field \d{2}[A-Za-z]?: ")
MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+\S")
NUMBERED_HEADING = re.compile(r"^\d+(\.\d+)*\.?\s+[A-Z][^.]{2,80}$")
CAPS_HEADING = re.compile(r"^[A-Z][A-Z0-9 ,/&'()-]{3,60}$")

TAG = re.compile(r"\b(\d{2}[A-Z])\b")
QUALIFIER = re.compile(r":([A-Z0-9]{4})//")
RULE_ID = re.compile(r"\b(C\d{1,2})\b")
ERROR_CODE = re.compile(r"\b([A-Z]\d{2})\b")
ISO_ELEMENT = re.compile(r"^- ([A-Za-z0-9]+) : ")
ISO_TYPE = re.compile(r"^## (?:Simple type|Type) ([A-Za-z0-9_]+)")
CODE_WORD = re.compile(r"\b([A-Z]{4})\b")

#: Section names the MRG reader produces, mapped onto the knowledge vocabulary.
_MRG_SECTION = {
    "MESSAGE_SCOPE": Section.SCOPE,
    "FORMAT_SPECIFICATION": Section.FORMAT_SPECIFICATION,
    "NETWORK_VALIDATED_RULE": Section.NETWORK_VALIDATED_RULE,
    "USAGE_RULE": Section.USAGE_RULE,
    "FIELD_SPECIFICATION": Section.FIELD_SPECIFICATION,
    "LEGAL_NOTICE": Section.LEGAL_NOTICE,
    "TABLE_OF_CONTENTS": Section.TABLE_OF_CONTENTS,
    "COVER": Section.COVER,
    "MESSAGE_TYPES": Section.OTHER,
    "DESCRIPTION_ONLY": Section.OTHER,
}


@dataclass
class _Block:
    lines: list[str]
    page: int | None
    section: Section
    heading: str | None

    @property
    def text(self) -> str:
        return "\n".join(self.lines).strip()


def segment_source(
    identity: SourceIdentity,
    text: str,
    *,
    partial_table_pages: frozenset[int] = frozenset(),
) -> list[SegmentRecord]:
    if identity.source_type is SourceType.MT_MESSAGE_REFERENCE_GUIDE and identity.message_type:
        blocks = _mrg_blocks(text, identity.message_type)
    elif identity.source_type is SourceType.ISO20022_XSD:
        blocks = _xsd_blocks(text)
    else:
        blocks = _generic_blocks(text)
    return _records(identity, blocks, partial_table_pages)


# -- block builders ------------------------------------------------------------------------


def _mrg_blocks(text: str, message_type: str) -> list[_Block]:
    from app.rule_engine.mt_mrg.document import classify, pages_of, section_of_line

    pages = pages_of(text)
    spans = classify(pages, message_type)
    blocks: list[_Block] = []
    current: _Block | None = None
    heading: str | None = None
    for page in pages:
        current = None  # never cross a page
        for line in page.lines:
            raw = line.text.rstrip()
            mrg_section = section_of_line(spans, line.number)
            section = _MRG_SECTION.get(mrg_section.value, Section.OTHER)
            stripped = raw.strip()
            starts_unit = bool(
                RULE_START.match(stripped)
                or FIELD_HEADING.match(stripped)
                or _is_section_heading(stripped)
            )
            if starts_unit:
                heading = stripped[:120]
            if (
                current is None
                or current.section is not section
                or starts_unit
                or (not stripped and len(current.text) >= MAX_SEGMENT_CHARS // 2)
                or len(current.text) + len(raw) > MAX_SEGMENT_CHARS
            ):
                if current is not None and current.text:
                    blocks.append(current)
                current = _Block([], page.number, section, heading)
            if stripped or current.lines:
                current.lines.append(raw)
        if current is not None and current.text:
            blocks.append(current)
    return blocks


def _is_section_heading(line: str) -> bool:
    return bool(
        re.match(
            r"^MT \d{3} (Scope|Format Specifications|Network Validated Rules|Usage Rules|"
            r"Field Specifications)$",
            line,
        )
    )


def _xsd_blocks(text: str) -> list[_Block]:
    blocks: list[_Block] = []
    current: _Block | None = None
    for raw in text.splitlines():
        if PAGE_MARKER.match(raw):
            continue
        if raw.startswith("## ") or current is None:
            if current is not None and current.text:
                blocks.append(current)
            heading = raw[3:].strip()[:120] if raw.startswith("## ") else raw.strip()[:120]
            current = _Block([], None, Section.ELEMENT_DEFINITION, heading or None)
            if not raw.startswith("## "):
                current.section = Section.MESSAGE_DEFINITION
        if len(current.text) + len(raw) > MAX_SEGMENT_CHARS:
            blocks.append(current)
            current = _Block([], None, current.section, current.heading)
        current.lines.append(raw)
    if current is not None and current.text:
        blocks.append(current)
    return blocks


def _generic_blocks(text: str) -> list[_Block]:
    blocks: list[_Block] = []
    current: _Block | None = None
    page: int | None = None
    heading: str | None = None
    section = Section.OTHER
    for raw in text.splitlines():
        marker = PAGE_MARKER.match(raw)
        if marker:
            if current is not None and current.text:
                blocks.append(current)
            current = None
            page = int(marker.group(1))
            continue
        stripped = raw.strip()
        is_heading = bool(
            MARKDOWN_HEADING.match(stripped)
            or NUMBERED_HEADING.match(stripped)
            or (CAPS_HEADING.match(stripped) and len(stripped.split()) <= 8)
        )
        if is_heading:
            heading = stripped.lstrip("#").strip()[:120]
            section = _section_from_heading(heading)
        if (
            current is None
            or is_heading
            or (not stripped and len(current.text) >= MAX_SEGMENT_CHARS // 2)
            or len(current.text) + len(raw) > MAX_SEGMENT_CHARS
        ):
            if current is not None and current.text:
                blocks.append(current)
            current = _Block([], page, section, heading)
        if stripped or current.lines:
            current.lines.append(raw)
    if current is not None and current.text:
        blocks.append(current)
    return blocks


def _section_from_heading(heading: str) -> Section:
    lowered = heading.lower()
    if "network validated" in lowered or lowered.startswith("rules"):
        return Section.NETWORK_VALIDATED_RULE
    if "usage" in lowered and "rule" in lowered:
        return Section.USAGE_RULE
    if "format" in lowered and "specification" in lowered:
        return Section.FORMAT_SPECIFICATION
    if "field" in lowered and "specification" in lowered:
        return Section.FIELD_SPECIFICATION
    if "scope" in lowered:
        return Section.SCOPE
    if "example" in lowered:
        return Section.EXAMPLE
    if "legal" in lowered or "copyright" in lowered:
        return Section.LEGAL_NOTICE
    if "business rule" in lowered:
        return Section.BUSINESS_RULES
    if "element" in lowered:
        return Section.ELEMENT_DEFINITION
    if "message definition" in lowered:
        return Section.MESSAGE_DEFINITION
    return Section.OTHER


# -- records ---------------------------------------------------------------------------------


def _records(
    identity: SourceIdentity, blocks: list[_Block], partial_pages: frozenset[int]
) -> list[SegmentRecord]:
    records: list[SegmentRecord] = []
    ordinal = 0
    for block in blocks:
        text = block.text
        if len(text) < MIN_SEGMENT_CHARS and block.section not in {
            Section.NETWORK_VALIDATED_RULE,
            Section.FORMAT_SPECIFICATION,
        }:
            # Tiny fragments (a lone page number, a running header) are noise for retrieval.
            continue
        ordinal += 1
        segment_hash = hashlib.sha256(
            f"{CHUNKER_VERSION}|{block.section.value}|{block.page}|{text}".encode()
        ).hexdigest()
        table_state = TableState.NONE
        if block.section is Section.FORMAT_SPECIFICATION:
            table_state = (
                TableState.TABLE_EXTRACTION_PARTIAL
                if block.page in partial_pages
                else TableState.TABLE_EXTRACTED
            )
        records.append(
            SegmentRecord(
                segment_id=f"{identity.source_id}#S{ordinal:04d}",
                source_id=identity.source_id,
                ordinal=ordinal,
                segment_hash=segment_hash,
                text_hash=hashlib.sha256(text.encode()).hexdigest(),
                section=block.section,
                page=block.page,
                heading=block.heading,
                identifiers=identifiers_in(text, identity.format),
                table_state=table_state,
                text=text,
                message_type=identity.message_type,
                message_version=identity.message_version,
                release=identity.release,
                format=identity.format,
            )
        )
    return records


def identifiers_in(text: str, format_: SourceFormat) -> tuple[str, ...]:
    """The exact tokens a tester types: tags, qualifiers, rule ids, error codes, element
    names, XPaths. Indexed in their own FTS column so they outrank prose."""
    found: list[str] = []
    if format_ is SourceFormat.MX:
        for line in text.splitlines():
            element = ISO_ELEMENT.match(line)
            if element:
                found.append(element.group(1))
            type_match = ISO_TYPE.match(line)
            if type_match:
                found.append(type_match.group(1))
        found.extend(match for match in re.findall(r"\b[a-z]{4}\.\d{3}(?:\.\d{3}\.\d{2})?\b", text))
    else:
        found.extend(TAG.findall(text))
        found.extend(f":{item}//" for item in QUALIFIER.findall(text))
        found.extend(QUALIFIER.findall(text))
        found.extend(RULE_ID.findall(text))
        found.extend(ERROR_CODE.findall(text))
        found.extend(CODE_WORD.findall(text))
        found.extend(re.findall(r"\bMT\d{3}\b", text))
    seen: dict[str, None] = {}
    for item in found:
        seen.setdefault(item, None)
    return tuple(list(seen)[:200])
