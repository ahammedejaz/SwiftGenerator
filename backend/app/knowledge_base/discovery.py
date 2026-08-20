"""Find every candidate source under the knowledge roots, safely.

Filenames are never trusted for identity — that is ``identify.py``'s job, from content. This
module only answers "which files exist, what are their bytes, and is it safe to read them":
no symlink is followed, nothing outside a root is touched, ZIP members are extracted into an
ignored cache under strict limits, and an original file is never written to.
"""

from __future__ import annotations

import hashlib
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

SUPPORTED_SUFFIXES = frozenset(
    {".pdf", ".txt", ".md", ".markdown", ".html", ".htm", ".xsd", ".xml", ".zip"}
)
#: Compressed bytes to uncompressed bytes. A legitimate PDF or XSD never approaches this.
MAX_ZIP_RATIO = 100
HASH_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class DiscoveredFile:
    """One readable candidate. ``relative_path`` is the only path that ever leaves here."""

    relative_path: str
    absolute_path: Path
    byte_size: int
    suffix: str
    #: ``archive.zip!member.pdf`` members carry the archive's relative path here.
    archive_path: str | None = None


@dataclass(frozen=True)
class SkippedFile:
    relative_path: str
    reason: str
    detail: str = ""


@dataclass
class Discovery:
    files: list[DiscoveredFile]
    skipped: list[SkippedFile]
    roots_missing: list[str]


def discover(
    roots: list[Path],
    *,
    cache_dir: Path,
    max_source_bytes: int,
    max_zip_member_bytes: int,
    max_zip_total_bytes: int,
) -> Discovery:
    files: list[DiscoveredFile] = []
    skipped: list[SkippedFile] = []
    missing: list[str] = []
    for index, root in enumerate(roots):
        if not root.exists():
            missing.append(root.name)
            continue
        if not root.is_dir():
            skipped.append(SkippedFile(root.name, "ROOT_NOT_A_DIRECTORY"))
            continue
        prefix = "" if len(roots) == 1 else f"{root.name}/"
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = sorted(
                name
                for name in dirnames
                if not name.startswith(".") and not _is_symlink(Path(dirpath) / name)
            )
            for filename in sorted(filenames):
                if filename.startswith("."):
                    continue
                absolute = Path(dirpath) / filename
                relative = prefix + absolute.relative_to(root).as_posix()
                if _is_symlink(absolute):
                    skipped.append(SkippedFile(relative, "SKIPPED_SYMLINK"))
                    continue
                if not _within(absolute, root):
                    skipped.append(SkippedFile(relative, "OUTSIDE_ROOT"))
                    continue
                suffix = absolute.suffix.lower()
                if suffix not in SUPPORTED_SUFFIXES:
                    skipped.append(SkippedFile(relative, "UNSUPPORTED_EXTENSION", suffix))
                    continue
                try:
                    size = absolute.stat().st_size
                except OSError as error:
                    skipped.append(SkippedFile(relative, "UNREADABLE", type(error).__name__))
                    continue
                if size > max_source_bytes:
                    skipped.append(SkippedFile(relative, "TOO_LARGE", f"{size} bytes"))
                    continue
                if suffix == ".zip":
                    members, zip_skipped = _extract_zip(
                        absolute,
                        relative,
                        cache_dir=cache_dir,
                        max_member_bytes=max_zip_member_bytes,
                        max_total_bytes=max_zip_total_bytes,
                    )
                    files.extend(members)
                    skipped.extend(zip_skipped)
                    continue
                files.append(DiscoveredFile(relative, absolute, size, suffix))
        del index
    return Discovery(files=files, skipped=skipped, roots_missing=missing)


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(HASH_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _is_symlink(path: Path) -> bool:
    try:
        return path.is_symlink()
    except OSError:
        return True


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError):
        return False
    return True


def _safe_member_name(name: str) -> str | None:
    """The member's path inside the cache, or None when it must not be extracted."""
    if not name or "\x00" in name:
        return None
    normalised = name.replace("\\", "/")
    if normalised.startswith("/") or len(normalised) > 1 and normalised[1] == ":":
        return None
    parts = PurePosixPath(normalised).parts
    if not parts or any(part in {"..", ""} for part in parts):
        return None
    return "/".join(parts)


def _extract_zip(
    archive: Path,
    relative: str,
    *,
    cache_dir: Path,
    max_member_bytes: int,
    max_total_bytes: int,
) -> tuple[list[DiscoveredFile], list[SkippedFile]]:
    files: list[DiscoveredFile] = []
    skipped: list[SkippedFile] = []
    try:
        archive_hash = sha256_of_file(archive)
        with zipfile.ZipFile(archive) as bundle:
            infos = bundle.infolist()
            total_uncompressed = sum(info.file_size for info in infos)
            total_compressed = max(1, sum(info.compress_size for info in infos))
            if total_uncompressed > max_total_bytes:
                skipped.append(SkippedFile(relative, "ZIP_TOO_LARGE", f"{total_uncompressed}"))
                return [], skipped
            if total_uncompressed / total_compressed > MAX_ZIP_RATIO:
                skipped.append(SkippedFile(relative, "ZIP_RATIO_EXCEEDED"))
                return [], skipped
            target_root = cache_dir / archive_hash[:16]
            for info in infos:
                member_label = f"{relative}!{info.filename}"
                if info.is_dir():
                    continue
                safe = _safe_member_name(info.filename)
                if safe is None:
                    skipped.append(SkippedFile(member_label, "ZIP_UNSAFE_MEMBER"))
                    continue
                mode = (info.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    skipped.append(SkippedFile(member_label, "ZIP_SYMLINK_MEMBER"))
                    continue
                suffix = PurePosixPath(safe).suffix.lower()
                if suffix == ".zip":
                    skipped.append(SkippedFile(member_label, "ZIP_NESTED_NOT_EXPANDED"))
                    continue
                if suffix not in SUPPORTED_SUFFIXES:
                    skipped.append(SkippedFile(member_label, "UNSUPPORTED_EXTENSION", suffix))
                    continue
                if info.file_size > max_member_bytes:
                    skipped.append(SkippedFile(member_label, "ZIP_MEMBER_TOO_LARGE"))
                    continue
                destination = target_root / safe
                if not _under(destination, target_root):
                    skipped.append(SkippedFile(member_label, "ZIP_UNSAFE_MEMBER"))
                    continue
                if not destination.exists() or destination.stat().st_size != info.file_size:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    written = 0
                    with bundle.open(info) as source, destination.open("wb") as sink:
                        while True:
                            chunk = source.read(HASH_CHUNK)
                            if not chunk:
                                break
                            written += len(chunk)
                            if written > max_member_bytes:
                                sink.close()
                                destination.unlink(missing_ok=True)
                                skipped.append(SkippedFile(member_label, "ZIP_MEMBER_TOO_LARGE"))
                                break
                            sink.write(chunk)
                    if not destination.exists():
                        continue
                files.append(
                    DiscoveredFile(
                        relative_path=member_label,
                        absolute_path=destination,
                        byte_size=destination.stat().st_size,
                        suffix=suffix,
                        archive_path=relative,
                    )
                )
    except (zipfile.BadZipFile, OSError, RuntimeError) as error:
        skipped.append(SkippedFile(relative, "ZIP_UNREADABLE", type(error).__name__))
    return files, skipped


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True
