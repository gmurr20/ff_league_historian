"""backend/services/side_bets_service.py - Side Bets Evaluation, Boxscore Breakdown & JSON Sync Service.

Purpose:
    Evaluates 1v1 and NvM group side bets against live/final weekly_lineups and matchups,
    computes spread-adjusted margins, starter/bench player breakdowns grouped by team,
    net +/- side bet earnings rollups for the financial leaderboard, and durable JSON
    persistence in db/side_bets.json across database rebuilds.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.jobs.deep_parsers import compute_optimal_score
from backend.models.lineup import WeeklyLineup
from backend.models.matchup import Matchup
from backend.models.player import Player
from backend.models.season import Season
from backend.models.side_bet import SideBet
from backend.models.sync_run import SyncRun
from backend.models.team import Team

logger = logging.getLogger(__name__)

# Canonical starter and bench slot sort order
SLOT_SORT_ORDER: dict[str, int] = {
    "QB": 0,
    "TQB": 1,
    "RB": 2,
    "RB/WR": 3,
    "WR": 4,
    "WR/TE": 5,
    "TE": 6,
    "FLEX": 7,
    "OP": 8,
    "D/ST": 9,
    "DST": 9,
    "K": 10,
    "BE": 20,
    "IR": 21,
}


def get_side_bets_json_path() -> Path:
    """Return the canonical path to db/side_bets.json."""
    return Path(__file__).resolve().parent.parent.parent / "db" / "side_bets.json"


def load_side_bets_json(json_path: str | Path | None = None) -> dict[str, Any]:
    """Load persisted commissioner side bets from db/side_bets.json."""
    path = Path(json_path) if json_path else get_side_bets_json_path()
    if path.is_file():
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict) and isinstance(raw.get("side_bets"), list):
                return raw
            if isinstance(raw, list):
                return {"side_bets": raw}
        except Exception as exc:
            logger.warning("Failed to load side bets JSON from %s: %s", path, exc)
    return {"side_bets": []}


def save_side_bets_json(
    data: dict[str, Any], json_path: str | Path | None = None
) -> None:
    """Persist commissioner side bets to db/side_bets.json."""
    path = Path(json_path) if json_path else get_side_bets_json_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        data
        if isinstance(data, dict) and "side_bets" in data
        else {"side_bets": list(data.get("side_bets", [])) if isinstance(data, dict) else []}
    )
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _serialize_bet_for_json(bet: SideBet) -> dict[str, Any]:
    """Convert a SideBet ORM entity into a canonical JSON-serializable dict."""
    return {
        "bet_uuid": bet.bet_uuid,
        "season_year": int(bet.season_year),
        "week": int(bet.week),
        "title": bet.title or "",
        "side_a_name": bet.side_a_name or "Side A",
        "side_b_name": bet.side_b_name or "Side B",
        "side_a_espn_team_ids": [int(x) for x in (bet.side_a_espn_team_ids or [])],
        "side_b_espn_team_ids": [int(x) for x in (bet.side_b_espn_team_ids or [])],
        "spread_side_a": round(float(bet.spread_side_a or 0.0), 2),
        "stake_amount": round(float(bet.stake_amount or 0.0), 2),
        "stake_description": bet.stake_description or "",
        "scoring_mode": bet.scoring_mode or "STARTERS",
        "is_deleted": bool(bet.is_deleted),
        "created_at": bet.created_at.isoformat() if bet.created_at else None,
        "updated_at": bet.updated_at.isoformat() if bet.updated_at else None,
    }


def upsert_side_bet_in_json(
    bet: SideBet, json_path: str | Path | None = None
) -> None:
    """Upsert a single SideBet record into db/side_bets.json by bet_uuid."""
    data = load_side_bets_json(json_path)
    items: list[dict[str, Any]] = data.setdefault("side_bets", [])
    serialized = _serialize_bet_for_json(bet)

    for idx, item in enumerate(items):
        if isinstance(item, dict) and item.get("bet_uuid") == bet.bet_uuid:
            items[idx] = serialized
            save_side_bets_json(data, json_path)
            return

    items.append(serialized)
    save_side_bets_json(data, json_path)


def ensure_side_bets_table(session: Session) -> None:
    """Ensure the side_bets table exists on the session's database engine."""
    bind = session.get_bind()
    SideBet.__table__.create(bind=bind, checkfirst=True)


