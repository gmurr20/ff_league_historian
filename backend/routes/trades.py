"""backend/routes/trades.py - Bilateral Trades & Commissioner Admin Endpoints."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import or_

from backend.database import SessionLocal
from backend.jobs.parsers import load_trade_overrides, save_trade_overrides
from backend.models.manager import Manager
from backend.models.player import Player
from backend.models.season import Season
from backend.models.team import Team
from backend.models.trade import Trade
from backend.models.transaction import Transaction, TransactionItem
from backend.services.trades_service import get_deleted_trades, get_trades_trends

trades_bp = Blueprint("trades", __name__)


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


@trades_bp.route("/trades/admin/verify", methods=["POST"])
def verify_admin_password() -> tuple[Any, int]:
    """Verify commissioner password."""
    if not _is_admin_authenticated():
        return _unauthorized_response()
    return jsonify({"authenticated": True}), 200


@trades_bp.route("/trades/admin/options", methods=["GET"])
def admin_options() -> tuple[Any, int]:
    """Return available seasons, teams, players, and deleted trades for the editor modal."""
    if not _is_admin_authenticated():
        return _unauthorized_response()

    session_factory = current_app.config.get("SESSION_FACTORY", SessionLocal)
    with session_factory() as session:
        seasons = [
            s.season_year
            for s in session.query(Season).order_by(Season.season_year.desc()).all()
        ]

        teams = (
            session.query(Team)
            .join(Manager, Team.manager_id == Manager.id)
            .order_by(Team.season_year.desc(), Team.team_name.asc())
            .all()
        )
        team_options = [
            {
                "team_id": t.id,
                "season_year": t.season_year,
                "team_name": t.team_name,
                "manager_id": t.manager_id,
                "manager_name": t.manager.display_name if t.manager else "",
                "logo_url": t.logo_url,
            }
            for t in teams
        ]

        players = (
            session.query(Player)
            .filter(Player.default_position != "PICK", Player.espn_player_id > 0)
            .order_by(Player.full_name.asc())
            .all()
        )
        player_options = [
            {
                "player_id": p.espn_player_id,
                "full_name": p.full_name,
                "default_position": p.default_position,
                "pro_team": p.pro_team,
                "headshot_url": p.headshot_url,
            }
            for p in players
        ]

        deleted_trades = get_deleted_trades(session)

        return (
            jsonify(
                {
                    "seasons": seasons,
                    "teams": team_options,
                    "players": player_options,
                    "deleted_trades": deleted_trades,
                }
            ),
            200,
        )


def _resolve_or_create_pick_player(
    session: Any, pick: dict[str, Any], default_season: int
) -> int:
    """Resolve or create a Player entity representing a draft pick selection."""
    pick_season = int(pick.get("season_year") or default_season)
    round_num = int(pick.get("round") or 1)
    pick_num_raw = pick.get("pick_number")
    pick_num = int(pick_num_raw) if pick_num_raw not in (None, "", 0) else None

    if pick_num is not None and pick_season == default_season:
        pid = -100000 - pick_num
        name = f"Round {round_num} Pick #{pick_num}"
    else:
        p_sub = pick_num % 100 if pick_num is not None else 0
        pid = -(pick_season * 10000 + round_num * 100 + p_sub)
        if pick_num is not None and pick_num > 0:
            name = f"{pick_season} Round {round_num} Pick #{pick_num}"
        elif pick_season != default_season:
            name = f"{pick_season} Round {round_num} Pick"
        else:
            name = f"Round {round_num} Pick"

    existing_player = session.get(Player, pid)
    if not existing_player:
        player = Player(
            espn_player_id=pid,
            full_name=name,
            default_position="PICK",
            pro_team="DRAFT",
        )
        session.add(player)
        session.flush()

    return pid


@trades_bp.route("/trades/<int:trade_id>", methods=["PUT"])
def update_trade(trade_id: int) -> tuple[Any, int]:
    """Edit an existing trade's week, assets (players & draft picks), and FAAB."""
    if not _is_admin_authenticated():
        return _unauthorized_response()

    data = request.get_json() or {}
    week = data.get("week")
    sides = data.get("sides") or []
    if len(sides) < 2:
        return (
            jsonify({"error": "BAD_REQUEST", "message": "Trades require exactly 2 sides"}),
            400,
        )

    session_factory = current_app.config.get("SESSION_FACTORY", SessionLocal)
    with session_factory() as session:
        trade = session.get(Trade, trade_id)
        if not trade:
            return jsonify({"error": "NOT_FOUND", "message": "Trade not found"}), 404

        side_a = sides[0]
        side_b = sides[1]

        side_a_team_id = int(side_a["team_id"])
        side_b_team_id = int(side_b["team_id"])

        trade.week = int(week) if week is not None else trade.week
        trade.proposing_team_id = side_a_team_id
        trade.accepting_team_id = side_b_team_id
        trade.faab_from_accepter = int(side_a.get("faab_received", 0))
        trade.faab_from_proposer = int(side_b.get("faab_received", 0))

        trade_summary = dict(trade.trade_summary or {})
        trade_summary["commissioner_edited"] = True
        trade.trade_summary = trade_summary

        # Find or create corresponding Transaction
        tx = (
            session.query(Transaction)
            .filter_by(
                season_year=trade.season_year,
                espn_transaction_id=trade.espn_transaction_id,
            )
            .first()
        )
        if not tx:
            tx = (
                session.query(Transaction)
                .filter_by(
                    season_year=trade.season_year,
                    related_espn_transaction_id=trade.espn_transaction_id,
                )
                .first()
            )

        if tx:
            tx.week = trade.week
            tx.team_id = side_a_team_id
            raw_summary = dict(tx.raw_summary or {})
            raw_summary["commissioner_edited"] = True
            tx.raw_summary = raw_summary

            # Rebuild TransactionItems
            session.query(TransactionItem).filter_by(transaction_id=tx.id).delete()

            items_to_add: list[TransactionItem] = []

            # Side A receives from Side B
            for p_id in side_a.get("player_ids", []):
                items_to_add.append(
                    TransactionItem(
                        transaction_id=tx.id,
                        player_id=int(p_id),
                        from_team_id=side_b_team_id,
                        to_team_id=side_a_team_id,
                        item_type="TRADE",
                    )
                )
            for pick_obj in side_a.get("draft_picks", []):
                pick_pid = _resolve_or_create_pick_player(
                    session, pick_obj, trade.season_year
                )
                items_to_add.append(
                    TransactionItem(
                        transaction_id=tx.id,
                        player_id=pick_pid,
                        from_team_id=side_b_team_id,
                        to_team_id=side_a_team_id,
                        item_type="TRADE",
                    )
                )

            # Side B receives from Side A
            for p_id in side_b.get("player_ids", []):
                items_to_add.append(
                    TransactionItem(
                        transaction_id=tx.id,
                        player_id=int(p_id),
                        from_team_id=side_a_team_id,
                        to_team_id=side_b_team_id,
                        item_type="TRADE",
                    )
                )
            for pick_obj in side_b.get("draft_picks", []):
                pick_pid = _resolve_or_create_pick_player(
                    session, pick_obj, trade.season_year
                )
                items_to_add.append(
                    TransactionItem(
                        transaction_id=tx.id,
                        player_id=pick_pid,
                        from_team_id=side_a_team_id,
                        to_team_id=side_b_team_id,
                        item_type="TRADE",
                    )
                )

            session.add_all(items_to_add)

        # Update db/trade_overrides.json
        overrides = load_trade_overrides()
        edited_trades = overrides.setdefault("edited_trades", {})
        edited_trades[trade.espn_transaction_id] = {
            "week": trade.week,
            "sides": sides,
            "proposing_team_id": side_a_team_id,
            "accepting_team_id": side_b_team_id,
        }
        save_trade_overrides(overrides)

        session.commit()
        return (
            jsonify({"message": "Trade updated successfully", "trade_id": trade.id}),
            200,
        )


