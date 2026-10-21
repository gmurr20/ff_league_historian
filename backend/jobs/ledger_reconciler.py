"""backend/jobs/ledger_reconciler.py - Idempotent Financial Earnings Ledger Reconciler.

Purpose:
    Maintains financial ledger integrity across regular-season weekly prizes ($10 wins, $5 ties)
    and season championship podium prizes ($600 Champion, $300 Runner-Up, $100 Third Place).
    Guarantees idempotency and cleanly resolves score reversals caused by Elias stat corrections.
"""

from __future__ import annotations

import logging
from collections import defaultdict
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
      - $10.00 to team(s) with highest point total of the week (entry_type='WEEKLY_HIGH_SCORE', split on tie)
      - $10.00 to losing team(s) with highest point total in a loss (entry_type='WEEKLY_HIGH_SCORE_LOSS', split on tie)

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
    if not matchups:
        return []

    # 2. Compute expected payouts: (manager_id, entry_type) -> (team_id, amount, description)
    expected_payouts: dict[tuple[int, str], tuple[int, Decimal, str]] = {}
    tie_amount = (season.weekly_win_payout / Decimal("2.0")).quantize(Decimal("0.01"))
    high_score_payout_val = (
        getattr(season, "weekly_high_score_payout", Decimal("10.00")) or Decimal("10.00")
    )
    high_score_loss_payout_val = (
        getattr(season, "weekly_high_score_loss_payout", Decimal("10.00")) or Decimal("10.00")
    )

    # A. Matchup Wins & Ties
    for m in matchups:
        if m.is_tie:
            h_team = session.get(Team, m.home_team_id)
            a_team = session.get(Team, m.away_team_id) if m.away_team_id else None
            if h_team:
                expected_payouts[(h_team.manager_id, "WEEKLY_TIE")] = (
                    h_team.id,
                    tie_amount,
                    f"Week {week} Regular Season Tie Split",
                )
            if a_team:
                expected_payouts[(a_team.manager_id, "WEEKLY_TIE")] = (
                    a_team.id,
                    tie_amount,
                    f"Week {week} Regular Season Tie Split",
                )
        elif m.winner_team_id:
            w_team = session.get(Team, m.winner_team_id)
            if w_team:
                expected_payouts[(w_team.manager_id, "WEEKLY_WIN")] = (
                    w_team.id,
                    season.weekly_win_payout,
                    f"Week {week} Regular Season Win",
                )

    # B. Highest Point Total for the Week
    team_scores: list[tuple[int, Decimal, int]] = []
    for m in matchups:
        h_team = session.get(Team, m.home_team_id)
        if h_team:
            team_scores.append((h_team.id, m.home_score, h_team.manager_id))
        if m.away_team_id:
            a_team = session.get(Team, m.away_team_id)
            if a_team:
                team_scores.append((a_team.id, m.away_score, a_team.manager_id))

    if team_scores:
        max_score = max(score for _, score, _ in team_scores)
        if max_score > Decimal("0.00"):
            high_score_teams = [
                (tid, mid) for tid, score, mid in team_scores if score == max_score
            ]
            split_count = len(high_score_teams)
            hs_amount = (high_score_payout_val / Decimal(split_count)).quantize(Decimal("0.01"))
            for tid, mid in high_score_teams:
                desc = (
                    f"Week {week} Regular Season High Score ({max_score:.2f} pts)"
                    if split_count == 1
                    else f"Week {week} Regular Season High Score Tie ({max_score:.2f} pts)"
                )
                expected_payouts[(mid, "WEEKLY_HIGH_SCORE")] = (
                    tid,
                    hs_amount,
                    desc,
                )

    # C. Highest Point Total That Lost
    losing_scores: list[tuple[int, Decimal, int]] = []
    for m in matchups:
        if not m.is_tie and m.winner_team_id:
            if m.winner_team_id == m.home_team_id and m.away_team_id:
                l_team = session.get(Team, m.away_team_id)
                if l_team:
                    losing_scores.append((l_team.id, m.away_score, l_team.manager_id))
            elif m.winner_team_id == m.away_team_id:
                l_team = session.get(Team, m.home_team_id)
                if l_team:
                    losing_scores.append((l_team.id, m.home_score, l_team.manager_id))

    if losing_scores:
        max_loss_score = max(score for _, score, _ in losing_scores)
        if max_loss_score > Decimal("0.00"):
            high_loss_teams = [
                (tid, mid) for tid, score, mid in losing_scores if score == max_loss_score
            ]
            loss_split_count = len(high_loss_teams)
            hsl_amount = (high_score_loss_payout_val / Decimal(loss_split_count)).quantize(
                Decimal("0.01")
            )
            for tid, mid in high_loss_teams:
                desc = (
                    f"Week {week} Regular Season Most Points in a Loss ({max_loss_score:.2f} pts)"
                    if loss_split_count == 1
                    else f"Week {week} Regular Season Most Points in a Loss Tie ({max_loss_score:.2f} pts)"
                )
                expected_payouts[(mid, "WEEKLY_HIGH_SCORE_LOSS")] = (
                    tid,
                    hsl_amount,
                    desc,
                )

    # 3. Query existing weekly ledger entries for this week
    weekly_types = [
        "WEEKLY_WIN",
        "WEEKLY_TIE",
        "WEEKLY_HIGH_SCORE",
        "WEEKLY_HIGH_SCORE_LOSS",
    ]
    existing_entries = (
        session.query(EarningsLedger)
        .filter(
            EarningsLedger.season_year == season.season_year,
            EarningsLedger.week == week,
            EarningsLedger.entry_type.in_(weekly_types),
        )
        .all()
    )
    existing_by_key = {(e.manager_id, e.entry_type): e for e in existing_entries}

    # 4. Remove entries that are no longer expected (due to stat correction flips)
    for key, entry in list(existing_by_key.items()):
        if key not in expected_payouts:
            logger.info(
                "Stat correction reconciliation: Deleting reversed %s payout "
                "for manager %d in season %d week %d.",
                entry.entry_type,
                entry.manager_id,
                season.season_year,
                week,
            )
            session.delete(entry)
            del existing_by_key[key]

    if session.deleted:
        session.flush()

    # 5. Add new or update modified entries
    results: list[EarningsLedger] = []
    for (mgr_id, entry_type), (team_id, amount, desc) in expected_payouts.items():
        if (mgr_id, entry_type) in existing_by_key:
            entry = existing_by_key[(mgr_id, entry_type)]
            entry.team_id = team_id
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


