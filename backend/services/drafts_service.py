"""backend/services/drafts_service.py - Draft History & Future Draft Order Service.

Purpose:
    Provides domain logic for previous draft boards and future draft pick order:
      - Future Draft (default: 2027):
          * Provisional draft order based on active season standings (reverse standings)
          * 16-round snake draft board tracking each pick's original team and current owner
          * Replays bilateral trades to follow picks as they move between franchises
          * Team draft capital inventory (total picks, net picks +/- differential, acquired vs. traded away)
          * Traded picks audit feed
      - Previous Drafts (e.g. 2026, 2025):
          * 192-pick draft board with drafted player details, positions, CDN headshots, and keepers
          * Traded pick detection (identifying when a pick was drafted by an acquiring team)
          * Flexible grouping by round and by team
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from backend.models.draft import DraftPick, DraftSettings, TradedDraftPick
from backend.models.manager import Manager
from backend.models.player import Player
from backend.models.season import Season
from backend.models.team import Team
from backend.models.transaction import Transaction, TransactionItem


def get_draft_data(session: Session, season_filter: int | None = None) -> dict[str, Any]:
    """Retrieve full draft payload for either a future draft (default 2027) or past draft boards."""
    try:
        from backend.database import init_db

        bind = session.get_bind()
        if bind is not None:
            init_db(bind)
    except Exception:
        pass

    seasons = session.query(Season).order_by(Season.season_year.desc()).all()
    active_season = next((s for s in seasons if s.is_active), seasons[0] if seasons else None)

    future_year = (active_season.season_year + 1) if active_season else 2027

    # Construct available seasons list starting with future draft year
    past_years = [s.season_year for s in seasons]
    available_seasons = [future_year] + [y for y in past_years if y != future_year]

    # Default to future draft year (2027) when not specified
    selected_season = season_filter if season_filter is not None else future_year

    is_future = selected_season >= future_year

    if is_future:
        future_data = _build_future_draft_data(session, selected_season, active_season)
        return {
            "selected_season": selected_season,
            "available_seasons": available_seasons,
            "is_future_draft": True,
            "league_size": future_data["league_size"],
            "total_rounds": future_data["total_rounds"],
            "future_draft": future_data,
            "historical_draft": None,
        }
    else:
        historical_data = _build_historical_draft_data(session, selected_season)
        return {
            "selected_season": selected_season,
            "available_seasons": available_seasons,
            "is_future_draft": False,
            "league_size": historical_data["league_size"],
            "total_rounds": historical_data["total_rounds"],
            "future_draft": None,
            "historical_draft": historical_data,
        }


def _build_future_draft_data(
    session: Session,
    future_season_year: int,
    active_season: Season | None,
) -> dict[str, Any]:
    """Build provisional draft order, pick-by-pick board, and team inventories for a future draft."""
    ref_season_year = active_season.season_year if active_season else (future_season_year - 1)

    teams = (
        session.query(Team)
        .join(Manager, Team.manager_id == Manager.id)
        .filter(Team.season_year == ref_season_year)
        .all()
    )
    mgr_map = {m.id: m.display_name for m in session.query(Manager).all()}

    league_size = len(teams) or 12
    total_rounds = 16

    # 1. Draft Order Resolution:
    # Check if official ESPN draftSettings.pickOrder exists for future_season_year.
    # Otherwise, project provisional order using reverse standings from the active season
    # (lowest win percentage picks first; tiebreaker is lowest points_for).
    future_settings = session.get(DraftSettings, future_season_year)
    is_official_order = False
    if (
        future_settings
        and future_settings.pick_order
        and len(future_settings.pick_order) >= len(teams)
    ):
        slot_map = {espn_id: idx for idx, espn_id in enumerate(future_settings.pick_order)}
        sorted_teams = sorted(teams, key=lambda t: slot_map.get(t.espn_team_id, 999))
        is_official_order = True
    else:
        sorted_teams = sorted(
            teams,
            key=lambda t: (
                float(t.wins) / max(1, t.wins + t.losses + t.ties),
                float(t.points_for or 0),
            ),
        )

    team_lookup = {t.id: t for t in teams}

    def _team_dict(t: Team) -> dict[str, Any]:
        return {
            "team_id": t.id,
            "espn_team_id": t.espn_team_id,
            "team_name": t.team_name,
            "manager_id": t.manager_id,
            "manager_name": mgr_map.get(t.manager_id, ""),
            "logo_url": t.logo_url,
        }

    # Assign provisional draft slot (1-indexed)
    provisional_slots: dict[int, int] = {}
    ordered_teams_summary: list[dict[str, Any]] = []
    for slot_idx, team in enumerate(sorted_teams, start=1):
        provisional_slots[team.id] = slot_idx
        ordered_teams_summary.append({
            **_team_dict(team),
            "provisional_slot": slot_idx,
            "record": f"{team.wins}-{team.losses}" + (f"-{team.ties}" if team.ties else ""),
            "points_for": round(float(team.points_for or 0), 1),
            "total_picks": 0,
            "net_picks": 0,
            "picks_held": [],
            "picks_traded_away": [],
            "picks_acquired": [],
        })

    # 2. Base Draft Board (16 Rounds × League Size) in Snake Order
    # Round 1: Slot 1 -> 12
    # Round 2: Slot 12 -> 1
    # Round 3: Slot 1 -> 12, etc.
    board_picks_by_round: dict[int, list[dict[str, Any]]] = defaultdict(list)
    pick_lookup_by_round_orig_espn: dict[tuple[int, int], dict[str, Any]] = {}
    pick_lookup_by_round_orig_tid: dict[tuple[int, int], dict[str, Any]] = {}

    for round_num in range(1, total_rounds + 1):
        is_even_round = (round_num % 2 == 0)
        round_slots = list(reversed(sorted_teams)) if is_even_round else sorted_teams

        for round_pick, orig_team in enumerate(round_slots, start=1):
            projected_overall = (round_num - 1) * league_size + round_pick
            pick_data: dict[str, Any] = {
                "round": round_num,
                "round_pick": round_pick,
                "projected_overall_pick": projected_overall,
                "original_slot": provisional_slots[orig_team.id],
                "original_team": _team_dict(orig_team),
                "current_team": _team_dict(orig_team),
                "is_traded": False,
                "trade_details": None,
                "movement_history": [_team_dict(orig_team)],
            }
            board_picks_by_round[round_num].append(pick_data)
            pick_lookup_by_round_orig_espn[(round_num, orig_team.espn_team_id)] = pick_data
            pick_lookup_by_round_orig_tid[(round_num, orig_team.id)] = pick_data

    # 3. Query and Apply Traded Draft Picks for this future season
    traded_picks_records = (
        session.query(TradedDraftPick, TransactionItem, Transaction)
        .join(TransactionItem, TradedDraftPick.transaction_item_id == TransactionItem.id)
        .join(Transaction, TransactionItem.transaction_id == Transaction.id)
        .filter(
            TradedDraftPick.draft_year == future_season_year,
            Transaction.status == "EXECUTED",
        )
        .order_by(Transaction.executed_at.asc(), Transaction.id.asc())
        .all()
    )

    # Secondary check: find any TransactionItems with draft pick placeholder players for this year
    # that may not have TradedDraftPick attached yet
    all_trade_items = (
        session.query(TransactionItem, Transaction, Player)
        .join(Transaction, TransactionItem.transaction_id == Transaction.id)
        .join(Player, TransactionItem.player_id == Player.espn_player_id)
        .filter(
            Transaction.status == "EXECUTED",
            TransactionItem.item_type == "TRADE",
            Player.default_position == "PICK",
        )
        .order_by(Transaction.executed_at.asc(), Transaction.id.asc())
        .all()
    )

    # Traded picks ledger feed
    traded_picks_log: list[dict[str, Any]] = []
    processed_item_ids: set[int] = set()

    for traded_pick, item, tx in traded_picks_records:
        processed_item_ids.add(item.id)
        round_num = traded_pick.round
        from_team = team_lookup.get(item.from_team_id) if item.from_team_id else None
        to_team = team_lookup.get(item.to_team_id) if item.to_team_id else None
        if not to_team:
            continue

        orig_espn = traded_pick.original_espn_team_id
        target_pick = None

        if orig_espn and (round_num, orig_espn) in pick_lookup_by_round_orig_espn:
            target_pick = pick_lookup_by_round_orig_espn[(round_num, orig_espn)]
        elif from_team and (round_num, from_team.id) in pick_lookup_by_round_orig_tid:
            target_pick = pick_lookup_by_round_orig_tid[(round_num, from_team.id)]
        else:
            # Fallback to any pick in this round held by from_team
            round_list = board_picks_by_round.get(round_num, [])
            target_pick = next(
                (p for p in round_list if p["current_team"]["team_id"] == from_team.id),
                None
            ) if from_team else None

        if target_pick:
            target_pick["current_team"] = _team_dict(to_team)
            target_pick["is_traded"] = True
            trade_info = {
                "transaction_id": tx.id,
                "espn_transaction_id": tx.espn_transaction_id,
                "week": tx.week,
                "executed_at": tx.executed_at.isoformat() if tx.executed_at else None,
                "from_team": _team_dict(from_team) if from_team else None,
                "to_team": _team_dict(to_team),
            }
            target_pick["trade_details"] = trade_info
            target_pick["movement_history"].append(_team_dict(to_team))

            traded_picks_log.append({
                "round": round_num,
                "projected_overall_pick": target_pick["projected_overall_pick"],
                "original_team": target_pick["original_team"],
                "from_team": _team_dict(from_team) if from_team else None,
                "to_team": _team_dict(to_team),
                "week": tx.week,
                "executed_at": tx.executed_at.isoformat() if tx.executed_at else None,
                "espn_transaction_id": tx.espn_transaction_id,
            })

    # Catch any legacy placeholder items
    for item, tx, player in all_trade_items:
        if item.id in processed_item_ids:
            continue
        # Check if player name or id references this future season
        round_match = re.search(r"Round\s+(\d+)", player.full_name or "", re.IGNORECASE)
        is_year = str(future_season_year) in (player.full_name or "") or str(player.espn_player_id).startswith(f"-{future_season_year}")
        if not is_year:
            continue

        round_num = int(round_match.group(1)) if round_match else 1
        from_team = team_lookup.get(item.from_team_id) if item.from_team_id else None
        to_team = team_lookup.get(item.to_team_id) if item.to_team_id else None
        if not to_team or not from_team:
            continue

        round_list = board_picks_by_round.get(round_num, [])
        target_pick = next(
            (p for p in round_list if p["current_team"]["team_id"] == from_team.id),
            None
        )
        if target_pick:
            target_pick["current_team"] = _team_dict(to_team)
            target_pick["is_traded"] = True
            trade_info = {
                "transaction_id": tx.id,
                "espn_transaction_id": tx.espn_transaction_id,
                "week": tx.week,
                "executed_at": tx.executed_at.isoformat() if tx.executed_at else None,
                "from_team": _team_dict(from_team),
                "to_team": _team_dict(to_team),
            }
            target_pick["trade_details"] = trade_info
            target_pick["movement_history"].append(_team_dict(to_team))
            traded_picks_log.append({
                "round": round_num,
                "projected_overall_pick": target_pick["projected_overall_pick"],
                "original_team": target_pick["original_team"],
                "from_team": _team_dict(from_team),
                "to_team": _team_dict(to_team),
                "week": tx.week,
                "executed_at": tx.executed_at.isoformat() if tx.executed_at else None,
                "espn_transaction_id": tx.espn_transaction_id,
            })

    # 4. Populate Team Inventories & Pick Counts
    teams_summary_map = {t["team_id"]: t for t in ordered_teams_summary}

    for round_num in range(1, total_rounds + 1):
        for pick in board_picks_by_round[round_num]:
            curr_tid = pick["current_team"]["team_id"]
            orig_tid = pick["original_team"]["team_id"]

            if curr_tid in teams_summary_map:
                teams_summary_map[curr_tid]["picks_held"].append(pick)
                teams_summary_map[curr_tid]["total_picks"] += 1
                if pick["is_traded"]:
                    teams_summary_map[curr_tid]["picks_acquired"].append(pick)

            if pick["is_traded"] and orig_tid in teams_summary_map:
                teams_summary_map[orig_tid]["picks_traded_away"].append(pick)

    for t_summary in ordered_teams_summary:
        t_summary["net_picks"] = t_summary["total_picks"] - total_rounds

    rounds_list = [
        {"round": r, "picks": board_picks_by_round[r]}
        for r in range(1, total_rounds + 1)
    ]

    return {
        "season_year": future_season_year,
        "reference_season_year": ref_season_year,
        "league_size": league_size,
        "total_rounds": total_rounds,
        "provisional_order_type": "OFFICIAL_ESPN" if is_official_order else "PENDING_SELECTION",
        "provisional_order_note": (
            f"Official {future_season_year} draft order confirmed from ESPN Draft Settings."
            if is_official_order
            else f"Draft order for {future_season_year} has not been determined yet. Each franchise must hold 16 draft picks on draft day to field a complete roster. Live pick capital and traded assets are tracked below."
        ),
        "rounds": rounds_list,
        "teams_summary": ordered_teams_summary,
        "traded_picks_log": traded_picks_log,
    }


def _build_historical_draft_data(session: Session, season_year: int) -> dict[str, Any]:
    """Build historical draft board (192 picks) with drafted players, keepers, and traded pick receipts."""
    picks_raw = (
        session.query(DraftPick)
        .filter(DraftPick.season_year == season_year)
        .order_by(DraftPick.overall_pick.asc())
        .all()
    )

    draft_settings = session.get(DraftSettings, season_year)
    draft_type = draft_settings.draft_type if draft_settings else "SNAKE"
    draft_date = draft_settings.draft_date.isoformat() if (draft_settings and draft_settings.draft_date) else None
    keeper_count = draft_settings.keeper_count if draft_settings else 0

    teams = session.query(Team).filter(Team.season_year == season_year).all()
    team_map = {t.id: t for t in teams}
    espn_team_map = {t.espn_team_id: t for t in teams}
    mgr_map = {m.id: m.display_name for m in session.query(Manager).all()}

    players_all = session.query(Player).all()
    player_map = {p.espn_player_id: p for p in players_all}

    # Traded pick mapping: check if any picks were acquired via trade prior to the draft
    # 1. TradedDraftPick table
    traded_picks = (
        session.query(TradedDraftPick, TransactionItem)
        .join(TransactionItem, TradedDraftPick.transaction_item_id == TransactionItem.id)
        .filter(TradedDraftPick.draft_year == season_year)
        .all()
    )
    # Map overall_pick -> original_espn_team_id
    traded_overall_map: dict[int, int] = {}
    for tp, _item in traded_picks:
        if tp.overall_pick and tp.original_espn_team_id:
            traded_overall_map[tp.overall_pick] = tp.original_espn_team_id

    # 2. Check preseason trades in transaction_items for draft pick player IDs
    preseason_pick_trades = (
        session.query(TransactionItem, Transaction)
        .join(Transaction, TransactionItem.transaction_id == Transaction.id)
        .filter(
            Transaction.season_year == season_year,
            Transaction.status == "EXECUTED",
            TransactionItem.item_type == "TRADE",
            TransactionItem.player_id < -100000,
        )
        .all()
    )
    for it, _tx in preseason_pick_trades:
        # e.g. player_id -100057 -> overall pick 57
        if -200000 < it.player_id <= -100000:
            overall = abs(it.player_id) - 100000
            from_t = team_map.get(it.from_team_id)
            if from_t:
                traded_overall_map[overall] = from_t.espn_team_id

    formatted_picks: list[dict[str, Any]] = []
    rounds_map: dict[int, list[dict[str, Any]]] = defaultdict(list)
    teams_picks_map: dict[int, list[dict[str, Any]]] = defaultdict(list)

    total_keepers = 0

    for dp in picks_raw:
        team = team_map.get(dp.team_id)
        player = player_map.get(dp.player_id) or dp.player
        if dp.is_keeper:
            total_keepers += 1

        was_traded = False
        orig_team_dict = None
        orig_espn = traded_overall_map.get(dp.overall_pick)
        if orig_espn and orig_espn in espn_team_map and team and team.espn_team_id != orig_espn:
            was_traded = True
            ot = espn_team_map[orig_espn]
            orig_team_dict = {
                "team_id": ot.id,
                "espn_team_id": ot.espn_team_id,
                "team_name": ot.team_name,
                "manager_id": ot.manager_id,
                "manager_name": mgr_map.get(ot.manager_id, ""),
                "logo_url": ot.logo_url,
            }

        pick_obj = {
            "overall_pick": dp.overall_pick,
            "round": dp.round,
            "round_pick": dp.round_pick,
            "bid_amount": dp.bid_amount,
            "is_keeper": dp.is_keeper,
            "was_traded": was_traded,
            "original_team": orig_team_dict,
            "drafting_team": {
                "team_id": team.id if team else dp.team_id,
                "espn_team_id": team.espn_team_id if team else 0,
                "team_name": team.team_name if team else f"Team {dp.team_id}",
                "manager_id": team.manager_id if team else 0,
                "manager_name": mgr_map.get(team.manager_id, "") if team else "",
                "logo_url": team.logo_url if team else None,
            },
            "player": {
                "player_id": player.espn_player_id if player else dp.player_id,
                "full_name": player.full_name if player else f"Player {dp.player_id}",
                "default_position": player.default_position if player else "FLEX",
                "pro_team": player.pro_team if player else "FA",
                "headshot_url": player.headshot_url if player else None,
            },
        }
        formatted_picks.append(pick_obj)
        rounds_map[dp.round].append(pick_obj)
        if team:
            teams_picks_map[team.id].append(pick_obj)

    max_round = max(rounds_map.keys()) if rounds_map else 16
    league_size = len(teams) or 12

    rounds_list = [
        {"round": r, "picks": rounds_map[r]}
        for r in range(1, max_round + 1)
    ]

    by_team_list = [
        {
            "team_id": t.id,
            "espn_team_id": t.espn_team_id,
            "team_name": t.team_name,
            "manager_id": t.manager_id,
            "manager_name": mgr_map.get(t.manager_id, ""),
            "logo_url": t.logo_url,
            "total_picks": len(teams_picks_map[t.id]),
            "keepers_count": sum(1 for p in teams_picks_map[t.id] if p["is_keeper"]),
            "picks": teams_picks_map[t.id],
        }
        for t in teams
    ]

    return {
        "season_year": season_year,
        "draft_type": draft_type,
        "draft_date": draft_date,
        "total_picks": len(formatted_picks),
        "total_rounds": max_round,
        "league_size": league_size,
        "keeper_count": total_keepers or keeper_count,
        "picks": formatted_picks,
        "rounds": rounds_list,
        "by_team": by_team_list,
    }
