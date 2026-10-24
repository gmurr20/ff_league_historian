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
from backend.models.manager import Manager
from backend.models.matchup import Matchup
from backend.models.season import Season
from backend.models.team import Team


def _resolve_historical_accolades(session: Session) -> tuple[
    dict[int, set[int]],
    dict[int, set[int]],
    dict[int, set[int]],
    dict[int, set[int]],
]:
    """Resolve manager IDs for 1st (champions), 2nd (runner-ups), 3rd place,
    and regular-season scoring titles across all completed seasons.
    """
    completed_seasons = (
        session.query(Season.season_year)
        .filter(Season.is_completed.is_(True))
        .all()
    )
    completed_years = {s[0] for s in completed_seasons}

    champions_by_year: dict[int, set[int]] = defaultdict(set)
    runner_ups_by_year: dict[int, set[int]] = defaultdict(set)
    third_places_by_year: dict[int, set[int]] = defaultdict(set)
    scoring_leaders_by_year: dict[int, set[int]] = defaultdict(set)

    # 1. EarningsLedger entries
    ledger_entries = (
        session.query(EarningsLedger.season_year, EarningsLedger.manager_id, EarningsLedger.entry_type)
        .filter(
            EarningsLedger.entry_type.in_([
                "CHAMPION",
                "RUNNER_UP",
                "THIRD_PLACE",
                "REGULAR_SEASON_MOST_POINTS",
            ])
        )
        .all()
    )
    for yr, mid, etype in ledger_entries:
        if etype == "CHAMPION":
            champions_by_year[yr].add(mid)
        elif etype == "RUNNER_UP":
            runner_ups_by_year[yr].add(mid)
        elif etype == "THIRD_PLACE":
            third_places_by_year[yr].add(mid)
        elif etype == "REGULAR_SEASON_MOST_POINTS":
            scoring_leaders_by_year[yr].add(mid)

    # 2. Fallbacks from Team.final_standing for completed seasons
    podium_teams = (
        session.query(Team.season_year, Team.manager_id, Team.final_standing)
        .filter(
            Team.final_standing.in_([1, 2, 3]),
            Team.season_year.in_(completed_years),
        )
        .all()
    )
    for yr, mid, standing in podium_teams:
        if standing == 1:
            champions_by_year[yr].add(mid)
        elif standing == 2:
            runner_ups_by_year[yr].add(mid)
        elif standing == 3:
            third_places_by_year[yr].add(mid)

    # 3. Fallbacks for regular season most points for completed seasons
    for yr in completed_years:
        if yr not in scoring_leaders_by_year:
            yr_teams = session.query(Team).filter(Team.season_year == yr).all()
            if yr_teams:
                max_pf = max((float(t.points_for) for t in yr_teams), default=0.0)
                if max_pf > 0:
                    for t in yr_teams:
                        if float(t.points_for) == max_pf and t.manager_id:
                            scoring_leaders_by_year[yr].add(t.manager_id)

    return (
        dict(champions_by_year),
        dict(runner_ups_by_year),
        dict(third_places_by_year),
        dict(scoring_leaders_by_year),
    )


