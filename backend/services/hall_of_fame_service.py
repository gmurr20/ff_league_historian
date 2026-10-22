"""backend/services/hall_of_fame_service.py - Hall of Fame & Championship Legends Query Service.

Purpose:
    Computes all-time championship banners and the featured champion's spotlight,
    highlighting the title-winning franchise and their top 4 performing players with photos and stats.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.models.earnings import EarningsLedger
from backend.models.lineup import WeeklyLineup
from backend.models.manager import Manager
from backend.models.matchup import Matchup
from backend.models.player import Player
from backend.models.season import Season
from backend.models.team import Team

ROLE_TITLES = [
    "TITLE GAME MVP",
    "TOP SCORER",
    "KEY STARTER",
    "KEY STARTER",
]


def _format_stats_summary(stats: dict[str, Any], points: float) -> str:
    """Format player boxscore statistics into a concise highlight string."""
    parts: list[str] = []
    tds = stats.get("touchdowns")
    if tds is not None and tds > 0:
        parts.append(f"{tds} TD{'s' if tds > 1 else ''}")
    pass_yds = stats.get("passing_yards")
    if pass_yds is not None and pass_yds > 0:
        parts.append(f"{pass_yds} Pass Yds")
    rush_yds = stats.get("rushing_yards")
    if rush_yds is not None and rush_yds > 0:
        parts.append(f"{rush_yds} Rush Yds")
    rec_yds = stats.get("receiving_yards")
    if rec_yds is not None and rec_yds > 0:
        parts.append(f"{rec_yds} Rec Yds")
    rec = stats.get("receptions")
    if rec is not None and rec > 0:
        parts.append(f"{rec} Rec")

    if parts:
        return " • ".join(parts[:2])
    return f"{points:.2f} Fantasy Pts"


def get_hall_of_fame(
    session: Session,
    season_year: int | None = None,
) -> dict[str, Any]:
    """Retrieve all-time championship banners and the featured Hall of Fame champion."""
    # 1. Fetch completed seasons ordered chronologically ascending for induction numbers
    completed_seasons = (
        session.query(Season)
        .filter(Season.is_completed.is_(True))
        .order_by(Season.season_year.asc())
        .all()
    )

    # If no completed seasons exist, fall back to all seasons
    all_seasons = session.query(Season).order_by(Season.season_year.asc()).all()
    target_seasons = completed_seasons if completed_seasons else all_seasons

    # Build map of season_year -> induction number (e.g. 2022 -> 1, 2023 -> 2)
    hof_numbers: dict[int, int] = {
        s.season_year: idx + 1 for idx, s in enumerate(target_seasons)
    }

    # Pre-fetch all managers and teams for quick lookups
    managers = session.query(Manager).all()
    manager_map = {m.id: m for m in managers}

    teams = session.query(Team).all()
    team_map = {t.id: t for t in teams}

    # Pre-fetch earnings by (season_year, team_id)
    earnings = session.query(EarningsLedger).all()
    earnings_by_team_season: dict[tuple[int, int], float] = {}
    for e in earnings:
        key = (e.season_year, e.team_id)
        earnings_by_team_season[key] = earnings_by_team_season.get(key, 0.0) + float(e.amount)

    # 2. Extract banners for all completed seasons
    banners: list[dict[str, Any]] = []
    season_champions: dict[int, dict[str, Any]] = {}

    for season in target_seasons:
        year = season.season_year

        # 1. Identify champion team: Team with final_standing == 1, or CHAMPION earnings entry
        champ_team = next(
            (t for t in teams if t.season_year == year and t.final_standing == 1),
            None,
        )
        if not champ_team:
            # Fallback to earnings ledger
            champ_earnings = (
                session.query(EarningsLedger)
                .filter(
                    EarningsLedger.season_year == year,
                    EarningsLedger.entry_type == "CHAMPION",
                )
                .first()
            )
            if champ_earnings:
                champ_team = team_map.get(champ_earnings.team_id)

        if not champ_team:
            continue

        # 2. Find the championship matchup involving the champion team in WINNERS_BRACKET
        champ_matchup = (
            session.query(Matchup)
            .filter(
                Matchup.season_year == year,
                Matchup.matchup_type == "WINNERS_BRACKET",
                Matchup.is_completed.is_(True),
                (Matchup.home_team_id == champ_team.id) | (Matchup.away_team_id == champ_team.id),
            )
            .order_by(Matchup.week.desc(), Matchup.id.desc())
            .first()
        )

        runner_up_team: Team | None = None
        winning_score = 0.0
        runner_up_score = 0.0
        champ_week = season.regular_season_weeks + 3  # default fallback week

        if champ_matchup:
            champ_week = champ_matchup.week
            if champ_matchup.home_team_id == champ_team.id:
                winning_score = float(champ_matchup.home_score)
                runner_up_score = float(champ_matchup.away_score)
                runner_up_team = team_map.get(champ_matchup.away_team_id) if champ_matchup.away_team_id else None
            else:
                winning_score = float(champ_matchup.away_score)
                runner_up_score = float(champ_matchup.home_score)
                runner_up_team = team_map.get(champ_matchup.home_team_id)

        if not runner_up_team:
            runner_up_team = next(
                (t for t in teams if t.season_year == year and t.final_standing == 2),
                None,
            )

        champ_mgr = manager_map.get(champ_team.manager_id)
        co_mgr = manager_map.get(champ_team.co_manager_id) if champ_team.co_manager_id else None
        runner_up_mgr = manager_map.get(runner_up_team.manager_id) if runner_up_team else None

        tot_earnings = round(earnings_by_team_season.get((year, champ_team.id), 0.0), 2)
        margin = round(abs(winning_score - runner_up_score), 2)

        banner_data = {
            "season_year": year,
            "team_id": champ_team.id,
            "team_name": champ_team.team_name,
            "team_abbrev": champ_team.team_abbrev or champ_team.team_name[:3].upper(),
            "logo_url": champ_team.logo_url,
            "manager_id": champ_mgr.id if champ_mgr else champ_team.manager_id,
            "manager_name": champ_mgr.display_name if champ_mgr else "Champion Manager",
            "avatar_url": champ_mgr.avatar_url if champ_mgr else None,
            "co_manager_id": co_mgr.id if co_mgr else None,
            "co_manager_name": co_mgr.display_name if co_mgr else None,
            "wins": champ_team.wins,
            "losses": champ_team.losses,
            "ties": champ_team.ties,
            "points_for": float(champ_team.points_for),
            "points_against": float(champ_team.points_against),
            "regular_season_finish": (
                f"Seed #{champ_team.playoff_seed}" if champ_team.playoff_seed else "1st Place"
            ),
            "championship_score": round(winning_score, 2),
            "runner_up_team_id": runner_up_team.id if runner_up_team else None,
            "runner_up_team_name": runner_up_team.team_name if runner_up_team else "Runner-Up",
            "runner_up_manager_name": runner_up_mgr.display_name if runner_up_mgr else None,
            "runner_up_score": round(runner_up_score, 2),
            "margin_of_victory": margin,
            "total_earnings": tot_earnings,
            "payout_amount": float(season.champion_payout),
        }
        banners.append(banner_data)

        season_champions[year] = {
            "banner": banner_data,
            "champ_matchup_id": champ_matchup.id if champ_matchup else None,
            "champ_week": champ_week,
            "champ_team": champ_team,
            "champ_mgr": champ_mgr,
            "co_mgr": co_mgr,
            "runner_up_team": runner_up_team,
            "runner_up_mgr": runner_up_mgr,
            "winning_score": winning_score,
            "runner_up_score": runner_up_score,
            "margin": margin,
            "season": season,
        }

    # Banners sorted by season_year descending for display in rafters
    banners.sort(key=lambda b: b["season_year"], reverse=True)

    available_seasons = [b["season_year"] for b in banners]
    latest_year = available_seasons[0] if available_seasons else (
        target_seasons[-1].season_year if target_seasons else 2023
    )

    # 3. Determine selected featured champion
    selected_year = season_year if (season_year and season_year in season_champions) else latest_year
    featured_meta = season_champions.get(selected_year)

    featured_champion: dict[str, Any] | None = None
    if featured_meta:
        b = featured_meta["banner"]
        c_team = featured_meta["champ_team"]
        c_mgr = featured_meta["champ_mgr"]
        co_m = featured_meta["co_mgr"]
        r_team = featured_meta["runner_up_team"]
        r_mgr = featured_meta["runner_up_mgr"]
        w_score = featured_meta["winning_score"]
        r_score = featured_meta["runner_up_score"]
        champ_wk = featured_meta["champ_week"]
        hof_num = hof_numbers.get(selected_year, 1)

        # 4. Extract Top 4 Players from the championship game
        top_lineups = (
            session.query(WeeklyLineup, Player)
            .join(Player, WeeklyLineup.player_id == Player.espn_player_id)
            .filter(
                WeeklyLineup.season_year == selected_year,
                WeeklyLineup.week == champ_wk,
                WeeklyLineup.team_id == c_team.id,
                WeeklyLineup.is_starter.is_(True),
            )
            .order_by(WeeklyLineup.actual_points.desc())
            .limit(4)
            .all()
        )

        # Fallback: if championship week has no starter boxscores, pull top seasonal starters
        if len(top_lineups) < 4:
            top_lineups = (
                session.query(WeeklyLineup, Player)
                .join(Player, WeeklyLineup.player_id == Player.espn_player_id)
                .filter(
                    WeeklyLineup.season_year == selected_year,
                    WeeklyLineup.team_id == c_team.id,
                    WeeklyLineup.is_starter.is_(True),
                )
                .order_by(WeeklyLineup.actual_points.desc())
                .limit(4)
                .all()
            )

        top_players: list[dict[str, Any]] = []
        for idx, (lineup, player) in enumerate(top_lineups):
            pts = float(lineup.actual_points)
            pct = round((pts / w_score) * 100, 1) if w_score > 0 else 0.0
            role_title = ROLE_TITLES[idx] if idx < len(ROLE_TITLES) else "KEY FACTOR"
            stats_str = _format_stats_summary(lineup.weekly_stats, pts)

            top_players.append(
                {
                    "rank": idx + 1,
                    "player_id": player.espn_player_id,
                    "full_name": player.full_name,
                    "default_position": player.default_position,
                    "pro_team": player.pro_team,
                    "headshot_url": player.headshot_url,
                    "slot_position": lineup.slot_position,
                    "fantasy_points": round(pts, 2),
                    "projected_points": round(float(lineup.projected_points), 2),
                    "stats_summary": stats_str,
                    "role_title": role_title,
                    "pct_of_team_points": pct,
                }
            )

        featured_champion = {
            "season_year": selected_year,
            "team_id": c_team.id,
            "team_name": c_team.team_name,
            "team_abbrev": c_team.team_abbrev or c_team.team_name[:3].upper(),
            "logo_url": c_team.logo_url,
            "manager_id": c_mgr.id if c_mgr else c_team.manager_id,
            "manager_name": c_mgr.display_name if c_mgr else "Champion",
            "avatar_url": c_mgr.avatar_url if c_mgr else None,
            "co_manager_id": co_m.id if co_m else None,
            "co_manager_name": co_m.display_name if co_m else None,
            "regular_season_finish": (
                f"Seed #{c_team.playoff_seed}" if c_team.playoff_seed else "1st Place"
            ),
            "hall_of_fame_number": hof_num,
            "record": f"{c_team.wins}-{c_team.losses}" + (f"-{c_team.ties}" if c_team.ties > 0 else ""),
            "total_earnings": b["total_earnings"],
            "championship_matchup": {
                "week": champ_wk,
                "matchup_id": featured_meta["champ_matchup_id"],
                "winning_score": round(w_score, 2),
                "runner_up_team_id": r_team.id if r_team else None,
                "runner_up_team_name": r_team.team_name if r_team else "Runner-Up",
                "runner_up_manager_name": r_mgr.display_name if r_mgr else None,
                "runner_up_logo_url": r_team.logo_url if r_team else None,
                "runner_up_score": round(r_score, 2),
                "margin_of_victory": round(featured_meta["margin"], 2),
            },
            "top_players": top_players,
        }

    return {
        "reigning_champion_year": latest_year,
        "selected_season": selected_year,
        "available_seasons": available_seasons,
        "banners": banners,
        "featured_champion": featured_champion,
    }
