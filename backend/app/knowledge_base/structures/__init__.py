"""Local Structure Packs compiled from source evidence.

MT packs come from Prowide structural evidence reconciled with SWIFT Message Reference
Guide Format Specifications; MX packs come from operator-supplied XSDs through the existing
compiler. Both are written to an ignored directory, carry their provenance, and load into
the same runtime types as the configured subset — in a separate, explicit
``KNOWLEDGE_PREVIEW`` lane.
"""

from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.knowledge_base.db import KnowledgeDatabase
from app.knowledge_base.models import SyncProgress


def compile_all(
    settings: Settings,
    database: KnowledgeDatabase,
    pack_dir: Path,
    report: SyncProgress,
    *,
    include_prowide: bool = True,
    prowide_filter: tuple[str, ...] | None = None,
) -> None:
    """Compile every structure the indexed sources support. Failures are recorded per
    message and never stop the run."""
    from app.knowledge_base.structures.mt_pack import compile_mt_structures
    from app.knowledge_base.structures.mx_pack import compile_mx_structures

    compile_mt_structures(
        settings,
        database,
        pack_dir / "mt",
        report,
        include_prowide=include_prowide,
        prowide_filter=prowide_filter,
    )
    compile_mx_structures(settings, database, pack_dir / "mx", report)
