"""backend/jobs/deep_parsers.py - Deep ESPN Payload Parsers for Players, Boxscores & Transactions.

Purpose:
    Extracts and normalizes granular fantasy data from ESPN Fantasy API v3 (and legacy snapshots):
      - Canonical NFL players (positions, pro teams, and CDN headshots)
      - Weekly boxscore player lineups (starters, bench, IR, actual and projected points)
      - Team Max PF optimal lineup score and bench points calculation on matchups
      - Transactions, FAAB bidding war receipts (losing bids linked via related_espn_transaction_id),
        free agents, drops, and deduplicated bilateral trades.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.jobs.draft_assets import (
    attach_espn_pick_identity,
    build_pick_trade_item,
    pick_order_from_payload,
)
from backend.jobs.parsers import get_combined_trade_overrides
from backend.models.draft import DraftPick
from backend.models.lineup import WeeklyLineup
from backend.models.matchup import Matchup
from backend.models.player import Player
from backend.models.raw_snapshot import RawEspnSnapshot
from backend.models.season import Season
from backend.models.team import Team
from backend.models.trade import Trade
from backend.models.transaction import Transaction, TransactionItem

logger = logging.getLogger(__name__)

# ESPN Position ID -> Standard Position
ESPN_POSITION_MAP: dict[int, str] = {
    1: "QB",
    2: "RB",
    3: "WR",
    4: "TE",
    5: "K",
    16: "D/ST",
}

# ESPN Lineup Slot ID -> Slot Position
ESPN_SLOT_MAP: dict[int, str] = {
    0: "QB",
    1: "TQB",
    2: "RB",
    3: "RB/WR",
    4: "WR",
    5: "WR/TE",
    6: "TE",
    7: "OP",
    16: "D/ST",
    17: "K",
    20: "BE",
    21: "IR",
    23: "FLEX",
}

# ESPN Pro Team ID -> NFL Team Abbreviation
ESPN_PRO_TEAM_MAP: dict[int, str] = {
    0: "FA",
    1: "ATL",
    2: "BUF",
    3: "CHI",
    4: "CIN",
    5: "CLE",
    6: "DAL",
    7: "DEN",
    8: "DET",
    9: "GB",
    10: "TEN",
    11: "IND",
    12: "KC",
    13: "LV",
    14: "LAR",
    15: "MIA",
    16: "MIN",
    17: "NE",
    18: "NO",
    19: "NYG",
    20: "NYJ",
    21: "PHI",
    22: "ARI",
    23: "PIT",
    24: "LAC",
    25: "SF",
    26: "SEA",
    27: "TB",
    28: "WAS",
    29: "CAR",
    30: "JAX",
    33: "BAL",
    34: "HOU",
}


def _parse_espn_timestamp(val: Any) -> datetime | None:
    """Parse ESPN timestamp (epoch milliseconds, epoch seconds, or ISO string) to UTC datetime."""
    if val is None or val == 0:
        return None
    if isinstance(val, (int, float)):
        # ESPN timestamps are usually epoch milliseconds
        ts = val / 1000.0 if val > 1e11 else float(val)
        try:
            return datetime.fromtimestamp(ts, tz=UTC)
        except (ValueError, OSError):
            return None
    if isinstance(val, str):
        cleaned = val.strip()
        if not cleaned:
            return None
        try:
            return datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        except ValueError:
            try:
                num = float(cleaned)
                ts = num / 1000.0 if num > 1e11 else num
                return datetime.fromtimestamp(ts, tz=UTC)
            except (ValueError, OSError):
                return None
    return None


def resolve_or_create_pick_player(
    session: Session, pick: dict[str, Any], default_season: int
) -> int:
    """Resolve or create a draft pick placeholder player."""
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

    existing_player = session.get(Player, pid)
    if not existing_player:
        player = Player(
            espn_player_id=pid,
            full_name=name,
            default_position="PICK",
            pro_team="DRAFT",
        )
        session.add(player)
        session.flush()

    return pid


def _resolve_team_id(
    t_val: Any,
    season_year: int,
    session: Session,
    team_lookup: dict[int, Team],
    prefer_espn_id: bool = False,
) -> int | None:
    """Resolve internal Team.id from DB id, espn_team_id, or team_lookup mapping."""
    if not t_val:
        return None
    try:
        t_int = int(t_val)
    except (ValueError, TypeError):
        return None

    if prefer_espn_id:
        if t_int in team_lookup:
            return team_lookup[t_int].id
        team_by_espn = (
            session.query(Team)
            .filter_by(espn_team_id=t_int, season_year=season_year)
            .first()
        )
        if team_by_espn:
            return team_by_espn.id

    team_by_id = session.query(Team).filter_by(id=t_int, season_year=season_year).first()
    if team_by_id:
        return team_by_id.id

    if t_int in team_lookup:
        return team_lookup[t_int].id

    team_by_espn = session.query(Team).filter_by(espn_team_id=t_int, season_year=season_year).first()
    if team_by_espn:
        return team_by_espn.id

    return None


def _resolve_side_team_id(
    side: dict[str, Any],
    season_year: int,
    session: Session,
    team_lookup: dict[int, Team],
) -> int | None:
    """Resolve a trade side's Team.id, preferring canonical espn_team_id when present."""
    if not isinstance(side, dict):
        return None
    if side.get("espn_team_id") is not None:
        resolved = _resolve_team_id(
            side.get("espn_team_id"),
            season_year,
            session,
            team_lookup,
            prefer_espn_id=True,
        )
        if resolved is not None:
            return resolved
    return _resolve_team_id(side.get("team_id"), season_year, session, team_lookup)


def normalize_position(raw_pos: Any) -> str:
    """Normalize ESPN position id or raw string to canonical position abbreviation."""
    if isinstance(raw_pos, int) and raw_pos in ESPN_POSITION_MAP:
        return ESPN_POSITION_MAP[raw_pos]
    if isinstance(raw_pos, str):
        cleaned = raw_pos.strip().upper()
        if cleaned in ("DST", "DEF"):
            return "D/ST"
        if cleaned in ("QB", "RB", "WR", "TE", "K", "D/ST", "FLEX"):
            return cleaned
        # Check if string of integer
        try:
            int_val = int(cleaned)
            if int_val in ESPN_POSITION_MAP:
                return ESPN_POSITION_MAP[int_val]
        except ValueError:
            pass
        return cleaned or "UNKNOWN"
    return "UNKNOWN"


def normalize_pro_team(raw_team: Any) -> str:
    """Normalize ESPN proTeamId or raw string to canonical NFL team abbreviation."""
    if isinstance(raw_team, int) and raw_team in ESPN_PRO_TEAM_MAP:
        return ESPN_PRO_TEAM_MAP[raw_team]
    if isinstance(raw_team, str):
        cleaned = raw_team.strip().upper()
        if cleaned in ("WSH", "WASHINGTON"):
            return "WAS"
        if cleaned in ("OAK", "OAKLAND"):
            return "LV"
        if cleaned in ("SD", "SAN DIEGO"):
            return "LAC"
        if cleaned in ("STL", "ST. LOUIS"):
            return "LAR"
        if cleaned in ESPN_PRO_TEAM_MAP.values():
            return cleaned
        try:
            int_val = int(cleaned)
            if int_val in ESPN_PRO_TEAM_MAP:
                return ESPN_PRO_TEAM_MAP[int_val]
        except ValueError:
            pass
        return cleaned or "FA"
    return "FA"


def normalize_slot_position(raw_slot: Any) -> str:
    """Normalize ESPN lineupSlotId or slot position string."""
    if isinstance(raw_slot, int) and raw_slot in ESPN_SLOT_MAP:
        return ESPN_SLOT_MAP[raw_slot]
    if isinstance(raw_slot, str):
        cleaned = raw_slot.strip().upper()
        if cleaned in ("DST", "DEF"):
            return "D/ST"
        if cleaned in ("BENCH", "BN"):
            return "BE"
        try:
            int_val = int(cleaned)
            if int_val in ESPN_SLOT_MAP:
                return ESPN_SLOT_MAP[int_val]
        except ValueError:
            pass
        return cleaned or "BE"
    return "BE"


def upsert_players_from_payload(
    session: Session, payload: dict[str, Any]
) -> dict[int, Player]:
    """Extract and upsert canonical NFL player entities from anywhere in the payload.

    Args:
        session: Active SQLAlchemy session.
        payload: ESPN league payload containing teams, schedule, boxscores, players, or transactions.

    Returns:
        Mapping of espn_player_id -> Player ORM instance.
    """
    raw_players: dict[int, dict[str, Any]] = {}

    def _extract_player_dict(data: Any) -> None:
        if not isinstance(data, dict):
            return
        # Case A: player pool entry or nested player
        p_obj = data.get("playerPoolEntry", {}).get("player") or data.get("player")
        if isinstance(p_obj, dict) and p_obj.get("id"):
            pid = int(p_obj["id"])
            raw_players[pid] = {
                "id": pid,
                "fullName": p_obj.get("fullName") or p_obj.get("name") or data.get("name"),
                "defaultPositionId": p_obj.get("defaultPositionId") or p_obj.get("defaultPosition"),
                "proTeamId": p_obj.get("proTeamId") or p_obj.get("proTeam"),
                "headshot_url": p_obj.get("headshot_url") or p_obj.get("headshotUrl"),
            }
            return

        # Case B: direct player dict
        if "id" in data and ("fullName" in data or "defaultPositionId" in data or "defaultPosition" in data):
            pid = int(data["id"])
            raw_players[pid] = {
                "id": pid,
                "fullName": data.get("fullName") or data.get("name"),
                "defaultPositionId": data.get("defaultPositionId") or data.get("defaultPosition"),
                "proTeamId": data.get("proTeamId") or data.get("proTeam"),
                "headshot_url": data.get("headshot_url") or data.get("headshotUrl"),
            }
            return

        # Case C: transaction item with playerId
        if "playerId" in data and int(data["playerId"]) not in raw_players:
            pid = int(data["playerId"])
            raw_players[pid] = {
                "id": pid,
                "fullName": data.get("playerName") or data.get("name") or f"Player {pid}",
                "defaultPositionId": data.get("defaultPositionId") or 0,
                "proTeamId": data.get("proTeamId") or 0,
                "headshot_url": data.get("headshot_url"),
            }

    # 1. Inspect top-level players / playerPool
    for p in payload.get("players", []):
        _extract_player_dict(p)
    for p in payload.get("playerPool", []):
        _extract_player_dict(p)

    # 2. Inspect teams roster
    for team in payload.get("teams", []):
        for entry in team.get("roster", {}).get("entries", []):
            _extract_player_dict(entry)

    # 3. Inspect schedule boxscore rosters
    for item in payload.get("schedule", []):
        for side in ("home", "away"):
            side_data = item.get(side)
            if not isinstance(side_data, dict):
                continue
            for roster_key in (
                "rosterForCurrentScoringPeriod",
                "rosterForMatchupPeriod",
                "roster",
            ):
                entries = side_data.get(roster_key, {}).get("entries", [])
                for entry in entries:
                    _extract_player_dict(entry)

    # 4. Inspect explicit weekly_lineups / boxscores
    for entry in payload.get("weekly_lineups", []):
        _extract_player_dict(entry)
    for entry in payload.get("boxscores", []):
        _extract_player_dict(entry)

    # 5. Inspect transactions
    for tx in payload.get("transactions", []):
        for item in tx.get("items", []):
            _extract_player_dict(item)

    upserted_players: dict[int, Player] = {}
    for pid, p_info in raw_players.items():
        name = p_info.get("fullName") or f"Player {pid}"
        pos = normalize_position(p_info.get("defaultPositionId"))
        if pos == "UNKNOWN":
            pos = "FLEX"
        team = normalize_pro_team(p_info.get("proTeamId"))

        headshot = p_info.get("headshot_url")
        if not headshot:
            if pos == "D/ST":
                headshot = None
            else:
                headshot = f"https://a.espncdn.com/i/headshots/nfl/players/full/{pid}.png"

        player = session.get(Player, pid)
        if not player:
            player = Player(
                espn_player_id=pid,
                full_name=name,
                default_position=pos,
                pro_team=team,
                headshot_url=headshot,
            )
            session.add(player)
        else:
            if name and not name.startswith("Player "):
                player.full_name = name
            if pos not in ("UNKNOWN", "FLEX"):
                player.default_position = pos
            elif player.default_position == "UNKNOWN":
                player.default_position = pos
            if team != "FA":
                player.pro_team = team
            if headshot:
                player.headshot_url = headshot

        upserted_players[pid] = player

    session.flush()
    return upserted_players


