"""SQLAlchemy session and metadata configuration."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


DATABASE_URL = _normalize_database_url(settings.database_url)
if DATABASE_URL.startswith("sqlite:///./"):
    Path(DATABASE_URL.removeprefix("sqlite:///./")).parent.mkdir(
        parents=True,
        exist_ok=True,
    )


class Base(DeclarativeBase):
    pass


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Revisions an unversioned database (made by the old create_all start-up)
# can be in, newest first, with a column that only exists from that revision.
_LEGACY_REVISIONS = (
    ("20261026_0002", "users", "session_version"),
    ("20260813_0001", "users", "id"),
)


def alembic_config(url: str):
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    config.attributes["database_url"] = url
    return config


def migrate_database(url: str) -> None:
    """Bring the database at url to the latest migration.

    Dev databases used to be created with create_all, which never adds
    columns to existing tables (a new column broke sign-in) and leaves no
    alembic_version, so alembic could not upgrade them either. Such
    databases are stamped with the revision they match, then upgraded.
    """
    from alembic import command
    from sqlalchemy import inspect

    config = alembic_config(url)
    target = create_engine(url)
    try:
        inspector = inspect(target)
        if inspector.has_table("users") and not inspector.has_table("alembic_version"):
            for revision, table, column in _LEGACY_REVISIONS:
                if column in {item["name"] for item in inspector.get_columns(table)}:
                    command.stamp(config, revision)
                    break
    finally:
        target.dispose()
    command.upgrade(config, "head")


def init_db() -> None:
    migrate_database(DATABASE_URL)


def session_scope() -> Session:
    """Return a session for synchronous repositories and context-aware stores."""
    return SessionLocal()
