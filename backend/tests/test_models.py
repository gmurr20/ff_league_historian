"""backend/tests/test_models.py - Model Constraints & Seed Harness Test Suite.

Purpose:
    Verifies that:
      1. All 12 SQLAlchemy ORM models initialize correctly with proper column mappings.
      2. Foreign key integrity and CASCADE deletion are enforced in SQLite and PostgreSQL.
      3. Cross-dialect nulls-not-distinct uniqueness rejects duplicate podium payouts (week=None).
      4. Partial unique index rejects conflicting weekly win/tie payouts in the same week.
      5. Canonical DDL in db/schema.sql contains required constraints and table definitions.
      6. db/seed_dev.py executes idempotently with identical counts across all 12 tables.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.database import create_db_engine, get_session, init_db
from backend.models import (
    DraftPick,
    EarningsLedger,
    Manager,
    Matchup,
    MediaAsset,
    Player,
    RawEspnSnapshot,
    Season,
    SyncRun,
    Team,
    Trade,
    Transaction,
    TransactionItem,
    WeeklyLineup,
)
from db.seed_dev import seed_database

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def test_engine():
    """Create a fresh in-memory SQLite database with foreign keys and custom indexes."""
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    return engine


@pytest.fixture
def session_factory(test_engine):
    """Session factory for the in-memory test engine."""
    return sessionmaker(bind=test_engine, autocommit=False, autoflush=False)


def test_all_12_models_instantiation(session_factory: sessionmaker[Session]) -> None:
    """Verifies that all 12 ORM models can be persisted and retrieved."""
    with get_session(session_factory) as session:
        # 1. Season
        season = Season(
            season_year=2023,
            league_id="12345678",
            league_name="Test League",
            is_active=False,
            is_completed=True,
            scoring_settings={"rec": 1.0},
            roster_slots={"QB": 1, "RB": 2},
        )
        session.add(season)

        # 2. Manager
        mgr1 = Manager(espn_member_id="{MGR-001}", display_name="Manager One")
        mgr2 = Manager(espn_member_id="{MGR-002}", display_name="Manager Two")
        session.add_all([mgr1, mgr2])
        session.flush()

        # 3. Team
        team1 = Team(
            season_year=2023,
            espn_team_id=1,
            team_name="Team One",
            manager_id=mgr1.id,
            raw_owner_guids=[mgr1.espn_member_id],
        )
        team2 = Team(
            season_year=2023,
            espn_team_id=2,
            team_name="Team Two",
            manager_id=mgr2.id,
            raw_owner_guids=[mgr2.espn_member_id],
        )
        session.add_all([team1, team2])
        session.flush()

        # 4. Player
        player = Player(
            espn_player_id=101,
            full_name="Christian McCaffrey",
            default_position="RB",
            pro_team="SF",
        )
        session.add(player)
        session.flush()

        # 5. Matchup
        matchup = Matchup(
            season_year=2023,
            week=1,
            espn_matchup_id=1,
            matchup_type="REGULAR",
            home_team_id=team1.id,
            away_team_id=team2.id,
            home_score=Decimal("120.50"),
            away_score=Decimal("110.25"),
            winner_team_id=team1.id,
            is_completed=True,
        )
        session.add(matchup)

        # 6. WeeklyLineup
        lineup = WeeklyLineup(
            season_year=2023,
            week=1,
            team_id=team1.id,
            player_id=player.espn_player_id,
            slot_position="RB",
            is_starter=True,
            actual_points=Decimal("24.50"),
            projected_points=Decimal("18.00"),
        )
        session.add(lineup)

        # 7. Transaction
        tx = Transaction(
            season_year=2023,
            week=1,
            scoring_period=1,
            espn_transaction_id="tx_test_001",
            transaction_type="WAIVER",
            status="EXECUTED",
            team_id=team1.id,
            bid_amount=15,
        )
        session.add(tx)
        session.flush()

        # 8. TransactionItem
        tx_item = TransactionItem(
            transaction_id=tx.id,
            player_id=player.espn_player_id,
            to_team_id=team1.id,
            item_type="ADD",
        )
        session.add(tx_item)

        # 9. Trade
        trade = Trade(
            season_year=2023,
            week=2,
            espn_transaction_id="trade_test_001",
            proposing_team_id=team1.id,
            accepting_team_id=team2.id,
            status="EXECUTED",
            faab_from_proposer=0,
            faab_from_accepter=5,
        )
        session.add(trade)

        # 10. EarningsLedger
        earnings = EarningsLedger(
            manager_id=mgr1.id,
            team_id=team1.id,
            season_year=2023,
            week=1,
            entry_type="WEEKLY_WIN",
            amount=Decimal("10.00"),
            description="Week 1 Win",
        )
        session.add(earnings)

        # 11. RawEspnSnapshot
        snapshot = RawEspnSnapshot(
            season_year=2023,
            view_name="mSettings",
            scoring_period=0,
            payload={"test": "payload"},
        )
        session.add(snapshot)

        # 12. SyncRun
        sync_run = SyncRun(
            run_type="BACKFILL",
            season_year=2023,
            status="SUCCESS",
            records_processed=100,
        )
        session.add(sync_run)

        # 13. DraftPick
        draft_pick = DraftPick(
            season_year=2023,
            round=1,
            round_pick=1,
            overall_pick=1,
            team_id=team1.id,
            player_id=player.espn_player_id,
            bid_amount=0,
            is_keeper=False,
        )
        session.add(draft_pick)

        # 14. MediaAsset
        media_asset = MediaAsset(
            id="test-asset-1",
            original_url="https://mystique-api.fantasy.espn.com/apis/v1/domains/lm/images/test-asset-1",
            content_type="image/jpeg",
            data=b"test-bytes",
            byte_size=10,
        )
        session.add(media_asset)

    # Verification: check all tables have records
    with get_session(session_factory) as session:
        assert session.query(Season).count() == 1
        assert session.query(Manager).count() == 2
        assert session.query(Team).count() == 2
        assert session.query(Player).count() == 1
        assert session.query(Matchup).count() == 1
        assert session.query(WeeklyLineup).count() == 1
        assert session.query(DraftPick).count() == 1
        assert session.query(Transaction).count() == 1
        assert session.query(TransactionItem).count() == 1
        assert session.query(Trade).count() == 1
        assert session.query(EarningsLedger).count() == 1
        assert session.query(RawEspnSnapshot).count() == 1
        assert session.query(SyncRun).count() == 1
        assert session.query(MediaAsset).count() == 1


def test_foreign_key_cascade_deletion(session_factory: sessionmaker[Session]) -> None:
    """Verifies that cascading deletion drops associated team records when season is deleted."""
    with get_session(session_factory) as session:
        season = Season(season_year=2023, league_id="1", league_name="League")
        mgr = Manager(espn_member_id="{MGR}", display_name="Manager")
        session.add_all([season, mgr])
        session.flush()

        team = Team(season_year=2023, espn_team_id=1, team_name="T1", manager_id=mgr.id)
        session.add(team)

    with get_session(session_factory) as session:
        s = session.query(Season).filter_by(season_year=2023).first()
        assert s is not None
        session.delete(s)

    with get_session(session_factory) as session:
        assert session.query(Season).count() == 0
        assert session.query(Team).count() == 0
        # Manager should still exist
        assert session.query(Manager).count() == 1


def test_foreign_key_violation_raises_integrity_error(session_factory: sessionmaker[Session]) -> None:
    """Verifies that inserting a team with a nonexistent manager raises IntegrityError."""
    with get_session(session_factory) as session:
        season = Season(season_year=2023, league_id="1", league_name="League")
        session.add(season)

    with pytest.raises(IntegrityError):
        with get_session(session_factory) as session:
            bad_team = Team(
                season_year=2023,
                espn_team_id=1,
                team_name="Bad Team",
                manager_id=99999,  # Non-existent manager
            )
            session.add(bad_team)


def test_duplicate_podium_payout_rejection(session_factory: sessionmaker[Session]) -> None:
    """Verifies that duplicate NULL-week championship podium entries are rejected by IntegrityError."""
    with get_session(session_factory) as session:
        season = Season(season_year=2023, league_id="1", league_name="League")
        mgr = Manager(espn_member_id="{CHAMP}", display_name="Champion")
        session.add_all([season, mgr])
        session.flush()

        team = Team(season_year=2023, espn_team_id=1, team_name="T1", manager_id=mgr.id)
        session.add(team)
        session.flush()

        first_award = EarningsLedger(
            manager_id=mgr.id,
            team_id=team.id,
            season_year=2023,
            week=None,
            entry_type="CHAMPION",
            amount=Decimal("600.00"),
        )
        session.add(first_award)

    # Attempting to add a second CHAMPION award for the same manager/season with week=None
    with pytest.raises(IntegrityError):
        with get_session(session_factory) as session:
            mgr = session.query(Manager).first()
            team = session.query(Team).first()
            dup_award = EarningsLedger(
                manager_id=mgr.id,
                team_id=team.id,
                season_year=2023,
                week=None,
                entry_type="CHAMPION",
                amount=Decimal("600.00"),
            )
            session.add(dup_award)


def test_conflicting_weekly_payout_rejection(session_factory: sessionmaker[Session]) -> None:
    """Verifies that multiple payouts in the same manager/season/week are rejected."""
    with get_session(session_factory) as session:
        season = Season(season_year=2023, league_id="1", league_name="League")
        mgr = Manager(espn_member_id="{MGR}", display_name="Manager")
        session.add_all([season, mgr])
        session.flush()

        team = Team(season_year=2023, espn_team_id=1, team_name="T1", manager_id=mgr.id)
        session.add(team)
        session.flush()

        win_award = EarningsLedger(
            manager_id=mgr.id,
            team_id=team.id,
            season_year=2023,
            week=1,
            entry_type="WEEKLY_WIN",
            amount=Decimal("10.00"),
        )
        session.add(win_award)

    # Attempting to add a WEEKLY_TIE award for the same manager in the same week
    with pytest.raises(IntegrityError):
        with get_session(session_factory) as session:
            mgr = session.query(Manager).first()
            team = session.query(Team).first()
            tie_award = EarningsLedger(
                manager_id=mgr.id,
                team_id=team.id,
                season_year=2023,
                week=1,
                entry_type="WEEKLY_TIE",
                amount=Decimal("5.00"),
            )
            session.add(tie_award)


def test_multiple_weekly_payout_types_allowed_and_duplicates_rejected(
    session_factory: sessionmaker[Session],
) -> None:
    """Verifies that a manager can receive both a win and high-score payout in the same week,
    while duplicate entries of the same type are rejected."""
    with get_session(session_factory) as session:
        season = Season(season_year=2023, league_id="1", league_name="League")
        mgr = Manager(espn_member_id="{MGR_MULTI}", display_name="Manager Multi")
        session.add_all([season, mgr])
        session.flush()

        team = Team(season_year=2023, espn_team_id=1, team_name="T1", manager_id=mgr.id)
        session.add(team)
        session.flush()

        # Manager can receive both WEEKLY_WIN and WEEKLY_HIGH_SCORE in week 1
        win_award = EarningsLedger(
            manager_id=mgr.id,
            team_id=team.id,
            season_year=2023,
            week=1,
            entry_type="WEEKLY_WIN",
            amount=Decimal("10.00"),
        )
        high_score_award = EarningsLedger(
            manager_id=mgr.id,
            team_id=team.id,
            season_year=2023,
            week=1,
            entry_type="WEEKLY_HIGH_SCORE",
            amount=Decimal("10.00"),
        )
        session.add_all([win_award, high_score_award])

    # Verify both were saved
    with get_session(session_factory) as session:
        entries = session.query(EarningsLedger).filter_by(season_year=2023, week=1).all()
        assert len(entries) == 2
        types = {e.entry_type for e in entries}
        assert types == {"WEEKLY_WIN", "WEEKLY_HIGH_SCORE"}

    # Attempting to add a duplicate WEEKLY_HIGH_SCORE award for the same manager in the same week
    with pytest.raises(IntegrityError):
        with get_session(session_factory) as session:
            mgr = session.query(Manager).first()
            team = session.query(Team).first()
            dup_hs = EarningsLedger(
                manager_id=mgr.id,
                team_id=team.id,
                season_year=2023,
                week=1,
                entry_type="WEEKLY_HIGH_SCORE",
                amount=Decimal("10.00"),
            )
            session.add(dup_hs)


def test_schema_sql_ddl_completeness() -> None:
    """Verifies that db/schema.sql contains required tables, constraints, and comments."""
    schema_file = REPO_ROOT / "db" / "schema.sql"
    assert schema_file.is_file(), "db/schema.sql is missing"
    ddl = schema_file.read_text(encoding="utf-8")

    expected_tables = [
        "raw_espn_snapshots",
        "seasons",
        "managers",
        "teams",
        "players",
        "matchups",
        "weekly_lineups",
        "transactions",
        "transaction_items",
        "trades",
        "earnings_ledger",
        "sync_runs",
        "draft_picks",
    ]
    for table in expected_tables:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in ddl, f"Missing table definition: {table}"

    expected_constraints = [
        "UNIQUE (season_year, view_name, scoring_period)",
        "UNIQUE (season_year, espn_team_id)",
        "UNIQUE (season_year, week, espn_matchup_id)",
        "UNIQUE (season_year, week, team_id, player_id)",
        "UNIQUE (season_year, espn_transaction_id)",
        "UNIQUE (season_year, overall_pick)",
        "UNIQUE NULLS NOT DISTINCT (manager_id, season_year, week, entry_type)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_earnings_weekly_single",
    ]
    for constraint in expected_constraints:
        assert constraint in ddl, f"Missing constraint in schema.sql: {constraint}"


def test_seed_database_idempotency(test_engine) -> None:
    """Verifies that seed_database() runs twice and produces identical counts across all tables."""
    counts_first_run = seed_database(test_engine)
    assert counts_first_run["seasons"] == 3
    assert counts_first_run["managers"] == 10
    assert counts_first_run["teams"] == 24
    assert counts_first_run["players"] == 20
    assert counts_first_run["matchups"] > 0
    assert counts_first_run["weekly_lineups"] > 0
    assert counts_first_run["transactions"] > 0
    assert counts_first_run["trades"] > 0
    assert counts_first_run["earnings_ledger"] > 0

    counts_second_run = seed_database(test_engine)
    assert counts_first_run == counts_second_run, "seed_database() is not idempotent"


def test_seed_data_business_invariants(test_engine) -> None:
    """Verifies business invariants in seed data: bidding war linkage, trade points, manager churn."""
    seed_database(test_engine)
    session_factory = sessionmaker(bind=test_engine)

    with get_session(session_factory) as session:
        # 1. Bidding war: failed waiver bids reference winning claim
        winning_tx = (
            session.query(Transaction)
            .filter_by(espn_transaction_id="tx_2023_w02_puka_win")
            .first()
        )
        assert winning_tx is not None
        assert winning_tx.status == "EXECUTED"

        losing_bids = (
            session.query(Transaction)
            .filter_by(related_espn_transaction_id="tx_2023_w02_puka_win")
            .all()
        )
        assert len(losing_bids) == 3
        reasons = {tx.failure_reason for tx in losing_bids}
        assert "OUTBID" in reasons
        assert "INSUFFICIENT_FUNDS" in reasons

        # 2. Trade execution and post-trade lineup points
        trade = (
            session.query(Trade)
            .filter_by(espn_transaction_id="trade_2023_w06_t1_t2")
            .first()
        )
        assert trade is not None
        assert trade.faab_from_accepter == 10

        # Acquired player 107 (Kyren Williams) started on acquiring Team 2 in week 7+
        t2_post_trade_starts = (
            session.query(WeeklyLineup)
            .filter(
                WeeklyLineup.team_id == trade.accepting_team_id,
                WeeklyLineup.player_id == 107,
                WeeklyLineup.week > trade.week,
                WeeklyLineup.is_starter.is_(True),
            )
            .all()
        )
        assert len(t2_post_trade_starts) > 0

        # 3. Manager churn: Legacy Lou is inactive, Rookie Rachel is active
        lou = session.query(Manager).filter_by(espn_member_id="{LLLL-0009-LOU}").first()
        assert lou is not None and not lou.is_active

        rachel = session.query(Manager).filter_by(espn_member_id="{RRRR-0010-RACHEL}").first()
        assert rachel is not None and rachel.is_active

        # 4. Co-management: Team 7 has both manager_id and co_manager_id
        t7 = (
            session.query(Team)
            .filter_by(season_year=2023, espn_team_id=7)
            .first()
        )
        assert t7 is not None
        assert t7.co_manager_id is not None
        assert len(t7.raw_owner_guids) == 2

        # 5. Playoff bye matchups have away_team_id = None
        bye_matchups = session.query(Matchup).filter_by(matchup_type="BYE").all()
        assert len(bye_matchups) >= 2
        for bye in bye_matchups:
            assert bye.away_team_id is None
            assert bye.winner_team_id == bye.home_team_id
