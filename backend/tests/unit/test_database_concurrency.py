"""The in-memory database must survive concurrent requests.

An in-memory SQLite database lives inside its connection, so every thread has to use the
same one — and a sqlite3 connection is not safe to use from two threads at once.
`check_same_thread=False`, which the engine needs, removes the guard that would have said so.

This was not a theoretical hazard. With a `StaticPool` handing the one connection to every
caller at the same time, eight threads produced `InterfaceError: bad parameter or other API
misuse` — and, worse, `NoResultFound` and `MultipleResultsFound` from a query that can only
ever return one row, which is threads reading each other's result sets. It surfaced as an
end-to-end test failing about one run in three, a different test each time.

FastAPI runs sync endpoints in a threadpool, so this is exactly what the studio does under
load.
"""

from __future__ import annotations

import threading

from sqlalchemy import text

from app.persistence.database import SessionLocal, engine


def test_the_in_memory_engine_hands_out_one_connection_at_a_time() -> None:
    if engine.url.render_as_string() != "sqlite://":
        return  # A file-backed or PostgreSQL engine gives each thread its own connection.
    assert engine.pool.size() == 1
    assert engine.pool._max_overflow == 0  # noqa: SLF001 - the guarantee under test


def test_concurrent_reads_never_see_another_thread_s_result(client) -> None:  # type: ignore[no-untyped-def]
    """The `client` fixture is here for its side effect: starting the app creates the
    schema, and an in-memory database has none until it does."""
    failures: list[str] = []

    def hammer() -> None:
        for _ in range(200):
            try:
                with SessionLocal() as session:
                    # `.one()` is the point: it fails loudly if the row count is wrong,
                    # which is how cross-thread result bleed shows up.
                    session.execute(text("SELECT count(*) FROM ai_result_cache")).one()
            except Exception as error:  # noqa: BLE001 - any exception is the failure
                failures.append(f"{type(error).__name__}: {error}")
                return

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []


def test_concurrent_writes_and_reads_stay_consistent(client) -> None:  # type: ignore[no-untyped-def]
    """A write from one thread must not corrupt a read in another."""
    failures: list[str] = []

    def writer(index: int) -> None:
        for step in range(40):
            try:
                with SessionLocal.begin() as session:
                    session.execute(
                        text(
                            "INSERT INTO reports (id, scenario_id, report_payload, "
                            "artifact_path, created_at) "
                            "VALUES (:id, NULL, '{}', NULL, CURRENT_TIMESTAMP)"
                        ),
                        {"id": f"concurrency-{index}-{step}"},
                    )
            except Exception as error:  # noqa: BLE001
                failures.append(f"write {type(error).__name__}: {error}")
                return

    def reader() -> None:
        for _ in range(80):
            try:
                with SessionLocal() as session:
                    session.execute(text("SELECT count(*) FROM reports")).one()
            except Exception as error:  # noqa: BLE001
                failures.append(f"read {type(error).__name__}: {error}")
                return

    threads = [threading.Thread(target=writer, args=(index,)) for index in range(4)]
    threads += [threading.Thread(target=reader) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
