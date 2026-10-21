"""backend/services/earnings_service.py - Financial Earnings Leaderboard Service.

Purpose:
    Computes all-time and single-season financial bankrolls per manager,
    aggregating regular-season weekly win/tie prizes ($10/$5) and championship
    podium awards (CHAMPION $600, RUNNER_UP $300, THIRD_PLACE $100).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from backend.models.earnings import EarningsLedger
from backend.models.manager import Manager
from backend.models.season import Season
from backend.models.team import Team


def get_earnings_leaderboard(
    session: Session, season_filter: int | None = None
) -> dict[str, Any]:
    """Calculate manager financial earnings, podium counts, and seasonal breakdown."""
    # Resolve weekly win value
    weekly_win_value = 10.0
    if season_filter is not None:
        season = session.query(Season).filter(Season.season_year == season_filter).first()
        if season is not None:
            weekly_win_value = float(season.weekly_win_payout)
    else:
        latest_season = session.query(Season).order_by(Season.season_year.desc()).first()
        if latest_season is not None:
            weekly_win_value = float(latest_season.weekly_win_payout)

    # Resolve managers and franchises
    teams_query = session.query(Team)
    if season_filter is not None:
        teams_query = teams_query.filter(Team.season_year == season_filter)
    all_teams = teams_query.all()

    # Map teams by manager_id
    manager_teams: dict[int, list[Team]] = defaultdict(list)
    for team in all_teams:
        manager_teams[team.manager_id].append(team)

    # Collect distinct managers to include
    manager_ids = set(manager_teams.keys())
    if season_filter is None:
        # Include all managers in the system
        all_managers = session.query(Manager).all()
        for mgr in all_managers:
            manager_ids.add(mgr.id)
    else:
        all_managers = session.query(Manager).filter(Manager.id.in_(manager_ids)).all()

    manager_map = {m.id: m for m in all_managers}

    # Query relevant earnings ledger entries
    ledger_query = session.query(EarningsLedger)
    if season_filter is not None:
        ledger_query = ledger_query.filter(EarningsLedger.season_year == season_filter)
    ledger_entries = ledger_query.all()

    # Group ledger entries by (manager_id, season_year)
    ledger_by_manager_season: dict[tuple[int, int], list[EarningsLedger]] = defaultdict(list)
    for entry in ledger_entries:
        ledger_by_manager_season[(entry.manager_id, entry.season_year)].append(entry)

    leaderboard: list[dict[str, Any]] = []

    for mgr_id in manager_ids:
        mgr = manager_map.get(mgr_id)
        if not mgr:
            continue

        teams_for_mgr = sorted(
            manager_teams.get(mgr_id, []),
            key=lambda t: t.season_year,
            reverse=True,
        )

        season_breakdowns: list[dict[str, Any]] = []
        mgr_total_weekly = 0.0
        mgr_total_podium = 0.0
        mgr_weekly_wins = 0
        mgr_weekly_ties = 0
        mgr_championships = 0
        mgr_runner_ups = 0
        mgr_third_places = 0

        for team in teams_for_mgr:
            year = team.season_year
            entries = ledger_by_manager_season.get((mgr_id, year), [])

            s_weekly = 0.0
            s_podium = 0.0
            s_wins = 0
            s_ties = 0
            trophy: str | None = None

            for e in entries:
                amt = float(e.amount)
                if e.entry_type == "WEEKLY_WIN":
                    s_weekly += amt
                    s_wins += 1
                elif e.entry_type == "WEEKLY_TIE":
                    s_weekly += amt
                    s_ties += 1
                elif e.entry_type in ("CHAMPION", "RUNNER_UP", "THIRD_PLACE"):
                    s_podium += amt
                    if e.entry_type == "CHAMPION":
                        trophy = "CHAMPION"
                    elif e.entry_type == "RUNNER_UP" and trophy != "CHAMPION":
                        trophy = "RUNNER_UP"
                    elif e.entry_type == "THIRD_PLACE" and not trophy:
                        trophy = "THIRD_PLACE"

            # Check final standing if trophy was not yet resolved from ledger
            if trophy is None and team.final_standing is not None:
                if team.final_standing == 1:
                    trophy = "CHAMPION"
                elif team.final_standing == 2:
                    trophy = "RUNNER_UP"
                elif team.final_standing == 3:
                    trophy = "THIRD_PLACE"

            if trophy == "CHAMPION":
                mgr_championships += 1
            elif trophy == "RUNNER_UP":
                mgr_runner_ups += 1
            elif trophy == "THIRD_PLACE":
                mgr_third_places += 1

            s_weekly = round(s_weekly, 2)
            s_podium = round(s_podium, 2)
            s_total = round(s_weekly + s_podium, 2)

            mgr_total_weekly += s_weekly
            mgr_total_podium += s_podium
            mgr_weekly_wins += s_wins
            mgr_weekly_ties += s_ties

            season_breakdowns.append(
                {
                    "season_year": year,
                    "team_name": team.team_name,
                    "weekly_earnings": s_weekly,
                    "podium_earnings": s_podium,
                    "total_earnings": s_total,
                    "weekly_wins": s_wins,
                    "weekly_ties": s_ties,
                    "final_standing": team.final_standing,
                    "trophy": trophy,
                }
            )

        mgr_total_weekly = round(mgr_total_weekly, 2)
        mgr_total_podium = round(mgr_total_podium, 2)
        mgr_total_earnings = round(mgr_total_weekly + mgr_total_podium, 2)

        leaderboard.append(
            {
                "manager_id": mgr.id,
                "display_name": mgr.display_name,
                "total_earnings": mgr_total_earnings,
                "weekly_earnings": mgr_total_weekly,
                "podium_earnings": mgr_total_podium,
                "weekly_wins_count": mgr_weekly_wins,
                "weekly_ties_count": mgr_weekly_ties,
                "championships": mgr_championships,
                "runner_ups": mgr_runner_ups,
                "third_places": mgr_third_places,
                "seasons_played": len(teams_for_mgr),
                "season_breakdown": season_breakdowns,
            }
        )

    # Sort leaderboard by total_earnings DESC, championships DESC, weekly_wins_count DESC, display_name ASC
    leaderboard.sort(
        key=lambda x: (
            -x["total_earnings"],
            -x["championships"],
            -x["weekly_wins_count"],
            x["display_name"].lower(),
        )
    )

    return {
        "season_filter": season_filter,
        "weekly_win_value": weekly_win_value,
        "leaderboard": leaderboard,
    }
