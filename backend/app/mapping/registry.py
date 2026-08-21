from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from app.config import CONFIG_ROOT
from app.mapping.models import MappingIdentity, MappingPack, MappingRelationship

RELATIONSHIPS_FILE = "relationships.yaml"


class MappingRegistry:
    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory or CONFIG_ROOT / "mappings"
        self._packs = self._load()
        self._relationships = self._load_relationships()

    def _load_relationships(self) -> tuple[MappingRelationship, ...]:
        path = self._directory / RELATIONSHIPS_FILE
        if not path.exists():
            return ()
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        found = [
            MappingRelationship.model_validate(item) for item in payload.get("relationships", [])
        ]
        ids = [item.relationship_id for item in found]
        if len(ids) != len(set(ids)):
            raise ValueError("Mapping relationship ids must be unique")
        return tuple(found)

    @property
    def packs(self) -> tuple[MappingPack, ...]:
        return self._packs

    @property
    def relationships(self) -> tuple[MappingRelationship, ...]:
        return self._relationships

    def relationships_for(self, source: MappingIdentity) -> list[MappingRelationship]:
        """Relationships whose source is this identity, or whose statement also covers
        this message in the same format and lane (MT205's scope for MT200–MT203)."""
        found: list[MappingRelationship] = []
        for item in self._relationships:
            same_lane = (
                item.source.format is source.format
                and item.source.lane is source.lane
                and (item.source.release is None or item.source.release == source.release)
            )
            if not same_lane:
                continue
            if item.source.message_type == source.message_type or (
                source.message_type in item.also_covers
            ):
                found.append(item)
        return found

    def _load(self) -> tuple[MappingPack, ...]:
        packs: list[MappingPack] = []
        seen: set[tuple[str, str]] = set()
        for path in sorted(self._directory.glob("*.yaml")):
            if path.name == RELATIONSHIPS_FILE:
                continue
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
