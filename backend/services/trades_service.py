"""backend/services/trades_service.py - Bilateral Trades & Realized Value Service.

Purpose:
    Analyzes bilateral trades, trade partner networks, and realized ROI
    (post-acquisition fantasy points scored while started in subsequent weeks).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from backend.models.lineup import WeeklyLineup
from backend.models.manager import Manager
from backend.models.season import Season
from backend.models.team import Team
from backend.models.trade import Trade
from backend.models.transaction import Transaction, TransactionItem


def get_trades_trends(
    session: Session, season_filter: int | None = None
) -> dict[str, Any]:
    """Calculate trade volumes, partner networks, and realized starter point autopsies."""
    has_transaction_data = True
    if season_filter is not None:
        season = session.query(Season).filter(Season.season_year == season_filter).first()
        if season is not None:
            has_transaction_data = season.has_transaction_data
    else:
        # Check if any season has transaction data
        seasons = session.query(Season).all()
        has_transaction_data = any(s.has_transaction_data for s in seasons) if seasons else True

    # Pre-fetch master records
    teams = session.query(Team).order_by(Team.season_year.desc(), Team.id.desc()).all()
    team_map = {t.id: t for t in teams}
    latest_team_by_mgr: dict[int, Team] = {}
    for t in teams:
        if t.manager_id not in latest_team_by_mgr:
            latest_team_by_mgr[t.manager_id] = t

    managers = session.query(Manager).all()
    mgr_map = {m.id: m.display_name for m in managers}
    mgr_avatar_map = {m.id: m.avatar_url for m in managers}

    def _mgr_team_name(mid: int) -> str:
        if mid in latest_team_by_mgr:
            return latest_team_by_mgr[mid].team_name
        return mgr_map.get(mid, "")

    def _mgr_avatar(mid: int) -> str | None:
        if mid in latest_team_by_mgr and latest_team_by_mgr[mid].logo_url:
            return latest_team_by_mgr[mid].logo_url
        return mgr_avatar_map.get(mid)

    # Query completed trades
    trades_query = session.query(Trade).filter(Trade.status == "EXECUTED")
    if season_filter is not None:
        trades_query = trades_query.filter(Trade.season_year == season_filter)
    trades = trades_query.order_by(Trade.executed_at.desc(), Trade.id.desc()).all()

    # Pre-fetch trade transactions and items
    trade_tx_ids = [t.espn_transaction_id for t in trades]
    transactions = (
        session.query(Transaction)
        .filter(Transaction.espn_transaction_id.in_(trade_tx_ids))
        .all()
    )
    tx_by_espn_id = {tx.espn_transaction_id: tx for tx in transactions}

    # Pre-fetch transaction items
    tx_pks = [tx.id for tx in transactions]
    trade_items = (
        session.query(TransactionItem)
        .filter(
            TransactionItem.transaction_id.in_(tx_pks),
            TransactionItem.item_type == "TRADE",
        )
        .all()
    )
    items_by_tx_id: dict[int, list[TransactionItem]] = defaultdict(list)
    for item in trade_items:
        items_by_tx_id[item.transaction_id].append(item)

    # Pre-fetch weekly lineups with starters for post-trade ROI calculation
    lineup_query = session.query(WeeklyLineup).filter(WeeklyLineup.is_starter.is_(True))
    if season_filter is not None:
        lineup_query = lineup_query.filter(WeeklyLineup.season_year == season_filter)
    starter_lineups = lineup_query.all()

    # Index starter lineups by (season_year, team_id, player_id) -> list of (week, points)
    lineup_index: dict[tuple[int, int, int], list[tuple[int, float]]] = defaultdict(list)
    for wl in starter_lineups:
        key = (wl.season_year, wl.team_id, wl.player_id)
        lineup_index[key].append((wl.week, float(wl.actual_points)))

    # Metrics accumulators
    pair_trade_counts: dict[tuple[int, int], int] = defaultdict(int)
    trader_stats: dict[int, dict[str, Any]] = defaultdict(
        lambda: {
            "total_trades": 0,
            "players_acquired": 0,
            "players_traded_away": 0,
            "net_starter_points_gained": 0.0,
        }
    )

    trade_details: list[dict[str, Any]] = []

    for trade in trades:
        prop_team = team_map.get(trade.proposing_team_id)
        acc_team = team_map.get(trade.accepting_team_id)
        if not prop_team or not acc_team:
            continue

        prop_mgr_id = prop_team.manager_id
        acc_mgr_id = acc_team.manager_id

        # Update partner trade counts using normalized manager order
        pair_key = (min(prop_mgr_id, acc_mgr_id), max(prop_mgr_id, acc_mgr_id))
        pair_trade_counts[pair_key] += 1

        # Fetch transaction items for this trade
        tx = tx_by_espn_id.get(trade.espn_transaction_id)
        items = items_by_tx_id.get(tx.id, []) if tx else []

        # Split items by receiving team
        prop_assets_items = [i for i in items if i.to_team_id == prop_team.id]
        acc_assets_items = [i for i in items if i.to_team_id == acc_team.id]

        trade_week = trade.week or 0

        # Build assets for proposing team
        prop_assets: list[dict[str, Any]] = []
        prop_total_pts = 0.0
        for item in prop_assets_items:
            player = item.player
            history = lineup_index.get((trade.season_year, prop_team.id, item.player_id), [])
            post_pts = sum(pts for wk, pts in history if wk > trade_week)
            post_wks = sum(1 for wk, _ in history if wk > trade_week)
            prop_total_pts += post_pts
            prop_assets.append(
                {
                    "player_id": player.espn_player_id if player else item.player_id,
                    "full_name": player.full_name if player else "Unknown Player",
                    "default_position": player.default_position if player else "N/A",
                    "pro_team": player.pro_team if player else "FA",
                    "headshot_url": player.headshot_url if player else None,
                    "post_trade_starter_points": round(post_pts, 2),
                    "post_trade_weeks_started": post_wks,
                }
            )

        # Build assets for accepting team
        acc_assets: list[dict[str, Any]] = []
        acc_total_pts = 0.0
        for item in acc_assets_items:
            player = item.player
            history = lineup_index.get((trade.season_year, acc_team.id, item.player_id), [])
            post_pts = sum(pts for wk, pts in history if wk > trade_week)
            post_wks = sum(1 for wk, _ in history if wk > trade_week)
            acc_total_pts += post_pts
            acc_assets.append(
                {
                    "player_id": player.espn_player_id if player else item.player_id,
                    "full_name": player.full_name if player else "Unknown Player",
                    "default_position": player.default_position if player else "N/A",
                    "pro_team": player.pro_team if player else "FA",
                    "headshot_url": player.headshot_url if player else None,
                    "post_trade_starter_points": round(post_pts, 2),
                    "post_trade_weeks_started": post_wks,
                }
            )

        prop_total_pts = round(prop_total_pts, 2)
        acc_total_pts = round(acc_total_pts, 2)

        # Update manager career trader stats
        trader_stats[prop_mgr_id]["total_trades"] += 1
        trader_stats[prop_mgr_id]["players_acquired"] += len(prop_assets)
        trader_stats[prop_mgr_id]["players_traded_away"] += len(acc_assets)
        trader_stats[prop_mgr_id]["net_starter_points_gained"] += prop_total_pts - acc_total_pts

        trader_stats[acc_mgr_id]["total_trades"] += 1
        trader_stats[acc_mgr_id]["players_acquired"] += len(acc_assets)
        trader_stats[acc_mgr_id]["players_traded_away"] += len(prop_assets)
        trader_stats[acc_mgr_id]["net_starter_points_gained"] += acc_total_pts - prop_total_pts

        # Determine winner and differential
        if prop_total_pts > acc_total_pts:
            winner_mgr_id: int | None = prop_mgr_id
            diff = round(prop_total_pts - acc_total_pts, 2)
        elif acc_total_pts > prop_total_pts:
            winner_mgr_id = acc_mgr_id
            diff = round(acc_total_pts - prop_total_pts, 2)
        else:
            winner_mgr_id = None
            diff = 0.0

        executed_at_str = (
            trade.executed_at.isoformat().replace("+00:00", "Z")
            if trade.executed_at
            else None
        )

        trade_details.append(
            {
                "trade_id": trade.id,
                "season_year": trade.season_year,
                "week": trade.week,
                "executed_at": executed_at_str,
                "espn_transaction_id": trade.espn_transaction_id,
                "sides": [
                    {
                        "team_id": prop_team.id,
                        "team_name": prop_team.team_name,
                        "logo_url": prop_team.logo_url or mgr_avatar_map.get(prop_mgr_id),
                        "manager_id": prop_mgr_id,
                        "manager_name": mgr_map.get(prop_mgr_id, ""),
                        "assets_received": prop_assets,
                        "faab_received": trade.faab_from_accepter,
                        "total_starter_points_gained": prop_total_pts,
                    },
                    {
                        "team_id": acc_team.id,
                        "team_name": acc_team.team_name,
                        "logo_url": acc_team.logo_url or mgr_avatar_map.get(acc_mgr_id),
                        "manager_id": acc_mgr_id,
                        "manager_name": mgr_map.get(acc_mgr_id, ""),
                        "assets_received": acc_assets,
                        "faab_received": trade.faab_from_proposer,
                        "total_starter_points_gained": acc_total_pts,
                    },
                ],
                "winner_manager_id": winner_mgr_id,
                "point_differential": diff,
            }
        )

    # Build Top Trade Partners list
    top_partners = [
        {
            "manager_a_id": pair[0],
            "manager_a_name": mgr_map.get(pair[0], ""),
            "manager_a_team_name": _mgr_team_name(pair[0]),
            "manager_a_avatar_url": _mgr_avatar(pair[0]),
            "manager_b_id": pair[1],
            "manager_b_name": mgr_map.get(pair[1], ""),
            "manager_b_team_name": _mgr_team_name(pair[1]),
            "manager_b_avatar_url": _mgr_avatar(pair[1]),
            "trade_count": count,
        }
        for pair, count in sorted(pair_trade_counts.items(), key=lambda x: -x[1])
    ]

    # Build Active Traders list
    active_traders = [
        {
            "manager_id": mid,
            "display_name": mgr_map.get(mid, ""),
            "team_name": _mgr_team_name(mid),
            "avatar_url": _mgr_avatar(mid),
            "total_trades": data["total_trades"],
            "players_acquired": data["players_acquired"],
            "players_traded_away": data["players_traded_away"],
            "net_starter_points_gained": round(data["net_starter_points_gained"], 2),
        }
        for mid, data in sorted(
            trader_stats.items(),
            key=lambda x: (-x[1]["total_trades"], -x[1]["net_starter_points_gained"]),
        )
    ]

    return {
        "season_filter": season_filter,
        "has_transaction_data": has_transaction_data,
        "top_partners": top_partners,
        "active_traders": active_traders,
        "trades": trade_details,
    }
