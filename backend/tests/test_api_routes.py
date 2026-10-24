"""backend/tests/test_api_routes.py - REST API Route & Contract Test Suite.

Purpose:
    Verifies all 7 REST API endpoints, aliases, query parameters, error handlers,
    caching headers, CORS, and critical engineering guardrails against an in-memory
    SQLite database seeded with seed_dev.py.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from flask.testing import FlaskClient
from sqlalchemy.orm import sessionmaker

from backend.app import create_app
from backend.database import create_db_engine
from backend.models.lineup import WeeklyLineup
from backend.models.player import Player
from backend.models.season import Season
from backend.models.team import Team
from backend.models.trade import Trade
from backend.models.transaction import TransactionItem
from backend.services.trades_service import _evaluate_trade
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
    assert top["points_title_cash"] >= 0
    assert top["weekly_wins_count"] > 0
    assert len(top["season_breakdown"]) >= 1
    assert "regular_season_points_winner" in data


def test_earnings_leaderboard_season_filter(client: FlaskClient) -> None:
    """Verifies single-season earnings filter."""
    res = client.get("/api/v1/earnings/leaderboard?season=2023")
    assert res.status_code == 200
    data = res.get_json()
    assert data["season_filter"] == 2023
    assert "regular_season_points_winner" in data

    for entry in data["leaderboard"]:
        assert "points_title_cash" in entry
        for breakdown in entry["season_breakdown"]:
            assert breakdown["season_year"] == 2023
            assert "points_title_cash" in breakdown


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
        assert isinstance(entry["championships"], int)
        assert isinstance(entry["championship_years"], list)
        assert isinstance(entry["is_defending_champion"], bool)

        # Weekly history matchups validation
        assert len(entry["weekly_history"]) > 0
        first_week = entry["weekly_history"][0]
        assert "opponent_team_name" in first_week
        assert "opponent_score" in first_week
        assert "result" in first_week
        assert first_week["result"] in ("WIN", "LOSS", "TIE", "BYE")
        assert "is_home" in first_week
        if first_week["result"] != "BYE":
            assert first_week["opponent_team_id"] is not None
            assert first_week["opponent_score"] is not None

    # Defending champion validation
    assert data["defending_champion_manager_id"] is not None
    assert data["defending_champion_team_id"] is not None
    assert data["playoff_bracket"] is None  # Active season week 8 has not concluded regular season
    defending_teams = [s for s in data["standings"] if s["is_defending_champion"]]
    assert len(defending_teams) == 1
    assert defending_teams[0]["manager_id"] == data["defending_champion_manager_id"]
    assert defending_teams[0]["championships"] >= 1
    assert len(defending_teams[0]["championship_years"]) == defending_teams[0]["championships"]


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

    # Playoff bracket is populated for completed season
    bracket = data["playoff_bracket"]
    assert bracket is not None
    assert bracket["is_available"] is True
    assert len(bracket["rounds"]) >= 1
    assert bracket["champion"] is not None
    assert bracket["champion"]["final_standing"] == 1

    # Accolades (runner-ups, third-places, scoring champions) are present on each entry
    for s in data["standings"]:
        assert isinstance(s["championships"], int)
        assert isinstance(s["championship_years"], list)
        assert isinstance(s["runner_ups"], int)
        assert isinstance(s["runner_up_years"], list)
        assert isinstance(s["third_places"], int)
        assert isinstance(s["third_place_years"], list)
        assert isinstance(s["scoring_champs"], int)
        assert isinstance(s["scoring_champ_years"], list)

    runner_up_entry = next((s for s in data["standings"] if s["final_standing"] == 2), None)
    assert runner_up_entry is not None
    assert runner_up_entry["runner_ups"] >= 1
    assert 2023 in runner_up_entry["runner_up_years"]


def test_standings_all_time_career(client: FlaskClient) -> None:
    """Verifies all-time career standings aggregating all seasons and identifying inactive managers."""
    res = client.get("/api/v1/standings/current?season=all")
    assert res.status_code == 200
    data = res.get_json()
    assert data["season_year"] is None
    assert data["is_active"] is False
    assert data["is_completed"] is True
    assert len(data["standings"]) == 9  # 9 primary franchise managers in seed_dev

    # In seed_dev, Legacy Lou (mgr_09) churned out after 2022
    legacy_lou = next((e for e in data["standings"] if "Legacy Lou" in e["manager_name"]), None)
    assert legacy_lou is not None
    assert legacy_lou["is_active"] is False  # Inactive manager

    # Alice Archer (mgr_01) is active
    alice = next((e for e in data["standings"] if "Alice Archer" in e["manager_name"]), None)
    assert alice is not None
    assert alice["is_active"] is True

    # Ranks are assigned 1..N
    ranks = [e["rank"] for e in data["standings"]]
    assert ranks == list(range(1, len(data["standings"]) + 1))

    # All-time entries expose podium finishes (1st, 2nd, 3rd) and scoring champ counts
    for e in data["standings"]:
        assert "championships" in e and isinstance(e["championships"], int)
        assert "runner_ups" in e and isinstance(e["runner_ups"], int)
        assert "third_places" in e and isinstance(e["third_places"], int)
        assert "scoring_champs" in e and isinstance(e["scoring_champs"], int)
        assert "championship_years" in e and isinstance(e["championship_years"], list)
        assert "runner_up_years" in e and isinstance(e["runner_up_years"], list)
        assert "third_place_years" in e and isinstance(e["third_place_years"], list)
        assert "scoring_champ_years" in e and isinstance(e["scoring_champ_years"], list)


def test_standings_not_found(client: FlaskClient) -> None:
    """Verifies 404 response when querying a non-existent season."""
    res = client.get("/api/v1/standings/current?season=1999")
    assert res.status_code == 404
    data = res.get_json()
    assert data["error"] == "NOT_FOUND"


# ============================================================================
# 4. Hall of Fame & Legends Spotlight Endpoints
# ============================================================================


def test_hall_of_fame_banners_and_championship_spotlight(client: FlaskClient) -> None:
    """Verifies championship banners, reigning champion spotlight, and top 4 championship heroes."""
    res = client.get("/api/v1/hall-of-fame")
    assert res.status_code == 200
    assert res.headers.get("Cache-Control") == "public, max-age=60"

    # Alias check
    alias_res = client.get("/api/v1/history/hall-of-fame")
    assert alias_res.status_code == 200
    assert res.get_json() == alias_res.get_json()

    data = res.get_json()
    assert "banners" in data
    assert "featured_champion" in data
    assert len(data["banners"]) >= 2  # 2023 and 2022 champions

    # Verify championship banners
    b2023 = next((b for b in data["banners"] if b["season_year"] == 2023), None)
    assert b2023 is not None
    assert b2023["team_name"] == "Archer Assassins"
    assert b2023["manager_name"] == "Alice Archer"
    assert b2023["championship_score"] > 0
    assert b2023["runner_up_team_name"] == "Baker's Dozen"
    assert b2023["payout_amount"] == 600.0

    # Verify featured champion
    champ = data["featured_champion"]
    assert champ is not None
    assert champ["season_year"] == 2023
    assert champ["team_name"] == "Archer Assassins"
    assert champ["regular_season_finish"] != ""
    assert champ["hall_of_fame_number"] == 2
    assert "championship_matchup" in champ
    matchup = champ["championship_matchup"]
    assert matchup["winning_score"] == 145.50
    assert matchup["runner_up_score"] == 138.20
    assert matchup["runner_up_team_name"] == "Baker's Dozen"

    # Top 4 players that won them the championship game
    top_players = champ["top_players"]
    assert len(top_players) == 4
    for idx, player in enumerate(top_players):
        assert player["rank"] == idx + 1
        assert player["full_name"] != ""
        assert player["default_position"] in ("QB", "RB", "WR", "TE", "K", "D/ST")
        assert player["fantasy_points"] > 0
        assert "headshot_url" in player
        assert player["role_title"] != ""


def test_hall_of_fame_season_filter(client: FlaskClient) -> None:
    """Verifies querying a historical champion year in Hall of Fame."""
    res = client.get("/api/v1/hall-of-fame?season=2022")
    assert res.status_code == 200
    data = res.get_json()
    assert data["selected_season"] == 2022
    champ = data["featured_champion"]
    assert champ is not None
    assert champ["season_year"] == 2022
    assert champ["hall_of_fame_number"] == 1
    assert len(champ["top_players"]) == 4


def test_hall_of_fame_invalid_season(client: FlaskClient) -> None:
    """Verifies 400 Bad Request on invalid season parameter."""
    res = client.get("/api/v1/hall-of-fame?season=invalid")
    assert res.status_code == 400
    data = res.get_json()
    assert data["error"] == "BAD_REQUEST"


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

    # Verify non-zero post-trade starter points and roster depth were calculated for acquired assets
    found_started_player = False
    for side in trade_2023["sides"]:
        assert side["total_roster_depth_points_gained"] >= 0.0
        for asset in side["assets_received"]:
            if asset["post_trade_starter_points"] > 0:
                found_started_player = True
                assert asset["post_trade_weeks_started"] > 0
            assert "roster_depth_points" in asset
            assert len(asset["weekly_breakdown"]) > 0
            wb = asset["weekly_breakdown"][0]
            assert "injury_status" in wb
            assert "is_injured" in wb
    assert found_started_player is True

    # Verify weekly trajectory and timeline events
    assert len(trade_2023["weekly_trajectory"]) > 0
    traj_pt = trade_2023["weekly_trajectory"][0]
    assert "side_a_cumulative_score" in traj_pt
    assert "side_b_cumulative_score" in traj_pt
    assert "cumulative_score_differential" in traj_pt
    assert "events" in traj_pt

    assert len(trade_2023["timeline_events"]) > 0
    trade_exec_event = next(
        (e for e in trade_2023["timeline_events"] if e["event_type"] == "TRADE_EXECUTED"), None
    )
    assert trade_exec_event is not None
    assert trade_exec_event["severity"] == "info"

    # Active traders leaderboard
    traders = data["active_traders"]
    assert len(traders) >= 2
    for tr in traders:
        assert tr["total_trades"] >= 1
        assert tr["players_acquired"] >= 1
        assert "net_roster_depth_points_gained" in tr


def test_trade_ir_penalty_and_trajectory_proration() -> None:
    """Verifies IR designation triggers -20.0 penalty, downgrades grade, and drops weekly trajectory."""
    season_2026 = Season(
        season_year=2026,
        league_id="test_league",
        league_name="Test League",
        is_active=True,
        is_completed=False,
        regular_season_weeks=14,
        current_week=7,
    )
    team_a = Team(id=1, season_year=2026, manager_id=1, team_name="Team Alpha", wins=5, losses=2)
    team_b = Team(id=2, season_year=2026, manager_id=2, team_name="Team Beta", wins=3, losses=4)
    team_map = {1: team_a, 2: team_b}
    mgr_map = {1: "Alpha Mgr", 2: "Beta Mgr"}
    mgr_avatar_map = {1: None, 2: None}

    bijan = Player(espn_player_id=101, full_name="Bijan Robinson", default_position="RB")
    adams = Player(espn_player_id=102, full_name="Davante Adams", default_position="WR")
    pick16 = Player(espn_player_id=-16, full_name="2027 Round 16 Pick", default_position="PICK")
    pick4 = Player(espn_player_id=-4, full_name="2027 Round 4 Pick", default_position="PICK")
    player_map = {101: bijan, 102: adams, -16: pick16, -4: pick4}

    # Trade in Week 6: Team A gets Bijan + 2027 R16 Pick; Team B gets Adams + 2027 R4 Pick
    trade = Trade(
        id=99,
        season_year=2026,
        week=6,
        espn_transaction_id="trade_2026_w06_bijan_adams",
        proposing_team_id=1,
        accepting_team_id=2,
        status="EXECUTED",
    )
    item_bijan = TransactionItem(id=1, transaction_id=1, player_id=101, from_team_id=2, to_team_id=1, item_type="TRADE")
    item_pick_a = TransactionItem(id=2, transaction_id=1, player_id=-16, from_team_id=2, to_team_id=1, item_type="TRADE")
    item_adams = TransactionItem(id=3, transaction_id=1, player_id=102, from_team_id=1, to_team_id=2, item_type="TRADE")
    item_pick_b = TransactionItem(id=4, transaction_id=1, player_id=-4, from_team_id=1, to_team_id=2, item_type="TRADE")
    items = [item_bijan, item_pick_a, item_adams, item_pick_b]

    # Lineups: Wk 6 both play; Wk 7 Adams is placed on IR (0 pts, IR status)
    wl_b6 = WeeklyLineup(id=1, season_year=2026, week=6, team_id=1, player_id=101, actual_points=Decimal("15.0"), is_starter=True, slot_position="RB")
    wl_b7 = WeeklyLineup(id=2, season_year=2026, week=7, team_id=1, player_id=101, actual_points=Decimal("12.0"), is_starter=True, slot_position="RB")

    wl_a6 = WeeklyLineup(id=3, season_year=2026, week=6, team_id=2, player_id=102, actual_points=Decimal("10.0"), is_starter=True, slot_position="WR")
    wl_a7 = WeeklyLineup(
        id=4, season_year=2026, week=7, team_id=2, player_id=102, actual_points=Decimal("0.0"),
        is_starter=False, slot_position="BE", weekly_stats={"injury_status": "INJURY_RESERVE", "injured": True}
    )

    scored_weeks = {(2026, 6), (2026, 7)}
    player_lineups = {
        (2026, 101): [wl_b6, wl_b7],
        (2026, 102): [wl_a6, wl_a7],
    }
    player_week_lineup = {
        (2026, 101, 6): wl_b6,
        (2026, 101, 7): wl_b7,
        (2026, 102, 6): wl_a6,
        (2026, 102, 7): wl_a7,
    }

    detail = _evaluate_trade(
        trade=trade,
        team_map=team_map,
        mgr_map=mgr_map,
        mgr_avatar_map=mgr_avatar_map,
        items=items,
        scored_weeks=scored_weeks,
        player_lineups=player_lineups,
        player_week_lineup=player_week_lineup,
        player_map=player_map,
        draft_pick_map={},
        league_size=12,
        season_info=season_2026,
    )
    assert detail is not None

    side_a = detail["sides"][0]
    side_b = detail["sides"][1]

    # Verify Adams has IR penalty of -20.0 in roster depth, and negative trade score
    adams_asset = next(a for a in side_b["assets_received"] if a["player_id"] == 102)
    assert adams_asset["roster_depth_points"] <= -18.0
    assert adams_asset["trade_score"] < 0.0

    # Verify future picks prorate along remaining season horizon (~2/9 = 22.2%)
    pick_b_asset = next(a for a in side_b["assets_received"] if a["asset_type"] == "PICK")
    assert pick_b_asset["trade_score"] < 15.0  # ~8.77, not 39.47

    # Side B receives grade D / C-, NOT B+
    assert side_b["grade"] in ("D", "D+", "C-")
    assert side_a["grade"] in ("A+", "A", "A-")

    # Verify weekly trajectory drops for Side B from Week 6 to Week 7 when Adams goes on IR
    traj = detail["weekly_trajectory"]
    assert len(traj) == 2
    wk6_pt = traj[0]
    wk7_pt = traj[1]
    assert wk7_pt["side_b_cumulative_score"] < wk6_pt["side_b_cumulative_score"]
    assert wk7_pt["leading_team_id"] == 1


def test_trades_legacy_era_no_transactions(client: FlaskClient) -> None:
    """Verifies legacy era seasons flag has_transaction_data = False."""
    res = client.get("/api/v1/trades/trends?season=2022")
    assert res.status_code == 200
    data = res.get_json()
    assert data["has_transaction_data"] is False
    assert len(data["trades"]) == 0


def test_trades_commissioner_admin_crud(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verifies commissioner trade admin auth, options, editing picks/FAAB, manual creation, soft-deletion, and restoration."""
    fake_overrides_path = tmp_path / "trade_overrides.json"
    fake_overrides_path.write_text('{"deleted_trades": [], "edited_trades": {}}', encoding="utf-8")

    monkeypatch.setattr(
        "backend.jobs.parsers.get_trade_overrides_path",
        lambda: fake_overrides_path,
    )
    monkeypatch.setattr(
        "backend.jobs.parsers.TRADE_OVERRIDES_PATH",
        fake_overrides_path,
        raising=False,
    )

    repo_overrides_path = Path("db/trade_overrides.json")
    repo_overrides_existed = repo_overrides_path.exists()
    repo_overrides_content = repo_overrides_path.read_text(encoding="utf-8") if repo_overrides_existed else None

    try:
        # 1. Verify admin password
        res_bad = client.post("/api/v1/trades/admin/verify", json={"password": "wrong"})
        assert res_bad.status_code == 401

        res_good = client.post("/api/v1/trades/admin/verify", json={"password": "commish"})
        assert res_good.status_code == 200
        assert res_good.get_json() == {"authenticated": True}

        # 2. Get admin options
        admin_headers = {"X-Admin-Password": "commish"}
        res_opts = client.get("/api/v1/trades/admin/options", headers=admin_headers)
        assert res_opts.status_code == 200
        opts = res_opts.get_json()
        assert len(opts["seasons"]) > 0
        assert len(opts["teams"]) > 0
        assert len(opts["players"]) > 0
        assert "deleted_trades" in opts

        # 3. Edit existing trade (2023 Week 6 trade)
        res_trends = client.get("/api/v1/trades/trends?season=2023")
        assert res_trends.status_code == 200
        trends_data = res_trends.get_json()
        trade_2023 = next(
            (t for t in trends_data["trades"] if t["season_year"] == 2023 and t["week"] == 6),
            None,
        )
        assert trade_2023 is not None
        trade_id = trade_2023["trade_id"]

        side_0 = trade_2023["sides"][0]
        side_1 = trade_2023["sides"][1]
        side_0_player_ids = [
            a["player_id"]
            for a in side_0["assets_received"]
            if a.get("asset_type") != "PICK"
        ]
        side_1_player_ids = [
            a["player_id"]
            for a in side_1["assets_received"]
            if a.get("asset_type") != "PICK"
        ]

        put_payload = {
            "week": trade_2023["week"],
            "sides": [
                {
                    "team_id": side_0["team_id"],
                    "player_ids": side_0_player_ids,
                    "draft_picks": [{"season_year": 2027, "round": 2, "pick_number": None}],
                    "faab_received": 10,
                },
                {
                    "team_id": side_1["team_id"],
                    "player_ids": side_1_player_ids,
                    "draft_picks": [],
                    "faab_received": 0,
                },
            ],
        }
        res_put = client.put(
            f"/api/v1/trades/{trade_id}",
            json=put_payload,
            headers=admin_headers,
        )
        assert res_put.status_code == 200

        res_trends_updated = client.get("/api/v1/trades/trends?season=2023")
        assert res_trends_updated.status_code == 200
        updated_trades = res_trends_updated.get_json()["trades"]
        updated_trade = next((t for t in updated_trades if t["trade_id"] == trade_id), None)
        assert updated_trade is not None

        updated_side_0 = updated_trade["sides"][0]
        assert updated_side_0["faab_received"] == 10
        assert updated_side_0["faab_value"] == 6.0

        pick_asset = next(
            (a for a in updated_side_0["assets_received"] if a.get("asset_type") == "PICK"),
            None,
        )
        assert pick_asset is not None
        assert pick_asset["full_name"] == "2027 Round 2 Pick"
        assert pick_asset["pick_round"] == 2
        assert pick_asset["pick_round_value"] > 0

        # 4. Manual trade creation, deletion, restoration, and re-deletion
        teams_2023 = [t for t in opts["teams"] if t["season_year"] == 2023]
        assert len(teams_2023) >= 2
        team_a_id = teams_2023[0]["team_id"]
        team_b_id = teams_2023[1]["team_id"]

        create_payload = {
            "season_year": 2023,
            "week": 7,
            "sides": [
                {
                    "team_id": team_a_id,
                    "player_ids": [],
                    "draft_picks": [{"season_year": 2025, "round": 1, "pick_number": None}],
                    "faab_received": 15,
                },
                {
                    "team_id": team_b_id,
                    "player_ids": [],
                    "draft_picks": [],
                    "faab_received": 0,
                },
            ],
        }
        res_create = client.post(
            "/api/v1/trades",
            json=create_payload,
            headers=admin_headers,
        )
        assert res_create.status_code == 201
        new_trade_id = res_create.get_json()["trade_id"]
        assert new_trade_id > 0

        # Delete manual trade
        res_del = client.delete(
            f"/api/v1/trades/{new_trade_id}",
            headers=admin_headers,
        )
        assert res_del.status_code == 200

        # Verify it appears in GET /api/v1/trades/admin/options deleted_trades
        res_opts_del = client.get("/api/v1/trades/admin/options", headers=admin_headers)
        assert res_opts_del.status_code == 200
        deleted_trades = res_opts_del.get_json()["deleted_trades"]
        assert any(dt["trade_id"] == new_trade_id for dt in deleted_trades)

        # Restore manual trade
        res_restore = client.post(
            f"/api/v1/trades/{new_trade_id}/restore",
            headers=admin_headers,
        )
        assert res_restore.status_code == 200

        # Verify it is restored (no longer in deleted_trades)
        res_opts_restored = client.get("/api/v1/trades/admin/options", headers=admin_headers)
        assert res_opts_restored.status_code == 200
        deleted_after_restore = res_opts_restored.get_json()["deleted_trades"]
        assert not any(dt["trade_id"] == new_trade_id for dt in deleted_after_restore)

        # Delete manual trade again
        res_del_again = client.delete(
            f"/api/v1/trades/{new_trade_id}",
            headers=admin_headers,
        )
        assert res_del_again.status_code == 200

    finally:
        if not repo_overrides_existed and repo_overrides_path.exists():
            repo_overrides_path.unlink()
        elif repo_overrides_existed and repo_overrides_content is not None:
            repo_overrides_path.write_text(repo_overrides_content, encoding="utf-8")


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


