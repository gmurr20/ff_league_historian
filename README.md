# Fantasy Football League Historian

> **Operating Mandate:** This repository is an **AI-Only Codebase**. Every line of code, test, migration, and documentation update is authored and maintained by autonomous AI agents. Human maintainers review PRs and deploy, while agents execute end-to-end tasks independently following strict architectural guardrails.

---

## 1. System Map & Architecture Overview

The Fantasy Football League Historian is an enterprise-grade fantasy analytics platform designed to immortalize league history, rivalries, trade heists, financial earnings, and manager luck across all eras of an ESPN fantasy football league.

The platform is engineered as three strictly decoupled components:

```
                           +---------------------------+
                           |     ESPN Fantasy API      |
                           +-------------+-------------+
                                         |
                       (One-time backfill / Weekly cron)
                                         v
+------------------+       +---------------------------+
|  SQLite (Local)  | <---> | SQLAlchemy 2.0 Ingestion  | ---> PostgreSQL 16
|  (Dev/Test/CI)   |       | (backend/jobs/ + models/) |      (Railway Production)
+------------------+       +-------------+-------------+
                                         |
                                (Read-only queries)
                                         v
                           +---------------------------+
                           |  Flask 3 REST API Server  |
                           |      (/api/v1/*)          |
                           |  Gunicorn (2w, 4 gthreads)|
                           +-------------+-------------+
                                         |
                               (JSON REST Contract)
                                         v
                           +---------------------------+
                           |   Vue 3 Mobile PWA App    |
                           |   (Vite + TS + Tailwind)  |
                           |    NGINX Alpine Server    |
                           +---------------------------+
```

1. **Out-of-Band ESPN Ingestion Layer (`backend/jobs/`):**
   - **`backend/jobs/backfill_history.py`:** One-time historical backfill crawling completed historical seasons (`is_completed = TRUE`), archiving raw ESPN API payloads into `raw_espn_snapshots`, and supporting `--from-snapshots` for zero-network database rebuilds.
   - **`backend/jobs/sync_weekly.py`:** Lightweight cron job querying *only* the active season (`is_active = TRUE`) across a rolling 2-week window (`current_week - 1` and `current_week`), reconciling financial payouts against Elias stat corrections, auto-completing the season at championship conclusion, and exiting as a fast no-op during the offseason.
2. **Read-Only Backend REST API (`backend/`):**
   - Flask 3 + SQLAlchemy 2.0 read-only service exposed under `/api/v1/*`.
   - Served by Gunicorn in production (`2 workers, 4 gthreads`), backed by PostgreSQL 16 (or local SQLite fallback).
   - Read-only queries with strict caching headers (`Cache-Control: public, max-age=60`).
3. **Mobile-First Client (`frontend/`):**
   - Vue 3 + Vite + TypeScript + Tailwind CSS PWA.
   - PWA caching: `NetworkFirst` for `/api/v1/*` endpoints, `CacheFirst` for static assets.
   - Dark/stadium athletic UI optimized for mobile touch and iOS safe-area insets.

---

## 2. Seven Critical Engineering Guardrails

1. **Two-Tier Ingestion Architecture:**
   Never re-crawl completed historical seasons in the weekly cron. Historical seasons (`is_completed = TRUE`) are immutable. `sync_weekly.py` queries *only* the active season (`is_active = TRUE`) over a rolling 2-week window.
2. **PostgreSQL `NULL` Uniqueness & Stat Corrections (`earnings_ledger`):**
   Because podium payouts have `week = NULL`, standard SQL `NULL != NULL` fails to block duplicate championship records. We enforce PostgreSQL 15+ `UNIQUE NULLS NOT DISTINCT` (and partial unique indexes on SQLite). Ingestion reconciles weekly payouts rather than blindly appending, cleanly handling Tuesday win -> Thursday Elias stat-correction flips.
3. **Manager Identity Across Churn & Co-Owners:**
   Franchise owners change accounts or co-manage teams. Managers are tracked by `espn_member_id` GUIDs with declarative alias resolution via `db/manager_overrides.json`.
4. **Playoff Brackets, Consolation Games, Multi-Week Finals & Byes:**
   ESPN groups championship playoffs, consolation ladders, toilet bowls, and byes in the same schedule feed. Matchups persist explicit `matchup_type` and `points_by_scoring_period JSONB`. Only `REGULAR` and `WINNERS_BRACKET` matchups count toward career Head-to-Head records.
5. **ESPN `mTransactions2` Deep Extraction & FAAB Bidding Wars:**
   Ingestion captures losing waiver bids (`WAIVER_ERROR`) linked via `related_espn_transaction_id` to winning claims, producing auditable FAAB Bidding War receipts. Legacy pre-2018 seasons lacking transaction logs are handled gracefully with `has_transaction_data = FALSE`.
