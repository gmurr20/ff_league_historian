"""backend/services/transactions_service.py - Transactions & FAAB Bidding Wars Service.

Purpose:
    Analyzes manager FAAB efficiency, waiver claim success rates, failure reason breakdowns,
    FAAB Bidding War receipts, and transaction audit trails.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from backend.models.lineup import WeeklyLineup
from backend.models.manager import Manager
from backend.models.season import Season
from backend.models.team import Team
from backend.models.transaction import Transaction, TransactionItem


def get_transactions_summary(
    session: Session, season_year: int | None = None
) -> dict[str, Any]:
    """Calculate FAAB efficiency, bidding wars, and transaction audit log for a season."""
    if season_year is not None:
        season = session.query(Season).filter(Season.season_year == season_year).first()
        if season is None:
            raise ValueError(f"Season {season_year} not found")
    else:
        season = session.query(Season).filter(Season.is_active.is_(True)).first()
        if season is None:
            season = session.query(Season).order_by(Season.season_year.desc()).first()
        if season is None:
            raise ValueError("No seasons found in database")

    has_transaction_data = season.has_transaction_data

    # Pre-fetch master managers, teams, and players
    managers = session.query(Manager).all()
    mgr_map = {m.id: m.display_name for m in managers}
    mgr_avatar_map = {m.id: m.avatar_url for m in managers}

    teams = session.query(Team).all()
    team_map = {t.id: t for t in teams}

    # Pre-fetch starter lineups in this season for realized point lookups
    starter_lineups = (
        session.query(WeeklyLineup)
        .filter(
            WeeklyLineup.season_year == season.season_year,
            WeeklyLineup.is_starter.is_(True),
        )
        .all()
    )
    # Index: (team_id, player_id) -> list of (week, points)
    lineup_index: dict[tuple[int, int], list[tuple[int, float]]] = defaultdict(list)
    for wl in starter_lineups:
        lineup_index[(wl.team_id, wl.player_id)].append((wl.week, float(wl.actual_points)))

    # Fetch all transactions for this season
    transactions = (
        session.query(Transaction)
        .filter(Transaction.season_year == season.season_year)
        .order_by(Transaction.executed_at.desc().nullslast(), Transaction.id.desc())
        .all()
    )

    # Pre-fetch transaction items
    tx_ids = [tx.id for tx in transactions]
    items = (
        session.query(TransactionItem)
        .filter(TransactionItem.transaction_id.in_(tx_ids))
        .all()
    )
    items_by_tx: dict[int, list[TransactionItem]] = defaultdict(list)
    for item in items:
        items_by_tx[item.transaction_id].append(item)

    # 1. Failure reasons breakdown
    failure_counts: dict[str, int] = defaultdict(int)
    for tx in transactions:
        if tx.status == "FAILED" and tx.failure_reason:
            failure_counts[tx.failure_reason] += 1

    failure_reasons = [
        {"reason": reason, "count": count}
        for reason, count in sorted(failure_counts.items(), key=lambda x: -x[1])
    ]

    # 2. Bidding Wars
    # Group failed waiver bids pointing to a winning claim via related_espn_transaction_id
    losing_bids_by_winning_espn_id: dict[str, list[Transaction]] = defaultdict(list)
    for tx in transactions:
        if tx.status == "FAILED" and tx.related_espn_transaction_id:
            losing_bids_by_winning_espn_id[tx.related_espn_transaction_id].append(tx)

    # Map transactions by espn_transaction_id
    tx_by_espn_id = {tx.espn_transaction_id: tx for tx in transactions}

    bidding_wars: list[dict[str, Any]] = []
    for winning_espn_id, losing_txs in losing_bids_by_winning_espn_id.items():
        win_tx = tx_by_espn_id.get(winning_espn_id)
        if not win_tx or not win_tx.team_id:
            continue

        win_team = team_map.get(win_tx.team_id)
        if not win_team:
            continue

        win_items = items_by_tx.get(win_tx.id, [])
        first_item = win_items[0] if win_items else None
        player = first_item.player if first_item else None

        pid = player.espn_player_id if player else (first_item.player_id if first_item else 0)
        pname = player.full_name if player else "Unknown Player"
        ppos = player.default_position if player else "N/A"
        pro_team = player.pro_team if player else "FA"
        pheadshot = player.headshot_url if player else None

        # Calculate realized points scored by claimed player while started
        claim_week = win_tx.week or 0
        claim_history = lineup_index.get((win_team.id, pid), [])
        post_claim_pts = sum(pts for wk, pts in claim_history if wk >= claim_week)

        # Build losing bids sorted by bid_amount DESC, waiver_priority ASC
        formatted_losing: list[dict[str, Any]] = []
        for ltx in sorted(
            losing_txs,
            key=lambda x: (-x.bid_amount, x.waiver_priority or 999),
        ):
            l_team = team_map.get(ltx.team_id) if ltx.team_id else None
            l_mgr_id = l_team.manager_id if l_team else (ltx.team.manager_id if ltx.team else 0)
            formatted_losing.append(
                {
                    "transaction_id": ltx.id,
                    "team_id": ltx.team_id,
                    "team_name": l_team.team_name if l_team else None,
                    "logo_url": (
                        l_team.logo_url
                        if l_team and l_team.logo_url
                        else mgr_avatar_map.get(l_mgr_id)
                    ),
                    "manager_id": l_mgr_id,
                    "manager_name": mgr_map.get(l_mgr_id, ""),
                    "bid_amount": ltx.bid_amount,
                    "failure_reason": ltx.failure_reason or "UNKNOWN",
                    "waiver_priority": ltx.waiver_priority,
                }
            )

        executed_at_str = (
            win_tx.executed_at.isoformat().replace("+00:00", "Z")
            if win_tx.executed_at
            else None
        )

        bidding_wars.append(
            {
                "winning_transaction_id": win_tx.id,
                "espn_transaction_id": win_tx.espn_transaction_id,
                "season_year": win_tx.season_year,
                "week": win_tx.week,
                "executed_at": executed_at_str,
                "player": {
                    "player_id": pid,
                    "full_name": pname,
                    "default_position": ppos,
                    "pro_team": pro_team,
                    "headshot_url": pheadshot,
                },
                "winner": {
                    "team_id": win_team.id,
                    "team_name": win_team.team_name,
                    "logo_url": win_team.logo_url or mgr_avatar_map.get(win_team.manager_id),
                    "manager_id": win_team.manager_id,
                    "manager_name": mgr_map.get(win_team.manager_id, ""),
                    "bid_amount": win_tx.bid_amount,
                    "post_claim_starter_points": round(post_claim_pts, 2),
                },
                "losing_bids": formatted_losing,
            }
        )

    bidding_wars.sort(
        key=lambda x: (x["week"] or 0, x["winner"]["bid_amount"]),
        reverse=True,
    )

    # 3. Manager Efficiency
    # Group transactions by team_id
    team_txs: dict[int, list[Transaction]] = defaultdict(list)
    for tx in transactions:
        if tx.team_id:
            team_txs[tx.team_id].append(tx)

    manager_efficiency: list[dict[str, Any]] = []
    season_teams = [t for t in teams if t.season_year == season.season_year]
    for team in season_teams:
        tid = team.id
        my_txs = team_txs.get(tid, [])

        exec_waivers = sum(
            1 for tx in my_txs if tx.transaction_type == "WAIVER" and tx.status == "EXECUTED"
        )
        failed_waivers = sum(
            1 for tx in my_txs if tx.transaction_type == "WAIVER" and tx.status == "FAILED"
        )
        total_waivers = exec_waivers + failed_waivers
        waiver_rate = (
            round(exec_waivers / total_waivers, 2) if total_waivers > 0 else 0.0
        )

        fa_adds = sum(
            1 for tx in my_txs if tx.transaction_type == "FREE_AGENT" and tx.status == "EXECUTED"
        )

        # Drops count
        drops = sum(
            1 for tx in my_txs if tx.transaction_type == "DROP" and tx.status == "EXECUTED"
        )
        for tx in my_txs:
            for item in items_by_tx.get(tx.id, []):
                if item.item_type == "DROP" and tx.transaction_type != "DROP":
                    drops += 1

        faab_budget = season.faab_budget
        faab_spent = max(0, faab_budget - team.faab_remaining)

        # Starter points from waiver acquisitions
        starter_pts_from_waivers = 0.0
        for tx in my_txs:
            if tx.transaction_type == "WAIVER" and tx.status == "EXECUTED":
                claim_wk = tx.week or 0
                for item in items_by_tx.get(tx.id, []):
                    if item.item_type == "ADD":
                        hist = lineup_index.get((tid, item.player_id), [])
                        starter_pts_from_waivers += sum(
                            pts for wk, pts in hist if wk >= claim_wk
                        )

        starter_pts_from_waivers = round(starter_pts_from_waivers, 2)
        pts_per_dollar = (
            round(starter_pts_from_waivers / faab_spent, 2) if faab_spent > 0 else None
        )

        manager_efficiency.append(
            {
                "manager_id": team.manager_id,
                "display_name": mgr_map.get(team.manager_id, ""),
                "team_name": team.team_name,
                "logo_url": team.logo_url or mgr_avatar_map.get(team.manager_id),
                "faab_budget": faab_budget,
                "faab_spent": faab_spent,
                "faab_remaining": team.faab_remaining,
                "executed_waivers": exec_waivers,
                "failed_waivers": failed_waivers,
                "waiver_success_rate": waiver_rate,
                "free_agent_adds": fa_adds,
                "drops": drops,
                "total_starter_points_from_waivers": starter_pts_from_waivers,
                "points_per_faab_dollar": pts_per_dollar,
            }
        )

    manager_efficiency.sort(
        key=lambda x: (
            -x["total_starter_points_from_waivers"],
            -x["waiver_success_rate"],
        )
    )

    # 4. Raw Transactions Audit Feed
    transactions_feed: list[dict[str, Any]] = []
    for tx in transactions:
        tx_team = team_map.get(tx.team_id) if tx.team_id else None
        tx_mgr_id = tx_team.manager_id if tx_team else None
        tx_mgr_name = mgr_map.get(tx_mgr_id, "") if tx_mgr_id else None

        item_list = []
        for it in items_by_tx.get(tx.id, []):
            f_team = team_map.get(it.from_team_id) if it.from_team_id else None
            t_team = team_map.get(it.to_team_id) if it.to_team_id else None
            f_mgr_id = f_team.manager_id if f_team else None
            t_mgr_id = t_team.manager_id if t_team else None

            pname = it.player.full_name if it.player else "Unknown Player"
            ppos = it.player.default_position if it.player else "N/A"
            pro_team = it.player.pro_team if it.player else "FA"
            pheadshot = it.player.headshot_url if it.player else None

            item_list.append(
                {
                    "player_id": it.player_id,
                    "full_name": pname,
                    "default_position": ppos,
                    "pro_team": pro_team,
                    "headshot_url": pheadshot,
                    "item_type": it.item_type,
                    "from_team_id": it.from_team_id,
                    "to_team_id": it.to_team_id,
                    "from_team_name": f_team.team_name if f_team else None,
                    "to_team_name": t_team.team_name if t_team else None,
                    "from_manager_id": f_mgr_id,
                    "to_manager_id": t_mgr_id,
                    "from_manager_name": mgr_map.get(f_mgr_id) if f_mgr_id else None,
                    "to_manager_name": mgr_map.get(t_mgr_id) if t_mgr_id else None,
                }
            )

        tx_exec_str = (
            tx.executed_at.isoformat().replace("+00:00", "Z")
            if tx.executed_at
            else None
        )

        transactions_feed.append(
            {
                "transaction_id": tx.id,
                "espn_transaction_id": tx.espn_transaction_id,
                "season_year": tx.season_year,
                "week": tx.week,
                "transaction_type": tx.transaction_type,
                "status": tx.status,
                "team_id": tx.team_id,
                "team_name": tx_team.team_name if tx_team else None,
                "logo_url": (
                    tx_team.logo_url
                    if tx_team and tx_team.logo_url
                    else (mgr_avatar_map.get(tx_mgr_id) if tx_mgr_id else None)
                ),
                "manager_id": tx_mgr_id,
                "manager_name": tx_mgr_name,
                "bid_amount": tx.bid_amount,
                "waiver_priority": tx.waiver_priority,
                "failure_reason": tx.failure_reason,
                "executed_at": tx_exec_str,
                "related_espn_transaction_id": tx.related_espn_transaction_id,
                "items": item_list,
            }
        )

    return {
        "season_year": season.season_year,
        "has_transaction_data": has_transaction_data,
        "manager_efficiency": manager_efficiency,
        "failure_reasons": failure_reasons,
        "bidding_wars": bidding_wars,
        "transactions": transactions_feed,
    }
