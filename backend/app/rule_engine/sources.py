"""Business-rule source documents: declaring them, reading them safely, segmenting them.

A source document is untrusted input twice over — it may be malformed, and its *content*
may try to instruct the model that later reads it. This module deals with the first
problem; ``extraction/prompts.py`` deals with the second.

Segmentation is deterministic and LLM-free. The same unchanged bytes always produce the
same segment identities, because a rule's evidence has to point at something that will
still be there tomorrow.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

import yaml
from pydantic import Field, ValidationError, model_validator

from app.config import get_settings, source_path
from app.rule_engine.diagnostics import (
    RuleEngineError,
    RuleFindingCode,
    RuleFindingLog,
)
from app.rule_engine.models import (
    SOURCE_ID_PATTERN,
    Evidence,
    RuleSourceType,
    SourceReference,
)
from app.rule_engine.refs import RuleModel

#: A guideline document that does not fit in 4 MB is not a guideline document.
MAX_SOURCE_BYTES = 4 * 1024 * 1024
#: Roughly the size of a long section — enough context for one rule, small enough that a
#: reviewer can read the evidence behind a candidate in a few seconds.
MAX_SEGMENT_CHARS = 2_000
#: Below this, a "text" extraction is almost certainly a scan or a broken decode.
MIN_ALPHABETIC_CHARACTERS = 20
#: Share of unprintable characters above which an extraction is treated as garbled.
MAX_UNPRINTABLE_RATIO = 0.02
#: Characters of text per page below which a PDF is treated as image-only.
MIN_PDF_CHARS_PER_PAGE = 50

ATX_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$")
SETEXT_UNDERLINE = re.compile(r"^(=|-){3,}$")
NUMBERED_HEADING = re.compile(r"^\d+(\.\d+)*[.)]?\s+[A-Z][^.]{0,110}$")
PAGE_MARKER = re.compile(r"^\s*\[\[PAGE (\d+)\]\]\s*$")


class SourceAdapter(StrEnum):
    TEXT = "TEXT"
    MARKDOWN = "MARKDOWN"
    HTML = "HTML"
    PDF_TEXT = "PDF_TEXT"


ADAPTER_BY_SUFFIX: dict[str, SourceAdapter] = {
    ".txt": SourceAdapter.TEXT,
    ".text": SourceAdapter.TEXT,
    ".md": SourceAdapter.MARKDOWN,
    ".markdown": SourceAdapter.MARKDOWN,
    ".html": SourceAdapter.HTML,
    ".htm": SourceAdapter.HTML,
    ".pdf": SourceAdapter.PDF_TEXT,
}


class Redistribution(RuleModel):
    """What the operator says may leave their premises. The tool makes no legal judgement.

    Both default to ``False``: a source whose licence has not been considered is treated as
    one that may not be redistributed, so silence never becomes permission.
    """

    source_may_be_committed: bool = Field(default=False, alias="sourceMayBeCommitted")
    excerpts_may_be_committed: bool = Field(default=False, alias="excerptsMayBeCommitted")


class SourceBundle(RuleModel):
    """One declared document of business-rule evidence."""

    source_id: str = Field(alias="sourceId", max_length=64)
    source_type: RuleSourceType = Field(alias="sourceType")
    title: str = Field(min_length=4, max_length=200)
    version: str = Field(max_length=64)
    source_location: str = Field(alias="sourceLocation", max_length=200)
    adapter: SourceAdapter | None = None
    redistribution: Redistribution = Redistribution()
    #: Recorded at ingestion. Declaring it up front lets a later ingest prove the bytes
    #: have not changed underneath the rules derived from them.
    source_checksum: str | None = Field(default=None, alias="sourceChecksum")
    standards_release: str | None = Field(default=None, alias="standardsRelease")
    applicable_message_categories: tuple[int, ...] = Field(
        default=(), alias="applicableMessageCategories"
    )
    message_identifiers: tuple[str, ...] = Field(default=(), alias="messageIdentifiers")
    source_allows_external_model_processing: bool | None = Field(
        default=None, alias="sourceAllowsExternalModelProcessing"
    )
    provider_approved_for_source_classification: bool | None = Field(
        default=None, alias="providerApprovedForSourceClassification"
    )
    market_identifier: str | None = Field(default=None, alias="marketIdentifier", max_length=64)
    client_identifier: str | None = Field(default=None, alias="clientIdentifier", max_length=64)

    @model_validator(mode="after")
    def check_identity(self) -> SourceBundle:
        if not SOURCE_ID_PATTERN.fullmatch(self.source_id):
            raise ValueError(
                f"{self.source_id} is not a source id: use upper-case words joined by hyphens"
            )
        if "/" in self.source_location or "\\" in self.source_location:
            raise ValueError("sourceLocation is a file name inside the drop directory")
        if self.source_location in {".", ".."}:
            raise ValueError("sourceLocation is a file name")
        if any(item < 0 or item > 9 for item in self.applicable_message_categories):
            raise ValueError("MT message categories must be digits 0 through 9")
        return self

    def resolved_adapter(self) -> SourceAdapter | None:
        if self.adapter is not None:
            return self.adapter
        return ADAPTER_BY_SUFFIX.get(Path(self.source_location).suffix.lower())

    def external_model_processing_allowed(self) -> bool:
        """Whether source text may be sent to an extraction model.

        Synthetic fixtures are repository-owned. Anything else needs two explicit
        operator declarations: the source permits external model processing, and the
        configured provider is approved for that source class. Unknown is blocked.
        """
        if self.source_type is RuleSourceType.SYNTHETIC_FIXTURE:
            return True
        return (
            self.source_allows_external_model_processing is True
            and self.provider_approved_for_source_classification is True
        )


@dataclass(frozen=True)
class SourceLine:
    number: int
    text: str
    page: int | None


@dataclass(frozen=True)
class Segment:
    """One addressable piece of a source document."""

    source_id: str
    segment_id: str
    ordinal: int
    text: str
    segment_hash: str
    heading: str | None
    page: int | None
    line_start: int
    line_end: int

    def excerpt(self, limit: int) -> str:
        return self.text if len(self.text) <= limit else self.text[: limit - 1].rstrip() + "…"

    def excerpt_hash(self, limit: int) -> str:
        return sha256_of(self.excerpt(limit))

    def evidence(self, bundle: SourceBundle, *, excerpt_limit: int) -> Evidence:
        """The evidence record a rule derived from this segment must carry."""
        return Evidence(
            source_id=bundle.source_id,
            segment_id=self.segment_id,
            source_location=bundle.source_location,
            source_version=bundle.version,
            source_checksum=bundle.source_checksum or sha256_of(""),
            segment_hash=self.segment_hash,
            excerpt_hash=self.excerpt_hash(excerpt_limit),
            excerpt=(
                self.excerpt(excerpt_limit)
                if bundle.redistribution.excerpts_may_be_committed
                else None
            ),
            heading=self.heading,
            page=self.page,
            line_start=self.line_start,
            line_end=self.line_end,
        )


@dataclass(frozen=True)
class IngestedSource:
    bundle: SourceBundle
    checksum: str
    adapter: SourceAdapter
    segments: tuple[Segment, ...]
    #: Pages the document turned out to have; 0 for formats without pages.
    page_count: int

    def reference(self) -> SourceReference:
        return SourceReference(
            source_id=self.bundle.source_id,
            source_type=self.bundle.source_type,
            title=self.bundle.title,
            version=self.bundle.version,
            source_location=self.bundle.source_location,
            source_checksum=self.checksum,
            excerpts_may_be_committed=(
                self.bundle.redistribution.excerpts_may_be_committed
            ),
            standards_release=self.bundle.standards_release,
            applicable_message_categories=self.bundle.applicable_message_categories,
            message_identifiers=self.bundle.message_identifiers,
            source_allows_external_model_processing=(
                self.bundle.source_allows_external_model_processing
            ),
            provider_approved_for_source_classification=(
                self.bundle.provider_approved_for_source_classification
            ),
        )


def sha256_of(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------------------
# Reading — every dangerous thing refused with a named finding
# --------------------------------------------------------------------------------------


def resolve_within(directory: Path, name: str, log: RuleFindingLog) -> Path | None:
    """A file inside the drop directory, symlinks included. Nothing else, ever."""
    root = directory.resolve()
    candidate = (root / name).resolve()
    if not candidate.is_relative_to(root):
        log.error(
            RuleFindingCode.SOURCE_OUTSIDE_DROP_DIRECTORY,
            f"{name} resolves outside the source directory.",
            "Keep every source document inside the configured drop directory.",
            subject=name,
        )
        return None
    if candidate.is_symlink() and not candidate.resolve().is_relative_to(root):
        log.error(
            RuleFindingCode.SOURCE_OUTSIDE_DROP_DIRECTORY,
            f"{name} is a link that leaves the source directory.",
            "Copy the real file into the directory instead of linking it.",
            subject=name,
        )
        return None
    if not candidate.is_file():
        log.error(
            RuleFindingCode.SOURCE_UNREADABLE,
            f"{name} is not a file in the source directory.",
            "Check the sourceLocation recorded in the manifest.",
            subject=name,
        )
        return None
    return candidate


def _read_bytes(path: Path, log: RuleFindingLog) -> bytes | None:
    try:
        size = path.stat().st_size
    except OSError:
        log.error(
            RuleFindingCode.SOURCE_UNREADABLE,
            f"{path.name} cannot be read.",
            "Check the file exists and is readable.",
            subject=path.name,
        )
        return None
    if size > MAX_SOURCE_BYTES:
        log.error(
            RuleFindingCode.SOURCE_TOO_LARGE,
            f"{path.name} is {size} bytes; the limit is {MAX_SOURCE_BYTES}.",
            "Split the document, or extract the relevant sections.",
            subject=path.name,
        )
        return None
    try:
        return path.read_bytes()
    except OSError:
        log.error(
            RuleFindingCode.SOURCE_UNREADABLE,
            f"{path.name} cannot be read.",
            "Check the file permissions.",
            subject=path.name,
        )
        return None


def _decode(raw: bytes, name: str, log: RuleFindingLog) -> str | None:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        log.error(
            RuleFindingCode.SOURCE_UNREADABLE,
            f"{name} is not UTF-8 text.",
            "Convert the document to UTF-8 before ingesting it.",
            subject=name,
        )
        return None


def _html_to_text(raw: bytes, name: str, log: RuleFindingLog) -> str | None:
    from lxml import etree, html
    from lxml.html import HtmlElement

    parser = html.HTMLParser(no_network=True, remove_comments=True, remove_pis=True)
    try:
        tree = html.document_fromstring(raw, parser=parser)
    except (etree.ParserError, etree.XMLSyntaxError, ValueError):
        log.error(
            RuleFindingCode.SOURCE_UNREADABLE,
            f"{name} could not be parsed as HTML.",
            "Save the page as text, or correct the markup.",
            subject=name,
        )
        return None
    for noise in list(tree.iter("script", "style", "noscript", "template")):
        parent = noise.getparent()
        if parent is not None:
            parent.remove(noise)
    blocks: list[str] = []
    carriers = ("p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td", "div")
    for element in tree.iter(*carriers):
        text = " ".join((cast("HtmlElement", element).text_content() or "").split())
        if text:
            blocks.append(text)
    # De-duplicate the nesting artefact where a div repeats its children's text.
    seen: set[str] = set()
    ordered: list[str] = []
    for block in blocks:
        if block in seen:
            continue
        seen.add(block)
        ordered.append(block)
    return "\n\n".join(ordered)


def _pdf_to_text(raw: bytes, name: str, log: RuleFindingLog) -> tuple[str, int] | None:
    """Text-layer extraction only. No OCR, and no dependency the platform does not have.

    ``pypdf`` is deliberately *not* a requirement of this repository: a PDF parser is a
    real attack surface, and every licensed document that would justify it is one CI can
    never see. The adapter exists so an operator who has installed it can use it, and says
    so plainly when they have not.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        log.error(
            RuleFindingCode.SOURCE_FORMAT_UNSUPPORTED,
            f"{name} is a PDF and no text extractor is installed.",
            "Convert it first — `pdftotext -layout document.pdf document.txt` — and ingest "
            "the text, which you can also checksum and read. Installing `pypdf` enables "
            "this adapter directly.",
            subject=name,
        )
        return None
    import io

    try:
        reader = PdfReader(io.BytesIO(raw))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception:  # noqa: BLE001 - any parser failure is one unusable-source outcome
        log.error(
            RuleFindingCode.SOURCE_UNREADABLE,
            f"{name} could not be read as a PDF.",
            "Check the file is a text-based PDF, or convert it with `pdftotext -layout`.",
            subject=name,
        )
        return None
    if not pages:
        log.error(
            RuleFindingCode.SOURCE_EXTRACTION_UNUSABLE,
            f"{name} has no pages.",
            "Check the document.",
            subject=name,
        )
        return None
    total = sum(len(page.strip()) for page in pages)
    if total / len(pages) < MIN_PDF_CHARS_PER_PAGE:
        log.error(
            RuleFindingCode.SOURCE_EXTRACTION_UNUSABLE,
            f"{name} yields {total} characters across {len(pages)} page(s), which reads as "
            "a scanned or image-only document.",
            "This phase does no OCR. Supply a text-based document instead.",
            subject=name,
        )
        return None
    marked = "\n".join(f"[[PAGE {index}]]\n{text}" for index, text in enumerate(pages, 1))
    return marked, len(pages)


