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
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from backend.models.lineup import WeeklyLineup
from backend.models.matchup import Matchup
from backend.models.player import Player
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
            if pos != "UNKNOWN":
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

    if not raw_entries:
        if season.season_year < 2019:
            # Check if any lineups exist in DB for this season
            existing_count = (
                session.query(WeeklyLineup)
                .filter_by(season_year=season.season_year)
                .count()
            )
            if existing_count == 0:
                season.has_boxscore_data = False
        return []

    # First ensure players exist
    player_map = upsert_players_from_payload(session, payload)

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
        actual_pts = Decimal(str(actual_raw or 0.0)).quantize(Decimal("0.01"))
        proj_pts = Decimal(str(proj_raw or 0.0)).quantize(Decimal("0.01"))

        acq_type = entry.get("acquisitionType") or ppe.get("acquisitionType")
        stats = entry.get("weeklyStats") or ppe.get("weeklyStats") or {}

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
            if isinstance(stats, dict) and stats:
                lineup.weekly_stats = stats

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
    raw_txs: list[dict[str, Any]] = payload.get("transactions", [])
    if not raw_txs:
        # Check topics in league communication
        raw_txs = payload.get("topics", []) or payload.get("leagueCommunication", {}).get("topics", [])

    if not raw_txs:
        if season.season_year < 2018:
            existing_count = (
                session.query(Transaction)
                .filter_by(season_year=season.season_year)
                .count()
            )
            if existing_count == 0:
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

    # Track processed transaction IDs in this run & database
    existing_tx_ids = {
        t.espn_transaction_id
        for t in session.query(Transaction.espn_transaction_id)
        .filter_by(season_year=season.season_year)
        .all()
    }
    processed_tx_ids: set[str] = set()
    upserted_transactions: list[Transaction] = []

    for raw in raw_txs:
        espn_tx_id = str(raw.get("id", ""))
        if not espn_tx_id:
            continue

        raw_type = str(raw.get("type", "WAIVER")).upper()
        related_id = raw.get("relatedTransactionId") or raw.get("related_espn_transaction_id")

        # Trade deduplication: Skip TRADE_UPHOLD if relatedTransactionId was already processed as TRADE_ACCEPT
        if raw_type == "TRADE_UPHOLD" and related_id:
            if related_id in processed_tx_ids or related_id in existing_tx_ids:
                logger.debug(
                    "Skipping duplicate TRADE_UPHOLD %s for existing trade %s",
                    espn_tx_id,
                    related_id,
                )
                continue

        sp = int(raw.get("scoringPeriodId", raw.get("scoring_period", 0)))
        w = int(raw.get("matchupPeriodId", raw.get("week", sp or 1)))

        # Incremental filter by week or scoring period
        if weeks is not None and w not in weeks:
            continue
        if scoring_periods is not None and sp not in scoring_periods:
            continue

        # Normalize type
        if raw_type in ("FREEAGENT", "FREE_AGENT", "FA"):
            tx_type = "FREE_AGENT"
        elif raw_type == "WAIVER":
            tx_type = "WAIVER"
        elif raw_type == "DROP":
            tx_type = "DROP"
        elif raw_type in ("TRADE_ACCEPT", "TRADE_UPHOLD", "TRADE"):
            tx_type = "TRADE"
        else:
            tx_type = raw_type

        # Normalize status & failure reason
        raw_status = str(raw.get("status", "EXECUTED")).upper()
        failure_reason: str | None = None

        if raw_status in ("WAIVER_ERROR", "FAILED_ROSTER_LIMIT", "FAILED_OUTBID", "FAILED_INSUFFICIENT_FUNDS") or raw_status.startswith("FAILED"):
            status = "FAILED"
            msg = f"{raw.get('processMessage', '')} {raw.get('failureReason', '')} {raw_status} {raw.get('comment', '')}".upper()
            if any(term in msg for term in ("INSUFFICIENT", "BUDGET", "FUNDS", "NOT ENOUGH")):
                failure_reason = "INSUFFICIENT_FUNDS"
            elif any(term in msg for term in ("ROSTER", "LIMIT", "FULL", "MAX PLAYERS")):
                failure_reason = "ROSTER_LIMIT"
            elif any(term in msg for term in ("ALREADY", "CLAIMED", "TAKEN", "ROSTERED")):
                failure_reason = "ALREADY_CLAIMED"
            elif any(term in msg for term in ("OUTBID", "PRIORITY", "LOWER")) or int(raw.get("bidAmount", 0)) > 0:
                failure_reason = "OUTBID"
            else:
                failure_reason = "INVALID_CLAIM"
        elif raw_status in ("CANCELED", "CANCELLED"):
            status = "CANCELED"
        elif raw_status == "VETOED":
            status = "VETOED"
        else:
            status = "EXECUTED"

        # Auto-link failed waiver bids to winning waiver claim if not populated
        if status == "FAILED" and tx_type == "WAIVER" and not related_id:
            for item in raw.get("items", []):
                pid = int(
                    item.get("playerId")
                    or item.get("playerPoolEntry", {}).get("player", {}).get("id")
                    or 0
                )
                if (w, pid) in executed_waiver_wins:
                    related_id = executed_waiver_wins[(w, pid)]
                    break
                if (sp, pid) in executed_waiver_wins:
                    related_id = executed_waiver_wins[(sp, pid)]
                    break

        bid_amount = int(raw.get("bidAmount", 0))
        sub_order = raw.get("subOrder")
        waiver_prio = int(sub_order) if sub_order is not None else raw.get("waiverPriority")
        proposed_at = _parse_espn_timestamp(raw.get("proposedDate") or raw.get("proposed_at"))
        executed_at = _parse_espn_timestamp(raw.get("executionDate") or raw.get("executed_at"))
        is_commish = bool(
            raw.get("isCommissionerOverride", False)
            or raw.get("isActingAsTeamOwner") is False
        )

        espn_team_id = raw.get("teamId")
        team_id = team_lookup[espn_team_id].id if espn_team_id in team_lookup else None

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
            tx.proposed_at = proposed_at
            tx.executed_at = executed_at
            tx.is_commissioner_override = is_commish
            tx.related_espn_transaction_id = related_id

        # Normalize and upsert transaction items
        session.query(TransactionItem).filter_by(transaction_id=tx.id).delete()
        items_to_add: list[TransactionItem] = []

        for item in raw.get("items", []):
            pid = int(
                item.get("playerId")
                or item.get("playerPoolEntry", {}).get("player", {}).get("id")
                or item.get("player", {}).get("id", 0)
            )
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

            raw_item_type = str(item.get("type", "")).upper()
            if raw_item_type == "LINEUP":
                continue

            if raw_item_type in ("ADD", "DROP", "TRADE"):
                item_type = raw_item_type
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
            items_to_add.append(t_item)

        session.add_all(items_to_add)
        session.flush()

        # If executed trade, upsert Trade record
        if tx_type == "TRADE" and status == "EXECUTED":
            prop_espn = raw.get("proposingTeamId")
            acc_espn = raw.get("acceptingTeamId")

            proposing_team_id = team_lookup[prop_espn].id if prop_espn in team_lookup else None
            accepting_team_id = team_lookup[acc_espn].id if acc_espn in team_lookup else None

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
                faab_prop = int(raw.get("faabFromProposer", raw.get("faab_from_proposer", 0)))
                faab_acc = int(raw.get("faabFromAccepter", raw.get("faab_from_accepter", 0)))
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
                    trade.week = w
                    trade.proposing_team_id = proposing_team_id
                    trade.accepting_team_id = accepting_team_id
                    trade.status = "EXECUTED"
                    trade.proposed_at = proposed_at
                    trade.executed_at = executed_at
                    trade.faab_from_proposer = faab_prop
                    trade.faab_from_accepter = faab_acc
                    if isinstance(trade_summary, dict) and trade_summary:
                        trade.trade_summary = trade_summary

        processed_tx_ids.add(espn_tx_id)
        upserted_transactions.append(tx)

    session.flush()
    return upserted_transactions
