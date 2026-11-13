"""backend/routes/side_bets.py - Side Bets & Commissioner Side Bet Desk Endpoints."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request

from backend.database import SessionLocal
from backend.models.side_bet import SideBet
from backend.services.side_bets_service import (
    ensure_side_bets_table,
    get_side_bets,
    normalize_to_espn_team_ids,
    sync_side_bets_to_db,
    upsert_side_bet_in_json,
)

side_bets_bp = Blueprint("side_bets", __name__)

VALID_SCORING_MODES = {"STARTERS", "MAX_PF", "BENCH"}


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


def _unauthorized_response() -> tuple[Any, int]:
    return (
        jsonify({"error": "UNAUTHORIZED", "message": "Invalid commissioner password"}),
        401,
    )


@side_bets_bp.route("/side-bets", methods=["GET"])
def list_side_bets() -> tuple[Any, int]:
    """Return evaluated side bets, player/team boxscore breakdowns, and P&L leaderboard."""
    season_str = request.args.get("season")
    season_filter: int | None = None
    if season_str is not None and season_str not in ("all", "all_time", "null", ""):
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

    week_str = request.args.get("week")
    week_filter: int | None = None
    if week_str is not None and week_str not in ("all", "null", ""):
        try:
            week_filter = int(week_str)
        except ValueError:
            return (
                jsonify(
                    {
                        "error": "BAD_REQUEST",
                        "message": f"Invalid week parameter: '{week_str}'",
                    }
                ),
                400,
            )

    session_factory = current_app.config.get("SESSION_FACTORY", SessionLocal)
    with session_factory() as session:
        data = get_side_bets(
            session, season_filter=season_filter, week_filter=week_filter
        )
        return jsonify(data), 200


@side_bets_bp.route("/side-bets", methods=["POST"])
def create_side_bet() -> tuple[Any, int]:
    """Create a new 1v1 or group side bet and persist to db/side_bets.json."""
    if not _is_admin_authenticated():
        return _unauthorized_response()

    data = request.get_json(silent=True) or {}
    try:
        season_year = int(data.get("season_year") or 0)
        week = int(data.get("week") or 0)
    except (ValueError, TypeError):
        return (
            jsonify(
                {
                    "error": "BAD_REQUEST",
                    "message": "season_year and week must be valid integers",
                }
            ),
            400,
        )

    raw_side_a = data.get("side_a_team_ids") or data.get("side_a_espn_team_ids") or []
    raw_side_b = data.get("side_b_team_ids") or data.get("side_b_espn_team_ids") or []

    if season_year <= 0 or week <= 0 or not raw_side_a or not raw_side_b:
        return (
            jsonify(
                {
                    "error": "BAD_REQUEST",
                    "message": "season_year, week, side_a_team_ids, and side_b_team_ids are required",
                }
            ),
            400,
        )

    try:
        spread_val = Decimal(str(data.get("spread_side_a", 0.0))).quantize(
            Decimal("0.01")
        )
        stake_val = Decimal(str(data.get("stake_amount", 0.0))).quantize(
            Decimal("0.01")
        )
    except Exception:
        return (
            jsonify(
                {
                    "error": "BAD_REQUEST",
                    "message": "spread_side_a and stake_amount must be valid numbers",
                }
            ),
            400,
        )

    scoring_mode = str(data.get("scoring_mode") or "STARTERS").strip().upper()
    if scoring_mode not in VALID_SCORING_MODES:
        scoring_mode = "STARTERS"

    session_factory = current_app.config.get("SESSION_FACTORY", SessionLocal)
    with session_factory() as session:
        ensure_side_bets_table(session)
        sync_side_bets_to_db(session)

        side_a_espn = normalize_to_espn_team_ids(session, season_year, raw_side_a)
        side_b_espn = normalize_to_espn_team_ids(session, season_year, raw_side_b)

        if not side_a_espn or not side_b_espn:
            return (
                jsonify(
                    {
                        "error": "BAD_REQUEST",
                        "message": "Both Side A and Side B must contain at least one team",
                    }
                ),
                400,
            )

        if set(side_a_espn) & set(side_b_espn):
            return (
                jsonify(
                    {
                        "error": "BAD_REQUEST",
                        "message": "A team cannot be on both Side A and Side B in the same bet",
                    }
                ),
                400,
            )

        bet_uuid = str(data.get("bet_uuid") or f"bet-{uuid4().hex[:12]}")
        now = datetime.now(UTC)

        bet = SideBet(
            bet_uuid=bet_uuid,
            season_year=season_year,
            week=week,
            title=str(data.get("title") or "").strip(),
            side_a_name=str(data.get("side_a_name") or "Side A").strip() or "Side A",
            side_b_name=str(data.get("side_b_name") or "Side B").strip() or "Side B",
            side_a_espn_team_ids=side_a_espn,
            side_b_espn_team_ids=side_b_espn,
            spread_side_a=spread_val,
            stake_amount=stake_val,
            stake_description=str(data.get("stake_description") or "").strip(),
            scoring_mode=scoring_mode,
            is_deleted=False,
            created_at=now,
            updated_at=now,
        )
        session.add(bet)
        session.flush()

        upsert_side_bet_in_json(bet)
        session.commit()

        return (
            jsonify(
                {
                    "message": "Side bet created",
                    "bet_id": bet.id,
                    "bet_uuid": bet.bet_uuid,
                }
            ),
            201,
        )


@side_bets_bp.route("/side-bets/<int:bet_id>", methods=["PUT"])
def update_side_bet(bet_id: int) -> tuple[Any, int]:
    """Update an existing side bet and sync to db/side_bets.json."""
    if not _is_admin_authenticated():
        return _unauthorized_response()

    data = request.get_json(silent=True) or {}
    session_factory = current_app.config.get("SESSION_FACTORY", SessionLocal)
    with session_factory() as session:
        ensure_side_bets_table(session)
        sync_side_bets_to_db(session)

        bet = session.get(SideBet, bet_id)
        if not bet or bet.is_deleted:
            return (
                jsonify({"error": "NOT_FOUND", "message": f"Side bet {bet_id} not found"}),
                404,
            )

        if "season_year" in data and data["season_year"] is not None:
            bet.season_year = int(data["season_year"])
        if "week" in data and data["week"] is not None:
            bet.week = int(data["week"])
        if "title" in data and data["title"] is not None:
            bet.title = str(data["title"]).strip()
        if "side_a_name" in data and data["side_a_name"] is not None:
            bet.side_a_name = str(data["side_a_name"]).strip() or "Side A"
        if "side_b_name" in data and data["side_b_name"] is not None:
            bet.side_b_name = str(data["side_b_name"]).strip() or "Side B"
        if "spread_side_a" in data and data["spread_side_a"] is not None:
            bet.spread_side_a = Decimal(str(data["spread_side_a"])).quantize(
                Decimal("0.01")
            )
        if "stake_amount" in data and data["stake_amount"] is not None:
            bet.stake_amount = Decimal(str(data["stake_amount"])).quantize(
                Decimal("0.01")
            )
        if "stake_description" in data and data["stake_description"] is not None:
            bet.stake_description = str(data["stake_description"]).strip()
        if "scoring_mode" in data and data["scoring_mode"] is not None:
            mode = str(data["scoring_mode"]).strip().upper()
            if mode in VALID_SCORING_MODES:
                bet.scoring_mode = mode

        raw_side_a = data.get("side_a_team_ids") or data.get("side_a_espn_team_ids")
        if raw_side_a is not None:
            bet.side_a_espn_team_ids = normalize_to_espn_team_ids(
                session, bet.season_year, raw_side_a
            )

        raw_side_b = data.get("side_b_team_ids") or data.get("side_b_espn_team_ids")
        if raw_side_b is not None:
            bet.side_b_espn_team_ids = normalize_to_espn_team_ids(
                session, bet.season_year, raw_side_b
            )

        if set(bet.side_a_espn_team_ids or []) & set(bet.side_b_espn_team_ids or []):
            return (
                jsonify(
                    {
                        "error": "BAD_REQUEST",
                        "message": "A team cannot be on both Side A and Side B in the same bet",
                    }
                ),
                400,
            )

        bet.updated_at = datetime.now(UTC)
        session.flush()

        upsert_side_bet_in_json(bet)
        session.commit()

        return (
            jsonify({"message": "Side bet updated", "bet_id": bet.id}),
            200,
        )


@side_bets_bp.route("/side-bets/<int:bet_id>", methods=["DELETE"])
def delete_side_bet(bet_id: int) -> tuple[Any, int]:
    """Soft-delete a side bet (is_deleted = True) and sync to db/side_bets.json."""
    if not _is_admin_authenticated():
        return _unauthorized_response()

    session_factory = current_app.config.get("SESSION_FACTORY", SessionLocal)
    with session_factory() as session:
        ensure_side_bets_table(session)
        sync_side_bets_to_db(session)

        bet = session.get(SideBet, bet_id)
        if not bet:
            return (
                jsonify({"error": "NOT_FOUND", "message": f"Side bet {bet_id} not found"}),
                404,
            )

        bet.is_deleted = True
        bet.updated_at = datetime.now(UTC)
        session.flush()

        upsert_side_bet_in_json(bet)
        session.commit()

        return (
            jsonify({"message": "Side bet deleted", "bet_id": bet.id}),
            200,
        )
