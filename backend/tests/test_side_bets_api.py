"""backend/tests/test_side_bets_api.py - Side Bets Service, CRUD Routes, Earnings Rollup & JSON Sync Tests."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from flask.testing import FlaskClient
from sqlalchemy.orm import sessionmaker

from backend.app import create_app
from backend.database import create_db_engine
from backend.models.lineup import WeeklyLineup
from backend.models.matchup import Matchup
from backend.models.player import Player
from backend.models.side_bet import SideBet
from backend.models.team import Team
from backend.routes.side_bets import side_bets_bp
from backend.services import side_bets_service
from db.seed_dev import seed_database


@pytest.fixture()
def isolated_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[FlaskClient, sessionmaker, Path]:
    """Create an isolated in-memory SQLite database, temporary side_bets.json, and Flask test client."""
    json_path = tmp_path / "side_bets.json"
    json_path.write_text('{"side_bets": []}\n', encoding="utf-8")
    monkeypatch.setattr(
        side_bets_service, "get_side_bets_json_path", lambda: json_path
    )

    engine = create_db_engine("sqlite:///:memory:")
    seed_database(engine)
    SideBet.__table__.create(bind=engine, checkfirst=True)

    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    app = create_app({"TESTING": True, "SESSION_FACTORY": session_factory})
    if "side_bets" not in app.blueprints:
        app.register_blueprint(side_bets_bp, url_prefix="/api/v1")

    return app.test_client(), session_factory, json_path


def test_side_bets_crud_and_auth(
    isolated_env: tuple[FlaskClient, sessionmaker, Path],
) -> None:
    """Verifies commissioner authentication on write endpoints and internal team_id normalization."""
    client, session_factory, _ = isolated_env

    with session_factory() as session:
        teams_2023 = (
            session.query(Team)
            .filter(Team.season_year == 2023)
            .order_by(Team.espn_team_id.asc())
            .all()
        )
        t1, t2 = teams_2023[0], teams_2023[1]

    payload = {
        "season_year": 2023,
        "week": 1,
        "title": "Opening Week Rivalry",
        "side_a_name": t1.team_name,
        "side_b_name": t2.team_name,
        "side_a_team_ids": [t1.id],  # Pass internal PK (differs from espn_team_id in 2023)
        "side_b_team_ids": [t2.id],
        "spread_side_a": -3.5,
        "stake_amount": 20.0,
        "stake_description": "$20 Venmo",
    }

    # Unauthenticated POST should fail with 401
    unauth_res = client.post("/api/v1/side-bets", json=payload)
    assert unauth_res.status_code == 401

    # Authenticated POST should succeed with 201
    headers = {"X-Admin-Password": "commish"}
    create_res = client.post("/api/v1/side-bets", json=payload, headers=headers)
    assert create_res.status_code == 201
    created = create_res.get_json()
    bet_id = created["bet_id"]
    assert created["bet_uuid"].startswith("bet-")

    # Verify normalized espn_team_ids via GET
    get_res = client.get("/api/v1/side-bets?season=2023&week=1")
    assert get_res.status_code == 200
    data = get_res.get_json()
    assert data["season_filter"] == 2023
    assert data["selected_week"] == 1
    assert len(data["bets"]) == 1

    bet_detail = data["bets"][0]
    assert bet_detail["bet_id"] == bet_id
    assert bet_detail["side_a"]["espn_team_ids"] == [t1.espn_team_id]
    assert bet_detail["side_b"]["espn_team_ids"] == [t2.espn_team_id]
    assert bet_detail["spread_side_a"] == -3.5
    assert bet_detail["stake_amount"] == 20.0

    # Unauthenticated PUT should fail with 401
    assert (
        client.put(f"/api/v1/side-bets/{bet_id}", json={"stake_amount": 50.0}).status_code
        == 401
    )

    # Authenticated PUT updates spread and stake
    put_res = client.put(
        f"/api/v1/side-bets/{bet_id}",
        json={"spread_side_a": 4.5, "stake_amount": 50.0, "title": "Updated Rivalry"},
        headers=headers,
    )
    assert put_res.status_code == 200

    get_updated = client.get("/api/v1/side-bets?season=2023&week=1").get_json()
    assert get_updated["bets"][0]["spread_side_a"] == 4.5
    assert get_updated["bets"][0]["stake_amount"] == 50.0
    assert get_updated["bets"][0]["title"] == "Updated Rivalry"

    # Unauthenticated DELETE should fail with 401
    assert client.delete(f"/api/v1/side-bets/{bet_id}").status_code == 401

    # Authenticated DELETE soft-deletes the bet
    del_res = client.delete(f"/api/v1/side-bets/{bet_id}", headers=headers)
    assert del_res.status_code == 200

    after_del = client.get("/api/v1/side-bets?season=2023&week=1").get_json()
    assert after_del["bets"] == []


def test_1v1_spreads_exact_push_and_group_matchups(
    isolated_env: tuple[FlaskClient, sessionmaker, Path],
) -> None:
    """Tests 1v1 spreads (positive & negative), exact 0.00 push, and 2v2/3v3 group bets."""
    client, session_factory, _ = isolated_env
    headers = {"X-Admin-Password": "commish"}

    # Inspect 2023 Week 1 team starter points so we can construct deterministic spreads
    res_init = client.post(
        "/api/v1/side-bets",
        json={
            "season_year": 2023,
            "week": 1,
            "side_a_team_ids": [1],
            "side_b_team_ids": [2],
            "spread_side_a": 0.0,
            "stake_amount": 25.0,
        },
        headers=headers,
    )
    probe_id = res_init.get_json()["bet_id"]
    probe_data = client.get("/api/v1/side-bets?season=2023&week=1").get_json()["bets"][0]
    pts_1 = probe_data["side_a"]["raw_points"]
    pts_2 = probe_data["side_b"]["raw_points"]
    diff_1_2 = round(pts_2 - pts_1, 2)

    # 1. Exact PUSH: set spread_side_a == (pts_2 - pts_1) so Side A adjusted == Side B raw
    client.put(
        f"/api/v1/side-bets/{probe_id}",
        json={"spread_side_a": diff_1_2, "title": "Exact Push Bet"},
        headers=headers,
    )
    push_bet = client.get("/api/v1/side-bets?season=2023&week=1").get_json()["bets"][0]
    assert push_bet["is_completed"] is True
    assert push_bet["margin_vs_spread"] == 0.0
    assert push_bet["currently_covering"] == "PUSH"
    assert push_bet["winning_side"] == "PUSH"

    # 2. Negative/Positive spread flipping winner:
    # Make Side A cover by +5.0 margin
    spread_a_wins = round(diff_1_2 + 5.0, 2)
    client.put(
        f"/api/v1/side-bets/{probe_id}",
        json={"spread_side_a": spread_a_wins},
        headers=headers,
    )
    a_win_bet = client.get("/api/v1/side-bets?season=2023&week=1").get_json()["bets"][0]
    assert a_win_bet["margin_vs_spread"] == 5.0
    assert a_win_bet["winning_side"] == "A"

    # Make Side B cover by -4.5 margin
    spread_b_wins = round(diff_1_2 - 4.5, 2)
    client.put(
        f"/api/v1/side-bets/{probe_id}",
        json={"spread_side_a": spread_b_wins},
        headers=headers,
    )
    b_win_bet = client.get("/api/v1/side-bets?season=2023&week=1").get_json()["bets"][0]
    assert b_win_bet["margin_vs_spread"] == -4.5
    assert b_win_bet["winning_side"] == "B"

    # 3. 3v3 Group Division War in 2023 Week 2
    group_res = client.post(
        "/api/v1/side-bets",
        json={
            "season_year": 2023,
            "week": 2,
            "title": "3v3 Division Showdown",
            "side_a_name": "Alpha Squad",
            "side_b_name": "Omega Squad",
            "side_a_team_ids": [1, 2, 3],
            "side_b_team_ids": [4, 5, 6],
            "spread_side_a": -6.5,
            "stake_amount": 30.0,
        },
        headers=headers,
    )
    assert group_res.status_code == 201
    w2_bets = client.get("/api/v1/side-bets?season=2023&week=2").get_json()["bets"]
    assert len(w2_bets) == 1
    g_bet = w2_bets[0]
    assert len(g_bet["side_a"]["teams"]) == 3
    assert len(g_bet["side_b"]["teams"]) == 3
    assert g_bet["side_a"]["raw_points"] == round(
        sum(t["starter_points"] for t in g_bet["side_a"]["teams"]), 2
    )
    assert g_bet["side_b"]["raw_points"] == round(
        sum(t["starter_points"] for t in g_bet["side_b"]["teams"]), 2
    )
    assert g_bet["side_a"]["adjusted_points"] == round(
        g_bet["side_a"]["raw_points"] - 6.5, 2
    )


def test_player_starter_and_bench_breakdown_and_live_status(
    isolated_env: tuple[FlaskClient, sessionmaker, Path],
) -> None:
    """Verifies canonical starter slot ordering, bench/IR separation, injury metadata, and live status."""
    client, session_factory, _ = isolated_env
    headers = {"X-Admin-Password": "commish"}

    with session_factory() as session:
        t1 = (
            session.query(Team)
            .filter_by(season_year=2024, espn_team_id=1)
            .first()
        )
        t2 = (
            session.query(Team)
            .filter_by(season_year=2024, espn_team_id=2)
            .first()
        )
        assert t1 is not None and t2 is not None

        # Mark 2024 Week 7 matchups as in-progress (is_completed = False)
        week_7_matchups = (
            session.query(Matchup)
            .filter_by(season_year=2024, week=7)
            .all()
        )
        for m in week_7_matchups:
            m.is_completed = False

        # Add an injured bench/IR player to t1 in 2024 Week 7 to verify injury flags & IR slot
        ir_player = Player(
            espn_player_id=999001,
            full_name="Injured Reserve Star",
            default_position="WR",
            pro_team="SF",
            headshot_url="https://a.espncdn.com/i/headshots/nfl/players/full/999001.png",
        )
        session.merge(ir_player)
        session.flush()

        ir_lineup = WeeklyLineup(
            season_year=2024,
            week=7,
            team_id=t1.id,
            player_id=999001,
            slot_position="IR",
            is_starter=False,
            actual_points=Decimal("0.00"),
            projected_points=Decimal("0.00"),
            weekly_stats={"injury_status": "INJURY_RESERVE", "injured": True},
        )
        session.add(ir_lineup)
        session.commit()

    client.post(
        "/api/v1/side-bets",
        json={
            "season_year": 2024,
            "week": 7,
            "title": "Live Week 7 Sweat",
            "side_a_team_ids": [1],
            "side_b_team_ids": [2],
            "spread_side_a": -2.5,
            "stake_amount": 15.0,
        },
        headers=headers,
    )

    resp = client.get("/api/v1/side-bets?season=2024&week=7").get_json()
    bet = resp["bets"][0]
    assert bet["is_completed"] is False
    assert bet["is_live"] is True
    assert bet["currently_covering"] in ("A", "B", "PUSH")
    assert bet["winning_side"] is None

    team_a_bd = bet["side_a"]["teams"][0]
    starters = team_a_bd["starters"]
    bench = team_a_bd["bench"]
    assert len(starters) > 0
    assert len(bench) > 0

    # Verify canonical starter slot ordering: QB -> RB -> WR -> TE -> FLEX -> D/ST -> K
    slot_order = {"QB": 0, "RB": 1, "WR": 2, "TE": 3, "FLEX": 4, "D/ST": 5, "K": 6}
    starter_ranks = [slot_order[p["slot_position"]] for p in starters if p["slot_position"] in slot_order]
    assert starter_ranks == sorted(starter_ranks)

    # Verify IR player appears in bench with injury metadata
    ir_entries = [p for p in bench if p["player_id"] == 999001]
    assert len(ir_entries) == 1
    assert ir_entries[0]["slot_position"] == "IR"
    assert ir_entries[0]["is_injured"] is True
    assert ir_entries[0]["injury_status"] == "INJURY_RESERVE"
    assert ir_entries[0]["pro_team"] == "SF"


def test_earnings_leaderboard_positive_and_negative_side_bets(
    isolated_env: tuple[FlaskClient, sessionmaker, Path],
) -> None:
    """Verifies winning side bets add to total_earnings and losing side bets subtract (allowing negative total_earnings)."""
    client, _, _ = isolated_env
    headers = {"X-Admin-Password": "commish"}

    # Baseline 2023 earnings before any side bets
    before_data = client.get("/api/v1/earnings/leaderboard?season=2023").get_json()
    before_by_mgr = {e["manager_id"]: e for e in before_data["leaderboard"]}

    # Create a high-stake completed side bet in 2023 Week 3 so the loser's total_earnings goes negative
    # Use a spread that guarantees Side A wins (+500.0 spread) and stake = $2000.00
    create_res = client.post(
        "/api/v1/side-bets",
        json={
            "season_year": 2023,
            "week": 3,
            "title": "Mega High Roller Bet",
            "side_a_team_ids": [1],
            "side_b_team_ids": [2],
            "spread_side_a": 500.0,
            "stake_amount": 2000.0,
        },
        headers=headers,
    )
    assert create_res.status_code == 201

    sb_data = client.get("/api/v1/side-bets?season=2023&week=3").get_json()
    bet = sb_data["bets"][0]
    assert bet["is_completed"] is True
    assert bet["winning_side"] == "A"
    winner_mgr_id = bet["side_a"]["teams"][0]["manager_id"]
    loser_mgr_id = bet["side_b"]["teams"][0]["manager_id"]

    after_data = client.get("/api/v1/earnings/leaderboard?season=2023").get_json()
    after_by_mgr = {e["manager_id"]: e for e in after_data["leaderboard"]}

    winner_after = after_by_mgr[winner_mgr_id]
    loser_after = after_by_mgr[loser_mgr_id]

    assert winner_after["side_bets_cash"] == 2000.0
    assert winner_after["side_bets_wins_count"] == 1
    assert winner_after["side_bets_losses_count"] == 0
    assert winner_after["total_earnings"] == round(
        before_by_mgr[winner_mgr_id]["total_earnings"] + 2000.0, 2
    )
    assert len(winner_after["side_bet_receipts"]) == 1
    assert winner_after["side_bet_receipts"][0]["result"] == "WIN"
    assert winner_after["side_bet_receipts"][0]["amount"] == 2000.0

    assert loser_after["side_bets_cash"] == -2000.0
    assert loser_after["side_bets_wins_count"] == 0
    assert loser_after["side_bets_losses_count"] == 1
    assert loser_after["total_earnings"] == round(
        before_by_mgr[loser_mgr_id]["total_earnings"] - 2000.0, 2
    )
    assert loser_after["total_earnings"] < 0
    assert len(loser_after["side_bet_receipts"]) == 1
    assert loser_after["side_bet_receipts"][0]["result"] == "LOSS"
    assert loser_after["side_bet_receipts"][0]["amount"] == -2000.0


def test_json_persistence_survives_database_rebuild(
    isolated_env: tuple[FlaskClient, sessionmaker, Path],
) -> None:
    """Verifies side bets saved in db/side_bets.json are restored on a fresh database rebuild."""
    client, _, json_path = isolated_env
    headers = {"X-Admin-Password": "commish"}

    res = client.post(
        "/api/v1/side-bets",
        json={
            "season_year": 2023,
            "week": 4,
            "title": "Indestructible Bet",
            "side_a_team_ids": [1, 3],
            "side_b_team_ids": [2, 4],
            "spread_side_a": -4.5,
            "stake_amount": 40.0,
        },
        headers=headers,
    )
    assert res.status_code == 201
    bet_uuid = res.get_json()["bet_uuid"]

    # Verify JSON file was written
    loaded_json = side_bets_service.load_side_bets_json(json_path)
    assert len(loaded_json["side_bets"]) == 1
    assert loaded_json["side_bets"][0]["bet_uuid"] == bet_uuid

    # Create a brand-new in-memory database (simulating full drop & rebuild)
    fresh_engine = create_db_engine("sqlite:///:memory:")
    seed_database(fresh_engine)
    fresh_session_factory = sessionmaker(
        bind=fresh_engine, autoflush=False, autocommit=False
    )
    fresh_app = create_app(
        {"TESTING": True, "SESSION_FACTORY": fresh_session_factory}
    )
    if "side_bets" not in fresh_app.blueprints:
        fresh_app.register_blueprint(side_bets_bp, url_prefix="/api/v1")
    fresh_client = fresh_app.test_client()

    # Query GET /api/v1/side-bets on the fresh DB; sync_side_bets_to_db should restore the bet
    restored = fresh_client.get("/api/v1/side-bets?season=2023&week=4").get_json()
    assert len(restored["bets"]) == 1
    assert restored["bets"][0]["bet_uuid"] == bet_uuid
    assert restored["bets"][0]["title"] == "Indestructible Bet"
    assert restored["bets"][0]["side_a"]["espn_team_ids"] == [1, 3]
    assert restored["bets"][0]["side_b"]["espn_team_ids"] == [2, 4]
    assert restored["bets"][0]["spread_side_a"] == -4.5
    assert restored["bets"][0]["stake_amount"] == 40.0