PODIUM_CONFIGS: list[tuple[int, str, str, str]] = [
    (1, "CHAMPION", "champion_payout", "League Champion Payout"),
    (2, "RUNNER_UP", "runner_up_payout", "League Runner-Up Payout"),
    (3, "THIRD_PLACE", "third_place_payout", "3rd Place Playoff Payout"),
    (4, "FOURTH_PLACE", "fourth_place_payout", "4th Place Playoff Payout"),
    (5, "FIFTH_PLACE", "fifth_place_payout", "5th Place Playoff Payout"),
]
PODIUM_ENTRY_TYPES: list[str] = [
    "CHAMPION",
    "RUNNER_UP",
    "THIRD_PLACE",
    "FOURTH_PLACE",
    "FIFTH_PLACE",
]


def reconcile_podium_ledger(
    session: Session,
    season: Season,
) -> list[EarningsLedger]:
    """Reconcile playoff placement payouts (1st through 5th place).

    Awards placement prizes (week = None) according to teams.final_standing:
      - 1st -> CHAMPION ($500.00 default)
      - 2nd -> RUNNER_UP ($300.00 default)
      - 3rd -> THIRD_PLACE ($200.00 default)
      - 4th -> FOURTH_PLACE ($150.00 default)
      - 5th -> FIFTH_PLACE ($100.00 default)

    Only applies when season.is_completed == True.

    Args:
        session: Active SQLAlchemy session.
        season: Season entity.

    Returns:
        List of reconciled podium and placement EarningsLedger entries.
    """
    if not season.is_completed:
        # If season is not completed, no podium entries should exist
        session.query(EarningsLedger).filter(
            EarningsLedger.season_year == season.season_year,
            EarningsLedger.week.is_(None),
            EarningsLedger.entry_type.in_(PODIUM_ENTRY_TYPES),
        ).delete(synchronize_session=False)
        session.flush()
        return []

    teams = session.query(Team).filter_by(season_year=season.season_year).all()
    standing_to_team = {
        t.final_standing: t for t in teams if t.final_standing in (1, 2, 3, 4, 5)
    }

    expected_podium: list[tuple[int, int, str, Decimal, str]] = []
    for standing, entry_type, attr_name, desc_suffix in PODIUM_CONFIGS:
        payout = getattr(season, attr_name, Decimal("0.00")) or Decimal("0.00")
        if standing in standing_to_team and payout > Decimal("0.00"):
            t = standing_to_team[standing]
            expected_podium.append((
                t.manager_id,
                t.id,
                entry_type,
                payout,
                f"{season.season_year} {desc_suffix}",
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
            EarningsLedger.entry_type.in_(PODIUM_ENTRY_TYPES),
        )
        .all()
    )
    existing_by_type = {e.entry_type: e for e in existing_podium}

    for entry_type, entry in list(existing_by_type.items()):
        if entry_type not in expected_map:
            session.delete(entry)
            del existing_by_type[entry_type]

    if session.deleted:
        session.flush()

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


