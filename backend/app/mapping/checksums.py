"""Recompute the specification checksums a Mapping Pack pins.

A pack records the checksum of the source and target message specifications it was written
against, and :meth:`MappingService._validate_pack` refuses to execute when either has
moved. That gate is what stops a pack silently mapping into a structure that no longer has
the element it names — but it also means one change to the specification *projection*
invalidates every pack at once, and the fix is mechanical rather than a judgement.

Offline only. Nothing here runs in the request path.
"""

from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path

import yaml

from app.config import CONFIG_ROOT
from app.mapping.models import MappingPack
from app.mapping.registry import RELATIONSHIPS_FILE
from app.studio.catalogue import message_spec

#: ``sourceStructureChecksum`` / ``targetStructureChecksum`` at the top level of the file.
#: Rewritten in place rather than by re-serialising the YAML, so a pack keeps its comments,
#: its key order and its line wrapping — a pack is read by a reviewer, not only by a parser.
_LINE = "(?m)^({key}: )[a-f0-9]{{64}}$"


def _checksum(pack: MappingPack, *, target: bool) -> str:
    identity = pack.target if target else pack.source
    spec = (
        message_spec(identity.format, identity.release or identity.message_type, identity.lane)
        if target
        else message_spec(
            identity.format, identity.message_type, identity.lane, identity.release
        )
    )
    return sha256(
        spec.model_dump_json(by_alias=True, exclude={"capability"}).encode("utf-8")
    ).hexdigest()


def refresh_pack_checksums(
    *, write: bool, directory: Path | None = None
) -> list[tuple[Path, str, str, str]]:
    """Every pack whose pinned checksum no longer matches, optionally rewritten.

    Returns one entry per stale checksum: the file, which of the two it is, the recorded
    value and the current one.
    """
    folder = directory or CONFIG_ROOT / "mappings"
    stale: list[tuple[Path, str, str, str]] = []
    for path in sorted(folder.glob("*.yaml")):
        if path.name == RELATIONSHIPS_FILE:
            continue
        text = path.read_text(encoding="utf-8")
        pack = MappingPack.model_validate(yaml.safe_load(text))
        for key, recorded, current in (
            (
                "sourceStructureChecksum",
                pack.source_structure_checksum,
                _checksum(pack, target=False),
            ),
            (
                "targetStructureChecksum",
                pack.target_structure_checksum,
                _checksum(pack, target=True),
            ),
        ):
            if recorded == current:
                continue
            stale.append((path, key, recorded, current))
            if write:
                text = re.sub(_LINE.format(key=key), r"\g<1>" + current, text, count=1)
        if write:
            path.write_text(text, encoding="utf-8")
    return stale
