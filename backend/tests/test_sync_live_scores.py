"""backend/tests/test_sync_live_scores.py - Unit & Integration Tests for 10-Minute Live Score Sync Job.

Covers:
  1. Offseason no-op (when no active season or active season is completed) with 0 network calls.
  2. Live in-week player point & matchup score updates from mock ESPN payload (single lightweight fetch).
  3. Offline snapshot fallback (from mBoxscore or mCombined RawEspnSnapshot when network fails).
  4. POST /api/v1/admin/sync-live authentication & execution, and GET /api/v1/meta last_live_sync_at.
"""

from __future__ import annotations

import copy
from decimal import Decimal
from typing import Any

import pytest
import requests
from sqlalchemy.orm import Session, sessionmaker

from backend.app import create_app
from backend.database import create_db_engine, init_db
from backend.jobs.espn_client import EspnClient
from backend.jobs.sync_live_scores import sync_live_scores
from backend.models.earnings import EarningsLedger
from backend.models.lineup import WeeklyLineup
from backend.models.manager import Manager
from backend.models.matchup import Matchup
from backend.models.player import Player
from backend.models.raw_snapshot import RawEspnSnapshot
from backend.models.season import Season
from backend.models.sync_run import SyncRun
from backend.models.team import Team


@pytest.fixture
def db_session_and_factory() -> Any:
    """Provide an isolated in-memory SQLite database session and session factory."""
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session, session_factory
    finally:
        session.close()
        engine.dispose()


class MockLiveEspnClient(EspnClient):
    """Offline mock client recording fetch_league calls and parameters."""

    def __init__(
        self,
        payload_to_return: dict[str, Any] | None = None,
        should_raise: bool = False,
    ) -> None:
        super().__init__(league_id="12345678", espn_s2="mock_s2", swid="{MOCK-SWID}")
        self.payload_to_return = payload_to_return
        self.should_raise = should_raise
        self.calls: list[dict[str, Any]] = []

    def fetch_league(
        self,
        season_year: int,
        views: list[str] | None = None,
        x_fantasy_filter: dict[str, Any] | None = None,
        allow_inaccessible: bool = True,
        league_id: str | None = None,
        scoring_period_id: int | None = None,
    ) -> dict[str, Any] | None:
        self.calls.append(
            {
                "season_year": season_year,
                "views": views,
                "x_fantasy_filter": x_fantasy_filter,
                "allow_inaccessible": allow_inaccessible,
                "league_id": league_id,
                "scoring_period_id": scoring_period_id,
            }
        )
        if self.should_raise:
            raise requests.RequestException("Simulated network timeout")
        if self.payload_to_return is not None:
            return copy.deepcopy(self.payload_to_return)
        return None


def _seed_active_season_base(session: Session) -> tuple[Season, Team, Team, Matchup]:
    """Seed a minimal active season (2024, Week 8) with 2 teams and 1 in-progress matchup."""
    season = Season(
        season_year=2024,
        league_id="12345678",
        league_name="Test Live League",
        is_active=True,
        is_completed=False,
        regular_season_weeks=14,
        current_week=8,
    )
    m1 = Manager(espn_member_id="{MGR-1}", display_name="Alice Archer", is_active=True)
    m2 = Manager(espn_member_id="{MGR-2}", display_name="Bob Baker", is_active=True)
    session.add_all([season, m1, m2])
    session.flush()

    t1 = Team(
        season_year=2024,
        espn_team_id=1,
        team_name="Archer Assassins",
        team_abbrev="ARCH",
        manager_id=m1.id,
    )
    t2 = Team(
        season_year=2024,
        espn_team_id=2,
        team_name="Baker's Dozen",
        team_abbrev="BAKE",
        manager_id=m2.id,
    )
    session.add_all([t1, t2])
    session.flush()

    matchup = Matchup(
        season_year=2024,
        week=8,
        espn_matchup_id=42,
        matchup_type="REGULAR",
        home_team_id=t1.id,
        away_team_id=t2.id,
        home_score=Decimal("45.00"),
        away_score=Decimal("38.50"),
        is_completed=False,
    )
    session.add(matchup)
    session.commit()
    return season, t1, t2, matchup