def _check_usable(text: str, name: str, log: RuleFindingLog) -> bool:
    letters = sum(1 for character in text if character.isalpha())
    if letters < MIN_ALPHABETIC_CHARACTERS:
        log.error(
            RuleFindingCode.SOURCE_EXTRACTION_UNUSABLE,
            f"{name} yields {letters} letters, which is not readable prose.",
            "Check the document is text and not an image or a binary.",
            subject=name,
        )
        return False
    unprintable = sum(
        1
        for character in text
        if not character.isprintable() and character not in "\n\r\t"
    )
    if text and unprintable / len(text) > MAX_UNPRINTABLE_RATIO:
        log.error(
            RuleFindingCode.SOURCE_EXTRACTION_UNUSABLE,
            f"{name} is {unprintable / len(text):.0%} unprintable characters, so the "
            "extraction is garbled.",
            "Re-export the document as clean text. Rules are never derived from garbled "
            "extraction.",
            subject=name,
        )
        return False
    return True


# --------------------------------------------------------------------------------------
# Normalisation and segmentation — deterministic, and never chosen by a model
# --------------------------------------------------------------------------------------


def normalise(text: str) -> str:
    normalised = unicodedata.normalize("NFC", text)
    normalised = normalised.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.expandtabs(4).rstrip() for line in normalised.split("\n")]
    collapsed: list[str] = []
    blanks = 0
    for line in lines:
        if line:
            blanks = 0
            collapsed.append(line)
            continue
        blanks += 1
        if blanks <= 2:
            collapsed.append(line)
    return "\n".join(collapsed).strip("\n")