def sync_side_bets_to_db(
    session: Session, json_path: str | Path | None = None
) -> int:
    """Synchronize persisted side bets from db/side_bets.json into the side_bets table."""
    ensure_side_bets_table(session)
    data = load_side_bets_json(json_path)
    raw_bets = data.get("side_bets", [])
    if not isinstance(raw_bets, list) or not raw_bets:
        return 0

    synced = 0
    for item in raw_bets:
        if not isinstance(item, dict):
            continue
        bet_uuid = str(item.get("bet_uuid") or "").strip()
        if not bet_uuid:
            bet_uuid = f"bet-{uuid4().hex[:12]}"

        season_year = int(item.get("season_year") or 0)
        week = int(item.get("week") or 1)
        if season_year <= 0:
            continue

        side_a_ids = [int(x) for x in (item.get("side_a_espn_team_ids") or [])]
        side_b_ids = [int(x) for x in (item.get("side_b_espn_team_ids") or [])]
        spread_val = Decimal(str(item.get("spread_side_a", 0.0))).quantize(Decimal("0.01"))
        stake_val = Decimal(str(item.get("stake_amount", 0.0))).quantize(Decimal("0.01"))
        title = str(item.get("title") or "")
        side_a_name = str(item.get("side_a_name") or "Side A")
        side_b_name = str(item.get("side_b_name") or "Side B")
        stake_desc = str(item.get("stake_description") or "")
        scoring_mode = str(item.get("scoring_mode") or "STARTERS").upper()
        is_deleted = bool(item.get("is_deleted", False))

        existing = session.query(SideBet).filter(SideBet.bet_uuid == bet_uuid).first()
        if not existing:
            bet = SideBet(
                bet_uuid=bet_uuid,
                season_year=season_year,
                week=week,
                title=title,
                side_a_name=side_a_name,
                side_b_name=side_b_name,
                side_a_espn_team_ids=side_a_ids,
                side_b_espn_team_ids=side_b_ids,
                spread_side_a=spread_val,
                stake_amount=stake_val,
                stake_description=stake_desc,
                scoring_mode=scoring_mode,
                is_deleted=is_deleted,
            )
            session.add(bet)
        else:
            existing.season_year = season_year
            existing.week = week
            existing.title = title
            existing.side_a_name = side_a_name
            existing.side_b_name = side_b_name
            existing.side_a_espn_team_ids = side_a_ids
            existing.side_b_espn_team_ids = side_b_ids
            existing.spread_side_a = spread_val
            existing.stake_amount = stake_val
            existing.stake_description = stake_desc
            existing.scoring_mode = scoring_mode
            existing.is_deleted = is_deleted
            existing.updated_at = datetime.now(UTC)

        synced += 1

    session.flush()
    return synced


def normalize_to_espn_team_ids(
    session: Session, season_year: int, raw_team_ids: list[Any]
) -> list[int]:
    """Normalize a list of internal Team.id or canonical espn_team_id integers to espn_team_ids.

    Checks internal Team.id for the given season_year first if the value matches a Team.id
    whose espn_team_id differs, or falls back to matching Team.espn_team_id in that season.
    """
    if not raw_team_ids:
        return []

    season_teams = (
        session.query(Team).filter(Team.season_year == season_year).all()
    )
    by_pk = {t.id: t.espn_team_id for t in season_teams}
    espn_set = {t.espn_team_id for t in season_teams}

    normalized: list[int] = []
    for raw_id in raw_team_ids:
        tid = int(raw_id)
        # If tid is a primary key for this season (and either not an espn_team_id or matches PK lookup):
        # Wait: in season 1, PKs might be 1..10 and espn_team_ids 1..10 (where by_pk[tid] == tid anyway!).
        # In later seasons, PKs are e.g. 21..30 while espn_team_ids are 1..10.
        if tid in by_pk and tid not in espn_set:
            espn_id = by_pk[tid]
        elif tid in espn_set and tid in by_pk and by_pk[tid] != tid:
            # Ambiguous integer that is both a PK and an espn_team_id in the same season:
            # Prefer espn_team_id if all raw_team_ids are in 1..12, otherwise check by_pk
            espn_id = tid
        elif tid in by_pk:
            espn_id = by_pk[tid]
        elif tid in espn_set:
            espn_id = tid
        else:
            # Fallback: check if tid is a Team PK from any season
            any_team = session.get(Team, tid)
            espn_id = any_team.espn_team_id if any_team else tid

        if espn_id not in normalized:
            normalized.append(espn_id)

    return normalized