def _build_mock_live_payload() -> dict[str, Any]:
    """Construct a mock ESPN mBoxscore + mMatchupScore payload for Week 8."""
    return {
        "seasonId": 2024,
        "scoringPeriodId": 8,
        "schedule": [
            {
                "id": 42,
                "matchupPeriodId": 8,
                "playoffTierType": "NONE",
                "winner": "UNDECIDED",
                "home": {
                    "teamId": 1,
                    "totalPoints": 112.40,
                    "totalProjectedPoints": 124.80,
                    "rosterForCurrentScoringPeriod": {
                        "entries": [
                            {
                                "playerId": 4040715,
                                "lineupSlotId": 0,  # QB starter
                                "appliedStatTotal": 28.40,
                                "projectedStatTotal": 24.10,
                                "playerPoolEntry": {
                                    "id": 4040715,
                                    "appliedStatTotal": 28.40,
                                    "projectedStatTotal": 24.10,
                                    "player": {
                                        "id": 4040715,
                                        "fullName": "Jalen Hurts",
                                        "defaultPositionId": 1,
                                        "proTeamId": 21,
                                        "injuryStatus": "ACTIVE",
                                        "injured": False,
                                    },
                                },
                            },
                            {
                                "playerId": 4241389,
                                "lineupSlotId": 20,  # BE bench
                                "appliedStatTotal": 14.20,
                                "projectedStatTotal": 11.50,
                                "playerPoolEntry": {
                                    "id": 4241389,
                                    "appliedStatTotal": 14.20,
                                    "projectedStatTotal": 11.50,
                                    "player": {
                                        "id": 4241389,
                                        "fullName": "CeeDee Lamb",
                                        "defaultPositionId": 3,
                                        "proTeamId": 6,
                                        "injuryStatus": "QUESTIONABLE",
                                        "injured": True,
                                    },
                                },
                            },
                        ]
                    },
                },
                "away": {
                    "teamId": 2,
                    "totalPoints": 98.75,
                    "totalProjectedPoints": 110.20,
                    "rosterForCurrentScoringPeriod": {
                        "entries": [
                            {
                                "playerId": 3117251,
                                "lineupSlotId": 2,  # RB starter
                                "appliedStatTotal": 22.75,
                                "projectedStatTotal": 19.80,
                                "playerPoolEntry": {
                                    "id": 3117251,
                                    "appliedStatTotal": 22.75,
                                    "projectedStatTotal": 19.80,
                                    "player": {
                                        "id": 3117251,
                                        "fullName": "Christian McCaffrey",
                                        "defaultPositionId": 2,
                                        "proTeamId": 25,
                                        "injuryStatus": "ACTIVE",
                                        "injured": False,
                                    },
                                },
                            }
                        ]
                    },
                },
            }
        ],
    }


def test_sync_live_scores_offseason_noop(db_session_and_factory: Any) -> None:
    """Verify offseason no-op when no active season exists or active season is completed."""
    session, _ = db_session_and_factory
    mock_client = MockLiveEspnClient(payload_to_return=_build_mock_live_payload())

    # Case 1: No seasons in DB at all
    run1 = sync_live_scores(session=session, client=mock_client)
    assert run1.run_type == "LIVE_SCORES"
    assert run1.status == "NOOP_OFFSEASON"
    assert run1.records_processed == 0
    assert len(mock_client.calls) == 0

    # Case 2: Completed season in DB (is_active=True, is_completed=True)
    completed_season = Season(
        season_year=2023,
        league_id="12345678",
        league_name="Completed League",
        is_active=True,
        is_completed=True,
        current_week=17,
    )
    session.add(completed_season)
    session.commit()

    run2 = sync_live_scores(session=session, client=mock_client)
    assert run2.run_type == "LIVE_SCORES"
    assert run2.status == "NOOP_OFFSEASON"
    assert run2.season_year == 2023
    assert run2.records_processed == 0
    assert len(mock_client.calls) == 0


