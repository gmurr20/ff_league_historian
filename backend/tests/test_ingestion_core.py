"""backend/tests/test_ingestion_core.py - Comprehensive Unit & Integration Tests for Ingestion Core.

Covers:
  1. Manager identity resolution (espn_member_id GUIDs, co-managers, db/manager_overrides.json).
  2. Matchup parsing (REGULAR, WINNERS_BRACKET, LOSERS_CONSOLATION_LADDER, BYE away_team_id=None, points_by_scoring_period).
  3. backfill_history multi-season crawl + --from-snapshots zero-network rebuild idempotency.
  4. sync_weekly 2-week rolling window sync (current_week - 1 and current_week), verifying completed seasons are never re-crawled.
  5. Stat correction flip test: Tuesday win -> Thursday flip to loss or tie removes previous payout and awards new payout with zero duplicates.
  6. Season-end championship transition: is_completed = True, podium payouts awarded, subsequent run is offseason no-op.
  7. EspnClient auth cookie parsing, legacy vs modern URL selection, and graceful 401/403/404 error handling.
"""

from __future__ import annotations

import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import requests
from sqlalchemy.orm import Session, sessionmaker

from backend.database import create_db_engine, init_db
from backend.jobs.backfill_history import backfill_history
from backend.jobs.espn_client import EspnAccessError, EspnClient, get_configured_league_ids
from backend.jobs.ledger_reconciler import (
    reconcile_podium_ledger,
    reconcile_regular_season_points_ledger,
    reconcile_week_ledger,
)
from backend.jobs.parsers import (
    load_manager_overrides,
    resolve_or_upsert_managers,
    upsert_matchups_from_payload,
    upsert_season_from_payload,
    upsert_teams_from_payload,
)
from backend.jobs.payout_policy import load_season_payout_rules
from backend.jobs.sync_weekly import sync_weekly
from backend.models.earnings import EarningsLedger
from backend.models.manager import Manager
from backend.models.matchup import Matchup
from backend.models.raw_snapshot import RawEspnSnapshot
from backend.models.season import Season
from backend.models.team import Team

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(filename: str) -> dict[str, Any]:
    with open(FIXTURES_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def db_session() -> Any:
    """Provide an isolated in-memory SQLite database session for each test."""
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


class MockEspnClient(EspnClient):
    """Offline mock client returning static fixture data."""

    def __init__(self, fixture_map: dict[int, dict[str, Any]]) -> None:
        super().__init__(league_id="12345678", espn_s2="mock_s2", swid="{MOCK-SWID}")
        self.fixture_map = fixture_map
        self.crawl_call_counts: dict[int, int] = {}

    def fetch_league(
        self,
        season_year: int,
        views: list[str] | None = None,
        x_fantasy_filter: dict[str, Any] | None = None,
        allow_inaccessible: bool = True,
        league_id: str | None = None,
    ) -> dict[str, Any] | None:
        self.crawl_call_counts[season_year] = self.crawl_call_counts.get(season_year, 0) + 1
        if season_year in self.fixture_map:
            return copy.deepcopy(self.fixture_map[season_year])
        if allow_inaccessible:
            return None
        raise EspnAccessError(f"Season {season_year} inaccessible", status_code=404)


# ==============================================================================
# 1. Manager Identity Resolution Tests
# ==============================================================================


def test_manager_identity_resolution(db_session: Session) -> None:
    """Verify manager resolution from ESPN members, team owners, and manager_overrides.json."""
    payload_2022 = load_fixture("espn_league_2022.json")
    overrides = load_manager_overrides()

    # Verify overrides configuration is loaded properly
    assert "{LEGACY-MEMBER-GUID-2017}" in overrides["guid_to_canonical_guid"]
    assert overrides["guid_to_canonical_guid"]["{LEGACY-MEMBER-GUID-2017}"] == "{CANONICAL-MGR-01}"
    assert "{CO-OWNER-MEMBER-GUID}" in overrides["guid_to_canonical_guid"]
    assert overrides["guid_to_canonical_guid"]["{CO-OWNER-MEMBER-GUID}"] == "{CANONICAL-MGR-07}"

    mgr_map = resolve_or_upsert_managers(db_session, payload_2022, overrides)
    assert len(mgr_map) > 0

    # Verify canonical GUID remapping:
    # {LEGACY-MEMBER-GUID-2017} should be mapped to {CANONICAL-MGR-01}
    assert "{CANONICAL-MGR-01}" in mgr_map
    canonical_mgr_1 = mgr_map["{CANONICAL-MGR-01}"]
    assert canonical_mgr_1.espn_member_id == "{CANONICAL-MGR-01}"

    # Verify team parsing links co-managers:
    season = upsert_season_from_payload(db_session, payload_2022)
    teams = upsert_teams_from_payload(db_session, season, payload_2022, mgr_map, overrides)

    team_7 = teams[7]  # Green Hill Zone
    assert team_7.manager_id is not None
    assert team_7.co_manager_id is not None
    assert team_7.manager_id != team_7.co_manager_id
    assert len(team_7.raw_owner_guids) == 2

    # Verify primary owner of team 7 is Grace Green
    grace_mgr = db_session.get(Manager, team_7.manager_id)
    assert grace_mgr is not None
    assert grace_mgr.display_name == "Grace Green"

    # Verify co-manager of team 7 resolved to canonical manager 7
    co_mgr = db_session.get(Manager, team_7.co_manager_id)
    assert co_mgr is not None
    assert co_mgr.espn_member_id == "{CANONICAL-MGR-07}"

    # Verify firstName + lastName takes priority over generic ESPN usernames and team logo attaches to manager
    custom_payload = {
        "seasonId": 2026,
        "members": [
            {
                "id": "{BRIAN-GUID}",
                "displayName": "ESPNFAN1112758055",
                "firstName": "Brian",
                "lastName": "Strumillo ",
            },
            {
                "id": "{ANDREW-GUID}",
                "displayName": "espn62471013",
                "firstName": "andrew",
                "lastName": "solano",
            },
        ],
        "teams": [
            {
                "id": 11,
                "name": "The Good Guys",
                "owners": ["{BRIAN-GUID}"],
                "logo": "https://g.espncdn.com/lm-static/ffl/images/default_logos/6.svg",
            },
            {
                "id": 9,
                "name": "Someone Feed Starvin' Marvin",
                "owners": ["{ANDREW-GUID}"],
                "logo": "https://g.espncdn.com/lm-static/ffl/images/default_logos/5.svg",
            },
        ],
    }
    custom_mgrs = resolve_or_upsert_managers(db_session, custom_payload, overrides)
    assert custom_mgrs["{BRIAN-GUID}"].display_name == "Brian Strumillo"
    assert custom_mgrs["{BRIAN-GUID}"].avatar_url == "https://g.espncdn.com/lm-static/ffl/images/default_logos/6.svg"
    assert custom_mgrs["{ANDREW-GUID}"].display_name == "Andrew Solano"
    assert custom_mgrs["{ANDREW-GUID}"].avatar_url == "https://g.espncdn.com/lm-static/ffl/images/default_logos/5.svg"


# ==============================================================================
# 2. Matchup Parsing Tests
# ==============================================================================


def test_matchup_parsing_types_and_byes(db_session: Session) -> None:
    """Verify parsing of REGULAR, WINNERS_BRACKET, LOSERS_CONSOLATION_LADDER, and BYEs."""
    payload_2022 = load_fixture("espn_league_2022.json")
    mgr_map = resolve_or_upsert_managers(db_session, payload_2022)
    season = upsert_season_from_payload(db_session, payload_2022)
    teams = upsert_teams_from_payload(db_session, season, payload_2022, mgr_map)
    matchups = upsert_matchups_from_payload(db_session, season, payload_2022, teams)

    assert len(matchups) > 0

    # 1. Regular season matchups
    reg_matchups = [m for m in matchups if m.matchup_type == "REGULAR"]
    assert len(reg_matchups) == 4
    for m in reg_matchups:
        assert m.home_team_id is not None
        assert m.away_team_id is not None
        assert m.home_score > 0
        assert m.away_score > 0
        assert m.points_by_scoring_period is not None

    # 2. Playoff BYE matchups (away_team_id = None, winner_team_id = None)
    bye_matchups = [m for m in matchups if m.matchup_type == "BYE"]
    assert len(bye_matchups) == 2
    for bye in bye_matchups:
        assert bye.away_team_id is None
        assert bye.winner_team_id is None
        assert bye.home_team_id in (teams[1].id, teams[2].id)
        assert bye.is_completed is True

    # 3. Playoff Winners Bracket matchups
    winners_bracket = [m for m in matchups if m.matchup_type == "WINNERS_BRACKET"]
    assert len(winners_bracket) >= 4
    for wb in winners_bracket:
        assert wb.home_team_id is not None
        assert wb.away_team_id is not None
        assert wb.winner_team_id is not None

    # 4. Losers Consolation Ladder matchups
    losers_consolation = [m for m in matchups if m.matchup_type == "LOSERS_CONSOLATION_LADDER"]
    assert len(losers_consolation) == 1
    assert losers_consolation[0].home_team_id == teams[7].id
    assert losers_consolation[0].away_team_id == teams[8].id

    # 5. Multi-week playoff points_by_scoring_period
    payload_2023 = load_fixture("espn_league_2023.json")
    season_2023 = upsert_season_from_payload(db_session, payload_2023)
    teams_2023 = upsert_teams_from_payload(db_session, season_2023, payload_2023, mgr_map)
    matchups_2023 = upsert_matchups_from_payload(db_session, season_2023, payload_2023, teams_2023)

    champ_2023 = next(m for m in matchups_2023 if m.espn_matchup_id == 1401)
    assert champ_2023.points_by_scoring_period["16"] == 70.00
    assert champ_2023.points_by_scoring_period["17"] == 75.50
    assert champ_2023.points_by_scoring_period["home"] == {"16": 70.00, "17": 75.50}
    assert champ_2023.points_by_scoring_period["away"] == {"16": 68.00, "17": 70.20}


# ==============================================================================
# 3. Backfill History & Rebuild Idempotency Tests
# ==============================================================================


def test_backfill_history_and_from_snapshots_replay(db_session: Session) -> None:
    """Verify live backfill crawl, snapshot archiving, and --from-snapshots zero-network rebuild."""
    fixture_2022 = load_fixture("espn_league_2022.json")
    fixture_2023 = load_fixture("espn_league_2023.json")

    mock_client = MockEspnClient({2022: fixture_2022, 2023: fixture_2023})

    # Step 1: Run backfill crawling simulated ESPN API for 2022-2023
    run = backfill_history(
        session=db_session,
        from_snapshots=False,
        from_year=2022,
        to_year=2023,
        league_id="12345678",
        client=mock_client,
    )
    assert run.status == "SUCCESS"
    assert run.records_processed > 0

    # Verify database state after initial backfill
    seasons_count = db_session.query(Season).count()
    teams_count = db_session.query(Team).count()
    matchups_count = db_session.query(Matchup).count()
    earnings_count = db_session.query(EarningsLedger).count()
    snapshots_count = db_session.query(RawEspnSnapshot).count()

    assert seasons_count == 2
    assert teams_count == 16  # 8 teams x 2 seasons
    assert snapshots_count >= 2

    # Step 2: Now run backfill with --from-snapshots (zero network calls)
    mock_client.crawl_call_counts.clear()

    replay_run = backfill_history(
        session=db_session,
        from_snapshots=True,
        from_year=2022,
        to_year=2023,
        league_id="12345678",
        client=mock_client,
    )
    assert replay_run.status == "SUCCESS"
    # Verify zero network calls were made
    assert len(mock_client.crawl_call_counts) == 0

    # Step 3: Verify strict idempotency — no duplicate rows created
    assert db_session.query(Season).count() == seasons_count
    assert db_session.query(Team).count() == teams_count
    assert db_session.query(Matchup).count() == matchups_count
    assert db_session.query(EarningsLedger).count() == earnings_count


# ==============================================================================
# 4. Weekly Cron & Stat Correction Tests
# ==============================================================================


def test_sync_weekly_rolling_window_and_no_historical_recrawl(db_session: Session) -> None:
    """Verify weekly cron syncs only the 2-week rolling window and NEVER re-crawls completed seasons."""
    # Seed historical completed season 2022 and 2023
    f2022 = load_fixture("espn_league_2022.json")
    f2023 = load_fixture("espn_league_2023.json")
    f2024 = load_fixture("espn_league_2024.json")

    mock_client = MockEspnClient({2022: f2022, 2023: f2023, 2024: f2024})

    # Historical backfill
    backfill_history(
        session=db_session,
        from_snapshots=False,
        from_year=2022,
        to_year=2023,
        league_id="12345678",
        client=mock_client,
    )

    # Now upsert 2024 as active season
    mgr_map = resolve_or_upsert_managers(db_session, f2024)
    s2024 = upsert_season_from_payload(db_session, f2024)
    t2024 = upsert_teams_from_payload(db_session, s2024, f2024, mgr_map)
    upsert_matchups_from_payload(db_session, s2024, f2024, t2024)
    db_session.commit()

    assert s2024.is_active is True
    assert s2024.current_week == 8

    # Reset API call counts
    mock_client.crawl_call_counts.clear()

    # Run sync_weekly
    sync_run = sync_weekly(session=db_session, client=mock_client)

    assert sync_run.status == "SUCCESS"
    assert sync_run.week_range == "7-8"

    # CRITICAL INVARIANT: 2022 and 2023 were NEVER re-crawled!
    assert 2022 not in mock_client.crawl_call_counts
    assert 2023 not in mock_client.crawl_call_counts
    assert mock_client.crawl_call_counts.get(2024, 0) == 1


def test_stat_correction_flip_win_to_loss_and_tie(db_session: Session) -> None:
    """Verify Thursday Elias stat correction flips Tuesday win to loss/tie with zero orphaned rows."""
    f2024 = load_fixture("espn_league_2024.json")
    mgr_map = resolve_or_upsert_managers(db_session, f2024)
    season = upsert_season_from_payload(db_session, f2024)
    teams = upsert_teams_from_payload(db_session, season, f2024, mgr_map)
    upsert_matchups_from_payload(db_session, season, f2024, teams)

    # Initially in week 7: Team 1 (120.50) beats Team 2 (110.00)
    entries_tuesday = reconcile_week_ledger(db_session, season, week=7)
    assert len(entries_tuesday) > 0
    team1 = teams[1]
    team2 = teams[2]

    # Verify Tuesday state:
    # Team 1 manager has $10 WEEKLY_WIN and $10 WEEKLY_HIGH_SCORE (120.50 pts)
    t1_win = (
        db_session.query(EarningsLedger)
        .filter_by(season_year=2024, week=7, manager_id=team1.manager_id, entry_type="WEEKLY_WIN")
        .first()
    )
    assert t1_win is not None
    assert t1_win.amount == Decimal("10.00")

    t1_hs = (
        db_session.query(EarningsLedger)
        .filter_by(season_year=2024, week=7, manager_id=team1.manager_id, entry_type="WEEKLY_HIGH_SCORE")
        .first()
    )
    assert t1_hs is not None
    assert t1_hs.amount == Decimal("10.00")

    # Team 2 lost (110.00), so no WEEKLY_WIN, but has $10 WEEKLY_HIGH_SCORE_LOSS (110.00 > 105.00)
    t2_win = (
        db_session.query(EarningsLedger)
        .filter_by(season_year=2024, week=7, manager_id=team2.manager_id, entry_type="WEEKLY_WIN")
        .first()
    )
    assert t2_win is None

    t2_hsl = (
        db_session.query(EarningsLedger)
        .filter_by(season_year=2024, week=7, manager_id=team2.manager_id, entry_type="WEEKLY_HIGH_SCORE_LOSS")
        .first()
    )
    assert t2_hsl is not None
    assert t2_hsl.amount == Decimal("10.00")

    # --- Thursday Stat Correction 1: Team 2 gets +15 points, score flips to Team 2 win (125.00 vs 120.50) ---
    f2024_flipped = copy.deepcopy(f2024)
    # Update matchup 2001 in week 7
    for item in f2024_flipped["schedule"]:
        if item["id"] == 2001:
            item["winner"] = "AWAY"
            item["away"]["totalPoints"] = 125.00
            item["home"]["totalPoints"] = 120.50

    upsert_matchups_from_payload(db_session, season, f2024_flipped, teams)
    entries_thursday = reconcile_week_ledger(db_session, season, week=7)
    assert len(entries_thursday) > 0

    # Verify Team 1's WEEKLY_WIN and WEEKLY_HIGH_SCORE were deleted!
    t1_win_after_flip = (
        db_session.query(EarningsLedger)
        .filter_by(season_year=2024, week=7, manager_id=team1.manager_id, entry_type="WEEKLY_WIN")
        .first()
    )
    assert t1_win_after_flip is None

    t1_hs_after_flip = (
        db_session.query(EarningsLedger)
        .filter_by(season_year=2024, week=7, manager_id=team1.manager_id, entry_type="WEEKLY_HIGH_SCORE")
        .first()
    )
    assert t1_hs_after_flip is None

    # Team 1 is now a loser with 120.50 pts, so gets WEEKLY_HIGH_SCORE_LOSS!
    t1_hsl_after_flip = (
        db_session.query(EarningsLedger)
        .filter_by(season_year=2024, week=7, manager_id=team1.manager_id, entry_type="WEEKLY_HIGH_SCORE_LOSS")
        .first()
    )
    assert t1_hsl_after_flip is not None
    assert t1_hsl_after_flip.amount == Decimal("10.00")

    # Verify Team 2's manager now has WEEKLY_WIN and WEEKLY_HIGH_SCORE, and no WEEKLY_HIGH_SCORE_LOSS
    t2_win_after_flip = (
        db_session.query(EarningsLedger)
        .filter_by(season_year=2024, week=7, manager_id=team2.manager_id, entry_type="WEEKLY_WIN")
        .first()
    )
    assert t2_win_after_flip is not None
    assert t2_win_after_flip.amount == Decimal("10.00")

    t2_hs_after_flip = (
        db_session.query(EarningsLedger)
        .filter_by(season_year=2024, week=7, manager_id=team2.manager_id, entry_type="WEEKLY_HIGH_SCORE")
        .first()
    )
    assert t2_hs_after_flip is not None
    assert t2_hs_after_flip.amount == Decimal("10.00")

    t2_hsl_after_flip = (
        db_session.query(EarningsLedger)
        .filter_by(season_year=2024, week=7, manager_id=team2.manager_id, entry_type="WEEKLY_HIGH_SCORE_LOSS")
        .first()
    )
    assert t2_hsl_after_flip is None

    # --- Thursday Stat Correction 2: Score adjusted to an exact TIE (120.50 to 120.50) ---
    f2024_tie = copy.deepcopy(f2024)
    for item in f2024_tie["schedule"]:
        if item["id"] == 2001:
            item["winner"] = "TIE"
            item["away"]["totalPoints"] = 120.50
            item["home"]["totalPoints"] = 120.50

    upsert_matchups_from_payload(db_session, season, f2024_tie, teams)
    entries_tie = reconcile_week_ledger(db_session, season, week=7)
    assert len(entries_tie) > 0

    # Verify both managers now have $5.00 WEEKLY_TIE and $5.00 WEEKLY_HIGH_SCORE tie,
    # and ZERO WEEKLY_WIN or WEEKLY_HIGH_SCORE_LOSS payouts exist for them!
    t1_tie = (
        db_session.query(EarningsLedger)
        .filter_by(season_year=2024, week=7, manager_id=team1.manager_id, entry_type="WEEKLY_TIE")
        .first()
    )
    t2_tie = (
        db_session.query(EarningsLedger)
        .filter_by(season_year=2024, week=7, manager_id=team2.manager_id, entry_type="WEEKLY_TIE")
        .first()
    )
    assert t1_tie is not None
    assert t1_tie.entry_type == "WEEKLY_TIE"
    assert t1_tie.amount == Decimal("5.00")

    assert t2_tie is not None
    assert t2_tie.entry_type == "WEEKLY_TIE"
    assert t2_tie.amount == Decimal("5.00")

    t1_hs_tie = (
        db_session.query(EarningsLedger)
        .filter_by(season_year=2024, week=7, manager_id=team1.manager_id, entry_type="WEEKLY_HIGH_SCORE")
        .first()
    )
    t2_hs_tie = (
        db_session.query(EarningsLedger)
        .filter_by(season_year=2024, week=7, manager_id=team2.manager_id, entry_type="WEEKLY_HIGH_SCORE")
        .first()
    )
    assert t1_hs_tie is not None
    assert t1_hs_tie.amount == Decimal("5.00")
    assert t2_hs_tie is not None
    assert t2_hs_tie.amount == Decimal("5.00")

    # Check total payouts for matchup 2001 managers (2 entries each: WEEKLY_TIE + WEEKLY_HIGH_SCORE = 4 total)
    total_entries_w7 = (
        db_session.query(EarningsLedger)
        .filter_by(season_year=2024, week=7)
        .filter(EarningsLedger.manager_id.in_([team1.manager_id, team2.manager_id]))
        .count()
    )
    assert total_entries_w7 == 4


# ==============================================================================
# 5. Championship Completion & Offseason Transition Tests
# ==============================================================================


def test_championship_auto_completion_and_offseason_noop(db_session: Session) -> None:
    """Verify season transitions to is_completed=True at championship final, awarding podium prizes, and subsequent run is no-op."""
    f2023 = load_fixture("espn_league_2023.json")
    # Simulate active season that just finalized week 17 championship
    f_active_champ = copy.deepcopy(f2023)
    f_active_champ["seasonId"] = 2024
    f_active_champ["status"]["isActive"] = True
    f_active_champ["status"]["currentMatchupPeriod"] = 17

    mock_client = MockEspnClient({2024: f_active_champ})

    # Initial state: active season
    mgr_map = resolve_or_upsert_managers(db_session, f_active_champ)
    season = upsert_season_from_payload(db_session, f_active_champ)
    teams = upsert_teams_from_payload(db_session, season, f_active_champ, mgr_map)
    upsert_matchups_from_payload(db_session, season, f_active_champ, teams)
    db_session.commit()

    assert season.is_completed is False

    # Run sync_weekly on week 17
    run = sync_weekly(session=db_session, week=17, client=mock_client)
    assert run.status == "SUCCESS"

    # Invariants:
    # 1. Season auto-completed
    db_session.refresh(season)
    assert season.is_completed is True
    assert season.is_active is False

    # 2. Podium awards created
    podium_entries = (
        db_session.query(EarningsLedger)
        .filter_by(season_year=2024, week=None)
        .all()
    )
    assert len(podium_entries) == 5
    champ = next(e for e in podium_entries if e.entry_type == "CHAMPION")
    runner_up = next(e for e in podium_entries if e.entry_type == "RUNNER_UP")
    third = next(e for e in podium_entries if e.entry_type == "THIRD_PLACE")
    fourth = next(e for e in podium_entries if e.entry_type == "FOURTH_PLACE")
    fifth = next(e for e in podium_entries if e.entry_type == "FIFTH_PLACE")

    assert champ.amount == season.champion_payout
    assert runner_up.amount == season.runner_up_payout
    assert third.amount == season.third_place_payout
    assert fourth.amount == season.fourth_place_payout
    assert fifth.amount == season.fifth_place_payout

    # 3. Subsequent run during offseason is a NOOP with 0 API calls
    mock_client.crawl_call_counts.clear()
    offseason_run = sync_weekly(session=db_session, client=mock_client)

    assert offseason_run.status == "NOOP_OFFSEASON"
    assert len(mock_client.crawl_call_counts) == 0


def test_reconcile_week_ledger_high_score_and_high_score_loss_with_ties(
    db_session: Session,
) -> None:
    """Verify weekly high score and high score loss rules with single winners and split ties."""
    season = Season(
        season_year=2025,
        league_id="test_league",
        league_name="Test League",
        is_active=True,
        regular_season_weeks=14,
        weekly_win_payout=Decimal("10.00"),
        weekly_high_score_payout=Decimal("10.00"),
        weekly_high_score_loss_payout=Decimal("10.00"),
    )
    m1 = Manager(espn_member_id="{M1}", display_name="Manager 1")
    m2 = Manager(espn_member_id="{M2}", display_name="Manager 2")
    m3 = Manager(espn_member_id="{M3}", display_name="Manager 3")
    m4 = Manager(espn_member_id="{M4}", display_name="Manager 4")
    db_session.add_all([season, m1, m2, m3, m4])
    db_session.flush()

    t1 = Team(season_year=2025, espn_team_id=1, team_name="T1", manager_id=m1.id)
    t2 = Team(season_year=2025, espn_team_id=2, team_name="T2", manager_id=m2.id)
    t3 = Team(season_year=2025, espn_team_id=3, team_name="T3", manager_id=m3.id)
    t4 = Team(season_year=2025, espn_team_id=4, team_name="T4", manager_id=m4.id)
    db_session.add_all([t1, t2, t3, t4])
    db_session.flush()

    # Week 1: Clean single winner for high score and high score loss
    # Matchup 1: T1 (145.20) beats T2 (132.80)
    # Matchup 2: T3 (120.00) beats T4 (110.50)
    matchup1 = Matchup(
        season_year=2025,
        week=1,
        espn_matchup_id=101,
        matchup_type="REGULAR",
        home_team_id=t1.id,
        away_team_id=t2.id,
        home_score=Decimal("145.20"),
        away_score=Decimal("132.80"),
        winner_team_id=t1.id,
        is_completed=True,
    )
    matchup2 = Matchup(
        season_year=2025,
        week=1,
        espn_matchup_id=102,
        matchup_type="REGULAR",
        home_team_id=t3.id,
        away_team_id=t4.id,
        home_score=Decimal("120.00"),
        away_score=Decimal("110.50"),
        winner_team_id=t3.id,
        is_completed=True,
    )
    db_session.add_all([matchup1, matchup2])
    db_session.flush()

    w1_entries = reconcile_week_ledger(db_session, season, week=1)
    assert len(w1_entries) == 4
    # T1: WEEKLY_WIN ($10.00) + WEEKLY_HIGH_SCORE ($10.00)
    t1_payouts = {e.entry_type: e.amount for e in w1_entries if e.manager_id == m1.id}
    assert t1_payouts == {"WEEKLY_WIN": Decimal("10.00"), "WEEKLY_HIGH_SCORE": Decimal("10.00")}

    # T3: WEEKLY_WIN ($10.00)
    t3_payouts = {e.entry_type: e.amount for e in w1_entries if e.manager_id == m3.id}
    assert t3_payouts == {"WEEKLY_WIN": Decimal("10.00")}

    # T2: WEEKLY_HIGH_SCORE_LOSS ($10.00) (scored 132.80 in a loss vs T4's 110.50)
    t2_payouts = {e.entry_type: e.amount for e in w1_entries if e.manager_id == m2.id}
    assert t2_payouts == {"WEEKLY_HIGH_SCORE_LOSS": Decimal("10.00")}

    # T4: 0 payouts
    t4_payouts = [e for e in w1_entries if e.manager_id == m4.id]
    assert len(t4_payouts) == 0

    # Week 2: Tied high score ($10 prize split $5 each) and tied high score in a loss ($10 prize split $5 each)
    # Matchup 3: T1 (140.00) beats T2 (115.00)
    # Matchup 4: T3 (140.00) beats T4 (115.00)
    matchup3 = Matchup(
        season_year=2025,
        week=2,
        espn_matchup_id=201,
        matchup_type="REGULAR",
        home_team_id=t1.id,
        away_team_id=t2.id,
        home_score=Decimal("140.00"),
        away_score=Decimal("115.00"),
        winner_team_id=t1.id,
        is_completed=True,
    )
    matchup4 = Matchup(
        season_year=2025,
        week=2,
        espn_matchup_id=202,
        matchup_type="REGULAR",
        home_team_id=t3.id,
        away_team_id=t4.id,
        home_score=Decimal("140.00"),
        away_score=Decimal("115.00"),
        winner_team_id=t3.id,
        is_completed=True,
    )
    db_session.add_all([matchup3, matchup4])
    db_session.flush()

    w2_entries = reconcile_week_ledger(db_session, season, week=2)
    assert len(w2_entries) == 6

    # T1 & T3 each get $10 WEEKLY_WIN + $5.00 WEEKLY_HIGH_SCORE split
    for mgr_id in (m1.id, m3.id):
        p = {e.entry_type: e.amount for e in w2_entries if e.manager_id == mgr_id}
        assert p["WEEKLY_WIN"] == Decimal("10.00")
        assert p["WEEKLY_HIGH_SCORE"] == Decimal("5.00")

    # T2 & T4 each get $5.00 WEEKLY_HIGH_SCORE_LOSS split
    for mgr_id in (m2.id, m4.id):
        p = {e.entry_type: e.amount for e in w2_entries if e.manager_id == mgr_id}
        assert p == {"WEEKLY_HIGH_SCORE_LOSS": Decimal("5.00")}


def test_regular_season_most_points_and_placements_with_ante_changes(
    db_session: Session,
) -> None:
    """Verify regular-season most points ($30) timing (after week 14) and 1st-5th placements ($500/$300/$200/$150/$100)."""
    payout_rules = load_season_payout_rules(2024)
    season = Season(
        season_year=2024,
        league_id="league_ante_2024",
        league_name="Ante League 2024",
        is_active=True,
        is_completed=False,
        regular_season_weeks=14,
        current_week=14,  # Week 14 ongoing
        weekly_win_payout=payout_rules["weekly_win_payout"],
        weekly_high_score_payout=payout_rules["weekly_high_score_payout"],
        weekly_high_score_loss_payout=payout_rules["weekly_high_score_loss_payout"],
        champion_payout=payout_rules["champion_payout"],
        runner_up_payout=payout_rules["runner_up_payout"],
        third_place_payout=payout_rules["third_place_payout"],
        fourth_place_payout=payout_rules["fourth_place_payout"],
        fifth_place_payout=payout_rules["fifth_place_payout"],
        regular_season_most_points_payout=payout_rules["regular_season_most_points_payout"],
    )
    managers = [Manager(espn_member_id=f"{{MGR_{i}}}", display_name=f"Manager {i}") for i in range(1, 7)]
    db_session.add_all([season, *managers])
    db_session.flush()

    teams = [
        Team(
            season_year=2024,
            espn_team_id=i,
            team_name=f"Team {i}",
            manager_id=managers[i - 1].id,
            final_standing=i,
        )
        for i in range(1, 7)
    ]
    db_session.add_all(teams)
    db_session.flush()

    # Create regular season matchups for weeks 1 through 14
    # In week 14, let Team 1 have 1800 total regular season points, Team 2 have 1750, etc.
    reg_matchups: list[Matchup] = []
    for wk in range(1, 14):
        # 13 weeks of completed matchups
        m = Matchup(
            season_year=2024,
            week=wk,
            espn_matchup_id=1000 + wk,
            matchup_type="REGULAR",
            home_team_id=teams[0].id,
            away_team_id=teams[1].id,
            home_score=Decimal("120.00"),
            away_score=Decimal("110.00"),
            winner_team_id=teams[0].id,
            is_completed=True,
        )
        reg_matchups.append(m)

    # Week 14 matchup: initially is_completed = False
    m14 = Matchup(
        season_year=2024,
        week=14,
        espn_matchup_id=1014,
        matchup_type="REGULAR",
        home_team_id=teams[0].id,
        away_team_id=teams[1].id,
        home_score=Decimal("140.00"),
        away_score=Decimal("115.00"),
        winner_team_id=teams[0].id,
        is_completed=False,  # Still in progress!
    )
    reg_matchups.append(m14)
    db_session.add_all(reg_matchups)
    db_session.flush()

    # Rule: Playoffs start week 15 so regular season ending won't happen until after week 14!
    # Because week 14 is incomplete and current_week == 14, regular season has NOT ended
    res_ongoing = reconcile_regular_season_points_ledger(db_session, season)
    assert len(res_ongoing) == 0

    # Complete week 14 and advance current_week to 15 (playoffs start week 15)
    m14.is_completed = True
    season.current_week = 15
    db_session.flush()

    # Now regular season is ended! Reconcile should award $30.00 to Team 1 (most regular season points)
    res_ended = reconcile_regular_season_points_ledger(db_session, season)
    assert len(res_ended) == 1
    pts_entry = res_ended[0]
    assert pts_entry.manager_id == managers[0].id
    assert pts_entry.entry_type == "REGULAR_SEASON_MOST_POINTS"
    assert pts_entry.amount == Decimal("30.00")
    assert pts_entry.week is None

    # Test Playoff Placements (1st: $500, 2nd: $300, 3rd: $200, 4th: $150, 5th: $100)
    # Season completes after championship
    season.is_completed = True
    podium_entries = reconcile_podium_ledger(db_session, season)
    assert len(podium_entries) == 5

    payout_by_type = {e.entry_type: e.amount for e in podium_entries}
    assert payout_by_type["CHAMPION"] == Decimal("500.00")
    assert payout_by_type["RUNNER_UP"] == Decimal("300.00")
    assert payout_by_type["THIRD_PLACE"] == Decimal("200.00")
    assert payout_by_type["FOURTH_PLACE"] == Decimal("150.00")
    assert payout_by_type["FIFTH_PLACE"] == Decimal("100.00")

    # Team 6 (final_standing=6) gets no placement prize
    t6_entries = [e for e in podium_entries if e.manager_id == managers[5].id]
    assert len(t6_entries) == 0


def test_historical_season_preserves_old_earnings(db_session: Session) -> None:
    """Verify that historical seasons (2022/2023) preserve old payouts ($600/$300/$100) with $0 for 4th/5th/most points."""
    rules_2022 = load_season_payout_rules(2022)
    assert rules_2022["champion_payout"] == Decimal("600.00")
    assert rules_2022["runner_up_payout"] == Decimal("300.00")
    assert rules_2022["third_place_payout"] == Decimal("100.00")
    assert rules_2022["fourth_place_payout"] == Decimal("0.00")
    assert rules_2022["fifth_place_payout"] == Decimal("0.00")
    assert rules_2022["regular_season_most_points_payout"] == Decimal("0.00")

    season_2022 = Season(
        season_year=2022,
        league_id="league_legacy",
        league_name="Legacy League",
        is_active=False,
        is_completed=True,
        regular_season_weeks=14,
        current_week=17,
        champion_payout=rules_2022["champion_payout"],
        runner_up_payout=rules_2022["runner_up_payout"],
        third_place_payout=rules_2022["third_place_payout"],
        fourth_place_payout=rules_2022["fourth_place_payout"],
        fifth_place_payout=rules_2022["fifth_place_payout"],
        regular_season_most_points_payout=rules_2022["regular_season_most_points_payout"],
    )
    managers = [Manager(espn_member_id=f"{{LEG_MGR_{i}}}", display_name=f"Legacy Mgr {i}") for i in range(1, 6)]
    db_session.add_all([season_2022, *managers])
    db_session.flush()

    teams = [
        Team(
            season_year=2022,
            espn_team_id=i,
            team_name=f"Legacy Team {i}",
            manager_id=managers[i - 1].id,
            final_standing=i,
        )
        for i in range(1, 6)
    ]
    db_session.add_all(teams)
    db_session.flush()

    # Reconciling 2022 podium preserves ONLY 1st, 2nd, 3rd awards (600, 300, 100)
    entries_2022 = reconcile_podium_ledger(db_session, season_2022)
    assert len(entries_2022) == 3
    types_2022 = {e.entry_type for e in entries_2022}
    assert types_2022 == {"CHAMPION", "RUNNER_UP", "THIRD_PLACE"}

    champ = next(e for e in entries_2022 if e.entry_type == "CHAMPION")
    assert champ.amount == Decimal("600.00")

    # Regular season points for 2022 awards nothing because regular_season_most_points_payout is 0.00
    pts_2022 = reconcile_regular_season_points_ledger(db_session, season_2022)
    assert len(pts_2022) == 0


# ==============================================================================
# 6. EspnClient Unit Tests
# ==============================================================================


def test_espn_client_configuration_and_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify cookie parsing, unquoting, and environment variable resolution."""
    monkeypatch.setenv("ESPN_LEAGUE_IDS", "900098275, 12345678")
    monkeypatch.setenv("ESPN_S2", "abc%2Bdef%2F123%3D%3D")
    monkeypatch.setenv("ESPN_SWID", "{TEST-SWID}")

    ids = get_configured_league_ids()
    assert ids == ["900098275", "12345678"]

    client = EspnClient()
    assert client.league_id == "900098275"
    assert client.espn_s2 == "abc+def/123=="
    assert client.swid == "{TEST-SWID}"

    cookies = client._build_cookies()
    assert cookies["espn_s2"] == "abc+def/123=="
    assert cookies["SWID"] == "{TEST-SWID}"


def test_espn_client_modern_vs_legacy_endpoints() -> None:
    """Verify modern v3 vs legacy URL template selection."""
    mock_session = MagicMock(spec=requests.Session)
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"seasonId": 2023}
    mock_session.get.return_value = mock_resp

    client = EspnClient(league_id="12345678", session=mock_session)

    # Modern (>= 2018)
    client.fetch_league(season_year=2023)
    call_url = mock_session.get.call_args[0][0]
    assert "apis/v3/games/ffl/seasons/2023/segments/0/leagues/12345678" in call_url

    # Legacy (< 2018)
    mock_resp.json.return_value = [{"seasonId": 2017}]
    client.fetch_league(season_year=2017)
    legacy_url = mock_session.get.call_args[0][0]
    assert "apis/v3/games/ffl/leagueHistory/12345678?seasonId=2017" in legacy_url


def test_espn_client_error_handling() -> None:
    """Verify 401/403/404 handling with allow_inaccessible True vs False."""
    mock_session = MagicMock(spec=requests.Session)
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    mock_session.get.return_value = mock_resp

    client = EspnClient(league_id="12345678", session=mock_session)

    # When allow_inaccessible=True, returns None
    result = client.fetch_league(season_year=2020, allow_inaccessible=True)
    assert result is None

    # When allow_inaccessible=False, raises EspnAccessError
    with pytest.raises(EspnAccessError) as exc_info:
        client.fetch_league(season_year=2020, allow_inaccessible=False)
    assert exc_info.value.status_code == 401