6. **Dual Database Dialect Support:**
   Production uses PostgreSQL 16 (`DATABASE_URL=postgresql+psycopg://...`). Offline verification and local testing default to SQLite (`sqlite:///ff_historian.db` or `sqlite:///:memory:`) when Docker/PostgreSQL is unavailable.
7. **PWA Service Worker vs. API Caching:**
   API endpoints (`/api/v1/*`) use `NetworkFirst` in Workbox and short TTLs (`max-age=60`) in Flask. Static bundles use `CacheFirst` (`max-age=31536000, immutable`), while `sw.js` and `index.html` use `no-cache` so PWA updates activate immediately.

---

## 3. Quickstart & Local Development

### Prerequisites
- Python 3.12+
- Node.js 20+ and npm 10+
- (Optional) Docker & Docker Compose for local PostgreSQL 16

### Developer Commands (`Makefile`)

All common workflows are accessible via the root `Makefile`:

```bash
# 1. Install all backend and frontend dependencies
make install

# 2. Seed development SQLite database with 3 seasons of rich mock data
make seed

# 3. Run historical backfill from local archived snapshots (zero network calls)
make backfill

# 4. Run incremental weekly sync worker
make sync-weekly

# 5. Run Python linter (Ruff)
make lint

# 6. Run full automated test suite (50 unit, integration, and E2E tests)
make test

# 7. Build production frontend PWA bundle
make build

# 8. Full verification pipeline (lint + test + build)
make check
```

---

## 4. Environment Configuration (`.env`)

Copy `.env.example` to `.env` to configure local or production variables:

```bash
cp .env.example .env
```

### Key Configuration Variables

| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `DATABASE_URL` | Database connection URI (PostgreSQL or SQLite) | `postgresql+psycopg://postgres:postgres@localhost:5432/ff_historian` or `sqlite:///ff_historian.db` |
| `ESPN_S2` | ESPN Authentication cookie string (`espn_s2`) | *Retrieved from browser cookies on espn.com* |
| `ESPN_SWID` | ESPN Member GUID cookie string (`SWID`) | `{12345678-ABCD-1234-ABCD-1234567890AB}` |
| `ESPN_LEAGUE_ID` | Primary ESPN League ID | `12345678` |
| `ESPN_LEAGUE_IDS` | Comma-separated league IDs across eras | `12345678,87654321` |
| `FLASK_ENV` | Application environment (`development`, `testing`, `production`) | `development` |
| `PORT` | Backend REST API port | `5000` |
| `VITE_API_BASE_URL`| Frontend API upstream URL override (empty uses relative proxy) | `""` or `http://localhost:5000` |