def _build_playoff_bracket(
    session: Session,
    season: Season,
    teams: list[Team],
) -> dict[str, Any] | None:
    """Build structured playoff tournament bracket when season has reached the playoffs."""
    # Only available once week 14 is finished (current_week > regular_season_weeks or is_completed)
    if not (season.is_completed or season.current_week > season.regular_season_weeks):
        return None

    playoff_matchups = (
        session.query(Matchup)
        .filter(
            Matchup.season_year == season.season_year,
            Matchup.matchup_type != "REGULAR",
        )
        .order_by(Matchup.week.asc(), Matchup.id.asc())
        .all()
    )
    if not playoff_matchups:
        return None

    team_lookup = {t.id: t for t in teams}

    def _team_ref(t: Team | None) -> dict[str, Any] | None:
        if not t:
            return None
        return {
            "team_id": t.id,
            "team_name": t.team_name,
            "team_abbrev": t.team_abbrev,
            "logo_url": t.logo_url or (t.manager.avatar_url if t.manager else None),
            "manager_id": t.manager_id,
            "manager_name": t.manager.display_name if t.manager else "",
            "playoff_seed": (
                t.playoff_seed if (t.playoff_seed and t.playoff_seed > 0) else None
            ),
            "final_standing": (
                t.final_standing if (t.final_standing and t.final_standing > 0) else None
            ),
        }

    weeks = sorted(list(set(m.week for m in playoff_matchups)))
    max_week = max(weeks)

    rounds: list[dict[str, Any]] = []
    for week_idx, w in enumerate(weeks, start=1):
        w_matches = [m for m in playoff_matchups if m.week == w]
        wb_matches = [m for m in w_matches if m.matchup_type == "WINNERS_BRACKET"]
        cons_matches = [m for m in w_matches if m.matchup_type != "WINNERS_BRACKET"]

        dist_from_final = max_week - w
        if dist_from_final == 0:
            round_label = "Championship"
        elif dist_from_final == 1:
            round_label = "Semifinals"
        elif dist_from_final == 2:
            round_label = "Quarterfinals"
        else:
            round_label = f"Round {week_idx}"

        def _format_matchup(
            m: Matchup, is_winners: bool, week_num: int = w, r_label: str = round_label
        ) -> dict[str, Any]:
            h_team = team_lookup.get(m.home_team_id)
            a_team = team_lookup.get(m.away_team_id) if m.away_team_id else None
            is_bye = m.matchup_type == "BYE" or m.away_team_id is None

            if week_num == max_week:
                if is_winners:
                    sub_label = "Championship Final"
                elif h_team and a_team and h_team.final_standing and a_team.final_standing:
                    min_standing = min(h_team.final_standing, a_team.final_standing)
                    if min_standing % 10 == 1 and min_standing % 100 != 11:
                        suffix = "st"
                    elif min_standing % 10 == 2 and min_standing % 100 != 12:
                        suffix = "nd"
                    elif min_standing % 10 == 3 and min_standing % 100 != 13:
                        suffix = "rd"
                    else:
                        suffix = "th"
                    sub_label = f"{min_standing}{suffix} Place Game"
                else:
                    sub_label = "Consolation Final"
            elif is_winners:
                sub_label = r_label
            else:
                sub_label = "Consolation"

            return {
                "id": m.id,
                "week": m.week,
                "matchup_type": m.matchup_type,
                "round_label": sub_label,
                "home_team": _team_ref(h_team),
                "away_team": _team_ref(a_team),
                "home_score": float(m.home_score),
                "away_score": float(m.away_score),
                "winner_team_id": m.winner_team_id,
                "is_completed": m.is_completed,
                "is_bye": is_bye,
            }

        rounds.append(
            {
                "week": w,
                "round_label": round_label,
                "winners_bracket": [_format_matchup(m, True) for m in wb_matches],
                "consolation": [_format_matchup(m, False) for m in cons_matches],
            }
        )

    champ_team = next((t for t in teams if t.final_standing == 1), None)
    runner_team = next((t for t in teams if t.final_standing == 2), None)
    third_team = next((t for t in teams if t.final_standing == 3), None)

    return {
        "season_year": season.season_year,
        "is_available": True,
        "championship_round_week": max_week,
        "rounds": rounds,
        "champion": _team_ref(champ_team),
        "runner_up": _team_ref(runner_team),
        "third_place": _team_ref(third_team),
    }


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
            "defending_champion_manager_id": None,
            "defending_champion_team_id": None,
            "playoff_bracket": None,
            "standings": [],
        }

    team_lookup: dict[int, Team] = {t.id: t for t in teams}

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
    actual_lineup_pts_for: dict[int, float] = defaultdict(float)
    games_with_lineup_data: dict[int, int] = defaultdict(int)

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
        week_matchup_details: dict[int, dict[str, Any]] = {}

        for m in week_matches:
            # Home team
            h_id = m.home_team_id
            h_score = float(m.home_score)
            h_has_lineup_data = False
            h_opt = 0.0
            h_bench = 0.0

            if m.home_optimal_score is not None and float(m.home_optimal_score) > 0:
                h_has_lineup_data = True
                h_opt = float(m.home_optimal_score)
                h_bench = (
                    float(m.home_bench_points)
                    if m.home_bench_points is not None
                    else lineup_pts_by_team_week.get((h_id, week), {}).get("bench", 0.0)
                )
            elif (h_id, week) in lineup_pts_by_team_week and (
                lineup_pts_by_team_week[(h_id, week)]["starter"] > 0
                or lineup_pts_by_team_week[(h_id, week)]["bench"] > 0
            ):
                h_has_lineup_data = True
                h_bench = lineup_pts_by_team_week[(h_id, week)]["bench"]
                h_opt = h_score + h_bench

            week_team_scores[h_id] = h_score
            cum_pf[h_id] += h_score

            if h_has_lineup_data:
                optimal_pts_for[h_id] += h_opt
                bench_pts_for[h_id] += h_bench
                actual_lineup_pts_for[h_id] += h_score
                games_with_lineup_data[h_id] += 1

            # Away team
            if m.away_team_id is not None:
                a_id = m.away_team_id
                a_score = float(m.away_score)
                a_has_lineup_data = False
                a_opt = 0.0
                a_bench = 0.0

                if m.away_optimal_score is not None and float(m.away_optimal_score) > 0:
                    a_has_lineup_data = True
                    a_opt = float(m.away_optimal_score)
                    a_bench = (
                        float(m.away_bench_points)
                        if m.away_bench_points is not None
                        else lineup_pts_by_team_week.get((a_id, week), {}).get("bench", 0.0)
                    )
                elif (a_id, week) in lineup_pts_by_team_week and (
                    lineup_pts_by_team_week[(a_id, week)]["starter"] > 0
                    or lineup_pts_by_team_week[(a_id, week)]["bench"] > 0
                ):
                    a_has_lineup_data = True
                    a_bench = lineup_pts_by_team_week[(a_id, week)]["bench"]
                    a_opt = a_score + a_bench

                week_team_scores[a_id] = a_score
                cum_pf[a_id] += a_score

                if a_has_lineup_data:
                    optimal_pts_for[a_id] += a_opt
                    bench_pts_for[a_id] += a_bench
                    actual_lineup_pts_for[a_id] += a_score
                    games_with_lineup_data[a_id] += 1

                if m.is_tie or (m.winner_team_id is None and h_score == a_score):
                    cum_ties[h_id] += 1
                    cum_ties[a_id] += 1
                    h_res = "TIE"
                    a_res = "TIE"
                elif m.winner_team_id == h_id or (m.winner_team_id is None and h_score > a_score):
                    cum_wins[h_id] += 1
                    cum_losses[a_id] += 1
                    h_res = "WIN"
                    a_res = "LOSS"
                else:
                    cum_wins[a_id] += 1
                    cum_losses[h_id] += 1
                    h_res = "LOSS"
                    a_res = "WIN"

                opp_a = team_lookup.get(a_id)
                opp_h = team_lookup.get(h_id)

                week_matchup_details[h_id] = {
                    "opponent_team_id": a_id,
                    "opponent_team_name": opp_a.team_name if opp_a else None,
                    "opponent_team_abbrev": opp_a.team_abbrev if opp_a else None,
                    "opponent_logo_url": (
                        opp_a.logo_url or (opp_a.manager.avatar_url if opp_a and opp_a.manager else None)
                        if opp_a
                        else None
                    ),
                    "opponent_manager_name": opp_a.manager.display_name if opp_a and opp_a.manager else None,
                    "opponent_score": round(a_score, 2),
                    "result": h_res,
                    "is_home": True,
                }
                week_matchup_details[a_id] = {
                    "opponent_team_id": h_id,
                    "opponent_team_name": opp_h.team_name if opp_h else None,
                    "opponent_team_abbrev": opp_h.team_abbrev if opp_h else None,
                    "opponent_logo_url": (
                        opp_h.logo_url or (opp_h.manager.avatar_url if opp_h and opp_h.manager else None)
                        if opp_h
                        else None
                    ),
                    "opponent_manager_name": opp_h.manager.display_name if opp_h and opp_h.manager else None,
                    "opponent_score": round(h_score, 2),
                    "result": a_res,
                    "is_home": False,
                }
            else:
                week_matchup_details[h_id] = {
                    "opponent_team_id": None,
                    "opponent_team_name": None,
                    "opponent_team_abbrev": None,
                    "opponent_logo_url": None,
                    "opponent_manager_name": None,
                    "opponent_score": None,
                    "result": "BYE",
                    "is_home": True,
                }

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
            m_info = week_matchup_details.get(
                tid,
                {
                    "opponent_team_id": None,
                    "opponent_team_name": None,
                    "opponent_team_abbrev": None,
                    "opponent_logo_url": None,
                    "opponent_manager_name": None,
                    "opponent_score": None,
                    "result": None,
                    "is_home": None,
                },
            )
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
                    "opponent_team_id": m_info["opponent_team_id"],
                    "opponent_team_name": m_info["opponent_team_name"],
                    "opponent_team_abbrev": m_info["opponent_team_abbrev"],
                    "opponent_logo_url": m_info["opponent_logo_url"],
                    "opponent_manager_name": m_info["opponent_manager_name"],
                    "opponent_score": m_info["opponent_score"],
                    "result": m_info["result"],
                    "is_home": m_info["is_home"],
                }
            )

    # Process completed playoff weeks (weeks > regular_season_weeks) for trajectory chart
    playoff_matchups = (
        session.query(Matchup)
        .filter(
            Matchup.season_year == season.season_year,
            Matchup.matchup_type != "REGULAR",
            Matchup.is_completed.is_(True),
        )
        .order_by(Matchup.week.asc(), Matchup.id.asc())
        .all()
    )

    playoff_matchups_by_week: dict[int, list[Matchup]] = defaultdict(list)
    for m in playoff_matchups:
        playoff_matchups_by_week[m.week].append(m)

    playoff_weeks = sorted(playoff_matchups_by_week.keys())
    if playoff_weeks:
        final_playoff_week = max(playoff_weeks)
        for p_week in playoff_weeks:
            p_matches = playoff_matchups_by_week[p_week]
            week_team_scores: dict[int, float] = {}
            playoff_matchup_details: dict[int, dict[str, Any]] = {}

            # Update scores and outcomes
            for m in p_matches:
                h_id = m.home_team_id
                h_score = float(m.home_score)
                week_team_scores[h_id] = h_score
                cum_pf[h_id] += h_score

                if m.away_team_id is not None:
                    a_id = m.away_team_id
                    a_score = float(m.away_score)
                    week_team_scores[a_id] = a_score
                    cum_pf[a_id] += a_score

                if m.winner_team_id is not None:
                    cum_wins[m.winner_team_id] += 1
                    loser_id = (
                        m.away_team_id
                        if m.winner_team_id == m.home_team_id
                        else m.home_team_id
                    )
                    if loser_id is not None:
                        cum_losses[loser_id] += 1

                if m.away_team_id is not None:
                    if m.winner_team_id == h_id:
                        h_res = "WIN"
                        a_res = "LOSS"
                    elif m.winner_team_id == a_id:
                        h_res = "LOSS"
                        a_res = "WIN"
                    elif m.is_tie or (m.winner_team_id is None and h_score == a_score):
                        h_res = "TIE"
                        a_res = "TIE"
                    elif h_score > a_score:
                        h_res = "WIN"
                        a_res = "LOSS"
                    else:
                        h_res = "LOSS"
                        a_res = "WIN"

                    opp_a = team_lookup.get(a_id)
                    opp_h = team_lookup.get(h_id)

                    playoff_matchup_details[h_id] = {
                        "opponent_team_id": a_id,
                        "opponent_team_name": opp_a.team_name if opp_a else None,
                        "opponent_team_abbrev": opp_a.team_abbrev if opp_a else None,
                        "opponent_logo_url": (
                            opp_a.logo_url or (opp_a.manager.avatar_url if opp_a and opp_a.manager else None)
                            if opp_a
                            else None
                        ),
                        "opponent_manager_name": opp_a.manager.display_name if opp_a and opp_a.manager else None,
                        "opponent_score": round(a_score, 2),
                        "result": h_res,
                        "is_home": True,
                    }
                    playoff_matchup_details[a_id] = {
                        "opponent_team_id": h_id,
                        "opponent_team_name": opp_h.team_name if opp_h else None,
                        "opponent_team_abbrev": opp_h.team_abbrev if opp_h else None,
                        "opponent_logo_url": (
                            opp_h.logo_url or (opp_h.manager.avatar_url if opp_h and opp_h.manager else None)
                            if opp_h
                            else None
                        ),
                        "opponent_manager_name": opp_h.manager.display_name if opp_h and opp_h.manager else None,
                        "opponent_score": round(h_score, 2),
                        "result": a_res,
                        "is_home": False,
                    }
                else:
                    playoff_matchup_details[h_id] = {
                        "opponent_team_id": None,
                        "opponent_team_name": None,
                        "opponent_team_abbrev": None,
                        "opponent_logo_url": None,
                        "opponent_manager_name": None,
                        "opponent_score": None,
                        "result": "BYE",
                        "is_home": True,
                    }

            # Determine rank for each team in this playoff week with strict playoff cutline guardrails:
            # Invariant: Teams that qualified for playoffs (playoff_seed <= playoff_team_count)
            # must strictly occupy ranks 1 .. playoff_team_count and can NEVER dip below the cutline.
            # Non-playoff teams must strictly occupy ranks playoff_team_count + 1 .. N.
            playoff_cutoff = (
                season.playoff_team_count
                if (season.playoff_team_count and season.playoff_team_count > 0)
                else max(1, len(teams) // 2)
            )

            def _team_seed(t: Team) -> int:
                if t.playoff_seed and t.playoff_seed > 0:
                    return t.playoff_seed
                reg_h = [
                    h
                    for h in weekly_history_by_team.get(t.id, [])
                    if h.get("week") == season.regular_season_weeks
                ]
                if reg_h:
                    return reg_h[0]["standings_rank"]
                return 999

            playoff_teams = [t for t in teams if _team_seed(t) <= playoff_cutoff]
            non_playoff_teams = [t for t in teams if _team_seed(t) > playoff_cutoff]

            team_lookup = {t.id: t for t in teams}

            # 1. Rank Playoff Teams (strictly within ranks 1 .. playoff_cutoff)
            if p_week == final_playoff_week and any(t.final_standing for t in playoff_teams):
                pt_order = sorted(playoff_teams, key=lambda t: t.final_standing or 999)
            else:
                p_matches_in_playoffs = [
                    m for m in p_matches
                    if m.home_team_id in [t.id for t in playoff_teams]
                ]
                wb_matches = [m for m in p_matches_in_playoffs if m.matchup_type == "WINNERS_BRACKET"]
                cons_p_matches = [m for m in p_matches_in_playoffs if m.matchup_type != "WINNERS_BRACKET"]

                wb_winners = [m.winner_team_id for m in wb_matches if m.winner_team_id]
                wb_losers = [
                    (m.away_team_id if m.winner_team_id == m.home_team_id else m.home_team_id)
                    for m in wb_matches
                    if m.winner_team_id
                ]
                cons_winners = [m.winner_team_id for m in cons_p_matches if m.winner_team_id]
                cons_losers = [
                    (m.away_team_id if m.winner_team_id == m.home_team_id else m.home_team_id)
                    for m in cons_p_matches
                    if m.winner_team_id
                ]

                def _sort_pt(
                    tids: list[int | None], target_teams: list[Team] = playoff_teams
                ) -> list[int]:
                    subset = [t for t in target_teams if t.id in tids]
                    return [
                        t.id
                        for t in sorted(
                            subset,
                            key=lambda x: (_team_seed(x), -cum_pf[x.id]),
                        )
                    ]

                ordered_pt_ids = (
                    _sort_pt(wb_winners)
                    + _sort_pt(wb_losers)
                    + _sort_pt(cons_winners)
                    + _sort_pt(cons_losers)
                )
                placed_pt = set(ordered_pt_ids)
                unplaced_pt = [
                    t.id
                    for t in sorted(playoff_teams, key=lambda x: _team_seed(x))
                    if t.id not in placed_pt
                ]
                ordered_pt_ids.extend(unplaced_pt)
                pt_order = [team_lookup[tid] for tid in ordered_pt_ids]

            # 2. Rank Non-Playoff Teams (strictly within ranks playoff_cutoff + 1 .. N)
            # Consolation bracket match results are disregarded; non-playoff teams stay fixed at their regular season seed
            npt_order = sorted(
                non_playoff_teams,
                key=lambda t: (
                    _team_seed(t),
                    -float(t.wins),
                    -cum_pf[t.id],
                ),
            )

            all_ordered = pt_order + npt_order
            week_rank_map = {t.id: idx for idx, t in enumerate(all_ordered, start=1)}

            for t in teams:
                tid = t.id
                rank = week_rank_map.get(tid, 1)
                last_hist = (
                    weekly_history_by_team[tid][-1]
                    if weekly_history_by_team[tid]
                    else None
                )
                ap_w = last_hist["all_play_wins"] if last_hist else 0
                ap_l = last_hist["all_play_losses"] if last_hist else 0
                ap_t = last_hist["all_play_ties"] if last_hist else 0
                ap_pct = last_hist["all_play_win_pct"] if last_hist else 0.0

                p_info = playoff_matchup_details.get(
                    tid,
                    {
                        "opponent_team_id": None,
                        "opponent_team_name": None,
                        "opponent_team_abbrev": None,
                        "opponent_logo_url": None,
                        "opponent_manager_name": None,
                        "opponent_score": None,
                        "result": None,
                        "is_home": None,
                    },
                )

                weekly_history_by_team[tid].append(
                    {
                        "week": p_week,
                        "standings_rank": rank,
                        "power_rank": rank,
                        "wins": cum_wins[tid],
                        "losses": cum_losses[tid],
                        "ties": cum_ties[tid],
                        "points_for": round(cum_pf[tid], 2),
                        "weekly_score": round(week_team_scores.get(tid, 0.0), 2),
                        "all_play_wins": ap_w,
                        "all_play_losses": ap_l,
                        "all_play_ties": ap_t,
                        "all_play_win_pct": ap_pct,
                        "opponent_team_id": p_info["opponent_team_id"],
                        "opponent_team_name": p_info["opponent_team_name"],
                        "opponent_team_abbrev": p_info["opponent_team_abbrev"],
                        "opponent_logo_url": p_info["opponent_logo_url"],
                        "opponent_manager_name": p_info["opponent_manager_name"],
                        "opponent_score": p_info["opponent_score"],
                        "result": p_info["result"],
                        "is_home": p_info["is_home"],
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
        elif e.entry_type in (
            "CHAMPION",
            "RUNNER_UP",
            "THIRD_PLACE",
            "FOURTH_PLACE",
            "FIFTH_PLACE",
            "REGULAR_SEASON_MOST_POINTS",
        ):
            podium_earnings_by_team[e.team_id] += amt

    # Resolve historical titles, podiums, scoring leaders, and defending champion
    (
        champions_by_year,
        runner_ups_by_year,
        third_places_by_year,
        scoring_leaders_by_year,
    ) = _resolve_historical_accolades(session)

    # Defending champion is the champion of the most recent completed season prior to this season
    prior_completed_years = [
        yr for yr in champions_by_year.keys()
        if yr < season.season_year
    ]
    defending_champ_mgr_id: int | None = None
    if prior_completed_years:
        last_year = max(prior_completed_years)
        champ_mids = champions_by_year.get(last_year, set())
        if champ_mids:
            defending_champ_mgr_id = next(iter(champ_mids))

    defending_champ_team_id: int | None = None
    if defending_champ_mgr_id is not None:
        for t in teams:
            if t.manager_id == defending_champ_mgr_id or (
                t.co_manager_id and t.co_manager_id == defending_champ_mgr_id
            ):
                defending_champ_team_id = t.id
                break

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
    playoff_cutoff = season.playoff_team_count or 6
    if season.is_completed and all(
        t.final_standing is not None and t.final_standing > 0 for t in teams
    ):
        playoff_teams = [
            t for t in teams if (t.playoff_seed and t.playoff_seed <= playoff_cutoff)
        ]
        non_playoff_teams = [
            t for t in teams if not (t.playoff_seed and t.playoff_seed <= playoff_cutoff)
        ]
        sorted_pt = sorted(playoff_teams, key=lambda t: t.final_standing or 999)
        sorted_npt = sorted(
            non_playoff_teams,
            key=lambda t: (
                t.playoff_seed if (t.playoff_seed and t.playoff_seed > 0) else 999,
                -float(t.wins),
                -float(t.points_for),
            ),
        )
        sorted_teams = sorted_pt + sorted_npt
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
        act_lineup_pf = actual_lineup_pts_for[tid]

        if games_with_lineup_data[tid] > 0 and opt_pf > 0:
            lineup_efficiency = round((act_lineup_pf / opt_pf) * 100, 2)
            lineup_efficiency = min(100.0, max(0.0, lineup_efficiency))
        else:
            lineup_efficiency = 0.0

        w_earn = round(weekly_earnings_by_team[tid], 2)
        p_earn = round(podium_earnings_by_team[tid], 2)
        tot_earn = round(w_earn + p_earn, 2)

        normalized_seed = (
            team.playoff_seed
            if (team.playoff_seed is not None and team.playoff_seed > 0)
            else None
        )
        if (
            season.is_completed
            and team.playoff_seed is not None
            and team.playoff_seed > playoff_cutoff
        ):
            normalized_final = team.playoff_seed
        else:
            normalized_final = (
                team.final_standing
                if (team.final_standing is not None and team.final_standing > 0)
                else None
            )

        mgr_champ_years = sorted(
            yr
            for yr, mids in champions_by_year.items()
            if (
                team.manager_id in mids
                or (team.co_manager_id and team.co_manager_id in mids)
            )
            and yr <= season.season_year
        )
        mgr_runner_years = sorted(
            yr
            for yr, mids in runner_ups_by_year.items()
            if (
                team.manager_id in mids
                or (team.co_manager_id and team.co_manager_id in mids)
            )
            and yr <= season.season_year
        )
        mgr_third_years = sorted(
            yr
            for yr, mids in third_places_by_year.items()
            if (
                team.manager_id in mids
                or (team.co_manager_id and team.co_manager_id in mids)
            )
            and yr <= season.season_year
        )
        mgr_scoring_years = sorted(
            yr
            for yr, mids in scoring_leaders_by_year.items()
            if (
                team.manager_id in mids
                or (team.co_manager_id and team.co_manager_id in mids)
            )
            and yr <= season.season_year
        )
        is_defending_champ = bool(
            defending_champ_mgr_id is not None
            and (
                team.manager_id == defending_champ_mgr_id
                or (team.co_manager_id is not None and team.co_manager_id == defending_champ_mgr_id)
            )
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
                "is_active": bool(team.manager.is_active if team.manager else True),
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
                "championships": len(mgr_champ_years),
                "championship_years": mgr_champ_years,
                "runner_ups": len(mgr_runner_years),
                "runner_up_years": mgr_runner_years,
                "third_places": len(mgr_third_years),
                "third_place_years": mgr_third_years,
                "scoring_champs": len(mgr_scoring_years),
                "scoring_champ_years": mgr_scoring_years,
                "is_defending_champion": is_defending_champ,
                "weekly_history": weekly_history_by_team[tid],
            }
        )

    playoff_bracket = _build_playoff_bracket(session, season, teams)

    return {
        "season_year": season.season_year,
        "is_active": season.is_active,
        "is_completed": season.is_completed,
        "current_week": season.current_week,
        "regular_season_weeks": season.regular_season_weeks,
        "playoff_team_count": season.playoff_team_count,
        "defending_champion_manager_id": defending_champ_mgr_id,
        "defending_champion_team_id": defending_champ_team_id,
        "playoff_bracket": playoff_bracket,
        "standings": standings,
    }


def get_all_time_standings(session: Session) -> dict[str, Any]:
    """Calculate all-time career standings and performance metrics across all seasons."""
    seasons = session.query(Season).order_by(Season.season_year.desc()).all()
    active_season = next((s for s in seasons if s.is_active), None)
    active_mgr_ids: set[int] = set()
    if active_season:
        active_mgr_ids = {
            t.manager_id for t in active_season.teams if t.manager_id
        } | {
            t.co_manager_id for t in active_season.teams if t.co_manager_id
        }

    # Query all teams and map by manager_id
    all_teams = session.query(Team).all()
    teams_by_manager: dict[int, list[Team]] = defaultdict(list)
    team_to_manager: dict[int, int] = {}
    for t in all_teams:
        if t.manager_id:
            teams_by_manager[t.manager_id].append(t)
            team_to_manager[t.id] = t.manager_id

    # Resolve completed regular-season matchups across history
    reg_matchups = (
        session.query(Matchup)
        .filter(
            Matchup.matchup_type == "REGULAR",
            Matchup.is_completed.is_(True),
            Matchup.away_team_id.isnot(None),
        )
        .all()
    )

    # Pre-fetch weekly lineups for optimal points and bench points
    weekly_lineups = session.query(WeeklyLineup).all()
    lineup_pts_by_team_week: dict[tuple[int, int, int], dict[str, float]] = defaultdict(
        lambda: {"starter": 0.0, "bench": 0.0}
    )
    for wl in weekly_lineups:
        key = (wl.season_year, wl.team_id, wl.week)
        pts = float(wl.actual_points)
        if wl.is_starter:
            lineup_pts_by_team_week[key]["starter"] += pts
        else:
            lineup_pts_by_team_week[key]["bench"] += pts

    # Group matchups by (season_year, week)
    matchups_by_season_week: dict[tuple[int, int], list[Matchup]] = defaultdict(list)
    for m in reg_matchups:
        matchups_by_season_week[(m.season_year, m.week)].append(m)

    ap_wins: dict[int, int] = defaultdict(int)
    ap_losses: dict[int, int] = defaultdict(int)
    ap_ties: dict[int, int] = defaultdict(int)
    med_wins: dict[int, int] = defaultdict(int)
    med_losses: dict[int, int] = defaultdict(int)
    med_ties: dict[int, int] = defaultdict(int)
    optimal_pts_for: dict[int, float] = defaultdict(float)
    bench_pts_for: dict[int, float] = defaultdict(float)
    actual_lineup_pts_for: dict[int, float] = defaultdict(float)
    games_with_lineup_data: dict[int, int] = defaultdict(int)

    for (s_yr, wk), matches in matchups_by_season_week.items():
        week_scores: dict[int, float] = {}
        for m in matches:
            h_id = m.home_team_id
            a_id = m.away_team_id
            h_score = float(m.home_score)
            a_score = float(m.away_score)
            week_scores[h_id] = h_score
            if a_id is not None:
                week_scores[a_id] = a_score

            h_mid = team_to_manager.get(h_id)
            if h_mid:
                h_key = (s_yr, h_id, wk)
                h_has_lineup_data = False
                h_opt = 0.0
                h_bench = 0.0

                if m.home_optimal_score is not None and float(m.home_optimal_score) > 0:
                    h_has_lineup_data = True
                    h_opt = float(m.home_optimal_score)
                    h_bench = (
                        float(m.home_bench_points)
                        if m.home_bench_points is not None
                        else lineup_pts_by_team_week[h_key]["bench"]
                    )
                elif h_key in lineup_pts_by_team_week and (
                    lineup_pts_by_team_week[h_key]["starter"] > 0
                    or lineup_pts_by_team_week[h_key]["bench"] > 0
                ):
                    h_has_lineup_data = True
                    h_bench = lineup_pts_by_team_week[h_key]["bench"]
                    h_opt = h_score + h_bench

                if h_has_lineup_data:
                    optimal_pts_for[h_mid] += h_opt
                    bench_pts_for[h_mid] += h_bench
                    actual_lineup_pts_for[h_mid] += h_score
                    games_with_lineup_data[h_mid] += 1

            if a_id is not None:
                a_mid = team_to_manager.get(a_id)
                if a_mid:
                    a_key = (s_yr, a_id, wk)
                    a_has_lineup_data = False
                    a_opt = 0.0
                    a_bench = 0.0

                    if m.away_optimal_score is not None and float(m.away_optimal_score) > 0:
                        a_has_lineup_data = True
                        a_opt = float(m.away_optimal_score)
                        a_bench = (
                            float(m.away_bench_points)
                            if m.away_bench_points is not None
                            else lineup_pts_by_team_week[a_key]["bench"]
                        )
                    elif a_key in lineup_pts_by_team_week and (
                        lineup_pts_by_team_week[a_key]["starter"] > 0
                        or lineup_pts_by_team_week[a_key]["bench"] > 0
                    ):
                        a_has_lineup_data = True
                        a_bench = lineup_pts_by_team_week[a_key]["bench"]
                        a_opt = a_score + a_bench

                    if a_has_lineup_data:
                        optimal_pts_for[a_mid] += a_opt
                        bench_pts_for[a_mid] += a_bench
                        actual_lineup_pts_for[a_mid] += a_score
                        games_with_lineup_data[a_mid] += 1

        scores = list(week_scores.values())
        if scores:
            med_val = statistics.median(scores)
            for tid, sc in week_scores.items():
                mid = team_to_manager.get(tid)
                if not mid:
                    continue
                if sc > med_val:
                    med_wins[mid] += 1
                elif sc < med_val:
                    med_losses[mid] += 1
                else:
                    med_ties[mid] += 1

                for other_tid, other_sc in week_scores.items():
                    if other_tid == tid:
                        continue
                    if sc > other_sc:
                        ap_wins[mid] += 1
                    elif sc < other_sc:
                        ap_losses[mid] += 1
                    else:
                        ap_ties[mid] += 1

    # Earnings ledger query
    ledger_entries = session.query(EarningsLedger).all()
    weekly_earnings: dict[int, float] = defaultdict(float)
    podium_earnings: dict[int, float] = defaultdict(float)
    total_earnings: dict[int, float] = defaultdict(float)
    for e in ledger_entries:
        amt = float(e.amount)
        total_earnings[e.manager_id] += amt
        if e.entry_type in (
            "CHAMPION",
            "RUNNER_UP",
            "THIRD_PLACE",
            "FOURTH_PLACE",
            "FIFTH_PLACE",
            "REGULAR_SEASON_MOST_POINTS",
        ):
            podium_earnings[e.manager_id] += amt
        else:
            weekly_earnings[e.manager_id] += amt

    # Resolve titles, runner-ups, 3rd places, scoring leaders, and defending champion
    (
        champions_by_year,
        runner_ups_by_year,
        third_places_by_year,
        scoring_leaders_by_year,
    ) = _resolve_historical_accolades(session)

    completed_seasons = [s for s in seasons if s.is_completed]
    defending_champ_mgr_id: int | None = None
    if completed_seasons:
        latest_comp = max(completed_seasons, key=lambda s: s.season_year)
        champ_mids = champions_by_year.get(latest_comp.season_year, set())
        if champ_mids:
            defending_champ_mgr_id = next(iter(champ_mids))

    managers = session.query(Manager).all()
    entries: list[dict[str, Any]] = []

    for mgr in managers:
        mgr_teams = sorted(teams_by_manager.get(mgr.id, []), key=lambda t: t.season_year)
        if not mgr_teams:
            continue

        latest_team = mgr_teams[-1]
        c_wins = sum(t.wins for t in mgr_teams)
        c_losses = sum(t.losses for t in mgr_teams)
        c_ties = sum(t.ties for t in mgr_teams)
        tot_games = c_wins + c_losses + c_ties
        win_pct = (
            round((c_wins + 0.5 * c_ties) / tot_games, 4) if tot_games > 0 else 0.0
        )
        c_pf = round(sum(float(t.points_for) for t in mgr_teams), 2)
        c_pa = round(sum(float(t.points_against) for t in mgr_teams), 2)

        champ_years = sorted(
            [yr for yr, mids in champions_by_year.items() if mgr.id in mids]
        )
        runner_years = sorted(
            [yr for yr, mids in runner_ups_by_year.items() if mgr.id in mids]
        )
        third_years = sorted(
            [yr for yr, mids in third_places_by_year.items() if mgr.id in mids]
        )
        scoring_years = sorted(
            [yr for yr, mids in scoring_leaders_by_year.items() if mgr.id in mids]
        )

        is_active = bool(mgr.is_active and (not active_season or mgr.id in active_mgr_ids))

        ap_w = ap_wins[mgr.id]
        ap_l = ap_losses[mgr.id]
        ap_t = ap_ties[mgr.id]
        ap_tot = ap_w + ap_l + ap_t
        ap_pct = (
            round((ap_w + 0.5 * ap_t) / ap_tot, 4) if ap_tot > 0 else 0.0
        )

        opt = optimal_pts_for[mgr.id]
        act_lineup = actual_lineup_pts_for[mgr.id]
        if games_with_lineup_data[mgr.id] > 0 and opt > 0:
            eff = round((act_lineup / opt) * 100, 2)
            eff = min(100.0, max(0.0, eff))
        else:
            eff = 0.0
        luck = round(win_pct - ap_pct, 4)

        # Weekly history maps to seasonal progression points
        season_history = [
            {
                "week": t.season_year,
                "standings_rank": t.final_standing or t.playoff_seed or 1,
                "power_rank": t.final_standing or t.playoff_seed or 1,
                "wins": t.wins,
                "losses": t.losses,
                "ties": t.ties,
                "points_for": round(float(t.points_for), 2),
                "weekly_score": round(float(t.points_for) / max(1, t.wins + t.losses + t.ties), 2),
                "all_play_wins": 0,
                "all_play_losses": 0,
                "all_play_ties": 0,
                "all_play_win_pct": 0.0,
                "opponent_team_id": None,
                "opponent_team_name": None,
                "opponent_team_abbrev": None,
                "opponent_logo_url": None,
                "opponent_manager_name": None,
                "opponent_score": None,
                "result": None,
                "is_home": None,
            }
            for t in mgr_teams
        ]

        entries.append(
            {
                "team_id": latest_team.id,
                "team_name": latest_team.team_name,
                "team_abbrev": latest_team.team_abbrev,
                "logo_url": latest_team.logo_url or mgr.avatar_url,
                "manager_id": mgr.id,
                "manager_name": mgr.display_name,
                "co_manager_name": (
                    latest_team.co_manager.display_name if latest_team.co_manager else None
                ),
                "is_active": is_active,
                "wins": c_wins,
                "losses": c_losses,
                "ties": c_ties,
                "points_for": c_pf,
                "points_against": c_pa,
                "win_pct": win_pct,
                "streak_type": latest_team.streak_type,
                "streak_length": latest_team.streak_length,
                "playoff_seed": None,
                "final_standing": None,
                "all_play_wins": ap_w,
                "all_play_losses": ap_l,
                "all_play_ties": ap_t,
                "all_play_win_pct": ap_pct,
                "median_wins": med_wins[mgr.id],
                "median_losses": med_losses[mgr.id],
                "median_ties": med_ties[mgr.id],
                "luck_index": luck,
                "optimal_points_for": round(opt, 2),
                "bench_points": round(bench_pts_for[mgr.id], 2),
                "lineup_efficiency": eff,
                "weekly_earnings": round(weekly_earnings[mgr.id], 2),
                "podium_earnings": round(podium_earnings[mgr.id], 2),
                "total_earnings": round(total_earnings[mgr.id], 2),
                "faab_remaining": 0,
                "championships": len(champ_years),
                "championship_years": champ_years,
                "runner_ups": len(runner_years),
                "runner_up_years": runner_years,
                "third_places": len(third_years),
                "third_place_years": third_years,
                "scoring_champs": len(scoring_years),
                "scoring_champ_years": scoring_years,
                "is_defending_champion": bool(mgr.id == defending_champ_mgr_id),
                "weekly_history": season_history,
            }
        )

    # Sort for official standings rank (win_pct desc, wins desc, points_for desc)
    sorted_by_standings = sorted(
        entries,
        key=lambda e: (-e["win_pct"], -e["wins"], -e["points_for"]),
    )
    for idx, e in enumerate(sorted_by_standings, start=1):
        e["rank"] = idx

    # Sort for power rank (all_play_win_pct desc, median_wins desc, points_for desc)
    sorted_by_power = sorted(
        entries,
        key=lambda e: (-e["all_play_win_pct"], -e["median_wins"], -e["points_for"]),
    )
    for idx, e in enumerate(sorted_by_power, start=1):
        e["power_rank"] = idx

    # Clean temporary helper key
    for e in entries:
        e.pop("win_pct", None)

    return {
        "season_year": None,
        "is_active": False,
        "is_completed": True,
        "current_week": 0,
        "regular_season_weeks": 14,
        "playoff_team_count": 6,
        "defending_champion_manager_id": defending_champ_mgr_id,
        "defending_champion_team_id": None,
        "playoff_bracket": None,
        "standings": sorted_by_standings,
    }
