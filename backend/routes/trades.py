"""backend/routes/trades.py - Bilateral Trades & Trends Endpoints."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify, request

from backend.database import SessionLocal
from backend.services.trades_service import get_trades_trends

trades_bp = Blueprint("trades", __name__)


@trades_bp.route("/trades/trends", methods=["GET"])
@trades_bp.route("/trades", methods=["GET"])
def trades_trends() -> tuple[Any, int]:
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
        data = get_trades_trends(session, season_filter=season_filter)
        return jsonify(data), 200
