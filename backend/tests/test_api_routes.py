"""backend/tests/test_api_routes.py - REST API Route & Contract Test Suite.

Purpose:
    Verifies all 7 REST API endpoints, aliases, query parameters, error handlers,
    caching headers, CORS, and critical engineering guardrails against an in-memory
    SQLite database seeded with seed_dev.py.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from flask.testing import FlaskClient
from sqlalchemy.orm import sessionmaker

from backend.app import create_app
from backend.database import create_db_engine
from backend.models.lineup import WeeklyLineup
from backend.models.team import Team
from db.seed_dev import seed_database


@pytest.fixture(scope="module")
def client() -> FlaskClient:
    """Create an isolated in-memory test database and configured Flask test client."""
    engine = create_db_engine("sqlite:///:memory:")
    seed_database(engine)

    test_session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    app = create_app({"TESTING": True, "SESSION_FACTORY": test_session_factory})
    return app.test_client()


# ============================================================================
# 1. Health & Meta Endpoints
# ============================================================================


def test_health_check(client: FlaskClient) -> None:
    """Verifies GET /api/v1/health returns connected database status and 60s cache header."""
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.headers.get("Cache-Control") == "public, max-age=60"

    data = res.get_json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert "timestamp" in data


def test_league_meta(client: FlaskClient) -> None:
    """Verifies GET /api/v1/meta returns league name, seasons, managers, and sync audits."""
    res = client.get("/api/v1/meta")
    assert res.status_code == 200
    assert res.headers.get("Cache-Control") == "public, max-age=60"

    data = res.get_json()
    assert data["league_name"] == "The League of Extraordinary Gentlemen"
    assert data["current_season"] == 2024
    assert len(data["available_seasons"]) == 3

    # Seasons ordered descending
    years = [s["season_year"] for s in data["available_seasons"]]
    assert years == [2024, 2023, 2022]

    # Managers ordered by display name
    managers = data["managers"]
    assert len(managers) == 10
    display_names = [m["display_name"] for m in managers]
    assert display_names == sorted(display_names)

    # Ingestion audit status
    last_sync = data["last_sync"]
    assert last_sync["last_sync_status"] == "SUCCESS"
    assert last_sync["last_backfill_at"] is not None
    assert last_sync["last_weekly_sync_at"] is not None


# ============================================================================
# 2. Earnings Leaderboard Endpoints
# ============================================================================


def test_earnings_leaderboard_all_time(client: FlaskClient) -> None:
    """Verifies all-time earnings calculation and route aliases."""
    res = client.get("/api/v1/earnings/leaderboard")
    assert res.status_code == 200
    assert res.headers.get("Cache-Control") == "public, max-age=60"

    # Alias check
    alias_res = client.get("/api/v1/earnings")
    assert alias_res.status_code == 200
    assert res.get_json() == alias_res.get_json()

    data = res.get_json()
    assert data["season_filter"] is None
    assert data["weekly_win_value"] == 10.0

    leaderboard = data["leaderboard"]
    assert len(leaderboard) >= 8

    # Sorted by total earnings descending
    totals = [entry["total_earnings"] for entry in leaderboard]
    assert totals == sorted(totals, reverse=True)

    # Top manager should have multiple championships and podium payouts
    top = leaderboard[0]
    assert top["total_earnings"] > 0
    assert top["weekly_earnings"] > 0
    assert top["podium_earnings"] > 0
    assert top["weekly_wins_count"] > 0
    assert len(top["season_breakdown"]) >= 1


def test_earnings_leaderboard_season_filter(client: FlaskClient) -> None:
    """Verifies single-season earnings filter."""
    res = client.get("/api/v1/earnings/leaderboard?season=2023")
    assert res.status_code == 200
    data = res.get_json()
    assert data["season_filter"] == 2023

    for entry in data["leaderboard"]:
        for breakdown in entry["season_breakdown"]:
            assert breakdown["season_year"] == 2023


def test_earnings_bad_param(client: FlaskClient) -> None:
    """Verifies 400 bad request on invalid season query param."""
    res = client.get("/api/v1/earnings/leaderboard?season=invalid")
    assert res.status_code == 400
    data = res.get_json()
    assert data["error"] == "BAD_REQUEST"


# ============================================================================
# 3. Standings & Performance Endpoints
# ============================================================================


def test_standings_current_and_derived_metrics(client: FlaskClient) -> None:
    """Verifies active season standings, all-play, median records, and lineup efficiency."""
    res = client.get("/api/v1/standings/current")
    assert res.status_code == 200
    assert res.headers.get("Cache-Control") == "public, max-age=60"

    # Alias check
    alias_res = client.get("/api/v1/standings")
    assert alias_res.status_code == 200
    assert res.get_json() == alias_res.get_json()

    data = res.get_json()
    assert data["season_year"] == 2024
    assert data["is_active"] is True
    assert len(data["standings"]) == 8

    for entry in data["standings"]:
        assert entry["rank"] >= 1
        assert entry["team_name"]
        assert entry["manager_name"]
        assert entry["wins"] + entry["losses"] + entry["ties"] == 14

        # All-Play Record: In 8-team league with 7 games, total all-play games = 7 * 7 = 49
        ap_total = entry["all_play_wins"] + entry["all_play_losses"] + entry["all_play_ties"]
        assert ap_total == 49
        assert 0.0 <= entry["all_play_win_pct"] <= 1.0

        # Weekly Median Record: sum equals number of completed weeks = 7
        med_total = entry["median_wins"] + entry["median_losses"] + entry["median_ties"]
        assert med_total == 7

        # Luck index formula: actual_win_pct - all_play_win_pct
        assert -1.0 <= entry["luck_index"] <= 1.0

        # Lineup Efficiency: optimal_points_for > 0, bench_points >= 0
        assert entry["optimal_points_for"] > 0
        assert entry["bench_points"] >= 0
        assert entry["lineup_efficiency"] > 0


def test_standings_completed_season(client: FlaskClient) -> None:
    """Verifies standings for a completed season with final standings populated."""
    res = client.get("/api/v1/standings/current?season=2023")
    assert res.status_code == 200
    data = res.get_json()
    assert data["season_year"] == 2023
    assert data["is_completed"] is True
    assert len(data["standings"]) == 8

    final_standings = [s["final_standing"] for s in data["standings"]]
    assert final_standings == [1, 2, 3, 4, 5, 6, 7, 8]


def test_standings_not_found(client: FlaskClient) -> None:
    """Verifies 404 response when querying a non-existent season."""
    res = client.get("/api/v1/standings/current?season=1999")
    assert res.status_code == 404
    data = res.get_json()
    assert data["error"] == "NOT_FOUND"


# ============================================================================
# 4. Head-to-Head Rivalry Endpoints & Guardrail #4
# ============================================================================


def test_head_to_head_matrix_and_guardrail_4(client: FlaskClient) -> None:
    """Verifies rivalry matrix symmetry and exclusion of consolation games and byes."""
    res = client.get("/api/v1/history/head-to-head")
    assert res.status_code == 200
    assert res.headers.get("Cache-Control") == "public, max-age=60"

    # Alias check
    alias_res = client.get("/api/v1/head-to-head")
    assert alias_res.status_code == 200
    assert res.get_json() == alias_res.get_json()

    data = res.get_json()
    matrix = data["matrix"]
    assert len(matrix) > 0

    # Build map of (a, b) -> entry for symmetry checks
    entry_map: dict[tuple[int, int], dict[str, Any]] = {
        (e["manager_a_id"], e["manager_b_id"]): e for e in matrix
    }

    # Verify matrix symmetry: A wins == B losses, A PF == B PA
    for (a_id, b_id), a_entry in entry_map.items():
        if (b_id, a_id) in entry_map:
            b_entry = entry_map[(b_id, a_id)]
            assert a_entry["wins"] == b_entry["losses"]
            assert a_entry["losses"] == b_entry["wins"]
            assert a_entry["ties"] == b_entry["ties"]
            assert a_entry["points_for"] == b_entry["points_against"]
            assert a_entry["points_against"] == b_entry["points_for"]


def test_head_to_head_pairwise_deep_dive(client: FlaskClient) -> None:
    """Verifies pairwise deep dive, regular vs playoff splits, and streaks."""
    res = client.get("/api/v1/history/head-to-head?managerA=1&managerB=2")
    assert res.status_code == 200
    data = res.get_json()

    pair = data["pair_detail"]
    assert pair is not None
    assert pair["manager_a"]["manager_id"] == 1
    assert pair["manager_b"]["manager_id"] == 2

    # Combined split matches sum of regular + playoffs
    reg = pair["regular_season"]
    play = pair["playoffs"]
    comb = pair["combined"]
    assert comb["a_wins"] == reg["a_wins"] + play["a_wins"]
    assert comb["b_wins"] == reg["b_wins"] + play["b_wins"]
    assert comb["ties"] == reg["ties"] + play["ties"]
    assert round(comb["a_points"] - comb["b_points"], 2) == comb["point_differential"]

    # Current streak verified
    streak = pair["current_streak"]
    assert streak["length"] >= 1
    assert streak["type"] in ("WIN", "TIE")

    # Matchups feed
    matchups = pair["matchups"]
    assert len(matchups) == comb["a_wins"] + comb["b_wins"] + comb["ties"]
    for m in matchups:
        assert m["matchup_type"] in ("REGULAR", "WINNERS_BRACKET")

    # Also test snake_case query params
    snake_res = client.get("/api/v1/history/head-to-head?manager_a=1&manager_b=2")
    assert snake_res.status_code == 200
    assert snake_res.get_json() == data


def test_head_to_head_consolation_exclusion(client: FlaskClient) -> None:
    """Guardrail #4: Verifies LOSERS_CONSOLATION_LADDER games are excluded from H2H."""
    # Manager 7 and Manager 8 played in week 15 2022 & 2023 as LOSERS_CONSOLATION_LADDER
    res = client.get("/api/v1/history/head-to-head?managerA=7&managerB=8")
    assert res.status_code == 200
    pair = res.get_json()["pair_detail"]
    if pair:
        for m in pair["matchups"]:
            assert m["matchup_type"] != "LOSERS_CONSOLATION_LADDER"
            assert m["matchup_type"] != "WINNERS_CONSOLATION_LADDER"
            assert m["matchup_type"] != "BYE"


