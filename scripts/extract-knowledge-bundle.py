#!/usr/bin/env python3
"""Extract a checksum-verified knowledge archive without paths, links, or devices."""

from __future__ import annotations

import argparse
import shutil
import stat
import tarfile
import zipfile
from pathlib import Path, PurePosixPath


def safe_name(raw: str) -> PurePosixPath:
    name = PurePosixPath(raw.replace("\\", "/"))
    if name.is_absolute() or ".." in name.parts or not name.parts:
        raise ValueError(f"Unsafe archive path: {raw!r}")
    if ":" in name.parts[0]:
        raise ValueError(f"Unsafe archive drive path: {raw!r}")
    return name


def destination(root: Path, raw: str) -> Path:
    relative = safe_name(raw)
    target = root.joinpath(*relative.parts)
    target.resolve().relative_to(root.resolve())
    return target


def extract_zip(archive: Path, root: Path, max_files: int, max_bytes: int) -> None:
    with zipfile.ZipFile(archive) as source:
        members = source.infolist()
        files = [member for member in members if not member.is_dir()]
        if len(files) > max_files or sum(member.file_size for member in files) > max_bytes:
            raise ValueError("Knowledge bundle exceeds the configured extraction limits")
        for member in members:
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError(f"Archive links are not allowed: {member.filename}")
            target = destination(root, member.filename)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open(member) as incoming, target.open("xb") as outgoing:
                shutil.copyfileobj(incoming, outgoing)


def extract_tar(archive: Path, root: Path, max_files: int, max_bytes: int) -> None:
    with tarfile.open(archive, mode="r:*") as source:
        members = source.getmembers()
        files = [member for member in members if member.isfile()]
        if len(files) > max_files or sum(member.size for member in files) > max_bytes:
            raise ValueError("Knowledge bundle exceeds the configured extraction limits")
        for member in members:
            if member.issym() or member.islnk() or member.isdev():
                raise ValueError(f"Archive links and devices are not allowed: {member.name}")
            target = destination(root, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ValueError(f"Unsupported archive entry: {member.name}")
            incoming = source.extractfile(member)
            if incoming is None:
                raise ValueError(f"Could not read archive entry: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with incoming, target.open("xb") as outgoing:
                shutil.copyfileobj(incoming, outgoing)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--max-files", type=int, default=20_000)
    parser.add_argument("--max-bytes", type=int, default=1_073_741_824)
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=False)
    if zipfile.is_zipfile(args.archive):
        extract_zip(args.archive, args.destination, args.max_files, args.max_bytes)
    elif tarfile.is_tarfile(args.archive):
        extract_tar(args.archive, args.destination, args.max_files, args.max_bytes)
    else:
        raise SystemExit("Knowledge bundle must be a ZIP or TAR archive")


if __name__ == "__main__":
    main()