def _build_team_breakdown(
    team: Team,
    lineup_rows: list[tuple[WeeklyLineup, Player | None]],
    week_matchups: list[Matchup],
    roster_slots: dict[str, Any] | None,
    scoring_mode: str,
    is_completed: bool = False,
) -> dict[str, Any]:
    """Build SideBetTeamBreakdown for a single participating franchise."""
    starters: list[dict[str, Any]] = []
    bench: list[dict[str, Any]] = []
    lineup_models: list[WeeklyLineup] = []

    for lu, player in lineup_rows:
        lineup_models.append(lu)
        w_stats = lu.weekly_stats if isinstance(lu.weekly_stats, dict) else {}
        inj_status = w_stats.get("injury_status")
        if inj_status in ("NORMAL", "ACTIVE"):
            inj_status = None
        is_injured = bool(
            w_stats.get("is_injured")
            or w_stats.get("injured")
            or (inj_status is not None and inj_status not in ("NORMAL", "ACTIVE"))
            or lu.slot_position == "IR"
        )

        slot_pos = lu.slot_position or "BE"
        is_starter = bool(lu.is_starter and slot_pos not in ("BE", "IR"))
        actual_pts = round(float(lu.actual_points or 0.0), 2)
        proj_pts = round(float(lu.projected_points or 0.0), 2)

        entry_dict: dict[str, Any] = {
            "player_id": lu.player_id,
            "full_name": player.full_name if player else f"Player {lu.player_id}",
            "default_position": (
                player.default_position if player else slot_pos
            ),
            "pro_team": player.pro_team if player else "FA",
            "headshot_url": player.headshot_url if player else None,
            "slot_position": slot_pos,
            "is_starter": is_starter,
            "actual_points": actual_pts,
            "projected_points": proj_pts,
            "injury_status": inj_status,
            "is_injured": is_injured,
        }

        if is_starter:
            starters.append(entry_dict)
        else:
            bench.append(entry_dict)

    starters.sort(
        key=lambda p: (
            SLOT_SORT_ORDER.get(p["slot_position"], 15),
            -p["actual_points"],
            p["full_name"].lower(),
        )
    )
    bench.sort(
        key=lambda p: (
            SLOT_SORT_ORDER.get(p["slot_position"], 25),
            -p["actual_points"],
            p["full_name"].lower(),
        )
    )

    # Find matching matchup for fallback or supplemental projections
    team_matchup_score: float | None = None
    team_matchup_proj: float | None = None
    team_matchup_bench: float | None = None
    team_matchup_opt: float | None = None
    for m in week_matchups:
        if m.home_team_id == team.id:
            team_matchup_score = float(m.home_score or 0.0)
            team_matchup_proj = (
                float(m.home_projected) if m.home_projected is not None else None
            )
            team_matchup_bench = (
                float(m.home_bench_points) if m.home_bench_points is not None else None
            )
            team_matchup_opt = (
                float(m.home_optimal_score)
                if m.home_optimal_score is not None
                else None
            )
            break
        if m.away_team_id == team.id:
            team_matchup_score = float(m.away_score or 0.0)
            team_matchup_proj = (
                float(m.away_projected) if m.away_projected is not None else None
            )
            team_matchup_bench = (
                float(m.away_bench_points) if m.away_bench_points is not None else None
            )
            team_matchup_opt = (
                float(m.away_optimal_score)
                if m.away_optimal_score is not None
                else None
            )
            break

    if starters:
        starter_points = round(sum(p["actual_points"] for p in starters), 2)
        raw_proj_sum = round(sum(p["projected_points"] for p in starters), 2)
        if is_completed:
            projected_points = (
                round(team_matchup_proj, 2)
                if raw_proj_sum == 0.0 and team_matchup_proj is not None
                else raw_proj_sum
            )
        else:
            # Live / Upcoming week:
            # Unplayed starters (actual == 0) contribute their pre-game projection;
            # active/scored starters contribute at least their actual points scored so far.
            live_starter_proj = round(
                sum(
                    max(p["actual_points"], p["projected_points"])
                    if p["actual_points"] > 0
                    else p["projected_points"]
                    for p in starters
                ),
                2,
            )
            if team_matchup_proj is not None and team_matchup_proj > 0 and raw_proj_sum == 0.0:
                projected_points = round(max(team_matchup_proj, starter_points), 2)
            else:
                projected_points = max(live_starter_proj, starter_points)
        bench_points = round(sum(p["actual_points"] for p in bench), 2)
        opt_dec, _ = compute_optimal_score(lineup_models, roster_slots=roster_slots)
        optimal_points = max(round(float(opt_dec), 2), starter_points)
    else:
        starter_points = round(team_matchup_score or 0.0, 2)
        projected_points = round(team_matchup_proj or 0.0, 2)
        bench_points = round(
            sum(p["actual_points"] for p in bench)
            if bench
            else (team_matchup_bench or 0.0),
            2,
        )
        optimal_points = round(
            team_matchup_opt if team_matchup_opt is not None else starter_points, 2
        )

    mode = (scoring_mode or "STARTERS").upper()
    if mode == "MAX_PF":
        effective_points = optimal_points
    elif mode == "BENCH":
        effective_points = bench_points
    else:
        effective_points = starter_points

    mgr_name = team.manager.display_name if team.manager else team.team_name
    logo = team.logo_url or (team.manager.avatar_url if team.manager else None)

    return {
        "team_id": team.id,
        "espn_team_id": team.espn_team_id,
        "team_name": team.team_name,
        "team_abbrev": team.team_abbrev,
        "logo_url": logo,
        "manager_id": team.manager_id,
        "manager_name": mgr_name,
        "starter_points": starter_points,
        "projected_points": projected_points,
        "bench_points": bench_points,
        "optimal_points": optimal_points,
        "effective_points": effective_points,
        "starters": starters,
        "bench": bench,
    }


