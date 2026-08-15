from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def test_clean_migration_allows_workflow_report_without_scenario(tmp_path: Path) -> None:
    backend_root = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "clean-migration.db"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{database_path}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO reports
                (id, scenario_id, report_payload, artifact_path, created_at)
            VALUES (?, NULL, ?, ?, ?)
            """,
            (
                "synthetic-workflow-report",
                json.dumps({"workflowBulk": True}),
                "/tmp/synthetic-workflow-report.zip",
                datetime.now(UTC).isoformat(),
            ),
        )
        connection.commit()
        stored = connection.execute(
            "SELECT scenario_id FROM reports WHERE id = ?",
            ("synthetic-workflow-report",),
        ).fetchone()

    assert stored == (None,)
