"""backend/services/earnings_service.py - Financial Earnings Leaderboard Service.

Purpose:
    Computes all-time and single-season financial bankrolls per manager,
    aggregating regular-season weekly win/tie prizes ($10/$5) and championship
    podium awards (CHAMPION $600, RUNNER_UP $300, THIRD_PLACE $100).
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from backend.models.earnings import EarningsLedger
from backend.models.manager import Manager
from backend.models.season import Season
from backend.models.team import Team
from backend.services.standings_service import _resolve_historical_accolades


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

    # Collect distinct managers to include (managers who have franchises or earnings entries)
    manager_ids = set(manager_teams.keys())

    # Query relevant earnings ledger entries
    ledger_query = session.query(EarningsLedger)
    if season_filter is not None:
        ledger_query = ledger_query.filter(EarningsLedger.season_year == season_filter)
    ledger_entries = ledger_query.all()

    for entry in ledger_entries:
        manager_ids.add(entry.manager_id)

    all_managers = session.query(Manager).filter(Manager.id.in_(manager_ids)).all()
    manager_map = {m.id: m for m in all_managers}

    # Resolve active season and active managers for career/churn tracking
    seasons = session.query(Season).order_by(Season.season_year.desc()).all()
    active_season = next((s for s in seasons if s.is_active), None)
    active_mgr_ids: set[int] = set()
    if active_season:
        active_mgr_ids = {
            t.manager_id for t in active_season.teams if t.manager_id
        } | {
            t.co_manager_id for t in active_season.teams if t.co_manager_id
        }

    # Group ledger entries by (manager_id, season_year)
    ledger_by_manager_season: dict[tuple[int, int], list[EarningsLedger]] = defaultdict(list)
    for entry in ledger_entries:
        ledger_by_manager_season[(entry.manager_id, entry.season_year)].append(entry)

    # Resolve historical titles, podiums, and defending champion
    (
        champions_by_year,
        runner_ups_by_year,
        third_places_by_year,
        scoring_leaders_by_year,
    ) = _resolve_historical_accolades(session)

    # Defending champion is the champion of the most recent completed season prior to this season
    if season_filter is not None:
        prior_completed_years = [
            yr for yr in champions_by_year.keys() if yr < season_filter
        ]
    else:
        prior_completed_years = list(champions_by_year.keys())
    defending_champ_mgr_id: int | None = None
    if prior_completed_years:
        last_champ_year = max(prior_completed_years)
        champ_mids = champions_by_year.get(last_champ_year, set())
        if champ_mids:
            defending_champ_mgr_id = next(iter(champ_mids))

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
        mgr_total_points_title = 0.0
        mgr_weekly_wins = 0
        mgr_weekly_ties = 0
        mgr_high_scores = 0
        mgr_high_score_losses = 0
        mgr_wins_cash = 0.0
        mgr_bonus_cash = 0.0
        mgr_championships = 0
        mgr_runner_ups = 0
        mgr_third_places = 0

        for team in teams_for_mgr:
            year = team.season_year
            entries = ledger_by_manager_season.get((mgr_id, year), [])

            s_weekly = 0.0
            s_podium = 0.0
            s_points_title = 0.0
            s_wins = 0
            s_ties = 0
            s_high_scores = 0
            s_high_score_losses = 0
            s_wins_cash = 0.0
            s_bonus_cash = 0.0
            trophy: str | None = None

            for e in entries:
                amt = float(e.amount)
                if e.entry_type == "WEEKLY_WIN":
                    s_weekly += amt
                    s_wins_cash += amt
                    s_wins += 1
                elif e.entry_type == "WEEKLY_TIE":
                    s_weekly += amt
                    s_wins_cash += amt
                    s_ties += 1
                elif e.entry_type == "WEEKLY_HIGH_SCORE":
                    s_weekly += amt
                    s_bonus_cash += amt
                    s_high_scores += 1
                elif e.entry_type == "WEEKLY_HIGH_SCORE_LOSS":
                    s_weekly += amt
                    s_bonus_cash += amt
                    s_high_score_losses += 1
                elif e.entry_type == "REGULAR_SEASON_MOST_POINTS":
                    s_points_title += amt
                elif e.entry_type in (
                    "CHAMPION",
                    "RUNNER_UP",
                    "THIRD_PLACE",
                    "FOURTH_PLACE",
                    "FIFTH_PLACE",
                ):
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
            s_points_title = round(s_points_title, 2)
            s_total = round(s_weekly + s_podium + s_points_title, 2)
            s_wins_cash = round(s_wins_cash, 2)
            s_bonus_cash = round(s_bonus_cash, 2)

            mgr_total_weekly += s_weekly
            mgr_total_podium += s_podium
            mgr_total_points_title += s_points_title
            mgr_weekly_wins += s_wins
            mgr_weekly_ties += s_ties
            mgr_high_scores += s_high_scores
            mgr_high_score_losses += s_high_score_losses
            mgr_wins_cash += s_wins_cash
            mgr_bonus_cash += s_bonus_cash

            # Extract itemized nuanced bounty receipts for this season
            season_bounties: list[dict[str, Any]] = []
            for e in entries:
                if e.entry_type in ("WEEKLY_HIGH_SCORE", "WEEKLY_HIGH_SCORE_LOSS") and e.week is not None:
                    m_pts = re.search(r"\(([\d\.]+)\s*pts\)", e.description)
                    pts = float(m_pts.group(1)) if m_pts else 0.0
                    season_bounties.append(
                        {
                            "week": e.week,
                            "entry_type": e.entry_type,
                            "amount": round(float(e.amount), 2),
                            "points": pts,
                            "description": e.description,
                        }
                    )
            season_bounties.sort(key=lambda b: b["week"])

            season_breakdowns.append(
                {
                    "season_year": year,
                    "team_name": team.team_name,
                    "logo_url": team.logo_url or mgr.avatar_url,
                    "weekly_earnings": s_weekly,
                    "podium_earnings": s_podium,
                    "points_title_cash": s_points_title,
                    "total_earnings": s_total,
                    "weekly_wins": s_wins,
                    "weekly_ties": s_ties,
                    "weekly_wins_cash": s_wins_cash,
                    "weekly_bonus_cash": s_bonus_cash,
                    "weekly_high_scores": s_high_scores,
                    "weekly_high_score_losses": s_high_score_losses,
                    "bounty_receipts": season_bounties,
                    "final_standing": (
                        team.final_standing
                        if (team.final_standing and team.final_standing > 0)
                        else None
                    ),
                    "trophy": trophy,
                }
            )

        mgr_total_weekly = round(mgr_total_weekly, 2)
        mgr_total_podium = round(mgr_total_podium, 2)
        mgr_total_points_title = round(mgr_total_points_title, 2)
        mgr_total_earnings = round(
            mgr_total_weekly + mgr_total_podium + mgr_total_points_title, 2
        )
        latest_team = teams_for_mgr[0] if teams_for_mgr else None

        # Resolve primary bounty receipts (from the current/selected season if filtered, else latest season)
        primary_bounties: list[dict[str, Any]] = []
        if season_breakdowns:
            primary_bounties = season_breakdowns[0].get("bounty_receipts", [])

        # Resolve manager's historical championship years (up to season_filter if filtered, else all-time)
        if season_filter is not None:
            mgr_champ_years = sorted(
                yr
                for yr, mids in champions_by_year.items()
                if (
                    mgr.id in mids
                    or any(
                        t.co_manager_id == mgr.id
                        for t in manager_teams.get(mgr.id, [])
                        if t.season_year == yr
                    )
                )
                and yr <= season_filter
            )
        else:
            mgr_champ_years = sorted(
                yr
                for yr, mids in champions_by_year.items()
                if (
                    mgr.id in mids
                    or any(
                        t.co_manager_id == mgr.id
                        for t in manager_teams.get(mgr.id, [])
                        if t.season_year == yr
                    )
                )
            )

        is_defending_champ = bool(
            defending_champ_mgr_id is not None
            and mgr.id == defending_champ_mgr_id
        )

        is_mgr_active = bool(mgr.is_active and (not active_season or mgr.id in active_mgr_ids))

        leaderboard.append(
            {
                "manager_id": mgr.id,
                "display_name": mgr.display_name,
                "team_name": latest_team.team_name if latest_team else mgr.display_name,
                "avatar_url": (
                    latest_team.logo_url
                    if latest_team and latest_team.logo_url
                    else mgr.avatar_url
                ),
                "is_active": is_mgr_active,
                "total_earnings": mgr_total_earnings,
                "weekly_earnings": mgr_total_weekly,
                "podium_earnings": mgr_total_podium,
                "points_title_cash": mgr_total_points_title,
                "weekly_wins_count": mgr_weekly_wins,
                "weekly_ties_count": mgr_weekly_ties,
                "weekly_wins_cash": round(mgr_wins_cash, 2),
                "weekly_bonus_cash": round(mgr_bonus_cash, 2),
                "weekly_high_scores_count": mgr_high_scores,
                "weekly_high_score_losses_count": mgr_high_score_losses,
                "bounty_receipts": primary_bounties,
                "championships": len(mgr_champ_years),
                "championship_years": mgr_champ_years,
                "is_defending_champion": is_defending_champ,
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

    for idx, item in enumerate(leaderboard, start=1):
        item["rank"] = idx

    # Build weekly nuanced payouts (week-by-week high score & high loser prizes)
    target_year = season_filter
    if target_year is None:
        latest_s = session.query(Season).order_by(Season.season_year.desc()).first()
        if latest_s is not None:
            target_year = latest_s.season_year

    weekly_nuanced_payouts: list[dict[str, Any]] = []
    if target_year is not None:
        special_entries = (
            session.query(EarningsLedger)
            .filter(
                EarningsLedger.season_year == target_year,
                EarningsLedger.entry_type.in_(["WEEKLY_HIGH_SCORE", "WEEKLY_HIGH_SCORE_LOSS"]),
            )
            .order_by(EarningsLedger.week.desc(), EarningsLedger.entry_type)
            .all()
        )

        by_week: dict[int, dict[str, list[EarningsLedger]]] = defaultdict(lambda: {"hs": [], "hl": []})
        for e in special_entries:
            if e.week is not None:
                if e.entry_type == "WEEKLY_HIGH_SCORE":
                    by_week[e.week]["hs"].append(e)
                elif e.entry_type == "WEEKLY_HIGH_SCORE_LOSS":
                    by_week[e.week]["hl"].append(e)

        def _extract_score(desc: str) -> float:
            m = re.search(r"\(([\d\.]+)\s*pts\)", desc)
            return float(m.group(1)) if m else 0.0

        for week in sorted(by_week.keys(), reverse=True):
            hs_list = by_week[week]["hs"]
            hl_list = by_week[week]["hl"]

            # High score team & score
            if hs_list:
                hs_teams = [session.get(Team, e.team_id) for e in hs_list if e.team_id]
                hs_mgrs = [session.get(Manager, e.manager_id) for e in hs_list if e.manager_id]
                hs_score = _extract_score(hs_list[0].description)
                hs_amount = sum(float(e.amount) for e in hs_list)
                is_tie = len(hs_list) > 1
                hs_team_name = " & ".join(t.team_name for t in hs_teams if t)
                hs_mgr_name = " & ".join(m.display_name for m in hs_mgrs if m)
                hs_avatar = (
                    hs_teams[0].logo_url
                    if hs_teams and hs_teams[0].logo_url
                    else (hs_mgrs[0].avatar_url if hs_mgrs else None)
                )
            else:
                hs_team_name = "-"
                hs_mgr_name = "-"
                hs_avatar = None
                hs_score = 0.0
                hs_amount = 0.0
                is_tie = False

            # High score loss team & score
            if hl_list:
                hl_teams = [session.get(Team, e.team_id) for e in hl_list if e.team_id]
                hl_mgrs = [session.get(Manager, e.manager_id) for e in hl_list if e.manager_id]
                hl_score = _extract_score(hl_list[0].description)
                hl_amount = sum(float(e.amount) for e in hl_list)
                hl_is_tie = len(hl_list) > 1
                hl_team_name = " & ".join(t.team_name for t in hl_teams if t)
                hl_mgr_name = " & ".join(m.display_name for m in hl_mgrs if m)
                hl_avatar = (
                    hl_teams[0].logo_url
                    if hl_teams and hl_teams[0].logo_url
                    else (hl_mgrs[0].avatar_url if hl_mgrs else None)
                )
            else:
                hl_team_name = "-"
                hl_mgr_name = "-"
                hl_avatar = None
                hl_score = 0.0
                hl_amount = 0.0
                hl_is_tie = False

            weekly_nuanced_payouts.append(
                {
                    "week": week,
                    "high_score_team_name": hs_team_name,
                    "high_score_manager_name": hs_mgr_name,
                    "high_score_avatar_url": hs_avatar,
                    "high_score_points": hs_score,
                    "high_score_amount": round(hs_amount, 2),
                    "high_score_is_tie": is_tie,
                    "high_loser_team_name": hl_team_name,
                    "high_loser_manager_name": hl_mgr_name,
                    "high_loser_avatar_url": hl_avatar,
                    "high_loser_points": hl_score,
                    "high_loser_amount": round(hl_amount, 2),
                    "high_loser_is_tie": hl_is_tie,
                }
            )

    # Regular season most points winner (season-level prize)
    points_winner: dict[str, Any] | None = None
    if target_year is not None:
        pts_entries = (
            session.query(EarningsLedger)
            .filter(
                EarningsLedger.season_year == target_year,
                EarningsLedger.entry_type == "REGULAR_SEASON_MOST_POINTS",
            )
            .all()
        )
        if pts_entries:
            pts_teams = [session.get(Team, e.team_id) for e in pts_entries if e.team_id]
            pts_mgrs = [session.get(Manager, e.manager_id) for e in pts_entries if e.manager_id]
            pts_score = _extract_score(pts_entries[0].description or "")
            pts_amount = sum(float(e.amount) for e in pts_entries)
            pts_team_name = " & ".join(t.team_name for t in pts_teams if t)
            pts_mgr_name = " & ".join(m.display_name for m in pts_mgrs if m)
            pts_avatar = (
                pts_teams[0].logo_url
                if pts_teams and pts_teams[0].logo_url
                else (pts_mgrs[0].avatar_url if pts_mgrs else None)
            )
            points_winner = {
                "manager_id": pts_entries[0].manager_id,
                "manager_name": pts_mgr_name,
                "team_id": pts_entries[0].team_id,
                "team_name": pts_team_name,
                "avatar_url": pts_avatar,
                "points": pts_score,
                "amount": round(pts_amount, 2),
                "is_tie": len(pts_entries) > 1,
                "description": (
                    pts_entries[0].description
                    or f"{target_year} Regular Season Most Points"
                ),
            }

    return {
        "season_filter": season_filter,
        "weekly_win_value": weekly_win_value,
        "leaderboard": leaderboard,
        "weekly_nuanced_payouts": weekly_nuanced_payouts,
        "regular_season_points_winner": points_winner,
    }
