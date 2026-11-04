"""backend/database.py - Database Connection, Session Management & Engine Hooks.

Purpose:
    Provides SQLAlchemy 2.0 connection engine configuration, scoped session factories,
    dual PostgreSQL 16 / SQLite dialect compatibility, and engine hooks for foreign key
    enforcement and custom unique indexes.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy 2.0 ORM models."""

    pass


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
    """Enforce SQLite foreign key integrity constraints on every new connection."""
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


@event.listens_for(Base.metadata, "after_create")
def _create_custom_indexes(target: Any, connection: Any, **kw: Any) -> None:
    """Create custom dual-dialect unique indexes.

    1. Blocks duplicate NULL-week entries (such as multiple CHAMPION awards in one season)
       using an expression index on COALESCE(week, -1), ensuring cross-dialect parity
       between PostgreSQL 15+ UNIQUE NULLS NOT DISTINCT and SQLite.
    2. Enforces at most one regular-season weekly win/tie payout per manager per week.
    """
    connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_earnings_nulls_not_distinct "
            "ON earnings_ledger (manager_id, season_year, COALESCE(week, -1), entry_type)"
        )
    )
    connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_earnings_weekly_single "
            "ON earnings_ledger (manager_id, season_year, week) "
            "WHERE entry_type IN ('WEEKLY_WIN', 'WEEKLY_TIE')"
        )
    )


def get_database_url() -> str:
    """Resolve database URL from environment, normalizing PostgreSQL driver names.

    Defaults to a local SQLite file (sqlite:///ff_historian.db) when DATABASE_URL is unset.
    Normalizes legacy 'postgres://' or standard 'postgresql://' to 'postgresql+psycopg://'.
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        return "sqlite:///ff_historian.db"
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def create_db_engine(url: str | None = None, **kwargs: Any) -> Engine:
    """Create and configure a SQLAlchemy 2.0 database engine."""
    target_url = url or get_database_url()
    engine_kwargs: dict[str, Any] = {}

    if target_url.startswith("sqlite"):
        if ":memory:" in target_url:
            engine_kwargs["poolclass"] = StaticPool
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        engine_kwargs["pool_pre_ping"] = True
        engine_kwargs["pool_size"] = kwargs.pop("pool_size", 5)
        engine_kwargs["max_overflow"] = kwargs.pop("max_overflow", 10)

    engine_kwargs.update(kwargs)
    return create_engine(target_url, **engine_kwargs)


# Module-level default engine and session factory
engine = create_db_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_session(session_factory: sessionmaker[Session] | None = None) -> Iterator[Session]:
    """Provide a transactional database session scope."""
    factory = session_factory or SessionLocal
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(target_engine: Engine | None = None) -> None:
    """Initialize all tables and indexes defined in Base metadata."""
    import backend.models  # noqa: F401

    active_engine = target_engine or engine
    Base.metadata.create_all(bind=active_engine)
    with active_engine.connect() as conn:
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_earnings_nulls_not_distinct "
                "ON earnings_ledger (manager_id, season_year, COALESCE(week, -1), entry_type)"
            )
        )
        if active_engine.dialect.name == "sqlite":
            res = conn.execute(
                text(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type='index' AND name='uq_earnings_weekly_single'"
                )
            ).scalar()
            if res and "WHERE WEEK IS NOT NULL" in res.upper():
                conn.execute(text("DROP INDEX IF EXISTS uq_earnings_weekly_single"))
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_earnings_weekly_single "
                "ON earnings_ledger (manager_id, season_year, week) "
                "WHERE entry_type IN ('WEEKLY_WIN', 'WEEKLY_TIE')"
            )
        )
        # Ensure draft_picks.player_pro_team column exists on upgraded databases
        try:
            if active_engine.dialect.name == "postgresql":
                conn.execute(
                    text("ALTER TABLE draft_picks ADD COLUMN IF NOT EXISTS player_pro_team VARCHAR(16)")
                )
            else:
                cols = [
                    row[1]
                    for row in conn.execute(text("PRAGMA table_info(draft_picks)")).fetchall()
                ]
                if cols and "player_pro_team" not in cols:
                    conn.execute(text("ALTER TABLE draft_picks ADD COLUMN player_pro_team VARCHAR(16)"))
        except Exception:
            pass
        # Heal previously mis-deleted 2026 trade 51056f5f-1511-40d1-a057-69a610de6092
        # and synchronize canonical trade overrides into the database.
        try:
            conn.execute(
                text(
                    "UPDATE transactions SET status = 'EXECUTED' "
                    "WHERE espn_transaction_id = '51056f5f-1511-40d1-a057-69a610de6092' "
                    "AND status = 'CANCELED'"
                )
            )
            conn.execute(
                text(
                    "UPDATE trades SET status = 'EXECUTED' "
                    "WHERE espn_transaction_id = '51056f5f-1511-40d1-a057-69a610de6092' "
                    "AND status = 'DELETED'"
                )
            )
            conn.execute(
                text(
                    "DELETE FROM trade_overrides "
                    "WHERE espn_transaction_id = 'ee64229b-8b7c-4e92-9abf-c5e52bade74e' "
                    "AND is_deleted = TRUE"
                )
            )
        except Exception:
            pass
        conn.commit()

    # Seed canonical trade overrides from db/trade_overrides.json into TradeOverride table
    try:
        from backend.jobs.parsers import sync_trade_overrides_to_db

        factory = sessionmaker(autocommit=False, autoflush=False, bind=active_engine)
        with get_session(factory) as session:
            sync_trade_overrides_to_db(session)
    except Exception:
        pass

