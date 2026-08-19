"""Phase 3 source manifests and batch scale-out stay honest and isolated."""

from __future__ import annotations

import hashlib
import io
import stat
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.spec_engine import source as source_module
from app.spec_engine.diagnostics import CompilationError, FindingCode, FindingLog
from app.spec_engine.mapper import map_message
from app.spec_engine.source import (
    HttpFetchResponse,
    RedistributionStatus,
    acquire_manifest_sources,
    discover_messages,
    fetch_message_set_bundle,
    fetch_source,
    index_message_set_bundle_bytes,
    load_manifest,
    manifest_yaml,
    parse_catalogue_html,
    parse_message_sets_html,
    run_scaleout,
)
from app.spec_engine.xsd_loader import load_schema_set
from app.spec_engine.xsd_reader import SchemaReader

CATALOGUE_HTML = """
<html><body>
  <h4>Payments Clearing and Settlement</h4>
  <span>Message ID (scheme)</span><span>Message name</span>
  <span>Submitting organisation</span><span>Downloads</span>
  <span>Last Updated</span><span>19 March 2026</span>
  <a href="/message-set/1249/download">Download complete message set</a>
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


def test_message_set_parser_resolves_official_download_links() -> None:
    message_sets = parse_message_sets_html(
        CATALOGUE_HTML,
        source_url="https://www.iso20022.org/iso-20022-message-definitions?search=pacs.008",
    )

    assert len(message_sets) == 1
    assert message_sets[0].message_set_name == "Payments Clearing and Settlement"
    assert message_sets[0].download_url == "https://www.iso20022.org/message-set/1249/download"
    assert message_sets[0].catalogue_observation == "Download complete message set"


def test_message_set_parser_skips_bah_and_variant_labels() -> None:
    message_sets = parse_message_sets_html(
        """
        <h4>Corporate Actions</h4>
        <a href="/bah">BAH</a>
        <span>Has variants</span>
        <span>Last Updated</span><span>17 March 2026</span>
        <a href="/message-set/1241/download">Download complete message set</a>
        """,
        source_url="https://www.iso20022.org/iso-20022-message-definitions?search=seev",
    )

    assert message_sets[0].message_set_name == "Corporate Actions"


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


def test_message_set_bundle_valid_zip_is_indexed_and_materialised(tmp_path: Path) -> None:
    body = _zip_bytes(
        {
            "doc/readme.txt": b"reviewed metadata",
            "schemas/pacs.008.001.14.xsd": _schema_bytes("pacs.008.001.14"),
        }
    )

    result = fetch_message_set_bundle(
        "https://www.iso20022.org/message-set/1249/download",
        tmp_path / "sources",
        message_set_name="Payments Clearing and Settlement",
        fetcher=lambda _url: _response(
            body,
            final_url="https://www.iso20022.org/message-set/1249/download",
            content_type="application/zip",
        ),
    )

    assert result.index.entries[0].exact_message_definition == "pacs.008.001.14"
    assert result.index.entries[0].source_file == "pacs.008.001.14.xsd"
    assert (tmp_path / "sources" / "pacs.008.001.14.xsd").read_bytes() == _schema_bytes(
        "pacs.008.001.14"
    )
    assert result.path == tmp_path / "sources" / "bundles" / "payments-clearing-and-settlement.zip"


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("../pacs.008.001.14.xsd", FindingCode.ISO_BUNDLE_PATH_TRAVERSAL),
        ("/pacs.008.001.14.xsd", FindingCode.ISO_BUNDLE_PATH_TRAVERSAL),
        ("C:/pacs.008.001.14.xsd", FindingCode.ISO_BUNDLE_PATH_TRAVERSAL),
    ],
)
def test_message_set_bundle_rejects_unsafe_paths(
    tmp_path: Path, name: str, code: FindingCode
) -> None:
    with pytest.raises(CompilationError) as error:
        index_message_set_bundle_bytes(
            _zip_bytes({name: _schema_bytes("pacs.008.001.14")}),
            destination=tmp_path,
            message_set_name="Payments Clearing and Settlement",
        )

    assert error.value.findings[0].code is code


def test_message_set_bundle_rejects_symlink(tmp_path: Path) -> None:
    info = zipfile.ZipInfo("schemas/pacs.008.001.14.xsd")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16

    with pytest.raises(CompilationError) as error:
        index_message_set_bundle_bytes(
            _zip_bytes({info: b"target"}),
            destination=tmp_path,
            message_set_name="Payments Clearing and Settlement",
        )

    assert error.value.findings[0].code is FindingCode.ISO_BUNDLE_SYMLINK_REJECTED


def test_message_set_bundle_rejects_oversized_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(source_module, "MAX_BUNDLE_MEMBER_BYTES", 64)

    with pytest.raises(CompilationError) as error:
        index_message_set_bundle_bytes(
            _zip_bytes({"schemas/pacs.008.001.14.xsd": _schema_bytes("pacs.008.001.14")}),
            destination=tmp_path,
            message_set_name="Payments Clearing and Settlement",
        )

    assert error.value.findings[0].code is FindingCode.ISO_BUNDLE_OVERSIZED


def test_message_set_bundle_rejects_too_many_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(source_module, "MAX_BUNDLE_FILE_COUNT", 1)

    with pytest.raises(CompilationError) as error:
        index_message_set_bundle_bytes(
            _zip_bytes({"a.txt": b"a", "b.txt": b"b"}),
            destination=tmp_path,
            message_set_name="Payments Clearing and Settlement",
        )

    assert error.value.findings[0].code is FindingCode.ISO_BUNDLE_OVERSIZED


def test_message_set_bundle_rejects_zip_bomb_ratio(tmp_path: Path) -> None:
    with pytest.raises(CompilationError) as error:
        index_message_set_bundle_bytes(
            _zip_bytes({"schemas/bomb.txt": b"0" * 50000}, compression=zipfile.ZIP_DEFLATED),
            destination=tmp_path,
            message_set_name="Payments Clearing and Settlement",
        )

    assert error.value.findings[0].code is FindingCode.ISO_BUNDLE_ZIP_BOMB


def test_message_set_bundle_rejects_nested_archive(tmp_path: Path) -> None:
    with pytest.raises(CompilationError) as error:
        index_message_set_bundle_bytes(
            _zip_bytes({"nested/archive.zip": _zip_bytes({"a.txt": b"a"})}),
            destination=tmp_path,
            message_set_name="Payments Clearing and Settlement",
        )

    assert error.value.findings[0].code is FindingCode.ISO_BUNDLE_NESTED_ARCHIVE_REJECTED


def test_message_set_bundle_rejects_duplicate_entries(tmp_path: Path) -> None:
    with pytest.raises(CompilationError) as error:
        index_message_set_bundle_bytes(
            _zip_bytes(
                [
                    ("schemas/pacs.008.001.14.xsd", _schema_bytes("pacs.008.001.14")),
                    ("schemas/pacs.008.001.14.xsd", _schema_bytes("pacs.008.001.14")),
                ]
            ),
            destination=tmp_path,
            message_set_name="Payments Clearing and Settlement",
        )

    assert error.value.findings[0].code is FindingCode.ISO_BUNDLE_DUPLICATE_ENTRY


@pytest.mark.parametrize(
    "body",
    [
        b"\x00\x01binary",
        b"<html><body>not a schema</body></html>",
        b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x>&e;</x>',
    ],
)
def test_message_set_bundle_rejects_bad_xsd_content(tmp_path: Path, body: bytes) -> None:
    with pytest.raises(CompilationError) as error:
        index_message_set_bundle_bytes(
            _zip_bytes({"schemas/pacs.008.001.14.xsd": body}),
            destination=tmp_path,
            message_set_name="Payments Clearing and Settlement",
        )

    assert error.value.findings[0].code is FindingCode.ISO_BUNDLE_BAD_XSD


def test_message_set_bundle_rejects_filename_namespace_mismatch(tmp_path: Path) -> None:
    with pytest.raises(CompilationError) as error:
        index_message_set_bundle_bytes(
            _zip_bytes({"schemas/pacs.008.001.14.xsd": _schema_bytes("pacs.009.001.13")}),
            destination=tmp_path,
            message_set_name="Payments Clearing and Settlement",
        )

    assert error.value.findings[0].code is FindingCode.ISO_BUNDLE_BAD_XSD


def test_manifest_acquisition_reuses_one_bundle_for_many_definitions(tmp_path: Path) -> None:
    definitions = [f"pacs.{index:03d}.001.01" for index in range(1, 30)]
    manifest = _write_text(
        tmp_path / "manifest.yaml",
        "manifestVersion: mx-source-manifest/1\n"
        "retrievedAt: '2026-08-19T00:00:00+00:00'\n"
        "sourceUrl: https://www.iso20022.org/iso-20022-message-definitions\n"
        "messageSets:\n"
        "  - messageSetName: Payments Clearing and Settlement\n"
        "    messageSetSourcePage: https://www.iso20022.org/iso-20022-message-definitions?search=pacs\n"
        "    messageSetDownloadUrl: https://www.iso20022.org/message-set/1249/download\n"
        "messages:\n"
        + "\n".join(
            [
                f"  - logicalMessage: pacs.{index:03d}\n"
                f"    messageDefinition: {definition}\n"
                "    messageSet: Payments Clearing and Settlement\n"
                "    sourceUrl: https://www.iso20022.org/iso-20022-message-definitions?search=pacs\n"
                f"    sourceLocation: {definition}.xsd"
                for index, definition in enumerate(definitions, start=1)
            ]
        )
        + "\n",
    )
    bundle = _zip_bytes(
        {f"schemas/{definition}.xsd": _schema_bytes(definition) for definition in definitions}
    )
    bundle_calls = 0
    individual_calls = 0

    def bundle_fetcher(url: str) -> HttpFetchResponse:
        nonlocal bundle_calls
        bundle_calls += 1
        assert url == "https://www.iso20022.org/message-set/1249/download"
        return _response(
            bundle,
            content_type="application/zip",
            final_url="https://www.iso20022.org/message-set/1249/download",
        )

    def individual_fetcher(url: str) -> HttpFetchResponse:
        nonlocal individual_calls
        individual_calls += 1
        return _response(_schema_bytes("pacs.001.001.01"), final_url=url)

    updated = acquire_manifest_sources(
        manifest,
        source_dir=tmp_path / "sources",
        bundle_fetcher=bundle_fetcher,
        fetcher=individual_fetcher,
    )

    assert bundle_calls == 1
    assert individual_calls == 0
    assert len([item for item in updated.messages if item.source_checksum]) == 29
    assert updated.message_sets[0].bundle_checksum


def test_bundle_only_acquisition_skips_individual_fallback(tmp_path: Path) -> None:
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
""",
    )
    individual_calls = 0

    def individual_fetcher(url: str) -> HttpFetchResponse:
        nonlocal individual_calls
        individual_calls += 1
        return _response(_schema_bytes("pacs.008.001.14"), final_url=url)

    updated = acquire_manifest_sources(
        manifest,
        source_dir=tmp_path / "sources",
        fetcher=individual_fetcher,
        allow_individual_fallback=False,
    )

    assert individual_calls == 0
    assert updated.messages[0].source_checksum is None
    assert updated.unresolved == [
        "pacs.008.001.14: not resolved from message-set bundles"
    ]


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


def _zip_bytes(
    entries: dict[str | zipfile.ZipInfo, bytes] | list[tuple[str | zipfile.ZipInfo, bytes]],
    *,
    compression: int = zipfile.ZIP_STORED,
) -> bytes:
    buffer = io.BytesIO()
    items = entries.items() if isinstance(entries, dict) else entries
    with zipfile.ZipFile(buffer, mode="w", compression=compression) as archive:
        for name, body in items:
            archive.writestr(name, body)
    return buffer.getvalue()


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
