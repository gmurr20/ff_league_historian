"""backend/tests/test_harness.py - AI Harness & Repo Skeleton Verification Suite.

Purpose:
    Verifies that the repository directory skeleton, hierarchical AGENTS.md files,
    canonical REST API contract specification, ADRs, and tooling configurations
    are properly set up and syntactically valid for autonomous AI agent development.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_directory_skeleton_exists() -> None:
    """Verifies that all required directories exist in the repository skeleton."""
    expected_dirs = [
        REPO_ROOT / "db",
        REPO_ROOT / "backend",
        REPO_ROOT / "backend" / "models",
        REPO_ROOT / "backend" / "jobs",
        REPO_ROOT / "backend" / "services",
        REPO_ROOT / "backend" / "routes",
        REPO_ROOT / "backend" / "tests",
        REPO_ROOT / "backend" / "tests" / "fixtures",
        REPO_ROOT / "frontend",
        REPO_ROOT / "docs",
        REPO_ROOT / "docs" / "adr",
    ]
    for directory in expected_dirs:
        assert directory.is_dir(), f"Expected directory missing: {directory}"


def test_agents_markdown_hierarchy() -> None:
    """Verifies that the root and domain AGENTS.md files exist and contain core rules."""
    agent_files = {
        REPO_ROOT / "AGENTS.md": [
            "Seven Critical Engineering Guardrails",
            "make lint",
            "make test",
            "sqlite:///",
            "PostgreSQL 16",
        ],
        REPO_ROOT / "db" / "AGENTS.md": [
            "schema.sql",
            "JSONB",
            "PRAGMA foreign_keys=ON",
            "UNIQUE NULLS NOT DISTINCT",
            "manager_overrides.json",
            "All-Play",
        ],
        REPO_ROOT / "backend" / "AGENTS.md": [
            "read-only",
            "backfill_history.py",
            "sync_weekly.py",
            "pytest",
        ],
        REPO_ROOT / "frontend" / "AGENTS.md": [
            "<script setup lang=\"ts\">",
            "docs/api-contracts.md",
            "NetworkFirst",
            "CacheFirst",
        ],
    }

    for path, expected_tokens in agent_files.items():
        assert path.is_file(), f"Expected context file missing: {path}"
        content = path.read_text(encoding="utf-8")
        for token in expected_tokens:
            assert token in content, f"Token '{token}' missing from {path.name}"


def test_api_contracts_specification() -> None:
    """Verifies that docs/api-contracts.md defines the canonical REST endpoints."""
    contracts_file = REPO_ROOT / "docs" / "api-contracts.md"
    assert contracts_file.is_file(), "docs/api-contracts.md is missing"

    content = contracts_file.read_text(encoding="utf-8")
    required_endpoints = [
        "/api/v1/health",
        "/api/v1/meta",
        "/api/v1/earnings/leaderboard",
        "/api/v1/standings/current",
        "/api/v1/history/head-to-head",
        "/api/v1/trades/trends",
        "/api/v1/transactions/summary",
    ]
    for endpoint in required_endpoints:
        assert endpoint in content, f"Endpoint '{endpoint}' missing from api-contracts.md"


def test_architecture_decision_record() -> None:
    """Verifies that docs/adr/001-maximal-espn-ingestion.md exists and documents key decisions."""
    adr_file = REPO_ROOT / "docs" / "adr" / "001-maximal-espn-ingestion.md"
    assert adr_file.is_file(), "ADR 001 is missing"

    content = adr_file.read_text(encoding="utf-8")
    for phrase in [
        "Maximal Upfront ESPN Data Ingestion",
        "Two-Tier",
        "raw_espn_snapshots",
        "SQLite",
        "PostgreSQL 16",
    ]:
        assert phrase in content, f"Phrase '{phrase}' missing from ADR 001"


def test_tooling_and_configuration_files() -> None:
    """Verifies required tooling and environment files exist."""
    required_files = [
        REPO_ROOT / "Makefile",
        REPO_ROOT / "pyproject.toml",
        REPO_ROOT / "backend" / "requirements.txt",
        REPO_ROOT / ".env.example",
        REPO_ROOT / "docker-compose.yml",
        REPO_ROOT / ".gitignore",
        REPO_ROOT / "db" / "schema.sql",
        REPO_ROOT / "db" / "manager_overrides.json",
    ]
    for file_path in required_files:
        assert file_path.is_file(), f"Required tooling file missing: {file_path}"

    # Verify Makefile has expected targets
    makefile_content = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    for target in ["install:", "lint:", "test:", "seed:", "backfill:", "sync-weekly:", "build:", "check:"]:
        assert target in makefile_content, f"Makefile missing target '{target}'"

    # Verify .env.example contains expected keys
    env_content = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    for key in ["DATABASE_URL", "ESPN_LEAGUE_ID", "ESPN_S2", "ESPN_SWID", "FLASK_ENV", "VITE_API_BASE_URL"]:
        assert key in env_content, f".env.example missing key '{key}'"

    # Verify db/manager_overrides.json parses as valid JSON
    overrides_file = REPO_ROOT / "db" / "manager_overrides.json"
    data = json.loads(overrides_file.read_text(encoding="utf-8"))
    assert "overrides" in data, "manager_overrides.json missing 'overrides' key"


def test_sqlite_foreign_key_and_connection_smoke() -> None:
    """Verifies that SQLite in-memory database initializes with foreign keys enabled."""
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA foreign_keys")
    row = cursor.fetchone()
    assert row is not None and row[0] == 1, "SQLite foreign keys pragma failed to enable"
    cursor.close()
    conn.close()
