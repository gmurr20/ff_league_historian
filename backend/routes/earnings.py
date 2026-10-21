"""backend/routes/earnings.py - Financial Earnings Leaderboard Endpoints."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify, request

from backend.database import SessionLocal
from backend.services.earnings_service import get_earnings_leaderboard

earnings_bp = Blueprint("earnings", __name__)


@earnings_bp.route("/earnings/leaderboard", methods=["GET"])
@earnings_bp.route("/earnings", methods=["GET"])
def earnings_leaderboard() -> tuple[Any, int]:
    season_str = request.args.get("season")
    season_filter: int | None = None
    if season_str is not None:
        try:
            season_filter = int(season_str)
        except ValueError:
            return (
                jsonify(
                    {
                        "error": "BAD_REQUEST",
                        "message": f"Invalid season parameter: '{season_str}'",
                    }
                ),
                400,
            )

    session_factory = current_app.config.get("SESSION_FACTORY", SessionLocal)
    with session_factory() as session:
        data = get_earnings_leaderboard(session, season_filter=season_filter)
        return jsonify(data), 200