# ============================================================================
# 8. Media Asset Streaming
# ============================================================================


def test_media_asset_endpoint(client: FlaskClient) -> None:
    """Verifies GET /api/v1/media/<asset_id> streams binary data with immutable cache headers."""
    from backend.models.media import MediaAsset

    # Inject a media asset into the test database
    engine = client.application.config["SESSION_FACTORY"]
    with engine() as session:
        test_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01test_image_data"
        asset = MediaAsset(
            id="test-logo-uuid-1234",
            original_url="https://mystique-api.fantasy.espn.com/apis/v1/domains/lm/images/test-logo-uuid-1234",
            content_type="image/jpeg",
            data=test_bytes,
            byte_size=len(test_bytes),
        )
        session.merge(asset)
        session.commit()

    res = client.get("/api/v1/media/test-logo-uuid-1234")
    assert res.status_code == 200
    assert res.data == test_bytes
    assert res.content_type == "image/jpeg"
    assert "public" in res.headers.get("Cache-Control", "")
    assert "immutable" in res.headers.get("Cache-Control", "")
    assert res.headers.get("ETag") == '"test-logo-uuid-1234"'

    # Verify 404 for unknown media asset
    res_404 = client.get("/api/v1/media/nonexistent-uuid")
    assert res_404.status_code == 404
    data_404 = res_404.get_json()
    assert data_404["error"] == "NOT_FOUND"