def _evaluate_side_bet(
    bet: SideBet,
    teams_by_season_espn: dict[tuple[int, int], Team],
    lineups_by_key: dict[tuple[int, int, int], list[tuple[WeeklyLineup, Player | None]]],
    matchups_by_season_week: dict[tuple[int, int], list[Matchup]],
    seasons_by_year: dict[int, Season],
) -> dict[str, Any]:
    """Evaluate a single SideBet ORM record into a full SideBetDetail dict."""
    s_year = bet.season_year
    week = bet.week
    season = seasons_by_year.get(s_year)
    roster_slots = season.roster_slots if season else None
    week_matchups = matchups_by_season_week.get((s_year, week), [])
    scoring_mode = (bet.scoring_mode or "STARTERS").upper()
    spread_side_a = round(float(bet.spread_side_a or 0.0), 2)
    stake_amount = round(float(bet.stake_amount or 0.0), 2)

    # Determine is_completed from Matchup.is_completed for that season/week
    if week_matchups:
        is_completed = all(bool(m.is_completed) for m in week_matchups)
    elif season is not None:
        is_completed = bool(season.is_completed or (week < season.current_week))
    else:
        is_completed = False

    side_a_espn_ids = [int(x) for x in (bet.side_a_espn_team_ids or [])]
    side_b_espn_ids = [int(x) for x in (bet.side_b_espn_team_ids or [])]

    side_a_teams: list[dict[str, Any]] = []
    for espn_id in side_a_espn_ids:
        t = teams_by_season_espn.get((s_year, espn_id))
        if t:
            lu_rows = lineups_by_key.get((s_year, week, t.id), [])
            side_a_teams.append(
                _build_team_breakdown(
                    t, lu_rows, week_matchups, roster_slots, scoring_mode, is_completed=is_completed
                )
            )

    side_b_teams: list[dict[str, Any]] = []
    for espn_id in side_b_espn_ids:
        t = teams_by_season_espn.get((s_year, espn_id))
        if t:
            lu_rows = lineups_by_key.get((s_year, week, t.id), [])
            side_b_teams.append(
                _build_team_breakdown(
                    t, lu_rows, week_matchups, roster_slots, scoring_mode, is_completed=is_completed
                )
            )

    side_a_raw = round(sum(t["effective_points"] for t in side_a_teams), 2)
    side_a_proj = round(sum(t["projected_points"] for t in side_a_teams), 2)
    side_a_bench = round(sum(t["bench_points"] for t in side_a_teams), 2)
    side_a_adj = round(side_a_raw + spread_side_a, 2)
    side_a_proj_adj = round(side_a_proj + spread_side_a, 2)

    side_b_raw = round(sum(t["effective_points"] for t in side_b_teams), 2)
    side_b_proj = round(sum(t["projected_points"] for t in side_b_teams), 2)
    side_b_bench = round(sum(t["bench_points"] for t in side_b_teams), 2)
    side_b_adj = round(side_b_raw, 2)
    side_b_proj_adj = round(side_b_proj, 2)

    default_a_name = (
        " & ".join(t["manager_name"] for t in side_a_teams)
        if side_a_teams
        else "Side A"
    )
    default_b_name = (
        " & ".join(t["manager_name"] for t in side_b_teams)
        if side_b_teams
        else "Side B"
    )
    side_a_name = (
        bet.side_a_name
        if (bet.side_a_name and bet.side_a_name != "Side A")
        else default_a_name
    )
    side_b_name = (
        bet.side_b_name
        if (bet.side_b_name and bet.side_b_name != "Side B")
        else default_b_name
    )
    title = bet.title or f"{side_a_name} vs. {side_b_name}"

    is_live = bool(not is_completed and (side_a_raw > 0 or side_b_raw > 0))

    margin_vs_spread = round(side_a_adj - side_b_raw, 2)
    projected_margin_vs_spread = round(side_a_proj_adj - side_b_proj, 2)

    if is_completed or is_live:
        if margin_vs_spread > 0:
            currently_covering: str | None = "A"
        elif margin_vs_spread < 0:
            currently_covering = "B"
        else:
            currently_covering = "PUSH"
    else:
        currently_covering = None

    winning_side: str | None = currently_covering if is_completed else None

    return {
        "bet_id": bet.id,
        "bet_uuid": bet.bet_uuid,
        "season_year": s_year,
        "week": week,
        "title": title,
        "scoring_mode": scoring_mode,
        "spread_side_a": spread_side_a,
        "stake_amount": stake_amount,
        "stake_description": bet.stake_description or "",
        "is_completed": is_completed,
        "is_live": is_live,
        "side_a": {
            "side_label": "A",
            "side_name": side_a_name,
            "espn_team_ids": side_a_espn_ids,
            "teams": side_a_teams,
            "raw_points": side_a_raw,
            "projected_points": side_a_proj,
            "bench_points": side_a_bench,
            "spread_applied": spread_side_a,
            "adjusted_points": side_a_adj,
            "projected_adjusted_points": side_a_proj_adj,
        },
        "side_b": {
            "side_label": "B",
            "side_name": side_b_name,
            "espn_team_ids": side_b_espn_ids,
            "teams": side_b_teams,
            "raw_points": side_b_raw,
            "projected_points": side_b_proj,
            "bench_points": side_b_bench,
            "spread_applied": round(-spread_side_a if spread_side_a != 0 else 0.0, 2),
            "adjusted_points": side_b_adj,
            "projected_adjusted_points": side_b_proj_adj,
        },
        "margin_vs_spread": margin_vs_spread,
        "projected_margin_vs_spread": projected_margin_vs_spread,
        "currently_covering": currently_covering,
        "winning_side": winning_side,
    }


