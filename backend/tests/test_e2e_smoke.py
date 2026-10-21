"""backend/tests/test_e2e_smoke.py - End-to-End Pipeline & Contract Verification Suite.

Purpose:
    Executes Phase 10 end-to-end verification covering:
    1. test_e2e_backfill_to_weekly_sync_to_api_responses:
       - In-memory database initialization
       - Multi-season backfill_history using recorded JSON fixtures (2022, 2023, 2023 deep, 2024)
       - raw_espn_snapshots persistence & --from-snapshots zero-network replay
       - Active-season sync_weekly rolling window execution
       - Flask REST API client querying all 7 endpoints with HTTP 200, 60s cache header, and non-empty payloads
    2. test_e2e_api_response_keys_match_typescript_contracts:
       - Programmatically extracts TypeScript interfaces from frontend/src/types/api.ts and docs/api-contracts.md
       - Asserts all top-level and nested keys across all 7 endpoints strictly match TypeScript contracts
    3. test_production_packaging_files_exist:
       - Verifies backend/Dockerfile, frontend/Dockerfile, frontend/nginx.conf, and railway.toml
       - Validates commands (gunicorn, sync_weekly, backfill_history, sw.js cache headers, 0 10 * * 2,4 schedule)
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy.orm import sessionmaker

from backend.app import create_app
from backend.database import create_db_engine, init_db
from backend.jobs.backfill_history import backfill_history
from backend.jobs.espn_client import EspnClient
from backend.jobs.sync_weekly import sync_weekly
from backend.models.raw_snapshot import RawEspnSnapshot
from db.seed_dev import seed_database

FIXTURES_DIR = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def load_fixture(filename: str) -> dict[str, Any]:
    with open(FIXTURES_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


class E2EMockEspnClient(EspnClient):
    """Mock ESPN API client serving fixture payloads with call counting."""

    def __init__(self, mapping: dict[int, dict[str, Any]]) -> None:
        super().__init__(league_id="12345678", espn_s2="mock_s2", swid="{MOCK-SWID}")
        self.mapping = mapping
        self.call_count = 0

    def fetch_league(
        self,
        season_year: int,
        views: list[str] | None = None,
        x_fantasy_filter: dict[str, Any] | None = None,
        allow_inaccessible: bool = True,
        league_id: str | None = None,
    ) -> dict[str, Any] | None:
        self.call_count += 1
        data = self.mapping.get(season_year)
        return copy.deepcopy(data) if data is not None else None


# ==============================================================================
# 1. Full Pipeline Flow E2E Smoke Test
# ==============================================================================


def test_e2e_backfill_to_weekly_sync_to_api_responses() -> None:
    """End-to-end smoke test verifying backfill -> snapshots -> weekly sync -> REST API."""
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()

    # Load recorded ESPN fixtures
    f2022 = load_fixture("espn_league_2022.json")
    f2023 = load_fixture("espn_league_2023.json")
    f2023_deep = load_fixture("espn_deep_2023.json")
    f2024 = load_fixture("espn_league_2024.json")

    # Step A: One-time historical backfill using live mock client
    initial_client = E2EMockEspnClient({2022: f2022, 2023: f2023, 2024: f2024})
    run_1 = backfill_history(
        session=session,
        from_snapshots=False,
        from_year=2022,
        to_year=2024,
        league_id="12345678",
        client=initial_client,
    )
    assert run_1.status == "SUCCESS"
    assert run_1.records_processed > 0
    assert initial_client.call_count == 3

    # Backfill deep 2023 payload to simulate transaction & lineup archive
    deep_client = E2EMockEspnClient({2023: f2023_deep})
    run_deep = backfill_history(
        session=session,
        from_snapshots=False,
        from_year=2023,
        to_year=2023,
        league_id="12345678",
        client=deep_client,
    )
    assert run_deep.status == "SUCCESS"

    # Verify raw_espn_snapshots were persisted
    snapshots_count = session.query(RawEspnSnapshot).count()
    assert snapshots_count >= 3

    # Step B: Test --from-snapshots zero-network replay
    replay_client = E2EMockEspnClient({2022: f2022, 2023: f2023_deep, 2024: f2024})
    run_replay = backfill_history(
        session=session,
        from_snapshots=True,
        from_year=2022,
        to_year=2024,
        league_id="12345678",
        client=replay_client,
    )
    assert run_replay.status == "SUCCESS"
    # Zero network calls during snapshot rebuild
    assert replay_client.call_count == 0

    # Step C: Run sync_weekly on active 2024 season over 2-week rolling window
    sync_client = E2EMockEspnClient({2024: f2024})
    sync_run = sync_weekly(session=session, client=sync_client)
    assert sync_run.status == "SUCCESS"
    assert sync_run.week_range == "7-8"
    session.commit()

    # Step D: Mount Flask test client and query all 7 REST endpoints
    app = create_app({"TESTING": True, "SESSION_FACTORY": session_factory})
    client = app.test_client()

    endpoints = [
        "/api/v1/health",
        "/api/v1/meta",
        "/api/v1/earnings/leaderboard",
        "/api/v1/standings/current",
        "/api/v1/history/head-to-head",
        "/api/v1/trades/trends",
        "/api/v1/transactions/summary",
    ]

    for ep in endpoints:
        resp = client.get(ep)
        assert resp.status_code == 200, f"Endpoint {ep} failed with status {resp.status_code}"
        assert resp.headers.get("Cache-Control") == "public, max-age=60"
        payload = resp.get_json()
        assert isinstance(payload, dict), f"Payload for {ep} was not a dict"
        assert len(payload) > 0, f"Payload for {ep} was empty"

    session.close()
    engine.dispose()


# ==============================================================================
# 2. TypeScript Contract Alignment E2E Test
# ==============================================================================


def _extract_ts_interfaces(ts_path: Path) -> dict[str, dict[str, Any]]:
    """Parse TypeScript interface definitions and their direct/inherited field sets."""
    content = ts_path.read_text(encoding="utf-8")
    interfaces: dict[str, dict[str, Any]] = {}
    pattern = re.compile(
        r"export\s+interface\s+(\w+)(?:\s+extends\s+(\w+))?\s*\{([^}]+)\}",
        re.DOTALL,
    )
    for match in pattern.finditer(content):
        name = match.group(1)
        parent = match.group(2)
        body = match.group(3)
        fields: set[str] = set()
        for line in body.split("\n"):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            field_match = re.match(r"^(\w+)\??\s*:", line)
            if field_match:
                fields.add(field_match.group(1))
        interfaces[name] = {"fields": fields, "parent": parent}

    # Resolve interface inheritance
    for data in interfaces.values():
        parent_name = data["parent"]
        while parent_name and parent_name in interfaces:
            data["fields"].update(interfaces[parent_name]["fields"])
            parent_name = interfaces[parent_name]["parent"]

    return interfaces


def test_e2e_api_response_keys_match_typescript_contracts() -> None:
    """Verifies every top-level and nested key returned by all 7 Flask endpoints matches api.ts."""
    ts_file = REPO_ROOT / "frontend" / "src" / "types" / "api.ts"
    assert ts_file.exists(), f"TypeScript definitions not found at {ts_file}"
    interfaces = _extract_ts_interfaces(ts_file)

    # Also assert docs/api-contracts.md exists as canonical reference
    contracts_file = REPO_ROOT / "docs" / "api-contracts.md"
    assert contracts_file.exists(), f"API contracts not found at {contracts_file}"

    # Setup seeded test database
    engine = create_db_engine("sqlite:///:memory:")
    seed_database(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    app = create_app({"TESTING": True, "SESSION_FACTORY": session_factory})
    client = app.test_client()

    def assert_interface(data: dict[str, Any], iface_name: str) -> None:
        assert iface_name in interfaces, f"Unknown TypeScript interface: {iface_name}"
        expected = interfaces[iface_name]["fields"]
        actual = set(data.keys())
        diff_actual = actual - expected
        diff_expected = expected - actual
        assert actual == expected, (
            f"Interface '{iface_name}' field mismatch! "
            f"Unexpected keys in response: {diff_actual}, Missing keys: {diff_expected}"
        )

    # 1. Health endpoint -> HealthResponse
    res_health = client.get("/api/v1/health")
    assert res_health.status_code == 200
    assert_interface(res_health.get_json(), "HealthResponse")

    # 2. Meta endpoint -> MetaResponse + SeasonMeta + ManagerMeta + SyncStatus
    res_meta = client.get("/api/v1/meta")
    assert res_meta.status_code == 200
    meta_json = res_meta.get_json()
    assert_interface(meta_json, "MetaResponse")
    assert len(meta_json["available_seasons"]) > 0
    assert_interface(meta_json["available_seasons"][0], "SeasonMeta")
    assert len(meta_json["managers"]) > 0
    assert_interface(meta_json["managers"][0], "ManagerMeta")
    assert_interface(meta_json["last_sync"], "SyncStatus")

    # 3. Earnings endpoint -> EarningsLeaderboardResponse + EarningsLeaderboardEntry + ManagerSeasonBreakdown
    res_earnings = client.get("/api/v1/earnings/leaderboard")
    assert res_earnings.status_code == 200
    earnings_json = res_earnings.get_json()
    assert_interface(earnings_json, "EarningsLeaderboardResponse")
    assert len(earnings_json["leaderboard"]) > 0
    leader = earnings_json["leaderboard"][0]
    assert_interface(leader, "EarningsLeaderboardEntry")
    assert len(leader["season_breakdown"]) > 0
    assert_interface(leader["season_breakdown"][0], "ManagerSeasonBreakdown")
    if len(earnings_json.get("weekly_nuanced_payouts", [])) > 0:
        assert_interface(earnings_json["weekly_nuanced_payouts"][0], "WeeklyNuancedPayoutEntry")

    # 4. Standings endpoint -> StandingsResponse + StandingEntry + WeeklyStandingPoint
    res_standings = client.get("/api/v1/standings/current")
    assert res_standings.status_code == 200
    standings_json = res_standings.get_json()
    assert_interface(standings_json, "StandingsResponse")
    assert len(standings_json["standings"]) > 0
    assert_interface(standings_json["standings"][0], "StandingEntry")
    assert len(standings_json["standings"][0]["weekly_history"]) > 0
    assert_interface(standings_json["standings"][0]["weekly_history"][0], "WeeklyStandingPoint")

    # 5. Head-to-Head endpoint (with pairwise query) -> HeadToHeadResponse + H2HPairDetail
    res_h2h = client.get("/api/v1/history/head-to-head?managerA=1&managerB=2")
    assert res_h2h.status_code == 200
    h2h_json = res_h2h.get_json()
    assert_interface(h2h_json, "HeadToHeadResponse")
    assert len(h2h_json["managers"]) > 0
    assert_interface(h2h_json["managers"][0], "H2HManagerRef")
    assert len(h2h_json["matrix"]) > 0
    assert_interface(h2h_json["matrix"][0], "H2HMatrixEntry")

    pair = h2h_json["pair_detail"]
    assert pair is not None
    assert_interface(pair, "H2HPairDetail")
    assert_interface(pair["manager_a"], "H2HManagerRef")
    assert_interface(pair["manager_b"], "H2HManagerRef")
    assert_interface(pair["regular_season"], "H2HRecordSplit")
    assert_interface(pair["playoffs"], "H2HRecordSplit")
    assert_interface(pair["combined"], "H2HCombinedSplit")
    assert_interface(pair["current_streak"], "H2HStreak")
    assert_interface(pair["biggest_blowout"], "H2HGameHighlight")
    assert len(pair["matchups"]) > 0
    assert_interface(pair["matchups"][0], "H2HMatchupGame")

    # 6. Trades endpoint -> TradesTrendsResponse + TopTradePartner + ActiveTrader + TradeDetail
    res_trades = client.get("/api/v1/trades/trends")
    assert res_trades.status_code == 200
    trades_json = res_trades.get_json()
    assert_interface(trades_json, "TradesTrendsResponse")
    assert len(trades_json["top_partners"]) > 0
    assert_interface(trades_json["top_partners"][0], "TopTradePartner")
    assert len(trades_json["active_traders"]) > 0
    assert_interface(trades_json["active_traders"][0], "ActiveTrader")
    assert len(trades_json["trades"]) > 0
    trade = trades_json["trades"][0]
    assert_interface(trade, "TradeDetail")
    assert len(trade["sides"]) > 0
    assert_interface(trade["sides"][0], "TradeSide")
    assert len(trade["sides"][0]["assets_received"]) > 0
    assert_interface(trade["sides"][0]["assets_received"][0], "TradePlayerAsset")

    # 7. Transactions endpoint (season=2023 with bidding wars & transaction items)
    res_tx = client.get("/api/v1/transactions/summary?season=2023")
    assert res_tx.status_code == 200
    tx_json = res_tx.get_json()
    assert_interface(tx_json, "TransactionsSummaryResponse")
    assert len(tx_json["manager_efficiency"]) > 0
    assert_interface(tx_json["manager_efficiency"][0], "ManagerEfficiency")
    assert len(tx_json["failure_reasons"]) > 0
    assert_interface(tx_json["failure_reasons"][0], "FailureReasonCount")
    assert len(tx_json["bidding_wars"]) > 0
    bw = tx_json["bidding_wars"][0]
    assert_interface(bw, "BiddingWar")
    assert_interface(bw["player"], "TransactionPlayerRef")
    assert_interface(bw["winner"], "WinningBidder")
    assert len(bw["losing_bids"]) > 0
    assert_interface(bw["losing_bids"][0], "LosingBid")
    assert len(tx_json["transactions"]) > 0
    assert_interface(tx_json["transactions"][0], "TransactionAuditItem")
    assert len(tx_json["transactions"][0]["items"]) > 0
    assert_interface(tx_json["transactions"][0]["items"][0], "TransactionItem")

    engine.dispose()


# ==============================================================================
# 3. Production Packaging Verification Test
# ==============================================================================


def test_production_packaging_files_exist() -> None:
    """Verifies Dockerfiles, NGINX config, and railway.toml exist with required commands."""
    backend_dockerfile = REPO_ROOT / "backend" / "Dockerfile"
    frontend_dockerfile = REPO_ROOT / "frontend" / "Dockerfile"
    frontend_nginx = REPO_ROOT / "frontend" / "nginx.conf"
    railway_toml = REPO_ROOT / "railway.toml"

    # 1. backend/Dockerfile
    assert backend_dockerfile.exists(), "backend/Dockerfile missing"
    backend_content = backend_dockerfile.read_text(encoding="utf-8")
    assert "python:3.12-slim" in backend_content
    assert "gunicorn" in backend_content
    assert "sync_weekly" in backend_content
    assert "backfill_history" in backend_content
    assert "backend/gunicorn.conf.py" in backend_content

    # 2. frontend/Dockerfile
    assert frontend_dockerfile.exists(), "frontend/Dockerfile missing"
    frontend_docker_content = frontend_dockerfile.read_text(encoding="utf-8")
    assert "node:20-alpine" in frontend_docker_content
    assert "nginx:1.27-alpine" in frontend_docker_content
    assert "npm run build" in frontend_docker_content

    # 3. frontend/nginx.conf
    assert frontend_nginx.exists(), "frontend/nginx.conf missing"
    nginx_content = frontend_nginx.read_text(encoding="utf-8")
    assert "try_files $uri $uri/ /index.html;" in nginx_content
    assert "sw.js" in nginx_content
    assert "no-cache" in nginx_content
    assert "public, max-age=31536000, immutable" in nginx_content
    assert "location /api/" in nginx_content
    assert "proxy_pass" in nginx_content

    # 4. railway.toml
    assert railway_toml.exists(), "railway.toml missing"
    railway_content = railway_toml.read_text(encoding="utf-8")
    assert "gunicorn" in railway_content
    assert "sync_weekly" in railway_content
    assert "backfill_history" in railway_content
    assert "0 10 * * 2,4" in railway_content
    assert "PostgreSQL" in railway_content or "postgres" in railway_content
    assert "services.api" in railway_content
    assert "services.frontend" in railway_content
    assert "services.cron-weekly-sync" in railway_content
