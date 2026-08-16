from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from app.config import get_settings


def _build_engine() -> Engine:
    database_url = get_settings().database_url
    kwargs: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    if database_url == "sqlite://":
        # An in-memory database lives inside its connection, so every thread has to use the
        # same one — but a sqlite3 connection is not safe to use from two threads at once,
        # and `check_same_thread=False` removes the guard that would have said so.
        #
        # This used to be StaticPool, which hands the one connection to every caller
        # simultaneously. Under concurrent requests that interleaves cursor and transaction
        # state on a single connection, and the damage is not limited to errors: a hammer
        # test across eight threads produced `InterfaceError: bad parameter or other API
        # misuse`, and also `NoResultFound` and `MultipleResultsFound` from a query that can
        # only ever return one row — threads reading each other's result sets. It surfaced
        # as an end-to-end test failing about one run in three, always a different test.
        #
        # One connection, and the pool blocks a second caller until the first gives it back.
        kwargs["poolclass"] = QueuePool
        kwargs["pool_size"] = 1
        kwargs["max_overflow"] = 0
    elif database_url.startswith("sqlite:///"):
        database_path = database_url.removeprefix("sqlite:///")
        if database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(database_url, **kwargs)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def create_schema() -> None:
    from app.persistence.models import Base
    from app.security.auth import seed_platform_foundation

    Base.metadata.create_all(engine)
    seed_platform_foundation(get_settings())