# ============================================================================
# 5. Trades & Realized ROI Endpoints
# ============================================================================


def test_trades_trends_and_roi(client: FlaskClient) -> None:
    """Verifies trades trends, partner alliances, and post-trade realized starter points."""
    res = client.get("/api/v1/trades/trends")
    assert res.status_code == 200
    assert res.headers.get("Cache-Control") == "public, max-age=60"

    # Alias check
    alias_res = client.get("/api/v1/trades")
    assert alias_res.status_code == 200
    assert res.get_json() == alias_res.get_json()

    data = res.get_json()
    assert data["has_transaction_data"] is True
    assert len(data["trades"]) >= 1

    # Check 2023 Week 6 trade between Team 1 and Team 2
    trade_2023 = next((t for t in data["trades"] if t["season_year"] == 2023 and t["week"] == 6), None)
    assert trade_2023 is not None
    assert len(trade_2023["sides"]) == 2

    # Verify non-zero post-trade starter points were calculated for acquired assets
    found_started_player = False
    for side in trade_2023["sides"]:
        for asset in side["assets_received"]:
            if asset["post_trade_starter_points"] > 0:
                found_started_player = True
                assert asset["post_trade_weeks_started"] > 0
    assert found_started_player is True

    # Active traders leaderboard
    traders = data["active_traders"]
    assert len(traders) >= 2
    for tr in traders:
        assert tr["total_trades"] >= 1
        assert tr["players_acquired"] >= 1


