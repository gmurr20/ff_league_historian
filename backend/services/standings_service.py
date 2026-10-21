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
            "regular_season_weeks": season.regular_season_weeks,
            "playoff_team_count": season.playoff_team_count,
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

    # Cumulative weekly tracking for trajectory / bump chart
    cum_wins: dict[int, int] = defaultdict(int)
    cum_losses: dict[int, int] = defaultdict(int)
    cum_ties: dict[int, int] = defaultdict(int)
    cum_pf: dict[int, float] = defaultdict(float)
    weekly_history_by_team: dict[int, list[dict[str, Any]]] = defaultdict(list)

    for week in sorted(matchups_by_week.keys()):
        week_matches = matchups_by_week[week]
        # Map team_id -> actual_score for this week
        week_team_scores: dict[int, float] = {}

        for m in week_matches:
            # Home team
            h_id = m.home_team_id
            h_score = float(m.home_score)
            h_opt = (
                float(m.home_optimal_score)
                if m.home_optimal_score is not None
                else (
                    h_score + lineup_pts_by_team_week.get((h_id, week), {}).get("bench", 0.0)
                )
            )
            h_bench = (
                float(m.home_bench_points)
                if m.home_bench_points is not None
                else lineup_pts_by_team_week.get((h_id, week), {}).get("bench", 0.0)
            )
            week_team_scores[h_id] = h_score
            optimal_pts_for[h_id] += h_opt
            bench_pts_for[h_id] += h_bench
            cum_pf[h_id] += h_score

            # Away team
            if m.away_team_id is not None:
                a_id = m.away_team_id
                a_score = float(m.away_score)
                a_opt = (
                    float(m.away_optimal_score)
                    if m.away_optimal_score is not None
                    else (
                        a_score + lineup_pts_by_team_week.get((a_id, week), {}).get("bench", 0.0)
                    )
                )
                a_bench = (
                    float(m.away_bench_points)
                    if m.away_bench_points is not None
                    else lineup_pts_by_team_week.get((a_id, week), {}).get("bench", 0.0)
                )
                week_team_scores[a_id] = a_score
                optimal_pts_for[a_id] += a_opt
                bench_pts_for[a_id] += a_bench
                cum_pf[a_id] += a_score

                if m.is_tie or (m.winner_team_id is None and h_score == a_score):
                    cum_ties[h_id] += 1
                    cum_ties[a_id] += 1
                elif m.winner_team_id == h_id or (m.winner_team_id is None and h_score > a_score):
                    cum_wins[h_id] += 1
                    cum_losses[a_id] += 1
                else:
                    cum_wins[a_id] += 1
                    cum_losses[h_id] += 1

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

        # Compute week-end standings_rank and power_rank across all teams
        week_standings_order = sorted(
            teams,
            key=lambda t: (
                -(
                    (cum_wins[t.id] + 0.5 * cum_ties[t.id])
                    / max(1, cum_wins[t.id] + cum_losses[t.id] + cum_ties[t.id])
                ),
                -cum_wins[t.id],
                -cum_ties[t.id],
                -cum_pf[t.id],
                t.espn_team_id,
            ),
        )
        week_standings_rank_map = {
            t.id: idx for idx, t in enumerate(week_standings_order, start=1)
        }

        # Compute week-end power_rank based on Median record with All-Play as tiebreaker
        def _week_power_sort_key(t: Team) -> tuple[float, float, float, int]:
            tid = t.id
            m_tot = median_wins[tid] + median_losses[tid] + median_ties[tid]
            m_pct = (median_wins[tid] + 0.5 * median_ties[tid]) / m_tot if m_tot > 0 else 0.0

            ap_tot = all_play_wins[tid] + all_play_losses[tid] + all_play_ties[tid]
            ap_pct = (all_play_wins[tid] + 0.5 * all_play_ties[tid]) / ap_tot if ap_tot > 0 else 0.0

            return (-m_pct, -ap_pct, -cum_pf[tid], t.espn_team_id)

        week_power_order = sorted(teams, key=_week_power_sort_key)
        week_power_rank_map = {
            t.id: idx for idx, t in enumerate(week_power_order, start=1)
        }

        for t in teams:
            tid = t.id
            ap_w = all_play_wins[tid]
            ap_l = all_play_losses[tid]
            ap_t = all_play_ties[tid]
            ap_tot = ap_w + ap_l + ap_t
            ap_pct = round((ap_w + 0.5 * ap_t) / ap_tot, 3) if ap_tot > 0 else 0.0
            weekly_history_by_team[tid].append(
                {
                    "week": week,
                    "standings_rank": week_standings_rank_map[tid],
                    "power_rank": week_power_rank_map[tid],
                    "wins": cum_wins[tid],
                    "losses": cum_losses[tid],
                    "ties": cum_ties[tid],
                    "points_for": round(cum_pf[tid], 2),
                    "weekly_score": round(week_team_scores.get(tid, 0.0), 2),
                    "all_play_wins": ap_w,
                    "all_play_losses": ap_l,
                    "all_play_ties": ap_t,
                    "all_play_win_pct": ap_pct,
                }
            )

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
        if e.entry_type in (
            "WEEKLY_WIN",
            "WEEKLY_TIE",
            "WEEKLY_HIGH_SCORE",
            "WEEKLY_HIGH_SCORE_LOSS",
        ):
            weekly_earnings_by_team[e.team_id] += amt
        elif e.entry_type in ("CHAMPION", "RUNNER_UP", "THIRD_PLACE"):
            podium_earnings_by_team[e.team_id] += amt

    # Overall Power Rank calculation based on Median record with All-Play tiebreaker
    def _season_power_sort_key(t: Team) -> tuple[float, float, float, int]:
        tid = t.id
        m_tot = median_wins[tid] + median_losses[tid] + median_ties[tid]
        m_pct = (median_wins[tid] + 0.5 * median_ties[tid]) / m_tot if m_tot > 0 else 0.0

        ap_tot = all_play_wins[tid] + all_play_losses[tid] + all_play_ties[tid]
        ap_pct = (all_play_wins[tid] + 0.5 * all_play_ties[tid]) / ap_tot if ap_tot > 0 else 0.0

        return (-m_pct, -ap_pct, -float(t.points_for), t.espn_team_id)

    power_sorted_teams = sorted(teams, key=_season_power_sort_key)
    power_rank_map = {t.id: idx for idx, t in enumerate(power_sorted_teams, start=1)}

    # Official Standings Rank sorting
    # Prioritize official final_standing (> 0) if season completed, otherwise playoff seed (> 0) or wins/PF
    if season.is_completed and all(
        t.final_standing is not None and t.final_standing > 0 for t in teams
    ):
        sorted_teams = sorted(teams, key=lambda t: t.final_standing or 999)
    elif any(t.playoff_seed is not None and t.playoff_seed > 0 for t in teams):
        sorted_teams = sorted(
            teams,
            key=lambda t: (
                t.playoff_seed if (t.playoff_seed is not None and t.playoff_seed > 0) else 999,
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

        normalized_seed = (
            team.playoff_seed
            if (team.playoff_seed is not None and team.playoff_seed > 0)
            else None
        )
        normalized_final = (
            team.final_standing
            if (team.final_standing is not None and team.final_standing > 0)
            else None
        )

        standings.append(
            {
                "rank": rank_idx,
                "power_rank": power_rank_map[tid],
                "team_id": team.id,
                "team_name": team.team_name,
                "team_abbrev": team.team_abbrev,
                "logo_url": team.logo_url or (team.manager.avatar_url if team.manager else None),
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
                "playoff_seed": normalized_seed,
                "final_standing": normalized_final,
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
                "weekly_history": weekly_history_by_team[tid],
            }
        )

    return {
        "season_year": season.season_year,
        "is_active": season.is_active,
        "is_completed": season.is_completed,
        "current_week": season.current_week,
        "regular_season_weeks": season.regular_season_weeks,
        "playoff_team_count": season.playoff_team_count,
        "standings": standings,
    }
