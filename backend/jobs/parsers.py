"""backend/jobs/parsers.py - Pure ESPN Fantasy Payload Parsers & Database Upserters.

Purpose:
    Extracts and normalizes raw ESPN Fantasy API payloads into SQLAlchemy ORM entities:
      - Manager identity resolution across GUID churn and co-owners via manager_overrides.json
      - Season settings, scoring rules, and lifecycle flags
      - Franchise teams, divisional alignments, records, and FAAB balances
      - Weekly schedule matchups across regular season, championship brackets, consolations, and byes.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.jobs.payout_policy import load_season_payout_rules
from backend.models.manager import Manager
from backend.models.matchup import Matchup
from backend.models.season import Season
from backend.models.team import Team
from backend.models.trade import TradeOverride

logger = logging.getLogger(__name__)


def get_default_overrides_path() -> Path:
    """Return the absolute path to db/manager_overrides.json."""
    return Path(__file__).resolve().parent.parent.parent / "db" / "manager_overrides.json"


def get_trade_overrides_path() -> Path:
    """Return the absolute path to db/trade_overrides.json."""
    return Path(__file__).resolve().parent.parent.parent / "db" / "trade_overrides.json"


def load_trade_overrides(overrides_path: str | Path | None = None) -> dict[str, Any]:
    """Load commissioner trade overrides from db/trade_overrides.json."""
    path = Path(overrides_path) if overrides_path else get_trade_overrides_path()
    if path.is_file():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"deleted_trades": [], "edited_trades": {}}
    return {"deleted_trades": [], "edited_trades": {}}


def save_trade_overrides(data: dict[str, Any], overrides_path: str | Path | None = None) -> None:
    """Save commissioner trade overrides to db/trade_overrides.json."""
    path = Path(overrides_path) if overrides_path else get_trade_overrides_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def sync_trade_overrides_to_db(
    session: Session,
    overrides_path: str | Path | None = None,
) -> None:
    """Synchronize canonical overrides from db/trade_overrides.json into the TradeOverride table."""
    file_data = load_trade_overrides(overrides_path)
    deleted_ids = set(str(x) for x in file_data.get("deleted_trades", []) if x)
    edited_map: dict[str, Any] = file_data.get("edited_trades", {}) or {}

    for del_id in deleted_ids:
        existing = (
            session.query(TradeOverride)
            .filter_by(espn_transaction_id=del_id)
            .first()
        )
        if not existing:
            session.add(
                TradeOverride(
                    season_year=2026,
                    espn_transaction_id=del_id,
                    is_deleted=True,
                )
            )
        else:
            existing.is_deleted = True

    for tx_id, e_val in edited_map.items():
        if not isinstance(e_val, dict):
            continue
        s_year = int(e_val.get("season_year") or 2026)
        existing = (
            session.query(TradeOverride)
            .filter_by(season_year=s_year, espn_transaction_id=str(tx_id))
            .first()
        )
        sides = e_val.get("sides") or []
        supp_picks = e_val.get("supplemental_picks") or []
        prop_espn = e_val.get("proposing_espn_team_id")
        acc_espn = e_val.get("accepting_espn_team_id")
        if prop_espn is None and len(sides) >= 1 and sides[0].get("espn_team_id") is not None:
            prop_espn = int(sides[0]["espn_team_id"])
        if acc_espn is None and len(sides) >= 2 and sides[1].get("espn_team_id") is not None:
            acc_espn = int(sides[1]["espn_team_id"])

        week_ovr = int(e_val["week"]) if e_val.get("week") is not None else None
        is_manual = bool(e_val.get("is_manual") or str(tx_id).startswith("manual-trade-"))

        if not existing:
            existing = TradeOverride(
                season_year=s_year,
                espn_transaction_id=str(tx_id),
                is_deleted=str(tx_id) in deleted_ids,
                is_manual=is_manual,
                week_override=week_ovr,
                proposing_espn_team_id=int(prop_espn) if prop_espn is not None else None,
                accepting_espn_team_id=int(acc_espn) if acc_espn is not None else None,
                override_sides=sides,
                supplemental_picks=supp_picks,
            )
            session.add(existing)
        else:
            if week_ovr is not None and existing.week_override is None:
                existing.week_override = week_ovr
            if prop_espn is not None:
                existing.proposing_espn_team_id = int(prop_espn)
            if acc_espn is not None:
                existing.accepting_espn_team_id = int(acc_espn)
            if supp_picks:
                existing.supplemental_picks = supp_picks
            if sides:
                if not existing.override_sides or any(s.get("espn_team_id") is None for s in existing.override_sides):
                    existing.override_sides = sides
            elif existing.override_sides:
                existing.override_sides = []
    session.flush()


def get_combined_trade_overrides(
    session: Session | None = None,
    overrides_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return unified trade overrides combining db/trade_overrides.json and TradeOverride DB rows."""
    base = load_trade_overrides(overrides_path)
    deleted_set: set[str] = {str(x) for x in base.get("deleted_trades", []) if x}
    edited_map: dict[str, dict[str, Any]] = {}
    for k, v in (base.get("edited_trades") or {}).items():
        if isinstance(v, dict):
            edited_map[str(k)] = dict(v)

    if session is not None:
        try:
            db_rows = session.query(TradeOverride).all()
            for row in db_rows:
                tx_id = str(row.espn_transaction_id)
                if row.is_deleted:
                    deleted_set.add(tx_id)
                elif tx_id in deleted_set:
                    deleted_set.discard(tx_id)

                if row.override_sides or row.supplemental_picks or row.week_override is not None or row.is_manual:
                    entry = dict(edited_map.get(tx_id, {}))
                    entry["season_year"] = row.season_year
                    if row.week_override is not None:
                        entry["week"] = row.week_override
                    if row.proposing_espn_team_id is not None:
                        entry["proposing_espn_team_id"] = row.proposing_espn_team_id
                    if row.accepting_espn_team_id is not None:
                        entry["accepting_espn_team_id"] = row.accepting_espn_team_id
                    if row.faab_from_proposer_override is not None:
                        entry["faab_from_proposer"] = row.faab_from_proposer_override
                    if row.faab_from_accepter_override is not None:
                        entry["faab_from_accepter"] = row.faab_from_accepter_override
                    if row.override_sides:
                        entry["sides"] = row.override_sides
                    if row.supplemental_picks:
                        entry["supplemental_picks"] = row.supplemental_picks
                    entry["is_manual"] = row.is_manual
                    edited_map[tx_id] = entry
        except Exception:
            pass

    return {
        "deleted_trades": sorted(deleted_set),
        "edited_trades": edited_map,
    }


