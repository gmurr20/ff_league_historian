"""backend/jobs/backfill_history.py - One-Time Historical ESPN Ingestion Job.

Purpose:
    Performs full crawl of completed historical seasons or rebuilds from stored
    raw_espn_snapshots in Postgres/SQLite.
    Archives raw ESPN responses into raw_espn_snapshots and populates normalized tables:
      - seasons, managers, teams, matchups, players, weekly_lineups,
        transactions, trades, and earnings_ledger.

Execution:
    python3 -m backend.jobs.backfill_history [--from-snapshots] [--from-year YYYY] [--to-year YYYY] [--league-id ID]
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
    upsert_draft_picks_from_payload,
    upsert_players_from_payload,
    upsert_transactions_from_payload,
    upsert_weekly_lineups_from_payload,
)
from backend.jobs.espn_client import EspnAccessError, EspnClient, get_configured_league_ids
from backend.jobs.ledger_reconciler import reconcile_season_ledger
from backend.jobs.parsers import (
    load_manager_overrides,
    resolve_or_upsert_managers,
    upsert_matchups_from_payload,
    upsert_season_from_payload,
    upsert_teams_from_payload,
)
from backend.models.player import Player
from backend.models.raw_snapshot import RawEspnSnapshot
from backend.models.sync_run import SyncRun

logger = logging.getLogger(__name__)


def backfill_history(
    session: Session,
    from_snapshots: bool = False,
    from_year: int | None = None,
    to_year: int | None = None,
    league_id: str | None = None,
    client: EspnClient | None = None,
) -> SyncRun:
    """Execute historical ingestion job.

    Args:
        session: Active SQLAlchemy session.
        from_snapshots: If True, rebuilds purely from raw_espn_snapshots without network calls.
        from_year: Starting season year (inclusive).
        to_year: Ending season year (inclusive).
        league_id: League ID override.
        client: Optional injected EspnClient instance.

    Returns:
        The created SyncRun audit record.
    """
    started_at = datetime.now(UTC)
    overrides_data = load_manager_overrides()
    records_processed = 0

    if from_snapshots:
        logger.info("Executing historical backfill purely from raw_espn_snapshots archive...")
        # Query distinct season years from raw_espn_snapshots
        query = session.query(RawEspnSnapshot)
        if from_year is not None:
            query = query.filter(RawEspnSnapshot.season_year >= from_year)
        if to_year is not None:
            query = query.filter(RawEspnSnapshot.season_year <= to_year)

        snapshots = query.order_by(RawEspnSnapshot.season_year.asc()).all()
        if not snapshots:
            logger.warning("No snapshots found in raw_espn_snapshots matching criteria.")
            sync_run = SyncRun(
                run_type="BACKFILL",
                season_year=from_year,
                status="SUCCESS",
                records_processed=0,
                started_at=started_at,
                completed_at=datetime.now(UTC),
            )
            session.add(sync_run)
            session.flush()
            return sync_run

        # Group snapshots by season_year
        by_year: dict[int, list[RawEspnSnapshot]] = {}
        for s in snapshots:
            by_year.setdefault(s.season_year, []).append(s)

        for year, year_snaps in sorted(by_year.items()):
            combined: dict[str, Any] = {"seasonId": year}
            for snap in year_snaps:
                if isinstance(snap.payload, dict):
                    if snap.view_name == "mCombined":
                        for k, v in snap.payload.items():
                            if k in ("transactions", "topics") and isinstance(v, list):
                                existing_list = combined.setdefault(k, [])
                                existing_ids = {
                                    str(item.get("id") or item.get("targetId"))
                                    for item in existing_list
                                    if isinstance(item, dict)
                                    and (item.get("id") is not None or item.get("targetId") is not None)
                                }
                                for item in v:
                                    if isinstance(item, dict):
                                        item_id = str(item.get("id") or item.get("targetId"))
                                        if item_id not in existing_ids:
                                            existing_list.append(item)
                                            existing_ids.add(item_id)
                                    else:
                                        existing_list.append(item)
                            else:
                                combined[k] = v
                    else:
                        for k in (
                            "settings",
                            "teams",
                            "members",
                            "schedule",
                            "status",
                            "players",
                            "playerPool",
                            "weekly_lineups",
                            "boxscores",
                            "transactions",
                            "topics",
                            "draftDetail",
                        ):
                            if k in snap.payload:
                                if k in ("transactions", "topics") and isinstance(snap.payload[k], list):
                                    existing_list = combined.setdefault(k, [])
                                    existing_ids = {
                                        str(item.get("id") or item.get("targetId"))
                                        for item in existing_list
                                        if isinstance(item, dict)
                                        and (item.get("id") is not None or item.get("targetId") is not None)
                                    }
                                    for item in snap.payload[k]:
                                        if isinstance(item, dict):
                                            item_id = str(item.get("id") or item.get("targetId"))
                                            if item_id not in existing_ids:
                                                existing_list.append(item)
                                                existing_ids.add(item_id)
                                        else:
                                            existing_list.append(item)
                                else:
                                    combined[k] = snap.payload[k]

            # Parse and upsert season domain entities
            mgr_map = resolve_or_upsert_managers(session, combined, overrides_data)
            season = upsert_season_from_payload(session, combined, league_id=league_id)
            team_map = upsert_teams_from_payload(session, season, combined, mgr_map, overrides_data)
            matchups = upsert_matchups_from_payload(session, season, combined, team_map)
            players = upsert_players_from_payload(session, combined)
            lineups = upsert_weekly_lineups_from_payload(session, season, combined, team_map)

            # Restore individual scoring period boxscore snapshots if present
            for snap in year_snaps:
                if snap.view_name == "mBoxscore" and snap.scoring_period > 0 and isinstance(snap.payload, dict):
                    upsert_players_from_payload(session, snap.payload)
                    period_lineups = upsert_weekly_lineups_from_payload(
                        session, season, snap.payload, team_map, weeks=[snap.scoring_period]
                    )
                    lineups.extend(period_lineups)

            draft_picks = upsert_draft_picks_from_payload(session, season, combined, team_map, client=client)
            txs = upsert_transactions_from_payload(session, season, combined, team_map)
            ledger_entries = reconcile_season_ledger(session, season)

            logger.info(
                "Season %d snapshot restored: %d teams, %d matchups, %d players, %d lineups, %d draft picks, %d transactions, %d earnings entries.",
                year,
                len(team_map),
                len(matchups),
                len(players),
                len(lineups),
                len(draft_picks),
                len(txs),
                len(ledger_entries),
            )

            records_processed += (
                1
                + len(team_map)
                + len(matchups)
                + len(players)
                + len(lineups)
                + len(draft_picks)
                + len(txs)
                + len(ledger_entries)
            )

        sync_run = SyncRun(
            run_type="BACKFILL",
            season_year=from_year,
            status="SUCCESS",
            records_processed=records_processed,
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )
        session.add(sync_run)
        session.flush()
        return sync_run

    # Live crawl from ESPN API
    espn_client = client or EspnClient(league_id=league_id)
    target_league_id = league_id or espn_client.league_id

    # If year range not provided, discover or default to recent past through current year
    current_calendar_year = datetime.now(UTC).year
    start_y = from_year or (current_calendar_year - 4)
    end_y = to_year or current_calendar_year

    logger.info(
        "Starting live ESPN backfill for league %s across seasons %d-%d...",
        target_league_id,
        start_y,
        end_y,
    )

    views = [
        "mSettings",
        "mTeam",
        "mMatchupScore",
        "mStatus",
        "mRoster",
        "mBoxscore",
        "mTransactions2",
        "mDraftDetail",
    ]

    for year in range(start_y, end_y + 1):
        logger.info("Crawling ESPN for season %d...", year)
        try:
            payload = espn_client.fetch_league(
                season_year=year,
                views=views,
                allow_inaccessible=True,
                league_id=target_league_id,
            )
        except EspnAccessError as e:
            logger.warning(
                "Season %d is inaccessible on ESPN (HTTP %s): %s. Skipping.",
                year,
                e.status_code,
                e,
            )
            continue
        except Exception as e:
            logger.error("Unexpected error fetching season %d: %s", year, e)
            continue

        if payload is None:
            logger.warning("Season %d returned no data or was inaccessible. Skipping.", year)
            continue

        # Archive raw payload into raw_espn_snapshots
        existing_snap = (
            session.query(RawEspnSnapshot)
            .filter_by(season_year=year, view_name="mCombined", scoring_period=0)
            .first()
        )
        if existing_snap:
            existing_snap.payload = payload
        else:
            session.add(
                RawEspnSnapshot(
                    season_year=year,
                    view_name="mCombined",
                    scoring_period=0,
                    payload=payload,
                )
            )

        # Parse entities
        mgr_map = resolve_or_upsert_managers(session, payload, overrides_data)
        season = upsert_season_from_payload(session, payload, league_id=target_league_id)
        team_map = upsert_teams_from_payload(session, season, payload, mgr_map, overrides_data)
        matchups = upsert_matchups_from_payload(session, season, payload, team_map)

        # If live ESPN crawl (client is not a mock without scoringPeriodId data), also pull per-scoring-period boxscores & transactions
        tx_filter = {
            "transactions": {
                "filterType": {
                    "value": [
                        "FREEAGENT",
                        "WAIVER",
                        "WAIVER_ERROR",
                        "TRADE_PROPOSAL",
                        "TRADE_ACCEPT",
                        "TRADE_UPHOLD",
                        "TRADE_VETO",
                        "ROSTER",
                    ]
                }
            }
        }
        max_sp = min(int(season.current_week or 1), 18)
        all_txs = list(payload.get("transactions") or [])
        if season.season_year >= 2018 and hasattr(espn_client, "http_session"):
            for sp in range(0, max_sp + 1):
                try:
                    sp_payload = espn_client.fetch_league(
                        season_year=year,
                        views=["mBoxscore", "mTransactions2", "mRoster", "mTeam"],
                        x_fantasy_filter=tx_filter,
                        allow_inaccessible=True,
                        league_id=target_league_id,
                        scoring_period_id=sp,
                    )
                    if isinstance(sp_payload, dict) and sp_payload.get("seasonId") == year:
                        sp_snap = (
                            session.query(RawEspnSnapshot)
                            .filter_by(season_year=year, view_name="mBoxscore", scoring_period=sp)
                            .first()
                        )
                        if sp_snap:
                            sp_snap.payload = sp_payload
                        else:
                            session.add(
                                RawEspnSnapshot(
                                    season_year=year,
                                    view_name="mBoxscore",
                                    scoring_period=sp,
                                    payload=sp_payload,
                                )
                            )
                        upsert_players_from_payload(session, sp_payload)
                        if sp > 0:
                            upsert_weekly_lineups_from_payload(
                                session, season, sp_payload, team_map, weeks=[sp]
                            )
                        all_txs.extend(sp_payload.get("transactions") or [])
                except Exception as sp_exc:
                    logger.debug("Skipping scoring period %d deep fetch: %s", sp, sp_exc)
        # Fetch league communication topics (recent activity) for executed trades (2019+)
        if season.season_year >= 2019 and hasattr(espn_client, "fetch_communication"):
            try:
                comm_filter = {
                    "topics": {
                        "filterType": {"value": ["ACTIVITY_TRANSACTIONS"]},
                        "limit": 500,
                        "limitPerMessageSet": {"value": 25},
                        "offset": 0,
                        "sortMessageDate": {"sortPriority": 1, "sortAsc": False},
                        "sortFor": {"sortPriority": 2, "sortAsc": False},
                        "filterIncludeMessageTypeIds": {"value": [244, 245, 246, 290]},
                    }
                }
                comm_data = espn_client.fetch_communication(
                    season_year=year,
                    league_id=target_league_id,
                    x_fantasy_filter=comm_filter,
                )
                if comm_data and comm_data.get("topics"):
                    payload = dict(payload)
                    payload["topics"] = comm_data.get("topics")
                    snap_to_update = (
                        session.query(RawEspnSnapshot)
                        .filter_by(season_year=year, view_name="mCombined", scoring_period=0)
                        .first()
                    )
                    if snap_to_update:
                        snap_to_update.payload = payload
                        flag_modified(snap_to_update, "payload")

                    # Fetch any missing players mentioned in communication topics
                    if hasattr(espn_client, "fetch_player_info"):
                        missing_pids = set()
                        for t in comm_data.get("topics", []):
                            for m in t.get("messages", []):
                                if m.get("messageTypeId") in (244, 245):
                                    pid = int(m.get("targetId", 0))
                                    if pid > 0 and not session.get(Player, pid):
                                        missing_pids.add(pid)
                        if missing_pids:
                            players_data = espn_client.fetch_player_info(
                                season_year=year,
                                player_ids=list(missing_pids),
                                league_id=target_league_id,
                            )
                            if players_data:
                                upsert_players_from_payload(session, {"players": players_data})
                                if "players" not in payload or not isinstance(payload["players"], list):
                                    payload["players"] = []
                                payload["players"].extend(players_data)
                                if snap_to_update:
                                    snap_to_update.payload = payload
                                    flag_modified(snap_to_update, "payload")
            except Exception as comm_exc:
                logger.debug("Skipping communication fetch: %s", comm_exc)

        if all_txs:
            payload = dict(payload)
            payload["transactions"] = all_txs
            snap_to_update = (
                session.query(RawEspnSnapshot)
                .filter_by(season_year=year, view_name="mCombined", scoring_period=0)
                .first()
            )
            if snap_to_update:
                snap_to_update.payload = payload
                flag_modified(snap_to_update, "payload")

        players = upsert_players_from_payload(session, payload)
        draft_picks = upsert_draft_picks_from_payload(
            session, season, payload, team_map, client=espn_client
        )
        lineups = upsert_weekly_lineups_from_payload(session, season, payload, team_map)
        txs = upsert_transactions_from_payload(session, season, payload, team_map)
        ledger_entries = reconcile_season_ledger(session, season)

        logger.info(
            "Season %d processed: %d teams, %d matchups, %d players, %d lineups, %d draft picks, %d transactions, %d earnings entries.",
            year,
            len(team_map),
            len(matchups),
            len(players),
            len(lineups),
            len(draft_picks),
            len(txs),
            len(ledger_entries),
        )

        records_processed += (
            1
            + len(team_map)
            + len(matchups)
            + len(players)
            + len(lineups)
            + len(draft_picks)
            + len(txs)
            + len(ledger_entries)
        )

    sync_run = SyncRun(
        run_type="BACKFILL",
        season_year=start_y,
        status="SUCCESS",
        records_processed=records_processed,
        started_at=started_at,
        completed_at=datetime.now(UTC),
    )
    session.add(sync_run)
    session.flush()
    return sync_run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="One-time ESPN Historical Backfill Job")
    parser.add_argument(
        "--from-snapshots",
        action="store_true",
        help="Rebuild tables purely from raw_espn_snapshots archive without hitting ESPN API.",
    )
    parser.add_argument("--from-year", type=int, default=None, help="Starting season year")
    parser.add_argument("--to-year", type=int, default=None, help="Ending season year")
    parser.add_argument("--league-id", type=str, default=None, help="ESPN League ID")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = parse_args()
    league_ids = [args.league_id] if args.league_id else get_configured_league_ids()
    target_league_id = league_ids[0]

    init_db()
    with get_session() as session:
        run = backfill_history(
            session=session,
            from_snapshots=args.from_snapshots,
            from_year=args.from_year,
            to_year=args.to_year,
            league_id=target_league_id,
        )
        print(f"✅ Backfill finished with status={run.status}, processed={run.records_processed} records.")


if __name__ == "__main__":
    main()
    sys.exit(0)
