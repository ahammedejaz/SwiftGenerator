"""The committed knowledge-source manifest: what the repository carries, by content.

``swiftKnowledgeBase/source-manifest.json`` lists every source file the repository
commits through Git LFS — path, byte size, SHA-256 and the identity the knowledge base
read from its content (format, message, release, source id). It is written from a synced
knowledge database (``python -m app.knowledge_base manifest --write``) and verified
anywhere (``--check``): every listed file is present, holds real bytes rather than an LFS
pointer, and hashes as recorded; nothing unlisted sits beside them. ``--identify`` also
re-reads each file's identity, which needs the PDF parser and is a local check.

Nothing here contains source text. The manifest is the contract that lets a fresh clone
prove, before any sync, that ``git lfs pull`` delivered the knowledge base intact.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import PROJECT_ROOT

MANIFEST_SCHEMA = "knowledge-source-manifest/1"
MANIFEST_NAME = "source-manifest.json"
LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"
#: File types the manifest lists; anything else beside them is reported, never hidden.
SOURCE_SUFFIXES = frozenset({".pdf", ".xsd", ".xml", ".zip", ".txt", ".md", ".html", ".htm"})
IGNORED_NAMES = frozenset({".DS_Store", MANIFEST_NAME, "README.md"})


@dataclass(frozen=True)
class ManifestEntry:
    relative_path: str
    bytes: int
    sha256: str
    source_id: str | None
    format: str | None
    message_type: str | None
    release: str | None
    document_type: str | None

    def as_payload(self) -> dict[str, Any]:
        return {
            "relativePath": self.relative_path,
            "bytes": self.bytes,
            "sha256": self.sha256,
            "sourceId": self.source_id,
            "format": self.format,
            "messageType": self.message_type,
            "release": self.release,
            "documentType": self.document_type,
        }


@dataclass
class ManifestVerdict:
    listed: int = 0
    verified: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.problems


def knowledge_root(root: Path | None = None) -> Path:
    """The committed folder beside the code; in a container, the first mounted root."""
    if root is not None:
        return root
    committed = PROJECT_ROOT / "swiftKnowledgeBase"
    if (committed / MANIFEST_NAME).exists():
        return committed
    from app.config import get_settings
    from app.knowledge_base.paths import knowledge_roots

    roots = knowledge_roots(get_settings())
    return roots[0] if roots else committed


def manifest_path(root: Path | None = None) -> Path:
    return knowledge_root(root) / MANIFEST_NAME


def is_lfs_pointer(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(LFS_POINTER_PREFIX)) == LFS_POINTER_PREFIX
    except OSError:
        return False


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_files(root: Path | None = None) -> list[Path]:
    folder = knowledge_root(root)
    found: list[Path] = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.is_symlink() or path.name in IGNORED_NAMES:
            continue
        if path.name.startswith("."):
            continue
        found.append(path)
    return found


def build_manifest(
    root: Path | None = None, *, identities: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """The manifest for the folder as it is. ``identities`` maps a sha256 to the identity
    the knowledge database recorded for those bytes; a file the database has not seen is
    listed with its hash and no identity, never guessed from its name."""
    folder = knowledge_root(root)
    entries: list[ManifestEntry] = []
    for path in source_files(folder):
        digest = sha256_of(path)
        identity = (identities or {}).get(digest, {})
        entries.append(
            ManifestEntry(
                relative_path=path.relative_to(folder).as_posix(),
                bytes=path.stat().st_size,
                sha256=digest,
                source_id=identity.get("sourceId"),
                format=identity.get("format"),
                message_type=identity.get("messageType"),
                release=identity.get("release"),
                document_type=identity.get("documentType"),
            )
        )
    return {
        "schemaVersion": MANIFEST_SCHEMA,
        "root": "swiftKnowledgeBase",
        "fileCount": len(entries),
        "totalBytes": sum(item.bytes for item in entries),
        "sources": [item.as_payload() for item in entries],
    }


def identities_from_database() -> dict[str, dict[str, Any]]:
    """``sha256 -> identity`` for every source the local knowledge database has read."""
    from app.knowledge_base.service import knowledge_service

    found: dict[str, dict[str, Any]] = {}
    if not knowledge_service.indexed:
        return found
    for record in knowledge_service.database.sources(include_deleted=True):
        found[record.checksum.removeprefix("sha256:")] = {
            "sourceId": record.source_id,
            "format": record.format.value,
            "messageType": record.message_type,
            "release": record.release,
            "documentType": record.document_type.value,
        }
    return found


def write_manifest(root: Path | None = None) -> Path:
    payload = build_manifest(root, identities=identities_from_database())
    target = manifest_path(root)
    target.write_text(json.dumps(payload, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    return target


def load_manifest(root: Path | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(manifest_path(root).read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != MANIFEST_SCHEMA:
        raise ValueError(f"manifest is {payload.get('schemaVersion')}, not {MANIFEST_SCHEMA}")
    return payload


def verify_manifest(root: Path | None = None, *, identify: bool = False) -> ManifestVerdict:
    """Every listed file present with real bytes and the recorded hash; nothing unlisted."""
    folder = knowledge_root(root)
    verdict = ManifestVerdict()
    if not manifest_path(folder).exists():
        verdict.problems.append(f"MANIFEST_MISSING: {manifest_path(folder)}")
        return verdict
    payload = load_manifest(folder)
    listed = {str(item["relativePath"]): item for item in payload["sources"]}
    verdict.listed = len(listed)
    for relative, item in listed.items():
        path = folder / relative
        if not path.is_file():
            verdict.problems.append(f"SOURCE_MISSING: {relative}")
            continue
        if is_lfs_pointer(path):
            verdict.problems.append(
                f"LFS_POINTER_NOT_FETCHED: {relative} is a Git LFS pointer; run `git lfs pull`"
            )
            continue
        if path.stat().st_size != int(item["bytes"]):
            verdict.problems.append(
                f"SOURCE_SIZE_MISMATCH: {relative} is {path.stat().st_size} bytes, "
                f"manifest says {item['bytes']}"
            )
            continue
        digest = sha256_of(path)
        if digest != item["sha256"]:
            verdict.problems.append(f"SOURCE_HASH_MISMATCH: {relative}")
            continue
        if identify and item.get("sourceId"):
            found = _identify(path)
            if found != (item.get("format"), item.get("messageType"), item.get("release")):
                verdict.problems.append(
                    f"SOURCE_IDENTITY_MISMATCH: {relative} reads as {found}, manifest says "
                    f"({item.get('format')}, {item.get('messageType')}, {item.get('release')})"
                )
                continue
        verdict.verified += 1
    present = {path.relative_to(folder).as_posix() for path in source_files(folder)}
    for extra in sorted(present - set(listed)):
        verdict.problems.append(f"SOURCE_NOT_IN_MANIFEST: {extra}")
    return verdict


def _identify(path: Path) -> tuple[str | None, str | None, str | None]:
    from app.knowledge_base.discovery import DiscoveredFile
    from app.knowledge_base.identify import parse_and_identify

    item = DiscoveredFile(
        relative_path=path.name,
        absolute_path=path,
        byte_size=path.stat().st_size,
        suffix=path.suffix.lower(),
    )
    parsed = parse_and_identify(item, path.read_bytes())
    identity = parsed.identity
    return identity.format.value, identity.message_type, identity.release
