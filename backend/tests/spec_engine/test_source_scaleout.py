"""Phase 3 source manifests and batch scale-out stay honest and isolated."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.spec_engine.diagnostics import FindingLog
from app.spec_engine.mapper import map_message
from app.spec_engine.source import (
    HttpFetchResponse,
    RedistributionStatus,
    acquire_manifest_sources,
    discover_messages,
    fetch_source,
    load_manifest,
    manifest_yaml,
    parse_catalogue_html,
    run_scaleout,
)
from app.spec_engine.xsd_loader import load_schema_set
from app.spec_engine.xsd_reader import SchemaReader

CATALOGUE_HTML = """
<html><body>
  <h4>Payments Clearing and Settlement</h4>
  <span>Message ID (scheme)</span><span>Message name</span>
  <span>Submitting organisation</span><span>Downloads</span>
  <span>pacs.008.001.14</span>
  <span>FIToFICustomerCreditTransferV14</span>
  <span>SWIFT</span>
  <a href="/catalogue/messages/pacs.008.001.14.xsd">XSD</a>
  <h4>Securities Events</h4>
  <span>seev.031.001.16</span>
  <span>CorporateActionNotificationV16</span>
  <span>SWIFT</span>
  <a href="https://www.iso20022.org/catalogue/messages/seev.031.001.16.xsd">XSD</a>
</body></html>
"""


def test_catalogue_parser_resolves_current_versions_and_xsd_links() -> None:
    messages = parse_catalogue_html(
        CATALOGUE_HTML,
        source_url="https://www.iso20022.org/iso-20022-message-definitions?search=pacs.008",
    )

    pacs = next(item for item in messages if item.logical_message == "pacs.008")
    assert pacs.message_definition == "pacs.008.001.14"
    assert pacs.message_name == "FIToFICustomerCreditTransferV14"
    assert pacs.business_area == "PAYMENTS_CLEARING_SETTLEMENT"
    assert pacs.xsd_url == "https://www.iso20022.org/catalogue/messages/pacs.008.001.14.xsd"

    seev = next(item for item in messages if item.logical_message == "seev.031")
    assert seev.business_area == "SECURITIES_EVENTS"


def test_discovery_manifest_defaults_to_unknown_redistribution(tmp_path: Path) -> None:
    def fetcher(url: str) -> tuple[bytes, str]:
        assert url == "https://www.iso20022.org/iso-20022-message-definitions?search=pacs.008"
        return CATALOGUE_HTML.encode(), "text/html"

    manifest = discover_messages(
        ["pacs.008"],
        fetcher=fetcher,
        retrieved_at=datetime(2026, 8, 19, tzinfo=UTC),
    )

    entry = manifest.messages[0]
    assert entry.message_definition == "pacs.008.001.14"
    assert [item.model_dump(by_alias=True) for item in manifest.logical_messages] == [
        {
            "logicalMessage": "pacs.008",
            "currentDefinitions": ["pacs.008.001.14"],
            "archivedDefinitions": [],
        }
    ]
    assert entry.redistribution_status is RedistributionStatus.UNKNOWN
    assert entry.derived_metadata_redistribution_status is RedistributionStatus.UNKNOWN
    assert entry.raw_source_committed is False
    assert load_manifest(_write_manifest(tmp_path, manifest)).messages[0] == entry


def test_non_iso_urls_are_refused_for_structural_sources(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="iso20022.org"):
        fetch_source("https://example.com/pacs.008.001.14.xsd", tmp_path)


def test_octet_stream_valid_xsd_is_accepted_from_trusted_host(tmp_path: Path) -> None:
    response = _response(_schema_bytes("pacs.008.001.14"))

    result = fetch_source(
        "https://www.iso20022.org/message/23500/download",
        tmp_path,
        expected_message_definition="pacs.008.001.14",
        fetcher=lambda _url: response,
    )

    assert result.path.name == "pacs.008.001.14.xsd"
    assert result.content_type == "application/octet-stream"
    assert result.checksum == "sha256:" + hashlib.sha256(response.body).hexdigest()
    assert result.path.read_bytes() == response.body


@pytest.mark.parametrize(
    ("body", "match"),
    [
        (b"\x00\x01binary", "does not look like XML"),
        (b"<html><body>not found</body></html>", "root is not xs:schema"),
    ],
)
def test_octet_stream_non_xsd_is_rejected(
    tmp_path: Path, body: bytes, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        fetch_source(
            "https://www.iso20022.org/message/23500/download",
            tmp_path,
            expected_message_definition="pacs.008.001.14",
            fetcher=lambda _url: _response(body),
        )


def test_redirect_within_iso_is_allowed(tmp_path: Path) -> None:
    result = fetch_source(
        "https://www.iso20022.org/message/23500/download",
        tmp_path,
        expected_message_definition="pacs.008.001.14",
        fetcher=lambda _url: _response(
            _schema_bytes("pacs.008.001.14"),
            final_url="https://iso20022.org/message/23500/download",
            redirects=("https://iso20022.org/message/23500/download",),
        ),
    )

    assert result.redirects == ("https://iso20022.org/message/23500/download",)


@pytest.mark.parametrize(
    ("final_url", "redirects"),
    [
        ("https://example.com/pacs.008.001.14.xsd", ()),
        (
            "https://www.iso20022.org/message/23500/download",
            ("https://example.com/pacs.008.001.14.xsd",),
        ),
    ],
)
def test_redirect_to_another_domain_is_rejected(
    tmp_path: Path, final_url: str, redirects: tuple[str, ...]
) -> None:
    with pytest.raises(ValueError, match="HTTPS iso20022.org"):
        fetch_source(
            "https://www.iso20022.org/message/23500/download",
            tmp_path,
            expected_message_definition="pacs.008.001.14",
            fetcher=lambda _url: _response(
                _schema_bytes("pacs.008.001.14"),
                final_url=final_url,
                redirects=redirects,
            ),
        )


def test_http_downgrade_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="HTTPS iso20022.org"):
        fetch_source(
            "https://www.iso20022.org/message/23500/download",
            tmp_path,
            expected_message_definition="pacs.008.001.14",
            fetcher=lambda _url: _response(
                _schema_bytes("pacs.008.001.14"),
                final_url="http://www.iso20022.org/message/23500/download",
            ),
        )


def test_target_namespace_mismatch_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="targetNamespace mismatch"):
        fetch_source(
            "https://www.iso20022.org/message/23500/download",
            tmp_path,
            expected_message_definition="pacs.008.001.14",
            fetcher=lambda _url: _response(_schema_bytes("pacs.009.001.13")),
        )


def test_checksum_mismatch_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="checksum mismatch"):
        fetch_source(
            "https://www.iso20022.org/message/23500/download",
            tmp_path,
            expected_message_definition="pacs.008.001.14",
            expected_checksum="sha256:" + "0" * 64,
            fetcher=lambda _url: _response(_schema_bytes("pacs.008.001.14")),
        )


def test_oversized_body_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="limit"):
        fetch_source(
            "https://www.iso20022.org/message/23500/download",
            tmp_path,
            expected_message_definition="pacs.008.001.14",
            fetcher=lambda _url: _response(b" " * (5 * 1024 * 1024 + 1)),
        )


def test_manifest_acquisition_records_checksums_without_committing_sources(
    tmp_path: Path,
) -> None:
    manifest = _write_text(
        tmp_path / "manifest.yaml",
        """
