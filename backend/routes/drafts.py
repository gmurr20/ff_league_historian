"""backend/routes/drafts.py - Draft Boards & Future Draft Order Endpoints."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify, request

from backend.database import SessionLocal
from backend.services.drafts_service import get_draft_data

drafts_bp = Blueprint("drafts", __name__)


@drafts_bp.route("/drafts", methods=["GET"])
@drafts_bp.route("/draft", methods=["GET"])
def get_drafts() -> tuple[Any, int]:
    """Return future draft order and previous draft board history.

    Query parameters:
        season (int, optional): Target season year. Defaults to future draft season (e.g. 2027).

    Returns:
        JSON response conforming to canonical drafts API contract.
    """
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
        data = get_draft_data(session, season_filter=season_filter)
        return jsonify(data), 200
