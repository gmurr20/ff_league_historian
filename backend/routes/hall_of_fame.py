"""backend/routes/hall_of_fame.py - Hall of Fame & Legends REST API Endpoints.

Purpose:
    Exposes all-time championship banners and the featured champion's Pokémon-inspired
    Elite Four Hall of Fame spotlight with top 4 championship heroes.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify, request

from backend.database import SessionLocal
from backend.services.hall_of_fame_service import get_hall_of_fame

hall_of_fame_bp = Blueprint("hall_of_fame", __name__)


@hall_of_fame_bp.route("/hall-of-fame", methods=["GET"])
@hall_of_fame_bp.route("/history/hall-of-fame", methods=["GET"])
def hall_of_fame() -> tuple[Any, int]:
    """Retrieve all-time championship banners and Pokémon-style Hall of Fame induction."""
    season_param = request.args.get("season")
    season_year: int | None = None

    if season_param is not None and season_param != "" and season_param.lower() != "all":
        try:
            season_year = int(season_param)
        except ValueError:
            return (
                jsonify(
                    {
                        "error": "BAD_REQUEST",
                        "message": f"Invalid season parameter: '{season_param}'",
                    }
                ),
                400,
            )

    session_factory = current_app.config.get("SESSION_FACTORY", SessionLocal)
    with session_factory() as session:
        data = get_hall_of_fame(session, season_year=season_year)
        return jsonify(data), 200