def _lines_with_pages(text: str) -> list[SourceLine]:
    result: list[SourceLine] = []
    page: int | None = None
    number = 0
    for raw in text.split("\n"):
        marker = PAGE_MARKER.match(raw)
        if marker:
            page = int(marker.group(1))
            continue
        number += 1
        result.append(SourceLine(number=number, text=raw, page=page))
    return result


def _peel_heading(
    block: list[SourceLine], adapter: SourceAdapter
) -> tuple[str | None, list[SourceLine]]:
    """Take the heading off the front of a block, leaving whatever followed it.

    A marker heading (``#``, or a Setext underline) is unambiguous, so it is peeled even
    when body text follows on the next line. A *numbered* heading is only recognised when
    it stands alone in its block: "2 Shares must be delivered" looks exactly like
    "4.1 Payment", and quietly deleting a sentence would be far worse than missing a
    heading.
    """
    first = block[0].text.strip()
    atx = ATX_HEADING.match(first)
    if atx:
        return atx.group(2).strip(), block[1:]
    if (
        adapter is SourceAdapter.MARKDOWN
        and len(block) >= 2
        and SETEXT_UNDERLINE.fullmatch(block[1].text.strip())
    ):
        return first, block[2:]
    if len(block) == 1 and NUMBERED_HEADING.match(first):
        return first, []
    return None, block