def reconcile_regular_season_points_ledger(
    session: Session,
    season: Season,
) -> list[EarningsLedger]:
    """Reconcile the regular-season most points payout ($30.00 default).

    Evaluates total points scored across all completed regular season matchups
    (week <= season.regular_season_weeks, matchup_type == 'REGULAR').

    Playoffs start week 15, so regular season ending won't happen until after week 14:
    This prize is only awarded when:
      1. completed regular season matchups exist up through regular_season_weeks,
      2. there are zero incomplete regular season matchups, and
      3. season.current_week > season.regular_season_weeks or season.is_completed == True.

    If regular season is not yet ended, removes any existing REGULAR_SEASON_MOST_POINTS entries.
    If multiple teams tie for most points, the prize is split equally.

    Args:
        session: Active SQLAlchemy session.
        season: Season entity.

    Returns:
        List of reconciled regular-season points EarningsLedger entries.
    """
    most_points_payout = (
        getattr(season, "regular_season_most_points_payout", Decimal("0.00")) or Decimal("0.00")
    )
    if most_points_payout <= Decimal("0.00"):
        # If this season has 0.00 for regular season most points (e.g. legacy historical seasons), clean up
        session.query(EarningsLedger).filter(
            EarningsLedger.season_year == season.season_year,
            EarningsLedger.week.is_(None),
            EarningsLedger.entry_type == "REGULAR_SEASON_MOST_POINTS",
        ).delete(synchronize_session=False)
        session.flush()
        return []

    reg_matchups = (
        session.query(Matchup)
        .filter(
            Matchup.season_year == season.season_year,
            Matchup.matchup_type == "REGULAR",
            Matchup.week <= season.regular_season_weeks,
        )
        .all()
    )
    if not reg_matchups:
        return []

    # Check if all regular season weeks up to regular_season_weeks are completed
    max_reg_week = max(m.week for m in reg_matchups)
    all_completed = all(m.is_completed for m in reg_matchups)
    regular_season_ended = (
        max_reg_week >= season.regular_season_weeks
        and all_completed
        and (season.current_week > season.regular_season_weeks or season.is_completed)
    )

    if not regular_season_ended:
        session.query(EarningsLedger).filter(
            EarningsLedger.season_year == season.season_year,
            EarningsLedger.week.is_(None),
            EarningsLedger.entry_type == "REGULAR_SEASON_MOST_POINTS",
        ).delete(synchronize_session=False)
        session.flush()
        return []

    # Calculate total regular season points scored per team
    team_points: dict[int, Decimal] = defaultdict(Decimal)
    for m in reg_matchups:
        team_points[m.home_team_id] += m.home_score
        if m.away_team_id:
            team_points[m.away_team_id] += m.away_score

    if not team_points:
        return []

    max_pts = max(team_points.values())
    if max_pts <= Decimal("0.00"):
        return []

    winning_team_ids = [tid for tid, pts in team_points.items() if pts == max_pts]
    split_count = len(winning_team_ids)
    amount_per_team = (most_points_payout / Decimal(split_count)).quantize(Decimal("0.01"))

    expected: list[tuple[int, int, Decimal, str]] = []
    for tid in winning_team_ids:
        t = session.get(Team, tid)
        if t:
            desc = (
                f"{season.season_year} Regular Season Most Points ({max_pts:.2f} pts)"
                if split_count == 1
                else f"{season.season_year} Regular Season Most Points Tie ({max_pts:.2f} pts)"
            )
            expected.append((t.manager_id, t.id, amount_per_team, desc))

    existing = (
        session.query(EarningsLedger)
        .filter(
            EarningsLedger.season_year == season.season_year,
            EarningsLedger.week.is_(None),
            EarningsLedger.entry_type == "REGULAR_SEASON_MOST_POINTS",
        )
        .all()
    )
    existing_by_mgr = {e.manager_id: e for e in existing}
    expected_mgr_ids = {mgr_id for mgr_id, _, _, _ in expected}

    for mgr_id, entry in list(existing_by_mgr.items()):
        if mgr_id not in expected_mgr_ids:
            session.delete(entry)
            del existing_by_mgr[mgr_id]

    if session.deleted:
        session.flush()

    results: list[EarningsLedger] = []
    for mgr_id, tid, amt, desc in expected:
        if mgr_id in existing_by_mgr:
            entry = existing_by_mgr[mgr_id]
            entry.team_id = tid
            entry.amount = amt
            entry.description = desc
            results.append(entry)
        else:
            new_entry = EarningsLedger(
                manager_id=mgr_id,
                team_id=tid,
                season_year=season.season_year,
                week=None,
                entry_type="REGULAR_SEASON_MOST_POINTS",
                amount=amt,
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
    """Reconcile entire season earnings: weekly prizes, regular season most points, and podium prizes.

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

    # Reconcile regular season most points (if regular season ended)
    reg_pts = reconcile_regular_season_points_ledger(session, season)
    all_entries.extend(reg_pts)

    if season.is_completed:
        podium = reconcile_podium_ledger(session, season)
        all_entries.extend(podium)

    return all_entries
