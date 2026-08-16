"""The documented setup must work on a machine that has never run this application.

`make install` then `make migrate` is the first thing anybody does with a fresh clone. It
failed on every one of them: alembic builds its own engine and never imports
`app.persistence.database`, which was the only place that created the folder a file-backed
SQLite database lives in. On any machine that had already run the app the folder existed, so
the defect was invisible to everyone who could have noticed it.
"""

from __future__ import annotations

from pathlib import Path

from app.config import ensure_database_directory


def test_a_file_backed_database_gets_its_folder_created(tmp_path: Path) -> None:
    target = tmp_path / "data" / "nested" / "studio.db"
    assert not target.parent.exists()

    ensure_database_directory(f"sqlite:///{target}")

    assert target.parent.is_dir()


def test_calling_it_twice_is_harmless(tmp_path: Path) -> None:
    """`make migrate` runs after the app may already have started."""
    target = tmp_path / "data" / "studio.db"

    ensure_database_directory(f"sqlite:///{target}")
    ensure_database_directory(f"sqlite:///{target}")

    assert target.parent.is_dir()


def test_an_in_memory_database_needs_no_folder() -> None:
    ensure_database_directory("sqlite://")
    ensure_database_directory("sqlite:///:memory:")


def test_a_server_database_is_left_alone() -> None:
    """PostgreSQL has no local path to create, and inventing one would be nonsense."""
    ensure_database_directory("postgresql+psycopg://user:pw@localhost:5432/studio")


def test_the_migration_environment_prepares_the_folder_too() -> None:
    """The regression itself: alembic's env.py must call this, because it builds its own
    engine and so never runs the application's."""
    env = (
        Path(__file__).resolve().parents[2] / "alembic" / "env.py"
    ).read_text(encoding="utf-8")

    assert "ensure_database_directory" in env
