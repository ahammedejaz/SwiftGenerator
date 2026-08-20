"""Source discovery: what is read, what is refused, and why."""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest

from app.knowledge_base.discovery import DiscoveredFile, discover, sha256_of_file
from app.knowledge_base.identify import SourceUnreadable, parse_and_identify
from app.knowledge_base.models import SourceClassification, SourceFormat, SourceType

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "knowledge"


def _discover(root: Path, cache: Path) -> tuple[list[str], dict[str, str]]:
    result = discover(
        [root],
        cache_dir=cache,
        max_source_bytes=10 * 1024 * 1024,
        max_zip_member_bytes=1024 * 1024,
        max_zip_total_bytes=4 * 1024 * 1024,
    )
    return sorted(f.relative_path for f in result.files), {
        s.relative_path: s.reason for s in result.skipped
    }


def test_nested_folders_are_walked_and_paths_stay_relative(tmp_path: Path) -> None:
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "b" / "note.md").write_text("# MT998 note\nMT998 MT998\n")
    (tmp_path / "top.txt").write_text("plain")
    files, skipped = _discover(tmp_path, tmp_path / "cache")
    assert files == ["a/b/note.md", "top.txt"]
    assert not any(str(tmp_path) in path for path in files)
    assert skipped == {}


def test_unsupported_extensions_hidden_files_and_symlinks_are_skipped_not_read(
    tmp_path: Path,
) -> None:
    (tmp_path / "ok.txt").write_text("x")
    (tmp_path / "binary.exe").write_bytes(b"MZ\x00")
    (tmp_path / ".hidden.txt").write_text("x")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("secret")
    os.symlink(outside, tmp_path / "link.txt")
    files, skipped = _discover(tmp_path, tmp_path / "cache")
    assert files == ["ok.txt"]
    assert skipped["binary.exe"] == "UNSUPPORTED_EXTENSION"
    assert skipped["link.txt"] == "SKIPPED_SYMLINK"


def test_same_bytes_under_two_names_share_a_checksum_and_a_rename_is_unchanged(
    tmp_path: Path,
) -> None:
    (tmp_path / "one.md").write_text("# MT998\nMT998 text\n")
    (tmp_path / "two.md").write_text("# MT998\nMT998 text\n")
    (tmp_path / "three.md").write_text("# MT998\ndifferent MT998 text\n")
    hashes = {name: sha256_of_file(tmp_path / name) for name in ("one.md", "two.md", "three.md")}
    assert hashes["one.md"] == hashes["two.md"]
    assert hashes["three.md"] != hashes["one.md"]


