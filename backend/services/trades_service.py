"""backend/services/trades_service.py - Bilateral Trades & Retrospective Scoring Engine.

Purpose:
    Analyzes bilateral trades, trade partner networks, and realized ROI
    using a multi-factor retrospective autopsy engine incorporating:
    - Positional scarcity multipliers
    - Starter vs total points weighting
    - Pre-trade form projections for early/recent trades
    - Draft pick valuation with exponential round decay
    - Future draft picks and commissioner overrides
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.models.draft import DraftPick
from backend.models.lineup import WeeklyLineup
from backend.models.manager import Manager
from backend.models.player import Player
from backend.models.season import Season
from backend.models.team import Team
from backend.models.trade import Trade
from backend.models.transaction import Transaction, TransactionItem

POS_MULTIPLIER: dict[str, float] = {
    "RB": 1.15,
    "WR": 1.00,
    "TE": 1.10,
    "QB": 0.85,
    "D/ST": 0.70,
    "K": 0.65,
    "FLEX": 1.00,
    "PICK": 1.00,
}

POSITION_BASELINES: dict[str, float] = {
    "RB": 10.0,
    "WR": 9.7,
    "TE": 9.8,
    "QB": 16.7,
    "FLEX": 9.8,
    "D/ST": 6.0,
    "K": 7.0,
}


def get_tier_info(rank: int | None) -> tuple[float, str | None]:
    """Return positional tier multiplier and descriptive tier label."""
    if rank is None or rank <= 0:
        return 1.00, None
    if rank <= 3:
        return 1.25, "Tier 1 - Elite Anchor"
    if rank <= 8:
        return 1.10, "Tier 2 - High-End Starter"
    if rank <= 16:
        return 1.00, "Tier 3 - Solid Starter"
    if rank <= 24:
        return 0.90, "Tier 4 - Flex / Low Starter"
    return 0.75, "Tier 5 - Replacement Level"


def compute_positional_ranks(
    season_year: int,
    effective_start_week: int,
    player_lineups: dict[tuple[int, int], list[WeeklyLineup]],
    player_map: dict[int, Player],
) -> dict[int, int]:
    """Calculate 1-based positional rank for all players in the season based on pre-trade PPG."""
    player_pre_metrics: dict[int, tuple[str, float, float, int]] = {}

    for (s_yr, p_id), lineups in player_lineups.items():
        if s_yr != season_year:
            continue
        pre_l = [wl for wl in lineups if wl.week < effective_start_week]
        if pre_l:
            pre_pts = sum(float(wl.actual_points or 0.0) for wl in pre_l)
            ppg = pre_pts / len(pre_l)
            tot_pts = pre_pts
        else:
            tot_pts = sum(float(wl.actual_points or 0.0) for wl in lineups)
            ppg = (tot_pts / len(lineups)) if lineups else 0.0

        p = player_map.get(p_id)
        pos = p.default_position if p and p.default_position else "FLEX"
        player_pre_metrics[p_id] = (pos, ppg, tot_pts, p_id)

    by_pos: dict[str, list[tuple[int, float, float, int]]] = defaultdict(list)
    for p_id, (pos, ppg, tot_pts, _) in player_pre_metrics.items():
        by_pos[pos].append((p_id, ppg, tot_pts, p_id))

    ranks: dict[int, int] = {}
    for _pos, p_list in by_pos.items():
        p_list.sort(key=lambda x: (-x[1], -x[2], x[3]))
        for r, (p_id, _, _, _) in enumerate(p_list, 1):
            ranks[p_id] = r

    return ranks

GRADE_POINTS: dict[str, float] = {
    "A+": 4.3,
    "A": 4.0,
    "B+": 3.3,
    "B": 3.0,
    "C+": 2.3,
    "C": 2.0,
    "C-": 1.7,
    "D": 1.0,
}


def compute_trade_grade(side_score: float, opp_score: float) -> str:
    """Calculate letter grade based on share of value and signed score differential."""
    total_score = side_score + opp_score
    signed_diff = side_score - opp_score
    share = (side_score / total_score) if total_score > 0 else 0.5

    if abs(signed_diff) < 2.0:
        return "B"
    if signed_diff >= 35.0 or share >= 0.72:
        return "A+"
    if signed_diff >= 20.0 or share >= 0.64:
        return "A"
    if signed_diff >= 10.0 or share >= 0.58:
        return "B+"
    if signed_diff >= 2.0 or share >= 0.52:
        return "B"
    if signed_diff <= -35.0 or share <= 0.28:
        return "D"
    if signed_diff <= -20.0 or share <= 0.36:
        return "C-"
    if signed_diff <= -10.0 or share <= 0.42:
        return "C"
    return "C+"


def average_letter_grade(grades: list[str]) -> str:
    """Calculate weighted GPA average and map back to standard letter grade."""
    if not grades:
        return "B"
    avg_pts = sum(GRADE_POINTS.get(g, 3.0) for g in grades) / len(grades)
    if avg_pts >= 4.15:
        return "A+"
    if avg_pts >= 3.65:
        return "A"
    if avg_pts >= 3.15:
        return "B+"
    if avg_pts >= 2.65:
        return "B"
    if avg_pts >= 2.15:
        return "C+"
    if avg_pts >= 1.85:
        return "C"
    if avg_pts >= 1.35:
        return "C-"
    return "D"


def _evaluate_trade(
    trade: Trade,
    team_map: dict[int, Team],
    mgr_map: dict[int, str],
    mgr_avatar_map: dict[int, str | None],
    items: list[TransactionItem],
    scored_weeks: set[tuple[int, int]],
    player_lineups: dict[tuple[int, int], list[WeeklyLineup]],
    player_week_lineup: dict[tuple[int, int, int], WeeklyLineup],
    player_map: dict[int, Player],
    draft_pick_map: dict[tuple[int, int], DraftPick],
    league_size: int,
    all_season_trades: list[tuple[Trade, list[TransactionItem]]] | None = None,
    ranks_cache: dict[tuple[int, int], dict[int, int]] | None = None,
    season_info: Season | None = None,
) -> dict[str, Any] | None:
    """Evaluate a single bilateral trade and produce canonical TradeDetail payload."""
    prop_team = team_map.get(trade.proposing_team_id)
    acc_team = team_map.get(trade.accepting_team_id)
    if not prop_team or not acc_team:
        return None

    prop_mgr_id = prop_team.manager_id
    acc_mgr_id = acc_team.manager_id

    # 4. Effective Post-Trade Window
    trade_week = trade.week or 0
    if trade_week <= 0:
        effective_start_week = 1
    else:
        appeared_in_trade_week = False
        if (trade.season_year, trade_week) in scored_weeks:
            for it in items:
                if it.to_team_id and it.player_id:
                    wl_cand = player_week_lineup.get((trade.season_year, it.player_id, trade_week))
                    if wl_cand and wl_cand.team_id == it.to_team_id:
                        appeared_in_trade_week = True
                        break
        if appeared_in_trade_week:
            effective_start_week = trade_week
        else:
            effective_start_week = trade_week + 1

    # Positional rankings for effective trade week
    if ranks_cache is None:
        ranks_cache = {}
    if (trade.season_year, effective_start_week) not in ranks_cache:
        ranks_cache[(trade.season_year, effective_start_week)] = compute_positional_ranks(
            trade.season_year, effective_start_week, player_lineups, player_map
        )
    season_ranks = ranks_cache[(trade.season_year, effective_start_week)]

    # Scored post-trade weeks count & season horizon
    season_weeks = sorted([w for (y, w) in scored_weeks if y == trade.season_year and w >= effective_start_week])
    n_post_weeks = len(season_weeks)
    effective_post_weeks = max(1, n_post_weeks)

    regular_weeks = season_info.regular_season_weeks if season_info else 14
    is_completed_season = season_info.is_completed if season_info else False
    expected_horizon = max(1, regular_weeks - effective_start_week + 1)
    season_horizon = max(n_post_weeks, expected_horizon)

    if is_completed_season:
        season_progress = 1.0
    elif n_post_weeks == 0:
        season_progress = 1.0
    else:
        season_progress = min(1.0, n_post_weeks / float(season_horizon))

    # Split transaction items by receiving team
    prop_assets_items = [i for i in items if i.to_team_id == prop_team.id]
    acc_assets_items = [i for i in items if i.to_team_id == acc_team.id]

    # Map of (player_id, receiving_team_id) -> (is_flipped, flip_week)
    flipped_map: dict[tuple[int, int], tuple[bool, int | None]] = {}

    def _evaluate_asset(item: TransactionItem, receiving_team: Team) -> dict[str, Any]:
        player = item.player or player_map.get(item.player_id)
        player_name = player.full_name if player else f"Player {item.player_id}"
        player_pos = player.default_position if player else "FLEX"
        player_pro_team = player.pro_team if player else "FA"
        player_headshot = player.headshot_url if player else None
        player_espn_id = player.espn_player_id if player else item.player_id

        # Check flipped equity for this asset
        is_flipped = False
        flip_week: int | None = None
        trade_wk = trade.week or 0
        if all_season_trades:
            for other_trade, other_items in all_season_trades:
                if other_trade.id == trade.id or other_trade.season_year != trade.season_year:
                    continue
                other_wk = other_trade.week or 0
                if other_wk > trade_wk:
                    for ot_item in other_items:
                        if ot_item.player_id == item.player_id:
                            is_outgoing = (
                                ot_item.from_team_id == receiving_team.id
                                or (
                                    receiving_team.id
                                    in (other_trade.proposing_team_id, other_trade.accepting_team_id)
                                    and ot_item.to_team_id != receiving_team.id
                                )
                            )
                            if is_outgoing:
                                is_flipped = True
                                flip_week = other_wk
                                break
                if is_flipped:
                    break

        flipped_map[(item.player_id, receiving_team.id)] = (is_flipped, flip_week)

        # Determine if this item is a Draft Pick
        is_pick = item.player_id < 0 or player_pos == "PICK"

        if is_pick:
            # Parse round number, pick number, and possible future season from name/id
            year_match = re.search(r"\b(20\d\d)\b", player_name)
            pick_season = int(year_match.group(1)) if year_match else trade.season_year
            is_future = pick_season > trade.season_year

            round_match = re.search(r"Round\s+(\d+)", player_name, re.IGNORECASE)
            pick_match = re.search(r"Pick\s+#?(\d+)", player_name, re.IGNORECASE)

            std_pick_num: int | None = None
            if -2000000 < item.player_id <= -100000:
                std_pick_num = abs(item.player_id) - 100000

            if pick_match:
                explicit_pick_num = int(pick_match.group(1))
            elif std_pick_num:
                explicit_pick_num = std_pick_num
            else:
                explicit_pick_num = None

            if round_match:
                round_num = int(round_match.group(1))
            elif explicit_pick_num:
                round_num = ((explicit_pick_num - 1) // league_size) + 1
            else:
                round_num = 1

            if explicit_pick_num is not None and explicit_pick_num > 0:
                pick_number = explicit_pick_num
                pick_round = ((pick_number - 1) // league_size) + 1
                pick_round_value = round(
                    max(5.0, 110.0 * math.exp(-0.025 * (pick_number - 1))), 2
                )
            else:
                pick_number = None
                pick_round = round_num
                effective_pick_num = (round_num - 1) * league_size + (league_size // 2)
                pick_round_value = round(
                    max(5.0, 110.0 * math.exp(-0.025 * (effective_pick_num - 1))), 2
                )

            # Check if this pick corresponds to an actual selection in DraftPick table
            can_resolve = (
                pick_number is not None
                and not is_future
                and (trade.season_year, pick_number) in draft_pick_map
            )

            if can_resolve:
                dp = draft_pick_map[(trade.season_year, pick_number)]  # type: ignore[index]
                drafted_player = player_map.get(dp.player_id) or dp.player
                drafted_player_id = dp.player_id
                drafted_player_name = (
                    drafted_player.full_name if drafted_player else f"Player {dp.player_id}"
                )
                drafted_player_pos = (
                    drafted_player.default_position if drafted_player else "FLEX"
                )
                drafted_player_headshot = (
                    drafted_player.headshot_url if drafted_player else None
                )

                all_dp_lineups = player_lineups.get((trade.season_year, dp.player_id), [])
                pre_dp_lineups = [wl for wl in all_dp_lineups if wl.week < effective_start_week]
                post_dp_lineups = [wl for wl in all_dp_lineups if wl.week >= effective_start_week]

                pre_trade_pts = round(sum(float(wl.actual_points) for wl in pre_dp_lineups), 2)
                pre_trade_ppg = (
                    round(pre_trade_pts / len(pre_dp_lineups), 2) if pre_dp_lineups else 0.0
                )
                season_total_pts = round(sum(float(wl.actual_points) for wl in all_dp_lineups), 2)
                season_ppg = (
                    round(season_total_pts / len(all_dp_lineups), 2) if all_dp_lineups else 0.0
                )

                post_trade_starter_pts = round(
                    sum(
                        float(wl.actual_points)
                        for wl in post_dp_lineups
                        if wl.team_id == receiving_team.id and wl.is_starter
                    ),
                    2,
                )
                post_trade_weeks_started = sum(
                    1
                    for wl in post_dp_lineups
                    if wl.team_id == receiving_team.id and wl.is_starter
                )
                post_trade_bench_pts = round(
                    sum(
                        float(wl.actual_points)
                        for wl in post_dp_lineups
                        if wl.team_id == receiving_team.id and not wl.is_starter
                    ),
                    2,
                )
                post_trade_total_pts = round(
                    sum(float(wl.actual_points) for wl in post_dp_lineups), 2
                )
                post_trade_weeks_played = len(post_dp_lineups)
                drafted_player_points = round(post_trade_total_pts, 2)

                weekly_breakdown = [
                    {
                        "week": wl.week,
                        "points": round(float(wl.actual_points), 2),
                        "is_starter": bool(wl.is_starter),
                        "slot_position": str(
                            wl.slot_position or ("BE" if not wl.is_starter else "FLEX")
                        ),
                        "on_acquiring_team": bool(wl.team_id == receiving_team.id),
                        "injury_status": (
                            wl.weekly_stats.get("injury_status")
                            if isinstance(wl.weekly_stats, dict) and wl.weekly_stats.get("injury_status")
                            else ("INJURY_RESERVE" if wl.slot_position == "IR" else None)
                        ),
                        "is_injured": bool(
                            (isinstance(wl.weekly_stats, dict) and wl.weekly_stats.get("injured"))
                            or wl.slot_position == "IR"
                            or (
                                isinstance(wl.weekly_stats, dict)
                                and wl.weekly_stats.get("injury_status") in ("INJURY_RESERVE", "OUT")
                            )
                        ),
                    }
                    for wl in sorted(post_dp_lineups, key=lambda x: x.week)
                ]

                dp_roster_depth = round(
                    (post_trade_bench_pts * 0.30) + (post_trade_weeks_played * 0.8), 2
                )
                pos_mult = POS_MULTIPLIER.get(drafted_player_pos, 1.0)
                dp_rank = season_ranks.get(dp.player_id)
                dp_tier_mult, dp_tier_label = get_tier_info(dp_rank)
                dp_effective_ppg = pre_trade_ppg if pre_dp_lineups else season_ppg
                dp_vorp_baseline = POSITION_BASELINES.get(drafted_player_pos, 9.8)
                dp_vorp_per_game = round(max(0.0, dp_effective_ppg - dp_vorp_baseline), 2)

                realized_player_score = (
                    (post_trade_starter_pts * pos_mult * dp_tier_mult) + dp_roster_depth
                )
                trade_score = round(
                    0.45 * (pick_round_value * season_progress) + 0.55 * realized_player_score, 2
                )
            else:
                drafted_player_id = None
                drafted_player_name = None
                drafted_player_pos = None
                drafted_player_headshot = None
                drafted_player_points = 0.0
                trade_score = round(pick_round_value * season_progress, 2)
                post_trade_starter_pts = 0.0
                post_trade_weeks_started = 0
                post_trade_bench_pts = 0.0
                post_trade_total_pts = 0.0
                post_trade_weeks_played = 0
                dp_roster_depth = 0.0
                pre_trade_pts = 0.0
                pre_trade_ppg = 0.0
                season_total_pts = 0.0
                season_ppg = 0.0
                weekly_breakdown = []
                dp_rank = None
                dp_tier_label = None
                dp_vorp_per_game = 0.0

            return {
                "player_id": player_espn_id,
                "full_name": player_name,
                "default_position": "PICK",
                "pro_team": "DRAFT",
                "headshot_url": player_headshot,
                "asset_type": "PICK",
                "post_trade_starter_points": post_trade_starter_pts,
                "post_trade_weeks_started": post_trade_weeks_started,
                "post_trade_total_points": post_trade_total_pts,
                "post_trade_bench_points": post_trade_bench_pts,
                "post_trade_weeks_played": post_trade_weeks_played,
                "roster_depth_points": dp_roster_depth,
                "pre_trade_points": pre_trade_pts,
                "pre_trade_ppg": pre_trade_ppg,
                "season_total_points": season_total_pts,
                "season_ppg": season_ppg,
                "positional_rank": dp_rank,
                "tier_label": dp_tier_label,
                "vorp_per_game": dp_vorp_per_game,
                "pick_round": pick_round,
                "pick_number": pick_number,
                "pick_round_value": pick_round_value,
                "drafted_player_id": drafted_player_id,
                "drafted_player_name": drafted_player_name,
                "drafted_player_position": drafted_player_pos,
                "drafted_player_headshot_url": drafted_player_headshot,
                "drafted_player_points": drafted_player_points,
                "trade_score": trade_score,
                "weekly_breakdown": weekly_breakdown,
            }

        # NFL Player asset
        pick_round = None
        pick_number = None
        pick_round_value = 0.0
        drafted_player_id = None
        drafted_player_name = None
        drafted_player_pos = None
        drafted_player_headshot = None
        drafted_player_points = 0.0

        all_p_lineups = player_lineups.get((trade.season_year, item.player_id), [])
        pre_p_lineups = [wl for wl in all_p_lineups if wl.week < effective_start_week]
        post_p_lineups = [wl for wl in all_p_lineups if wl.week >= effective_start_week]

        pre_trade_pts = round(sum(float(wl.actual_points) for wl in pre_p_lineups), 2)
        pre_trade_ppg = round(pre_trade_pts / len(pre_p_lineups), 2) if pre_p_lineups else 0.0
        season_total_pts = round(sum(float(wl.actual_points) for wl in all_p_lineups), 2)
        season_ppg = round(season_total_pts / len(all_p_lineups), 2) if all_p_lineups else 0.0

        post_trade_starter_pts = round(
            sum(
                float(wl.actual_points)
                for wl in post_p_lineups
                if wl.team_id == receiving_team.id and wl.is_starter
            ),
            2,
        )
        post_trade_weeks_started = sum(
            1 for wl in post_p_lineups if wl.team_id == receiving_team.id and wl.is_starter
        )
        post_trade_bench_pts = round(
            sum(
                float(wl.actual_points)
                for wl in post_p_lineups
                if wl.team_id == receiving_team.id and not wl.is_starter
            ),
            2,
        )
        post_trade_total_pts = round(sum(float(wl.actual_points) for wl in post_p_lineups), 2)
        post_trade_weeks_played = len(post_p_lineups)

        weekly_breakdown = [
            {
                "week": wl.week,
                "points": round(float(wl.actual_points), 2),
                "is_starter": bool(wl.is_starter),
                "slot_position": str(wl.slot_position or ("BE" if not wl.is_starter else "FLEX")),
                "on_acquiring_team": bool(wl.team_id == receiving_team.id),
                "injury_status": (
                    wl.weekly_stats.get("injury_status")
                    if isinstance(wl.weekly_stats, dict) and wl.weekly_stats.get("injury_status")
                    else ("INJURY_RESERVE" if wl.slot_position == "IR" else None)
                ),
                "is_injured": bool(
                    (isinstance(wl.weekly_stats, dict) and wl.weekly_stats.get("injured"))
                    or wl.slot_position == "IR"
                    or (
                        isinstance(wl.weekly_stats, dict)
                        and wl.weekly_stats.get("injury_status") in ("INJURY_RESERVE", "OUT")
                    )
                ),
            }
            for wl in sorted(post_p_lineups, key=lambda x: x.week)
        ]

        pos_rank = season_ranks.get(item.player_id) if item.player_id else None
        tier_mult, tier_label = get_tier_info(pos_rank)
        effective_ppg = pre_trade_ppg if pre_p_lineups else season_ppg
        vorp_baseline = POSITION_BASELINES.get(player_pos, 9.8)
        vorp_per_game = round(max(0.0, effective_ppg - vorp_baseline), 2)

        bench_points = post_trade_bench_pts
        weeks_held = post_trade_weeks_played

        ir_weeks = sum(
            1
            for wb in weekly_breakdown
            if wb.get("on_acquiring_team")
            and (wb.get("injury_status") == "INJURY_RESERVE" or wb.get("slot_position") == "IR")
        )
        out_weeks = sum(
            1
            for wb in weekly_breakdown
            if wb.get("on_acquiring_team")
            and wb.get("is_injured")
            and not (wb.get("injury_status") == "INJURY_RESERVE" or wb.get("slot_position") == "IR")
        )

        if ir_weeks > 0:
            ir_penalty = -20.0 - (max(0, ir_weeks - 4) * 5.0) - (out_weeks * 5.0)
        else:
            ir_penalty = -(out_weeks * 5.0)

        roster_depth_score = round(
            max(-50.0, (bench_points * 0.30) + (weeks_held * 0.8) + (10.0 if is_flipped else 0.0) + ir_penalty),
            2,
        )

        pos_mult = POS_MULTIPLIER.get(player_pos, 1.0)
        if post_trade_weeks_played > 0 and post_trade_total_pts > 0:
            trade_score = round(
                (post_trade_starter_pts * pos_mult * tier_mult) + roster_depth_score,
                2,
            )
        else:
            base_proj = round((effective_ppg * 4.0) * pos_mult * tier_mult, 2)
            trade_score = round(base_proj + roster_depth_score, 2) if ir_penalty < 0 else base_proj

        return {
            "player_id": player_espn_id,
            "full_name": player_name,
            "default_position": player_pos,
            "pro_team": player_pro_team,
            "headshot_url": player_headshot,
            "asset_type": "PLAYER",
            "post_trade_starter_points": post_trade_starter_pts,
            "post_trade_weeks_started": post_trade_weeks_started,
            "post_trade_total_points": post_trade_total_pts,
            "post_trade_bench_points": post_trade_bench_pts,
            "post_trade_weeks_played": post_trade_weeks_played,
            "roster_depth_points": roster_depth_score,
            "pre_trade_points": pre_trade_pts,
            "pre_trade_ppg": pre_trade_ppg,
            "season_total_points": season_total_pts,
            "season_ppg": season_ppg,
            "positional_rank": pos_rank,
            "tier_label": tier_label,
            "vorp_per_game": vorp_per_game,
            "pick_round": pick_round,
            "pick_number": pick_number,
            "pick_round_value": pick_round_value,
            "drafted_player_id": drafted_player_id,
            "drafted_player_name": drafted_player_name,
            "drafted_player_position": drafted_player_pos,
            "drafted_player_headshot_url": drafted_player_headshot,
            "drafted_player_points": drafted_player_points,
            "trade_score": trade_score,
            "weekly_breakdown": weekly_breakdown,
        }

    prop_assets = [_evaluate_asset(it, prop_team) for it in prop_assets_items]
    acc_assets = [_evaluate_asset(it, acc_team) for it in acc_assets_items]

    # Check for 2-for-1 or unbalanced package and Stud Consolidation Premium
    prop_players = [a for a in prop_assets if a["asset_type"] == "PLAYER"]
    acc_players = [a for a in acc_assets if a["asset_type"] == "PLAYER"]
    n_prop_p = len(prop_players)
    n_acc_p = len(acc_players)

    # Roster slot equalization points (+10.0 pts/week for freed starter slot on the team receiving fewer players)
    prop_slot_equalization = 0.0
    acc_slot_equalization = 0.0
    if n_prop_p < n_acc_p:
        delta_n = n_acc_p - n_prop_p
        prop_slot_equalization = round(delta_n * 10.0 * effective_post_weeks, 2)
    elif n_acc_p < n_prop_p:
        delta_n = n_prop_p - n_acc_p
        acc_slot_equalization = round(delta_n * 10.0 * effective_post_weeks, 2)

    # Stud Consolidation Premium:
    # If the trade is unbalanced (different number of players), the side receiving the superior elite anchor
    # (Tier 1/2 stud with rank <= 8 and better rank than any player on the other side) receives a +15% consolidation premium
    all_players = prop_players + acc_players
    if all_players and n_prop_p != n_acc_p:
        best_player = min(all_players, key=lambda a: a["positional_rank"] if a.get("positional_rank") is not None else 999)
        best_rank = best_player.get("positional_rank")
        if best_rank is not None and best_rank <= 8:
            if (n_prop_p < n_acc_p and best_player in prop_players) or (n_acc_p < n_prop_p and best_player in acc_players):
                best_player["trade_score"] = round(best_player["trade_score"] * 1.15, 2)
                best_player["is_stud"] = True

    # Side Totals
    faab_received_prop = int(trade.faab_from_accepter or 0)
    faab_value_prop = round((faab_received_prop * 0.60) * season_progress, 2)
    prop_starter_pts = round(sum(a["post_trade_starter_points"] for a in prop_assets), 2)
    prop_ros_pts = round(sum(a["post_trade_total_points"] for a in prop_assets), 2)
    prop_roster_depth_pts = round(sum(a["roster_depth_points"] for a in prop_assets), 2)
    prop_pick_val = round(sum(a["trade_score"] for a in prop_assets if a["asset_type"] == "PICK"), 2)
    prop_trade_score = round(sum(a["trade_score"] for a in prop_assets) + faab_value_prop + prop_slot_equalization, 2)

    faab_received_acc = int(trade.faab_from_proposer or 0)
    faab_value_acc = round((faab_received_acc * 0.60) * season_progress, 2)
    acc_starter_pts = round(sum(a["post_trade_starter_points"] for a in acc_assets), 2)
    acc_ros_pts = round(sum(a["post_trade_total_points"] for a in acc_assets), 2)
    acc_roster_depth_pts = round(sum(a["roster_depth_points"] for a in acc_assets), 2)
    acc_pick_val = round(sum(a["trade_score"] for a in acc_assets if a["asset_type"] == "PICK"), 2)
    acc_trade_score = round(sum(a["trade_score"] for a in acc_assets) + faab_value_acc + acc_slot_equalization, 2)

    # Grades
    prop_grade = compute_trade_grade(prop_trade_score, acc_trade_score)
    acc_grade = compute_trade_grade(acc_trade_score, prop_trade_score)

    # Projection Status
    all_assets = prop_assets + acc_assets
    player_assets = [a for a in all_assets if a["asset_type"] == "PLAYER"]
    is_projected = False
    if player_assets:
        if (
            all(a["post_trade_total_points"] == 0.0 for a in player_assets)
            and sum(a["pick_round_value"] for a in all_assets) == 0.0
        ):
            is_projected = True

    # Differential and Winner
    score_diff = round(abs(prop_trade_score - acc_trade_score), 2)
    starter_diff = round(abs(prop_starter_pts - acc_starter_pts), 2)
    point_diff = starter_diff if starter_diff > 0.0 else score_diff

    if score_diff < 1.0:
        winner_mgr_id: int | None = None
    elif prop_trade_score > acc_trade_score:
        winner_mgr_id = prop_mgr_id
    else:
        winner_mgr_id = acc_mgr_id

    # Verdict Label (Neutral & Informative)
    if is_projected:
        verdict_label = "Upcoming / In Progress"
    elif score_diff >= 35.0:
        verdict_label = "Major Value Margin"
    elif score_diff >= 18.0:
        verdict_label = "Significant Margin"
    elif score_diff >= 6.0:
        verdict_label = "Moderate Margin"
    elif score_diff >= 1.0:
        verdict_label = "Slight Margin"
    else:
        verdict_label = "Balanced Exchange"

    executed_at_str = (
        trade.executed_at.isoformat().replace("+00:00", "Z")
        if trade.executed_at
        else None
    )

    prop_logo = prop_team.logo_url or mgr_avatar_map.get(prop_mgr_id)
    acc_logo = acc_team.logo_url or mgr_avatar_map.get(acc_mgr_id)

    # Detect Timeline Events
    timeline_events: list[dict[str, Any]] = [
        {
            "week": trade.week or effective_start_week,
            "player_id": 0,
            "player_name": "",
            "team_id": prop_team.id,
            "team_name": prop_team.team_name,
            "event_type": "TRADE_EXECUTED",
            "severity": "info",
            "title": "Trade Executed",
            "description": f"Trade executed between {prop_team.team_name} and {acc_team.team_name}",
        }
    ]

    for side_assets, receiving_team in [(prop_assets, prop_team), (acc_assets, acc_team)]:
        for asset in side_assets:
            is_fl, fl_wk = flipped_map.get((asset["player_id"], receiving_team.id), (False, None))
            if is_fl and fl_wk is not None:
                timeline_events.append({
                    "week": fl_wk,
                    "player_id": asset["player_id"],
                    "player_name": asset["full_name"],
                    "team_id": receiving_team.id,
                    "team_name": receiving_team.team_name,
                    "event_type": "FLIPPED",
                    "severity": "info",
                    "title": f"Flipped: {asset['full_name']}",
                    "description": f"{asset['full_name']} was traded away to another team in Week {fl_wk}",
                })

            for wb in asset.get("weekly_breakdown", []):
                if not wb.get("on_acquiring_team"):
                    continue
                w_pts = wb["points"]
                w_num = wb["week"]
                if wb.get("slot_position") == "IR" or wb.get("injury_status") == "INJURY_RESERVE":
                    timeline_events.append({
                        "week": w_num,
                        "player_id": asset["player_id"],
                        "player_name": asset["full_name"],
                        "team_id": receiving_team.id,
                        "team_name": receiving_team.team_name,
                        "event_type": "INJURY_IR",
                        "severity": "danger",
                        "title": f"{asset['full_name']} Placed on IR",
                        "description": f"{asset['full_name']} placed on IR ({w_pts:.1f} pts)",
                    })
                elif wb.get("injury_status") == "OUT":
                    timeline_events.append({
                        "week": w_num,
                        "player_id": asset["player_id"],
                        "player_name": asset["full_name"],
                        "team_id": receiving_team.id,
                        "team_name": receiving_team.team_name,
                        "event_type": "INJURY_OUT",
                        "severity": "warning",
                        "title": f"{asset['full_name']} Ruled OUT",
                        "description": f"{asset['full_name']} ruled OUT ({w_pts:.1f} pts)",
                    })

                if wb.get("is_starter") and w_pts >= 20.0:
                    timeline_events.append({
                        "week": w_num,
                        "player_id": asset["player_id"],
                        "player_name": asset["full_name"],
                        "team_id": receiving_team.id,
                        "team_name": receiving_team.team_name,
                        "event_type": "BIG_GAME",
                        "severity": "success",
                        "title": f"Big Game: {asset['full_name']}",
                        "description": f"{asset['full_name']} scored {w_pts:.1f} pts in Week {w_num}",
                    })
                elif not wb.get("is_starter") and w_pts >= 15.0:
                    timeline_events.append({
                        "week": w_num,
                        "player_id": asset["player_id"],
                        "player_name": asset["full_name"],
                        "team_id": receiving_team.id,
                        "team_name": receiving_team.team_name,
                        "event_type": "BENCH_BOOM",
                        "severity": "warning",
                        "title": f"Bench Boom: {asset['full_name']}",
                        "description": f"{asset['full_name']} scored {w_pts:.1f} pts on the bench in Week {w_num}",
                    })

    timeline_events.sort(key=lambda e: (e["week"], e["player_id"]))

    # Construct weekly trajectory
    fixed_cap_a = round(faab_received_prop * 0.60, 2) + sum(
        a["pick_round_value"]
        for a in prop_assets
        if a["asset_type"] == "PICK" and a["drafted_player_id"] is None
    ) + sum(
        round(0.45 * a["pick_round_value"], 2)
        for a in prop_assets
        if a["asset_type"] == "PICK" and a["drafted_player_id"] is not None
    )

    fixed_cap_b = round(faab_received_acc * 0.60, 2) + sum(
        a["pick_round_value"]
        for a in acc_assets
        if a["asset_type"] == "PICK" and a["drafted_player_id"] is None
    ) + sum(
        round(0.45 * a["pick_round_value"], 2)
        for a in acc_assets
        if a["asset_type"] == "PICK" and a["drafted_player_id"] is not None
    )

    trajectory: list[dict[str, Any]] = []
    cum_starter_a = 0.0
    cum_bench_a = 0.0
    cum_depth_a = 0.0
    cum_score_a = 0.0

    cum_starter_b = 0.0
    cum_bench_b = 0.0
    cum_depth_b = 0.0
    cum_score_b = 0.0

    for i, w in enumerate(season_weeks, 1):
        # Side A weekly metrics
        w_starter_a = 0.0
        w_bench_a = 0.0
        w_depth_a = 0.0
        w_score_a = 0.0
        for a in prop_assets:
            for wb in a.get("weekly_breakdown", []):
                if wb["week"] == w and wb.get("on_acquiring_team"):
                    pts = wb["points"]
                    is_st = wb["is_starter"]
                    if is_st:
                        w_starter_a += pts
                    else:
                        w_bench_a += pts
                    b_pts = pts if not is_st else 0.0
                    held_pts = 0.8
                    is_fl, fl_wk = flipped_map.get((a["player_id"], prop_team.id), (False, None))
                    flip_pts = 10.0 if (is_fl and fl_wk == w) else 0.0

                    ir_weeks_on_team = [
                        wb_item["week"] for wb_item in a.get("weekly_breakdown", [])
                        if wb_item.get("on_acquiring_team")
                        and (wb_item.get("injury_status") == "INJURY_RESERVE" or wb_item.get("slot_position") == "IR")
                    ]
                    first_ir_week = min(ir_weeks_on_team) if ir_weeks_on_team else None
                    if wb.get("injury_status") == "INJURY_RESERVE" or wb.get("slot_position") == "IR":
                        if w == first_ir_week:
                            ir_penalty = -20.0
                        elif first_ir_week is not None and w > first_ir_week + 3:
                            ir_penalty = -5.0
                        else:
                            ir_penalty = 0.0
                    elif wb.get("is_injured"):
                        ir_penalty = -5.0
                    else:
                        ir_penalty = 0.0

                    d_pts = (b_pts * 0.30) + held_pts + flip_pts + ir_penalty
                    w_depth_a += d_pts
                    pos_mult = POS_MULTIPLIER.get(a["default_position"], 1.0)
                    tier_mult, _ = get_tier_info(a.get("positional_rank"))
                    stud_factor = 1.15 if a.get("is_stud") else 1.0
                    if a["asset_type"] == "PLAYER":
                        w_score_a += ((pts if is_st else 0.0) * pos_mult * tier_mult * stud_factor) + d_pts
                    elif a["asset_type"] == "PICK" and a["drafted_player_id"] is not None:
                        w_score_a += 0.55 * (((pts if is_st else 0.0) + d_pts) * pos_mult)
                    break

        # Slot equalization for Side A
        if n_prop_p < n_acc_p:
            w_slot_a = (n_acc_p - n_prop_p) * 10.0
            w_starter_a += w_slot_a
            w_score_a += w_slot_a

        cum_starter_a += w_starter_a
        cum_bench_a += w_bench_a
        cum_depth_a += w_depth_a
        cum_score_a += w_score_a
        prorated_fixed_a = (fixed_cap_a * (i / season_horizon)) if season_horizon > 0 else 0.0
        side_a_cum_score = round(cum_score_a + prorated_fixed_a, 2)

        # Side B weekly metrics
        w_starter_b = 0.0
        w_bench_b = 0.0
        w_depth_b = 0.0
        w_score_b = 0.0
        for a in acc_assets:
            for wb in a.get("weekly_breakdown", []):
                if wb["week"] == w and wb.get("on_acquiring_team"):
                    pts = wb["points"]
                    is_st = wb["is_starter"]
                    if is_st:
                        w_starter_b += pts
                    else:
                        w_bench_b += pts
                    b_pts = pts if not is_st else 0.0
                    held_pts = 0.8
                    is_fl, fl_wk = flipped_map.get((a["player_id"], acc_team.id), (False, None))
                    flip_pts = 10.0 if (is_fl and fl_wk == w) else 0.0

                    ir_weeks_on_team = [
                        wb_item["week"] for wb_item in a.get("weekly_breakdown", [])
                        if wb_item.get("on_acquiring_team")
                        and (wb_item.get("injury_status") == "INJURY_RESERVE" or wb_item.get("slot_position") == "IR")
                    ]
                    first_ir_week = min(ir_weeks_on_team) if ir_weeks_on_team else None
                    if wb.get("injury_status") == "INJURY_RESERVE" or wb.get("slot_position") == "IR":
                        if w == first_ir_week:
                            ir_penalty = -20.0
                        elif first_ir_week is not None and w > first_ir_week + 3:
                            ir_penalty = -5.0
                        else:
                            ir_penalty = 0.0
                    elif wb.get("is_injured"):
                        ir_penalty = -5.0
                    else:
                        ir_penalty = 0.0

                    d_pts = (b_pts * 0.30) + held_pts + flip_pts + ir_penalty
                    w_depth_b += d_pts
                    pos_mult = POS_MULTIPLIER.get(a["default_position"], 1.0)
                    tier_mult, _ = get_tier_info(a.get("positional_rank"))
                    stud_factor = 1.15 if a.get("is_stud") else 1.0
                    if a["asset_type"] == "PLAYER":
                        w_score_b += ((pts if is_st else 0.0) * pos_mult * tier_mult * stud_factor) + d_pts
                    elif a["asset_type"] == "PICK" and a["drafted_player_id"] is not None:
                        w_score_b += 0.55 * (((pts if is_st else 0.0) + d_pts) * pos_mult)
                    break

        # Slot equalization for Side B
        if n_acc_p < n_prop_p:
            w_slot_b = (n_prop_p - n_acc_p) * 10.0
            w_starter_b += w_slot_b
            w_score_b += w_slot_b

        cum_starter_b += w_starter_b
        cum_bench_b += w_bench_b
        cum_depth_b += w_depth_b
        cum_score_b += w_score_b
        prorated_fixed_b = (fixed_cap_b * (i / season_horizon)) if season_horizon > 0 else 0.0
        side_b_cum_score = round(cum_score_b + prorated_fixed_b, 2)

        diff = round(abs(side_a_cum_score - side_b_cum_score), 2)
        leading_team_id: int | None = None
        if diff >= 1.0:
            leading_team_id = prop_team.id if side_a_cum_score > side_b_cum_score else acc_team.id

        w_events = [e for e in timeline_events if e["week"] == w or (i == 1 and e["week"] < w)]

        trajectory.append({
            "week": w,
            "side_a_starter_points": round(w_starter_a, 2),
            "side_a_bench_points": round(w_bench_a, 2),
            "side_a_depth_points": round(w_depth_a, 2),
            "side_a_cumulative_starter_points": round(cum_starter_a, 2),
            "side_a_cumulative_total_points": round(cum_starter_a + cum_bench_a, 2),
            "side_a_cumulative_score": side_a_cum_score,
            "side_b_starter_points": round(w_starter_b, 2),
            "side_b_bench_points": round(w_bench_b, 2),
            "side_b_depth_points": round(w_depth_b, 2),
            "side_b_cumulative_starter_points": round(cum_starter_b, 2),
            "side_b_cumulative_total_points": round(cum_starter_b + cum_bench_b, 2),
            "side_b_cumulative_score": side_b_cum_score,
            "cumulative_score_differential": diff,
            "leading_team_id": leading_team_id,
            "events": w_events,
        })

    return {
        "trade_id": trade.id,
        "season_year": trade.season_year,
        "week": trade.week,
        "executed_at": executed_at_str,
        "espn_transaction_id": trade.espn_transaction_id,
        "sides": [
            {
                "team_id": prop_team.id,
                "team_name": prop_team.team_name,
                "logo_url": prop_logo,
                "manager_id": prop_mgr_id,
                "manager_name": mgr_map.get(prop_mgr_id, ""),
                "assets_received": prop_assets,
                "faab_received": faab_received_prop,
                "faab_value": faab_value_prop,
                "total_starter_points_gained": prop_starter_pts,
                "total_ros_points_gained": prop_ros_pts,
                "total_roster_depth_points_gained": prop_roster_depth_pts,
                "slot_equalization_points": prop_slot_equalization,
                "total_pick_value_gained": prop_pick_val,
                "total_trade_score": prop_trade_score,
                "grade": prop_grade,
            },
            {
                "team_id": acc_team.id,
                "team_name": acc_team.team_name,
                "logo_url": acc_logo,
                "manager_id": acc_mgr_id,
                "manager_name": mgr_map.get(acc_mgr_id, ""),
                "assets_received": acc_assets,
                "faab_received": faab_received_acc,
                "faab_value": faab_value_acc,
                "total_starter_points_gained": acc_starter_pts,
                "total_ros_points_gained": acc_ros_pts,
                "total_roster_depth_points_gained": acc_roster_depth_pts,
                "slot_equalization_points": acc_slot_equalization,
                "total_pick_value_gained": acc_pick_val,
                "total_trade_score": acc_trade_score,
                "grade": acc_grade,
            },
        ],
        "winner_manager_id": winner_mgr_id,
        "point_differential": point_diff,
        "score_differential": score_diff,
        "verdict_label": verdict_label,
        "is_projected": is_projected,
        "weekly_trajectory": trajectory,
        "timeline_events": timeline_events,
    }


def get_trades_trends(
    session: Session, season_filter: int | None = None
) -> dict[str, Any]:
    """Calculate trade volumes, partner networks, and retrospective autopsy scores."""
    seasons = session.query(Season).all()
    season_map = {s.season_year: s for s in seasons}
    has_transaction_data = True
    if season_filter is not None:
        season = season_map.get(season_filter)
        if season is not None:
            has_transaction_data = season.has_transaction_data
    else:
        has_transaction_data = any(s.has_transaction_data for s in seasons) if seasons else True

    # Pre-fetch master teams & managers
    teams = session.query(Team).order_by(Team.season_year.desc(), Team.id.desc()).all()
    team_map = {t.id: t for t in teams}
    teams_by_year: dict[int, list[Team]] = defaultdict(list)
    for t in teams:
        teams_by_year[t.season_year].append(t)

    def _get_league_size(year: int) -> int:
        return len(teams_by_year.get(year, [])) or 12

    latest_team_by_mgr: dict[int, Team] = {}
    for t in teams:
        if t.manager_id not in latest_team_by_mgr:
            latest_team_by_mgr[t.manager_id] = t

    active_season = next((s for s in seasons if s.is_active), None)
    active_mgr_ids: set[int] = set()
    if active_season:
        active_mgr_ids = {
            t.manager_id for t in teams_by_year.get(active_season.season_year, []) if t.manager_id
        } | {
            t.co_manager_id for t in teams_by_year.get(active_season.season_year, []) if t.co_manager_id
        }

    managers = session.query(Manager).all()
    mgr_map = {m.id: m.display_name for m in managers}
    mgr_avatar_map = {m.id: m.avatar_url for m in managers}
    mgr_active_map = {
        m.id: bool(m.is_active and (not active_season or m.id in active_mgr_ids))
        for m in managers
    }

    def _mgr_team_name(mid: int) -> str:
        if mid in latest_team_by_mgr:
            return latest_team_by_mgr[mid].team_name
        return mgr_map.get(mid, "")

    def _mgr_avatar(mid: int) -> str | None:
        if mid in latest_team_by_mgr and latest_team_by_mgr[mid].logo_url:
            return latest_team_by_mgr[mid].logo_url
        return mgr_avatar_map.get(mid)

    # 1. Query completed trades
    trades_query = session.query(Trade).filter(Trade.status == "EXECUTED")
    if season_filter is not None:
        trades_query = trades_query.filter(Trade.season_year == season_filter)
    trades_raw = trades_query.order_by(Trade.executed_at.desc(), Trade.id.desc()).all()

    # Pre-fetch trade transactions (Step 1 fix: check both espn_tx_id and related)
    trade_tx_ids = [t.espn_transaction_id for t in trades_raw]
    transactions = (
        session.query(Transaction)
        .filter(
            or_(
                Transaction.espn_transaction_id.in_(trade_tx_ids),
                Transaction.related_espn_transaction_id.in_(trade_tx_ids),
            )
        )
        .all()
    )
    tx_by_espn_id = {tx.espn_transaction_id: tx for tx in transactions}
    for tx in transactions:
        if tx.related_espn_transaction_id and tx.related_espn_transaction_id not in tx_by_espn_id:
            tx_by_espn_id[tx.related_espn_transaction_id] = tx

    # Pre-fetch executed waivers and free agent adds per team/manager
    tx_waiver_query = (
        session.query(Transaction.team_id, Transaction.transaction_type, func.count(Transaction.id))
        .filter(
            Transaction.status == "EXECUTED",
            Transaction.transaction_type.in_(["WAIVER", "FREE_AGENT"]),
        )
    )
    if season_filter is not None:
        tx_waiver_query = tx_waiver_query.filter(Transaction.season_year == season_filter)
    waiver_counts_by_team = tx_waiver_query.group_by(Transaction.team_id, Transaction.transaction_type).all()

    mgr_waivers: dict[int, int] = defaultdict(int)
    mgr_fa_adds: dict[int, int] = defaultdict(int)
    for tid, txtype, cnt in waiver_counts_by_team:
        if tid is not None and tid in team_map:
            mid = team_map[tid].manager_id
            if txtype == "WAIVER":
                mgr_waivers[mid] += cnt
            elif txtype == "FREE_AGENT":
                mgr_fa_adds[mid] += cnt

    # Pre-fetch trade items
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

    # Pre-fetch draft picks
    draft_picks_query = session.query(DraftPick)
    if season_filter is not None:
        draft_picks_query = draft_picks_query.filter(DraftPick.season_year == season_filter)
    draft_picks = draft_picks_query.all()
    draft_pick_map: dict[tuple[int, int], DraftPick] = {
        (dp.season_year, dp.overall_pick): dp for dp in draft_picks
    }

    # Pre-fetch players
    players_all = session.query(Player).all()
    player_map = {p.espn_player_id: p for p in players_all}

    # Pre-fetch all weekly lineups (starters and bench)
    lineup_query = session.query(WeeklyLineup)
    if season_filter is not None:
        lineup_query = lineup_query.filter(WeeklyLineup.season_year == season_filter)
    all_lineups = lineup_query.all()

    # 2. Completed/Scored Weeks Detection
    week_points_sum: dict[tuple[int, int], float] = defaultdict(float)
    max_week_by_season: dict[int, int] = {}
    for wl in all_lineups:
        week_points_sum[(wl.season_year, wl.week)] += float(wl.actual_points or 0.0)
        max_week_by_season[wl.season_year] = max(max_week_by_season.get(wl.season_year, 0), wl.week)

    # Scored weeks have points > 0, plus the latest in-progress/active week with rostered lineups
    scored_weeks = {k for k, total_pts in week_points_sum.items() if total_pts > 0.0}
    for y, max_w in max_week_by_season.items():
        if (y, max_w) in week_points_sum:
            scored_weeks.add((y, max_w))

    player_lineups: dict[tuple[int, int], list[WeeklyLineup]] = defaultdict(list)
    player_week_lineup: dict[tuple[int, int, int], WeeklyLineup] = {}
    for wl in all_lineups:
        if (wl.season_year, wl.week) in scored_weeks:
            player_lineups[(wl.season_year, wl.player_id)].append(wl)
            player_week_lineup[(wl.season_year, wl.player_id, wl.week)] = wl

    # Deduplicate trades (prioritize trades with associated items)
    trades_sorted = sorted(
        trades_raw,
        key=lambda t: (
            len(items_by_tx_id.get(tx_by_espn_id.get(t.espn_transaction_id).id, []))
            if tx_by_espn_id.get(t.espn_transaction_id)
            else 0
        ),
        reverse=True,
    )
    seen_trade_pairs: set[tuple[int, int, frozenset[int]]] = set()
    trades: list[Trade] = []
    for t in trades_sorted:
        t_pair = (t.season_year, t.week or 0, frozenset([t.proposing_team_id, t.accepting_team_id]))
        if t_pair in seen_trade_pairs:
            continue
        seen_trade_pairs.add(t_pair)
        trades.append(t)
    trades.sort(key=lambda t: (t.executed_at or datetime.min, t.id), reverse=True)

    # Accumulators for Top Partners and Active Traders
    partner_stats: dict[tuple[int, int], dict[str, Any]] = defaultdict(
        lambda: {
            "trade_count": 0,
            "total_assets_exchanged": 0,
            "total_trade_score_volume": 0.0,
            "net_score_mgr_a": 0.0,  # mgr_a score - mgr_b score
        }
    )

    trader_stats: dict[int, dict[str, Any]] = defaultdict(
        lambda: {
            "total_trades": 0,
            "trades_won": 0,
            "trades_lost": 0,
            "trades_tied": 0,
            "players_acquired": 0,
            "players_traded_away": 0,
            "picks_acquired": 0,
            "picks_traded_away": 0,
            "faab_net": 0,
            "net_starter_points_gained": 0.0,
            "net_ros_points_gained": 0.0,
            "net_roster_depth_points_gained": 0.0,
            "net_trade_score_gained": 0.0,
            "grades": [],
        }
    )

    all_season_trades: list[tuple[Trade, list[TransactionItem]]] = []
    for tr in trades_raw:
        tr_tx = tx_by_espn_id.get(tr.espn_transaction_id)
        tr_items = items_by_tx_id.get(tr_tx.id, []) if tr_tx else []
        if not tr_items and tr_tx:
            for cand_tx in transactions:
                if cand_tx.related_espn_transaction_id == tr.espn_transaction_id:
                    cand_items = items_by_tx_id.get(cand_tx.id, [])
                    if cand_items:
                        tr_items = cand_items
                        break
        all_season_trades.append((tr, tr_items))

    trade_details: list[dict[str, Any]] = []

    for trade in trades:
        tx = tx_by_espn_id.get(trade.espn_transaction_id)
        items = items_by_tx_id.get(tx.id, []) if tx else []
        if not items:
            for cand_tx in transactions:
                if cand_tx.related_espn_transaction_id == trade.espn_transaction_id:
                    cand_items = items_by_tx_id.get(cand_tx.id, [])
                    if cand_items:
                        items = cand_items
                        break

        detail = _evaluate_trade(
            trade=trade,
            team_map=team_map,
            mgr_map=mgr_map,
            mgr_avatar_map=mgr_avatar_map,
            items=items,
            scored_weeks=scored_weeks,
            player_lineups=player_lineups,
            player_week_lineup=player_week_lineup,
            player_map=player_map,
            draft_pick_map=draft_pick_map,
            league_size=_get_league_size(trade.season_year),
            all_season_trades=all_season_trades,
            season_info=season_map.get(trade.season_year),
        )
        if not detail:
            continue

        trade_details.append(detail)

        # Update partner stats
        prop_side = detail["sides"][0]
        acc_side = detail["sides"][1]
        prop_mgr = prop_side["manager_id"]
        acc_mgr = acc_side["manager_id"]
        mgr_a = min(prop_mgr, acc_mgr)
        mgr_b = max(prop_mgr, acc_mgr)
        pair_key = (mgr_a, mgr_b)

        p_stat = partner_stats[pair_key]
        p_stat["trade_count"] += 1
        p_stat["total_assets_exchanged"] += len(prop_side["assets_received"]) + len(
            acc_side["assets_received"]
        )
        p_stat["total_trade_score_volume"] += (
            prop_side["total_trade_score"] + acc_side["total_trade_score"]
        )

        score_a = prop_side["total_trade_score"] if prop_mgr == mgr_a else acc_side["total_trade_score"]
        score_b = acc_side["total_trade_score"] if prop_mgr == mgr_a else prop_side["total_trade_score"]
        p_stat["net_score_mgr_a"] += score_a - score_b

        # Update active trader stats for proposing manager
        winner_id = detail["winner_manager_id"]
        t_prop = trader_stats[prop_mgr]
        t_prop["total_trades"] += 1
        if winner_id == prop_mgr:
            t_prop["trades_won"] += 1
        elif winner_id == acc_mgr:
            t_prop["trades_lost"] += 1
        else:
            t_prop["trades_tied"] += 1

        t_prop["players_acquired"] += sum(
            1 for a in prop_side["assets_received"] if a["asset_type"] == "PLAYER"
        )
        t_prop["players_traded_away"] += sum(
            1 for a in acc_side["assets_received"] if a["asset_type"] == "PLAYER"
        )
        t_prop["picks_acquired"] += sum(
            1 for a in prop_side["assets_received"] if a["asset_type"] == "PICK"
        )
        t_prop["picks_traded_away"] += sum(
            1 for a in acc_side["assets_received"] if a["asset_type"] == "PICK"
        )
        t_prop["faab_net"] += prop_side["faab_received"] - acc_side["faab_received"]
        t_prop["net_starter_points_gained"] += (
            prop_side["total_starter_points_gained"] - acc_side["total_starter_points_gained"]
        )
        t_prop["net_ros_points_gained"] += (
            prop_side["total_ros_points_gained"] - acc_side["total_ros_points_gained"]
        )
        t_prop["net_roster_depth_points_gained"] += (
            prop_side["total_roster_depth_points_gained"] - acc_side["total_roster_depth_points_gained"]
        )
        t_prop["net_trade_score_gained"] += (
            prop_side["total_trade_score"] - acc_side["total_trade_score"]
        )
        t_prop["grades"].append(prop_side["grade"])

        # Update active trader stats for accepting manager
        t_acc = trader_stats[acc_mgr]
        t_acc["total_trades"] += 1
        if winner_id == acc_mgr:
            t_acc["trades_won"] += 1
        elif winner_id == prop_mgr:
            t_acc["trades_lost"] += 1
        else:
            t_acc["trades_tied"] += 1

        t_acc["players_acquired"] += sum(
            1 for a in acc_side["assets_received"] if a["asset_type"] == "PLAYER"
        )
        t_acc["players_traded_away"] += sum(
            1 for a in prop_side["assets_received"] if a["asset_type"] == "PLAYER"
        )
        t_acc["picks_acquired"] += sum(
            1 for a in acc_side["assets_received"] if a["asset_type"] == "PICK"
        )
        t_acc["picks_traded_away"] += sum(
            1 for a in prop_side["assets_received"] if a["asset_type"] == "PICK"
        )
        t_acc["faab_net"] += acc_side["faab_received"] - prop_side["faab_received"]
        t_acc["net_starter_points_gained"] += (
            acc_side["total_starter_points_gained"] - prop_side["total_starter_points_gained"]
        )
        t_acc["net_ros_points_gained"] += (
            acc_side["total_ros_points_gained"] - prop_side["total_ros_points_gained"]
        )
        t_acc["net_roster_depth_points_gained"] += (
            acc_side["total_roster_depth_points_gained"] - prop_side["total_roster_depth_points_gained"]
        )
        t_acc["net_trade_score_gained"] += (
            acc_side["total_trade_score"] - prop_side["total_trade_score"]
        )
        t_acc["grades"].append(acc_side["grade"])

    # Build TopTradePartner list
    top_partners: list[dict[str, Any]] = []
    for (mgr_a, mgr_b), p_stat in sorted(
        partner_stats.items(), key=lambda x: -x[1]["trade_count"]
    ):
        net_score = p_stat["net_score_mgr_a"]
        if abs(net_score) < 1.0:
            net_winner: int | None = None
            net_diff = 0.0
        elif net_score > 0:
            net_winner = mgr_a
            net_diff = round(net_score, 2)
        else:
            net_winner = mgr_b
            net_diff = round(abs(net_score), 2)

        top_partners.append(
            {
                "manager_a_id": mgr_a,
                "manager_a_name": mgr_map.get(mgr_a, ""),
                "manager_a_team_name": _mgr_team_name(mgr_a),
                "manager_a_avatar_url": _mgr_avatar(mgr_a),
                "manager_b_id": mgr_b,
                "manager_b_name": mgr_map.get(mgr_b, ""),
                "manager_b_team_name": _mgr_team_name(mgr_b),
                "manager_b_avatar_url": _mgr_avatar(mgr_b),
                "trade_count": p_stat["trade_count"],
                "total_assets_exchanged": p_stat["total_assets_exchanged"],
                "total_trade_score_volume": round(p_stat["total_trade_score_volume"], 2),
                "net_winner_manager_id": net_winner,
                "net_score_differential": net_diff,
            }
        )

    # Build ActiveTrader list
    active_traders: list[dict[str, Any]] = []
    for mid, t_data in sorted(
        trader_stats.items(),
        key=lambda x: (-x[1]["total_trades"], -x[1]["net_trade_score_gained"]),
    ):
        tot_trades = t_data["total_trades"]
        win_rate = round(t_data["trades_won"] / tot_trades, 3) if tot_trades > 0 else 0.0
        active_traders.append(
            {
                "manager_id": mid,
                "display_name": mgr_map.get(mid, ""),
                "team_name": _mgr_team_name(mid),
                "avatar_url": _mgr_avatar(mid),
                "is_active": mgr_active_map.get(mid, True),
                "total_trades": tot_trades,
                "trades_won": t_data["trades_won"],
                "trades_lost": t_data["trades_lost"],
                "trades_tied": t_data["trades_tied"],
                "win_rate": win_rate,
                "players_acquired": t_data["players_acquired"],
                "players_traded_away": t_data["players_traded_away"],
                "picks_acquired": t_data["picks_acquired"],
                "picks_traded_away": t_data["picks_traded_away"],
                "faab_net": t_data["faab_net"],
                "net_starter_points_gained": round(t_data["net_starter_points_gained"], 2),
                "net_ros_points_gained": round(t_data["net_ros_points_gained"], 2),
                "net_roster_depth_points_gained": round(t_data["net_roster_depth_points_gained"], 2),
                "net_trade_score_gained": round(t_data["net_trade_score_gained"], 2),
                "average_grade": average_letter_grade(t_data["grades"]),
                "executed_waivers": mgr_waivers[mid],
                "free_agent_adds": mgr_fa_adds[mid],
            }
        )

    return {
        "season_filter": season_filter,
        "has_transaction_data": has_transaction_data,
        "top_partners": top_partners,
        "active_traders": active_traders,
        "trades": trade_details,
    }


def get_deleted_trades(session: Session) -> list[dict[str, Any]]:
    """Return serialized TradeDetail records for trades with status == 'DELETED'."""
    deleted_raw = (
        session.query(Trade)
        .filter(Trade.status == "DELETED")
        .order_by(Trade.executed_at.desc(), Trade.id.desc())
        .all()
    )
    if not deleted_raw:
        return []

    # Pre-fetch master teams & managers
    teams = session.query(Team).all()
    team_map = {t.id: t for t in teams}
    seasons = session.query(Season).all()
    season_map = {s.season_year: s for s in seasons}
    teams_by_year: dict[int, list[Team]] = defaultdict(list)
    for t in teams:
        teams_by_year[t.season_year].append(t)

    def _get_league_size(year: int) -> int:
        return len(teams_by_year.get(year, [])) or 12

    managers = session.query(Manager).all()
    mgr_map = {m.id: m.display_name for m in managers}
    mgr_avatar_map = {m.id: m.avatar_url for m in managers}

    trade_tx_ids = [t.espn_transaction_id for t in deleted_raw]
    transactions = (
        session.query(Transaction)
        .filter(
            or_(
                Transaction.espn_transaction_id.in_(trade_tx_ids),
                Transaction.related_espn_transaction_id.in_(trade_tx_ids),
            )
        )
        .all()
    )
    tx_by_espn_id = {tx.espn_transaction_id: tx for tx in transactions}
    for tx in transactions:
        if tx.related_espn_transaction_id and tx.related_espn_transaction_id not in tx_by_espn_id:
            tx_by_espn_id[tx.related_espn_transaction_id] = tx

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

    draft_picks = session.query(DraftPick).all()
    draft_pick_map = {(dp.season_year, dp.overall_pick): dp for dp in draft_picks}
    players_all = session.query(Player).all()
    player_map = {p.espn_player_id: p for p in players_all}

    all_lineups = session.query(WeeklyLineup).all()
    week_points_sum: dict[tuple[int, int], float] = defaultdict(float)
    max_week_by_season: dict[int, int] = {}
    for wl in all_lineups:
        week_points_sum[(wl.season_year, wl.week)] += float(wl.actual_points or 0.0)
        max_week_by_season[wl.season_year] = max(max_week_by_season.get(wl.season_year, 0), wl.week)
    scored_weeks = {k for k, total_pts in week_points_sum.items() if total_pts > 0.0}
    for y, max_w in max_week_by_season.items():
        if (y, max_w) in week_points_sum:
            scored_weeks.add((y, max_w))

    player_lineups: dict[tuple[int, int], list[WeeklyLineup]] = defaultdict(list)
    player_week_lineup: dict[tuple[int, int, int], WeeklyLineup] = {}
    for wl in all_lineups:
        if (wl.season_year, wl.week) in scored_weeks:
            player_lineups[(wl.season_year, wl.player_id)].append(wl)
            player_week_lineup[(wl.season_year, wl.player_id, wl.week)] = wl

    all_season_trades: list[tuple[Trade, list[TransactionItem]]] = []
    for tr in deleted_raw:
        tr_tx = tx_by_espn_id.get(tr.espn_transaction_id)
        tr_items = items_by_tx_id.get(tr_tx.id, []) if tr_tx else []
        all_season_trades.append((tr, tr_items))

    deleted_details: list[dict[str, Any]] = []
    for trade in deleted_raw:
        tx = tx_by_espn_id.get(trade.espn_transaction_id)
        items = items_by_tx_id.get(tx.id, []) if tx else []
        detail = _evaluate_trade(
            trade=trade,
            team_map=team_map,
            mgr_map=mgr_map,
            mgr_avatar_map=mgr_avatar_map,
            items=items,
            scored_weeks=scored_weeks,
            player_lineups=player_lineups,
            player_week_lineup=player_week_lineup,
            player_map=player_map,
            draft_pick_map=draft_pick_map,
            league_size=_get_league_size(trade.season_year),
            all_season_trades=all_season_trades,
            season_info=season_map.get(trade.season_year),
        )
        if detail:
            deleted_details.append(detail)

    return deleted_details