@trades_bp.route("/trades", methods=["POST"])
def create_trade() -> tuple[Any, int]:
    """Manually create a new bilateral trade record."""
    if not _is_admin_authenticated():
        return _unauthorized_response()

    data = request.get_json() or {}
    season_year = int(data.get("season_year") or 0)
    week = int(data.get("week") or 1)
    sides = data.get("sides") or []
    if season_year <= 0 or len(sides) < 2:
        return (
            jsonify(
                {
                    "error": "BAD_REQUEST",
                    "message": "Invalid trade payload; season_year and 2 sides required",
                }
            ),
            400,
        )

    session_factory = current_app.config.get("SESSION_FACTORY", SessionLocal)
    with session_factory() as session:
        side_a = sides[0]
        side_b = sides[1]

        side_a_team_id = int(side_a["team_id"])
        side_b_team_id = int(side_b["team_id"])
        faab_a = int(side_a.get("faab_received", 0))
        faab_b = int(side_b.get("faab_received", 0))

        espn_tx_id = f"manual-trade-{uuid4().hex[:10]}"
        now = datetime.now(UTC)

        tx = Transaction(
            season_year=season_year,
            week=week,
            scoring_period=week,
            espn_transaction_id=espn_tx_id,
            transaction_type="TRADE",
            status="EXECUTED",
            team_id=side_a_team_id,
            proposed_at=now,
            executed_at=now,
            is_commissioner_override=True,
            raw_summary={"commissioner_edited": True, "is_manual": True},
        )
        session.add(tx)
        session.flush()

        trade = Trade(
            season_year=season_year,
            week=week,
            espn_transaction_id=espn_tx_id,
            proposing_team_id=side_a_team_id,
            accepting_team_id=side_b_team_id,
            status="EXECUTED",
            proposed_at=now,
            executed_at=now,
            faab_from_proposer=faab_b,
            faab_from_accepter=faab_a,
            trade_summary={"commissioner_edited": True, "is_manual": True},
        )
        session.add(trade)
        session.flush()

        items_to_add: list[TransactionItem] = []

        # Side A receives from Side B
        for p_id in side_a.get("player_ids", []):
            items_to_add.append(
                TransactionItem(
                    transaction_id=tx.id,
                    player_id=int(p_id),
                    from_team_id=side_b_team_id,
                    to_team_id=side_a_team_id,
                    item_type="TRADE",
                )
            )
        for pick_obj in side_a.get("draft_picks", []):
            pick_pid = _resolve_or_create_pick_player(session, pick_obj, season_year)
            items_to_add.append(
                TransactionItem(
                    transaction_id=tx.id,
                    player_id=pick_pid,
                    from_team_id=side_b_team_id,
                    to_team_id=side_a_team_id,
                    item_type="TRADE",
                )
            )

        # Side B receives from Side A
        for p_id in side_b.get("player_ids", []):
            items_to_add.append(
                TransactionItem(
                    transaction_id=tx.id,
                    player_id=int(p_id),
                    from_team_id=side_a_team_id,
                    to_team_id=side_b_team_id,
                    item_type="TRADE",
                )
            )
        for pick_obj in side_b.get("draft_picks", []):
            pick_pid = _resolve_or_create_pick_player(session, pick_obj, season_year)
            items_to_add.append(
                TransactionItem(
                    transaction_id=tx.id,
                    player_id=pick_pid,
                    from_team_id=side_a_team_id,
                    to_team_id=side_b_team_id,
                    item_type="TRADE",
                )
            )

        session.add_all(items_to_add)

        # Save to overrides
        overrides = load_trade_overrides()
        edited_trades = overrides.setdefault("edited_trades", {})
        edited_trades[espn_tx_id] = {
            "season_year": season_year,
            "week": week,
            "sides": sides,
            "proposing_team_id": side_a_team_id,
            "accepting_team_id": side_b_team_id,
        }
        save_trade_overrides(overrides)

        session.commit()
        return (
            jsonify({"message": "Trade created successfully", "trade_id": trade.id}),
            201,
        )


