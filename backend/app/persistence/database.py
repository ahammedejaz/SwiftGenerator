from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings


def _build_engine() -> Engine:
    database_url = get_settings().database_url
    kwargs: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    if database_url == "sqlite://":
        kwargs["poolclass"] = StaticPool
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