def segment_text(text: str, source_id: str, adapter: SourceAdapter) -> list[Segment]:
    """Split normalised text into stable, addressable segments.

    Boundaries fall on blank lines, headings and page breaks — never mid-sentence and
    never at a position a model chose. Segment size may be tuned for a context window; the
    *segmentation* stays deterministic, so the same bytes always yield the same identities.
    """
    lines = _lines_with_pages(text)
    blocks: list[list[SourceLine]] = []
    current: list[SourceLine] = []
    length = 0
    for line in lines:
        if not line.text.strip():
            if current:
                blocks.append(current)
                current = []
                length = 0
            continue
        # A page break and the segment ceiling both end a block, not just a blank line.
        # An extracted PDF can run hundreds of pages without a single blank line, and a
        # document that produced one segment would give every rule in it the same
        # evidence identity — which is no evidence at all.
        if current and (
            current[-1].page != line.page or length + len(line.text) > MAX_SEGMENT_CHARS
        ):
            blocks.append(current)
            current = []
            length = 0
        current.append(line)
        length += len(line.text) + 1
    if current:
        blocks.append(current)

    segments: list[Segment] = []
    heading: str | None = None
    pending: list[list[SourceLine]] = []
    pending_heading: str | None = None
    pending_page: int | None = None

    def flush() -> None:
        nonlocal pending, pending_heading, pending_page
        if not pending:
            return
        body = "\n\n".join(
            "\n".join(item.text for item in block) for block in pending
        ).strip()
        first_line = pending[0][0].number
        last_line = pending[-1][-1].number
        ordinal = len(segments) + 1
        segments.append(
            Segment(
                source_id=source_id,
                segment_id=f"{source_id}#S{ordinal:04d}",
                ordinal=ordinal,
                text=body,
                segment_hash=sha256_of(body),
                heading=pending_heading,
                page=pending_page,
                line_start=first_line,
                line_end=last_line,
            )
        )
        pending = []
        pending_heading = None
        pending_page = None

    for original in blocks:
        block_heading, block = _peel_heading(original, adapter)
        if block_heading is not None:
            # A heading opens a section; the heading itself carries no rule.
            flush()
            heading = block_heading
        if not block:
            continue
        block_page = block[0].page
        block_text = "\n".join(item.text for item in block)
        current_length = sum(
            len("\n".join(item.text for item in existing)) + 2 for existing in pending
        )
        if pending and (
            pending_page != block_page
            or current_length + len(block_text) > MAX_SEGMENT_CHARS
        ):
            flush()
        if not pending:
            pending_heading = heading
            pending_page = block_page
        pending.append(block)
    flush()
    return segments


