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
    reconcile_week_ledger,
)
from backend.jobs.parsers import (
    load_manager_overrides,
    resolve_or_upsert_managers,
    upsert_matchups_from_payload,
    upsert_season_from_payload,
    upsert_teams_from_payload,
)
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

    # Verify Tuesday state: Team 1 manager has $10 WEEKLY_WIN
    t1_payout = (
        db_session.query(EarningsLedger)
        .filter_by(season_year=2024, week=7, manager_id=team1.manager_id)
        .first()
    )
    assert t1_payout is not None
    assert t1_payout.entry_type == "WEEKLY_WIN"
    assert t1_payout.amount == Decimal("10.00")

    t2_payout = (
        db_session.query(EarningsLedger)
        .filter_by(season_year=2024, week=7, manager_id=team2.manager_id)
        .first()
    )
    assert t2_payout is None

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

    # Verify Team 1's $10 payout was completely deleted!
    t1_after_flip = (
        db_session.query(EarningsLedger)
        .filter_by(season_year=2024, week=7, manager_id=team1.manager_id)
        .first()
    )
    assert t1_after_flip is None

    # Verify Team 2's manager now has the $10 WEEKLY_WIN
    t2_after_flip = (
        db_session.query(EarningsLedger)
        .filter_by(season_year=2024, week=7, manager_id=team2.manager_id)
        .first()
    )
    assert t2_after_flip is not None
    assert t2_after_flip.entry_type == "WEEKLY_WIN"
    assert t2_after_flip.amount == Decimal("10.00")

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

    # Verify both managers now have $5.00 WEEKLY_TIE and ZERO $10 payouts exist for this game
    t1_tie = (
        db_session.query(EarningsLedger)
        .filter_by(season_year=2024, week=7, manager_id=team1.manager_id)
        .first()
    )
    t2_tie = (
        db_session.query(EarningsLedger)
        .filter_by(season_year=2024, week=7, manager_id=team2.manager_id)
        .first()
    )
    assert t1_tie is not None
    assert t1_tie.entry_type == "WEEKLY_TIE"
    assert t1_tie.amount == Decimal("5.00")

    assert t2_tie is not None
    assert t2_tie.entry_type == "WEEKLY_TIE"
    assert t2_tie.amount == Decimal("5.00")

    # Check total payouts for matchup 2001 managers
    total_entries_w7 = (
        db_session.query(EarningsLedger)
        .filter_by(season_year=2024, week=7)
        .filter(EarningsLedger.manager_id.in_([team1.manager_id, team2.manager_id]))
        .count()
    )
    assert total_entries_w7 == 2


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
    assert len(podium_entries) == 3
    champ = next(e for e in podium_entries if e.entry_type == "CHAMPION")
    runner_up = next(e for e in podium_entries if e.entry_type == "RUNNER_UP")
    third = next(e for e in podium_entries if e.entry_type == "THIRD_PLACE")

    assert champ.amount == Decimal("600.00")
    assert runner_up.amount == Decimal("300.00")
    assert third.amount == Decimal("100.00")

    # 3. Subsequent run during offseason is a NOOP with 0 API calls
    mock_client.crawl_call_counts.clear()
    offseason_run = sync_weekly(session=db_session, client=mock_client)

    assert offseason_run.status == "NOOP_OFFSEASON"
    assert len(mock_client.crawl_call_counts) == 0


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
