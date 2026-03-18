from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from utils.config import get_database_url

_DB_PATH = Path(__file__).resolve().parents[2] / "coursemate.sqlite3"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


# Use PostgreSQL (or any other DB) when DATABASE_URL is provided via
# utils.config.get_database_url(), otherwise fall back to the local
# SQLite file.
DATABASE_URL = get_database_url() or f"sqlite:///{_DB_PATH}"


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM models."""


engine = create_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    """Create all tables for registered ORM models."""

    # Import models so they are registered with Base.metadata before create_all
    from services import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