### How to Retrieve ESPN Cookies (`ESPN_S2` & `ESPN_SWID`)
1. Log into your fantasy league on [fantasy.espn.com](https://fantasy.espn.com).
2. Open Developer Tools in your browser (F12 or right-click -> Inspect).
3. Navigate to **Application** (Chrome/Edge) or **Storage** (Firefox/Safari) -> **Cookies** -> `https://fantasy.espn.com`.
4. Copy the value of the `espn_s2` cookie (a long alphanumeric string ending in `==`).
5. Copy the value of the `SWID` cookie (a UUID wrapped in curly braces, e.g. `{...}`).

### Historical Season Access & Incremental Backfill
- **Recent Seasons (2018–present):** Fully accessible via the modern ESPN v3 API endpoints (`/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{id}`).
- **Legacy Seasons (pre-2018):** ESPN routes older seasons through the legacy `leagueHistory` endpoint (`/apis/v3/games/ffl/leagueHistory/{id}?seasonId={year}`).
- **League ID Migrations:** If your league reconstituted or changed league IDs in past seasons, list all IDs in `ESPN_LEAGUE_IDS=ID1,ID2`.
- **Offline Snapshot Replay:** Every live crawl automatically archives raw JSON responses into `raw_espn_snapshots`. Run `python -m backend.jobs.backfill_history --from-snapshots` to rebuild tables without network access.

---

## 5. Railway Production Deployment Runbook

The system is configured for multi-service deployment on [Railway](https://railway.app) using `railway.toml`.

### Architecture Services

```
+----------------------------------------------------------------------------------+
|                             Railway Production Project                           |
|                                                                                  |
|  +--------------------+         +--------------------+     +------------------+  |
|  |   PostgreSQL 16    | <------ | Flask 3 API Server | <-- | Vue 3 PWA Client |  |
|  |   Managed DB       |         | Gunicorn (2w, 4th) |     | NGINX Alpine     |  |
|  +--------------------+         +--------------------+     +------------------+  |
|            ^                              ^                                      |
|            |                              |                                      |
|            +------ +----------------------+                                      |
|                    | Weekly Cron Worker   |                                      |
|                    | (0 10 * * 2,4)       |                                      |
|                    +----------------------+                                      |
+----------------------------------------------------------------------------------+
```

1. **Service 1: PostgreSQL 16 Database:**
   - Add Railway's managed PostgreSQL plugin.
   - Railway injects `DATABASE_URL=postgresql+psycopg://postgres:...`.
2. **Service 2: Flask 3 REST API (`backend`):**
   - Source: `backend/Dockerfile`
   - Start Command: `gunicorn -c backend/gunicorn.conf.py "backend.app:create_app()"`
   - Healthcheck Path: `/api/v1/health`
3. **Service 3: Vue 3 PWA Frontend (`frontend`):**
   - Source: `frontend/Dockerfile` (multi-stage build serving via `nginx:1.27-alpine`)
   - NGINX serves SPA routing with `try_files $uri $uri/ /index.html;`, caches static assets immutably, forces `no-cache` on `sw.js` and `manifest.webmanifest`, and proxies `/api/` to the API service.
4. **Service 4: Rolling Weekly Sync Worker (`cron-weekly-sync`):**
   - Source: `backend/Dockerfile`
   - Schedule: `0 10 * * 2,4` (Every Tuesday and Thursday at 10:00 UTC / 05:00 CST / 06:00 EST).
   - Start Command: `python -m backend.jobs.sync_weekly`
   - Finalizes Monday Night Football matchups on Tuesday morning, reconciles NFL Elias stat corrections on Thursday morning, processes FAAB waiver claims, and automatically transitions the season to `is_completed = TRUE` after championship week.

### Initial Production Deployment Steps

1. Connect the repository to Railway.
2. Provision the PostgreSQL 16 database service.
3. Configure environment variables (`DATABASE_URL`, `ESPN_S2`, `ESPN_SWID`, `ESPN_LEAGUE_ID`).
4. Execute the one-time historical backfill using the Railway CLI:
   ```bash
   railway run python -m backend.jobs.backfill_history
   ```
5. Deploy the API and Frontend services. The weekly cron worker will execute autonomously on Tuesdays and Thursdays.

---

## 6. REST API Endpoints & Contracts

All endpoints return JSON under `/api/v1/*` with strict `Cache-Control: public, max-age=60` headers. Canonical schemas are specified in [`docs/api-contracts.md`](file:///Users/gregmurray/Documents/git/ff_league_historian/docs/api-contracts.md) and typed in `frontend/src/types/api.ts`:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/health` | Service health status and database connectivity check. |
| `GET` | `/api/v1/meta` | League metadata, season list, managers, and ingestion audit status. |
| `GET` | `/api/v1/earnings/leaderboard` | All-time & seasonal bankroll rankings ($10 regular win, $5 tie, podium payouts). |
| `GET` | `/api/v1/standings/current` | Season standings with All-Play record, Weekly Median, Schedule Luck, and Max PF. |
| `GET` | `/api/v1/history/head-to-head` | Career rivalry matrix & pairwise Tale of the Tape comparator. |
| `GET` | `/api/v1/trades/trends` | Trade network, frequent trading partner alliances, and post-trade realized points. |
| `GET` | `/api/v1/transactions/summary` | FAAB efficiency, waiver success/fail rates, and FAAB Bidding War receipts. |

---

## 7. Developer Context Map (Progressive Disclosure)

Agents and contributors should navigate directly to domain-specific documentation:

- **Root Context:** [`AGENTS.md`](file:///Users/gregmurray/Documents/git/ff_league_historian/AGENTS.md) — System map, engineering rules, handoff protocol.
- **Database Architecture:** [`db/AGENTS.md`](file:///Users/gregmurray/Documents/git/ff_league_historian/db/AGENTS.md) — Schema DDL invariants, constraint rules, manager identity overrides.
- **Backend & Ingestion:** [`backend/AGENTS.md`](file:///Users/gregmurray/Documents/git/ff_league_historian/backend/AGENTS.md) — Blueprints, query services, backfill vs weekly sync jobs.
- **Frontend PWA:** [`frontend/AGENTS.md`](file:///Users/gregmurray/Documents/git/ff_league_historian/frontend/AGENTS.md) — Vue 3 setup patterns, mobile design tokens, Workbox caching.
- **API Contracts:** [`docs/api-contracts.md`](file:///Users/gregmurray/Documents/git/ff_league_historian/docs/api-contracts.md) — Canonical TypeScript interfaces and endpoint schemas.
- **Architecture Decisions:** [`docs/adr/001-maximal-espn-ingestion.md`](file:///Users/gregmurray/Documents/git/ff_league_historian/docs/adr/001-maximal-espn-ingestion.md) — Maximal upfront ingestion strategy.

---

## 8. Automated Verification Suite

Run full pipeline verification locally:

```bash
make check
```

This executes:
1. `make lint`: Ruff linting across Python modules (zero errors or warnings).
2. `make test`: 50 automated tests in `backend/tests/` (model constraints, pure parsers, live crawl/snapshot replay, rolling weekly sync, Elias stat-correction flip, REST query services, and E2E contract smoke tests).
3. `make build`: TypeScript typecheck (`vue-tsc --noEmit`) and Vite production PWA bundle build.
