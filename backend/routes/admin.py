"""backend/routes/admin.py - Commissioner Administration & Manual Ingestion Triggers.

Endpoints:
  POST /api/v1/admin/backfill - Trigger historical ingestion or snapshot rebuild
  POST /api/v1/admin/sync     - Trigger rolling weekly sync for the active season
"""

from __future__ import annotations

import os
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from backend.database import SessionLocal
from backend.jobs.backfill_history import backfill_history
from backend.jobs.sync_weekly import sync_weekly

admin_bp = Blueprint("admin", __name__)


def _is_admin_authenticated() -> bool:
    """Validate X-Admin-Password header or JSON password against configured admin secret."""
    auth_header = request.headers.get("X-Admin-Password")
    if not auth_header and request.is_json:
        body = request.get_json(silent=True) or {}
        auth_header = body.get("password")

    expected_password = (
        os.getenv("TRADE_ADMIN_PASSWORD")
        or os.getenv("ADMIN_PASSWORD")
        or "commish"
    )
    return bool(auth_header and auth_header == expected_password)


@admin_bp.route("/admin/backfill", methods=["POST"])
def trigger_backfill() -> tuple[Any, int]:
    """Execute backfill job (either from stored snapshots or live crawl)."""
    if not _is_admin_authenticated():
        return jsonify({"error": "UNAUTHORIZED", "message": "Invalid commissioner password"}), 401

    body = request.get_json(silent=True) or {}
    from_snapshots = bool(body.get("from_snapshots", True))
    from_year = body.get("from_year")
    to_year = body.get("to_year")
    league_id = body.get("league_id")

    session_factory = current_app.config.get("SESSION_FACTORY", SessionLocal)
    with session_factory() as session:
        try:
            run = backfill_history(
                session=session,
                from_snapshots=from_snapshots,
                from_year=from_year,
                to_year=to_year,
                league_id=league_id,
            )
            session.commit()
            return (
                jsonify(
                    {
                        "status": run.status,
                        "records_processed": run.records_processed,
                        "started_at": run.started_at.isoformat() if run.started_at else None,
                        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                        "from_snapshots": from_snapshots,
                    }
                ),
                200,
            )
        except Exception as e:
            session.rollback()
            return (
                jsonify({"error": "INTERNAL_ERROR", "message": str(e)}),
                500,
            )


@admin_bp.route("/admin/sync", methods=["POST"])
def trigger_sync() -> tuple[Any, int]:
    """Execute rolling weekly sync for the active season."""
    if not _is_admin_authenticated():
        return jsonify({"error": "UNAUTHORIZED", "message": "Invalid commissioner password"}), 401

    body = request.get_json(silent=True) or {}
    week = body.get("week")
    league_id = body.get("league_id")

    session_factory = current_app.config.get("SESSION_FACTORY", SessionLocal)
    with session_factory() as session:
        try:
            run = sync_weekly(
                session=session,
                week=week,
                league_id=league_id,
            )
            session.commit()
            return (
                jsonify(
                    {
                        "status": run.status,
                        "records_processed": run.records_processed,
                        "started_at": run.started_at.isoformat() if run.started_at else None,
                        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                    }
                ),
                200,
            )
        except Exception as e:
            session.rollback()
            return (
                jsonify({"error": "INTERNAL_ERROR", "message": str(e)}),
                500,
            )