def _load_evaluated_side_bets(
    session: Session,
    season_filter: int | None = None,
    sync_json: bool = True,
) -> tuple[list[dict[str, Any]], dict[int, Season]]:
    """Query and evaluate all non-deleted SideBet records for the requested season scope."""
    ensure_side_bets_table(session)
    if sync_json:
        sync_side_bets_to_db(session)

    query = session.query(SideBet).filter(SideBet.is_deleted.is_(False))
    if season_filter is not None:
        query = query.filter(SideBet.season_year == season_filter)

    bets_rows = query.order_by(
        SideBet.season_year.desc(), SideBet.week.desc(), SideBet.id.desc()
    ).all()

    seasons = session.query(Season).order_by(Season.season_year.desc()).all()
    seasons_by_year = {s.season_year: s for s in seasons}

    if not bets_rows:
        return [], seasons_by_year

    target_years = {b.season_year for b in bets_rows}
    target_weeks = {b.week for b in bets_rows}

    teams = (
        session.query(Team)
        .filter(Team.season_year.in_(target_years))
        .all()
    )
    teams_by_season_espn: dict[tuple[int, int], Team] = {
        (t.season_year, t.espn_team_id): t for t in teams
    }

    lineup_query = (
        session.query(WeeklyLineup, Player)
        .outerjoin(Player, WeeklyLineup.player_id == Player.espn_player_id)
        .filter(
            WeeklyLineup.season_year.in_(target_years),
            WeeklyLineup.week.in_(target_weeks),
        )
        .all()
    )
    lineups_by_key: dict[tuple[int, int, int], list[tuple[WeeklyLineup, Player | None]]] = (
        defaultdict(list)
    )
    for lu, player in lineup_query:
        lineups_by_key[(lu.season_year, lu.week, lu.team_id)].append((lu, player))

    matchups = (
        session.query(Matchup)
        .filter(
            Matchup.season_year.in_(target_years),
            Matchup.week.in_(target_weeks),
        )
        .all()
    )
    matchups_by_season_week: dict[tuple[int, int], list[Matchup]] = defaultdict(list)
    for m in matchups:
        matchups_by_season_week[(m.season_year, m.week)].append(m)

    evaluated = [
        _evaluate_side_bet(
            b,
            teams_by_season_espn=teams_by_season_espn,
            lineups_by_key=lineups_by_key,
            matchups_by_season_week=matchups_by_season_week,
            seasons_by_year=seasons_by_year,
        )
        for b in bets_rows
    ]
    return evaluated, seasons_by_year


