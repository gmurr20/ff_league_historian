"""backend/routes/history.py - Head-to-Head Rivalry History Endpoints."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify, request

from backend.database import SessionLocal
from backend.services.history_service import get_head_to_head

history_bp = Blueprint("history", __name__)


@history_bp.route("/history/head-to-head", methods=["GET"])
@history_bp.route("/head-to-head", methods=["GET"])
def head_to_head() -> tuple[Any, int]:
    # Support both camelCase and snake_case query params
    mgr_a_str = request.args.get("managerA") or request.args.get("manager_a")
    mgr_b_str = request.args.get("managerB") or request.args.get("manager_b")

    manager_a_id: int | None = None
    manager_b_id: int | None = None

    if mgr_a_str is not None:
        try:
            manager_a_id = int(mgr_a_str)
        except ValueError:
            return (
                jsonify(
                    {
                        "error": "BAD_REQUEST",
                        "message": f"Invalid managerA parameter: '{mgr_a_str}'",
                    }
                ),
                400,
            )

    if mgr_b_str is not None:
        try:
            manager_b_id = int(mgr_b_str)
        except ValueError:
            return (
                jsonify(
                    {
                        "error": "BAD_REQUEST",
                        "message": f"Invalid managerB parameter: '{mgr_b_str}'",
                    }
                ),
                400,
            )

    session_factory = current_app.config.get("SESSION_FACTORY", SessionLocal)
    with session_factory() as session:
        data = get_head_to_head(
            session,
            manager_a_id=manager_a_id,
            manager_b_id=manager_b_id,
        )
        return jsonify(data), 200
