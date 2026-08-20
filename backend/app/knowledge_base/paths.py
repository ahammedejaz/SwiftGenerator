"""Where the knowledge base lives on disk, resolved once from settings.

Kept apart from the indexer so the runtime lane can find packs and the database without
importing anything that reads source documents.
"""

from __future__ import annotations

from pathlib import Path

from app.config import PROJECT_ROOT, Settings


def resolve_project_path(configured: str) -> Path:
    path = Path(configured).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def knowledge_roots(settings: Settings) -> list[Path]:
    roots: list[Path] = []
    for item in settings.knowledge_source_dir.split(","):
        candidate = item.strip()
        if candidate:
            roots.append(resolve_project_path(candidate))
    return roots


def knowledge_db_path(settings: Settings) -> Path:
    return resolve_project_path(settings.knowledge_db_path)


def knowledge_pack_dir(settings: Settings) -> Path:
    return resolve_project_path(settings.knowledge_pack_dir)