manifestVersion: mx-source-manifest/1
retrievedAt: '2026-08-19T00:00:00+00:00'
sourceUrl: https://www.iso20022.org/iso-20022-message-definitions
messages:
  - logicalMessage: pacs.008
    messageDefinition: pacs.008.001.14
    sourceUrl: https://www.iso20022.org/iso-20022-message-definitions?search=pacs.008
    xsdUrl: https://www.iso20022.org/message/23500/download
    sourceLocation: pacs.008.001.14.xsd
""",
    )

    updated = acquire_manifest_sources(
        manifest,
        source_dir=tmp_path / "sources",
        out_manifest=tmp_path / "acquired.yaml",
        fetcher=lambda _url: _response(_schema_bytes("pacs.008.001.14")),
    )

    entry = updated.messages[0]
    assert entry.source_checksum == "sha256:" + hashlib.sha256(
        _schema_bytes("pacs.008.001.14")
    ).hexdigest()
    assert entry.raw_source_committed is False
    assert (tmp_path / "sources" / "pacs.008.001.14.xsd").exists()
    assert load_manifest(tmp_path / "acquired.yaml").messages[0].source_checksum


def test_manifest_acquisition_resolves_missing_xsd_url_from_catalogue(
    tmp_path: Path,
) -> None:
    manifest = _write_text(
        tmp_path / "manifest.yaml",
        """
manifestVersion: mx-source-manifest/1
retrievedAt: '2026-08-19T00:00:00+00:00'
sourceUrl: https://www.iso20022.org/iso-20022-message-definitions
messages:
  - logicalMessage: pacs.008
    messageDefinition: pacs.008.001.14
    sourceUrl: https://www.iso20022.org/iso-20022-message-definitions?search=pacs.008
    sourceLocation: pacs.008.001.14.xsd