def _compute_side_bet_leaderboard(
    evaluated_bets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compute SideBetManagerStanding[] leaderboard across the evaluated bets."""
    standings_map: dict[int, dict[str, Any]] = {}

    for bet in evaluated_bets:
        stake = float(bet["stake_amount"] or 0.0)
        is_completed = bool(bet["is_completed"])
        winning_side = bet["winning_side"]

        for side_label, side_key in (("A", "side_a"), ("B", "side_b")):
            side_obj = bet[side_key]
            seen_mgrs: set[int] = set()
            for team in side_obj["teams"]:
                mgr_id = team["manager_id"]
                if mgr_id in seen_mgrs:
                    continue
                seen_mgrs.add(mgr_id)

                if mgr_id not in standings_map:
                    standings_map[mgr_id] = {
                        "manager_id": mgr_id,
                        "manager_name": team["manager_name"],
                        "team_name": team["team_name"],
                        "avatar_url": team["logo_url"],
                        "bets_count": 0,
                        "wins": 0,
                        "losses": 0,
                        "pushes": 0,
                        "pending": 0,
                        "net_earnings": 0.0,
                        "total_staked": 0.0,
                    }

                entry = standings_map[mgr_id]
                entry["bets_count"] += 1
                entry["total_staked"] = round(entry["total_staked"] + stake, 2)

                if not is_completed:
                    entry["pending"] += 1
                elif winning_side == "PUSH":
                    entry["pushes"] += 1
                elif winning_side == side_label:
                    entry["wins"] += 1
                    if stake > 0:
                        entry["net_earnings"] = round(entry["net_earnings"] + stake, 2)
                elif winning_side in ("A", "B"):
                    entry["losses"] += 1
                    if stake > 0:
                        entry["net_earnings"] = round(entry["net_earnings"] - stake, 2)

    leaderboard = list(standings_map.values())
    leaderboard.sort(
        key=lambda x: (
            -x["net_earnings"],
            -x["wins"],
            x["losses"],
            x["manager_name"].lower(),
        )
    )
    return leaderboard


def get_side_bets(
    session: Session,
    season_filter: int | None = None,
    week_filter: int | None = None,
    sync_json: bool = True,
) -> dict[str, Any]:
    """Return full SideBetsResponse with evaluated bets, boxscore breakdowns, and leaderboard."""
    evaluated_bets, seasons_by_year = _load_evaluated_side_bets(
        session, season_filter=season_filter, sync_json=sync_json
    )

    # Resolve current_week from active or target season
    active_season = next(
        (s for s in seasons_by_year.values() if s.is_active),
        None,
    )
    if season_filter is not None and season_filter in seasons_by_year:
        current_week = int(seasons_by_year[season_filter].current_week or 1)
    elif active_season is not None:
        current_week = int(active_season.current_week or 1)
    elif seasons_by_year:
        latest_s = max(seasons_by_year.values(), key=lambda s: s.season_year)
        current_week = int(latest_s.current_week or 1)
    else:
        current_week = 1

    available_weeks = sorted({b["week"] for b in evaluated_bets}, reverse=True)

    if week_filter is not None:
        selected_week: int | None = week_filter
        filtered_bets = [b for b in evaluated_bets if b["week"] == week_filter]
    else:
        filtered_bets = evaluated_bets
        if current_week in available_weeks:
            selected_week = current_week
        elif available_weeks:
            selected_week = available_weeks[0]
        else:
            selected_week = current_week

    leaderboard = _compute_side_bet_leaderboard(evaluated_bets)

    # Query most recent LIVE_SCORES sync timestamp if available
    last_live_sync = (
        session.query(SyncRun)
        .filter(
            SyncRun.run_type == "LIVE_SCORES",
            SyncRun.status == "SUCCESS",
        )
        .order_by(SyncRun.completed_at.desc(), SyncRun.id.desc())
        .first()
    )
    last_live_sync_at = (
        last_live_sync.completed_at.isoformat()
        if last_live_sync and last_live_sync.completed_at
        else None
    )

    return {
        "season_filter": season_filter,
        "selected_week": selected_week,
        "current_week": current_week,
        "available_weeks": available_weeks,
        "last_live_sync_at": last_live_sync_at,
        "bets": filtered_bets,
        "leaderboard": leaderboard,
    }


def compute_manager_side_bet_rollups(
    session: Session,
    season_filter: int | None = None,
    sync_json: bool = True,
) -> dict[tuple[int, int], dict[str, Any]]:
    """Compute per-(manager_id, season_year) side bet cash, win/loss/push counts, and receipts.

    Only completed side bets factor into financial rollups.
    Winning side teams earn +stake_amount; losing side teams incur -stake_amount; PUSH = 0.0.
    """
    evaluated_bets, _ = _load_evaluated_side_bets(
        session, season_filter=season_filter, sync_json=sync_json
    )

    rollups: dict[tuple[int, int], dict[str, Any]] = defaultdict(
        lambda: {
            "side_bets_cash": 0.0,
            "side_bets_wins": 0,
            "side_bets_losses": 0,
            "side_bets_pushes": 0,
            "side_bet_receipts": [],
        }
    )

    for bet in evaluated_bets:
        if not bet["is_completed"]:
            continue

        s_year = int(bet["season_year"])
        week = int(bet["week"])
        stake = float(bet["stake_amount"] or 0.0)
        winning_side = bet["winning_side"]
        side_a = bet["side_a"]
        side_b = bet["side_b"]

        for side_label, my_side, opp_side in (
            ("A", side_a, side_b),
            ("B", side_b, side_a),
        ):
            if winning_side == "PUSH":
                result = "PUSH"
                amount = 0.0
            elif winning_side == side_label:
                result = "WIN"
                amount = round(stake, 2)
            elif winning_side in ("A", "B"):
                result = "LOSS"
                amount = round(-stake if stake > 0 else 0.0, 2)
            else:
                continue

            seen_mgrs: set[int] = set()
            for team in my_side["teams"]:
                mgr_id = int(team["manager_id"])
                if mgr_id in seen_mgrs:
                    continue
                seen_mgrs.add(mgr_id)

                bucket = rollups[(mgr_id, s_year)]
                bucket["side_bets_cash"] = round(
                    bucket["side_bets_cash"] + amount, 2
                )
                if result == "WIN":
                    bucket["side_bets_wins"] += 1
                elif result == "LOSS":
                    bucket["side_bets_losses"] += 1
                else:
                    bucket["side_bets_pushes"] += 1

                bucket["side_bet_receipts"].append(
                    {
                        "bet_id": bet["bet_id"],
                        "season_year": s_year,
                        "week": week,
                        "title": bet["title"],
                        "opponent_label": opp_side["side_name"],
                        "spread_applied": my_side["spread_applied"],
                        "team_side_points": my_side["adjusted_points"],
                        "opponent_side_points": opp_side["adjusted_points"],
                        "result": result,
                        "amount": amount,
                    }
                )

    for bucket in rollups.values():
        bucket["side_bet_receipts"].sort(
            key=lambda r: (r["season_year"], r["week"], r["bet_id"])
        )

    return rollups
