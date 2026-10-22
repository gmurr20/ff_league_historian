"""backend/routes/standings.py - Standings & Performance Endpoints."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify, request

from backend.database import SessionLocal
from backend.services.standings_service import get_all_time_standings, get_standings

standings_bp = Blueprint("standings", __name__)


@standings_bp.route("/standings/current", methods=["GET"])
@standings_bp.route("/standings", methods=["GET"])
def standings() -> tuple[Any, int]:
    season_str = request.args.get("season")
    session_factory = current_app.config.get("SESSION_FACTORY", SessionLocal)
    with session_factory() as session:
        if season_str in ("all", "all_time", "null"):
            data = get_all_time_standings(session)
            return jsonify(data), 200

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

        try:
            data = get_standings(session, season_year=season_filter)
            return jsonify(data), 200
        except ValueError as exc:
            return (
                jsonify(
                    {
                        "error": "NOT_FOUND",
                        "message": str(exc),
                    }
                ),
                404,
            )