def _get_slot_count(slots: dict[str, Any], *keys: str | int, default: int = 0) -> int:
    """Extract integer slot count from roster_slots dict supporting names or numeric IDs."""
    for k in keys:
        if k in slots:
            try:
                return int(slots[k])
            except (ValueError, TypeError):
                pass
        str_k = str(k)
        if str_k in slots:
            try:
                return int(slots[str_k])
            except (ValueError, TypeError):
                pass
    return default


def compute_optimal_score(
    lineup_entries: list[dict[str, Any] | WeeklyLineup],
    roster_slots: dict[str, Any] | None = None,
    player_positions: dict[int, str] | None = None,
) -> tuple[Decimal, Decimal]:
    """Compute optimal lineup score (Max PF) and total bench points for a team's weekly lineup.

    Rules:
      - Bench points: sum of actual_points where slot_position == "BE".
      - Optimal score: highest-scoring legal starter combination from rostered non-IR players
        based on season roster_slots (defaulting to 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 D/ST, 1 K).
      - Invariant: optimal_score >= actual_starter_points.

    Args:
        lineup_entries: Weekly lineup records (dicts or WeeklyLineup models) for one team in one week.
        roster_slots: Optional season roster_slots mapping (e.g. {"QB": 1, "RB": 2, "WR": 2, ...}).
        player_positions: Optional player_id -> default_position mapping.

    Returns:
        tuple of (optimal_score, bench_points).
    """
    slots = roster_slots or {}
    qb_count = _get_slot_count(slots, "QB", 0, default=1)
    rb_count = _get_slot_count(slots, "RB", 2, default=2)
    wr_count = _get_slot_count(slots, "WR", 4, default=2)
    te_count = _get_slot_count(slots, "TE", 6, default=1)
    flex_count = _get_slot_count(slots, "FLEX", 23, default=1)
    dst_count = _get_slot_count(slots, "D/ST", "DST", 16, default=1)
    k_count = _get_slot_count(slots, "K", 17, default=1)
    superflex_count = _get_slot_count(slots, "OP", "SUPERFLEX", 7, default=0)

    bench_points = Decimal("0.00")
    actual_starter_points = Decimal("0.00")

    candidates: list[dict[str, Any]] = []

    for item in lineup_entries:
        if isinstance(item, WeeklyLineup):
            pid = item.player_id
            slot = item.slot_position
            is_start = item.is_starter
            pts = Decimal(str(item.actual_points))
            pos = item.player.default_position if item.player else "FLEX"
        else:
            pid = int(item.get("player_id", item.get("playerId", 0)))
            slot = normalize_slot_position(item.get("slot_position", item.get("lineupSlotId", "BE")))
            is_start = bool(item.get("is_starter", slot not in ("BE", "IR")))
            raw_pts = item.get("actual_points", item.get("appliedStatTotal", item.get("actualPoints", 0.0)))
            pts = Decimal(str(raw_pts or 0.0))
            pos = item.get("default_position") or (player_positions.get(pid) if player_positions else None) or "FLEX"

        pos = normalize_position(pos)

        if slot == "BE":
            bench_points += pts
        if is_start:
            actual_starter_points += pts

        # IR players are excluded from optimal starter selection
        if slot != "IR":
            candidates.append({
                "player_id": pid,
                "position": pos,
                "actual_points": pts,
            })

    # Group eligible candidates by position
    qbs = sorted([c for c in candidates if c["position"] == "QB"], key=lambda x: x["actual_points"], reverse=True)
    rbs = sorted([c for c in candidates if c["position"] == "RB"], key=lambda x: x["actual_points"], reverse=True)
    wrs = sorted([c for c in candidates if c["position"] == "WR"], key=lambda x: x["actual_points"], reverse=True)
    tes = sorted([c for c in candidates if c["position"] == "TE"], key=lambda x: x["actual_points"], reverse=True)
    dsts = sorted([c for c in candidates if c["position"] == "D/ST"], key=lambda x: x["actual_points"], reverse=True)
    ks = sorted([c for c in candidates if c["position"] == "K"], key=lambda x: x["actual_points"], reverse=True)

    selected: list[dict[str, Any]] = []
    selected.extend(qbs[:qb_count])
    selected.extend(rbs[:rb_count])
    selected.extend(wrs[:wr_count])
    selected.extend(tes[:te_count])
    selected.extend(dsts[:dst_count])
    selected.extend(ks[:k_count])

    # Remaining RB, WR, TE form candidate pool for FLEX
    remaining_flex = rbs[rb_count:] + wrs[wr_count:] + tes[te_count:]
    remaining_flex.sort(key=lambda x: x["actual_points"], reverse=True)
    selected.extend(remaining_flex[:flex_count])

    if superflex_count > 0:
        remaining_superflex = qbs[qb_count:] + remaining_flex[flex_count:]
        remaining_superflex.sort(key=lambda x: x["actual_points"], reverse=True)
        selected.extend(remaining_superflex[:superflex_count])

    optimal_calculated = sum((c["actual_points"] for c in selected), Decimal("0.00"))
    optimal_score = max(optimal_calculated, actual_starter_points)

    return optimal_score.quantize(Decimal("0.01")), bench_points.quantize(Decimal("0.01"))


