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

from backend.jobs.parsers import get_combined_trade_overrides
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
    trade_overrides = get_combined_trade_overrides(session)
    deleted_trade_ids = set(trade_overrides.get("deleted_trades", []))
    edited_trades = trade_overrides.get("edited_trades", {})
    espn_team_lookup = {t.espn_team_id: t for t in teams}

    # Fetch rich TradeDetail objects for any trades linked to draft picks
    trade_detail_map: dict[str, dict[str, Any]] = {}
    try:
        from backend.services.trades_service import get_trades_trends
        trends_payload = get_trades_trends(session, None)
        for t_obj in trends_payload.get("trades", []):
            if isinstance(t_obj, dict) and t_obj.get("espn_transaction_id"):
                trade_detail_map[str(t_obj["espn_transaction_id"])] = t_obj
    except Exception:
        trade_detail_map = {}

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
        if tx.espn_transaction_id in deleted_trade_ids or (
            tx.related_espn_transaction_id and tx.related_espn_transaction_id in deleted_trade_ids
        ):
            continue
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
            tx_detail = trade_detail_map.get(str(tx.espn_transaction_id))
            trade_info = {
                "transaction_id": tx.id,
                "espn_transaction_id": tx.espn_transaction_id,
                "week": tx.week,
                "executed_at": tx.executed_at.isoformat() if tx.executed_at else None,
                "from_team": _team_dict(from_team) if from_team else None,
                "to_team": _team_dict(to_team),
                "trade_detail": tx_detail,
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
                "trade_detail": tx_detail,
            })

    # Catch any legacy placeholder items
    for item, tx, player in all_trade_items:
        if tx.espn_transaction_id in deleted_trade_ids or (
            tx.related_espn_transaction_id and tx.related_espn_transaction_id in deleted_trade_ids
        ):
            continue
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
            tx_detail = trade_detail_map.get(str(tx.espn_transaction_id))
            trade_info = {
                "transaction_id": tx.id,
                "espn_transaction_id": tx.espn_transaction_id,
                "week": tx.week,
                "executed_at": tx.executed_at.isoformat() if tx.executed_at else None,
                "from_team": _team_dict(from_team),
                "to_team": _team_dict(to_team),
                "trade_detail": tx_detail,
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
                "trade_detail": tx_detail,
            })

    # Also apply any supplemental_picks from TradeOverride / edited_trades not yet in traded_picks_log
    logged_tx_rounds = {(entry["espn_transaction_id"], int(entry["round"])) for entry in traded_picks_log}
    for e_tx_id, e_val in edited_trades.items():
        if e_tx_id in deleted_trade_ids or not isinstance(e_val, dict):
            continue
        for sp_pick in e_val.get("supplemental_picks") or []:
            p_year = int(sp_pick.get("season_year") or future_season_year)
            if p_year != future_season_year:
                continue
            r_num = int(sp_pick.get("round") or 1)
            if (e_tx_id, r_num) in logged_tx_rounds:
                continue
            to_espn = sp_pick.get("to_espn_team_id")
            from_espn = sp_pick.get("from_espn_team_id")
            orig_espn = sp_pick.get("original_espn_team_id") or from_espn
            to_team = espn_team_lookup.get(int(to_espn)) if to_espn is not None else None
            from_team = espn_team_lookup.get(int(from_espn)) if from_espn is not None else None
            if not to_team or not from_team:
                continue
            target_pick = pick_lookup_by_round_orig_espn.get((r_num, int(orig_espn))) if orig_espn else None
            if target_pick:
                target_pick["current_team"] = _team_dict(to_team)
                target_pick["is_traded"] = True
                w_val = e_val.get("week")
                tx_detail = trade_detail_map.get(str(e_tx_id))
                trade_info = {
                    "transaction_id": 0,
                    "espn_transaction_id": e_tx_id,
                    "week": w_val,
                    "executed_at": None,
                    "from_team": _team_dict(from_team),
                    "to_team": _team_dict(to_team),
                    "trade_detail": tx_detail,
                }
                target_pick["trade_details"] = trade_info
                target_pick["movement_history"].append(_team_dict(to_team))
                traded_picks_log.append({
                    "round": r_num,
                    "projected_overall_pick": target_pick["projected_overall_pick"],
                    "original_team": target_pick["original_team"],
                    "from_team": _team_dict(from_team),
                    "to_team": _team_dict(to_team),
                    "week": w_val,
                    "executed_at": None,
                    "espn_transaction_id": e_tx_id,
                    "trade_detail": tx_detail,
                })
                logged_tx_rounds.add((e_tx_id, r_num))

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

    # Populate active season roster with positional rank and tier for each franchise
    try:
        from backend.models.lineup import WeeklyLineup
        from backend.services.trades_service import (
            _dedupe_lineups_by_week,
            _has_played_week,
            compute_positional_ranks,
            compute_tier_ranks,
            get_tier_info,
        )

        season_lineups = (
            session.query(WeeklyLineup)
            .filter(WeeklyLineup.season_year == ref_season_year)
            .all()
        )
        if season_lineups:
            p_ids = {wl.player_id for wl in season_lineups}
            players_list = (
                session.query(Player).filter(Player.espn_player_id.in_(p_ids)).all()
                if p_ids
                else []
            )
            p_map = {p.espn_player_id: p for p in players_list}
            p_lineups: dict[tuple[int, int], list[WeeklyLineup]] = defaultdict(list)
            team_week_lineups: dict[int, dict[int, list[WeeklyLineup]]] = defaultdict(
                lambda: defaultdict(list)
            )
            scored_season_weeks: set[int] = set()
            max_season_wk = 0
            for wl in season_lineups:
                if wl.week >= 1:
                    p_lineups[(ref_season_year, wl.player_id)].append(wl)
                    if float(wl.actual_points or 0.0) > 0.0:
                        scored_season_weeks.add(wl.week)
                team_week_lineups[wl.team_id][wl.week].append(wl)
                if wl.week > max_season_wk:
                    max_season_wk = wl.week

            # Determine canonical owner in max_season_wk if a player was traded or dropped mid-week
            latest_owner_by_pid: dict[int, int | None] = {}
            for wl in sorted(season_lineups, key=lambda x: (x.week, x.id or 0)):
                latest_owner_by_pid[wl.player_id] = wl.team_id
            recent_tx_items = (
                session.query(TransactionItem, Transaction)
                .join(Transaction, TransactionItem.transaction_id == Transaction.id)
                .filter(
                    Transaction.season_year == ref_season_year,
                    Transaction.status == "EXECUTED",
                    Transaction.week >= max(1, max_season_wk - 1),
                )
                .order_by(Transaction.week.asc(), Transaction.executed_at.asc(), Transaction.id.asc())
                .all()
            )
            for item, tx in recent_tx_items:
                if tx.espn_transaction_id in deleted_trade_ids:
                    continue
                if item.item_type == "DROP":
                    if latest_owner_by_pid.get(item.player_id) == item.from_team_id:
                        latest_owner_by_pid[item.player_id] = None
                elif item.item_type in ("ADD", "TRADE") and item.to_team_id:
                    latest_owner_by_pid[item.player_id] = item.to_team_id

            pos_ranks = compute_positional_ranks(
                ref_season_year, max_season_wk + 1, p_lineups, p_map
            )
            tier_ranks = compute_tier_ranks(
                ref_season_year, max_season_wk + 1, p_lineups, p_map
            )

            pos_order = {"QB": 1, "RB": 2, "WR": 3, "TE": 4, "FLEX": 5, "D/ST": 6, "K": 7}

            for t_summary in ordered_teams_summary:
                tid = t_summary["team_id"]
                wk_map = team_week_lineups.get(tid, {})
                if not wk_map:
                    t_summary["roster_players"] = []
                    continue
                latest_wk = max(wk_map.keys())
                curr_wls = wk_map[latest_wk]

                roster_items: list[dict[str, Any]] = []
                seen_pids: set[int] = set()
                for wl in curr_wls:
                    if wl.player_id in seen_pids:
                        continue
                    # If player appears on multiple teams in latest_wk due to a mid-week trade,
                    # only show them on their latest owning team.
                    if latest_owner_by_pid.get(wl.player_id, tid) != tid:
                        continue
                    seen_pids.add(wl.player_id)
                    p = p_map.get(wl.player_id)
                    if not p:
                        continue
                    pos = p.default_position or "FLEX"
                    if pos == "PICK":
                        continue
                    rk = pos_ranks.get(wl.player_id)
                    t_rk = tier_ranks.get(wl.player_id)
                    _, tier_lbl = get_tier_info(t_rk)
                    if t_rk is not None and t_rk <= 3:
                        tier_num = 1
                    elif t_rk is not None and t_rk <= 8:
                        tier_num = 2
                    elif t_rk is not None and t_rk <= 16:
                        tier_num = 3
                    elif t_rk is not None and t_rk <= 24:
                        tier_num = 4
                    else:
                        tier_num = 5

                    dedup_wls = _dedupe_lineups_by_week(p_lineups[(ref_season_year, wl.player_id)])
                    played_wls = [
                        x
                        for x in dedup_wls
                        if _has_played_week(x, scored_season_weeks)
                    ]
                    tot_pts = sum(float(x.actual_points or 0.0) for x in played_wls)
                    ppg = (tot_pts / len(played_wls)) if played_wls else 0.0

                    inj_status = (
                        wl.weekly_stats.get("injury_status")
                        if isinstance(wl.weekly_stats, dict)
                        else None
                    )
                    if wl.slot_position == "IR" or inj_status == "INJURY_RESERVE":
                        display_slot = "IR"
                    elif inj_status in ("OUT", "DOUBTFUL", "SUSPENSION"):
                        display_slot = "OUT"
                    else:
                        display_slot = wl.slot_position

                    roster_items.append({
                        "player_id": p.espn_player_id,
                        "full_name": p.full_name,
                        "default_position": pos,
                        "pro_team": p.pro_team,
                        "headshot_url": p.headshot_url,
                        "slot_position": display_slot,
                        "is_starter": bool(wl.is_starter),
                        "ppg": round(ppg, 1),
                        "total_points": round(tot_pts, 1),
                        "positional_rank": rk,
                        "tier": tier_num,
                        "tier_label": tier_lbl,
                    })

                roster_items.sort(
                    key=lambda x: (
                        pos_order.get(x["default_position"], 99),
                        x["tier"],
                        x["positional_rank"] if x["positional_rank"] is not None else 999,
                        -x["ppg"],
                    )
                )
                t_summary["roster_players"] = roster_items
        else:
            for t_summary in ordered_teams_summary:
                t_summary["roster_players"] = []
    except Exception:
        for t_summary in ordered_teams_summary:
            t_summary.setdefault("roster_players", [])

    rounds_list = [
        {"round": r, "picks": board_picks_by_round[r]}
        for r in range(1, total_rounds + 1)
    ]

    # Collect distinct full TradeDetail records involved in future traded picks
    relevant_trades: list[dict[str, Any]] = []
    seen_tx: set[str] = set()
    for entry in traded_picks_log:
        tx_id = entry.get("espn_transaction_id")
        if tx_id and tx_id not in seen_tx:
            seen_tx.add(tx_id)
            if tx_id in trade_detail_map:
                relevant_trades.append(trade_detail_map[tx_id])

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
        "trades": relevant_trades,
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

    # Self-heal season-specific pro_team and any unresolved "Player <id>" entries on historical drafts
    season_pro_teams: dict[int, str] = {}
    draft_day_team_names: dict[int, str] = {}
    try:
        from backend.jobs.deep_parsers import normalize_pro_team, upsert_players_from_payload
        from backend.models.raw_snapshot import RawEspnSnapshot

        snaps = (
            session.query(RawEspnSnapshot)
            .filter_by(season_year=season_year)
            .order_by(RawEspnSnapshot.scoring_period.asc())
            .all()
        )
        for sn in snaps:
            if not isinstance(sn.payload, dict):
                continue
            if sn.view_name == "mBoxscore" and sn.scoring_period in (0, 1):
                for tm_raw in sn.payload.get("teams", []):
                    t_espn_id = tm_raw.get("id")
                    t_name = tm_raw.get("name") or (
                        f"{tm_raw.get('location', '')} {tm_raw.get('nickname', '')}".strip()
                    )
                    if t_espn_id and t_name and int(t_espn_id) not in draft_day_team_names:
                        draft_day_team_names[int(t_espn_id)] = t_name
            for p_raw in sn.payload.get("players", []):
                p_obj = p_raw.get("playerPoolEntry", {}).get("player") or p_raw.get("player") or p_raw
                if isinstance(p_obj, dict) and p_obj.get("id"):
                    pt = normalize_pro_team(p_obj.get("proTeamId") if p_obj.get("proTeamId") is not None else p_obj.get("proTeam"))
                    if pt and pt != "FA":
                        season_pro_teams[int(p_obj["id"])] = pt
            for tm_raw in sn.payload.get("teams", []):
                for entry in tm_raw.get("roster", {}).get("entries", []):
                    p_obj = entry.get("playerPoolEntry", {}).get("player") or entry.get("player") or {}
                    if isinstance(p_obj, dict) and p_obj.get("id"):
                        pt = normalize_pro_team(p_obj.get("proTeamId") if p_obj.get("proTeamId") is not None else p_obj.get("proTeam"))
                        if pt and pt != "FA" and int(p_obj["id"]) not in season_pro_teams:
                            season_pro_teams[int(p_obj["id"])] = pt

        pids_needing_fetch = [
            dp.player_id
            for dp in picks_raw
            if dp.player_id > 0
            and dp.player_id < 9000000
            and (
                not dp.player_pro_team
                or dp.player_id not in player_map
                or player_map[dp.player_id].full_name.startswith("Player ")
                or player_map[dp.player_id].default_position in ("UNKNOWN", "FLEX")
            )
            and (
                dp.player_id not in season_pro_teams
                or dp.player_id not in player_map
                or player_map[dp.player_id].full_name.startswith("Player ")
                or player_map[dp.player_id].default_position in ("UNKNOWN", "FLEX")
            )
        ]
        if pids_needing_fetch:
            from backend.jobs.espn_client import EspnClient

            fetched = EspnClient().fetch_player_info(
                season_year=season_year,
                player_ids=sorted(set(pids_needing_fetch)),
            )
            if fetched:
                for fp in fetched:
                    p_obj = fp.get("playerPoolEntry", {}).get("player") or fp.get("player") or fp
                    if isinstance(p_obj, dict) and p_obj.get("id"):
                        pt = normalize_pro_team(p_obj.get("proTeamId") if p_obj.get("proTeamId") is not None else p_obj.get("proTeam"))
                        if pt:
                            season_pro_teams[int(p_obj["id"])] = pt
                upsert_players_from_payload(session, {"players": fetched})
                for p in session.query(Player).filter(Player.espn_player_id.in_(pids_needing_fetch)).all():
                    player_map[p.espn_player_id] = p

        dirty = False
        for dp in picks_raw:
            resolved_pt = season_pro_teams.get(dp.player_id)
            if resolved_pt and dp.player_pro_team != resolved_pt:
                dp.player_pro_team = resolved_pt
                dirty = True
        if dirty or pids_needing_fetch:
            session.commit()
    except Exception:
        pass

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
                "team_name": draft_day_team_names.get(ot.espn_team_id, ot.team_name),
                "manager_id": ot.manager_id,
                "manager_name": mgr_map.get(ot.manager_id, ""),
                "logo_url": ot.logo_url,
            }

        resolved_pro_team = (
            dp.player_pro_team
            or season_pro_teams.get(dp.player_id)
            or (player.pro_team if player else "FA")
        )

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
                "team_name": (
                    draft_day_team_names.get(team.espn_team_id, team.team_name)
                    if team
                    else f"Team {dp.team_id}"
                ),
                "manager_id": team.manager_id if team else 0,
                "manager_name": mgr_map.get(team.manager_id, "") if team else "",
                "logo_url": team.logo_url if team else None,
            },
            "player": {
                "player_id": player.espn_player_id if player else dp.player_id,
                "full_name": player.full_name if player else f"Player {dp.player_id}",
                "default_position": player.default_position if player else "FLEX",
                "pro_team": resolved_pro_team,
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
            "team_name": draft_day_team_names.get(t.espn_team_id, t.team_name),
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
