"""backend/jobs/sync_live_scores.py - Lightweight 10-Minute Live In-Week Score & Boxscore Sync Job.

Purpose:
    Purpose-built for a 10-minute cron (*/10 * * * 0,1,4,6 on NFL game days) or manual trigger.
    Queries ONLY the active season (is_active = TRUE) and performs a single lightweight ESPN fetch
    with views=["mBoxscore", "mMatchupScore"] for target_week (defaults to active_season.current_week).
    Updates matchups, players, and weekly_lineups for target_week without fetching transactions,
    communication topics, draft picks, or media assets, and without reconciling earnings_ledger.

Execution:
    python3 -m backend.jobs.sync_live_scores [--week N] [--league-id ID]
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from backend.database import get_session, init_db
from backend.jobs.deep_parsers import (
    upsert_players_from_payload,
    upsert_weekly_lineups_from_payload,
)
from backend.jobs.espn_client import EspnClient, get_configured_league_ids
from backend.jobs.parsers import (
    load_manager_overrides,
    resolve_or_upsert_managers,
    upsert_matchups_from_payload,
    upsert_teams_from_payload,
)
from backend.models.raw_snapshot import RawEspnSnapshot
from backend.models.season import Season
from backend.models.sync_run import SyncRun
from backend.models.team import Team

logger = logging.getLogger(__name__)


def sync_live_scores(
    session: Session,
    week: int | None = None,
    client: EspnClient | None = None,
    league_id: str | None = None,
) -> SyncRun:
    """Execute lightweight live score and player boxscore sync for a single week of the active season.

    Args:
        session: Active SQLAlchemy session.
        week: Optional explicit scoring week override (defaults to active_season.current_week).
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
            run_type="LIVE_SCORES",
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

    # 2. Determine target week
    target_week = int(week if week is not None else (active_season.current_week or 1))
    target_league_id = league_id or active_season.league_id

    logger.info(
        "Syncing live scores for active season %d week %d...",
        active_season.season_year,
        target_week,
    )

    # 3. Single lightweight ESPN fetch (or local snapshot fallback when offline)
    espn_client = client or EspnClient(league_id=target_league_id)
    views = ["mBoxscore", "mMatchupScore"]

    payload: dict[str, Any] | None = None
    try:
        payload = espn_client.fetch_league(
            season_year=active_season.season_year,
            views=views,
            allow_inaccessible=True,
            league_id=target_league_id,
            scoring_period_id=target_week,
        )
    except Exception as exc:
        logger.warning(
            "Network error querying ESPN live scores (%s). Checking local snapshot fallback...",
            exc,
        )

    if payload is None:
        # Fallback to RawEspnSnapshot for (season_year, "mBoxscore", target_week) or "mCombined"
        snap = (
            session.query(RawEspnSnapshot)
            .filter_by(
                season_year=active_season.season_year,
                view_name="mBoxscore",
                scoring_period=target_week,
            )
            .first()
        )
        if not snap:
            snap = (
                session.query(RawEspnSnapshot)
                .filter_by(
                    season_year=active_season.season_year,
                    view_name="mCombined",
                )
                .first()
            )
        if not snap:
            snap = (
                session.query(RawEspnSnapshot)
                .filter_by(season_year=active_season.season_year)
                .first()
            )

        if snap and isinstance(snap.payload, dict):
            logger.info(
                "Using local snapshot (%s, period=%s) for season %d week %d.",
                snap.view_name,
                snap.scoring_period,
                active_season.season_year,
                target_week,
            )
            payload = snap.payload
        else:
            err_msg = (
                f"Failed to retrieve live scores for season {active_season.season_year} "
                f"week {target_week}."
            )
            logger.error(err_msg)
            fail_run = SyncRun(
                run_type="LIVE_SCORES",
                season_year=active_season.season_year,
                week_range=str(target_week),
                status="FAILED",
                records_processed=0,
                error_message=err_msg,
                started_at=started_at,
                completed_at=datetime.now(UTC),
            )
            session.add(fail_run)
            session.flush()
            return fail_run

    # 4. Update the RawEspnSnapshot for (season_year, "mBoxscore", target_week)
    box_snap = (
        session.query(RawEspnSnapshot)
        .filter_by(
            season_year=active_season.season_year,
            view_name="mBoxscore",
            scoring_period=target_week,
        )
        .first()
    )
    if box_snap:
        box_snap.payload = payload
        flag_modified(box_snap, "payload")
    else:
        session.add(
            RawEspnSnapshot(
                season_year=active_season.season_year,
                view_name="mBoxscore",
                scoring_period=target_week,
                payload=payload,
            )
        )

    # 5. Build team_map from existing Team rows in DB for active_season.season_year
    existing_teams = (
        session.query(Team)
        .filter_by(season_year=active_season.season_year)
        .all()
    )
    team_map: dict[int, Team] = {t.espn_team_id: t for t in existing_teams}

    if not team_map and payload.get("teams"):
        overrides_data = load_manager_overrides()
        mgr_map = resolve_or_upsert_managers(session, payload, overrides_data)
        team_map = upsert_teams_from_payload(
            session, active_season, payload, mgr_map, overrides_data
        )

    # 6. Update matchups, players, and weekly lineups for target_week only
    upsert_matchups_from_payload(session, active_season, payload, team_map)
    upsert_players_from_payload(session, payload)
    lineups = upsert_weekly_lineups_from_payload(
        session,
        active_season,
        payload,
        team_map,
        weeks=[target_week],
    )

    sync_run = SyncRun(
        run_type="LIVE_SCORES",
        season_year=active_season.season_year,
        week_range=str(target_week),
        status="SUCCESS",
        records_processed=len(lineups),
        started_at=started_at,
        completed_at=datetime.now(UTC),
    )
    session.add(sync_run)
    session.flush()
    return sync_run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lightweight 10-Minute Live In-Week Score & Boxscore Sync"
    )
    parser.add_argument(
        "--week", type=int, default=None, help="Explicit scoring week to sync"
    )
    parser.add_argument(
        "--league-id", type=str, default=None, help="ESPN League ID"
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    args = parse_args()
    league_ids = [args.league_id] if args.league_id else get_configured_league_ids()
    target_league_id = league_ids[0]

    init_db()
    with get_session() as session:
        run = sync_live_scores(
            session=session,
            week=args.week,
            league_id=target_league_id,
        )
        print(
            f"✅ Sync live scores finished with status={run.status}, "
            f"processed={run.records_processed} lineup records."
        )


if __name__ == "__main__":
    main()
    sys.exit(0)