""",
    )

    updated = acquire_manifest_sources(
        manifest,
        source_dir=tmp_path / "sources",
        fetcher=lambda url: _response(
            _schema_bytes("pacs.008.001.14"), final_url=url
        ),
        catalogue_fetcher=lambda _url: (CATALOGUE_HTML.encode(), "text/html"),
    )

    assert updated.messages[0].xsd_url == (
        "https://www.iso20022.org/catalogue/messages/pacs.008.001.14.xsd"
    )
    assert updated.messages[0].source_checksum


def test_batch_scaleout_compiles_good_sources_and_isolates_bad_ones(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    source = _schema_for(sources, "pacs.008.001.14")
    checksum = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        f"""
manifestVersion: mx-source-manifest/1
retrievedAt: '2026-08-19T00:00:00+00:00'
sourceUrl: https://www.iso20022.org/iso-20022-message-definitions
messages:
  - logicalMessage: pacs.008
    messageDefinition: pacs.008.001.14
    messageName: SyntheticTestInstructionV01
    messageSet: Synthetic
    businessArea: OTHER
    sourceUrl: https://www.iso20022.org/iso-20022-message-definitions?search=pacs.008
    xsdUrl: https://www.iso20022.org/catalogue/messages/pacs.008.001.14.xsd
    sourceLocation: pacs.008.001.14.xsd
    sourceChecksum: '{checksum}'
  - logicalMessage: pacs.009
    messageDefinition: pacs.009.001.13
    sourceUrl: https://www.iso20022.org/iso-20022-message-definitions?search=pacs.009
    sourceLocation: missing.xsd
""",
        encoding="utf-8",
    )

    result = run_scaleout(manifest, source_dir=sources, candidates_dir=tmp_path / "candidates")

    assert result.attempted == 2
    assert result.compiled == 1
    assert result.passed == 1
    assert result.failed == 1
    assert result.items[0].pack_path and result.items[0].pack_path.exists()
    assert result.items[0].gates and result.items[0].gates.passed
    assert "missing.xsd is missing" in result.items[1].error


def test_business_area_mapping_covers_phase_3_families(tmp_path: Path) -> None:
    expected = {
        "pacs.008.001.14": "PAYMENTS_CLEARING_SETTLEMENT",
        "pain.001.001.13": "PAYMENT_INITIATION",
        "camt.053.001.13": "CASH_MANAGEMENT",
        "sese.023.001.11": "SECURITIES_SETTLEMENT",
        "semt.002.001.12": "SECURITIES_MANAGEMENT",
        "seev.031.001.16": "SECURITIES_EVENTS",
    }
    for version, area in expected.items():
        schema_set = load_schema_set(_schema_for(tmp_path, version))
        reader_log = FindingLog()
        ir = SchemaReader(schema_set, reader_log).read(schema_set.entry_namespace())
        spec, log = map_message(
            ir,
            source_type="OPERATOR_SUPPLIED_XSD",
            source_reference=f"TEST-{version}",
            source_location=f"{version}.xsd",
            source_checksum="sha256:" + "0" * 64,
            root_name="Document",
        )
        assert not reader_log.blocked
        assert not log.blocked
        assert spec["businessArea"] == area


def _write_manifest(tmp_path: Path, manifest) -> Path:  # type: ignore[no-untyped-def]
    path = tmp_path / "mx-source-manifest.yaml"
    path.write_text(manifest_yaml(manifest), encoding="utf-8")
    return path


def _schema_for(tmp_path: Path, version: str) -> Path:
    path = tmp_path / f"{version}.xsd"
    path.write_bytes(_schema_bytes(version))
    return path


def _schema_bytes(version: str) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
  xmlns="urn:iso:std:iso:20022:tech:xsd:{version}"
  targetNamespace="urn:iso:std:iso:20022:tech:xsd:{version}"
  elementFormDefault="qualified">
  <xs:element name="Document" type="Document"/>
  <xs:complexType name="Document">
    <xs:sequence><xs:element name="Msg" type="Msg"/></xs:sequence>
  </xs:complexType>
  <xs:complexType name="Msg">
    <xs:sequence><xs:element name="Id" type="xs:string"/></xs:sequence>
  </xs:complexType>
</xs:schema>
""".encode()


def _response(
    body: bytes,
    *,
    content_type: str = "application/octet-stream",
    final_url: str = "https://www.iso20022.org/message/23500/download",
    redirects: tuple[str, ...] = (),
) -> HttpFetchResponse:
    return HttpFetchResponse(
        body=body,
        content_type=content_type,
        final_url=final_url,
        redirects=redirects,
    )


def _write_text(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path
