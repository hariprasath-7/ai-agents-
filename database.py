"""Database setup for the Todo Agent.

Connects to Vercel Postgres via SQLAlchemy, defines the Todo model, and
provides initialization + seeding helpers.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, declarative_base, sessionmaker

load_dotenv()

Base = declarative_base()


class Todo(Base):
    """A single todo/task row."""

    __tablename__ = "todos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    priority = Column(String(20), nullable=False, default="medium")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Todo id={self.id} title={self.title!r} status={self.status}>"


def _normalize_url(raw_url: str) -> str:
    """Normalize a Postgres URL for SQLAlchemy + psycopg2.

    - Vercel/Heroku sometimes hand out ``postgres://`` which SQLAlchemy no
      longer accepts; rewrite to ``postgresql+psycopg2://``.
    - Ensure ``sslmode=require`` is present (Vercel Postgres needs SSL).
    """
    url = make_url(raw_url)

    if url.drivername in ("postgres", "postgresql"):
        url = url.set(drivername="postgresql+psycopg2")

    query = dict(url.query)
    if "sslmode" not in query:
        query["sslmode"] = "require"
    url = url.set(query=query)

    return url.render_as_string(hide_password=False)


def _get_connection_string() -> str:
    raw = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")
    if not raw:
        raise RuntimeError(
            "No database URL found. Set POSTGRES_URL or DATABASE_URL in your .env."
        )
    return _normalize_url(raw)


def _build_engine() -> Engine:
    return create_engine(
        _get_connection_string(),
        pool_pre_ping=True,   # transparently recover from stale/dropped connections
        pool_recycle=1800,    # recycle connections every 30 min
        future=True,
    )


# Lazily-created singletons so importing this module never forces a connection.
_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def _get_session_factory() -> sessionmaker[Session]:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(
            bind=get_engine(), expire_on_commit=False, future=True
        )
    return _SessionFactory


@contextmanager
def get_session() -> Generator[Session, None, None]:
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
    with get_session() as session:
        if session.query(Todo).count() > 0:
            return

        samples = [
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
                description="Bump SQLAlchemy and LangChain to latest minor versions.",
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
        session.add_all(samples)


if __name__ == "__main__":
    init_db()
    print("Database initialized and seeded (if it was empty).")
