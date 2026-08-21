from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from app.config import CONFIG_ROOT
from app.mapping.models import MappingIdentity, MappingPack


class MappingRegistry:
    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory or CONFIG_ROOT / "mappings"
        self._packs = self._load()

    def _load(self) -> tuple[MappingPack, ...]:
        packs: list[MappingPack] = []
        seen: set[tuple[str, str]] = set()
        for path in sorted(self._directory.glob("*.yaml")):
            pack = MappingPack.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
            key = (pack.pack_id, pack.version)
            if key in seen:
                raise ValueError(f"Duplicate Mapping Pack: {pack.pack_id} {pack.version}")
            seen.add(key)
            packs.append(pack)
        return tuple(packs)

    def targets(self, source: MappingIdentity) -> list[MappingPack]:
        return [pack for pack in self._packs if pack.source == source]

    def resolve(
        self,
        source: MappingIdentity,
        target: MappingIdentity,
        pack_id: str | None = None,
    ) -> MappingPack | None:
        matches = [
            pack
            for pack in self._packs
            if pack.source == source
            and pack.target == target
            and (pack_id is None or pack.pack_id == pack_id)
        ]
        if len(matches) > 1:
            raise ValueError("Mapping Pack selection is ambiguous; supply mappingPackId")
        return matches[0] if matches else None


@lru_cache(maxsize=1)
def mapping_registry() -> MappingRegistry:
    return MappingRegistry()
