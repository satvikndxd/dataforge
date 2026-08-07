"""Database engine/session management.

SQLite by default (single-file, zero-config); Postgres via DATABASE_URL.
JSON columns are used for flexible metadata (JSONB on Postgres).
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.core.config import get_settings

_engine = None
_session_factory: sessionmaker | None = None


class Base(DeclarativeBase):
    pass


def get_engine():
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        kwargs: dict = {"future": True}
        if settings.database_url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(settings.database_url, **kwargs)
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def init_db() -> None:
    from backend.db import models  # noqa: F401 — register mappings

    Base.metadata.create_all(get_engine())


def reset_engine() -> None:
    """Test helper — drop cached engine so DATABASE_URL changes take effect."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


@contextmanager
def session_scope() -> Iterator[Session]:
    get_engine()
    assert _session_factory is not None
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