def upsert_weekly_lineups_from_payload(
    session: Session,
    season: Season,
    payload: dict[str, Any],
    team_lookup: dict[int, Team],
    weeks: list[int] | None = None,
) -> list[WeeklyLineup]:
    """Parse weekly boxscore player lineups and update matchup optimal scores & bench points.

    Args:
        session: Active SQLAlchemy session.
        season: Upserted Season ORM entity.
        payload: ESPN league payload containing schedule or weekly_lineups.
        team_lookup: Mapping of espn_team_id -> Team instance.
        weeks: Optional list of scoring weeks to restrict processing (for incremental weekly sync).

    Returns:
        List of upserted WeeklyLineup ORM instances.
    """
    raw_entries: list[dict[str, Any]] = []

    # 1. Extract roster entries from schedule boxscores
    for item in payload.get("schedule", []):
        week = int(item.get("matchupPeriodId", 1))
        if weeks is not None and week not in weeks:
            continue

        for side in ("home", "away"):
            side_data = item.get(side)
            if not isinstance(side_data, dict):
                continue
            espn_team_id = side_data.get("teamId")
            if espn_team_id not in team_lookup:
                continue

            for roster_key in (
                "rosterForCurrentScoringPeriod",
                "rosterForMatchupPeriod",
                "roster",
            ):
                entries = side_data.get(roster_key, {}).get("entries", [])
                if entries:
                    for entry in entries:
                        raw_entries.append({
                            "week": week,
                            "espn_team_id": espn_team_id,
                            "entry": entry,
                        })
                    break

    # 2. Extract from explicit weekly_lineups / boxscores if provided
    for entry in payload.get("weekly_lineups", []) + payload.get("boxscores", []):
        w = int(entry.get("week", entry.get("matchupPeriodId", 1)))
        if weeks is not None and w not in weeks:
            continue
        espn_t = entry.get("espn_team_id", entry.get("teamId"))
        if espn_t in team_lookup:
            raw_entries.append({
                "week": w,
                "espn_team_id": espn_t,
                "entry": entry,
            })

    # 3. Extract from team rosters (e.g. from mTeam + mRoster in ESPN leagueHistory,
    #    scoring_period=0 opening rosters, or teams on a playoff bye missing from schedule boxscores)
    if "teams" in payload and ((weeks and len(weeks) == 1) or not raw_entries):
        target_week = (
            weeks[0]
            if weeks and len(weeks) == 1
            else int(payload.get("scoringPeriodId") or season.current_week or 1)
        )
        if weeks is None or target_week in weeks:
            teams_with_week_entries = {
                r["espn_team_id"] for r in raw_entries if r["week"] == target_week
            }
            for team_item in payload.get("teams", []):
                espn_t = team_item.get("id")
                if espn_t not in team_lookup or espn_t in teams_with_week_entries:
                    continue
                entries = team_item.get("roster", {}).get("entries", [])
                for entry in entries:
                    raw_entries.append({
                        "week": target_week,
                        "espn_team_id": espn_t,
                        "entry": entry,
                        "from_team_roster": True,
                    })

    if not raw_entries:
        existing_count = (
            session.query(WeeklyLineup)
            .filter_by(season_year=season.season_year)
            .count()
        )
        if existing_count == 0 and (season.season_year < 2019 or season.is_completed):
            season.has_boxscore_data = False
        return []

    # First ensure players exist
    player_map = upsert_players_from_payload(session, payload)

    # Build player injury status lookup from teams and players payloads
    injury_lookup: dict[int, tuple[str | None, bool]] = {}
    for team_item in payload.get("teams", []):
        for t_entry in team_item.get("roster", {}).get("entries", []):
            tp_obj = (
                t_entry.get("playerPoolEntry", {}).get("player")
                or t_entry.get("player", {})
            )
            t_pid = t_entry.get("playerId") or tp_obj.get("id")
            if not t_pid:
                continue
            t_status = tp_obj.get("injuryStatus") or t_entry.get("injuryStatus")
            if t_status in ("NORMAL", "ACTIVE"):
                t_status = None
            t_injured = bool(tp_obj.get("injured", False))
            injury_lookup[int(t_pid)] = (t_status, t_injured)

    for p_item in payload.get("players", []):
        p_sub = p_item.get("player", p_item)
        p_pid = p_sub.get("id")
        if p_pid and int(p_pid) not in injury_lookup:
            p_status = p_sub.get("injuryStatus")
            if p_status in ("NORMAL", "ACTIVE"):
                p_status = None
            injury_lookup[int(p_pid)] = (p_status, bool(p_sub.get("injured", False)))

    upserted_lineups: list[WeeklyLineup] = []
    # Group entries by (week, team_id) for optimal score calculation
    by_week_team: dict[tuple[int, int], list[WeeklyLineup]] = {}

    for raw in raw_entries:
        week = raw["week"]
        espn_team_id = raw["espn_team_id"]
        team = team_lookup[espn_team_id]
        entry = raw["entry"]

        # Extract player id
        p_obj = entry.get("playerPoolEntry", {}).get("player") or entry.get("player", {})
        pid = (
            entry.get("playerId")
            or p_obj.get("id")
            or entry.get("playerPoolEntry", {}).get("id")
        )
        if not pid:
            continue
        pid = int(pid)

        # Ensure player exists
        if pid not in player_map and not session.get(Player, pid):
            p = Player(
                espn_player_id=pid,
                full_name=entry.get("playerName") or p_obj.get("fullName") or f"Player {pid}",
                default_position=normalize_position(p_obj.get("defaultPositionId")),
                pro_team=normalize_pro_team(p_obj.get("proTeamId")),
            )
            session.add(p)
            session.flush()
            player_map[pid] = p

        slot_raw = entry.get("lineupSlotId", entry.get("slotPosition", "BE"))
        slot = normalize_slot_position(slot_raw)
        is_starter = slot not in ("BE", "IR")

        # Points
        ppe = entry.get("playerPoolEntry", {})
        from_team_roster = bool(raw.get("from_team_roster"))
        if week == 0:
            actual_raw = 0.0
            proj_raw = 0.0
        elif from_team_roster and "actualPoints" not in entry and "appliedStatTotal" not in entry:
            # On team.roster.entries, playerPoolEntry.appliedStatTotal is the full season total,
            # so default to 0.0 unless per-scoringPeriod stats for `week` are found below.
            actual_raw = 0.0
            proj_raw = 0.0
        else:
            actual_raw = (
                entry.get("actualPoints")
                if "actualPoints" in entry
                else entry.get("appliedStatTotal", ppe.get("appliedStatTotal", 0.0))
            )
            proj_raw = (
                entry.get("projectedPoints")
                if "projectedPoints" in entry
                else entry.get("projectedStatTotal", ppe.get("projectedStatTotal", 0.0))
            )

        stats = dict(entry.get("weeklyStats") or ppe.get("weeklyStats") or {})

        # If actual_raw is 0 or appliedStatTotal is seasonal, check per-scoringPeriod stats on player
        p_stats = (p_obj.get("stats") or []) if isinstance(p_obj, dict) else []
        if p_stats and week > 0:
            for s in p_stats:
                if s.get("scoringPeriodId") == week:
                    if s.get("statSourceId") == 0:
                        actual_raw = s.get("appliedTotal", actual_raw)
                        if not stats:
                            raw_s = s.get("stats", {})
                            td_sum = int(raw_s.get("4", 0) + raw_s.get("25", 0) + raw_s.get("43", 0))
                            if td_sum > 0:
                                stats["touchdowns"] = td_sum
                            if "3" in raw_s:
                                stats["passing_yards"] = int(raw_s["3"])
                            if "24" in raw_s:
                                stats["rushing_yards"] = int(raw_s["24"])
                            if "42" in raw_s:
                                stats["receiving_yards"] = int(raw_s["42"])
                            if "53" in raw_s:
                                stats["receptions"] = int(raw_s["53"])
                    elif s.get("statSourceId") == 1:
                        proj_raw = s.get("appliedTotal", proj_raw)

        # Injury tracking
        injury_status = (
            p_obj.get("injuryStatus")
            or entry.get("injuryStatus")
            or ppe.get("injuryStatus")
        )
        if injury_status in ("NORMAL", "ACTIVE"):
            injury_status = None
        injured = bool(p_obj.get("injured", False))

        if not injury_status and not injured and pid in injury_lookup:
            l_status, l_inj = injury_lookup[pid]
            if not is_starter or l_status != "INJURY_RESERVE":
                if l_status:
                    injury_status = l_status
                if l_inj:
                    injured = True

        if slot == "IR":
            injured = True
            if not injury_status:
                injury_status = "INJURY_RESERVE"

        stats["injury_status"] = injury_status
        stats["injured"] = injured

        actual_pts = Decimal(str(actual_raw or 0.0)).quantize(Decimal("0.01"))
        proj_pts = Decimal(str(proj_raw or 0.0)).quantize(Decimal("0.01"))

        acq_type = entry.get("acquisitionType") or ppe.get("acquisitionType")

        lineup = (
            session.query(WeeklyLineup)
            .filter_by(
                season_year=season.season_year,
                week=week,
                team_id=team.id,
                player_id=pid,
            )
            .first()
        )
        if not lineup:
            lineup = WeeklyLineup(
                season_year=season.season_year,
                week=week,
                team_id=team.id,
                player_id=pid,
                slot_position=slot,
                is_starter=is_starter,
                actual_points=actual_pts,
                projected_points=proj_pts,
                acquisition_type=acq_type,
                weekly_stats=stats if isinstance(stats, dict) else {},
            )
            session.add(lineup)
        else:
            lineup.slot_position = slot
            lineup.is_starter = is_starter
            lineup.actual_points = actual_pts
            lineup.projected_points = proj_pts
            if acq_type:
                lineup.acquisition_type = acq_type
            if isinstance(stats, dict):
                merged_stats = dict(lineup.weekly_stats or {})
                merged_stats.update(stats)
                lineup.weekly_stats = merged_stats

        upserted_lineups.append(lineup)
        by_week_team.setdefault((week, team.id), []).append(lineup)

    session.flush()

    # Calculate optimal scores and bench points on matchups
    player_pos_map = {p.espn_player_id: p.default_position for p in player_map.values()}
    for (week, team_id), entries in by_week_team.items():
        opt_score, bench_pts = compute_optimal_score(
            entries,
            roster_slots=season.roster_slots,
            player_positions=player_pos_map,
        )

        matchup = (
            session.query(Matchup)
            .filter(
                Matchup.season_year == season.season_year,
                Matchup.week == week,
                (Matchup.home_team_id == team_id) | (Matchup.away_team_id == team_id),
            )
            .first()
        )
        if matchup:
            if matchup.home_team_id == team_id:
                matchup.home_optimal_score = opt_score
                matchup.home_bench_points = bench_pts
            elif matchup.away_team_id == team_id:
                matchup.away_optimal_score = opt_score
                matchup.away_bench_points = bench_pts

    season.has_boxscore_data = True
    session.flush()
    return upserted_lineups