def load_manager_overrides(
    overrides_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load declarative manager overrides from db/manager_overrides.json.

    Returns:
        Dictionary with:
          - "guid_to_canonical_guid": dict[str, str]
          - "team_season_overrides": dict[tuple[int, int], str] -> (season_year, espn_team_id): canonical_guid
          - "display_name_overrides": dict[str, str] -> canonical_guid/source_id: display_name
          - "ignored_member_guids": set[str]
    """
    path = Path(overrides_path) if overrides_path else get_default_overrides_path()
    if not path.is_file():
        logger.warning("Manager overrides file not found at %s. Using defaults.", path)
        return {
            "guid_to_canonical_guid": {},
            "team_season_overrides": {},
            "display_name_overrides": {},
            "ignored_member_guids": set(),
        }

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        logger.error("Failed to parse manager overrides JSON at %s: %s", path, exc)
        return {
            "guid_to_canonical_guid": {},
            "team_season_overrides": {},
            "display_name_overrides": {},
            "ignored_member_guids": set(),
        }

    guid_map = data.get("guid_to_canonical_guid", {})
    team_season_map: dict[tuple[int, int], str] = {}
    for item in data.get("team_season_overrides", []):
        year = item.get("season_year")
        t_id = item.get("espn_team_id")
        c_guid = item.get("canonical_manager_guid")
        if year is not None and t_id is not None and c_guid:
            team_season_map[(int(year), int(t_id))] = c_guid

    display_name_map: dict[str, str] = {}
    for item in data.get("overrides", []):
        src_id = item.get("source_espn_member_id")
        target_name = item.get("target_display_name")
        if src_id and target_name:
            display_name_map[src_id] = target_name

    ignored_guids = set(data.get("ignored_member_guids", []))

    return {
        "guid_to_canonical_guid": guid_map,
        "team_season_overrides": team_season_map,
        "display_name_overrides": display_name_map,
        "ignored_member_guids": ignored_guids,
    }


def _format_name_token(token: str) -> str:
    """Normalize a name token, capitalizing all-lowercase words while preserving mixed case."""
    cleaned = token.strip()
    if not cleaned:
        return ""
    if cleaned.islower():
        return " ".join(part.capitalize() for part in cleaned.split())
    return cleaned


def resolve_or_upsert_managers(
    session: Session,
    payload: dict[str, Any],
    overrides_data: dict[str, Any] | None = None,
) -> dict[str, Manager]:
    """Resolve manager identities from ESPN members and team owners, respecting overrides.

    Args:
        session: Active SQLAlchemy session.
        payload: ESPN league payload containing 'members' and/or 'teams'.
        overrides_data: Preloaded overrides or None to load from default path.

    Returns:
        Mapping of canonical_guid -> Manager instance.
    """
    overrides = overrides_data or load_manager_overrides()
    guid_to_canonical = overrides.get("guid_to_canonical_guid", {})
    display_name_overrides = overrides.get("display_name_overrides", {})
    team_season_overrides = overrides.get("team_season_overrides", {})
    ignored_guids = set(overrides.get("ignored_member_guids", set()))

    season_year = payload.get("seasonId") or payload.get("season_year", 0)

    # 1. Collect all member information from payload['members']
    members_data: dict[str, dict[str, Any]] = {}
    for m in payload.get("members", []):
        raw_guid = m.get("id")
        if not raw_guid or raw_guid in ignored_guids:
            continue
        members_data[raw_guid] = m

    # 2. Collect all owner GUIDs and team avatars/logos from payload['teams']
    needed_guids: set[str] = set(members_data.keys())
    owner_logo_map: dict[str, str] = {}
    for t in payload.get("teams", []):
        espn_t_id = t.get("id")
        t_logo = t.get("logo") or t.get("logoUrl")
        # Check team season override first
        if (season_year, espn_t_id) in team_season_overrides:
            override_guid = team_season_overrides[(season_year, espn_t_id)]
            if override_guid not in ignored_guids:
                needed_guids.add(override_guid)
                if t_logo:
                    owner_logo_map[override_guid] = t_logo

        primary_owner = t.get("primaryOwner")
        if primary_owner and primary_owner not in ignored_guids:
            needed_guids.add(primary_owner)
            if t_logo:
                owner_logo_map[primary_owner] = t_logo
        for owner in t.get("owners", []):
            if owner and owner not in ignored_guids:
                needed_guids.add(owner)
                if t_logo and owner not in owner_logo_map:
                    owner_logo_map[owner] = t_logo

    # 3. Canonicalize all needed GUIDs
    # Sort so that canonical GUIDs (raw_guid == canonical_guid) are processed before aliases
    sorted_guids = sorted(
        needed_guids,
        key=lambda g: 0 if guid_to_canonical.get(g, g) == g else 1,
    )
    canonical_to_info: dict[str, dict[str, Any]] = {}
    for raw_guid in sorted_guids:
        canonical_guid = guid_to_canonical.get(raw_guid, raw_guid)
        if canonical_guid in ignored_guids:
            continue
        m_info = members_data.get(raw_guid, {})

        first = _format_name_token(str(m_info.get("firstName") or ""))
        last = _format_name_token(str(m_info.get("lastName") or ""))
        real_name = f"{first} {last}".strip()

        display_name = ""
        if raw_guid in display_name_overrides:
            display_name = display_name_overrides[raw_guid]
        elif canonical_guid in display_name_overrides:
            display_name = display_name_overrides[canonical_guid]
        elif real_name:
            display_name = real_name
        elif m_info.get("displayName"):
            display_name = str(m_info["displayName"]).strip()
        else:
            display_name = canonical_guid

        avatar_url = (
            m_info.get("avatarUrl")
            or (m_info.get("avatar") or {}).get("imageUrl")
            or owner_logo_map.get(raw_guid)
            or owner_logo_map.get(canonical_guid)
        )

        existing_info = canonical_to_info.get(canonical_guid)
        if existing_info is None:
            canonical_to_info[canonical_guid] = {
                "display_name": display_name,
                "avatar_url": avatar_url,
            }
        else:
            # If canonical_to_info already has an entry from canonical GUID,
            # do not let an alias overwrite the canonical manager's display name.
            if existing_info["display_name"] == canonical_guid and display_name != canonical_guid:
                existing_info["display_name"] = display_name
            if avatar_url and not existing_info.get("avatar_url"):
                existing_info["avatar_url"] = avatar_url

    # 4. Upsert Manager records in database
    managers_by_guid: dict[str, Manager] = {}
    for canonical_guid, info in canonical_to_info.items():
        mgr = (
            session.query(Manager)
            .filter_by(espn_member_id=canonical_guid)
            .first()
        )
        if mgr:
            if info["display_name"] and mgr.display_name != info["display_name"]:
                mgr.display_name = info["display_name"]
            if info["avatar_url"]:
                mgr.avatar_url = info["avatar_url"]
        else:
            mgr = Manager(
                espn_member_id=canonical_guid,
                display_name=info["display_name"],
                avatar_url=info["avatar_url"],
                is_active=True,
            )
            session.add(mgr)
        managers_by_guid[canonical_guid] = mgr

    session.flush()
    return managers_by_guid


def upsert_season_from_payload(
    session: Session,
    payload: dict[str, Any],
    league_id: str | None = None,
) -> Season:
    """Upsert Season entity from ESPN payload.

    Args:
        session: Active SQLAlchemy session.
        payload: ESPN league payload.
        league_id: League ID override (if omitted, inferred from payload or settings).

    Returns:
        Upserted Season ORM instance.
    """
    season_year = int(payload.get("seasonId") or payload.get("season_year", 2024))
    raw_settings = payload.get("settings")
    settings = raw_settings if isinstance(raw_settings, dict) else {}
    raw_status = payload.get("status")
    status = raw_status if isinstance(raw_status, dict) else {}

    season = session.get(Season, season_year)

    target_league_id = (
        league_id
        or str(payload.get("id") or settings.get("leagueId") or (season.league_id if season else "12345678"))
    )
    league_name = (
        settings.get("name")
        or payload.get("league_name")
        or (season.league_name if season else f"League {target_league_id}")
    )

    schedule_settings = settings.get("scheduleSettings", {})
    scoring_settings = settings.get("scoringSettings", {})
    roster_settings = settings.get("rosterSettings", {})
    acquisition_settings = settings.get("acquisitionSettings", {})

    regular_season_weeks = schedule_settings.get(
        "matchupPeriodCount", season.regular_season_weeks if season else 14
    )
    playoff_team_count = schedule_settings.get(
        "playoffTeamCount", season.playoff_team_count if season else 6
    )
    playoff_matchup_length = schedule_settings.get(
        "playoffMatchupPeriodLength", season.playoff_matchup_length if season else 1
    )
    scoring_type = scoring_settings.get(
        "scoringType", season.scoring_type if season else "PPR"
    )
    faab_budget = acquisition_settings.get(
        "acquisitionBudget", season.faab_budget if season else 100
    )

    if status:
        current_week = status.get("currentMatchupPeriod", 1)
        is_active = bool(status.get("isActive", False))
        final_scoring_period = status.get("finalScoringPeriod", 17)
        latest_scoring_period = status.get("latestScoringPeriod", 0)
        is_completed = (
            (not is_active)
            or (current_week > final_scoring_period)
            or (latest_scoring_period > final_scoring_period)
        )
        if is_completed and latest_scoring_period > final_scoring_period:
            is_active = False
    elif season:
        current_week = season.current_week
        is_active = season.is_active
        is_completed = season.is_completed
    else:
        current_week = 1
        is_active = False
        is_completed = True

    has_transaction_data = season_year >= 2018
    payout_rules = load_season_payout_rules(season_year)

    if not season:
        season = Season(
            season_year=season_year,
            league_id=target_league_id,
            league_name=league_name,
            is_active=is_active,
            is_completed=is_completed,
            regular_season_weeks=regular_season_weeks,
            current_week=current_week,
            playoff_team_count=playoff_team_count,
            playoff_matchup_length=playoff_matchup_length,
            scoring_type=scoring_type,
            scoring_settings=scoring_settings,
            roster_slots=roster_settings.get("lineupSlotCounts", {}),
            faab_budget=faab_budget,
            weekly_win_payout=payout_rules["weekly_win_payout"],
            weekly_high_score_payout=payout_rules["weekly_high_score_payout"],
            weekly_high_score_loss_payout=payout_rules["weekly_high_score_loss_payout"],
            champion_payout=payout_rules["champion_payout"],
            runner_up_payout=payout_rules["runner_up_payout"],
            third_place_payout=payout_rules["third_place_payout"],
            fourth_place_payout=payout_rules["fourth_place_payout"],
            fifth_place_payout=payout_rules["fifth_place_payout"],
            regular_season_most_points_payout=payout_rules["regular_season_most_points_payout"],
            has_transaction_data=has_transaction_data,
            has_boxscore_data=True,
        )
        session.add(season)
    else:
        season.league_id = target_league_id
        season.league_name = league_name
        season.is_active = is_active
        season.is_completed = is_completed
        season.regular_season_weeks = regular_season_weeks
        season.current_week = current_week
        season.playoff_team_count = playoff_team_count
        season.playoff_matchup_length = playoff_matchup_length
        season.scoring_type = scoring_type
        season.faab_budget = faab_budget
        season.weekly_win_payout = payout_rules["weekly_win_payout"]
        season.weekly_high_score_payout = payout_rules["weekly_high_score_payout"]
        season.weekly_high_score_loss_payout = payout_rules["weekly_high_score_loss_payout"]
        season.champion_payout = payout_rules["champion_payout"]
        season.runner_up_payout = payout_rules["runner_up_payout"]
        season.third_place_payout = payout_rules["third_place_payout"]
        season.fourth_place_payout = payout_rules["fourth_place_payout"]
        season.fifth_place_payout = payout_rules["fifth_place_payout"]
        season.regular_season_most_points_payout = payout_rules["regular_season_most_points_payout"]
        if scoring_settings:
            season.scoring_settings = scoring_settings
        if roster_settings.get("lineupSlotCounts"):
            season.roster_slots = roster_settings.get("lineupSlotCounts")
        season.has_transaction_data = has_transaction_data

    session.flush()
    return season


def upsert_teams_from_payload(
    session: Session,
    season: Season,
    payload: dict[str, Any],
    manager_map: dict[str, Manager],
    overrides_data: dict[str, Any] | None = None,
) -> dict[int, Team]:
    """Upsert Team entities for a given season from ESPN payload.

    Args:
        session: Active SQLAlchemy session.
        season: Upserted Season ORM instance.
        payload: ESPN league payload.
        manager_map: Mapping of canonical_guid -> Manager.
        overrides_data: Preloaded overrides or None.

    Returns:
        Mapping of espn_team_id (int) -> Team instance.
    """
    overrides = overrides_data or load_manager_overrides()
    guid_to_canonical = overrides.get("guid_to_canonical_guid", {})
    team_season_overrides = overrides.get("team_season_overrides", {})
    ignored_guids = set(overrides.get("ignored_member_guids", set()))

    raw_settings = payload.get("settings")
    settings = raw_settings if isinstance(raw_settings, dict) else {}
    schedule_settings = (
        settings.get("scheduleSettings")
        if isinstance(settings.get("scheduleSettings"), dict)
        else {}
    )
    divisions_list = schedule_settings.get("divisions", [])
    division_map = {
        int(d["id"]): str(d.get("name"))
        for d in divisions_list
        if isinstance(d, dict) and "id" in d and d.get("name")
    }

    teams_by_espn_id: dict[int, Team] = {}

    for t in payload.get("teams", []):
        espn_team_id = int(t["id"])

        # Name formatting
        name = t.get("name")
        if not name:
            loc = t.get("location", "").strip()
            nick = t.get("nickname", "").strip()
            name = f"{loc} {nick}".strip() or f"Team {espn_team_id}"

        team_abbrev = t.get("abbrev")
        logo_url = t.get("logo") or t.get("logoUrl")
        division_id = t.get("divisionId")
        division_name = (
            t.get("divisionName")
            or (
                division_map.get(int(division_id))
                if division_id is not None
                else None
            )
        )

        # Owner resolution
        primary_guid = None
        if (season.season_year, espn_team_id) in team_season_overrides:
            primary_guid = team_season_overrides[(season.season_year, espn_team_id)]
        else:
            cand = t.get("primaryOwner")
            if cand and cand not in ignored_guids:
                primary_guid = cand
            elif t.get("owners"):
                non_ignored = [o for o in t["owners"] if o and o not in ignored_guids]
                if non_ignored:
                    primary_guid = non_ignored[0]

        canonical_primary = guid_to_canonical.get(primary_guid, primary_guid) if primary_guid else None
        manager = manager_map.get(canonical_primary) if canonical_primary else None
        if not manager:
            # Fallback: create placeholder manager if missing
            mgr_key = canonical_primary or f"placeholder_mgr_{espn_team_id}"
            manager = Manager(
                espn_member_id=mgr_key,
                display_name=f"Manager {espn_team_id}",
                is_active=True,
            )
            session.add(manager)
            session.flush()
            manager_map[mgr_key] = manager

        # Co-manager resolution
        co_manager: Manager | None = None
        raw_owners = [
            o for o in t.get("owners", [primary_guid] if primary_guid else [])
            if o and o not in ignored_guids
        ]
        if len(raw_owners) > 1:
            co_guid = raw_owners[1]
            canonical_co = guid_to_canonical.get(co_guid, co_guid)
            if canonical_co and canonical_co != canonical_primary:
                co_candidate = manager_map.get(canonical_co)
                if co_candidate and co_candidate.id != manager.id:
                    co_manager = co_candidate

        # Attach ESPN team avatar to manager / co-manager
        if logo_url and manager:
            manager.avatar_url = logo_url
        if logo_url and co_manager and not co_manager.avatar_url:
            co_manager.avatar_url = logo_url

        record = t.get("record", {})
        overall = record.get("overall", {})
        home = record.get("home", {})
        away = record.get("away", {})
        div_rec = record.get("division", {})

        wins = int(overall.get("wins", 0))
        losses = int(overall.get("losses", 0))
        ties = int(overall.get("ties", 0))
        home_wins = int(home.get("wins", 0))
        home_losses = int(home.get("losses", 0))
        home_ties = int(home.get("ties", 0))
        away_wins = int(away.get("wins", 0))
        away_losses = int(away.get("losses", 0))
        away_ties = int(away.get("ties", 0))
        division_wins = int(div_rec.get("wins", 0))
        division_losses = int(div_rec.get("losses", 0))
        division_ties = int(div_rec.get("ties", 0))

        pf = Decimal(str(t.get("points") or overall.get("pointsFor", 0.0)))
        pa = Decimal(str(t.get("pointsAgainst") or overall.get("pointsAgainst", 0.0)))

        streak_type = overall.get("streakType") or t.get("streakType")
        streak_length = int(overall.get("streakLength") or t.get("streakLength", 0))

        raw_seed = t.get("playoffSeed")
        playoff_seed = int(raw_seed) if raw_seed and int(raw_seed) > 0 else None
        raw_final = t.get("rankCalculatedFinal")
        final_standing = int(raw_final) if raw_final and int(raw_final) > 0 else None

        # Consolation / bottom bracket guardrail:
        # Teams that did not make the championship playoff bracket (playoff_seed > playoff_team_count)
        # do not move standings based on consolation ladder results.
        # Their final standing remains their regular season seed.
        playoff_cutoff = season.playoff_team_count or 6
        if playoff_seed is not None and playoff_seed > playoff_cutoff:
            final_standing = playoff_seed

        tx_counter = t.get("transactionCounter", {})
        budget_spent = tx_counter.get("acquisitionBudgetSpent", 0)
        faab_remaining = max(0, season.faab_budget - budget_spent)
        acquisitions = tx_counter.get("acquisitions", 0)
        drops = tx_counter.get("drops", 0)
        trades = tx_counter.get("trades", 0)
        ir_moves = tx_counter.get("moveToIR", 0)
        waiver_rank = t.get("waiverRank")

        team = (
            session.query(Team)
            .filter_by(season_year=season.season_year, espn_team_id=espn_team_id)
            .first()
        )
        if not team:
            team = Team(
                season_year=season.season_year,
                espn_team_id=espn_team_id,
                team_name=name,
                team_abbrev=team_abbrev,
                logo_url=logo_url,
                manager_id=manager.id,
                co_manager_id=co_manager.id if co_manager else None,
                raw_owner_guids=raw_owners,
                division_id=division_id,
                division_name=division_name,
                wins=wins,
                losses=losses,
                ties=ties,
                home_wins=home_wins,
                home_losses=home_losses,
                home_ties=home_ties,
                away_wins=away_wins,
                away_losses=away_losses,
                away_ties=away_ties,
                division_wins=division_wins,
                division_losses=division_losses,
                division_ties=division_ties,
                points_for=pf,
                points_against=pa,
                streak_type=streak_type,
                streak_length=streak_length,
                playoff_seed=playoff_seed,
                final_standing=final_standing,
                faab_remaining=faab_remaining,
                waiver_rank=waiver_rank,
                acquisitions=acquisitions,
                drops=drops,
                trades=trades,
                ir_moves=ir_moves,
            )
            session.add(team)
        else:
            team.team_name = name
            team.team_abbrev = team_abbrev
            team.logo_url = logo_url
            team.manager_id = manager.id
            team.co_manager_id = co_manager.id if co_manager else None
            team.raw_owner_guids = raw_owners
            team.division_id = division_id
            team.division_name = division_name
            team.wins = wins
            team.losses = losses
            team.ties = ties
            team.home_wins = home_wins
            team.home_losses = home_losses
            team.home_ties = home_ties
            team.away_wins = away_wins
            team.away_losses = away_losses
            team.away_ties = away_ties
            team.division_wins = division_wins
            team.division_losses = division_losses
            team.division_ties = division_ties
            team.points_for = pf
            team.points_against = pa
            team.streak_type = streak_type
            team.streak_length = streak_length
            team.playoff_seed = playoff_seed
            team.final_standing = final_standing
            team.faab_remaining = faab_remaining
            team.waiver_rank = waiver_rank
            team.acquisitions = acquisitions
            team.drops = drops
            team.trades = trades
            team.ir_moves = ir_moves

        teams_by_espn_id[espn_team_id] = team

    session.flush()
    return teams_by_espn_id


def upsert_matchups_from_payload(
    session: Session,
    season: Season,
    payload: dict[str, Any],
    team_lookup: dict[int, Team],
) -> list[Matchup]:
    """Upsert Matchup entities across regular season, playoffs, consolations, and byes.

    Args:
        session: Active SQLAlchemy session.
        season: Upserted Season ORM instance.
        payload: ESPN league payload containing 'schedule'.
        team_lookup: Mapping of espn_team_id -> Team instance.

    Returns:
        List of upserted Matchup ORM instances.
    """
    tier_map = {
        "NONE": "REGULAR",
        "WINNERS_BRACKET": "WINNERS_BRACKET",
        "WINNERS_CONSOLATION_LADDER": "WINNERS_CONSOLATION_LADDER",
        "LOSERS_CONSOLATION_LADDER": "LOSERS_CONSOLATION_LADDER",
    }

    matchups: list[Matchup] = []

    for item in payload.get("schedule", []):
        espn_matchup_id = int(item["id"])
        week = int(item.get("matchupPeriodId", 1))

        raw_tier = item.get("playoffTierType") or "NONE"
        matchup_type = tier_map.get(raw_tier, raw_tier)

        home_data = item.get("home", {})
        away_data = item.get("away")

        home_espn_id = home_data.get("teamId")
        if home_espn_id not in team_lookup:
            continue
        home_team = team_lookup[home_espn_id]

        raw_home_pts = (
            home_data.get("totalPointsLive")
            if home_data.get("totalPointsLive") is not None and not float(home_data.get("totalPoints") or 0.0)
            else home_data.get("totalPoints", 0.0)
        )
        home_score = Decimal(str(raw_home_pts or 0.0))

        # Handle BYE matchup (away is missing or null)
        if away_data is None or away_data.get("teamId") is None:
            matchup_type = "BYE"
            away_team_id = None
            away_score = Decimal("0.00")
            winner_team_id = None
            is_tie = False
            is_completed = bool(
                season.is_completed or (week <= season.current_week)
            )
        else:
            away_espn_id = away_data.get("teamId")
            if away_espn_id not in team_lookup:
                continue
            away_team = team_lookup[away_espn_id]
            away_team_id = away_team.id
            raw_away_pts = (
                away_data.get("totalPointsLive")
                if away_data.get("totalPointsLive") is not None and not float(away_data.get("totalPoints") or 0.0)
                else away_data.get("totalPoints", 0.0)
            )
            away_score = Decimal(str(raw_away_pts or 0.0))

            winner_str = item.get("winner")
            is_tie = False
            winner_team_id = None

            if winner_str == "HOME":
                winner_team_id = home_team.id
            elif winner_str == "AWAY":
                winner_team_id = away_team.id
            elif winner_str == "TIE":
                is_tie = True
            else:
                # winner_str is "UNDECIDED" or missing: infer if season is completed or past week
                if season.is_completed or (week < season.current_week):
                    if home_score > away_score:
                        winner_team_id = home_team.id
                    elif away_score > home_score:
                        winner_team_id = away_team.id
                    elif home_score == away_score and home_score > 0:
                        is_tie = True

            is_completed = bool(
                (winner_str in ("HOME", "AWAY", "TIE"))
                or season.is_completed
                or (week < season.current_week)
                or item.get("isCompleted") is True
            )

        # Points by scoring period extraction
        points_by_period: dict[str, Any] = {}
        if "pointsByScoringPeriod" in item:
            points_by_period = item["pointsByScoringPeriod"]
        else:
            h_pts = home_data.get("pointsByScoringPeriod", {})
            a_pts = away_data.get("pointsByScoringPeriod", {}) if away_data else {}
            points_by_period = dict(h_pts)
            if a_pts:
                points_by_period["home"] = h_pts
                points_by_period["away"] = a_pts

        # Optional projected & optimal scores (prefer ESPN's live updated projection when in-progress)
        raw_home_proj = (
            home_data.get("totalProjectedPointsLive")
            if home_data.get("totalProjectedPointsLive") is not None
            else home_data.get("totalProjectedPoints")
        )
        raw_away_proj = (
            away_data.get("totalProjectedPointsLive")
            if away_data and away_data.get("totalProjectedPointsLive") is not None
            else (away_data.get("totalProjectedPoints") if away_data else None)
        )
        home_proj = (
            Decimal(str(raw_home_proj))
            if raw_home_proj is not None
            else None
        )
        away_proj = (
            Decimal(str(raw_away_proj))
            if raw_away_proj is not None
            else None
        )

        matchup = (
            session.query(Matchup)
            .filter_by(
                season_year=season.season_year,
                week=week,
                espn_matchup_id=espn_matchup_id,
            )
            .first()
        )
        if not matchup:
            matchup = Matchup(
                season_year=season.season_year,
                week=week,
                espn_matchup_id=espn_matchup_id,
                matchup_type=matchup_type,
                home_team_id=home_team.id,
                away_team_id=away_team_id,
                home_score=home_score,
                away_score=away_score,
                home_projected=home_proj,
                away_projected=away_proj,
                winner_team_id=winner_team_id,
                is_tie=is_tie,
                is_completed=is_completed,
                points_by_scoring_period=points_by_period,
            )
            session.add(matchup)
        else:
            matchup.matchup_type = matchup_type
            matchup.home_team_id = home_team.id
            matchup.away_team_id = away_team_id
            matchup.home_score = home_score
            matchup.away_score = away_score
            if home_proj is not None:
                matchup.home_projected = home_proj
            if away_proj is not None:
                matchup.away_projected = away_proj
            matchup.winner_team_id = winner_team_id
            matchup.is_tie = is_tie
            matchup.is_completed = is_completed
            if points_by_period:
                matchup.points_by_scoring_period = points_by_period

        matchups.append(matchup)

    session.flush()
    return matchups
