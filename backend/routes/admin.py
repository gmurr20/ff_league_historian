"""backend/routes/admin.py - Commissioner Administration & Manual Ingestion Triggers.

Endpoints:
  POST /api/v1/admin/backfill  - Trigger historical ingestion or snapshot rebuild
  POST /api/v1/admin/sync      - Trigger rolling weekly sync for the active season
  POST /api/v1/admin/sync-live - Trigger lightweight live score & boxscore sync for the active week
"""

from __future__ import annotations

import os
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from backend.database import SessionLocal
from backend.jobs.backfill_history import backfill_history
from backend.jobs.sync_live_scores import sync_live_scores
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


@admin_bp.route("/admin/sync-live", methods=["POST"])
def trigger_sync_live() -> tuple[Any, int]:
    """Execute lightweight in-week live score and player boxscore sync for the active season."""
    if not _is_admin_authenticated():
        return jsonify({"error": "UNAUTHORIZED", "message": "Invalid commissioner password"}), 401

    body = request.get_json(silent=True) or {}
    week = body.get("week")
    league_id = body.get("league_id")

    session_factory = current_app.config.get("SESSION_FACTORY", SessionLocal)
    with session_factory() as session:
        try:
            run = sync_live_scores(
                session=session,
                week=week,
                league_id=league_id,
            )
            session.commit()
            return (
                jsonify(
                    {
                        "status": run.status,
                        "season_year": run.season_year,
                        "week_range": run.week_range,
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


@admin_bp.route("/admin/diagnose", methods=["GET"])
def diagnose() -> tuple[Any, int]:
    """Return database diagnostic state for trades, transactions, and snapshots."""
    session_factory = current_app.config.get("SESSION_FACTORY", SessionLocal)
    with session_factory() as session:
        from backend.models.player import Player
        from backend.models.raw_snapshot import RawEspnSnapshot
        from backend.models.trade import Trade
        from backend.models.transaction import Transaction

        trades = session.query(Trade).all()
        trade_txs = session.query(Transaction).filter_by(transaction_type="TRADE").all()
        any_84 = session.query(Transaction).filter_by(espn_transaction_id="84f604f2-1163-40ce-b93a-a342e68f6e53").first()
        pitts = session.get(Player, 4360248)
        waddle = session.get(Player, 4372016)
        snapshots = session.query(
            RawEspnSnapshot.season_year, RawEspnSnapshot.view_name, RawEspnSnapshot.scoring_period
        ).all()

        return (
            jsonify(
                {
                    "has_espn_s2": bool(os.getenv("ESPN_S2")),
                    "has_espn_swid": bool(os.getenv("ESPN_SWID")),
                    "trade_records": [
                        {"id": t.id, "espn_id": t.espn_transaction_id, "week": t.week, "status": t.status}
                        for t in trades
                    ],
                    "trade_transactions": [
                        {
                            "id": x.id,
                            "espn_id": x.espn_transaction_id,
                            "week": x.week,
                            "status": x.status,
                            "related": x.related_espn_transaction_id,
                            "type": x.transaction_type,
                        }
                        for x in trade_txs
                    ],
                    "any_84_tx": {
                        "id": any_84.id,
                        "type": any_84.transaction_type,
                        "status": any_84.status,
                    } if any_84 else None,
                    "has_pitts": pitts is not None,
                    "has_waddle": waddle is not None,
                    "snapshots_count": len(snapshots),
                    "snapshots": [f"{s[0]}_{s[1]}_{s[2]}" for s in snapshots],
                }
            ),
            200,
        )