def _infer_nfl_week_from_timestamp(
    ts_sec: float,
    week_ranges: list[tuple[int, float, float]],
    default_season_year: int | None = None,
) -> int:
    """Resolve NFL fantasy week (0 for Preseason, 1..18 for season) from epoch seconds."""
    if not ts_sec or ts_sec <= 0:
        return 1

    dt = datetime.fromtimestamp(ts_sec, tz=UTC)
    if dt.month <= 8:
        return 0

    sep1_weekday = datetime(dt.year, 9, 1, tzinfo=UTC).weekday()
    first_monday_day = 1 + (0 - sep1_weekday) % 7
    w1_start_dt = datetime(dt.year, 9, first_monday_day + 1, 0, 0, tzinfo=UTC)
    w1_rollover_anchor_sec = datetime(dt.year, 9, first_monday_day + 2, 8, 0, tzinfo=UTC).timestamp()

    if ts_sec < w1_start_dt.timestamp():
        return 0

    if week_ranges:
        for wk, start_ts, end_ts in week_ranges:
            if start_ts - 1.5 * 86400 <= ts_sec <= end_ts + 1.5 * 86400:
                return wk

        if week_ranges[0][0] == 1 and ts_sec < week_ranges[0][1] - 2 * 86400:
            return 0

        closest_wk, c_start, c_end = min(
            week_ranges,
            key=lambda r: min(abs(ts_sec - r[1]), abs(ts_sec - r[2])),
        )
        anchor_mid = (c_start + c_end) / 2.0
        delta_weeks = round((ts_sec - anchor_mid) / (7.0 * 86400.0))
        inferred_wk = closest_wk + int(delta_weeks)
        if inferred_wk >= 1:
            return min(18, inferred_wk)

    days_since_w1 = (ts_sec - w1_rollover_anchor_sec) / 86400.0
    if days_since_w1 < 0:
        return 1
    return max(1, min(18, int(days_since_w1 // 7) + 1))


def normalize_communication_topics_to_transactions(
    topics: list[dict[str, Any]],
    raw_txs: list[dict[str, Any]] | None = None,
    session: Session | None = None,
    season_year: int | None = None,
) -> list[dict[str, Any]]:
    """Convert executed trade topics from kona_league_communication into normalized transactions.

    Args:
        topics: List of topic dictionaries from kona_league_communication.
        raw_txs: Optional list of raw transactions used to derive exact timestamp boundaries per week.
        session: Optional SQLAlchemy session for cross-referencing stored season transactions.
        season_year: Optional season year for DB transaction/snapshot week lookup.

    Returns:
        List of normalized transaction dictionaries suitable for upsert_transactions_from_payload.
    """
    tx_by_week: dict[int, list[float]] = defaultdict(list)
    tx_week_by_id: dict[str, int] = {}
    tx_prop_date_by_id: dict[str, Any] = {}
    prop_team_by_id: dict[str, int] = {}

    def _ingest_tx_meta(tx: dict[str, Any]) -> None:
        w_val = (
            tx.get("matchupPeriodId")
            if tx.get("matchupPeriodId") is not None
            else tx.get("week", tx.get("scoringPeriodId", 0))
        )
        try:
            w_int = int(w_val or 0)
        except (ValueError, TypeError):
            w_int = 0

        ts = (
            tx.get("proposedDate")
            or tx.get("executionDate")
            or tx.get("proposed_at")
            or tx.get("executed_at")
        )
        t_sec: float | None = None
        if ts:
            if isinstance(ts, (int, float)):
                t_sec = ts / 1000.0 if ts > 1e11 else float(ts)
            elif isinstance(ts, str):
                try:
                    t_sec = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                except ValueError:
                    pass

        if w_int > 0 and t_sec:
            dt_check = datetime.fromtimestamp(t_sec, tz=UTC)
            if dt_check.month >= 9 or dt_check.month <= 2:
                tx_by_week[w_int].append(t_sec)

        tid = str(tx.get("id") or "")
        rel_id = str(tx.get("relatedTransactionId") or "")
        if w_int > 0 or (w_int == 0 and t_sec and datetime.fromtimestamp(t_sec, tz=UTC).month <= 8):
            if tid:
                tx_week_by_id[tid] = w_int
            if rel_id:
                tx_week_by_id[rel_id] = w_int

        tx_type_str = str(tx.get("type", "")).upper()
        if tx_type_str == "TRADE_PROPOSAL":
            if tx.get("teamId"):
                if tid:
                    prop_team_by_id[tid] = int(tx["teamId"])
                if rel_id:
                    prop_team_by_id[rel_id] = int(tx["teamId"])
            if tx.get("proposedDate"):
                if tid:
                    tx_prop_date_by_id[tid] = tx["proposedDate"]
                if rel_id:
                    tx_prop_date_by_id[rel_id] = tx["proposedDate"]

    for tx in raw_txs or []:
        if isinstance(tx, dict):
            _ingest_tx_meta(tx)

    if session is not None and season_year is not None:
        try:
            snaps = (
                session.query(RawEspnSnapshot)
                .filter(RawEspnSnapshot.season_year == season_year)
                .all()
            )
            for snap in snaps:
                if isinstance(snap.payload, dict):
                    for stx in snap.payload.get("transactions") or []:
                        if isinstance(stx, dict):
                            _ingest_tx_meta(stx)
            db_txs = (
                session.query(Transaction)
                .filter(Transaction.season_year == season_year)
                .all()
            )
            for dtx in db_txs:
                dt_obj = dtx.executed_at or dtx.proposed_at
                if dt_obj is not None:
                    t_sec = dt_obj.timestamp()
                    dt_utc = datetime.fromtimestamp(t_sec, tz=UTC)
                    if dtx.week and dtx.week > 0 and (dt_utc.month >= 9 or dt_utc.month <= 2):
                        tx_by_week[dtx.week].append(t_sec)
                        tx_week_by_id.setdefault(dtx.espn_transaction_id, dtx.week)
                        if dtx.related_espn_transaction_id:
                            tx_week_by_id.setdefault(dtx.related_espn_transaction_id, dtx.week)
        except Exception:
            pass

    week_ranges: list[tuple[int, float, float]] = []
    for wk, ts_list in tx_by_week.items():
        if ts_list:
            week_ranges.append((wk, min(ts_list), max(ts_list)))
    week_ranges.sort(key=lambda r: r[0])

    exec_topics: list[dict[str, Any]] = []
    prop_topics: list[dict[str, Any]] = []

    for t in topics:
        msgs = t.get("messages", [])
        m_types = {m.get("messageTypeId") for m in msgs}
        if m_types & {244, 246}:
            exec_topics.append(t)
        elif 224 in m_types:
            prop_topics.append(t)

    def _topic_fingerprint(t: dict[str, Any]) -> tuple[frozenset[int], frozenset[int]]:
        msgs = t.get("messages", [])
        teams: set[int] = set()
        assets: set[int] = set()
        for m in msgs:
            if m.get("from") and int(m.get("from")) > 0:
                teams.add(int(m.get("from")))
            if m.get("to") and int(m.get("to")) > 0:
                teams.add(int(m.get("to")))
            if m.get("messageTypeId") in (224, 244, 246) and m.get("targetId") is not None:
                try:
                    assets.add(int(m.get("targetId")))
                except (ValueError, TypeError):
                    pass
        return frozenset(teams), frozenset(assets)

    exec_fingerprints = [_topic_fingerprint(t) for t in exec_topics]
    used_exec_indices: set[int] = set()

    filtered_prop_topics: list[dict[str, Any]] = []
    for pt in prop_topics:
        p_teams, p_assets = _topic_fingerprint(pt)
        pt_date = float(pt.get("date") or 0)
        matched_exec: dict[str, Any] | None = None
        for i, (e_teams, e_assets) in enumerate(exec_fingerprints):
            if i in used_exec_indices:
                continue
            et_date = float(exec_topics[i].get("date") or 0)
            date_ok = (not pt_date or not et_date) or abs(et_date - pt_date) <= 10 * 86400 * 1000
            if p_teams == e_teams and (p_assets & e_assets) and date_ok:
                matched_exec = exec_topics[i]
                used_exec_indices.add(i)
                break

        if matched_exec is not None:
            pt_id = str(pt.get("targetId") or pt.get("id"))
            matched_exec["matched_proposal_id"] = pt_id
            if pt.get("date") and not matched_exec.get("proposed_date"):
                matched_exec["proposed_date"] = pt.get("date")
            pt_faab_msgs = [m for m in pt.get("messages", []) if m.get("messageTypeId") in (284, 290)]
            exec_faab_msgs = [m for m in matched_exec.get("messages", []) if m.get("messageTypeId") in (284, 290)]
            if pt_faab_msgs and not exec_faab_msgs:
                matched_exec.setdefault("messages", []).extend(pt_faab_msgs)
        else:
            pt_id = str(pt.get("targetId") or pt.get("id"))
            is_confirmed_executed = any(
                (str(tx.get("id")) == pt_id or str(tx.get("relatedTransactionId")) == pt_id)
                and (
                    str(tx.get("status", "")).upper() == "EXECUTED"
                    or str(tx.get("type", "")).upper() in ("TRADE_ACCEPT", "TRADE_UPHOLD")
                )
                for tx in (raw_txs or [])
            )
            if is_confirmed_executed:
                filtered_prop_topics.append(pt)

    candidate_topics = exec_topics + filtered_prop_topics

    converted: list[dict[str, Any]] = []
    for t in candidate_topics:
        msgs = t.get("messages", [])
        trade_msgs = [m for m in msgs if m.get("messageTypeId") in (224, 244, 246)]
        if not trade_msgs:
            continue

        tx_id = str(t.get("targetId") or t.get("id"))
        matched_prop_id = str(t.get("matched_proposal_id") or "")
        ts_ms = t.get("date", 0)
        ts_sec = ts_ms / 1000.0 if ts_ms > 1e11 else float(ts_ms)
        prop_ts_ms = (
            tx_prop_date_by_id.get(tx_id)
            or (tx_prop_date_by_id.get(matched_prop_id) if matched_prop_id else None)
            or t.get("proposed_date")
            or ts_ms
        )

        if tx_id in tx_week_by_id:
            w = tx_week_by_id[tx_id]
        elif matched_prop_id and matched_prop_id in tx_week_by_id:
            w = tx_week_by_id[matched_prop_id]
        else:
            w = _infer_nfl_week_from_timestamp(ts_sec, week_ranges, default_season_year=season_year)

        items: list[dict[str, Any]] = []
        faab_prop = 0
        faab_acc = 0
        faab_by_from_team: dict[int, int] = {}

        teams_in_trade: set[int] = set()
        for m in trade_msgs:
            if m.get("from"):
                teams_in_trade.add(int(m.get("from")))
            if m.get("to"):
                teams_in_trade.add(int(m.get("to")))

        known_prop_team = prop_team_by_id.get(tx_id) or (
            prop_team_by_id.get(matched_prop_id) if matched_prop_id else None
        )
        if known_prop_team and known_prop_team in teams_in_trade:
            prop_team = known_prop_team
            other_teams = teams_in_trade - {prop_team}
            acc_team = next(iter(other_teams)) if other_teams else None
        else:
            t_list = sorted(list(teams_in_trade))
            prop_team = t_list[0] if len(t_list) > 0 else None
            acc_team = t_list[1] if len(t_list) > 1 else None

        for m in msgs:
            mt = m.get("messageTypeId")
            if mt in (224, 244):
                items.append({
                    "type": "TRADE",
                    "playerId": m.get("targetId"),
                    "fromTeamId": m.get("from"),
                    "toTeamId": m.get("to"),
                })
            elif mt == 246:
                items.append({
                    "type": "DRAFT_TRADE",
                    "playerId": 0,
                    "overallPickNumber": m.get("targetId"),
                    "fromTeamId": m.get("from"),
                    "toTeamId": m.get("to"),
                })
            elif mt == 245:
                items.append({
                    "type": "DROP",
                    "playerId": m.get("targetId"),
                    "fromTeamId": m.get("from"),
                    "toTeamId": 0,
                })
            elif mt in (284, 290):
                from_id = m.get("from")
                if from_id is not None:
                    try:
                        from_int = int(from_id)
                        faab_by_from_team[from_int] = faab_by_from_team.get(from_int, 0) + int(m.get("targetId", 0))
                    except (ValueError, TypeError):
                        pass
                if m.get("from") == prop_team:
                    faab_prop += int(m.get("targetId", 0))
                else:
                    faab_acc += int(m.get("targetId", 0))

        converted.append({
            "id": tx_id,
            "relatedTransactionId": t.get("matched_proposal_id"),
            "type": "TRADE_ACCEPT",
            "status": "EXECUTED",
            "executionType": "PROCESS",
            "scoringPeriodId": w,
            "matchupPeriodId": w,
            "week": w,
            "executionDate": ts_ms,
            "proposedDate": prop_ts_ms,
            "proposingTeamId": prop_team,
            "acceptingTeamId": acc_team,
            "faabFromProposer": faab_prop,
            "faabFromAccepter": faab_acc,
            "faabByFromTeam": faab_by_from_team,
            "items": items,
        })

    return converted


def upsert_transactions_from_payload(
    session: Session,
    season: Season,
    payload: dict[str, Any],
    team_lookup: dict[int, Team],
    weeks: list[int] | None = None,
    scoring_periods: list[int] | None = None,
) -> list[Transaction]:
    """Parse transactions, FAAB bidding war receipts, and deduplicated bilateral trades.

    Args:
        session: Active SQLAlchemy session.
        season: Upserted Season ORM entity.
        payload: ESPN league payload containing transactions array.
        team_lookup: Mapping of espn_team_id -> Team instance.
        weeks: Optional list of scoring weeks to filter (for weekly sync).
        scoring_periods: Optional list of scoring periods to filter (for weekly sync).

    Returns:
        List of upserted Transaction ORM instances.
    """
    raw_txs: list[dict[str, Any]] = list(payload.get("transactions", []))
    topics = payload.get("topics", []) or payload.get("communication", {}).get("topics", [])
    trade_overrides = get_combined_trade_overrides(session)
    deleted_trade_ids = set(trade_overrides.get("deleted_trades", []))
    edited_trades = trade_overrides.get("edited_trades", {})
    payload_pick_order, payload_draft_type = pick_order_from_payload(payload)
    if topics:
        converted_trades = normalize_communication_topics_to_transactions(
            topics,
            raw_txs=raw_txs,
            session=session,
            season_year=season.season_year,
        )
        existing_txs_by_rel_id = {
            str(tx.get("relatedTransactionId")): tx
            for tx in raw_txs
            if tx.get("relatedTransactionId")
        }
        for ctx in converted_trades:
            ctx_id = str(ctx.get("id"))
            if ctx_id in existing_txs_by_rel_id:
                rel_tx = existing_txs_by_rel_id[ctx_id]
                rel_items = rel_tx.setdefault("items", [])
                existing_item_keys = {
                    (
                        str(it.get("type", "")).upper(),
                        int(it.get("playerId") or 0),
                        int(it.get("overallPickNumber") or 0),
                        it.get("fromTeamId"),
                        it.get("toTeamId"),
                    )
                    for it in rel_items
                }
                for item in ctx.get("items", []):
                    key = (
                        str(item.get("type", "")).upper(),
                        int(item.get("playerId") or 0),
                        int(item.get("overallPickNumber") or 0),
                        item.get("fromTeamId"),
                        item.get("toTeamId"),
                    )
                    if key not in existing_item_keys:
                        rel_items.append(item)
                        existing_item_keys.add(key)
                if "faabByFromTeam" in ctx and "faabByFromTeam" not in rel_tx:
                    rel_tx["faabByFromTeam"] = ctx["faabByFromTeam"]

        # Prepend converted trades so executed topic trades process first
        conv_ids = {str(c.get("id")) for c in converted_trades}
        raw_txs = converted_trades + [tx for tx in raw_txs if str(tx.get("id")) not in conv_ids]

    # Ensure any manual trades defined in overrides are present in raw_txs
    if season.season_year >= 2018:
        existing_raw_ids = {str(tx.get("id")) for tx in raw_txs}
        for e_id, e_val in edited_trades.items():
            if (
                e_id not in existing_raw_ids
                and e_val.get("season_year") == season.season_year
                and (e_val.get("is_manual") or str(e_id).startswith("manual-trade-"))
            ):
                raw_txs.append({
                    "id": e_id,
                    "type": "TRADE",
                    "status": "EXECUTED",
                    "executionType": "PROCESS",
                    "scoringPeriodId": e_val.get("week", 1),
                    "matchupPeriodId": e_val.get("week", 1),
                    "week": e_val.get("week", 1),
                    "proposingTeamId": e_val.get("proposing_espn_team_id") or e_val.get("proposing_team_id"),
                    "acceptingTeamId": e_val.get("accepting_espn_team_id") or e_val.get("accepting_team_id"),
                    "items": [],
                })

    if not raw_txs and "leagueCommunication" in payload:
        raw_txs = payload.get("leagueCommunication", {}).get("topics", [])

    if not raw_txs:
        existing_count = (
            session.query(Transaction)
            .filter_by(season_year=season.season_year)
            .count()
        )
        if existing_count == 0 and (season.season_year < 2018 or season.is_completed):
            season.has_transaction_data = False
        return []

    season.has_transaction_data = True
    upsert_players_from_payload(session, payload)

    # 1. Build map of winning waiver claims to link losing bids (FAAB Bidding Wars)
    # (week, player_id) -> winning_espn_transaction_id
    executed_waiver_wins: dict[tuple[int, int], str] = {}
    for raw in raw_txs:
        raw_type = str(raw.get("type", "WAIVER")).upper()
        raw_status = str(raw.get("status", "EXECUTED")).upper()
        if raw_type == "WAIVER" and raw_status in ("EXECUTED", "SUCCESS"):
            tx_id = str(raw.get("id"))
            w = int(raw.get("matchupPeriodId", raw.get("scoringPeriodId", 0)))
            sp = int(raw.get("scoringPeriodId", 0))
            for item in raw.get("items", []):
                pid = int(
                    item.get("playerId")
                    or item.get("playerPoolEntry", {}).get("player", {}).get("id")
                    or 0
                )
                if pid:
                    if w:
                        executed_waiver_wins[(w, pid)] = tx_id
                    if sp:
                        executed_waiver_wins[(sp, pid)] = tx_id

    # Also include existing executed waiver wins in DB
    existing_db_wins = (
        session.query(Transaction)
        .filter(
            Transaction.season_year == season.season_year,
            Transaction.transaction_type == "WAIVER",
            Transaction.status == "EXECUTED",
        )
        .all()
    )
    for db_tx in existing_db_wins:
        for item in db_tx.items:
            if item.item_type == "ADD":
                if db_tx.week:
                    executed_waiver_wins[(db_tx.week, item.player_id)] = db_tx.espn_transaction_id
                if db_tx.scoring_period:
                    executed_waiver_wins[(db_tx.scoring_period, item.player_id)] = db_tx.espn_transaction_id

    # Track proposals, vetoes, and finalized executed trades
    proposal_items_by_id: dict[str, list[dict[str, Any]]] = {}
    vetoed_proposal_ids: set[str] = set()
    accepted_proposal_ids: set[str] = set()
    executed_trade_tx_ids: set[str] = set()
    proposal_to_executed_tx: dict[str, str] = {}

    for raw in raw_txs:
        r_type = str(raw.get("type", "")).upper()
        r_id = str(raw.get("id", ""))
        r_rel = str(raw.get("relatedTransactionId") or "")
        r_status = str(raw.get("status") or "").upper()
        r_exec = str(raw.get("executionType") or "").upper()

        if raw.get("items"):
            if r_id:
                proposal_items_by_id.setdefault(r_id, []).extend(raw.get("items"))
            if r_rel:
                proposal_items_by_id.setdefault(r_rel, []).extend(raw.get("items"))

        if r_type == "TRADE_PROPOSAL" and r_id:
            pass
        elif r_type == "TRADE_VETO" and r_status == "EXECUTED" and r_exec == "PROCESS" and r_rel:
            vetoed_proposal_ids.add(r_rel)
        elif r_type in ("TRADE_ACCEPT", "TRADE"):
            if r_status in ("EXECUTED", "SUCCESS") or r_exec == "PROCESS":
                executed_trade_tx_ids.add(r_id)
                if r_rel and (r_rel not in proposal_to_executed_tx or r_exec == "PROCESS"):
                    proposal_to_executed_tx[r_rel] = r_id

    vetoed_proposal_ids -= set(proposal_to_executed_tx.keys()) | executed_trade_tx_ids

    processed_tx_ids: set[str] = set()
    executed_proposal_ids: set[str] = set()
    upserted_transactions: list[Transaction] = []
    valid_trade_ids: set[int] = set()

    for raw in raw_txs:
        espn_tx_id = str(raw.get("id", ""))
        if not espn_tx_id:
            continue

        raw_type = str(raw.get("type", "WAIVER")).upper()
        raw_status_val = raw.get("status")
        raw_status = str(raw_status_val or "EXECUTED").upper() if raw_status_val is not None else ""
        raw_exec = str(raw.get("executionType") or "").upper()
        related_id = raw.get("relatedTransactionId") or raw.get("related_espn_transaction_id")

        # Skip deleted trades (commissioner override)
        if espn_tx_id in deleted_trade_ids or (related_id and str(related_id) in deleted_trade_ids):
            cand_trade = (
                session.query(Trade)
                .filter(
                    Trade.season_year == season.season_year,
                    or_(
                        Trade.espn_transaction_id == espn_tx_id,
                        Trade.espn_transaction_id == str(related_id),
                    ),
                )
                .first()
            )
            if cand_trade:
                cand_trade.status = "DELETED"
            cand_txs = (
                session.query(Transaction)
                .filter(
                    Transaction.season_year == season.season_year,
                    or_(
                        Transaction.espn_transaction_id == espn_tx_id,
                        Transaction.espn_transaction_id == str(related_id),
                        Transaction.related_espn_transaction_id == espn_tx_id,
                        Transaction.related_espn_transaction_id == str(related_id),
                    ),
                )
                .all()
            )
            for ctx in cand_txs:
                ctx.status = "CANCELED"
            continue

        # Skip intermediate proposals/declines/veto-votes and unexecuted pending claims
        if raw_type in ("TRADE_PROPOSAL", "TRADE_DECLINE", "TRADE_VETO"):
            continue
        if raw_status == "PENDING":
            continue

        # Skip lineup-only ROSTER transactions
        if raw_type == "ROSTER":
            non_lineup = [
                it for it in (raw.get("items") or [])
                if str(it.get("type", "")).upper() not in ("LINEUP", "")
            ]
            if not non_lineup:
                continue

        # Trade deduplication & voting phase handling:
        # In ESPN, trades progress: PROPOSAL -> ACCEPT (pending voting) -> UPHOLD/VETO -> PROCESS (execution).
        # If an executed PROCESS record exists for this proposal, skip duplicate acceptance/uphold steps.
        if espn_tx_id in proposal_to_executed_tx and espn_tx_id != proposal_to_executed_tx[espn_tx_id]:
            logger.debug(
                "Skipping proposal/topic %s superseded by finalized trade %s",
                espn_tx_id,
                proposal_to_executed_tx[espn_tx_id],
            )
            continue
        if raw_type in ("TRADE_ACCEPT", "TRADE_UPHOLD") and related_id:
            rel_str = str(related_id)
            if rel_str in proposal_to_executed_tx and espn_tx_id != proposal_to_executed_tx[rel_str]:
                logger.debug(
                    "Skipping duplicate trade step %s for finalized trade %s",
                    espn_tx_id,
                    proposal_to_executed_tx[rel_str],
                )
                continue
            if rel_str in processed_tx_ids or rel_str in executed_proposal_ids:
                logger.debug("Skipping duplicate trade step %s for %s", espn_tx_id, rel_str)
                continue
            if rel_str in vetoed_proposal_ids:
                logger.debug("Skipping trade step %s for vetoed trade %s", espn_tx_id, rel_str)
                continue

        # Skip intermediate owner-approval or uphold-vote records that contain no TRADE items
        if (
            raw_type in ("TRADE_ACCEPT", "TRADE_UPHOLD")
            and not raw_status_val
            and raw_exec == "EXECUTE"
        ):
            has_trade_items = any(
                str(it.get("type", "")).upper() in ("TRADE", "DRAFT_TRADE")
                for it in (raw.get("items") or [])
            )
            if not has_trade_items:
                continue

        if raw_type in ("TRADE_ACCEPT", "TRADE_UPHOLD") and related_id:
            accepted_proposal_ids.add(str(related_id))
            if raw_status_val == "EXECUTED" or raw_exec == "PROCESS":
                executed_proposal_ids.add(str(related_id))

        sp = int(raw.get("scoringPeriodId", raw.get("scoring_period", 0)))
        raw_matchup_period = raw.get("matchupPeriodId")
        if raw_matchup_period is not None:
            w = int(raw_matchup_period)
        elif raw.get("week") is not None:
            w = int(raw.get("week"))
        else:
            w = sp

        # Normalize type
        if raw_type in ("FREEAGENT", "FREE_AGENT", "FA"):
            tx_type = "FREE_AGENT"
        elif raw_type == "WAIVER":
            tx_type = "WAIVER"
        elif raw_type == "DROP":
            tx_type = "DROP"
        elif raw_type == "ROSTER":
            item_types = {str(it.get("type", "")).upper() for it in (raw.get("items") or [])}
            tx_type = "FREE_AGENT" if "ADD" in item_types else "DROP"
        elif raw_type in ("TRADE_ACCEPT", "TRADE_UPHOLD", "TRADE"):
            tx_type = "TRADE"
        else:
            tx_type = raw_type

        # Incremental filter by week or scoring period (waivers and adds only; never skip trades)
        if tx_type != "TRADE":
            if weeks is not None and w not in weeks:
                continue
            if scoring_periods is not None and sp not in scoring_periods:
                continue

        # Normalize status & failure reason
        failure_reason: str | None = None

        if raw_type == "TRADE_ACCEPT" and related_id and str(related_id) in vetoed_proposal_ids:
            status = "VETOED"
        elif raw_status in ("WAIVER_ERROR", "FAILED_ROSTER_LIMIT", "FAILED_OUTBID", "FAILED_INSUFFICIENT_FUNDS") or raw_status.startswith("FAILED"):
            status = "FAILED"
            msg = f"{raw.get('processMessage', '')} {raw.get('failureReason', '')} {raw_status} {raw.get('comment', '')}".upper()
            if any(term in msg for term in ("INSUFFICIENT", "BUDGET", "FUNDS", "NOT ENOUGH")):
                failure_reason = "INSUFFICIENT_FUNDS"
            elif any(term in msg for term in ("ROSTER", "LIMIT", "FULL", "MAX PLAYERS")):
                failure_reason = "ROSTER_LIMIT"
            elif any(term in msg for term in ("OUTBID", "PRIORITY", "LOWER", "INVALIDPLAYERSOURCE")) or int(raw.get("bidAmount", 0)) > 0:
                failure_reason = "OUTBID"
            elif any(term in msg for term in ("ALREADY", "CLAIMED", "TAKEN", "ROSTERED", "PLAYERALREADYDROPPED")):
                failure_reason = "ALREADY_CLAIMED"
            else:
                failure_reason = "INVALID_CLAIM"
        elif raw_status in ("CANCELED", "CANCELLED"):
            status = "CANCELED"
        elif raw_status == "VETOED" or (raw_type == "TRADE_ACCEPT" and related_id and str(related_id) in vetoed_proposal_ids):
            status = "VETOED"
        elif raw_type in ("TRADE_ACCEPT", "TRADE") and not raw_status_val and raw_exec != "PROCESS":
            status = "PENDING"
        else:
            status = "EXECUTED"

        # Link failed waiver bids to winning waiver claim on the same player in that week/scoring period
        if status == "FAILED" and tx_type == "WAIVER":
            winning_claim_id = None
            for item in (raw.get("items") or []):
                if str(item.get("type", "ADD")).upper() not in ("ADD", ""):
                    continue
                pid = int(
                    item.get("playerId")
                    or item.get("playerPoolEntry", {}).get("player", {}).get("id")
                    or 0
                )
                if (w, pid) in executed_waiver_wins:
                    winning_claim_id = executed_waiver_wins[(w, pid)]
                    break
                if (sp, pid) in executed_waiver_wins:
                    winning_claim_id = executed_waiver_wins[(sp, pid)]
                    break
            if winning_claim_id:
                related_id = winning_claim_id

        bid_amount = int(raw.get("bidAmount", 0))
        sub_order = raw.get("subOrder")
        waiver_prio = int(sub_order) if sub_order is not None else raw.get("waiverPriority")
        proposed_at = _parse_espn_timestamp(raw.get("proposedDate") or raw.get("proposed_at") or raw.get("date"))
        executed_at = _parse_espn_timestamp(
            raw.get("executionDate")
            or raw.get("processDate")
            or raw.get("executed_at")
            or raw.get("acceptedDate")
            or raw.get("date")
        )
        is_commish = bool(
            raw.get("isCommissionerOverride", False)
            or raw.get("isActingAsTeamOwner") is False
        )

        espn_team_id = raw.get("teamId")
        team_id = team_lookup[espn_team_id].id if espn_team_id in team_lookup else None

        edit_data = edited_trades.get(espn_tx_id) or (
            edited_trades.get(str(related_id)) if related_id else None
        )
        if tx_type == "TRADE" and edit_data and edit_data.get("week") is not None:
            w = int(edit_data["week"])

        tx = (
            session.query(Transaction)
            .filter_by(season_year=season.season_year, espn_transaction_id=espn_tx_id)
            .first()
        )
        if not tx:
            tx = Transaction(
                season_year=season.season_year,
                week=w,
                scoring_period=sp,
                espn_transaction_id=espn_tx_id,
                transaction_type=tx_type,
                status=status,
                team_id=team_id,
                bid_amount=bid_amount,
                waiver_priority=waiver_prio,
                failure_reason=failure_reason,
                proposed_at=proposed_at,
                executed_at=executed_at,
                is_commissioner_override=is_commish,
                related_espn_transaction_id=related_id,
                raw_summary=raw.get("raw_summary", raw.get("summary", {})),
            )
            session.add(tx)
            session.flush()
        else:
            tx.week = w
            tx.scoring_period = sp
            tx.transaction_type = tx_type
            tx.status = status
            tx.team_id = team_id
            tx.bid_amount = bid_amount
            tx.waiver_priority = waiver_prio
            tx.failure_reason = failure_reason
            if proposed_at:
                tx.proposed_at = proposed_at
            if executed_at:
                tx.executed_at = executed_at
            tx.is_commissioner_override = is_commish
            tx.related_espn_transaction_id = related_id

        if tx_type == "TRADE" and related_id and str(related_id) != espn_tx_id:
            superseded_tx = (
                session.query(Transaction)
                .filter_by(season_year=season.season_year, espn_transaction_id=str(related_id))
                .first()
            )
            if superseded_tx and superseded_tx.id != tx.id:
                session.query(TransactionItem).filter_by(transaction_id=superseded_tx.id).delete()
                session.delete(superseded_tx)
                session.flush()

        is_commish_edited = (
            tx_type == "TRADE"
            and (
                bool(edit_data)
                or bool(
                    tx.raw_summary
                    and isinstance(tx.raw_summary, dict)
                    and tx.raw_summary.get("commissioner_edited")
                )
            )
        )

        items_to_add: list[TransactionItem] = []
        used_override_sides = False
        if is_commish_edited and edit_data and len(edit_data.get("sides", [])) >= 2:
            sides = edit_data["sides"]
            side_a = sides[0]
            side_b = sides[1]
            side_a_tid = _resolve_side_team_id(side_a, season.season_year, session, team_lookup)
            side_b_tid = _resolve_side_team_id(side_b, season.season_year, session, team_lookup)

            if side_a_tid and side_b_tid:
                used_override_sides = True
                session.query(TransactionItem).filter_by(transaction_id=tx.id).delete()
                # Side A receives from Side B
                for p_id in side_a.get("player_ids", []):
                    pid = int(p_id)
                    if not session.get(Player, pid):
                        session.add(Player(espn_player_id=pid, full_name=f"Player {pid}", default_position="FLEX", pro_team="FA"))
                        session.flush()
                    items_to_add.append(TransactionItem(
                        transaction_id=tx.id,
                        player_id=pid,
                        from_team_id=side_b_tid,
                        to_team_id=side_a_tid,
                        item_type="TRADE",
                    ))
                for pick_obj in side_a.get("draft_picks", []):
                    items_to_add.append(
                        build_pick_trade_item(
                            session,
                            transaction_id=tx.id,
                            pick=pick_obj,
                            default_season=season.season_year,
                            from_team_id=side_b_tid,
                            to_team_id=side_a_tid,
                        )
                    )

                # Side B receives from Side A
                for p_id in side_b.get("player_ids", []):
                    pid = int(p_id)
                    if not session.get(Player, pid):
                        session.add(Player(espn_player_id=pid, full_name=f"Player {pid}", default_position="FLEX", pro_team="FA"))
                        session.flush()
                    items_to_add.append(TransactionItem(
                        transaction_id=tx.id,
                        player_id=pid,
                        from_team_id=side_a_tid,
                        to_team_id=side_b_tid,
                        item_type="TRADE",
                    ))
                for pick_obj in side_b.get("draft_picks", []):
                    items_to_add.append(
                        build_pick_trade_item(
                            session,
                            transaction_id=tx.id,
                            pick=pick_obj,
                            default_season=season.season_year,
                            from_team_id=side_a_tid,
                            to_team_id=side_b_tid,
                        )
                    )

                session.add_all(items_to_add)
                session.flush()

        if not used_override_sides:
            if is_commish_edited and not edit_data and tx.items:
                items_to_add = list(tx.items)
            else:
                # Normalize and upsert transaction items from ESPN
                session.query(TransactionItem).filter_by(transaction_id=tx.id).delete()

                raw_items = list(raw.get("items") or [])
                if tx_type == "TRADE":
                    item_sources = []
                    if related_id and str(related_id) in proposal_items_by_id:
                        item_sources.extend(proposal_items_by_id[str(related_id)])
                    if espn_tx_id in proposal_items_by_id:
                        item_sources.extend(proposal_items_by_id[espn_tx_id])
                    existing_pids = {int(it.get("playerId") or 0) for it in raw_items}
                    existing_picks = {int(it.get("overallPickNumber") or 0) for it in raw_items}
                    for prop_item in item_sources:
                        prop_pid = int(prop_item.get("playerId") or 0)
                        prop_pick = int(prop_item.get("overallPickNumber") or 0)
                        if prop_pid and prop_pid not in existing_pids:
                            raw_items.append(prop_item)
                            existing_pids.add(prop_pid)
                        elif prop_pick and not any(int(it.get("overallPickNumber") or 0) == prop_pick for it in raw_items):
                            raw_items.append(prop_item)
                            existing_picks.add(prop_pick)

                for item in raw_items:
                    raw_item_type = str(item.get("type", "")).upper()
                    if raw_item_type == "LINEUP":
                        continue

                    pick_num = int(item.get("overallPickNumber") or 0)
                    pid = int(
                        item.get("playerId")
                        or item.get("playerPoolEntry", {}).get("player", {}).get("id")
                        or item.get("player", {}).get("id", 0)
                    )

                    # Support draft pick trades (DRAFT_TRADE items with overallPickNumber)
                    if (raw_item_type == "DRAFT_TRADE" or pick_num > 0) and not pid:
                        pid = -100000 - pick_num
                        league_size = len(team_lookup) if team_lookup else 12
                        round_num = ((pick_num - 1) // league_size) + 1
                        pick_in_round = ((pick_num - 1) % league_size) + 1
                        pick_name = f"Round {round_num} Pick #{pick_num} (Pick {round_num}.{pick_in_round:02d})"
                        if not session.get(Player, pid):
                            session.add(
                                Player(
                                    espn_player_id=pid,
                                    full_name=pick_name,
                                    default_position="PICK",
                                    pro_team="DRAFT",
                                )
                            )
                            session.flush()

                    if not pid:
                        continue

                    # Ensure player exists
                    if not session.get(Player, pid):
                        session.add(
                            Player(
                                espn_player_id=pid,
                                full_name=f"Player {pid}",
                                default_position="FLEX",
                                pro_team="FA",
                            )
                        )
                        session.flush()

                    from_espn = item.get("fromTeamId")
                    to_espn = item.get("toTeamId")
                    from_tid = team_lookup[from_espn].id if from_espn in team_lookup else None
                    to_tid = team_lookup[to_espn].id if to_espn in team_lookup else None

                    if raw_item_type in ("ADD", "DROP", "TRADE", "DRAFT_TRADE"):
                        item_type = "TRADE" if raw_item_type == "DRAFT_TRADE" else raw_item_type
                    elif from_tid and to_tid and from_tid != to_tid:
                        item_type = "TRADE"
                    elif to_tid and not from_tid:
                        item_type = "ADD"
                    elif from_tid and not to_tid:
                        item_type = "DROP"
                    else:
                        item_type = "ADD"

                    t_item = TransactionItem(
                        transaction_id=tx.id,
                        player_id=pid,
                        from_team_id=from_tid,
                        to_team_id=to_tid,
                        item_type=item_type,
                    )
                    if raw_item_type == "DRAFT_TRADE" or pick_num > 0:
                        attach_espn_pick_identity(
                            t_item,
                            season_year=season.season_year,
                            overall_pick=pick_num,
                            pick_order=payload_pick_order,
                            draft_type=payload_draft_type,
                            league_size=len(team_lookup) if team_lookup else 12,
                        )
                        if t_item.traded_pick and t_item.traded_pick.original_espn_team_id is None and from_espn:
                            t_item.traded_pick.original_espn_team_id = int(from_espn)
                    items_to_add.append(t_item)

                if tx_type == "TRADE" and edit_data and edit_data.get("supplemental_picks"):
                    prop_fallback_tid = _resolve_team_id(
                        edit_data.get("proposing_espn_team_id") or raw.get("proposingTeamId"),
                        season.season_year,
                        session,
                        team_lookup,
                        prefer_espn_id=True,
                    )
                    acc_fallback_tid = _resolve_team_id(
                        edit_data.get("accepting_espn_team_id") or raw.get("acceptingTeamId"),
                        season.season_year,
                        session,
                        team_lookup,
                        prefer_espn_id=True,
                    )
                    for sp_pick in edit_data["supplemental_picks"]:
                        raw_to = (
                            sp_pick.get("to_espn_team_id")
                            or sp_pick.get("receiving_espn_team_id")
                            or sp_pick.get("to_team_id")
                        )
                        prefer_to_espn = (
                            sp_pick.get("to_espn_team_id") is not None
                            or sp_pick.get("receiving_espn_team_id") is not None
                        )
                        to_tid = _resolve_team_id(
                            raw_to,
                            season.season_year,
                            session,
                            team_lookup,
                            prefer_espn_id=prefer_to_espn,
                        )
                        raw_from = sp_pick.get("from_espn_team_id") or sp_pick.get("from_team_id")
                        from_tid = _resolve_team_id(
                            raw_from,
                            season.season_year,
                            session,
                            team_lookup,
                            prefer_espn_id=sp_pick.get("from_espn_team_id") is not None,
                        )
                        if not from_tid and to_tid and prop_fallback_tid and acc_fallback_tid:
                            from_tid = acc_fallback_tid if to_tid == prop_fallback_tid else prop_fallback_tid
                        if to_tid and from_tid:
                            items_to_add.append(
                                build_pick_trade_item(
                                    session,
                                    transaction_id=tx.id,
                                    pick=sp_pick,
                                    default_season=season.season_year,
                                    from_team_id=from_tid,
                                    to_team_id=to_tid,
                                )
                            )

                session.add_all(items_to_add)
                session.flush()

        # If executed trade, upsert Trade record
        if tx_type == "TRADE" and status == "EXECUTED":
            prop_espn = raw.get("proposingTeamId")
            acc_espn = raw.get("acceptingTeamId")

            proposing_team_id = team_lookup[prop_espn].id if prop_espn in team_lookup else None
            accepting_team_id = team_lookup[acc_espn].id if acc_espn in team_lookup else None

            if is_commish_edited and edit_data:
                if len(edit_data.get("sides", [])) >= 2:
                    side_a_tid = _resolve_side_team_id(edit_data["sides"][0], season.season_year, session, team_lookup)
                    side_b_tid = _resolve_side_team_id(edit_data["sides"][1], season.season_year, session, team_lookup)
                    if side_a_tid and side_b_tid:
                        proposing_team_id = side_a_tid
                        accepting_team_id = side_b_tid
                if edit_data.get("week") is not None:
                    w = int(edit_data["week"])

            if not proposing_team_id or not accepting_team_id:
                # Infer from transaction items
                teams_in_trade = set()
                for it in items_to_add:
                    if it.from_team_id:
                        teams_in_trade.add(it.from_team_id)
                    if it.to_team_id:
                        teams_in_trade.add(it.to_team_id)

                if team_id and team_id in teams_in_trade:
                    proposing_team_id = team_id
                    other = teams_in_trade - {team_id}
                    accepting_team_id = next(iter(other)) if other else None
                elif len(teams_in_trade) >= 2:
                    t_list = sorted(teams_in_trade)
                    proposing_team_id = t_list[0]
                    accepting_team_id = t_list[1]

            if proposing_team_id and accepting_team_id:
                trade = (
                    session.query(Trade)
                    .filter_by(
                        season_year=season.season_year,
                        espn_transaction_id=espn_tx_id,
                    )
                    .first()
                )
                if not trade and related_id:
                    trade = (
                        session.query(Trade)
                        .filter_by(
                            season_year=season.season_year,
                            espn_transaction_id=str(related_id),
                        )
                        .first()
                    )

                faab_prop = int(raw.get("faabFromProposer", raw.get("faab_from_proposer", 0)))
                faab_acc = int(raw.get("faabFromAccepter", raw.get("faab_from_accepter", 0)))
                if raw.get("faabByFromTeam"):
                    faab_prop = 0
                    faab_acc = 0
                    for from_espn_id, amount in raw["faabByFromTeam"].items():
                        try:
                            f_id = int(from_espn_id)
                            team_obj = team_lookup.get(f_id)
                            if team_obj:
                                if team_obj.id == proposing_team_id:
                                    faab_prop += int(amount)
                                elif team_obj.id == accepting_team_id:
                                    faab_acc += int(amount)
                        except (ValueError, TypeError):
                            pass
                if is_commish_edited and edit_data and len(edit_data.get("sides", [])) >= 2:
                    s_a = edit_data["sides"][0]
                    s_b = edit_data["sides"][1]
                    if s_a.get("faab_received") is not None or s_b.get("faab_received") is not None:
                        faab_acc = int(s_a.get("faab_received") or 0)
                        faab_prop = int(s_b.get("faab_received") or 0)

                trade_summary = raw.get("tradeSummary", raw.get("trade_summary", {}))

                if not trade:
                    trade = Trade(
                        season_year=season.season_year,
                        week=w,
                        espn_transaction_id=espn_tx_id,
                        proposing_team_id=proposing_team_id,
                        accepting_team_id=accepting_team_id,
                        status="EXECUTED",
                        proposed_at=proposed_at,
                        executed_at=executed_at,
                        faab_from_proposer=faab_prop,
                        faab_from_accepter=faab_acc,
                        trade_summary=trade_summary if isinstance(trade_summary, dict) else {},
                    )
                    session.add(trade)
                else:
                    if trade.status == "DELETED":
                        pass
                    else:
                        trade.week = w
                        trade.espn_transaction_id = espn_tx_id
                        trade.proposing_team_id = proposing_team_id
                        trade.accepting_team_id = accepting_team_id
                        trade.status = "EXECUTED"
                        if proposed_at:
                            trade.proposed_at = proposed_at
                        if executed_at:
                            trade.executed_at = executed_at
                        has_faab_data = (
                            bool(raw.get("faabByFromTeam"))
                            or "faabFromProposer" in raw
                            or "faabFromAccepter" in raw
                            or "faab_from_proposer" in raw
                            or "faab_from_accepter" in raw
                            or (is_commish_edited and edit_data)
                        )
                        if has_faab_data:
                            trade.faab_from_proposer = faab_prop
                            trade.faab_from_accepter = faab_acc
                        else:
                            if trade.faab_from_proposer is None:
                                trade.faab_from_proposer = faab_prop
                            if trade.faab_from_accepter is None:
                                trade.faab_from_accepter = faab_acc

                        # Bilateral invariant: net FAAB can only move in one direction
                        if trade.faab_from_proposer > 0 and trade.faab_from_accepter > 0:
                            if trade.faab_from_proposer >= trade.faab_from_accepter:
                                trade.faab_from_proposer -= trade.faab_from_accepter
                                trade.faab_from_accepter = 0
                            else:
                                trade.faab_from_accepter -= trade.faab_from_proposer
                                trade.faab_from_proposer = 0
                        if isinstance(trade_summary, dict) and trade_summary:
                            trade.trade_summary = trade_summary

                session.flush()
                valid_trade_ids.add(trade.id)

        processed_tx_ids.add(espn_tx_id)
        upserted_transactions.append(tx)

    # Prune orphaned duplicate trades for this season when running a full-season trade sync
    if valid_trade_ids and (topics or (weeks is None and scoring_periods is None)):
        season_trades = session.query(Trade).filter_by(season_year=season.season_year).all()
        for st in season_trades:
            if st.id not in valid_trade_ids:
                is_manual_trade = bool(
                    (st.espn_transaction_id and st.espn_transaction_id.startswith("manual-trade-"))
                    or (isinstance(st.trade_summary, dict) and st.trade_summary.get("is_manual"))
                )
                if (
                    st.status == "DELETED"
                    or is_manual_trade
                    or (st.espn_transaction_id and st.espn_transaction_id in edited_trades)
                ):
                    continue
                orph_txs = (
                    session.query(Transaction)
                    .filter_by(season_year=season.season_year, espn_transaction_id=st.espn_transaction_id)
                    .all()
                )
                for otx in orph_txs:
                    session.query(TransactionItem).filter_by(transaction_id=otx.id).delete(synchronize_session=False)
                    session.delete(otx)
                session.delete(st)

    session.flush()
    return upserted_transactions


def upsert_draft_picks_from_payload(
    session: Session,
    season: Season,
    payload: dict[str, Any],
    team_lookup: dict[int, Team],
    client: Any | None = None,
) -> list[DraftPick]:
    """Parse and upsert annual draft board selections from ESPN mDraftDetail payload.

    Args:
        session: Active SQLAlchemy session.
        season: Upserted Season ORM entity.
        payload: ESPN league payload containing draftDetail.
        team_lookup: Mapping of espn_team_id -> Team instance.
        client: Optional EspnClient for resolving missing player information.

    Returns:
        List of upserted DraftPick ORM instances.
    """
    draft_detail = payload.get("draftDetail")
    if not isinstance(draft_detail, dict):
        return []

    raw_picks = draft_detail.get("picks", [])
    if not raw_picks:
        return []

    # 1. Collect all valid player IDs in draft picks (including negative IDs for D/ST units)
    pids = [int(p.get("playerId", 0)) for p in raw_picks if p.get("playerId")]
    pids = [pid for pid in pids if pid != 0]

    # Extract season-specific proTeamId for players present in this season's payload
    season_pro_teams: dict[int, str] = {}

    def _record_season_pro_team(entry: Any) -> None:
        if not isinstance(entry, dict):
            return
        p_obj = entry.get("playerPoolEntry", {}).get("player") or entry.get("player") or entry
        if isinstance(p_obj, dict) and p_obj.get("id"):
            raw_pt = p_obj.get("proTeamId") if p_obj.get("proTeamId") is not None else p_obj.get("proTeam")
            if raw_pt is not None:
                pt_norm = normalize_pro_team(raw_pt)
                if pt_norm and pt_norm != "FA":
                    season_pro_teams[int(p_obj["id"])] = pt_norm

    for p in payload.get("players", []):
        _record_season_pro_team(p)
    for p in payload.get("playerPool", []):
        _record_season_pro_team(p)
    for tm in payload.get("teams", []):
        for entry in tm.get("roster", {}).get("entries", []):
            _record_season_pro_team(entry)
    for item in payload.get("schedule", []):
        for side in ("home", "away"):
            side_data = item.get(side)
            if isinstance(side_data, dict):
                for r_key in ("rosterForCurrentScoringPeriod", "rosterForMatchupPeriod", "roster"):
                    for entry in side_data.get(r_key, {}).get("entries", []):
                        _record_season_pro_team(entry)

    # 2. Check which players already exist in DB
    existing_players: dict[int, Player] = {}
    if pids:
        for p in session.query(Player).filter(Player.espn_player_id.in_(pids)).all():
            existing_players[p.espn_player_id] = p
    missing_pids = [pid for pid in set(pids) if pid not in existing_players]

    # 3. Resolve positive player IDs that are missing, unresolved ("Player <id>"), or lacking season-specific pro_team
    positive_to_fetch = [
        pid
        for pid in set(pids)
        if pid > 0
        and (
            pid not in existing_players
            or existing_players[pid].full_name.startswith("Player ")
            or existing_players[pid].default_position in ("UNKNOWN", "FLEX")
            or pid not in season_pro_teams
        )
    ]
    if positive_to_fetch and client is not None and hasattr(client, "fetch_player_info"):
        try:
            fetched_players = client.fetch_player_info(
                season_year=season.season_year,
                player_ids=positive_to_fetch,
                league_id=season.league_id,
            )
            if fetched_players:
                for fp in fetched_players:
                    _record_season_pro_team(fp)
                upsert_players_from_payload(session, {"players": fetched_players})
                for p in session.query(Player).filter(Player.espn_player_id.in_(positive_to_fetch)).all():
                    existing_players[p.espn_player_id] = p
                # Persist fetched players into season mCombined snapshot for offline rebuilds
                m_comb = (
                    session.query(RawEspnSnapshot)
                    .filter_by(season_year=season.season_year, view_name="mCombined", scoring_period=0)
                    .first()
                )
                if m_comb and isinstance(m_comb.payload, dict):
                    from sqlalchemy.orm.attributes import flag_modified

                    updated_payload = dict(m_comb.payload)
                    existing_p_list = list(updated_payload.get("players") or [])
                    seen_p_ids = {
                        int((x.get("player") or x).get("id", 0))
                        for x in existing_p_list
                        if isinstance(x, dict)
                    }
                    for fp in fetched_players:
                        fp_id = int((fp.get("player") or fp).get("id", 0)) if isinstance(fp, dict) else 0
                        if fp_id and fp_id not in seen_p_ids:
                            existing_p_list.append(fp)
                            seen_p_ids.add(fp_id)
                    updated_payload["players"] = existing_p_list
                    m_comb.payload = updated_payload
                    flag_modified(m_comb, "payload")
        except Exception as exc:
            logger.debug("Failed to fetch player info for draft picks: %s", exc)

    # 4. Fallback for any still-missing player IDs to satisfy foreign keys
    for pid in missing_pids:
        if pid not in existing_players and not session.get(Player, pid):
            if pid < 0:
                # ESPN D/ST unit format: -16000 - proTeamId
                pro_team_id = abs(pid) - 16000
                pro_team = normalize_pro_team(pro_team_id)
                name = f"{pro_team} D/ST" if pro_team != "UNKNOWN" else f"D/ST {pid}"
                fallback_player = Player(
                    espn_player_id=pid,
                    full_name=name,
                    default_position="D/ST",
                    pro_team=pro_team if pro_team != "UNKNOWN" else "FA",
                    headshot_url=None,
                )
                season_pro_teams[pid] = pro_team if pro_team != "UNKNOWN" else "FA"
            else:
                fallback_player = Player(
                    espn_player_id=pid,
                    full_name=f"Player {pid}",
                    default_position="UNKNOWN",
                    pro_team="FA",
                )
            session.add(fallback_player)
            session.flush()
            existing_players[pid] = fallback_player
        elif pid < 0 and pid in existing_players:
            season_pro_teams[pid] = existing_players[pid].pro_team

    # 5. Upsert DraftPick records
    upserted_picks: list[DraftPick] = []
    for raw in raw_picks:
        overall = int(raw.get("overallPickNumber", 0))
        if overall <= 0:
            continue

        round_num = int(raw.get("roundId", 1))
        round_pick = int(raw.get("roundPickNumber", 1))
        espn_team_id = int(raw.get("teamId", 0))
        team = team_lookup.get(espn_team_id)
        if not team:
            continue

        pid = int(raw.get("playerId", 0))
        if pid == 0 or pid not in existing_players:
            continue

        bid_amt = int(raw.get("bidAmount", 0))
        is_keeper = bool(raw.get("keeper", False))
        slot_id = raw.get("lineupSlotId")
        auto_type = int(raw.get("autoDraftTypeId", 0))
        pick_pro_team = season_pro_teams.get(pid) or existing_players[pid].pro_team

        nom_espn_team = raw.get("nominatingTeamId")
        nom_team = team_lookup.get(int(nom_espn_team)) if nom_espn_team else None

        draft_pick = (
            session.query(DraftPick)
            .filter_by(season_year=season.season_year, overall_pick=overall)
            .first()
        )
        if not draft_pick:
            draft_pick = DraftPick(
                season_year=season.season_year,
                round=round_num,
                round_pick=round_pick,
                overall_pick=overall,
                team_id=team.id,
                player_id=pid,
                bid_amount=bid_amt,
                nominating_team_id=nom_team.id if nom_team else None,
                is_keeper=is_keeper,
                lineup_slot_id=slot_id,
                auto_draft_type_id=auto_type,
                player_pro_team=pick_pro_team,
            )
            session.add(draft_pick)
        else:
            draft_pick.round = round_num
            draft_pick.round_pick = round_pick
            draft_pick.team_id = team.id
            draft_pick.player_id = pid
            draft_pick.bid_amount = bid_amt
            draft_pick.nominating_team_id = nom_team.id if nom_team else None
            draft_pick.is_keeper = is_keeper
            draft_pick.lineup_slot_id = slot_id
            draft_pick.auto_draft_type_id = auto_type
            draft_pick.player_pro_team = pick_pro_team

        upserted_picks.append(draft_pick)

    session.flush()
    return upserted_picks
