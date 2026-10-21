# backend/AGENTS.md — Backend Architecture, Ingestion & API Guidelines

> **Scope:** This guide governs Flask blueprints (`backend/routes/`), SQLAlchemy query services (`backend/services/`), ingestion jobs (`backend/jobs/`), database session lifecycles, and test suites (`backend/tests/`).

---

## 1. Service Boundaries & Design Principles

The backend is strictly divided into two distinct responsibilities:
1. **Out-of-Band Ingestion Jobs (`backend/jobs/`):** The *only* components that perform database writes, scrape ESPN endpoints, or process raw payloads.
2. **Read-Only Flask REST API (`backend/routes/`):** Purely read-only query endpoints under `/api/v1/*`. Under no circumstance should a GET request trigger an ingestion sync or write to the database.

---

## 2. SQLAlchemy 2.0 Session Management (`backend/database.py`)

- **Scoped Session Lifecycle:** Use `scoped_session` with context managers to guarantee sessions are closed and returned to the pool after each request or job execution.
- **Read-Only Mode:** Flask API endpoints query with auto-commit or read-only transactions.
- **Connection Configuration:**
  ```python
  from sqlalchemy import create_engine
  from sqlalchemy.orm import sessionmaker, declarative_base

  # Default to SQLite if DATABASE_URL is not set
  DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///ff_historian.db")
  engine = create_engine(DATABASE_URL, pool_pre_ping=True)
  SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
  Base = declarative_base()
  ```
- **Engine Event Hooks:** SQLite requires `PRAGMA foreign_keys=ON` on engine connect.

---

## 3. Ingestion Jobs: Two-Tier Architecture

### 3.1 Workflow A: One-Time Historical Backfill (`backend/jobs/backfill_history.py`)
- **Trigger:** Manual CLI execution once during initial onboarding or at season rollover.
- **Target:** All past seasons (`is_completed = TRUE`).
- **Behaviors:**
  - Rate-limits ESPN API calls politely with backoff.
  - Saves the raw HTTP response of every view into `raw_espn_snapshots` before parsing.
  - **`--from-snapshots` Flag:** Replays and reparses directly from stored snapshots in `raw_espn_snapshots` without network calls. This guarantees offline repeatability.

### 3.2 Workflow B: Incremental Weekly Cron (`backend/jobs/sync_weekly.py`)
- **Trigger:** Scheduled twice weekly (Tuesday & Thursday mornings: `0 10 * * 2,4`).
- **Target:** **Only** the current active season (`is_active = TRUE`).
- **Window:** Rolling 2-week window (`current_week - 1` and `current_week`).
  - *Tuesday Run:* Ingests Monday Night Football box scores, updates weekly matchups, awards regular season `$10` wins / `$5` ties.
  - *Thursday Run:* Ingests Wednesday waivers/FAAB bids, reconciles against official Elias Sports Bureau stat corrections (reversing or updating payouts if scores changed).
- **Offseason Behavior:** If no season has `is_active = TRUE`, exits immediately in under 1 second as a no-op.
- **Season Completion:** When the final playoff week completes, marks `is_completed = TRUE`, `is_active = FALSE`, computes podium payouts (1st, 2nd, 3rd), and transitions the season cleanly.

---

## 4. Flask API Conventions (`backend/routes/` & `backend/services/`)

- **Contract Adherence:** Every route must strictly conform to [`docs/api-contracts.md`](file:///Users/gregmurray/Documents/git/ff_league_historian/docs/api-contracts.md).
- **Blueprints:**
  - `backend/routes/meta.py` (`/api/v1/health`, `/api/v1/meta`)
  - `backend/routes/earnings.py` (`/api/v1/earnings/leaderboard`)
  - `backend/routes/standings.py` (`/api/v1/standings/current`)
  - `backend/routes/history.py` (`/api/v1/history/head-to-head`)
  - `backend/routes/trades.py` (`/api/v1/trades/trends`)
  - `backend/routes/transactions.py` (`/api/v1/transactions/summary`)
- **Caching Headers:** Add `Cache-Control: public, max-age=60` to API responses to allow fast browser/PWA caching while preventing stale financial/standings data.
- **Error Responses:** Standard JSON `{ "error": "NOT_FOUND", "message": "Season 1999 not found" }` with appropriate HTTP status codes (400, 404, 500).

---

## 5. Offline Fixture Testing Conventions (`backend/tests/` via `pytest`)

- **Test Runner:** All unit, integration, and regression suites run through `pytest` (`make test`).
- **Zero External Network Dependencies:** No unit or integration test should ever attempt to contact ESPN APIs.
- **Recorded Fixtures:** Place anonymized/scrubbed ESPN JSON responses in `backend/tests/fixtures/`:
  - `fixtures/espn_mSettings.json`
  - `fixtures/espn_mBoxscore.json`
  - `fixtures/espn_mTransactions2.json`
- **Database Fixtures:** Use SQLite in-memory database (`sqlite:///:memory:`) for fast test execution with full rollback between test cases.
- **Test Invariants:**
  1. Ledger payout reconciliation does not duplicate records.
  2. All-Play calculations sum correctly across league matchups.
  3. FAAB bidding war parser correctly links losing bids via `related_espn_transaction_id`.
  4. Matrix symmetry in Head-to-Head (`A wins = B losses`, `A PA = B PF`).
