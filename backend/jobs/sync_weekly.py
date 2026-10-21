"""backend/jobs/sync_weekly.py - Incremental Active-Season Rolling Window Sync Job.

Purpose:
    Lightweight cron worker syncing only the active season (is_active = TRUE) over a 2-week rolling window
    (current_week - 1 and current_week). Reconciles earnings ledger against official Elias/NFL stat
    corrections, syncs player lineups and transactions for the window, auto-completes season at championship
    finalization, and performs zero network calls during offseason.

Execution:
    python3 -m backend.jobs.sync_weekly [--week N] [--league-id ID]
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.database import get_session
from backend.jobs.deep_parsers import (
    upsert_players_from_payload,
    upsert_transactions_from_payload,
    upsert_weekly_lineups_from_payload,
)
from backend.jobs.espn_client import EspnClient, get_configured_league_ids
from backend.jobs.ledger_reconciler import reconcile_podium_ledger, reconcile_week_ledger
from backend.jobs.parsers import (
    load_manager_overrides,
    resolve_or_upsert_managers,
    upsert_matchups_from_payload,
    upsert_season_from_payload,
    upsert_teams_from_payload,
)
from backend.models.matchup import Matchup
from backend.models.raw_snapshot import RawEspnSnapshot
from backend.models.season import Season
from backend.models.sync_run import SyncRun
from backend.models.team import Team

logger = logging.getLogger(__name__)


def sync_weekly(
    session: Session,
    week: int | None = None,
    client: EspnClient | None = None,
    league_id: str | None = None,
) -> SyncRun:
    """Execute active-season incremental sync over a 2-week rolling window.

    Args:
        session: Active SQLAlchemy session.
        week: Optional explicit week override.
        client: Optional injected EspnClient instance.
        league_id: Optional league ID override.

    Returns:
        The created SyncRun audit record.
    """
    started_at = datetime.now(UTC)

    # 1. Query ONLY the active season
    active_season = (
        session.query(Season)
        .filter_by(is_active=True)
        .first()
    )

    if not active_season or active_season.is_completed:
        logger.info(
            "Offseason no-op: No active uncompleted season found. "
            "Exiting immediately with 0 ESPN API calls."
        )
        noop_run = SyncRun(
            run_type="WEEKLY_CRON",
            season_year=active_season.season_year if active_season else None,
            week_range=None,
            status="NOOP_OFFSEASON",
            records_processed=0,
            error_message="Offseason: No active uncompleted season found",
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )
        session.add(noop_run)
        session.flush()
        return noop_run

    # 2. Determine 2-week rolling window
    if week is not None:
        weeks_to_sync = [week]
    else:
        cur_w = active_season.current_week
        weeks_to_sync = sorted(list({max(1, cur_w - 1), cur_w}))

    week_range_str = (
        f"{weeks_to_sync[0]}-{weeks_to_sync[-1]}"
        if len(weeks_to_sync) > 1
        else str(weeks_to_sync[0])
    )

    logger.info(
        "Syncing active season %d over rolling window %s...",
        active_season.season_year,
        week_range_str,
    )

    # 3. Fetch active season data from ESPN API (or local snapshot fallback if offline)
    espn_client = client or EspnClient(league_id=league_id or active_season.league_id)
    views = [
        "mSettings",
        "mTeam",
        "mMatchupScore",
        "mStatus",
        "mRoster",
        "mBoxscore",
        "mTransactions2",
    ]

    payload = None
    try:
        payload = espn_client.fetch_league(
            season_year=active_season.season_year,
            views=views,
            allow_inaccessible=True,
            league_id=league_id or active_season.league_id,
        )
    except Exception as exc:
        logger.warning(
            "Network error querying ESPN API (%s). Checking local snapshot fallback...",
            exc,
        )

    if payload is None:
        # Check raw_espn_snapshots fallback for offline development / verification
        snap = (
            session.query(RawEspnSnapshot)
            .filter_by(season_year=active_season.season_year)
            .first()
        )
        if snap and isinstance(snap.payload, dict):
            logger.info("Using local snapshot for active season %d.", active_season.season_year)
            payload = snap.payload
        else:
            err_msg = f"Failed to retrieve data for active season {active_season.season_year}."
            logger.error(err_msg)
            fail_run = SyncRun(
                run_type="WEEKLY_CRON",
                season_year=active_season.season_year,
                week_range=week_range_str,
                status="FAILED",
                records_processed=0,
                error_message=err_msg,
                started_at=started_at,
                completed_at=datetime.now(UTC),
            )
            session.add(fail_run)
            session.flush()
            return fail_run

    # Save / update snapshot
    snap_record = (
        session.query(RawEspnSnapshot)
        .filter_by(season_year=active_season.season_year, view_name="mCombined", scoring_period=0)
        .first()
    )
    if snap_record:
        snap_record.payload = payload
    else:
        session.add(
            RawEspnSnapshot(
                season_year=active_season.season_year,
                view_name="mCombined",
                scoring_period=0,
                payload=payload,
            )
        )

    # Upsert updated standings and matchups
    overrides_data = load_manager_overrides()
    mgr_map = resolve_or_upsert_managers(session, payload, overrides_data)
    season = upsert_season_from_payload(session, payload, league_id=active_season.league_id)
    team_map = upsert_teams_from_payload(session, season, payload, mgr_map, overrides_data)
    upsert_matchups_from_payload(session, season, payload, team_map)

    # Upsert players, lineups and transactions restricted to the rolling window
    upsert_players_from_payload(session, payload)
    upsert_weekly_lineups_from_payload(
        session, season, payload, team_map, weeks=weeks_to_sync
    )
    upsert_transactions_from_payload(
        session,
        season,
        payload,
        team_map,
        weeks=weeks_to_sync,
        scoring_periods=weeks_to_sync,
    )

    # 4. Reconcile weekly ledger entries for the rolling window
    reconciled_count = 0
    for w in weeks_to_sync:
        entries = reconcile_week_ledger(session, season, w)
        reconciled_count += len(entries)

    # 5. Championship auto-completion transition
    # Check if final championship matchup is completed
    champ_matchup = (
        session.query(Matchup)
        .filter(
            Matchup.season_year == season.season_year,
            Matchup.matchup_type == "WINNERS_BRACKET",
            Matchup.week > season.regular_season_weeks,
            Matchup.is_completed == True,  # noqa: E712
        )
        .order_by(Matchup.week.desc())
        .first()
    )
    # Check if teams have final standing 1 populated
    champ_team = (
        session.query(Team)
        .filter_by(season_year=season.season_year, final_standing=1)
        .first()
    )

    # If championship week completed and champion assigned, or season status has completed
    if (champ_matchup and champ_team) or (season.current_week > 17):
        logger.info(
            "Championship finalized for season %d! Marking is_completed=True, is_active=False.",
            season.season_year,
        )
        season.is_completed = True
        season.is_active = False
        podium_entries = reconcile_podium_ledger(session, season)
        reconciled_count += len(podium_entries)

    sync_run = SyncRun(
        run_type="WEEKLY_CRON",
        season_year=season.season_year,
        week_range=week_range_str,
        status="SUCCESS",
        records_processed=reconciled_count,
        started_at=started_at,
        completed_at=datetime.now(UTC),
    )
    session.add(sync_run)
    session.flush()
    return sync_run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Incremental Active-Season Rolling Window Sync")
    parser.add_argument("--week", type=int, default=None, help="Explicit scoring week to sync")
    parser.add_argument("--league-id", type=str, default=None, help="ESPN League ID")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = parse_args()
    league_ids = [args.league_id] if args.league_id else get_configured_league_ids()
    target_league_id = league_ids[0]

    with get_session() as session:
        run = sync_weekly(
            session=session,
            week=args.week,
            league_id=target_league_id,
        )
        print(f"✅ Sync weekly finished with status={run.status}, processed={run.records_processed} records.")


if __name__ == "__main__":
    main()
    sys.exit(0)
