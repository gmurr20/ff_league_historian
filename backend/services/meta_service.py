"""backend/services/meta_service.py - Health & League Metadata Query Service.

Purpose:
    Provides database connectivity health checks and system-wide league metadata,
    available seasons, canonical managers, and sync run audit timestamps.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from backend.models.manager import Manager
from backend.models.season import Season
from backend.models.sync_run import SyncRun


def get_health(session: Session) -> tuple[dict[str, Any], int]:
    """Execute a database connectivity ping and return system health status."""
    now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    try:
        session.execute(text("SELECT 1"))
        return (
            {
                "status": "ok",
                "database": "connected",
                "timestamp": now_iso,
            },
            200,
        )
    except Exception:
        return (
            {
                "status": "error",
                "database": "disconnected",
                "timestamp": now_iso,
            },
            503,
        )


def get_meta(session: Session) -> dict[str, Any]:
    """Retrieve canonical league metadata, seasons, managers, and sync status."""
    seasons = session.query(Season).order_by(Season.season_year.desc()).all()
    active_season = next((s for s in seasons if s.is_active), None)

    current_season_year: int | None = None
    league_name = "Fantasy Football League"

    if active_season:
        current_season_year = active_season.season_year
        league_name = active_season.league_name
    elif seasons:
        current_season_year = seasons[0].season_year
        league_name = seasons[0].league_name

    available_seasons = [
        {
            "season_year": s.season_year,
            "is_active": s.is_active,
            "is_completed": s.is_completed,
            "regular_season_weeks": s.regular_season_weeks,
            "current_week": s.current_week,
            "has_transaction_data": s.has_transaction_data,
            "has_boxscore_data": s.has_boxscore_data,
        }
        for s in seasons
    ]

    managers_query = session.query(Manager).order_by(Manager.display_name.asc()).all()
    managers = [
        {
            "id": m.id,
            "espn_member_id": m.espn_member_id,
            "display_name": m.display_name,
            "is_active": m.is_active,
        }
        for m in managers_query
    ]

    # Ingestion audit status
    last_backfill = (
        session.query(func.max(SyncRun.completed_at))
        .filter(SyncRun.run_type == "BACKFILL", SyncRun.status == "SUCCESS")
        .scalar()
    )
    last_weekly_sync = (
        session.query(func.max(SyncRun.completed_at))
        .filter(SyncRun.run_type == "WEEKLY_CRON", SyncRun.status == "SUCCESS")
        .scalar()
    )
    latest_run = session.query(SyncRun).order_by(SyncRun.started_at.desc(), SyncRun.id.desc()).first()

    last_sync = {
        "last_backfill_at": (
            last_backfill.isoformat().replace("+00:00", "Z") if last_backfill else None
        ),
        "last_weekly_sync_at": (
            last_weekly_sync.isoformat().replace("+00:00", "Z") if last_weekly_sync else None
        ),
        "last_sync_status": latest_run.status if latest_run else None,
    }

    return {
        "league_name": league_name,
        "current_season": current_season_year,
        "available_seasons": available_seasons,
        "managers": managers,
        "last_sync": last_sync,
    }
