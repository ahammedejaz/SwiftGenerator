"""Read a source's bytes and decide what it is — from its content, never its name.

Outputs a :class:`ParsedSource`: page-marked text (``[[PAGE n]]`` lines, the same marker the
MRG reader uses), the identity, and the classification that drives the privacy policy.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from app.knowledge_base.discovery import DiscoveredFile
from app.knowledge_base.models import (
    DocumentType,
    SourceClassification,
    SourceFormat,
    SourceIdentity,
    SourceType,
)

PARSER_VERSION = "knowledge-parser/1"
MIN_PDF_CHARS_PER_PAGE = 50
ISO_MESSAGE_ID = re.compile(r"\b([a-z]{4})\.(\d{3})\.(\d{3})\.(\d{2})\b")
ISO_LOGICAL_ID = re.compile(r"\b([a-z]{4})\.(\d{3})\b")
MT_ID = re.compile(r"\bMT\s?(\d{3})\b")
SR_ID = re.compile(r"\bSR\s?(20\d{2})\b")
#: A synthetic fixture declares itself in its own body. Content-based, like every identity.
SYNTHETIC_DECLARATION = re.compile(
    r"KNOWLEDGE-SOURCE-CLASSIFICATION:\s*SYNTHETIC_FIXTURE", re.IGNORECASE
)
ISO_NAMESPACE = re.compile(r"urn:iso:std:iso:20022:tech:xsd:([a-z]{4}\.\d{3}\.\d{3}\.\d{2})")


@dataclass
class ParsedSource:
    text: str
    page_count: int | None
    identity: SourceIdentity
    classification: SourceClassification
    failure_code: str | None = None
    failure_detail: str | None = None


class SourceUnreadable(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def parse_and_identify(item: DiscoveredFile, raw: bytes) -> ParsedSource:
    if item.suffix == ".pdf":
        text, pages = _pdf_text(raw, item.relative_path)
        return _identify_text(text, pages, item)
    if item.suffix in {".xsd", ".xml"}:
        return _identify_xml(raw, item)
    if item.suffix in {".html", ".htm"}:
        text = _html_text(_decode(raw))
        return _identify_text(_paginate(text), None, item, html=True)
    text = _decode(raw)
    return _identify_text(_paginate(text), None, item)


# -- PDF ---------------------------------------------------------------------------------


def _pdf_text(raw: bytes, name: str) -> tuple[str, int]:
    try:
        from pypdf import PdfReader
    except ImportError as error:  # pragma: no cover - environment dependent
        raise SourceUnreadable(
            "KNOWLEDGE_SOURCE_UNSUPPORTED",
            "Reading a PDF needs the optional pypdf package (backend/.venv/bin/pip install pypdf).",
        ) from error
    import io

    try:
        reader = PdfReader(io.BytesIO(raw), strict=False)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as error:  # noqa: BLE001 - reported as unreadable
                raise SourceUnreadable("KNOWLEDGE_SOURCE_UNREADABLE", "encrypted PDF") from error
        pages = [page.extract_text() or "" for page in reader.pages]
    except SourceUnreadable:
        raise
    except Exception as error:  # noqa: BLE001 - any parser failure is one named outcome
        raise SourceUnreadable(
            "KNOWLEDGE_SOURCE_UNREADABLE", f"{type(error).__name__} while reading {name}"
        ) from error
    if not pages:
        raise SourceUnreadable("KNOWLEDGE_SOURCE_UNREADABLE", "the PDF has no pages")
    total = sum(len(page.strip()) for page in pages)
    if total / len(pages) < MIN_PDF_CHARS_PER_PAGE:
        raise SourceUnreadable(
            "KNOWLEDGE_SOURCE_UNSUPPORTED",
            "the PDF carries no usable text layer (scanned image?)",
        )
    marked = "\n".join(f"[[PAGE {index}]]\n{page}" for index, page in enumerate(pages, start=1))
    return marked, len(pages)


# -- text-like -----------------------------------------------------------------------------


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _paginate(text: str) -> str:
    """Text files have no pages; one synthetic page keeps the reader uniform unless the
    document already carries page markers (synthetic fixtures do)."""
    if re.search(r"^\s*\[\[PAGE \d+\]\]\s*$", text, re.MULTILINE):
        return text
    return f"[[PAGE 1]]\n{text}"


class _HtmlToText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip += 1
        if tag in {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip:
            self._skip -= 1
        if tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")
        if tag in {"td", "th"}:
            self.parts.append("\t")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def _html_text(markup: str) -> str:
    parser = _HtmlToText()
    parser.feed(markup)
    return re.sub(r"\n{3,}", "\n\n", "".join(parser.parts))


# -- identity ------------------------------------------------------------------------------


def _identify_text(
    text: str, pages: int | None, item: DiscoveredFile, *, html: bool = False
) -> ParsedSource:
    synthetic = bool(SYNTHETIC_DECLARATION.search(text[:4000]))
    mrg = _identify_mrg(text)
    if mrg is not None:
        identity, page_count = mrg
        classification = (
            SourceClassification.SYNTHETIC_FIXTURE
            if synthetic
            else SourceClassification.OFFICIAL_SWIFT_MT_STANDARDS_MATERIAL
        )
        return ParsedSource(text, pages or page_count, identity, classification)

    head = _head(text)
    mt_counts = Counter(f"MT{match}" for match in MT_ID.findall(head))
    mx_counts = Counter(".".join(match) for match in ISO_MESSAGE_ID.findall(head))
    logical_counts = Counter(
        f"{family}.{number}" for family, number in ISO_LOGICAL_ID.findall(head)
    )
    releases = Counter(f"SR{year}" for year in SR_ID.findall(head))
    release = releases.most_common(1)[0][0] if releases else None
    problems: list[str] = []
    classification = (
        SourceClassification.SYNTHETIC_FIXTURE
        if synthetic
        else SourceClassification.OPERATOR_SUPPLIED_DOCUMENT
    )
    source_type = SourceType.HTML_DOCUMENT if html else SourceType.TEXT_NOTE
    title = _first_heading(text)

    mt_best = _dominant(mt_counts)
    mx_best = _dominant(mx_counts)
    if mt_best and not mx_best:
        return ParsedSource(
            text,
            pages,
            SourceIdentity(
                source_id=_note_id("MT", mt_best, release, item),
                source_type=SourceType.MT_DOCUMENT,
                format=SourceFormat.MT,
                document_type=DocumentType.USAGE_GUIDE,
                message_type=mt_best,
                release=release,
                title=title,
            ),
            classification,
        )
    if mx_best and not mt_best:
        logical = ".".join(mx_best.split(".")[:2])
        return ParsedSource(
            text,
            pages,
            SourceIdentity(
                source_id=_note_id("MX", mx_best, None, item),
                source_type=SourceType.ISO20022_DOCUMENT,
                format=SourceFormat.MX,
                document_type=DocumentType.USAGE_GUIDE,
                message_type=logical,
                message_version=mx_best,
                title=title,
            ),
            classification,
        )
    logical_best = _dominant(logical_counts) if not mt_best and not mx_best else None
    if logical_best:
        return ParsedSource(
            text,
            pages,
            SourceIdentity(
                source_id=_note_id("MX", logical_best, None, item),
                source_type=SourceType.ISO20022_DOCUMENT,
                format=SourceFormat.MX,
                document_type=DocumentType.USAGE_GUIDE,
                message_type=logical_best,
                title=title,
                problems=("MESSAGE_VERSION_NOT_STATED",),
            ),
            classification,
        )
    if mt_best and mx_best:
        problems.append("KNOWLEDGE_IDENTITY_AMBIGUOUS")
    elif mt_counts or mx_counts:
        problems.append("KNOWLEDGE_IDENTITY_AMBIGUOUS")
    return ParsedSource(
        text,
        pages,
        SourceIdentity(
            source_id=_note_id(None, None, None, item),
            source_type=source_type,
            format=SourceFormat.UNKNOWN,
            document_type=DocumentType.NOTE if not problems else DocumentType.UNKNOWN,
            title=title,
            problems=tuple(problems),
        ),
        classification,
    )


def _identify_mrg(text: str) -> tuple[SourceIdentity, int] | None:
    from app.rule_engine.mt_mrg.document import identify, pages_of

    pages = pages_of(text)
    identity, problems = identify(pages)
    if identity is None:
        del problems
        return None
    return (
        SourceIdentity(
            source_id=identity.logical_source_id,
            source_type=SourceType.MT_MESSAGE_REFERENCE_GUIDE,
            format=SourceFormat.MT,
            document_type=DocumentType.MRG,
            message_type=identity.message_type,
            release=identity.standards_release,
            publisher="SWIFT / MyStandards",
            title=f"{identity.message_type} {identity.message_name} "
            f"{identity.standards_release} Message Reference Guide",
        ),
        identity.page_count,
    )


def _identify_xml(raw: bytes, item: DiscoveredFile) -> ParsedSource:
    from lxml import etree

    parser = etree.XMLParser(
        resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False
    )
    try:
        root = etree.fromstring(raw, parser)
    except etree.XMLSyntaxError as error:
        raise SourceUnreadable("KNOWLEDGE_SOURCE_UNREADABLE", "not well-formed XML") from error
    if raw.lstrip().startswith(b"<!DOCTYPE") or b"<!DOCTYPE" in raw[:2048]:
        raise SourceUnreadable("KNOWLEDGE_SOURCE_UNSUPPORTED", "DOCTYPE is refused")
    tag = etree.QName(root).localname
    namespace = etree.QName(root).namespace or ""
    text = _decode(raw)
    synthetic = bool(SYNTHETIC_DECLARATION.search(text[:4000]))
    xsd_classification = (
        SourceClassification.SYNTHETIC_FIXTURE
        if synthetic
        else SourceClassification.OPERATOR_SUPPLIED_XSD
    )
    if tag == "schema" and namespace == "http://www.w3.org/2001/XMLSchema":
        target = root.get("targetNamespace") or ""
        match = ISO_NAMESPACE.search(target)
        if match is None:
            return ParsedSource(
                _paginate(text),
                None,
                SourceIdentity(
                    source_id=_note_id("XSD", None, None, item),
                    source_type=SourceType.ISO20022_XSD,
                    format=SourceFormat.UNKNOWN,
                    document_type=DocumentType.XSD,
                    title=target or item.relative_path.rsplit("/", 1)[-1],
                    problems=("STRUCTURE_SOURCE_UNSUPPORTED",),
                ),
                xsd_classification,
            )
        version = match.group(1)
        return ParsedSource(
            _paginate(_xsd_summary_text(root, version)),
            None,
            SourceIdentity(
                source_id=f"ISO20022-XSD-{version}",
                source_type=SourceType.ISO20022_XSD,
                format=SourceFormat.MX,
                document_type=DocumentType.XSD,
                message_type=".".join(version.split(".")[:2]),
                message_version=version,
                publisher="ISO 20022 (operator-supplied schema)",
                title=f"{version} XSD",
            ),
            xsd_classification,
        )
    match = ISO_NAMESPACE.search(namespace)
    if match is not None:
        version = match.group(1)
        return ParsedSource(
            _paginate(text),
            None,
            SourceIdentity(
                source_id=f"ISO20022-INSTANCE-{version}-{item.relative_path.rsplit('/', 1)[-1]}",
                source_type=SourceType.ISO20022_DOCUMENT,
                format=SourceFormat.MX,
                document_type=DocumentType.NOTE,
                message_type=".".join(version.split(".")[:2]),
                message_version=version,
                title=f"{version} instance document",
            ),
            SourceClassification.OPERATOR_SUPPLIED_DOCUMENT,
        )
    raise SourceUnreadable(
        "KNOWLEDGE_SOURCE_UNSUPPORTED", "XML that is neither a schema nor an ISO 20022 document"
    )


def _xsd_summary_text(root: object, version: str) -> str:
    """A readable rendering of a schema for lexical search: one line per element and type,
    with documentation annotations. The schema itself stays the structural authority."""
    from lxml import etree

    assert isinstance(root, etree._Element)
    xs = "{http://www.w3.org/2001/XMLSchema}"
    lines = [f"ISO 20022 message definition {version}", ""]
    for complex_type in root.iter(f"{xs}complexType"):
        name = complex_type.get("name")
        if not name:
            continue
        lines.append(f"## Type {name}")
        doc = complex_type.find(f"{xs}annotation/{xs}documentation")
        if doc is not None and doc.text:
            lines.append(" ".join(doc.text.split()))
        for element in complex_type.iter(f"{xs}element"):
            element_name = element.get("name") or element.get("ref") or ""
            element_type = element.get("type") or ""
            minimum = element.get("minOccurs", "1")
            maximum = element.get("maxOccurs", "1")
            lines.append(f"- {element_name} : {element_type} [{minimum}..{maximum}]")
    for simple_type in root.iter(f"{xs}simpleType"):
        name = simple_type.get("name")
        if not name:
            continue
        codes = [
            value
            for value in (item.get("value") for item in simple_type.iter(f"{xs}enumeration"))
            if value
        ]
        restriction = simple_type.find(f"{xs}restriction")
        base = restriction.get("base", "") if restriction is not None else ""
        pattern_node = simple_type.find(f"{xs}restriction/{xs}pattern")
        pattern = pattern_node.get("value", "") if pattern_node is not None else ""
        line = f"## Simple type {name} base {base}"
        if pattern:
            line += f" pattern {pattern}"
        lines.append(line)
        if codes:
            lines.append("codes: " + " ".join(codes))
    return "\n".join(lines)


# -- helpers -------------------------------------------------------------------------------


def _head(text: str, pages: int = 3, chars: int = 12_000) -> str:
    parts = re.split(r"^\s*\[\[PAGE \d+\]\]\s*$", text, flags=re.MULTILINE)
    return "\n".join(parts[: pages + 1])[:chars]


def _dominant(counts: Counter[str]) -> str | None:
    """The single identifier that clearly dominates, or None when two compete."""
    if not counts:
        return None
    ranked = counts.most_common(2)
    if len(ranked) == 1:
        return ranked[0][0]
    (first, first_n), (_second, second_n) = ranked
    return first if first_n >= 2 * max(second_n, 1) and first_n >= 2 else None


def _first_heading(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped and not stripped.startswith("[[PAGE"):
            return stripped[:120]
    return None


def _note_id(
    format_: str | None, message: str | None, release: str | None, item: DiscoveredFile
) -> str:
    import hashlib

    stem = hashlib.sha256(item.relative_path.encode()).hexdigest()[:10]
    if format_ and message:
        return f"{format_}-DOC-{message}{'-' + release if release else ''}-{stem}"
    return f"UNIDENTIFIED-{stem}"


def read_bytes(path: Path) -> bytes:
    return path.read_bytes()
