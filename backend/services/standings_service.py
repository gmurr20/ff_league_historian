"""backend/services/standings_service.py - Standings & Performance Service.

Purpose:
    Computes regular-season standings, official win/loss records, All-Play records,
    Weekly Median records, Schedule Luck Index, and Coaching Lineup Efficiency.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from backend.models.earnings import EarningsLedger
from backend.models.lineup import WeeklyLineup
from backend.models.matchup import Matchup
from backend.models.season import Season
from backend.models.team import Team


def get_standings(session: Session, season_year: int | None = None) -> dict[str, Any]:
    """Calculate comprehensive standings and derived metrics for a season."""
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

    # Fetch all teams in the season
    teams = (
        session.query(Team)
        .filter(Team.season_year == season.season_year)
        .order_by(Team.id.asc())
        .all()
    )
    if not teams:
        return {
            "season_year": season.season_year,
            "is_active": season.is_active,
            "is_completed": season.is_completed,
            "current_week": season.current_week,
            "standings": [],
        }

    # Fetch completed regular-season matchups
    reg_matchups = (
        session.query(Matchup)
        .filter(
            Matchup.season_year == season.season_year,
            Matchup.matchup_type == "REGULAR",
            Matchup.is_completed.is_(True),
            Matchup.away_team_id.isnot(None),
        )
        .all()
    )

    # Pre-fetch weekly lineups in case optimal score or bench points are null on matchups
    weekly_lineups = (
        session.query(WeeklyLineup)
        .filter(WeeklyLineup.season_year == season.season_year)
        .all()
    )
    lineup_pts_by_team_week: dict[tuple[int, int], dict[str, float]] = defaultdict(
        lambda: {"starter": 0.0, "bench": 0.0}
    )
    for wl in weekly_lineups:
        key = (wl.team_id, wl.week)
        pts = float(wl.actual_points)
        if wl.is_starter:
            lineup_pts_by_team_week[key]["starter"] += pts
        else:
            lineup_pts_by_team_week[key]["bench"] += pts

    # Group matchups by week to compute weekly medians and all-play comparisons
    matchups_by_week: dict[int, list[Matchup]] = defaultdict(list)
    for m in reg_matchups:
        matchups_by_week[m.week].append(m)

    # Tracking dictionaries per team
    all_play_wins: dict[int, int] = defaultdict(int)
    all_play_losses: dict[int, int] = defaultdict(int)
    all_play_ties: dict[int, int] = defaultdict(int)
    median_wins: dict[int, int] = defaultdict(int)
    median_losses: dict[int, int] = defaultdict(int)
    median_ties: dict[int, int] = defaultdict(int)
    optimal_pts_for: dict[int, float] = defaultdict(float)
    bench_pts_for: dict[int, float] = defaultdict(float)

    for week, week_matches in matchups_by_week.items():
        # Map team_id -> (actual_score, optimal_score, bench_points)
        week_team_scores: dict[int, float] = {}

        for m in week_matches:
            # Home team
            h_score = float(m.home_score)
            h_opt = (
                float(m.home_optimal_score)
                if m.home_optimal_score is not None
                else (
                    h_score + lineup_pts_by_team_week.get((m.home_team_id, week), {}).get("bench", 0.0)
                )
            )
            h_bench = (
                float(m.home_bench_points)
                if m.home_bench_points is not None
                else lineup_pts_by_team_week.get((m.home_team_id, week), {}).get("bench", 0.0)
            )
            week_team_scores[m.home_team_id] = h_score
            optimal_pts_for[m.home_team_id] += h_opt
            bench_pts_for[m.home_team_id] += h_bench

            # Away team
            if m.away_team_id is not None:
                a_score = float(m.away_score)
                a_opt = (
                    float(m.away_optimal_score)
                    if m.away_optimal_score is not None
                    else (
                        a_score + lineup_pts_by_team_week.get((m.away_team_id, week), {}).get("bench", 0.0)
                    )
                )
                a_bench = (
                    float(m.away_bench_points)
                    if m.away_bench_points is not None
                    else lineup_pts_by_team_week.get((m.away_team_id, week), {}).get("bench", 0.0)
                )
                week_team_scores[m.away_team_id] = a_score
                optimal_pts_for[m.away_team_id] += a_opt
                bench_pts_for[m.away_team_id] += a_bench

        if not week_team_scores:
            continue

        # Compute weekly median score
        scores_list = list(week_team_scores.values())
        week_median = statistics.median(scores_list)

        # Weekly median records
        for tid, score in week_team_scores.items():
            if score > week_median:
                median_wins[tid] += 1
            elif score < week_median:
                median_losses[tid] += 1
            else:
                median_ties[tid] += 1

        # All-Play record (compare against every other team playing that week)
        for tid_a, score_a in week_team_scores.items():
            for tid_b, score_b in week_team_scores.items():
                if tid_a == tid_b:
                    continue
                if score_a > score_b:
                    all_play_wins[tid_a] += 1
                elif score_a < score_b:
                    all_play_losses[tid_a] += 1
                else:
                    all_play_ties[tid_a] += 1

    # Fetch financial earnings from earnings ledger for this season
    earnings_entries = (
        session.query(EarningsLedger)
        .filter(EarningsLedger.season_year == season.season_year)
        .all()
    )
    weekly_earnings_by_team: dict[int, float] = defaultdict(float)
    podium_earnings_by_team: dict[int, float] = defaultdict(float)
    for e in earnings_entries:
        amt = float(e.amount)
        if e.entry_type in ("WEEKLY_WIN", "WEEKLY_TIE"):
            weekly_earnings_by_team[e.team_id] += amt
        elif e.entry_type in ("CHAMPION", "RUNNER_UP", "THIRD_PLACE"):
            podium_earnings_by_team[e.team_id] += amt

    # Rank sorting
    # Prioritize official final_standing if season completed, otherwise playoff seed or wins/PF
    if all(t.final_standing is not None for t in teams):
        sorted_teams = sorted(teams, key=lambda t: t.final_standing or 999)
    elif any(t.playoff_seed is not None for t in teams):
        sorted_teams = sorted(
            teams,
            key=lambda t: (
                t.playoff_seed if t.playoff_seed is not None else 999,
                -float(t.wins),
                -float(t.points_for),
            ),
        )
    else:
        sorted_teams = sorted(
            teams,
            key=lambda t: (-t.wins, -t.ties, -float(t.points_for)),
        )

    standings: list[dict[str, Any]] = []
    for rank_idx, team in enumerate(sorted_teams, start=1):
        tid = team.id
        ap_w = all_play_wins[tid]
        ap_l = all_play_losses[tid]
        ap_t = all_play_ties[tid]
        total_ap_games = ap_w + ap_l + ap_t
        all_play_win_pct = (
            round((ap_w + 0.5 * ap_t) / total_ap_games, 3) if total_ap_games > 0 else 0.0
        )

        total_actual_games = team.wins + team.losses + team.ties
        actual_win_pct = (
            (team.wins + 0.5 * team.ties) / total_actual_games
            if total_actual_games > 0
            else 0.0
        )
        luck_index = round(actual_win_pct - all_play_win_pct, 4)

        opt_pf = round(optimal_pts_for[tid], 2)
        bench_pf = round(bench_pts_for[tid], 2)
        pf = float(team.points_for)

        if opt_pf > 0:
            lineup_efficiency = round((pf / opt_pf) * 100, 2)
        else:
            lineup_efficiency = 100.0

        w_earn = round(weekly_earnings_by_team[tid], 2)
        p_earn = round(podium_earnings_by_team[tid], 2)
        tot_earn = round(w_earn + p_earn, 2)

        standings.append(
            {
                "rank": rank_idx,
                "team_id": team.id,
                "team_name": team.team_name,
                "manager_id": team.manager_id,
                "manager_name": team.manager.display_name if team.manager else "",
                "co_manager_name": (
                    team.co_manager.display_name if team.co_manager else None
                ),
                "wins": team.wins,
                "losses": team.losses,
                "ties": team.ties,
                "points_for": round(float(team.points_for), 2),
                "points_against": round(float(team.points_against), 2),
                "streak_type": team.streak_type,
                "streak_length": team.streak_length,
                "playoff_seed": team.playoff_seed,
                "final_standing": team.final_standing,
                "all_play_wins": ap_w,
                "all_play_losses": ap_l,
                "all_play_ties": ap_t,
                "all_play_win_pct": all_play_win_pct,
                "median_wins": median_wins[tid],
                "median_losses": median_losses[tid],
                "median_ties": median_ties[tid],
                "luck_index": luck_index,
                "optimal_points_for": opt_pf,
                "bench_points": bench_pf,
                "lineup_efficiency": lineup_efficiency,
                "weekly_earnings": w_earn,
                "podium_earnings": p_earn,
                "total_earnings": tot_earn,
                "faab_remaining": team.faab_remaining,
            }
        )

    return {
        "season_year": season.season_year,
        "is_active": season.is_active,
        "is_completed": season.is_completed,
        "current_week": season.current_week,
        "standings": standings,
    }