def test_trades_legacy_era_no_transactions(client: FlaskClient) -> None:
    """Verifies legacy era seasons flag has_transaction_data = False."""
    res = client.get("/api/v1/trades/trends?season=2022")
    assert res.status_code == 200
    data = res.get_json()
    assert data["has_transaction_data"] is False
    assert len(data["trades"]) == 0


# ============================================================================
# 6. Transactions & FAAB Bidding Wars Endpoints
# ============================================================================


def test_transactions_summary_and_bidding_wars(client: FlaskClient) -> None:
    """Verifies manager FAAB efficiency, failure reasons, and FAAB bidding wars receipts."""
    res = client.get("/api/v1/transactions/summary?season=2023")
    assert res.status_code == 200
    assert res.headers.get("Cache-Control") == "public, max-age=60"

    # Alias check
    alias_res = client.get("/api/v1/transactions?season=2023")
    assert alias_res.status_code == 200
    assert res.get_json() == alias_res.get_json()

    data = res.get_json()
    assert data["season_year"] == 2023
    assert data["has_transaction_data"] is True

    # Failure reasons breakdown includes OUTBID and INSUFFICIENT_FUNDS
    reasons = {r["reason"]: r["count"] for r in data["failure_reasons"]}
    assert "OUTBID" in reasons
    assert "INSUFFICIENT_FUNDS" in reasons

    # Bidding wars: Verify Puka Nacua claim has losing bids linked via related_espn_transaction_id
    assert len(data["bidding_wars"]) >= 1
    puka_war = data["bidding_wars"][0]
    assert puka_war["winner"]["bid_amount"] == 35
    assert len(puka_war["losing_bids"]) == 3

    # Verify losing bids order: highest bid first
    losing_bids = puka_war["losing_bids"]
    assert losing_bids[0]["bid_amount"] == 40  # INSUFFICIENT_FUNDS
    assert losing_bids[1]["bid_amount"] == 27  # OUTBID
    assert losing_bids[2]["bid_amount"] == 19  # OUTBID

    # Manager efficiency: Verify FAAB spent, success rate, and starter points from claims
    eff = data["manager_efficiency"]
    assert len(eff) == 8
    winner_mgr = next((m for m in eff if m["manager_id"] == 1), None)
    assert winner_mgr is not None
    assert winner_mgr["executed_waivers"] >= 1
    assert winner_mgr["total_starter_points_from_waivers"] >= 0
    assert winner_mgr["points_per_faab_dollar"] is not None or winner_mgr["faab_spent"] > 0

    # Transactions audit log
    txs = data["transactions"]
    assert len(txs) >= 4
    for tx in txs:
        assert tx["espn_transaction_id"]
        assert tx["status"] in ("EXECUTED", "FAILED", "CANCELED", "VETOED")