def test_a_zip_is_extracted_only_into_the_cache_and_unsafe_members_are_refused(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("docs/mt998-note.md", "# MT998 note\nMT998 MT998\n")
        bundle.writestr("../escape.md", "outside")
        bundle.writestr("/abs.md", "absolute")
        bundle.writestr("nested.zip", b"PK\x03\x04")
        bundle.writestr("tool.exe", b"MZ")
        info = zipfile.ZipInfo("link.md")
        info.external_attr = 0o120777 << 16
        bundle.writestr(info, "/etc/passwd")
    files, skipped = _discover(tmp_path, tmp_path / "cache")
    assert files == ["bundle.zip!docs/mt998-note.md"]
    assert skipped["bundle.zip!../escape.md"] == "ZIP_UNSAFE_MEMBER"
    assert skipped["bundle.zip!/abs.md"] == "ZIP_UNSAFE_MEMBER"
    assert skipped["bundle.zip!nested.zip"] == "ZIP_NESTED_NOT_EXPANDED"
    assert skipped["bundle.zip!tool.exe"] == "UNSUPPORTED_EXTENSION"
    assert skipped["bundle.zip!link.md"] == "ZIP_SYMLINK_MEMBER"
    extracted = list((tmp_path / "cache").rglob("*.md"))
    assert len(extracted) == 1 and extracted[0].name == "mt998-note.md"
    assert not (tmp_path / "escape.md").exists()


def test_a_zip_bomb_is_refused_by_ratio_and_size(tmp_path: Path) -> None:
    archive = tmp_path / "bomb.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("big.txt", "0" * (3 * 1024 * 1024))
    _files, skipped = _discover(tmp_path, tmp_path / "cache")
    assert skipped["bomb.zip"] in {"ZIP_RATIO_EXCEEDED", "ZIP_TOO_LARGE"}


def test_a_bad_pdf_is_unreadable_not_fatal(tmp_path: Path) -> None:
    item = DiscoveredFile("bad.pdf", tmp_path / "bad.pdf", 4, ".pdf")
    with pytest.raises(SourceUnreadable) as caught:
        parse_and_identify(item, b"%PDF-1.4 garbage")
    assert caught.value.code in {"KNOWLEDGE_SOURCE_UNREADABLE", "KNOWLEDGE_SOURCE_UNSUPPORTED"}


def test_a_bad_xsd_and_a_doctype_are_refused(tmp_path: Path) -> None:
    item = DiscoveredFile("bad.xsd", tmp_path / "bad.xsd", 4, ".xsd")
    with pytest.raises(SourceUnreadable):
        parse_and_identify(item, b"<xs:schema")
    with pytest.raises(SourceUnreadable) as caught:
        parse_and_identify(
            item,
            b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
            b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>',
        )
    assert caught.value.code == "KNOWLEDGE_SOURCE_UNSUPPORTED"


def test_identity_comes_from_content_not_filename(tmp_path: Path) -> None:
    guide = (FIXTURES / "guides" / "mt999-synthetic-guide-sr2026.txt").read_bytes()
    item = DiscoveredFile("completely-misleading-name.txt", tmp_path / "x", len(guide), ".txt")
    parsed = parse_and_identify(item, guide)
    assert parsed.identity.source_type is SourceType.MT_MESSAGE_REFERENCE_GUIDE
    assert parsed.identity.message_type == "MT999"
    assert parsed.identity.release == "SR2026"
    assert parsed.identity.source_id == "SWIFT-MT-SR2026-MT999-MRG"
    assert parsed.classification is SourceClassification.SYNTHETIC_FIXTURE
    assert parsed.page_count == 11


def test_the_second_release_of_the_same_guide_is_a_distinct_identity() -> None:
    older = (FIXTURES / "guides" / "mt999-synthetic-guide-sr2026.txt").read_bytes()
    newer = (FIXTURES / "guides" / "mt999-synthetic-guide-sr2027.txt").read_bytes()
    a = parse_and_identify(DiscoveredFile("a", FIXTURES, 1, ".txt"), older)
    b = parse_and_identify(DiscoveredFile("b", FIXTURES, 1, ".txt"), newer)
    assert (a.identity.message_type, a.identity.release) == ("MT999", "SR2026")
    assert (b.identity.message_type, b.identity.release) == ("MT999", "SR2027")
    assert a.identity.source_id != b.identity.source_id


def test_an_xsd_is_identified_from_its_namespace() -> None:
    raw = (FIXTURES / "schemas" / "test.001.001.01.xsd").read_bytes()
    parsed = parse_and_identify(DiscoveredFile("whatever.xsd", FIXTURES, 1, ".xsd"), raw)
    assert parsed.identity.source_type is SourceType.ISO20022_XSD
    assert parsed.identity.format is SourceFormat.MX
    assert parsed.identity.message_type == "test.001"
    assert parsed.identity.message_version == "test.001.001.01"
    assert parsed.classification is SourceClassification.SYNTHETIC_FIXTURE


def test_a_note_binds_to_the_message_it_is_dominated_by_and_an_ambiguous_one_is_flagged() -> None:
    note = (FIXTURES / "notes" / "mt998-usage-note.md").read_bytes()
    parsed = parse_and_identify(DiscoveredFile("n.md", FIXTURES, 1, ".md"), note)
    assert parsed.identity.message_type == "MT998"
    assert parsed.identity.format is SourceFormat.MT
    mixed = b"MT103 and MT202 and pacs.008.001.14 all appear once each here."
    parsed = parse_and_identify(DiscoveredFile("m.md", FIXTURES, 1, ".md"), mixed)
    assert parsed.identity.message_type is None
    assert "KNOWLEDGE_IDENTITY_AMBIGUOUS" in parsed.identity.problems


def test_a_licensed_looking_guide_without_the_synthetic_declaration_is_classified_licensed() -> (
    None
):
    guide = (FIXTURES / "guides" / "mt999-synthetic-guide-sr2026.txt").read_text()
    guide = guide.replace("KNOWLEDGE-SOURCE-CLASSIFICATION: SYNTHETIC_FIXTURE\n", "")
    parsed = parse_and_identify(DiscoveredFile("g.txt", FIXTURES, 1, ".txt"), guide.encode())
    assert parsed.classification is SourceClassification.OFFICIAL_SWIFT_MT_STANDARDS_MATERIAL