# --------------------------------------------------------------------------------------
# Ingestion
# --------------------------------------------------------------------------------------


def ingest(bundle: SourceBundle, directory: Path) -> IngestedSource:
    """Read, check and segment one declared source. Raises with named findings."""
    log = RuleFindingLog()
    adapter = bundle.resolved_adapter()
    if adapter is None:
        log.error(
            RuleFindingCode.SOURCE_FORMAT_UNSUPPORTED,
            f"{bundle.source_location} has no adapter for its file type.",
            "Supported types are .txt, .md, .html and .pdf; declare `adapter:` to override.",
            subject=bundle.source_id,
        )
        raise RuleEngineError(log.findings)

    path = resolve_within(directory, bundle.source_location, log)
    if path is None:
        raise RuleEngineError(log.findings)
    raw = _read_bytes(path, log)
    if raw is None:
        raise RuleEngineError(log.findings)

    # Over the exact bytes on disk, so a re-encode or a whitespace fix is a new source.
    checksum = "sha256:" + hashlib.sha256(raw).hexdigest()
    if bundle.source_checksum and bundle.source_checksum != checksum:
        log.error(
            RuleFindingCode.SOURCE_HASH_MISMATCH,
            f"{bundle.source_location} digests to {checksum[:19]}…, but the manifest "
            f"records {bundle.source_checksum[:19]}….",
            "The document changed. Re-ingest it and re-review every rule derived from it.",
            subject=bundle.source_id,
        )
        raise RuleEngineError(log.findings)

    page_count = 0
    if adapter is SourceAdapter.HTML:
        text = _html_to_text(raw, bundle.source_location, log) or ""
    elif adapter is SourceAdapter.PDF_TEXT:
        extracted = _pdf_to_text(raw, bundle.source_location, log)
        if extracted is None:
            raise RuleEngineError(log.findings)
        text, page_count = extracted
    else:
        text = _decode(raw, bundle.source_location, log) or ""
    if log.blocked:
        raise RuleEngineError(log.findings)

    normalised = normalise(text)
    if not _check_usable(normalised, bundle.source_location, log):
        raise RuleEngineError(log.findings)

    segments = segment_text(normalised, bundle.source_id, adapter)
    if not segments:
        log.error(
            RuleFindingCode.SOURCE_EXTRACTION_UNUSABLE,
            f"{bundle.source_location} produced no segments.",
            "Check the document has readable paragraphs.",
            subject=bundle.source_id,
        )
        raise RuleEngineError(log.findings)

    stamped = bundle.model_copy(update={"source_checksum": checksum, "adapter": adapter})
    return IngestedSource(
        bundle=stamped,
        checksum=checksum,
        adapter=adapter,
        segments=tuple(segments),
        page_count=page_count,
    )


