"""backend/tests/test_ingestion_deep.py - Comprehensive Tests for Deep Ingestion Engine.

Covers:
  1. Canonical Player upsert from roster/boxscore/transaction payloads with position/team mapping,
     CDN headshot URLs, and None for D/ST.
  2. WeeklyLineup start/bench/IR extraction and automatic calculation of Matchup home_optimal_score
     (Max PF including bench-boosted points while excluding IR) and home_bench_points.
  3. Transactions: FREE_AGENT, EXECUTED WAIVER, FAILED WAIVER_ERROR (OUTBID, INSUFFICIENT_FUNDS),
     and automatic linking of losing bids to winning claims for FAAB Bidding Wars.
  4. Trade deduplication (TRADE_ACCEPT vs duplicate TRADE_UPHOLD) and Trade + TransactionItem creation.
  5. Pre-2018 / pre-2019 legacy season handling (has_transaction_data=False, has_boxscore_data=False).
  6. Scoped execution in backfill_history (full crawl + snapshot replay) vs sync_weekly (rolling window delta).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session, sessionmaker

from backend.database import create_db_engine, init_db
from backend.jobs.backfill_history import backfill_history
from backend.jobs.deep_parsers import (
    compute_optimal_score,
    normalize_position,
    normalize_pro_team,
    normalize_slot_position,
    upsert_draft_picks_from_payload,
    upsert_players_from_payload,
    upsert_transactions_from_payload,
    upsert_weekly_lineups_from_payload,
)
from backend.jobs.espn_client import EspnClient
from backend.jobs.parsers import (
    resolve_or_upsert_managers,
    upsert_matchups_from_payload,
    upsert_season_from_payload,
    upsert_teams_from_payload,
)
from backend.jobs.sync_weekly import sync_weekly
from backend.models.draft import DraftPick
from backend.models.lineup import WeeklyLineup
from backend.models.matchup import Matchup
from backend.models.player import Player
from backend.models.trade import Trade
from backend.models.transaction import Transaction

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
        return self.fixture_map.get(season_year)


# ==============================================================================
# 1. Canonical Player Upserter Tests
# ==============================================================================


def test_player_normalization_and_upsert(db_session: Session) -> None:
    """Verify player position mapping, NFL pro team mapping, and headshot URLs."""
    # Test normalization helpers
    assert normalize_position(1) == "QB"
    assert normalize_position(2) == "RB"
    assert normalize_position(3) == "WR"
    assert normalize_position(4) == "TE"
    assert normalize_position(5) == "K"
    assert normalize_position(16) == "D/ST"
    assert normalize_position("DST") == "D/ST"
    assert normalize_position("DEF") == "D/ST"

    assert normalize_pro_team(2) == "BUF"
    assert normalize_pro_team(25) == "SF"
    assert normalize_pro_team(0) == "FA"
    assert normalize_pro_team("WSH") == "WAS"
    assert normalize_pro_team("OAK") == "LV"

    assert normalize_slot_position(0) == "QB"
    assert normalize_slot_position(2) == "RB"
    assert normalize_slot_position(20) == "BE"
    assert normalize_slot_position(21) == "IR"
    assert normalize_slot_position(23) == "FLEX"

    fixture = load_fixture("espn_deep_2023.json")
    players = upsert_players_from_payload(db_session, fixture)

    # Verify standard player (Josh Allen: QB, BUF)
    assert 103 in players
    p_allen = players[103]
    assert p_allen.full_name == "Josh Allen"
    assert p_allen.default_position == "QB"
    assert p_allen.pro_team == "BUF"
    assert p_allen.headshot_url == "https://a.espncdn.com/i/headshots/nfl/players/full/103.png"

    # Verify D/ST player (49ers D/ST: position D/ST, headshot is None)
    assert 16025 in players
    p_dst = players[16025]
    assert p_dst.full_name == "49ers D/ST"
    assert p_dst.default_position == "D/ST"
    assert p_dst.pro_team == "SF"
    assert p_dst.headshot_url is None

    # Verify idempotency on second run
    count_before = db_session.query(Player).count()
    upsert_players_from_payload(db_session, fixture)
    assert db_session.query(Player).count() == count_before


# ==============================================================================
# 2. Optimal Score & Bench Points Calculation Tests
# ==============================================================================


def test_compute_optimal_score_unit() -> None:
    """Verify compute_optimal_score selects highest legal starters and ignores IR."""
    entries = [
        {"player_id": 1, "default_position": "QB", "slot_position": "QB", "is_starter": True, "actual_points": 20.0},
        {"player_id": 2, "default_position": "RB", "slot_position": "RB", "is_starter": True, "actual_points": 10.0},
        {"player_id": 3, "default_position": "RB", "slot_position": "RB", "is_starter": True, "actual_points": 8.0},
        {"player_id": 4, "default_position": "WR", "slot_position": "WR", "is_starter": True, "actual_points": 15.0},
        {"player_id": 5, "default_position": "WR", "slot_position": "WR", "is_starter": True, "actual_points": 12.0},
        {"player_id": 6, "default_position": "TE", "slot_position": "TE", "is_starter": True, "actual_points": 7.0},
        {"player_id": 7, "default_position": "WR", "slot_position": "FLEX", "is_starter": True, "actual_points": 9.0},
        {"player_id": 8, "default_position": "D/ST", "slot_position": "D/ST", "is_starter": True, "actual_points": 5.0},
        {"player_id": 9, "default_position": "K", "slot_position": "K", "is_starter": True, "actual_points": 6.0},
        # Bench players: RB 10 has 22.0 pts (should replace RB 3 with 8 pts, boosting score by 14 pts)
        {"player_id": 10, "default_position": "RB", "slot_position": "BE", "is_starter": False, "actual_points": 22.0},
        {"player_id": 11, "default_position": "WR", "slot_position": "BE", "is_starter": False, "actual_points": 4.0},
        # IR player: RB 12 has 40.0 pts (on IR, must NOT be included in optimal score!)
        {"player_id": 12, "default_position": "RB", "slot_position": "IR", "is_starter": False, "actual_points": 40.0},
    ]

    # Starters sum: 20 + 10 + 8 + 15 + 12 + 7 + 9 + 5 + 6 = 92.0
    # Optimal: QB 20, RB1 22, RB2 10, WR1 15, WR2 12, TE 7, FLEX 9 (WR 7) or 8 (RB 3) -> 9, D/ST 5, K 6 = 106.0
    # Bench points: 22.0 + 4.0 = 26.0 (excluding IR)
    opt, bench = compute_optimal_score(entries)
    assert opt == Decimal("106.00")
    assert bench == Decimal("26.00")
    assert opt >= Decimal("92.00")


def test_weekly_lineup_and_matchup_optimal_scores(db_session: Session) -> None:
    """Verify weekly lineup parsing updates matchup optimal scores and bench points."""
    fixture = load_fixture("espn_deep_2023.json")
    mgr_map = resolve_or_upsert_managers(db_session, fixture)
    season = upsert_season_from_payload(db_session, fixture)
    team_map = upsert_teams_from_payload(db_session, season, fixture, mgr_map)
    upsert_matchups_from_payload(db_session, season, fixture, team_map)

    # Ingest lineups
    lineups = upsert_weekly_lineups_from_payload(db_session, season, fixture, team_map)
    assert len(lineups) > 0
    assert "injury_status" in lineups[0].weekly_stats
    assert "injured" in lineups[0].weekly_stats

    # Query Matchup 1 (Week 1, Team 1 vs Team 2)
    m1 = (
        db_session.query(Matchup)
        .filter_by(season_year=2023, week=1, espn_matchup_id=1)
        .first()
    )
    assert m1 is not None

    # Starter points: 134.00
    # Higher bench players Kyren (24.0) and Nacua (15.0) replace Bijan (14.0) and Wilson (10.0)
    # 134.00 - 24.00 + 39.00 = 149.00 optimal score!
    # Bench points: Kyren (24.0) + Nacua (15.0) = 39.00
    assert m1.home_score == Decimal("134.00")
    assert m1.home_optimal_score == Decimal("149.00")
    assert m1.home_bench_points == Decimal("39.00")
    assert m1.home_optimal_score >= m1.home_score

    # Away team has Mahomes (20.0), Hall (15.0) as starters, Gibbs (12.0) on bench
    assert m1.away_score == Decimal("105.00")
    assert m1.away_bench_points == Decimal("12.00")


# ==============================================================================
# 3. Transactions & FAAB Bidding Wars Tests
# ==============================================================================


def test_transactions_and_faab_bidding_war_linking(db_session: Session) -> None:
    """Verify free agents, waiver claims, and automatic linking of losing bids to winning claims."""
    fixture = load_fixture("espn_deep_2023.json")
    mgr_map = resolve_or_upsert_managers(db_session, fixture)
    season = upsert_season_from_payload(db_session, fixture)
    team_map = upsert_teams_from_payload(db_session, season, fixture, mgr_map)

    txs = upsert_transactions_from_payload(db_session, season, fixture, team_map)
    assert len(txs) > 0

    # 1. Winning claim for Puka Nacua
    tx_win = (
        db_session.query(Transaction)
        .filter_by(espn_transaction_id="tx_puka_win")
        .first()
    )
    assert tx_win is not None
    assert tx_win.transaction_type == "WAIVER"
    assert tx_win.status == "EXECUTED"
    assert tx_win.bid_amount == 35
    assert tx_win.waiver_priority == 3
    assert len(tx_win.items) == 1
    assert tx_win.items[0].player_id == 106
    assert tx_win.items[0].item_type == "ADD"

    # 2. Losing bid T2 with explicit relatedTransactionId
    tx_loss2 = (
        db_session.query(Transaction)
        .filter_by(espn_transaction_id="tx_puka_loss_t2")
        .first()
    )
    assert tx_loss2 is not None
    assert tx_loss2.status == "FAILED"
    assert tx_loss2.failure_reason == "OUTBID"
    assert tx_loss2.bid_amount == 27
    assert tx_loss2.related_espn_transaction_id == "tx_puka_win"

    # 3. Losing bid T3 with NO relatedTransactionId in payload — automatically linked to winning claim!
    tx_loss3 = (
        db_session.query(Transaction)
        .filter_by(espn_transaction_id="tx_puka_loss_t3")
        .first()
    )
    assert tx_loss3 is not None
    assert tx_loss3.status == "FAILED"
    assert tx_loss3.failure_reason == "OUTBID"
    assert tx_loss3.bid_amount == 19
    # AUTOMATIC LINK INVARIANT: Must link to winning waiver claim in same week/player!
    assert tx_loss3.related_espn_transaction_id == "tx_puka_win"

    # 4. Losing bid T4 with INSUFFICIENT_FUNDS
    tx_loss4 = (
        db_session.query(Transaction)
        .filter_by(espn_transaction_id="tx_puka_loss_t4")
        .first()
    )
    assert tx_loss4 is not None
    assert tx_loss4.status == "FAILED"
    assert tx_loss4.failure_reason == "INSUFFICIENT_FUNDS"
    assert tx_loss4.related_espn_transaction_id == "tx_puka_win"

    # 5. Free Agent Add and Drop
    tx_fa = (
        db_session.query(Transaction)
        .filter_by(espn_transaction_id="tx_fa_laporta")
        .first()
    )
    assert tx_fa is not None
    assert tx_fa.transaction_type == "FREE_AGENT"
    assert tx_fa.status == "EXECUTED"
    assert len(tx_fa.items) == 2
    types = {it.item_type for it in tx_fa.items}
    assert types == {"ADD", "DROP"}


# ==============================================================================
# 4. Trade Deduplication & Bilateral Trade Creation
# ==============================================================================


def test_trade_deduplication_and_model_creation(db_session: Session) -> None:
    """Verify TRADE_ACCEPT vs TRADE_UPHOLD deduplication and Trade ORM persistence."""
    fixture = load_fixture("espn_deep_2023.json")
    mgr_map = resolve_or_upsert_managers(db_session, fixture)
    season = upsert_season_from_payload(db_session, fixture)
    team_map = upsert_teams_from_payload(db_session, season, fixture, mgr_map)

    upsert_transactions_from_payload(db_session, season, fixture, team_map)

    # In fixture, there is trade_accept_t1_t2 and trade_uphold_t1_t2
    # Verify ONLY 1 trade transaction was created (trade_uphold duplicate was skipped)
    trade_txs = (
        db_session.query(Transaction)
        .filter(
            Transaction.season_year == 2023,
            Transaction.transaction_type == "TRADE",
        )
        .all()
    )
    assert len(trade_txs) == 1
    assert trade_txs[0].espn_transaction_id == "trade_accept_t1_t2"

    # Verify Trade entity created
    trades = db_session.query(Trade).filter_by(season_year=2023).all()
    assert len(trades) == 1
    t = trades[0]
    assert t.espn_transaction_id == "trade_accept_t1_t2"
    assert t.proposing_team_id == team_map[1].id
    assert t.accepting_team_id == team_map[2].id
    assert t.faab_from_accepter == 10
    assert t.status == "EXECUTED"


# ==============================================================================
# 5. Legacy Era Flag Handling
# ==============================================================================


def test_legacy_season_availability_flags(db_session: Session) -> None:
    """Verify pre-2018 seasons set has_transaction_data=False and pre-2019 set has_boxscore_data=False."""
    # 2017 legacy payload without transactions or boxscores
    legacy_payload = {
        "seasonId": 2017,
        "status": {"isActive": False, "finalScoringPeriod": 16},
        "settings": {"name": "Legacy League"},
        "members": [{"id": "{MEMBER-1}", "displayName": "Legacy Mgr"}],
        "teams": [
            {
                "id": 1,
                "name": "Team 1",
                "primaryOwner": "{MEMBER-1}",
                "record": {"overall": {"wins": 8, "losses": 5, "ties": 0}},
            }
        ],
        "schedule": [],
    }

    mgr_map = resolve_or_upsert_managers(db_session, legacy_payload)
    season = upsert_season_from_payload(db_session, legacy_payload)
    team_map = upsert_teams_from_payload(db_session, season, legacy_payload, mgr_map)

    upsert_weekly_lineups_from_payload(db_session, season, legacy_payload, team_map)
    upsert_transactions_from_payload(db_session, season, legacy_payload, team_map)

    assert season.has_transaction_data is False
    assert season.has_boxscore_data is False


# ==============================================================================
# 6. Scoped Execution: backfill_history vs sync_weekly
# ==============================================================================


def test_scoped_backfill_and_weekly_sync_execution(db_session: Session) -> None:
    """Verify backfill_history ingests all deep data while sync_weekly scopes to the rolling window."""
    f2023 = load_fixture("espn_deep_2023.json")
    mock_client = MockEspnClient({2023: f2023})

    # Step 1: Run full backfill
    run = backfill_history(
        session=db_session,
        from_snapshots=False,
        from_year=2023,
        to_year=2023,
        league_id="12345678",
        client=mock_client,
    )
    assert run.status == "SUCCESS"
    assert run.records_processed > 0

    # Verify deep tables populated
    assert db_session.query(Player).count() > 0
    assert db_session.query(WeeklyLineup).count() > 0
    assert db_session.query(Transaction).count() > 0
    assert db_session.query(Trade).count() > 0

    # Step 2: Verify snapshot replay idempotency with deep entities
    lineups_count = db_session.query(WeeklyLineup).count()
    tx_count = db_session.query(Transaction).count()
    trade_count = db_session.query(Trade).count()

    mock_client.crawl_call_counts.clear()
    replay = backfill_history(
        session=db_session,
        from_snapshots=True,
        from_year=2023,
        to_year=2023,
        league_id="12345678",
        client=mock_client,
    )
    assert replay.status == "SUCCESS"
    assert len(mock_client.crawl_call_counts) == 0

    # Strict idempotency
    assert db_session.query(WeeklyLineup).count() == lineups_count
    assert db_session.query(Transaction).count() == tx_count
    assert db_session.query(Trade).count() == trade_count

    # Step 3: Incremental sync_weekly on active season restricts to rolling window
    # Prepare active season for 2024
    f2024 = load_fixture("espn_league_2024.json")
    # Add week 8 boxscore entry and week 8 transaction
    f2024["schedule"] = [
        {
            "id": 101,
            "matchupPeriodId": 8,
            "playoffTierType": "NONE",
            "winner": "UNDECIDED",
            "home": {
                "teamId": 1,
                "totalPoints": 120.0,
                "rosterForCurrentScoringPeriod": {
                    "entries": [
                        {
                            "lineupSlotId": 0,
                            "playerPoolEntry": {
                                "id": 103,
                                "appliedStatTotal": 22.0,
                                "player": {"id": 103, "fullName": "Josh Allen", "defaultPositionId": 1, "proTeamId": 2},
                            },
                        }
                    ]
                },
            },
            "away": {"teamId": 2, "totalPoints": 110.0},
        }
    ]
    f2024["transactions"] = [
        {
            "id": "tx_2024_w08_fa",
            "type": "FREEAGENT",
            "status": "EXECUTED",
            "teamId": 1,
            "matchupPeriodId": 8,
            "scoringPeriodId": 8,
            "items": [{"playerId": 103, "type": "ADD", "toTeamId": 1}],
        },
        # Transaction in week 3 (outside rolling window 7-8)
        {
            "id": "tx_2024_w03_old",
            "type": "FREEAGENT",
            "status": "EXECUTED",
            "teamId": 1,
            "matchupPeriodId": 3,
            "scoringPeriodId": 3,
            "items": [{"playerId": 103, "type": "ADD", "toTeamId": 1}],
        },
    ]

    mock_client.fixture_map[2024] = f2024
    # Upsert active season
    mgr_map = resolve_or_upsert_managers(db_session, f2024)
    s2024 = upsert_season_from_payload(db_session, f2024)
    t2024 = upsert_teams_from_payload(db_session, s2024, f2024, mgr_map)
    upsert_matchups_from_payload(db_session, s2024, f2024, t2024)
    db_session.commit()

    # Run sync_weekly
    sync_run = sync_weekly(session=db_session, client=mock_client)
    assert sync_run.status == "SUCCESS"
    assert sync_run.week_range == "7-8"

    # Week 8 transaction was ingested, but week 3 transaction was NOT ingested!
    assert db_session.query(Transaction).filter_by(espn_transaction_id="tx_2024_w08_fa").first() is not None
    assert db_session.query(Transaction).filter_by(espn_transaction_id="tx_2024_w03_old").first() is None


def test_draft_picks_parsing_and_resolution(db_session: Session) -> None:
    """Verifies draft pick extraction, keeper flags, player resolution, and idempotency."""
    f2023 = load_fixture("espn_deep_2023.json")
    mgr_map = resolve_or_upsert_managers(db_session, f2023)
    season = upsert_season_from_payload(db_session, f2023)
    team_map = upsert_teams_from_payload(db_session, season, f2023, mgr_map)

    # Simulated draftDetail payload with 3 picks
    draft_payload = {
        "seasonId": 2023,
        "draftDetail": {
            "drafted": True,
            "inProgress": False,
            "picks": [
                {
                    "overallPickNumber": 1,
                    "roundId": 1,
                    "roundPickNumber": 1,
                    "teamId": 1,
                    "playerId": 4362628,
                    "bidAmount": 0,
                    "keeper": False,
                    "lineupSlotId": 4,
                    "autoDraftTypeId": 0,
                },
                {
                    "overallPickNumber": 2,
                    "roundId": 1,
                    "roundPickNumber": 2,
                    "teamId": 2,
                    "playerId": 9999999,  # Unresolved player to test fallback
                    "bidAmount": 15,
                    "keeper": True,
                    "lineupSlotId": 2,
                    "autoDraftTypeId": 0,
                },
            ],
        },
    }

    # First run: parses both picks and creates fallback for player 9999999
    picks = upsert_draft_picks_from_payload(db_session, season, draft_payload, team_map)
    assert len(picks) == 2

    p1 = db_session.query(DraftPick).filter_by(season_year=2023, overall_pick=1).first()
    assert p1 is not None
    assert p1.round == 1
    assert p1.round_pick == 1
    assert p1.team_id == team_map[1].id
    assert p1.player_id == 4362628
    assert p1.is_keeper is False
    assert p1.bid_amount == 0

    p2 = db_session.query(DraftPick).filter_by(season_year=2023, overall_pick=2).first()
    assert p2 is not None
    assert p2.is_keeper is True
    assert p2.bid_amount == 15
    assert db_session.get(Player, 9999999) is not None

    # Idempotent re-run
    picks_again = upsert_draft_picks_from_payload(db_session, season, draft_payload, team_map)
    assert len(picks_again) == 2
    assert db_session.query(DraftPick).filter_by(season_year=2023).count() == 2


def test_canonical_trade_overrides_multi_trades_and_supplemental_picks(db_session):
    """Verifies canonical espn_team_id trade overrides, supplemental future draft picks,
    accurate NFL week inference for communication topics, and same-pair multi-trade preservation."""
    from backend.models import Trade, TradedDraftPick, TradeOverride
    from backend.services.drafts_service import get_draft_data
    from backend.services.trades_service import get_trades_trends

    f2023 = load_fixture("espn_deep_2023.json")
    mgr_map = resolve_or_upsert_managers(db_session, f2023)
    season = upsert_season_from_payload(db_session, f2023)
    season.is_active = True
    season.is_completed = False
    team_map = upsert_teams_from_payload(db_session, season, f2023, mgr_map)
    upsert_players_from_payload(db_session, f2023)

    # Seed a canonical TradeOverride with supplemental future draft picks (keyed by espn_team_id, not DB team.id)
    override = TradeOverride(
        season_year=2023,
        espn_transaction_id="tx-exec-1",
        proposing_espn_team_id=1,
        accepting_espn_team_id=2,
        supplemental_picks=[
            {"receiving_espn_team_id": 1, "season_year": 2024, "round": 16},
            {"receiving_espn_team_id": 2, "season_year": 2024, "round": 4},
        ],
    )
    db_session.add(override)
    db_session.flush()

    # Construct payload with:
    # 1. Intermediate TRADE_ACCEPT (status=None, executionType=EXECUTE) -> should be ignored
    # 2. Single-manager TRADE_VETO ballot (executionType=EXECUTE) -> should be ignored
    # 3. Two distinct executed trades between the SAME team pair (Team 1 and Team 2) in Week 6
    #    via communication topics (224 proposal + 244 execution) with October timestamps
    oct_14_2023_ms = 1697300000000  # Mid-October 2023 -> Week 6
    oct_15_2023_ms = 1697386400000  # Next day -> still Week 6
    payload = {
        "seasonId": 2023,
        "scoringPeriodId": 1,
        "Schedule": [],  # Empty schedule to simulate single-week sync where schedule timestamps are absent
        "transactions": [
            {
                "id": "tx-accept-intermediate",
                "type": "TRADE_ACCEPT",
                "status": None,
                "executionType": "EXECUTE",
                "scoringPeriodId": 6,
                "teamId": 2,
                "relatedTransactionId": "tx-prop-1",
                "items": [],
            },
            {
                "id": "tx-veto-ballot",
                "type": "TRADE_VETO",
                "status": None,
                "executionType": "EXECUTE",
                "scoringPeriodId": 6,
                "teamId": 3,
                "relatedTransactionId": "tx-prop-1",
                "items": [],
            },
        ],
        "topics": [
            {
                "id": "topic-prop-1",
                "type": "ACTIVITY_TRANSACTIONS",
                "date": oct_14_2023_ms - 3600000,
                "messages": [
                    {
                        "messageTypeId": 224,
                        "targetId": "tx-prop-1",
                        "from": 1,
                        "to": 2,
                        "date": oct_14_2023_ms - 3600000,
                    }
                ],
            },
            {
                "id": "tx-exec-1",
                "type": "ACTIVITY_TRANSACTIONS",
                "date": oct_14_2023_ms,
                "messages": [
                    {
                        "messageTypeId": 244,
                        "targetId": 4248339,
                        "date": oct_14_2023_ms,
                        "for": 1,
                        "to": 2,
                    },
                    {
                        "messageTypeId": 244,
                        "targetId": 4362628,
                        "date": oct_14_2023_ms,
                        "for": 2,
                        "to": 1,
                    },
                ],
            },
            {
                "id": "topic-prop-2",
                "type": "ACTIVITY_TRANSACTIONS",
                "date": oct_15_2023_ms - 3600000,
                "messages": [
                    {
                        "messageTypeId": 224,
                        "targetId": "tx-prop-2",
                        "from": 1,
                        "to": 2,
                        "date": oct_15_2023_ms - 3600000,
                    }
                ],
            },
            {
                "id": "tx-exec-2",
                "type": "ACTIVITY_TRANSACTIONS",
                "date": oct_15_2023_ms,
                "messages": [
                    {
                        "messageTypeId": 244,
                        "targetId": 3117251,
                        "date": oct_15_2023_ms,
                        "for": 1,
                        "to": 2,
                    },
                    {
                        "messageTypeId": 244,
                        "targetId": 4047365,
                        "date": oct_15_2023_ms,
                        "for": 2,
                        "to": 1,
                    },
                ],
            },
        ],
    }

    upsert_transactions_from_payload(db_session, season, payload, team_map)
    db_session.commit()

    # Both executed trades between Team 1 and Team 2 must exist independently in Week 6
    t1 = db_session.query(Trade).filter_by(season_year=2023, espn_transaction_id="tx-exec-1").first()
    t2 = db_session.query(Trade).filter_by(season_year=2023, espn_transaction_id="tx-exec-2").first()
    assert t1 is not None
    assert t2 is not None
    assert t1.id != t2.id
    assert t1.week == 6
    assert t2.week == 6
    assert t1.status == "EXECUTED"
    assert t2.status == "EXECUTED"

    # Intermediate TRADE_ACCEPT and TRADE_VETO ballot must not create Trade records
    assert db_session.query(Trade).filter_by(espn_transaction_id="tx-accept-intermediate").first() is None
    assert db_session.query(Trade).filter_by(espn_transaction_id="tx-veto-ballot").first() is None

    # Supplemental 2024 picks on tx-exec-1 must be materialized into TradedDraftPick rows
    traded_2024 = db_session.query(TradedDraftPick).filter_by(draft_year=2024).order_by(TradedDraftPick.round).all()
    assert len(traded_2024) == 2
    assert traded_2024[0].round == 4
    assert traded_2024[0].transaction_item.from_team_id == team_map[1].id
    assert traded_2024[0].transaction_item.to_team_id == team_map[2].id
    assert traded_2024[1].round == 16
    assert traded_2024[1].transaction_item.from_team_id == team_map[2].id
    assert traded_2024[1].transaction_item.to_team_id == team_map[1].id

    # Verify trades trends service returns both executed trades and includes the supplemental picks in assets_received
    trends = get_trades_trends(db_session, season_filter=2023)
    exec_ids = {r["espn_transaction_id"] for r in trends["trades"]}
    assert "tx-exec-1" in exec_ids
    assert "tx-exec-2" in exec_ids
    tx1_record = next(r for r in trends["trades"] if r["espn_transaction_id"] == "tx-exec-1")
    side_a_names = [p["full_name"] for p in tx1_record["sides"][0]["assets_received"]]
    side_b_names = [p["full_name"] for p in tx1_record["sides"][1]["assets_received"]]
    assert "2024 Round 16 Pick" in side_a_names
    assert "2024 Round 4 Pick" in side_b_names

    # Verify Drafts page future draft board shows the traded 2024 picks
    drafts_data = get_draft_data(db_session, season_filter=None)
    assert drafts_data["future_draft"] is not None
    assert len(drafts_data["future_draft"]["traded_picks_log"]) == 2


def test_week_zero_and_playoff_bye_roster_persistence(db_session):
    """Verify week=0 opening rosters and playoff bye week rosters are captured without inflating points."""
    from backend.models.manager import Manager
    from backend.models.season import Season
    from backend.models.team import Team

    season = Season(
        season_year=2025,
        league_id="12345",
        league_name="Test League",
        is_active=False,
        is_completed=True,
        current_week=15,
        regular_season_weeks=14,
        playoff_team_count=6,
    )
    db_session.add(season)
    m1 = Manager(espn_member_id="{M1}", display_name="Alpha")
    m2 = Manager(espn_member_id="{M2}", display_name="Bravo")
    m3 = Manager(espn_member_id="{M3}", display_name="Charlie")
    db_session.add_all([m1, m2, m3])
    db_session.flush()

    t1 = Team(season_year=2025, espn_team_id=1, team_name="Team 1", manager_id=m1.id)
    t2 = Team(season_year=2025, espn_team_id=2, team_name="Team 2", manager_id=m2.id)
    t3 = Team(season_year=2025, espn_team_id=3, team_name="Team 3 (Bye)", manager_id=m3.id)
    db_session.add_all([t1, t2, t3])
    db_session.flush()
    team_map = {1: t1, 2: t2, 3: t3}

    # 1. Pre-Week 1 (week=0) post-draft snapshot where playerPoolEntry has season totals
    sp0_payload = {
        "seasonId": 2025,
        "scoringPeriodId": 0,
        "teams": [
            {
                "id": 1,
                "roster": {
                    "entries": [
                        {
                            "playerId": 9001,
                            "lineupSlotId": 0,
                            "acquisitionType": "DRAFT",
                            "playerPoolEntry": {
                                "appliedStatTotal": 295.4,
                                "player": {
                                    "id": 9001,
                                    "fullName": "Josh Allen",
                                    "defaultPositionId": 1,
                                    "proTeamId": 2,
                                },
                            },
                        }
                    ]
                },
            }
        ],
    }
    lineups_w0 = upsert_weekly_lineups_from_payload(
        db_session, season, sp0_payload, team_map, weeks=[0]
    )
    assert len(lineups_w0) == 1
    assert lineups_w0[0].week == 0
    assert float(lineups_w0[0].actual_points) == 0.0
    assert lineups_w0[0].acquisition_type == "DRAFT"

    # 2. Week 15 Playoff week: Team 1 vs Team 2 in schedule; Team 3 has a BYE (only in teams[].roster)
    sp15_payload = {
        "seasonId": 2025,
        "scoringPeriodId": 15,
        "schedule": [
            {
                "id": 101,
                "matchupPeriodId": 15,
                "home": {
                    "teamId": 1,
                    "rosterForCurrentScoringPeriod": {
                        "entries": [
                            {
                                "playerId": 9001,
                                "lineupSlotId": 0,
                                "appliedStatTotal": 28.5,
                                "playerPoolEntry": {
                                    "player": {
                                        "id": 9001,
                                        "fullName": "Josh Allen",
                                        "defaultPositionId": 1,
                                        "proTeamId": 2,
                                    }
                                },
                            }
                        ]
                    },
                },
                "away": {
                    "teamId": 2,
                    "rosterForCurrentScoringPeriod": {
                        "entries": [
                            {
                                "playerId": 9002,
                                "lineupSlotId": 2,
                                "appliedStatTotal": 19.2,
                                "playerPoolEntry": {
                                    "player": {
                                        "id": 9002,
                                        "fullName": "Saquon Barkley",
                                        "defaultPositionId": 2,
                                        "proTeamId": 21,
                                    }
                                },
                            }
                        ]
                    },
                },
            }
        ],
        "teams": [
            {
                "id": 3,
                "roster": {
                    "entries": [
                        {
                            "playerId": 9003,
                            "lineupSlotId": 4,
                            "playerPoolEntry": {
                                "appliedStatTotal": 310.0,
                                "player": {
                                    "id": 9003,
                                    "fullName": "Ja'Marr Chase",
                                    "defaultPositionId": 3,
                                    "proTeamId": 4,
                                    "stats": [
                                        {
                                            "scoringPeriodId": 15,
                                            "statSourceId": 0,
                                            "appliedTotal": 24.6,
                                        }
                                    ],
                                },
                            },
                        }
                    ]
                },
            }
        ],
    }
    lineups_w15 = upsert_weekly_lineups_from_payload(
        db_session, season, sp15_payload, team_map, weeks=[15]
    )
    assert len(lineups_w15) == 3
    bye_lineup = next(wl for wl in lineups_w15 if wl.team_id == t3.id)
    assert bye_lineup.week == 15
    assert bye_lineup.player_id == 9003
    assert float(bye_lineup.actual_points) == 24.6

    # 3. Verify composite positional tier ranking:
    # A full-season WR1 with high projected points (~19.5) ranks #1 ahead of a
    # 2-week spike WR who put up 0.0 in his 3rd week with low projected points (~6.5).
    from backend.models.lineup import WeeklyLineup
    from backend.models.player import Player
    from backend.services.trades_service import compute_positional_ranks

    stud_wr = Player(espn_player_id=9101, full_name="Stud WR", default_position="WR", pro_team="CIN")
    spike_wr = Player(espn_player_id=9102, full_name="Spike WR", default_position="WR", pro_team="NYJ")
    p_map = {9101: stud_wr, 9102: spike_wr}
    p_lineups = {
        (2025, 9101): [
            WeeklyLineup(
                season_year=2025,
                week=w,
                team_id=t1.id,
                player_id=9101,
                slot_position="WR",
                is_starter=True,
                actual_points=Decimal("18.5"),
                projected_points=Decimal("19.5"),
                weekly_stats={},
            )
            for w in range(1, 7)
        ],
        (2025, 9102): [
            WeeklyLineup(
                season_year=2025,
                week=4,
                team_id=t2.id,
                player_id=9102,
                slot_position="BE",
                is_starter=False,
                actual_points=Decimal("22.0"),
                projected_points=Decimal("5.5"),
                weekly_stats={},
            ),
            WeeklyLineup(
                season_year=2025,
                week=5,
                team_id=t2.id,
                player_id=9102,
                slot_position="BE",
                is_starter=False,
                actual_points=Decimal("20.0"),
                projected_points=Decimal("6.5"),
                weekly_stats={},
            ),
            WeeklyLineup(
                season_year=2025,
                week=6,
                team_id=t2.id,
                player_id=9102,
                slot_position="WR",
                is_starter=True,
                actual_points=Decimal("0.0"),
                projected_points=Decimal("7.0"),
                weekly_stats={},
            ),
        ],
    }
    ranks = compute_positional_ranks(2025, 7, p_lineups, p_map)
    assert ranks[9101] == 1
    assert ranks[9102] == 2




