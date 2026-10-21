"""backend/jobs/ledger_reconciler.py - Idempotent Financial Earnings Ledger Reconciler.

Purpose:
    Maintains financial ledger integrity across regular-season weekly prizes ($10 wins, $5 ties)
    and season championship podium prizes ($600 Champion, $300 Runner-Up, $100 Third Place).
    Guarantees idempotency and cleanly resolves score reversals caused by Elias stat corrections.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy.orm import Session

from backend.models.earnings import EarningsLedger
from backend.models.matchup import Matchup
from backend.models.season import Season
from backend.models.team import Team

logger = logging.getLogger(__name__)


def reconcile_week_ledger(
    session: Session,
    season: Season,
    week: int,
) -> list[EarningsLedger]:
    """Reconcile financial ledger entries for a single regular season week.

    Awards:
      - $10.00 to winning manager (entry_type='WEEKLY_WIN')
      - $5.00 each to tied managers (entry_type='WEEKLY_TIE')
    Idempotently deletes or updates any stale/reversed payouts caused by
    official Elias Sports Bureau stat corrections.

    Args:
        session: Active SQLAlchemy session.
        season: Season entity.
        week: Scoring period week number.

    Returns:
        List of reconciled EarningsLedger records for the week.
    """
    if week > season.regular_season_weeks:
        return []

    # 1. Query all completed regular season matchups for this week
    matchups = (
        session.query(Matchup)
        .filter(
            Matchup.season_year == season.season_year,
            Matchup.week == week,
            Matchup.matchup_type == "REGULAR",
            Matchup.is_completed == True,  # noqa: E712
        )
        .all()
    )

    # 2. Compute expected payouts: manager_id -> (team_id, entry_type, amount, description)
    expected_payouts: dict[int, tuple[int, str, Decimal, str]] = {}
    tie_amount = (season.weekly_win_payout / Decimal("2.0")).quantize(Decimal("0.01"))

    for m in matchups:
        if m.is_tie:
            h_team = session.get(Team, m.home_team_id)
            a_team = session.get(Team, m.away_team_id) if m.away_team_id else None
            if h_team:
                expected_payouts[h_team.manager_id] = (
                    h_team.id,
                    "WEEKLY_TIE",
                    tie_amount,
                    f"Week {week} Regular Season Tie Split",
                )
            if a_team:
                expected_payouts[a_team.manager_id] = (
                    a_team.id,
                    "WEEKLY_TIE",
                    tie_amount,
                    f"Week {week} Regular Season Tie Split",
                )
        elif m.winner_team_id:
            w_team = session.get(Team, m.winner_team_id)
            if w_team:
                expected_payouts[w_team.manager_id] = (
                    w_team.id,
                    "WEEKLY_WIN",
                    season.weekly_win_payout,
                    f"Week {week} Regular Season Win",
                )

    # 3. Query existing weekly ledger entries for this week
    existing_entries = (
        session.query(EarningsLedger)
        .filter(
            EarningsLedger.season_year == season.season_year,
            EarningsLedger.week == week,
            EarningsLedger.entry_type.in_(["WEEKLY_WIN", "WEEKLY_TIE"]),
        )
        .all()
    )
    existing_by_manager = {e.manager_id: e for e in existing_entries}

    # 4. Remove entries for managers who no longer won/tied (due to stat correction flip)
    for mgr_id, entry in list(existing_by_manager.items()):
        if mgr_id not in expected_payouts:
            logger.info(
                "Stat correction reconciliation: Deleting reversed %s payout "
                "for manager %d in season %d week %d.",
                entry.entry_type,
                mgr_id,
                season.season_year,
                week,
            )
            session.delete(entry)
            del existing_by_manager[mgr_id]

    # 5. Add new or update modified entries
    results: list[EarningsLedger] = []
    for mgr_id, (team_id, entry_type, amount, desc) in expected_payouts.items():
        if mgr_id in existing_by_manager:
            entry = existing_by_manager[mgr_id]
            entry.team_id = team_id
            entry.entry_type = entry_type
            entry.amount = amount
            entry.description = desc
            results.append(entry)
        else:
            new_entry = EarningsLedger(
                manager_id=mgr_id,
                team_id=team_id,
                season_year=season.season_year,
                week=week,
                entry_type=entry_type,
                amount=amount,
                description=desc,
            )
            session.add(new_entry)
            results.append(new_entry)

    session.flush()
    return results


def reconcile_podium_ledger(
    session: Session,
    season: Season,
) -> list[EarningsLedger]:
    """Reconcile championship podium payouts (CHAMPION, RUNNER_UP, THIRD_PLACE).

    Awards podium prizes (week = None) according to teams.final_standing:
      - 1st -> CHAMPION ($600.00)
      - 2nd -> RUNNER_UP ($300.00)
      - 3rd -> THIRD_PLACE ($100.00)
    Only applies when season.is_completed == True.

    Args:
        session: Active SQLAlchemy session.
        season: Season entity.

    Returns:
        List of reconciled podium EarningsLedger entries.
    """
    if not season.is_completed:
        # If season is not completed, no podium entries should exist
        session.query(EarningsLedger).filter(
            EarningsLedger.season_year == season.season_year,
            EarningsLedger.week.is_(None),
            EarningsLedger.entry_type.in_(["CHAMPION", "RUNNER_UP", "THIRD_PLACE"]),
        ).delete(synchronize_session=False)
        session.flush()
        return []

    teams = session.query(Team).filter_by(season_year=season.season_year).all()
    standing_to_team = {t.final_standing: t for t in teams if t.final_standing in (1, 2, 3)}

    expected_podium: list[tuple[int, int, str, Decimal, str]] = []
    if 1 in standing_to_team:
        t = standing_to_team[1]
        expected_podium.append((
            t.manager_id,
            t.id,
            "CHAMPION",
            season.champion_payout,
            f"{season.season_year} League Champion Payout",
        ))
    if 2 in standing_to_team:
        t = standing_to_team[2]
        expected_podium.append((
            t.manager_id,
            t.id,
            "RUNNER_UP",
            season.runner_up_payout,
            f"{season.season_year} League Runner-Up Payout",
        ))
    if 3 in standing_to_team:
        t = standing_to_team[3]
        expected_podium.append((
            t.manager_id,
            t.id,
            "THIRD_PLACE",
            season.third_place_payout,
            f"{season.season_year} 3rd Place Playoff Payout",
        ))

    expected_map = {
        entry_type: (mgr_id, team_id, amount, desc)
        for mgr_id, team_id, entry_type, amount, desc in expected_podium
    }

    existing_podium = (
        session.query(EarningsLedger)
        .filter(
            EarningsLedger.season_year == season.season_year,
            EarningsLedger.week.is_(None),
            EarningsLedger.entry_type.in_(["CHAMPION", "RUNNER_UP", "THIRD_PLACE"]),
        )
        .all()
    )
    existing_by_type = {e.entry_type: e for e in existing_podium}

    for entry_type, entry in list(existing_by_type.items()):
        if entry_type not in expected_map:
            session.delete(entry)
            del existing_by_type[entry_type]

    results: list[EarningsLedger] = []
    for entry_type, (mgr_id, team_id, amount, desc) in expected_map.items():
        if entry_type in existing_by_type:
            entry = existing_by_type[entry_type]
            entry.manager_id = mgr_id
            entry.team_id = team_id
            entry.amount = amount
            entry.description = desc
            results.append(entry)
        else:
            new_entry = EarningsLedger(
                manager_id=mgr_id,
                team_id=team_id,
                season_year=season.season_year,
                week=None,
                entry_type=entry_type,
                amount=amount,
                description=desc,
            )
            session.add(new_entry)
            results.append(new_entry)

    session.flush()
    return results


def reconcile_season_ledger(
    session: Session,
    season: Season,
) -> list[EarningsLedger]:
    """Reconcile entire season earnings: regular season weekly prizes and podium prizes.

    Args:
        session: Active SQLAlchemy session.
        season: Season entity.

    Returns:
        List of all reconciled EarningsLedger records for the season.
    """
    all_entries: list[EarningsLedger] = []
    for week in range(1, season.regular_season_weeks + 1):
        entries = reconcile_week_ledger(session, season, week)
        all_entries.extend(entries)

    if season.is_completed:
        podium = reconcile_podium_ledger(session, season)
        all_entries.extend(podium)

    return all_entries
