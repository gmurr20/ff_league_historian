"""backend/jobs/draft_assets.py - Draft Settings & Traded Pick Identity Helpers.

Purpose:
    Shared helpers used by ingestion jobs (backfill / weekly sync) and the
    commissioner trade editor to:
      - Persist ESPN `settings.draftSettings` (round-1 pick order, snake vs. linear,
        keeper count, draft date) into `draft_settings`.
      - Map an overall pick number to its round, round pick and *original* franchise
        slot (espn_team_id) using the snake/linear pick order.
      - Build trade TransactionItems for draft picks with an attached
        `TradedDraftPick` identity `(draft_year, round, original_espn_team_id)` so a
        specific team's pick can be followed as it is re-traded.

Franchise identity:
    Picks are tied to ESPN franchise *slots* (`teams.espn_team_id`) rather than
    season-scoped `teams.id` rows, because future-season team rows do not exist yet
    and franchise slots persist across seasons (and manager churn).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.models.draft import DraftSettings, TradedDraftPick
from backend.models.player import Player
from backend.models.season import Season
from backend.models.team import Team
from backend.models.transaction import TransactionItem

LINEAR_DRAFT_TYPES = {"LINEAR", "AUCTION", "OFFLINE"}


# ---------------------------------------------------------------------------
# Pick-order math
# ---------------------------------------------------------------------------


def is_snake(draft_type: str | None) -> bool:
    """Return True when the draft reverses order on even rounds (default ESPN snake)."""
    return str(draft_type or "SNAKE").upper() not in LINEAR_DRAFT_TYPES


def round_pick_for_slot(
    round_num: int, slot_index: int, team_count: int, draft_type: str | None = "SNAKE"
) -> int:
    """Return 1-based pick-within-round for a 0-based round-1 slot index."""
    if is_snake(draft_type) and round_num % 2 == 0:
        return team_count - slot_index
    return slot_index + 1


def overall_for_slot(
    round_num: int, slot_index: int, team_count: int, draft_type: str | None = "SNAKE"
) -> tuple[int, int]:
    """Return (round_pick, overall_pick) for a round and 0-based round-1 slot index."""
    rp = round_pick_for_slot(round_num, slot_index, team_count, draft_type)
    return rp, (round_num - 1) * team_count + rp


def slot_from_overall(
    overall_pick: int, pick_order: list[int], draft_type: str | None = "SNAKE"
) -> tuple[int, int, int | None]:
    """Map an overall pick to (round, round_pick, original espn_team_id).

    Returns `None` for the franchise slot when the pick order is unknown.
    """
    team_count = len(pick_order)
    if team_count <= 0 or overall_pick <= 0:
        return 0, 0, None
    round_num = ((overall_pick - 1) // team_count) + 1
    round_pick = ((overall_pick - 1) % team_count) + 1
    if is_snake(draft_type) and round_num % 2 == 0:
        slot_index = team_count - round_pick
    else:
        slot_index = round_pick - 1
    return round_num, round_pick, int(pick_order[slot_index])


def pick_order_from_payload(payload: dict[str, Any]) -> tuple[list[int], str]:
    """Extract (round-1 pick order, draft type) from an ESPN league payload."""
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    ds = settings.get("draftSettings") if isinstance(settings.get("draftSettings"), dict) else {}
    draft_type = str(ds.get("type") or "SNAKE").upper()
    order: list[int] = []
    for raw in ds.get("pickOrder") or []:
        try:
            order.append(int(raw))
        except (TypeError, ValueError):
            continue

    if not order:
        # Fallback: reconstruct round-1 order from completed draft picks.
        detail = payload.get("draftDetail") if isinstance(payload.get("draftDetail"), dict) else {}
        round_one = sorted(
            (p for p in detail.get("picks") or [] if int(p.get("roundId") or 0) == 1),
            key=lambda p: int(p.get("roundPickNumber") or 0),
        )
        order = [int(p.get("teamId")) for p in round_one if p.get("teamId")]
    return order, draft_type


def _ms_to_datetime(val: Any) -> datetime | None:
    if not val:
        return None
    try:
        num = float(val)
    except (TypeError, ValueError):
        return None
    ts = num / 1000.0 if num > 1e11 else num
    try:
        return datetime.fromtimestamp(ts, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Ingestion: draft settings
# ---------------------------------------------------------------------------


def upsert_draft_settings_from_payload(
    session: Session, season: Season, payload: dict[str, Any]
) -> DraftSettings | None:
    """Persist ESPN `settings.draftSettings` + `draftDetail` status for a season."""
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    ds = settings.get("draftSettings") if isinstance(settings.get("draftSettings"), dict) else {}
    detail = payload.get("draftDetail") if isinstance(payload.get("draftDetail"), dict) else {}
    if not ds and not detail:
        return None

    pick_order, draft_type = pick_order_from_payload(payload)

    row = session.get(DraftSettings, season.season_year)
    if row is None:
        row = DraftSettings(season_year=season.season_year)
        session.add(row)

    row.draft_type = draft_type
    row.order_type = str(ds.get("orderType")) if ds.get("orderType") else None
    if pick_order:
        row.pick_order = pick_order
    elif row.pick_order is None:
        row.pick_order = []
    row.keeper_count = int(ds.get("keeperCount") or 0)
    row.draft_date = _ms_to_datetime(ds.get("date")) or row.draft_date
    row.is_drafted = bool(detail.get("drafted", row.is_drafted or False))
    row.completed_at = _ms_to_datetime(detail.get("completeDate")) or row.completed_at
    if ds:
        row.raw_settings = ds
    session.flush()
    return row


# ---------------------------------------------------------------------------
# Trades: draft pick placeholder players & identities
# ---------------------------------------------------------------------------


def resolve_or_create_pick_player(
    session: Session, pick: dict[str, Any], default_season: int
) -> int:
    """Resolve or create the placeholder Player row representing a draft pick asset."""
    pick_season = int(pick.get("season_year") or default_season)
    round_num = int(pick.get("round") or 1)
    pick_num_raw = pick.get("pick_number")
    pick_num = int(pick_num_raw) if pick_num_raw not in (None, "", 0) else None

    if pick_num is not None and pick_season == default_season:
        pid = -100000 - pick_num
        name = f"Round {round_num} Pick #{pick_num}"
    else:
        p_sub = pick_num % 100 if pick_num is not None else 0
        pid = -(pick_season * 10000 + round_num * 100 + p_sub)
        if pick_num is not None and pick_num > 0:
            name = f"{pick_season} Round {round_num} Pick #{pick_num}"
        elif pick_season != default_season:
            name = f"{pick_season} Round {round_num} Pick"
        else:
            name = f"Round {round_num} Pick"

    if not session.get(Player, pid):
        session.add(
            Player(
                espn_player_id=pid,
                full_name=name,
                default_position="PICK",
                pro_team="DRAFT",
            )
        )
        session.flush()
    return pid


def resolve_original_espn_team_id(
    session: Session,
    pick: dict[str, Any],
    default_season: int,
    fallback_from_team_id: int | None = None,
) -> int | None:
    """Resolve the original franchise slot for a commissioner-entered pick.

    Priority: explicit `original_team_id` (season-scoped teams.id) →
    explicit `original_espn_team_id` → derived from a current-season overall pick
    number via stored draft settings → fallback to `fallback_from_team_id`'s espn_team_id → None.
    """
    raw_team_id = pick.get("original_team_id")
    if raw_team_id not in (None, "", 0):
        try:
            team = session.get(Team, int(raw_team_id))
        except (TypeError, ValueError):
            team = None
        if team is not None:
            return int(team.espn_team_id)

    raw_espn = pick.get("original_espn_team_id")
    if raw_espn not in (None, "", 0):
        try:
            return int(raw_espn)
        except (TypeError, ValueError):
            pass

    pick_season = int(pick.get("season_year") or default_season)
    pick_num_raw = pick.get("pick_number")
    if pick_num_raw not in (None, "", 0):
        settings = session.get(DraftSettings, pick_season)
        if settings and settings.pick_order:
            _, _, slot = slot_from_overall(
                int(pick_num_raw), [int(x) for x in settings.pick_order], settings.draft_type
            )
            return slot

    if fallback_from_team_id is not None:
        fallback_team = session.get(Team, fallback_from_team_id)
        if fallback_team is not None:
            return int(fallback_team.espn_team_id)

    return None


def build_pick_trade_item(
    session: Session,
    *,
    transaction_id: int,
    pick: dict[str, Any],
    default_season: int,
    from_team_id: int | None,
    to_team_id: int | None,
) -> TransactionItem:
    """Create a TRADE TransactionItem for a draft pick with its TradedDraftPick identity."""
    pick_pid = resolve_or_create_pick_player(session, pick, default_season)
    pick_num_raw = pick.get("pick_number")
    item = TransactionItem(
        transaction_id=transaction_id,
        player_id=pick_pid,
        from_team_id=from_team_id,
        to_team_id=to_team_id,
        item_type="TRADE",
    )
    item.traded_pick = TradedDraftPick(
        draft_year=int(pick.get("season_year") or default_season),
        round=int(pick.get("round") or 1),
        original_espn_team_id=resolve_original_espn_team_id(
            session, pick, default_season, fallback_from_team_id=from_team_id
        ),
        overall_pick=int(pick_num_raw) if pick_num_raw not in (None, "", 0) else None,
    )
    return item


def attach_espn_pick_identity(
    item: TransactionItem,
    *,
    season_year: int,
    overall_pick: int,
    pick_order: list[int],
    draft_type: str,
    league_size: int,
) -> None:
    """Attach identity to an ESPN DRAFT_TRADE item (current-season overall pick)."""
    if pick_order:
        round_num, _, slot = slot_from_overall(overall_pick, pick_order, draft_type)
    else:
        size = league_size or 12
        round_num, slot = ((overall_pick - 1) // size) + 1, None
    item.traded_pick = TradedDraftPick(
        draft_year=season_year,
        round=round_num,
        original_espn_team_id=slot,
        overall_pick=overall_pick,
    )
