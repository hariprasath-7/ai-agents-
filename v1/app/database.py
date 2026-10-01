"""Database layer for the Telegram AI Agent (SQLAlchemy 2.0).

Provides the engine, a ``SessionLocal`` factory, the ``Todo`` ORM model,
``init_db()`` for schema creation + seeding, and a ``session_scope`` context
manager for transactional work.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import DateTime, Integer, String, Text, create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    sessionmaker,
)

from app.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models (SQLAlchemy 2.0 style)."""


class Todo(Base):
    """A single todo/task row."""

    __tablename__ = "todos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default="medium"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Todo id={self.id} title={self.title!r} status={self.status}>"


def _normalize_url(raw_url: str) -> str:
    """Normalize a Postgres URL for SQLAlchemy + psycopg2.

    - Rewrite the legacy ``postgres://`` scheme to ``postgresql+psycopg2://``.
    - Ensure ``sslmode=require`` is present (managed Postgres needs SSL).
    """
    url = make_url(raw_url)

    if url.drivername in ("postgres", "postgresql"):
        url = url.set(drivername="postgresql+psycopg2")

    query = dict(url.query)
    if url.drivername.startswith("postgresql") and "sslmode" not in query:
        query["sslmode"] = "require"
    url = url.set(query=query)

    return url.render_as_string(hide_password=False)


def _build_engine() -> Engine:
    raw = settings.resolved_database_url
    if not raw:
        raise RuntimeError(
            "No database URL found. Set POSTGRES_URL or DATABASE_URL."
        )
    return create_engine(
        _normalize_url(raw),
        pool_pre_ping=True,   # transparently recover from dropped connections
        pool_recycle=1800,    # recycle connections every 30 min
        future=True,
    )


# Lazily-created singletons so importing this module never forces a connection.
_engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def _get_session_factory() -> sessionmaker[Session]:
    global SessionLocal
    if SessionLocal is None:
        SessionLocal = sessionmaker(
            bind=get_engine(), expire_on_commit=False, future=True
        )
    return SessionLocal


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Yield a session, committing on success and rolling back on error."""
    session = _get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create tables if they don't exist, then seed sample data if empty."""
    Base.metadata.create_all(bind=get_engine())
    _seed_if_empty()


def _seed_if_empty() -> None:
    """Insert a few realistic sample tasks when the table has no rows."""
    with session_scope() as session:
        if session.query(Todo).count() > 0:
            return

        session.add_all(
            [
                Todo(
                    title="Write project README",
                    description="Document setup, environment variables, and usage.",
                    status="in_progress",
                    priority="high",
                ),
                Todo(
                    title="Fix login redirect bug",
                    description="Users land on a blank page after OAuth callback.",
                    status="pending",
                    priority="high",
                ),
                Todo(
                    title="Upgrade dependencies",
                    description="Bump SQLAlchemy and LangChain to latest versions.",
                    status="pending",
                    priority="medium",
                ),
                Todo(
                    title="Archive Q2 reports",
                    description="Move finished quarterly reports to cold storage.",
                    status="completed",
                    priority="low",
                ),
            ]
        )
