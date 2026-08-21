"""The committed knowledge-source manifest: present, real bytes, recorded hashes, nothing
unlisted — on a scratch folder for the mechanics, and on the repository's own
``swiftKnowledgeBase/`` wherever Git LFS has delivered it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import PROJECT_ROOT
from app.knowledge_base import manifest


def _folder(tmp_path: Path) -> Path:
    root = tmp_path / "kb"
    (root / "MT").mkdir(parents=True)
    (root / "MX").mkdir()
    (root / "MT" / "guide.pdf").write_bytes(b"%PDF-1.4 synthetic bytes " * 40)
    (root / "MX" / "schema.xsd").write_text("<xs:schema/>", encoding="utf-8")
    return root


def test_a_manifest_lists_every_source_by_content(tmp_path: Path) -> None:
    root = _folder(tmp_path)
    payload = manifest.build_manifest(root, identities={})
    assert payload["fileCount"] == 2
    assert {item["relativePath"] for item in payload["sources"]} == {
        "MT/guide.pdf",
        "MX/schema.xsd",
    }
    assert all(len(item["sha256"]) == 64 for item in payload["sources"])
    assert all(item["sourceId"] is None for item in payload["sources"])  # never from a name
    manifest.manifest_path(root).write_text(json.dumps(payload), encoding="utf-8")
    verdict = manifest.verify_manifest(root)
    assert verdict.passed and verdict.verified == 2


def test_verification_names_tampering_pointers_and_strays(tmp_path: Path) -> None:
    root = _folder(tmp_path)
    manifest.manifest_path(root).write_text(
        json.dumps(manifest.build_manifest(root, identities={})), encoding="utf-8"
    )
    (root / "MT" / "guide.pdf").write_bytes(b"%PDF-1.4 OTHER bytes     " * 40)
    (root / "MX" / "schema.xsd").write_text(
        "version https://git-lfs.github.com/spec/v1\noid sha256:00\nsize 12\n", encoding="utf-8"
    )
    (root / "MT" / "notes.txt").write_text("stray", encoding="utf-8")
    verdict = manifest.verify_manifest(root)
    codes = sorted(problem.split(":")[0] for problem in verdict.problems)
    assert codes == ["LFS_POINTER_NOT_FETCHED", "SOURCE_HASH_MISMATCH", "SOURCE_NOT_IN_MANIFEST"]


def test_a_missing_manifest_is_a_named_problem(tmp_path: Path) -> None:
    verdict = manifest.verify_manifest(_folder(tmp_path))
    assert verdict.problems and verdict.problems[0].startswith("MANIFEST_MISSING")


def test_the_committed_knowledge_base_matches_its_manifest() -> None:
    """On a clone where ``git lfs pull`` ran, every committed source is intact. On a
    runner that checked out pointers only, the check is skipped by name — never passed."""
    root = PROJECT_ROOT / "swiftKnowledgeBase"
    if not manifest.manifest_path(root).exists():
        pytest.skip("no committed knowledge base on this checkout")
    files = manifest.source_files(root)
    if files and all(manifest.is_lfs_pointer(path) for path in files):
        pytest.skip("Git LFS content not fetched on this checkout (pointer files only)")
    verdict = manifest.verify_manifest(root)
    assert verdict.passed, verdict.problems[:10]
    assert verdict.verified == verdict.listed >= 1