# --------------------------------------------------------------------------------------
# The manifest
# --------------------------------------------------------------------------------------


def rule_source_directory() -> Path:
    return source_path(get_settings().rule_source_directory, "rule_sources")


MANIFEST_NAME = "sources.yaml"


class SourceManifest:
    """The declared sources of a drop directory. Absent is normal, not an error."""

    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory or rule_source_directory()
        self._bundles = self._load()

    def _load(self) -> dict[str, SourceBundle]:
        path = self._directory / MANIFEST_NAME
        if not path.is_file():
            return {}
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        entries = raw.get("sources") or []
        bundles: dict[str, SourceBundle] = {}
        for entry in entries:
            try:
                bundle = SourceBundle.model_validate(entry)
            except ValidationError as error:
                raise ValueError(
                    f"{MANIFEST_NAME} declares an invalid source: "
                    f"{'; '.join(item['msg'] for item in error.errors()[:3])}"
                ) from error
            if bundle.source_id in bundles:
                raise ValueError(f"Duplicate source id: {bundle.source_id}")
            bundles[bundle.source_id] = bundle
        return bundles

    @property
    def directory(self) -> Path:
        return self._directory

    def ids(self) -> list[str]:
        return sorted(self._bundles)

    def get(self, source_id: str) -> SourceBundle:
        try:
            return self._bundles[source_id.strip().upper()]
        except KeyError as error:
            raise KeyError(f"Unknown source: {source_id}") from error

    def ingest(self, source_id: str) -> IngestedSource:
        return ingest(self.get(source_id), self._directory)
