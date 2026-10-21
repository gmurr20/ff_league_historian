"""backend/jobs - ESPN Fantasy Football Ingestion Engine & Out-of-Band Cron Workers.

Purpose:
    Exports core client, domain parsers, financial ledger reconciler,
    deep boxscore/transaction parsers, historical backfill worker, and incremental
    active-season rolling weekly sync job.
"""

from __future__ import annotations

from typing import Any

from backend.jobs.deep_parsers import (
    compute_optimal_score,
    normalize_position,
    normalize_pro_team,
    normalize_slot_position,
    upsert_players_from_payload,
    upsert_transactions_from_payload,
    upsert_weekly_lineups_from_payload,
)
from backend.jobs.espn_client import EspnAccessError, EspnClient, get_configured_league_ids
from backend.jobs.ledger_reconciler import (
    reconcile_podium_ledger,
    reconcile_season_ledger,
    reconcile_week_ledger,
)
from backend.jobs.parsers import (
    load_manager_overrides,
    resolve_or_upsert_managers,
    upsert_matchups_from_payload,
    upsert_season_from_payload,
    upsert_teams_from_payload,
)


def __getattr__(name: str) -> Any:
    if name == "backfill_history":
        from backend.jobs.backfill_history import backfill_history

        return backfill_history
    if name == "sync_weekly":
        from backend.jobs.sync_weekly import sync_weekly

        return sync_weekly
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "EspnClient",
    "EspnAccessError",
    "get_configured_league_ids",
    "load_manager_overrides",
    "resolve_or_upsert_managers",
    "upsert_season_from_payload",
    "upsert_teams_from_payload",
    "upsert_matchups_from_payload",
    "reconcile_week_ledger",
    "reconcile_podium_ledger",
    "reconcile_season_ledger",
    "backfill_history",
    "sync_weekly",
    "normalize_position",
    "normalize_pro_team",
    "normalize_slot_position",
    "upsert_players_from_payload",
    "compute_optimal_score",
    "upsert_weekly_lineups_from_payload",
    "upsert_transactions_from_payload",
]
