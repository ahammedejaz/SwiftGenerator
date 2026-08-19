"""ISO 20022 source discovery, manifests and batch scale-out.

This module is deliberately offline/developer tooling. Runtime generation still loads
reviewed specification packs only; it never fetches a schema and never compiles one.
"""

from __future__ import annotations

import hashlib
import io
import re
import ssl
import stat
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, NoReturn
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

import yaml
from lxml import etree
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.spec_engine.diagnostics import CompilationError, FindingCode, FindingLog
from app.spec_engine.gates import PackValidation, validate_pack
from app.spec_engine.pipeline import CompiledPack, compile_schema
from app.spec_engine.xsd_loader import MAX_FILE_BYTES, XS

ISO_CATALOGUE_URL = "https://www.iso20022.org/iso-20022-message-definitions"
OFFICIAL_HOSTS = {"iso20022.org", "www.iso20022.org"}
MESSAGE_ID_RE = re.compile(r"\b([a-z]{4}\.\d{3}\.\d{3}\.\d{2})\b")
XML_CONTENT_TYPES = {"application/xml", "text/xml", "application/xsd+xml"}
OCTET_STREAM = "application/octet-stream"
ZIP_CONTENT_TYPES = {
    "application/zip",
    "application/x-zip",
    "application/x-zip-compressed",
    OCTET_STREAM,
}
MAX_BUNDLE_DOWNLOAD_BYTES = 80 * 1024 * 1024
MAX_BUNDLE_FILE_COUNT = 2500
MAX_BUNDLE_MEMBER_BYTES = MAX_FILE_BYTES
MAX_BUNDLE_TOTAL_UNCOMPRESSED_BYTES = 250 * 1024 * 1024
MAX_BUNDLE_COMPRESSION_RATIO = 100
NESTED_ARCHIVE_SUFFIXES = {
    ".7z",
    ".bz2",
    ".gz",
    ".jar",
    ".rar",
    ".tar",
    ".tgz",
    ".xz",
    ".zip",
}


class CatalogueState(StrEnum):
    CURRENT = "CURRENT"
    ARCHIVED = "ARCHIVED"


class SourceType(StrEnum):
    OFFICIAL_ISO_20022_XSD = "OFFICIAL_ISO_20022_XSD"
    OPERATOR_SUPPLIED_XSD = "OPERATOR_SUPPLIED_XSD"
    REVIEWED_LOCAL_SOURCE_BUNDLE = "REVIEWED_LOCAL_SOURCE_BUNDLE"


class RedistributionStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    OPERATOR_APPROVED = "OPERATOR_APPROVED"
    REDISTRIBUTABLE = "REDISTRIBUTABLE"
    DO_NOT_COMMIT = "DO_NOT_COMMIT"


_BUSINESS_AREA_BY_LABEL = {
    "Bank-to-Customer Cash Management": "CASH_MANAGEMENT",
    "Payments Clearing and Settlement": "PAYMENTS_CLEARING_SETTLEMENT",
    "Payments Initiation": "PAYMENT_INITIATION",
    "Cash Management": "CASH_MANAGEMENT",
    "Settlement and Reconciliation": "SECURITIES_SETTLEMENT",
    "Securities Settlement": "SECURITIES_SETTLEMENT",
    "Securities Management": "SECURITIES_MANAGEMENT",
    "Securities Events": "SECURITIES_EVENTS",
    "Corporate Actions": "SECURITIES_EVENTS",
    "Business Application Header": "OTHER",
}


@dataclass(frozen=True)
class CatalogueMessage:
    logical_message: str
    message_definition: str
    message_name: str
    message_set: str
    business_area: str
    submitting_organisation: str
    catalogue_state: CatalogueState
    source_url: str
    xsd_url: str | None


@dataclass(frozen=True)
class CatalogueMessageSet:
    message_set_name: str
    source_page: str
    download_url: str
    catalogue_observation: str
    last_updated: str = ""


class SourceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    logical_message: str = Field(alias="logicalMessage", pattern=r"^[a-z]{4}\.\d{3}$")
    message_definition: str = Field(
        alias="messageDefinition", pattern=r"^[a-z]{4}\.\d{3}\.\d{3}\.\d{2}$"
    )
    message_name: str = Field(default="", alias="messageName")
    message_set: str = Field(default="", alias="messageSet")
    business_area: str = Field(default="OTHER", alias="businessArea")
    submitting_organisation: str = Field(default="", alias="submittingOrganisation")
    catalogue_state: CatalogueState = Field(default=CatalogueState.CURRENT, alias="catalogueState")
    source_type: SourceType = Field(default=SourceType.OPERATOR_SUPPLIED_XSD, alias="sourceType")
    source_url: str = Field(alias="sourceUrl")
    xsd_url: str | None = Field(default=None, alias="xsdUrl")
    source_location: str | None = Field(default=None, alias="sourceLocation")
    source_checksum: str | None = Field(default=None, alias="sourceChecksum")
    content_type: str = Field(default="application/xml", alias="contentType")
    authority_declaration: str = Field(
        default=(
            "Declared by catalogue/operator metadata; not independently verified by "
            "the platform."
        ),
        alias="authorityDeclaration",
    )
    redistribution_status: RedistributionStatus = Field(
        default=RedistributionStatus.UNKNOWN, alias="redistributionStatus"
    )
    derived_metadata_redistribution_status: RedistributionStatus = Field(
        default=RedistributionStatus.UNKNOWN, alias="derivedMetadataRedistributionStatus"
    )
    raw_source_committed: bool = Field(default=False, alias="rawSourceCommitted")

    @field_validator("source_url")
    @classmethod
    def source_reference_is_constrained(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme in {"https", "http"}:
            _assert_official_url(value)
            return value
        if parsed.scheme in {"operator-local", "reviewed-local"}:
            return value
        raise ValueError(
            "sourceUrl must be an iso20022.org URL, operator-local:<id>, or reviewed-local:<id>"
        )

    @field_validator("xsd_url")
    @classmethod
    def official_xsd_urls_only(cls, value: str | None) -> str | None:
        if value is not None:
            _assert_official_url(value)
        return value

    @field_validator("source_location")
    @classmethod
    def source_location_is_file_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        path = Path(value)
        if path.is_absolute() or ".." in path.parts or len(path.parts) != 1:
            raise ValueError("sourceLocation must be a file name inside the source directory")
        return value


class MessageSetEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    message_set_name: str = Field(alias="messageSetName")
    download_url: str | None = Field(default=None, alias="messageSetDownloadUrl")
    source_page: str = Field(alias="messageSetSourcePage")
    catalogue_observation: str = Field(default="", alias="catalogueObservation")
    last_updated: str = Field(default="", alias="lastUpdated")
    bundle_location: str | None = Field(default=None, alias="bundleLocation")
    bundle_checksum: str | None = Field(default=None, alias="bundleChecksum")
    redistribution_status: RedistributionStatus = Field(
        default=RedistributionStatus.UNKNOWN, alias="redistributionStatus"
    )
    raw_source_committed: bool = Field(default=False, alias="rawSourceCommitted")

    @field_validator("download_url")
    @classmethod
    def official_download_urls_only(cls, value: str | None) -> str | None:
        if value is not None:
            _assert_official_https_url(value)
        return value

    @field_validator("source_page")
    @classmethod
    def source_page_is_official(cls, value: str) -> str:
        _assert_official_url(value)
        return value

    @field_validator("bundle_location")
    @classmethod
    def bundle_location_stays_inside_source_cache(cls, value: str | None) -> str | None:
        if value is None:
            return None
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or not path.name:
            raise ValueError("bundleLocation must stay inside the source directory")
        if PureWindowsPath(value).drive:
            raise ValueError("bundleLocation must not use a Windows drive path")
        return value


class LogicalMessageDefinitions(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    logical_message: str = Field(alias="logicalMessage", pattern=r"^[a-z]{4}\.\d{3}$")
    current_definitions: list[str] = Field(default_factory=list, alias="currentDefinitions")
    archived_definitions: list[str] = Field(default_factory=list, alias="archivedDefinitions")


class SourceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    manifest_version: str = Field(default="mx-source-manifest/1", alias="manifestVersion")
    retrieved_at: str = Field(alias="retrievedAt")
    source_url: str = Field(default=ISO_CATALOGUE_URL, alias="sourceUrl")
    message_sets_inspected: list[str] = Field(default_factory=list, alias="messageSetsInspected")
    message_sets: list[MessageSetEntry] = Field(default_factory=list, alias="messageSets")
    unresolved: list[str] = Field(default_factory=list)
    logical_messages: list[LogicalMessageDefinitions] = Field(
        default_factory=list, alias="logicalMessages"
    )
    messages: list[SourceEntry] = Field(default_factory=list)

    @field_validator("source_url")
    @classmethod
    def manifest_source_is_official(cls, value: str) -> str:
        _assert_official_url(value)
        return value


@dataclass(frozen=True)
class BatchItemResult:
    entry: SourceEntry
    source_path: Path | None
    pack_path: Path | None = None
    compiled: bool = False
    gates: PackValidation | None = None
    error: str = ""
    pack: CompiledPack | None = None

    @property
    def passed(self) -> bool:
        return self.compiled and self.gates is not None and self.gates.passed


@dataclass
class BatchResult:
    manifest_path: Path
    candidates_dir: Path
    items: list[BatchItemResult] = field(default_factory=list)

    @property
    def attempted(self) -> int:
        return len(self.items)

    @property
    def compiled(self) -> int:
        return sum(1 for item in self.items if item.compiled)

    @property
    def passed(self) -> int:
        return sum(1 for item in self.items if item.passed)

    @property
    def failed(self) -> int:
        return self.attempted - self.passed


@dataclass(frozen=True)
class FetchResult:
    url: str
    final_url: str
    path: Path
    checksum: str
    content_type: str
    size: int
    redirects: tuple[str, ...] = ()


@dataclass(frozen=True)
class BundleIndexEntry:
    exact_message_definition: str
    target_namespace: str
    source_file: str
    source_checksum: str
    bundle_checksum: str
    message_set: str
    source_authority: str = "OFFICIAL_ISO_20022"
    redistribution_status: RedistributionStatus = RedistributionStatus.UNKNOWN


@dataclass(frozen=True)
class BundleIndex:
    message_set: str
    bundle_path: Path | None
    bundle_checksum: str
    entries: tuple[BundleIndexEntry, ...]
    inspected_files: tuple[str, ...]

    @property
    def by_definition(self) -> dict[str, BundleIndexEntry]:
        return {item.exact_message_definition: item for item in self.entries}


@dataclass(frozen=True)
class BundleFetchResult:
    url: str
    final_url: str
    path: Path
    checksum: str
    content_type: str
    size: int
    index: BundleIndex
    redirects: tuple[str, ...] = ()


@dataclass(frozen=True)
class HttpFetchResponse:
    body: bytes
    content_type: str
    final_url: str
    redirects: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Token:
    text: str
    href: str | None = None


class _CatalogueParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tokens: list[_Token] = []
        self._href_stack: list[str | None] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        href = None
        if tag == "a":
            href = dict(attrs).get("href")
        self._href_stack.append(href)

    def handle_endtag(self, tag: str) -> None:
        if self._href_stack:
            self._href_stack.pop()

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if text:
            href = next((item for item in reversed(self._href_stack) if item), None)
            self.tokens.append(_Token(text=text, href=href))


def _assert_official_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or parsed.hostname not in OFFICIAL_HOSTS:
        raise ValueError("ISO 20022 structural-source URLs must use iso20022.org")


def _assert_official_https_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS:
        raise ValueError("ISO 20022 source downloads must stay on HTTPS iso20022.org")


def _absolute_official_url(base_url: str, href: str | None) -> str | None:
    if not href:
        return None
    url = urljoin(base_url, href)
    _assert_official_url(url)
    return url


def _next_value(tokens: list[_Token], start: int, stop: int) -> str:
    ignored = {
        "More Less",
        "Show more Show less",
        "Downloads",
        "Message ID (scheme)",
        "Message name",
        "Submitting organisation",
        "XSD",
        "Download",
        "Updated",
    }
    for index in range(start, stop):
        text = tokens[index].text
        if text in ignored or MESSAGE_ID_RE.fullmatch(text):
            continue
        return text
    return ""


def _nearest_business_area(tokens: list[_Token], index: int) -> tuple[str, str]:
    for previous in range(index - 1, max(-1, index - 80), -1):
        text = tokens[previous].text
        if text in _BUSINESS_AREA_BY_LABEL:
            return text, _BUSINESS_AREA_BY_LABEL[text]
    return "", "OTHER"


def parse_catalogue_html(
    html: str, *, source_url: str, catalogue_state: CatalogueState = CatalogueState.CURRENT
) -> list[CatalogueMessage]:
    """Extract message-definition metadata from an ISO catalogue results page."""
    _assert_official_url(source_url)
    parser = _CatalogueParser()
    parser.feed(html)
    tokens = parser.tokens
    messages: dict[str, CatalogueMessage] = {}

    for index, token in enumerate(tokens):
        match = MESSAGE_ID_RE.fullmatch(token.text)
        if not match:
            continue
        definition = match.group(1)
        next_message = next(
            (
                later
                for later in range(index + 1, len(tokens))
                if MESSAGE_ID_RE.fullmatch(tokens[later].text)
            ),
            len(tokens),
        )
        message_set_label, business_area = _nearest_business_area(tokens, index)
        xsd_url = next(
            (
                _absolute_official_url(source_url, item.href)
                for item in tokens[index + 1 : next_message]
                if item.text == "XSD" and item.href
            ),
            None,
        )
        message = CatalogueMessage(
            logical_message=".".join(definition.split(".")[:2]),
            message_definition=definition,
            message_name=_next_value(tokens, index + 1, next_message),
            message_set=message_set_label or definition.split(".")[0],
            business_area=business_area,
            submitting_organisation=_next_value(tokens, index + 2, next_message),
            catalogue_state=catalogue_state,
            source_url=source_url,
            xsd_url=xsd_url,
        )
        existing = messages.get(definition)
        if existing is None or (existing.xsd_url is None and message.xsd_url is not None):
            messages[definition] = message

    return list(messages.values())


def parse_message_sets_html(html: str, *, source_url: str) -> list[CatalogueMessageSet]:
    """Extract official message-set download links from an ISO catalogue results page."""
    _assert_official_url(source_url)
    parser = _CatalogueParser()
    parser.feed(html)
    tokens = parser.tokens
    message_sets: dict[tuple[str, str], CatalogueMessageSet] = {}

    for index, token in enumerate(tokens):
        if token.text != "Download complete message set" or token.href is None:
            continue
        download_url = _absolute_official_url(source_url, token.href)
        if download_url is None:
            continue
        name = _nearest_message_set_name(tokens, index)
        if not name:
            name = "UNKNOWN_MESSAGE_SET"
        last_updated = _nearest_last_updated(tokens, index)
        message_set = CatalogueMessageSet(
            message_set_name=name,
            source_page=source_url,
            download_url=download_url,
            catalogue_observation=token.text,
            last_updated=last_updated,
        )
        message_sets[(name, download_url)] = message_set

    return list(message_sets.values())


def _nearest_message_set_name(tokens: list[_Token], index: int) -> str:
    ignored = {
        "Download complete message set",
        "Downloads",
        "Last Updated",
        "Updated",
        "Message ID (scheme)",
        "Message name",
        "Submitting organisation",
        "Message set",
        "Business area",
        "More Less",
        "Show more Show less",
        "BAH",
        "Has variants",
        "Is variant",
        "Has Variant",
        "Is Variant",
    }
    date_re = re.compile(r"\d{1,2}\s+[A-Za-z]+\s+\d{4}")
    for previous in range(index - 1, max(-1, index - 50), -1):
        text = tokens[previous].text
        if text in ignored or MESSAGE_ID_RE.fullmatch(text) or date_re.fullmatch(text):
            continue
        if text == "XSD" or text.endswith(".xsd"):
            continue
        return text
    return ""


def _nearest_last_updated(tokens: list[_Token], index: int) -> str:
    date_re = re.compile(r"\d{1,2}\s+[A-Za-z]+\s+\d{4}")
    for previous in range(index - 1, max(-1, index - 20), -1):
        if date_re.fullmatch(tokens[previous].text):
            return tokens[previous].text
    return ""


class _ConstrainedRedirectHandler(HTTPRedirectHandler):
    def __init__(self) -> None:
        super().__init__()
        self.redirects: list[str] = []

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        _assert_official_https_url(req.full_url)
        _assert_official_https_url(newurl)
        self.redirects.append(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch_bytes(url: str) -> tuple[bytes, str]:
    response = _fetch_official_url(url)
    return response.body, response.content_type


def _fetch_official_url(url: str, *, max_bytes: int = MAX_FILE_BYTES) -> HttpFetchResponse:
    _assert_official_https_url(url)
    request = Request(url, headers={"User-Agent": "FinancialMessageStudio/phase3"})
    context = _tls_context()
    redirect_handler = _ConstrainedRedirectHandler()
    opener = build_opener(HTTPSHandler(context=context), redirect_handler)
    with opener.open(request, timeout=60) as response:  # noqa: S310
        final_url = response.geturl()
        _assert_official_https_url(final_url)
        content_type = response.headers.get("Content-Type", "application/octet-stream")
        body = response.read(max_bytes + 1)
        return HttpFetchResponse(
            body=body,
            content_type=content_type.split(";", 1)[0].lower(),
            final_url=final_url,
            redirects=tuple(redirect_handler.redirects),
        )


def _fetch_official_bundle_url(url: str) -> HttpFetchResponse:
    return _fetch_official_url(url, max_bytes=MAX_BUNDLE_DOWNLOAD_BYTES)


def _tls_context() -> ssl.SSLContext:
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def discover_messages(
    logical_messages: list[str],
    *,
    fetcher: Callable[[str], tuple[bytes, str]] = _fetch_bytes,
    retrieved_at: datetime | None = None,
) -> SourceManifest:
    """Resolve logical message IDs from the official ISO catalogue."""
    retrieved = (retrieved_at or datetime.now(UTC)).replace(microsecond=0).isoformat()
    entries: list[SourceEntry] = []
    sets: set[str] = set()
    message_sets: dict[tuple[str, str], MessageSetEntry] = {}
    unresolved: list[str] = []
    for logical in logical_messages:
        if not re.fullmatch(r"[a-z]{4}\.\d{3}", logical):
            raise ValueError(f"{logical} is not a logical ISO 20022 message id")
        url = ISO_CATALOGUE_URL + "?" + urlencode({"search": logical})
        try:
            raw, _content_type = fetcher(url)
        except Exception as error:  # noqa: BLE001 - discovery records partial failure.
            unresolved.append(f"{logical}: {error}")
            continue
        for message_set in parse_message_sets_html(
            raw.decode("utf-8", errors="replace"), source_url=url
        ):
            message_sets[(message_set.message_set_name, message_set.download_url)] = (
                MessageSetEntry(
                    message_set_name=message_set.message_set_name,
                    download_url=message_set.download_url,
                    source_page=message_set.source_page,
                    catalogue_observation=message_set.catalogue_observation,
                    last_updated=message_set.last_updated,
                    redistribution_status=RedistributionStatus.UNKNOWN,
                    raw_source_committed=False,
                )
            )
        matches = [
            item
            for item in parse_catalogue_html(raw.decode("utf-8", errors="replace"), source_url=url)
            if item.logical_message == logical
        ]
        if not matches:
            unresolved.append(f"{logical}: not found in catalogue search results")
            continue
        for selected in sorted(matches, key=lambda item: item.message_definition):
            sets.add(selected.message_set)
            entries.append(
                SourceEntry(
                    logical_message=selected.logical_message,
                    message_definition=selected.message_definition,
                    message_name=selected.message_name,
                    message_set=selected.message_set,
                    business_area=selected.business_area,
                    submitting_organisation=selected.submitting_organisation,
                    catalogue_state=selected.catalogue_state,
                    source_type=SourceType.OFFICIAL_ISO_20022_XSD,
                    source_url=selected.source_url,
                    xsd_url=selected.xsd_url,
                    source_location=f"{selected.message_definition}.xsd",
                    redistribution_status=RedistributionStatus.UNKNOWN,
                    derived_metadata_redistribution_status=RedistributionStatus.UNKNOWN,
                    raw_source_committed=False,
                )
            )
    return SourceManifest(
        retrieved_at=retrieved,
        source_url=ISO_CATALOGUE_URL,
        message_sets_inspected=sorted(sets),
        message_sets=[message_sets[key] for key in sorted(message_sets)],
        unresolved=unresolved,
        logical_messages=_group_logical_definitions(entries),
        messages=entries,
    )


def load_manifest(path: Path) -> SourceManifest:
    return SourceManifest.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def manifest_yaml(manifest: SourceManifest) -> str:
    return yaml.safe_dump(
        manifest.model_dump(by_alias=True, mode="json", exclude_none=True),
        sort_keys=False,
        allow_unicode=False,
    )


def _group_logical_definitions(entries: list[SourceEntry]) -> list[LogicalMessageDefinitions]:
    grouped: dict[str, dict[CatalogueState, set[str]]] = {}
    for entry in entries:
        states = grouped.setdefault(
            entry.logical_message,
            {CatalogueState.CURRENT: set(), CatalogueState.ARCHIVED: set()},
        )
        states[entry.catalogue_state].add(entry.message_definition)
    return [
        LogicalMessageDefinitions(
            logical_message=logical,
            current_definitions=sorted(states[CatalogueState.CURRENT]),
            archived_definitions=sorted(states[CatalogueState.ARCHIVED]),
        )
        for logical, states in sorted(grouped.items())
    ]


def _xsd_target_namespace(raw: bytes, *, source_name: str) -> str:
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError(f"{source_name} is {len(raw)} bytes; the limit is {MAX_FILE_BYTES}")
    head = raw[:4096].lstrip()
    if b"<!DOCTYPE" in raw:
        raise ValueError(f"{source_name} declares a DOCTYPE")
    if not head.startswith((b"<?xml", b"<")):
        raise ValueError(f"{source_name} does not look like XML")
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
    )
    try:
        root = etree.fromstring(raw, parser=parser)
    except etree.XMLSyntaxError as error:
        raise ValueError(f"{source_name} is not well-formed XML: {error.msg}") from error
    if root.tag != f"{{{XS}}}schema":
        raise ValueError(f"{source_name} root is not xs:schema")
    return root.get("targetNamespace") or ""


def _expected_namespace(message_definition: str) -> str:
    return f"urn:iso:std:iso:20022:tech:xsd:{message_definition}"


def _validate_xsd_fetch(
    response: HttpFetchResponse,
    *,
    expected_message_definition: str | None,
    expected_checksum: str | None,
) -> str:
    for redirect in response.redirects:
        _assert_official_https_url(redirect)
    _assert_official_https_url(response.final_url)
    content_type = response.content_type.split(";", 1)[0].lower()
    if content_type not in XML_CONTENT_TYPES | {OCTET_STREAM}:
        raise ValueError(f"unexpected content-type for XSD source: {response.content_type}")
    source_name = Path(urlparse(response.final_url).path).name or "source"
    namespace = _xsd_target_namespace(response.body, source_name=source_name)
    if expected_message_definition is not None:
        expected = _expected_namespace(expected_message_definition)
        if namespace != expected:
            raise ValueError(f"targetNamespace mismatch: expected {expected}, got {namespace}")
    checksum = "sha256:" + hashlib.sha256(response.body).hexdigest()
    if expected_checksum is not None and checksum != expected_checksum:
        raise ValueError(f"checksum mismatch: expected {expected_checksum}, got {checksum}")
    return checksum


def discover_message_sets(
    family: str,
    *,
    fetcher: Callable[[str], tuple[bytes, str]] = _fetch_bytes,
) -> list[MessageSetEntry]:
    """Resolve official message-set download links from the current ISO catalogue."""
    if not re.fullmatch(r"[a-z]{4}(?:\.\d{3})?", family):
        raise ValueError(f"{family} is not an ISO 20022 family or logical message id")
    url = ISO_CATALOGUE_URL + "?" + urlencode({"search": family})
    raw, _content_type = fetcher(url)
    return [
        MessageSetEntry(
            message_set_name=item.message_set_name,
            download_url=item.download_url,
            source_page=item.source_page,
            catalogue_observation=item.catalogue_observation,
            last_updated=item.last_updated,
            redistribution_status=RedistributionStatus.UNKNOWN,
            raw_source_committed=False,
        )
        for item in parse_message_sets_html(raw.decode("utf-8", errors="replace"), source_url=url)
    ]


def fetch_message_set_bundle(
    url: str,
    target: Path,
    *,
    message_set_name: str,
    fetcher: Callable[[str], HttpFetchResponse] = _fetch_official_bundle_url,
) -> BundleFetchResult:
    """Fetch and safely index one official ISO message-set archive."""
    _assert_official_https_url(url)
    try:
        response = fetcher(url)
    except Exception as error:  # noqa: BLE001 - convert transport failure to diagnostics.
        _raise_bundle_error(
            FindingCode.ISO_BUNDLE_DOWNLOAD_FAILED,
            f"could not download ISO message-set archive: {error}",
            "Retry later or use an operator-supplied local ISO message-set archive.",
        )
    for redirect in response.redirects:
        _assert_official_https_url(redirect)
    _assert_official_https_url(response.final_url)
    content_type = response.content_type.split(";", 1)[0].lower()
    if content_type not in ZIP_CONTENT_TYPES:
        _raise_bundle_error(
            FindingCode.ISO_BUNDLE_DOWNLOAD_FAILED,
            f"unexpected content-type for message-set archive: {response.content_type}",
            "Use the official ISO complete-message-set download link.",
        )
    if len(response.body) > MAX_BUNDLE_DOWNLOAD_BYTES:
        _raise_bundle_error(
            FindingCode.ISO_BUNDLE_OVERSIZED,
            f"message-set archive is {len(response.body)} bytes; "
            f"the limit is {MAX_BUNDLE_DOWNLOAD_BYTES}",
            "Use a smaller reviewed source bundle or raise the configured limit deliberately.",
        )
    zip_path = _bundle_target_path(target, message_set_name, response.final_url)
    destination = zip_path.parent.parent if zip_path.parent.name == "bundles" else zip_path.parent
    index = index_message_set_bundle_bytes(
        response.body,
        destination=destination,
        message_set_name=message_set_name,
        bundle_path=zip_path,
    )
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    zip_path.write_bytes(response.body)
    return BundleFetchResult(
        url=url,
        final_url=response.final_url,
        path=zip_path,
        checksum=index.bundle_checksum,
        content_type=response.content_type,
        size=len(response.body),
        index=index,
        redirects=response.redirects,
    )


def index_message_set_bundle(
    bundle_path: Path,
    *,
    destination: Path,
    message_set_name: str,
) -> BundleIndex:
    """Safely index a local message-set archive already present in the source cache."""
    return index_message_set_bundle_bytes(
        bundle_path.read_bytes(),
        destination=destination,
        message_set_name=message_set_name,
        bundle_path=bundle_path,
    )


def index_message_set_bundle_bytes(
    raw: bytes,
    *,
    destination: Path,
    message_set_name: str,
    bundle_path: Path | None = None,
) -> BundleIndex:
    """Validate a ZIP and materialise only verified XSD entries into destination."""
    if len(raw) > MAX_BUNDLE_DOWNLOAD_BYTES:
        _raise_bundle_error(
            FindingCode.ISO_BUNDLE_OVERSIZED,
            f"message-set archive is {len(raw)} bytes; the limit is {MAX_BUNDLE_DOWNLOAD_BYTES}",
            "Use a smaller reviewed source bundle or raise the configured limit deliberately.",
        )
    if not zipfile.is_zipfile(io.BytesIO(raw)):
        _raise_bundle_error(
            FindingCode.ISO_BUNDLE_DOWNLOAD_FAILED,
            "message-set download is not a valid ZIP archive",
            "Use the official ISO complete-message-set archive.",
        )

    bundle_checksum = "sha256:" + hashlib.sha256(raw).hexdigest()
    destination.mkdir(parents=True, exist_ok=True)
    entries_to_write: dict[str, tuple[bytes, str, str]] = {}
    inspected_files: list[str] = []
    seen_names: set[str] = set()
    total_uncompressed = 0

    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            file_count = sum(1 for info in infos if not info.is_dir())
            if file_count > MAX_BUNDLE_FILE_COUNT:
                _raise_bundle_error(
                    FindingCode.ISO_BUNDLE_OVERSIZED,
                    f"message-set archive contains {file_count} files; "
                    f"the limit is {MAX_BUNDLE_FILE_COUNT}",
                    "Review the archive contents before raising the configured limit.",
                )
            for info in infos:
                name = _normalise_bundle_member_name(info.filename)
                _assert_zip_member_type(info, name)
                if not info.is_dir() and name in seen_names:
                    _raise_bundle_error(
                        FindingCode.ISO_BUNDLE_DUPLICATE_ENTRY,
                        f"duplicate archive filename: {name}",
                        "Use a deterministic archive without repeated filenames.",
                        source=name,
                    )
                seen_names.add(name)
                inspected_files.append(name)
                if info.is_dir():
                    continue
                _assert_zip_member_sizes(info, name)
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_BUNDLE_TOTAL_UNCOMPRESSED_BYTES:
                    _raise_bundle_error(
                        FindingCode.ISO_BUNDLE_OVERSIZED,
                        "message-set archive expands beyond the configured total limit",
                        "Review the archive contents before raising the configured limit.",
                        source=name,
                    )
                if PurePosixPath(name).suffix.lower() in NESTED_ARCHIVE_SUFFIXES:
                    _raise_bundle_error(
                        FindingCode.ISO_BUNDLE_NESTED_ARCHIVE_REJECTED,
                        f"nested archive entry is not allowed: {name}",
                        "Unpack and review nested archives outside this automated path.",
                        source=name,
                    )
                _assert_destination_containment(destination, name)
                if PurePosixPath(name).suffix.lower() != ".xsd":
                    continue
                candidate = archive.read(info)
                namespace = _safe_xsd_namespace(candidate, source_name=name)
                definition = _message_definition_from_namespace(namespace)
                if definition is None:
                    continue
                filename_match = MESSAGE_ID_RE.search(PurePosixPath(name).name)
                if filename_match and filename_match.group(1) != definition:
                    _raise_bundle_error(
                        FindingCode.ISO_BUNDLE_BAD_XSD,
                        "XSD filename and targetNamespace identify different messages",
                        "Review the archive manually and do not trust filename identity.",
                        source=name,
                    )
                checksum = "sha256:" + hashlib.sha256(candidate).hexdigest()
                existing = entries_to_write.get(definition)
                if existing is not None and existing[1] != checksum:
                    _raise_bundle_error(
                        FindingCode.ISO_BUNDLE_DUPLICATE_ENTRY,
                        f"conflicting XSD entries for {definition}",
                        "Keep only one authoritative schema for each exact message definition.",
                        source=name,
                    )
                entries_to_write[definition] = (candidate, checksum, namespace)
    except zipfile.BadZipFile as error:
        _raise_bundle_error(
            FindingCode.ISO_BUNDLE_DOWNLOAD_FAILED,
            f"message-set archive cannot be read: {error}",
            "Use the official ISO complete-message-set archive.",
        )

    if not entries_to_write:
        _raise_bundle_error(
            FindingCode.ISO_BUNDLE_NO_XSD_FOUND,
            "message-set archive did not contain indexable ISO message XSD files",
            "Inspect the official archive layout or provide the exact local source explicitly.",
        )

    index_entries: list[BundleIndexEntry] = []
    for definition, (body, checksum, namespace) in sorted(entries_to_write.items()):
        source_file = f"{definition}.xsd"
        output_path = destination / source_file
        if output_path.exists() and output_path.read_bytes() != body:
            _raise_bundle_error(
                FindingCode.ISO_BUNDLE_DUPLICATE_ENTRY,
                f"{source_file} already exists with different bytes",
                "Use an empty source cache or separate caches for different source sets.",
                source=source_file,
            )
        output_path.write_bytes(body)
        index_entries.append(
            BundleIndexEntry(
                exact_message_definition=definition,
                target_namespace=namespace,
                source_file=source_file,
                source_checksum=checksum,
                bundle_checksum=bundle_checksum,
                message_set=message_set_name,
            )
        )

    return BundleIndex(
        message_set=message_set_name,
        bundle_path=bundle_path,
        bundle_checksum=bundle_checksum,
        entries=tuple(index_entries),
        inspected_files=tuple(sorted(inspected_files)),
    )


def render_bundle_index(index: BundleIndex) -> str:
    lines = [
        f"message-set: {index.message_set}",
        f"bundle: {index.bundle_path or '-'}",
        f"bundle-checksum: {index.bundle_checksum}",
        f"inspected-files: {len(index.inspected_files)}",
        f"xsd-definitions: {len(index.entries)}",
    ]
    for entry in index.entries:
        lines.append(
            f"- {entry.exact_message_definition}: {entry.source_file} "
            f"({entry.source_checksum})"
        )
    return "\n".join(lines)


def _bundle_target_path(target: Path, message_set_name: str, final_url: str) -> Path:
    if target.suffix.lower() == ".zip":
        return target
    parsed_path = PurePosixPath(urlparse(final_url).path)
    last_parts = [part for part in parsed_path.parts if part not in {"/", ""}]
    url_hint = "-".join(last_parts[-3:-1]) if len(last_parts) >= 2 else ""
    slug = _slug(message_set_name or url_hint or "message-set")
    return target / "bundles" / f"{slug}.zip"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "message-set"


def _normalise_bundle_member_name(name: str) -> str:
    if not name or "\x00" in name or "\\" in name:
        _raise_bundle_error(
            FindingCode.ISO_BUNDLE_PATH_TRAVERSAL,
            f"unsafe archive path: {name!r}",
            "Use ZIP entries with relative POSIX paths only.",
            source=name or None,
        )
    if PureWindowsPath(name).drive:
        _raise_bundle_error(
            FindingCode.ISO_BUNDLE_PATH_TRAVERSAL,
            f"Windows drive path is not allowed: {name}",
            "Use ZIP entries with relative POSIX paths only.",
            source=name,
        )
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        _raise_bundle_error(
            FindingCode.ISO_BUNDLE_PATH_TRAVERSAL,
            f"archive path escapes the source cache: {name}",
            "Use ZIP entries with paths below the destination root.",
            source=name,
        )
    normalised = str(path)
    if normalised in {"", "."}:
        _raise_bundle_error(
            FindingCode.ISO_BUNDLE_PATH_TRAVERSAL,
            f"unsafe archive path: {name!r}",
            "Use ZIP entries with relative POSIX paths only.",
            source=name,
        )
    return normalised


def _assert_zip_member_type(info: zipfile.ZipInfo, name: str) -> None:
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        _raise_bundle_error(
            FindingCode.ISO_BUNDLE_SYMLINK_REJECTED,
            f"symlink entry is not allowed: {name}",
            "Use a message-set archive containing regular files and directories only.",
            source=name,
        )
    file_type = stat.S_IFMT(mode)
    if file_type and not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
        _raise_bundle_error(
            FindingCode.ISO_BUNDLE_SYMLINK_REJECTED,
            f"non-regular archive entry is not allowed: {name}",
            "Use a message-set archive containing regular files and directories only.",
            source=name,
        )


def _assert_zip_member_sizes(info: zipfile.ZipInfo, name: str) -> None:
    if info.file_size > MAX_BUNDLE_MEMBER_BYTES:
        _raise_bundle_error(
            FindingCode.ISO_BUNDLE_OVERSIZED,
            f"{name} is {info.file_size} bytes; the limit is {MAX_BUNDLE_MEMBER_BYTES}",
            "Review the archive contents before raising the configured limit.",
            source=name,
        )
    if info.file_size and info.compress_size == 0:
        _raise_bundle_error(
            FindingCode.ISO_BUNDLE_ZIP_BOMB,
            f"{name} has an invalid compressed size of zero",
            "Reject archives with suspicious compression metadata.",
            source=name,
        )
    if info.compress_size and info.file_size / info.compress_size > MAX_BUNDLE_COMPRESSION_RATIO:
        _raise_bundle_error(
            FindingCode.ISO_BUNDLE_ZIP_BOMB,
            f"{name} exceeds compression ratio limit {MAX_BUNDLE_COMPRESSION_RATIO}",
            "Reject highly compressed archives unless they are reviewed manually.",
            source=name,
        )


def _assert_destination_containment(destination: Path, member_name: str) -> None:
    root = destination.resolve()
    target = (destination / member_name).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        _raise_bundle_error(
            FindingCode.ISO_BUNDLE_PATH_TRAVERSAL,
            f"archive path escapes the source cache: {member_name}",
            "Use ZIP entries with paths below the destination root.",
            source=member_name,
        )


def _safe_xsd_namespace(raw: bytes, *, source_name: str) -> str:
    try:
        return _xsd_target_namespace(raw, source_name=source_name)
    except ValueError as error:
        _raise_bundle_error(
            FindingCode.ISO_BUNDLE_BAD_XSD,
            str(error),
            "Only well-formed XML Schema files are accepted from a message-set archive.",
            source=source_name,
        )


def _message_definition_from_namespace(namespace: str) -> str | None:
    prefix = "urn:iso:std:iso:20022:tech:xsd:"
    if not namespace.startswith(prefix):
        return None
    definition = namespace.removeprefix(prefix)
    return definition if MESSAGE_ID_RE.fullmatch(definition) else None


def _raise_bundle_error(
    code: FindingCode, message: str, suggestion: str, *, source: str | None = None
) -> NoReturn:
    log = FindingLog()
    log.error(code, message, suggestion, source=source)
    raise CompilationError(log.findings)


def fetch_source(
    url: str,
    target: Path,
    *,
    expected_message_definition: str | None = None,
    expected_checksum: str | None = None,
    fetcher: Callable[[str], HttpFetchResponse] = _fetch_official_url,
) -> FetchResult:
    """Fetch one official-source artifact into an operator-controlled cache directory."""
    _assert_official_https_url(url)
    response = fetcher(url)
    checksum = _validate_xsd_fetch(
        response,
        expected_message_definition=expected_message_definition,
        expected_checksum=expected_checksum,
    )
    if target.suffix:
        path = target
    else:
        name = (
            f"{expected_message_definition}.xsd"
            if expected_message_definition
            else Path(urlparse(response.final_url).path).name or "source.xsd"
        )
        path = target / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.body)
    return FetchResult(
        url=url,
        final_url=response.final_url,
        path=path,
        checksum=checksum,
        content_type=response.content_type,
        size=len(response.body),
        redirects=response.redirects,
    )


def acquire_manifest_sources(
    manifest_path: Path,
    *,
    source_dir: Path,
    out_manifest: Path | None = None,
    fetcher: Callable[[str], HttpFetchResponse] = _fetch_official_url,
    bundle_fetcher: Callable[[str], HttpFetchResponse] = _fetch_official_bundle_url,
    catalogue_fetcher: Callable[[str], tuple[bytes, str]] = _fetch_bytes,
    allow_individual_fallback: bool = True,
) -> SourceManifest:
    """Acquire manifest XSDs, preferring local files and message-set bundles."""
    manifest = load_manifest(manifest_path)
    source_dir.mkdir(parents=True, exist_ok=True)
    bundle_indexes, message_sets, message_set_unresolved = _acquire_message_set_indexes(
        manifest,
        source_dir=source_dir,
        bundle_fetcher=bundle_fetcher,
    )
    acquired: list[SourceEntry] = []
    unresolved = [*manifest.unresolved, *message_set_unresolved]
    for entry in manifest.messages:
        try:
            local_result = _resolve_local_source(entry, source_dir)
        except Exception as error:  # noqa: BLE001 - continue to bundle/remote fallback.
            unresolved.append(f"{entry.message_definition}: local source rejected: {error}")
            local_result = None
        if local_result is not None:
            checksum, content_type, source_location = local_result
            acquired.append(
                entry.model_copy(
                    update={
                        "source_checksum": checksum,
                        "content_type": content_type,
                        "source_location": source_location,
                        "raw_source_committed": False,
                    }
                )
            )
            continue
        bundle_entry = bundle_indexes.get(entry.message_definition)
        if bundle_entry is not None:
            acquired.append(
                entry.model_copy(
                    update={
                        "source_checksum": bundle_entry.source_checksum,
                        "content_type": "application/xml",
                        "source_location": bundle_entry.source_file,
                        "raw_source_committed": False,
                    }
                )
            )
            continue
        if not allow_individual_fallback:
            unresolved.append(f"{entry.message_definition}: not resolved from message-set bundles")
            acquired.append(entry)
            continue
        xsd_url = entry.xsd_url
        if xsd_url is None:
            try:
                xsd_url = _resolve_manifest_xsd_url(entry, catalogue_fetcher)
            except Exception as error:  # noqa: BLE001 - per-entry acquisition report.
                unresolved.append(f"{entry.message_definition}: xsdUrl unresolved: {error}")
                acquired.append(entry)
                continue
        if xsd_url is None:
            unresolved.append(f"{entry.message_definition}: xsdUrl unresolved")
            acquired.append(entry)
            continue
        try:
            result = fetch_source(
                xsd_url,
                source_dir / (entry.source_location or f"{entry.message_definition}.xsd"),
                expected_message_definition=entry.message_definition,
                expected_checksum=entry.source_checksum,
                fetcher=fetcher,
            )
        except Exception as error:  # noqa: BLE001 - acquisition report stays per message.
            unresolved.append(f"{entry.message_definition}: {error}")
            acquired.append(entry)
            continue
        acquired.append(
            entry.model_copy(
                update={
                    "source_checksum": result.checksum,
                    "content_type": result.content_type,
                    "xsd_url": xsd_url,
                    "source_location": result.path.name,
                    "raw_source_committed": False,
                }
            )
        )
    updated = manifest.model_copy(
        update={
            "message_sets": message_sets,
            "messages": acquired,
            "unresolved": unresolved,
            "logical_messages": _group_logical_definitions(acquired),
        }
    )
    if out_manifest is not None:
        out_manifest.parent.mkdir(parents=True, exist_ok=True)
        out_manifest.write_text(manifest_yaml(updated), encoding="utf-8")
    return updated


def _acquire_message_set_indexes(
    manifest: SourceManifest,
    *,
    source_dir: Path,
    bundle_fetcher: Callable[[str], HttpFetchResponse],
) -> tuple[dict[str, BundleIndexEntry], list[MessageSetEntry], list[str]]:
    by_definition: dict[str, BundleIndexEntry] = {}
    updated_sets: list[MessageSetEntry] = []
    unresolved: list[str] = []
    seen: set[tuple[str, str | None, str | None]] = set()

    for message_set in manifest.message_sets:
        key = (
            message_set.message_set_name,
            message_set.download_url,
            message_set.bundle_location,
        )
        if key in seen:
            updated_sets.append(message_set)
            continue
        seen.add(key)
        try:
            if message_set.bundle_location:
                bundle_path = source_dir / message_set.bundle_location
                index = index_message_set_bundle(
                    bundle_path,
                    destination=source_dir,
                    message_set_name=message_set.message_set_name,
                )
                updated = message_set.model_copy(
                    update={"bundle_checksum": index.bundle_checksum, "raw_source_committed": False}
                )
            elif message_set.download_url:
                result = fetch_message_set_bundle(
                    message_set.download_url,
                    source_dir,
                    message_set_name=message_set.message_set_name,
                    fetcher=bundle_fetcher,
                )
                index = result.index
                updated = message_set.model_copy(
                    update={
                        "bundle_location": str(result.path.relative_to(source_dir)),
                        "bundle_checksum": result.checksum,
                        "raw_source_committed": False,
                    }
                )
            else:
                unresolved.append(
                    f"{message_set.message_set_name}: message-set download URL unavailable"
                )
                updated_sets.append(message_set)
                continue
        except CompilationError as error:
            unresolved.append(
                f"{message_set.message_set_name}: "
                + "; ".join(item.render() for item in error.findings)
            )
            updated_sets.append(message_set)
            continue
        except Exception as error:  # noqa: BLE001 - report per message set and continue.
            unresolved.append(f"{message_set.message_set_name}: {error}")
            updated_sets.append(message_set)
            continue
        for item in index.entries:
            by_definition.setdefault(item.exact_message_definition, item)
        updated_sets.append(updated)

    return by_definition, updated_sets, unresolved


def _resolve_local_source(entry: SourceEntry, source_dir: Path) -> tuple[str, str, str] | None:
    candidates = []
    if entry.source_location:
        candidates.append(source_dir / entry.source_location)
    candidates.append(source_dir / f"{entry.message_definition}.xsd")
    for path in candidates:
        if not path.is_file():
            continue
        raw = path.read_bytes()
        namespace = _xsd_target_namespace(raw, source_name=path.name)
        expected = _expected_namespace(entry.message_definition)
        if namespace != expected:
            raise ValueError(f"targetNamespace mismatch: expected {expected}, got {namespace}")
        checksum = "sha256:" + hashlib.sha256(raw).hexdigest()
        if entry.source_checksum and checksum != entry.source_checksum:
            raise ValueError(f"checksum mismatch: expected {entry.source_checksum}, got {checksum}")
        return checksum, "application/xml", path.name
    return None


def _resolve_manifest_xsd_url(
    entry: SourceEntry, fetcher: Callable[[str], tuple[bytes, str]]
) -> str | None:
    raw, _content_type = fetcher(entry.source_url)
    matches = parse_catalogue_html(
        raw.decode("utf-8", errors="replace"),
        source_url=entry.source_url,
        catalogue_state=entry.catalogue_state,
    )
    for item in matches:
        if item.message_definition == entry.message_definition:
            return item.xsd_url
    return None


def _source_path(entry: SourceEntry, source_dir: Path) -> Path | None:
    if entry.source_location is None:
        return None
    return (source_dir / entry.source_location).resolve()


def _verify_checksum(entry: SourceEntry, path: Path) -> str | None:
    actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    if entry.source_checksum and entry.source_checksum != actual:
        return f"checksum mismatch: manifest {entry.source_checksum}, file {actual}"
    return None


def run_scaleout(manifest_path: Path, *, source_dir: Path, candidates_dir: Path) -> BatchResult:
    """Compile every source in a manifest, isolating failures per message."""
    manifest = load_manifest(manifest_path)
    candidates_dir.mkdir(parents=True, exist_ok=True)
    result = BatchResult(manifest_path=manifest_path, candidates_dir=candidates_dir)

    for entry in manifest.messages:
        path = _source_path(entry, source_dir)
        if path is None:
            result.items.append(
                BatchItemResult(entry=entry, source_path=None, error="no sourceLocation")
            )
            continue
        if not path.is_file():
            result.items.append(
                BatchItemResult(entry=entry, source_path=path, error=f"{path.name} is missing")
            )
            continue
        checksum_error = _verify_checksum(entry, path)
        if checksum_error:
            result.items.append(
                BatchItemResult(entry=entry, source_path=path, error=checksum_error)
            )
            continue
        try:
            pack = compile_schema(
                path,
                bundle_root=source_dir,
                source_type=entry.source_type.value,
                root_name="Document",
            )
            target = candidates_dir / pack.file_name
            target.write_text(pack.yaml_text, encoding="utf-8")
            gates = validate_pack(pack.yaml_text, pack.version, path)
            result.items.append(
                BatchItemResult(
                    entry=entry,
                    source_path=path,
                    pack_path=target,
                    compiled=True,
                    gates=gates,
                    pack=pack,
                )
            )
        except CompilationError as error:
            result.items.append(
                BatchItemResult(
                    entry=entry,
                    source_path=path,
                    error="; ".join(item.render() for item in error.findings),
                )
            )
        except Exception as error:  # noqa: BLE001 - batch report, not traceback, is the UI.
            result.items.append(BatchItemResult(entry=entry, source_path=path, error=str(error)))
    return result


def render_batch_report(result: BatchResult) -> str:
    lines = [
        "# MX Scale-Out Batch Report",
        "",
        f"- Manifest: `{result.manifest_path}`",
        f"- Candidate directory: `{result.candidates_dir}`",
        f"- Attempted: **{result.attempted}**",
        f"- Compiled: **{result.compiled}**",
        f"- Six-gate passed: **{result.passed}**",
        f"- Failed: **{result.failed}**",
        "",
        "| Logical | Definition | Source checksum | Redistribution | Compile | Gates | Detail |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in result.items:
        gates = item.gates
        gate_text = "PASS" if gates and gates.passed else "FAIL" if gates else "NOT_RUN"
        detail = gates.render().replace("\n", "<br>") if gates else item.error
        source_checksum = (
            item.pack.source_checksum if item.pack else item.entry.source_checksum or ""
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    item.entry.logical_message,
                    item.entry.message_definition,
                    source_checksum,
                    item.entry.redistribution_status.value,
                    "PASS" if item.compiled else "FAIL",
                    gate_text,
                    detail.replace("|", "\\|"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)
