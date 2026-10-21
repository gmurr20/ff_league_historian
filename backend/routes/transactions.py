"""backend/routes/transactions.py - Transactions & FAAB Bidding Wars Endpoints."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify, request

from backend.database import SessionLocal
from backend.services.transactions_service import get_transactions_summary

transactions_bp = Blueprint("transactions", __name__)


@transactions_bp.route("/transactions/summary", methods=["GET"])
@transactions_bp.route("/transactions", methods=["GET"])
def transactions_summary() -> tuple[Any, int]:
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
        try:
            data = get_transactions_summary(session, season_year=season_filter)
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
