"""The loader treats every schema as untrusted XML, and proves it."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.spec_engine.diagnostics import CompilationError, FindingCode
from app.spec_engine.xsd_loader import MAX_FILE_BYTES, load_schema_set

NS = "urn:iso:std:iso:20022:tech:xsd:test.001.001.01"


def _schema(body: str = "", extra_attrs: str = "") -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
        f'targetNamespace="{NS}" xmlns="{NS}" elementFormDefault="qualified"{extra_attrs}>'
        f"{body}</xs:schema>"
    )


def _codes(error: CompilationError) -> set[FindingCode]:
    return {finding.code for finding in error.findings}


def test_a_doctype_is_refused_outright(tmp_path: Path) -> None:
    # XXE and billion-laughs both arrive through a DOCTYPE; its presence alone is refused.
    hostile = (
        '<?xml version="1.0"?><!DOCTYPE schema [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        + _schema()[38:]
    )
    path = tmp_path / "evil.xsd"
    path.write_text(hostile, encoding="utf-8")
    with pytest.raises(CompilationError) as caught:
        load_schema_set(path)
    assert FindingCode.XSD_DOCTYPE_FORBIDDEN in _codes(caught.value)


def test_a_remote_schema_location_is_blocked(tmp_path: Path) -> None:
    body = '<xs:include schemaLocation="https://attacker.example/common.xsd"/>'
    path = tmp_path / "remote.xsd"
    path.write_text(_schema(body), encoding="utf-8")
    with pytest.raises(CompilationError) as caught:
        load_schema_set(path)
    assert FindingCode.XSD_REMOTE_FETCH_BLOCKED in _codes(caught.value)


def test_path_traversal_out_of_the_bundle_is_blocked(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    outside = tmp_path / "outside.xsd"
    outside.write_text(_schema(), encoding="utf-8")
    entry = bundle / "entry.xsd"
    entry.write_text(_schema('<xs:include schemaLocation="../outside.xsd"/>'), "utf-8")
    with pytest.raises(CompilationError) as caught:
        load_schema_set(entry, bundle)
    assert FindingCode.XSD_IMPORT_OUTSIDE_BUNDLE in _codes(caught.value)


def test_a_symlink_that_leaves_the_bundle_is_blocked(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    secret = tmp_path / "secret.xsd"
    secret.write_text(_schema(), encoding="utf-8")
    (bundle / "link.xsd").symlink_to(secret)
    entry = bundle / "entry.xsd"
    entry.write_text(_schema('<xs:include schemaLocation="link.xsd"/>'), "utf-8")
    with pytest.raises(CompilationError) as caught:
        load_schema_set(entry, bundle)
    assert FindingCode.XSD_IMPORT_OUTSIDE_BUNDLE in _codes(caught.value)


def test_a_missing_import_names_the_namespace(tmp_path: Path) -> None:
    body = (
        '<xs:import namespace="urn:example:common" schemaLocation="common.xsd"/>'
    )
    path = tmp_path / "entry.xsd"
    path.write_text(_schema(body), encoding="utf-8")
    with pytest.raises(CompilationError) as caught:
        load_schema_set(path)
    findings = caught.value.findings
    assert any(
        finding.code is FindingCode.XSD_IMPORT_NOT_FOUND and "common.xsd" in finding.message
        for finding in findings
    )


def test_an_oversized_schema_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "big.xsd"
    path.write_text(_schema("<!-- " + "A" * (MAX_FILE_BYTES + 100) + " -->"), "utf-8")
    with pytest.raises(CompilationError) as caught:
        load_schema_set(path)
    assert FindingCode.XSD_SOURCE_TOO_LARGE in _codes(caught.value)


def test_malformed_xml_is_a_named_finding_not_a_stack_trace(tmp_path: Path) -> None:
    path = tmp_path / "broken.xsd"
    path.write_text("<xs:schema unclosed", encoding="utf-8")
    with pytest.raises(CompilationError) as caught:
        load_schema_set(path)
    assert FindingCode.XSD_NOT_WELL_FORMED in _codes(caught.value)


def test_a_non_schema_document_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "notaschema.xsd"
    path.write_text("<html><body>hello</body></html>", encoding="utf-8")
    with pytest.raises(CompilationError) as caught:
        load_schema_set(path)
    assert FindingCode.XSD_UNSUPPORTED_CONSTRUCT in _codes(caught.value)


def test_cyclic_includes_terminate(tmp_path: Path) -> None:
    a = tmp_path / "a.xsd"
    b = tmp_path / "b.xsd"
    a.write_text(_schema('<xs:include schemaLocation="b.xsd"/>'), encoding="utf-8")
    b.write_text(_schema('<xs:include schemaLocation="a.xsd"/>'), encoding="utf-8")
    schema_set = load_schema_set(a)
    assert len(schema_set.by_namespace[NS]) == 2


def test_a_missing_source_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(CompilationError) as caught:
        load_schema_set(tmp_path / "nowhere.xsd")
    assert FindingCode.XSD_SOURCE_NOT_FOUND in _codes(caught.value)