def test_transactions_with_starter_waiver_points() -> None:
    """Verifies that claimed waiver players who start accumulate realized waiver points."""
    engine = create_db_engine("sqlite:///:memory:")
    seed_database(engine)

    test_session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with test_session_factory() as session:
        t1 = session.query(Team).filter(Team.season_year == 2023, Team.espn_team_id == 1).first()
        assert t1 is not None

        # Add starter lineup for Puka Nacua (player 106) in week 3 for team 1
        lineup = WeeklyLineup(
            season_year=2023,
            week=3,
            team_id=t1.id,
            player_id=106,
            slot_position="WR",
            is_starter=True,
            actual_points=Decimal("24.50"),
            projected_points=Decimal("15.00"),
            acquisition_type="WAIVER",
        )
        session.add(lineup)
        session.commit()

    app = create_app({"TESTING": True, "SESSION_FACTORY": test_session_factory})
    with app.test_client() as client:
        res = client.get("/api/v1/transactions/summary?season=2023")
        assert res.status_code == 200
        data = res.get_json()

        # Check bidding war post claim starter points
        puka_war = data["bidding_wars"][0]
        assert puka_war["winner"]["post_claim_starter_points"] == 24.50

        # Check manager efficiency total starter points from waivers
        eff = data["manager_efficiency"]
        winner_mgr = next((m for m in eff if m["manager_id"] == 1), None)
        assert winner_mgr is not None
        assert winner_mgr["total_starter_points_from_waivers"] == 24.50
        assert winner_mgr["points_per_faab_dollar"] is not None
        assert winner_mgr["points_per_faab_dollar"] > 0


# ============================================================================
# 7. Global CORS and Error Handling
# ============================================================================


def test_cors_headers(client: FlaskClient) -> None:
    """Verifies CORS headers are set on API responses."""
    res = client.get("/api/v1/health")
    assert res.headers.get("Access-Control-Allow-Origin") == "*"


def test_404_not_found_handler(client: FlaskClient) -> None:
    """Verifies global 404 JSON response for nonexistent routes."""
    res = client.get("/api/v1/nonexistent-route")
    assert res.status_code == 404
    data = res.get_json()
    assert data["error"] == "NOT_FOUND"