def test_sync_live_scores_updates_matchups_and_lineups(db_session_and_factory: Any) -> None:
    """Verify single lightweight ESPN fetch updates live matchup scores, players, lineups, and snapshot."""
    session, _ = db_session_and_factory
    season, t1, t2, matchup = _seed_active_season_base(session)
    payload = _build_mock_live_payload()
    mock_client = MockLiveEspnClient(payload_to_return=payload)

    run = sync_live_scores(session=session, client=mock_client)
    session.commit()

    # 1. Verify SyncRun record
    assert run.run_type == "LIVE_SCORES"
    assert run.status == "SUCCESS"
    assert run.season_year == 2024
    assert run.week_range == "8"
    assert run.records_processed == 3  # 2 players on Team 1 + 1 player on Team 2

    # 2. Verify exactly ONE lightweight ESPN fetch call with mBoxscore + mMatchupScore
    assert len(mock_client.calls) == 1
    call = mock_client.calls[0]
    assert call["season_year"] == 2024
    assert call["views"] == ["mBoxscore", "mMatchupScore"]
    assert call["scoring_period_id"] == 8

    # 3. Verify matchup live scores & projections updated
    session.refresh(matchup)
    assert matchup.home_score == Decimal("112.40")
    assert matchup.away_score == Decimal("98.75")
    assert matchup.home_projected == Decimal("124.80")
    assert matchup.away_projected == Decimal("110.20")

    # 4. Verify players and weekly lineups updated
    hurts = session.get(Player, 4040715)
    assert hurts is not None
    assert hurts.full_name == "Jalen Hurts"
    assert hurts.default_position == "QB"
    assert hurts.pro_team == "PHI"

    hurts_lineup = (
        session.query(WeeklyLineup)
        .filter_by(season_year=2024, week=8, team_id=t1.id, player_id=4040715)
        .first()
    )
    assert hurts_lineup is not None
    assert hurts_lineup.slot_position == "QB"
    assert hurts_lineup.is_starter is True
    assert hurts_lineup.actual_points == Decimal("28.40")
    assert hurts_lineup.projected_points == Decimal("24.10")

    lamb_lineup = (
        session.query(WeeklyLineup)
        .filter_by(season_year=2024, week=8, team_id=t1.id, player_id=4241389)
        .first()
    )
    assert lamb_lineup is not None
    assert lamb_lineup.slot_position == "BE"
    assert lamb_lineup.is_starter is False
    assert lamb_lineup.actual_points == Decimal("14.20")
    assert lamb_lineup.weekly_stats.get("injury_status") == "QUESTIONABLE"
    assert lamb_lineup.weekly_stats.get("injured") is True

    # 5. Verify RawEspnSnapshot for (2024, "mBoxscore", 8) was stored
    snap = (
        session.query(RawEspnSnapshot)
        .filter_by(season_year=2024, view_name="mBoxscore", scoring_period=8)
        .first()
    )
    assert snap is not None
    assert snap.payload["scoringPeriodId"] == 8

    # 6. Verify earnings_ledger was NOT touched
    assert session.query(EarningsLedger).count() == 0


def test_sync_live_scores_offline_snapshot_fallback(db_session_and_factory: Any) -> None:
    """Verify fallback to stored RawEspnSnapshot when network call fails."""
    session, _ = db_session_and_factory
    season, t1, t2, matchup = _seed_active_season_base(session)
    payload = _build_mock_live_payload()

    # Pre-populate mCombined snapshot in DB
    session.add(
        RawEspnSnapshot(
            season_year=2024,
            view_name="mCombined",
            scoring_period=0,
            payload=payload,
        )
    )
    session.commit()

    # Client raises network error
    offline_client = MockLiveEspnClient(should_raise=True)
    run = sync_live_scores(session=session, week=8, client=offline_client)
    session.commit()

    assert run.status == "SUCCESS"
    assert run.records_processed == 3

    session.refresh(matchup)
    assert matchup.home_score == Decimal("112.40")
    assert matchup.away_score == Decimal("98.75")


def test_admin_sync_live_endpoint_and_meta_timestamp(
    db_session_and_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify POST /api/v1/admin/sync-live auth & trigger and GET /api/v1/meta last_live_sync_at."""
    session, session_factory = db_session_and_factory
    _seed_active_season_base(session)
    payload = _build_mock_live_payload()
    mock_client = MockLiveEspnClient(payload_to_return=payload)

    # Inject mock EspnClient into sync_live_scores when called via route
    monkeypatch.setattr(
        "backend.jobs.sync_live_scores.EspnClient",
        lambda *args, **kwargs: mock_client,
    )

    app = create_app({"TESTING": True, "SESSION_FACTORY": session_factory})
    client = app.test_client()

    # 1. Unauthorized without commissioner password
    res_unauth = client.post("/api/v1/admin/sync-live", json={"week": 8})
    assert res_unauth.status_code == 401

    # 2. Authorized with X-Admin-Password header
    res_ok = client.post(
        "/api/v1/admin/sync-live",
        json={"week": 8},
        headers={"X-Admin-Password": "commish"},
    )
    assert res_ok.status_code == 200
    data = res_ok.get_json()
    assert data["status"] == "SUCCESS"
    assert data["season_year"] == 2024
    assert data["week_range"] == "8"
    assert data["records_processed"] == 3
    assert data["completed_at"] is not None

    # 3. Verify GET /api/v1/meta exposes last_live_sync_at in last_sync
    res_meta = client.get("/api/v1/meta")
    assert res_meta.status_code == 200
    meta_json = res_meta.get_json()
    assert "last_sync" in meta_json
    assert meta_json["last_sync"]["last_live_sync_at"] is not None
    assert meta_json["last_sync"]["last_sync_status"] == "SUCCESS"
    assert session.query(SyncRun).filter_by(run_type="LIVE_SCORES", status="SUCCESS").count() == 1
