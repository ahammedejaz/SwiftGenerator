"""The ``KNOWLEDGE_PREVIEW`` lane at runtime: local Structure Packs loaded into the same
registry types the configured subset uses, kept in separate instances.

Runtime-safe: reads YAML packs and the knowledge database's structure table only. It never
imports the compiler, Prowide tooling, the MRG reader or a PDF library. Nothing here is
consulted unless a caller names the lane explicitly, and nothing here can promote a pack
into the configured registries.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path

from app.config import Settings, get_settings
from app.knowledge_base.models import Readiness, release_lane
from app.knowledge_base.paths import resolve_project_path
from app.knowledge_base.structures.mt_loader import load_mt_pack
from app.specifications.models import MessageSpecification
from app.studio.mx.models import MxMessageSpec
from app.studio.mx.registry import MxRegistry


@dataclass(frozen=True)
class StructureStatus:
    format: str
    message_type: str
    release: str
    readiness: Readiness
    blockers: tuple[str, ...]
    structure_source: str
    pack_checksum: str | None
    gates: dict[str, dict[str, object]]
    source_ids: tuple[str, ...]
    name: str
    business_area: str | None

    @property
    def generation_ready(self) -> bool:
        return self.readiness is Readiness.GENERATION_READY


class PreviewUnavailable(LookupError):
    """A preview message that cannot be generated, with the exact reason."""

    def __init__(self, code: str, message: str, *, blockers: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.code = code
        self.blockers = blockers


@dataclass
class PreviewRegistries:
    """Every local pack the knowledge sync produced, loaded once per process."""

    pack_dir: Path
    db_path: Path
    enabled: bool
    mt_specs: dict[tuple[str, str], MessageSpecification] = field(default_factory=dict)
    mx_registry: MxRegistry | None = None
    structures: dict[tuple[str, str, str], StructureStatus] = field(default_factory=dict)
    load_errors: list[str] = field(default_factory=list)

    # -- loading -------------------------------------------------------------------------

    def load(self) -> None:
        self.mt_specs = {}
        self.mx_registry = None
        self.structures = {}
        self.load_errors = []
        if not self.enabled:
            return
        self._load_structures()
        mt_dir = self.pack_dir / "mt"
        if mt_dir.is_dir():
            for path in sorted(mt_dir.glob("*.yaml")):
                try:
                    spec = load_mt_pack(path)
                except Exception as error:  # noqa: BLE001 - one bad pack must not hide the rest
                    self.load_errors.append(f"{path.name}: {type(error).__name__}")
                    continue
                self.mt_specs[(spec.message_type, spec.release or "")] = spec
        mx_dir = self.pack_dir / "mx"
        if mx_dir.is_dir() and any(mx_dir.glob("*.yaml")):
            try:
                self.mx_registry = MxRegistry(mx_dir)
            except Exception as error:  # noqa: BLE001 - reported, the lane stays empty
                self.load_errors.append(f"mx packs: {type(error).__name__}: {error}")

    def _load_structures(self) -> None:
        if not self.db_path.exists():
            return
        try:
            connection = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=5.0)
        except sqlite3.Error:
            return
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute("SELECT * FROM knowledge_structure").fetchall()
        except sqlite3.Error:
            rows = []
        finally:
            connection.close()
        for row in rows:
            detail = json.loads(row["detail"] or "{}")
            status = StructureStatus(
                format=str(row["format"]),
                message_type=str(row["message_type"]),
                release=str(row["release"]),
                readiness=Readiness(row["readiness"]),
                blockers=tuple(json.loads(row["blockers"] or "[]")),
                structure_source=str(row["structure_source"]),
                pack_checksum=row["pack_checksum"],
                gates=json.loads(row["gates"] or "{}"),
                source_ids=tuple(json.loads(row["source_ids"] or "[]")),
                name=str(detail.get("name") or row["message_type"]),
                business_area=detail.get("businessArea"),
            )
            self.structures[(status.format, status.message_type, status.release)] = status

    # -- MT ------------------------------------------------------------------------------

    def mt_releases(self, message_type: str) -> list[str]:
        wanted = message_type.strip().upper()
        return sorted(release for (mt, release) in self.mt_specs if mt == wanted)

    def resolve_mt(self, message_type: str, release: str | None) -> MessageSpecification:
        wanted = message_type.strip().upper()
        releases = self.mt_releases(wanted)
        if not releases:
            status = self._any_structure("MT", wanted)
            if status is not None:
                raise PreviewUnavailable(
                    "MESSAGE_GENERATION_NOT_READY",
                    f"{wanted} is known but not generation-ready ({status.readiness.value}).",
                    blockers=status.blockers,
                )
            raise PreviewUnavailable(
                "STRUCTURE_SOURCE_MISSING",
                f"{wanted} has no local Structure Pack in the knowledge-preview lane.",
            )
        chosen = release
        if chosen is None:
            ready = [
                item
                for item in releases
                if (status := self.structures.get(("MT", wanted, item))) is None
                or status.generation_ready
            ]
            candidates = ready or releases
            if len(candidates) == 1:
                chosen = candidates[0]
            else:
                # Among generation-ready releases the current-live one wins; otherwise the
                # caller must choose — a default is deterministic or it is not a default.
                live = [item for item in candidates if release_lane(item).value == "CURRENT_LIVE"]
                if len(live) == 1:
                    chosen = live[0]
                else:
                    raise PreviewUnavailable(
                        "KNOWLEDGE_RELEASE_REQUIRED",
                        f"{wanted} exists for releases {', '.join(releases)}; name one.",
                    )
        spec = self.mt_specs.get((wanted, chosen))
        if spec is None:
            raise PreviewUnavailable(
                "KNOWLEDGE_RELEASE_UNKNOWN",
                f"{wanted} has no {chosen} pack; available: {', '.join(releases)}.",
            )
        status = self.structures.get(("MT", wanted, chosen))
        if status is not None and not status.generation_ready:
            raise PreviewUnavailable(
                "MESSAGE_GENERATION_NOT_READY",
                f"{wanted} {chosen} is {status.readiness.value}; generation is disabled.",
                blockers=status.blockers,
            )
        return spec

    def known_mt(self, message_type: str) -> bool:
        return bool(self.mt_releases(message_type))

    # -- MX ------------------------------------------------------------------------------

    def resolve_mx(self, message_type: str) -> MxMessageSpec:
        if self.mx_registry is None or not self.mx_registry.known(message_type):
            status = self._any_structure("MX", message_type)
            if status is not None:
                raise PreviewUnavailable(
                    "MESSAGE_GENERATION_NOT_READY",
                    f"{message_type} is known but not generation-ready ({status.readiness.value}).",
                    blockers=status.blockers,
                )
            raise PreviewUnavailable(
                "STRUCTURE_SOURCE_MISSING",
                f"{message_type} has no compiled schema in the knowledge-preview lane.",
            )
        spec = self.mx_registry.get(message_type)
        status = self.structures.get(("MX", spec.message_type, spec.version))
        if status is not None and not status.generation_ready:
            raise PreviewUnavailable(
                "MESSAGE_GENERATION_NOT_READY",
                f"{spec.version} is {status.readiness.value}; generation is disabled.",
                blockers=status.blockers,
            )
        return spec

    def known_mx(self, message_type: str) -> bool:
        return self.mx_registry is not None and self.mx_registry.known(message_type)

    def mx_xsd_path(self, spec: MxMessageSpec) -> Path | None:
        candidate = self.pack_dir / "mx" / "xsd" / f"{spec.version}.xsd"
        return candidate if candidate.is_file() else None

    # -- status ----------------------------------------------------------------------------

    def _any_structure(self, format_: str, message_type: str) -> StructureStatus | None:
        wanted = message_type.strip().upper() if format_ == "MT" else message_type.strip().lower()
        matches = [
            status
            for (fmt, mt, release), status in self.structures.items()
            if fmt == format_ and (mt == wanted or release == wanted)
        ]
        return matches[0] if matches else None

    def status_for(self, format_: str, message_type: str, release: str) -> StructureStatus | None:
        return self.structures.get((format_, message_type, release))


_LOCK = threading.Lock()
_REGISTRIES: PreviewRegistries | None = None


def preview_registries(settings: Settings | None = None) -> PreviewRegistries:
    """The process-wide preview lane, built on first use and rebuilt by :func:`reload`."""
    global _REGISTRIES
    with _LOCK:
        if _REGISTRIES is None:
            resolved = settings or get_settings()
            _REGISTRIES = PreviewRegistries(
                pack_dir=resolve_project_path(resolved.knowledge_pack_dir),
                db_path=resolve_project_path(resolved.knowledge_db_path),
                enabled=resolved.knowledge_enabled,
            )
            _REGISTRIES.load()
        return _REGISTRIES


def reload_preview(settings: Settings | None = None) -> PreviewRegistries:
    global _REGISTRIES
    with _LOCK:
        _REGISTRIES = None
    return preview_registries(settings)