@trades_bp.route("/trades/<int:trade_id>", methods=["DELETE"])
def delete_trade(trade_id: int) -> tuple[Any, int]:
    """Mark trade as DELETED and cancel its underlying transaction."""
    if not _is_admin_authenticated():
        return _unauthorized_response()

    session_factory = current_app.config.get("SESSION_FACTORY", SessionLocal)
    with session_factory() as session:
        trade = session.get(Trade, trade_id)
        if not trade:
            return jsonify({"error": "NOT_FOUND", "message": "Trade not found"}), 404

        trade.status = "DELETED"

        txs = (
            session.query(Transaction)
            .filter(
                Transaction.season_year == trade.season_year,
                or_(
                    Transaction.espn_transaction_id == trade.espn_transaction_id,
                    Transaction.related_espn_transaction_id == trade.espn_transaction_id,
                ),
            )
            .all()
        )
        for tx in txs:
            tx.status = "CANCELED"

        # Update overrides
        overrides = load_trade_overrides()
        deleted_list = overrides.setdefault("deleted_trades", [])
        if trade.espn_transaction_id not in deleted_list:
            deleted_list.append(trade.espn_transaction_id)
        save_trade_overrides(overrides)

        session.commit()
        return (
            jsonify({"message": "Trade deleted successfully", "trade_id": trade.id}),
            200,
        )


@trades_bp.route("/trades/<int:trade_id>/restore", methods=["POST"])
def restore_trade(trade_id: int) -> tuple[Any, int]:
    """Restore a previously deleted trade back to EXECUTED status."""
    if not _is_admin_authenticated():
        return _unauthorized_response()

    session_factory = current_app.config.get("SESSION_FACTORY", SessionLocal)
    with session_factory() as session:
        trade = session.get(Trade, trade_id)
        if not trade:
            return jsonify({"error": "NOT_FOUND", "message": "Trade not found"}), 404

        trade.status = "EXECUTED"

        txs = (
            session.query(Transaction)
            .filter(
                Transaction.season_year == trade.season_year,
                or_(
                    Transaction.espn_transaction_id == trade.espn_transaction_id,
                    Transaction.related_espn_transaction_id == trade.espn_transaction_id,
                ),
            )
            .all()
        )
        for tx in txs:
            tx.status = "EXECUTED"

        # Update overrides
        overrides = load_trade_overrides()
        deleted_list = overrides.setdefault("deleted_trades", [])
        if trade.espn_transaction_id in deleted_list:
            deleted_list.remove(trade.espn_transaction_id)
        save_trade_overrides(overrides)

        session.commit()
        return (
            jsonify({"message": "Trade restored successfully", "trade_id": trade.id}),
            200,
        )
