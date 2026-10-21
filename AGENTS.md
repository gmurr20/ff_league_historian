# AGENTS.md — Master Context & Engineering Guardrails

> **Operating Mandate:** This repository is an **AI-Only Codebase**. Every line of code, test, migration, schema adjustment, and documentation update is authored and maintained by autonomous AI agents. Human maintainers review PRs and deploy, but agents execute end-to-end tasks independently.

---

## 1. System Map & Architecture Overview

The system is designed as three strictly decoupled components:
1. **Out-of-Band ESPN Ingestion Layer (`backend/jobs/`):**
   - Two-tier ingestion pipeline:
     - `backend/jobs/backfill_history.py`: One-time historical backfill crawling past completed seasons (`is_completed = TRUE`), archiving raw payloads in `raw_espn_snapshots`, and supporting `--from-snapshots` for zero-network database rebuilds.
     - `backend/jobs/sync_weekly.py`: Lightweight cron job querying *only* the active season (`is_active = TRUE`) across a rolling 2-week window (`current_week - 1` and `current_week`), reconciling financial payouts against Elias stat corrections.
2. **Read-Only Backend REST API (`backend/`):**
   - Flask 3 + SQLAlchemy 2.0 read-only service exposed under `/api/v1/*`.
   - Served by Gunicorn in production (`2 workers, 4 gthreads`), backed by PostgreSQL 16 (or local SQLite fallback).
   - Read-only queries with strict caching headers (`Cache-Control: public, max-age=60`).
3. **Mobile-First Client (`frontend/`):**
   - Vue 3 + Vite + TypeScript + Tailwind CSS PWA.
   - PWA caching: `NetworkFirst` for `/api/v1/*` endpoints, `CacheFirst` for static assets.
   - Dark/stadium athletic UI optimized for mobile touch and iOS safe-area insets.

```
                           +---------------------------+
                           |     ESPN Fantasy API      |
                           +-------------+-------------+
                                         |
                       (One-time backfill / Weekly cron)
                                         v
+------------------+       +---------------------------+
|  SQLite (Local)  | <---> | SQLAlchemy 2.0 Ingestion  | ---> PostgreSQL 16
|  (Dev/Test/CI)   |       | (backend/jobs/ + models/) |      (Docker/Railway)
+------------------+       +-------------+-------------+
                                         |
                                (Read-only queries)
                                         v
                           +---------------------------+
                           |  Flask 3 REST API Server  |
                           |      (/api/v1/*)          |
                           +-------------+-------------+
                                         |
                               (JSON REST Contract)
                                         v
                           +---------------------------+
                           |   Vue 3 Mobile PWA App    |
                           |   (Vite + TS + Tailwind)  |
                           +---------------------------+
```

---

## 2. Progressive Disclosure: Context Map

Agents must navigate directly to domain-specific instruction files rather than searching the whole repository:
- **Root Context (This File):** System map, global engineering rules, Makefile commands, handoff protocol.
- **Database Architecture:** [`db/AGENTS.md`](file:///Users/gregmurray/Documents/git/ff_league_historian/db/AGENTS.md) — Schema DDL invariants, dual PostgreSQL 16 / SQLite dialect compatibility, manager identity overrides, and SQL rules for derived metrics.
- **Backend & Ingestion:** [`backend/AGENTS.md`](file:///Users/gregmurray/Documents/git/ff_league_historian/backend/AGENTS.md) — Flask route blueprints, query services, session management, job execution rules, and offline test conventions.
- **Frontend PWA:** [`frontend/AGENTS.md`](file:///Users/gregmurray/Documents/git/ff_league_historian/frontend/AGENTS.md) — Vue 3 `<script setup lang="ts">` patterns, typed API client mirroring, mobile stadium styling, and Workbox PWA caching rules.
- **API Contracts:** [`docs/api-contracts.md`](file:///Users/gregmurray/Documents/git/ff_league_historian/docs/api-contracts.md) — Single source of truth for TypeScript interfaces and endpoint JSON payloads.
- **Architecture Decisions:** [`docs/adr/`](file:///Users/gregmurray/Documents/git/ff_league_historian/docs/adr/) — Context and rationale for fundamental architectural choices.

---

## 3. Seven Critical Engineering Guardrails

1. **Two-Tier Ingestion Architecture: Never Re-crawl Completed History in the Weekly Cron**
   - Historical seasons (`is_completed = TRUE`) are immutable. Crawling them requires dozens of network calls.
   - `backend/jobs/backfill_history.py` is executed once (or at season rollover) and supports `--from-snapshots` to rebuild tables without network access.
   - `backend/jobs/sync_weekly.py` runs on a schedule (`0 10 * * 2,4`) and **only** inspects the active season (`is_active = TRUE`) in a 2-week rolling window (`current_week - 1` and `current_week`). It auto-completes the season when the championship finalizes and becomes a fast no-op in the offseason.
2. **PostgreSQL `NULL` Uniqueness & Stat Corrections (`earnings_ledger`)**
   - Standard SQL treats `NULL != NULL`. Because podium payouts have `week = NULL`, a naive unique constraint fails to block duplicate championship records.
   - Use PostgreSQL 15+ `UNIQUE NULLS NOT DISTINCT` (and equivalent partial/coalesced indexes in SQLite).
   - Ingestion must **reconcile** weekly payouts (handling score flips from Elias stat corrections) rather than blindly appending with `ON CONFLICT DO NOTHING`.
3. **Manager Identity Across Churn & Co-Owners (`managers` ↔ `teams`)**
   - Owners change accounts or co-manage franchises.
   - `managers` stores `espn_member_id` (GUID). `teams` stores `manager_id`, optional `co_manager_id`, and `raw_owner_guids JSONB`.
   - Ingestion must check [`db/manager_overrides.json`](file:///Users/gregmurray/Documents/git/ff_league_historian/db/manager_overrides.json) before creating duplicate manager records.
4. **Playoff Brackets, Consolation Games, Multi-Week Finals & Byes (`matchups`)**
   - ESPN groups `WINNERS_BRACKET`, `WINNERS_CONSOLATION_LADDER`, `LOSERS_CONSOLATION_LADDER`, and `BYE` matchups in the same schedule endpoint.
   - Store explicit `matchup_type`, make `away_team_id` and `winner_team_id` nullable, and persist `points_by_scoring_period JSONB`.
   - Only count `REGULAR` and `WINNERS_BRACKET` matchups toward career Head-to-Head records.
5. **ESPN `mTransactions2` Deep Extraction & Bidding Wars**
   - ESPN requires explicit `x-fantasy-filter` headers per scoring period to reveal failed waiver bids (`WAIVER_ERROR`).
   - Store `related_espn_transaction_id` to link losing bids to winning claims for FAAB Bidding War receipts.
   - Gracefully handle legacy pre-2018 seasons where transaction logs were purged by ESPN (`has_transaction_data = FALSE`).
6. **Dual Database Dialect Support (PostgreSQL 16 & SQLite Fallback)**
   - Production uses PostgreSQL 16 (`DATABASE_URL=postgresql+psycopg://...`).
   - Offline verification and local testing default to SQLite (`sqlite:///ff_historian.db` or `sqlite:///:memory:`) when Docker/PostgreSQL is unavailable.
   - Models and migrations must remain dialect-compatible (SQLAlchemy `JSON` with Postgres `JSONB`, `PRAGMA foreign_keys=ON` on SQLite).
7. **PWA Service Worker vs. API Caching**
   - API endpoints (`/api/v1/*`) MUST use `NetworkFirst` in Workbox and short TTLs (`max-age=60`) in Flask.
   - Static bundles use `CacheFirst`. Users must never see stale financial payouts or standings due to aggressive service worker caching.

---

## 4. Standard Agent Verification Commands

All agents must verify their changes locally before handoff using the root `Makefile`:

| Command | Action | Invariant / Expectation |
| :--- | :--- | :--- |
| `make install` | Installs dependencies | Creates `.venv`, installs `backend/requirements.txt`, and runs `npm install` in `frontend/` if present. |
| `make lint` | Code linting | Runs `ruff check .` with zero errors or warnings. |
| `make test` | Test suite | Runs `pytest` against `backend/tests/` using offline fixtures and SQLite in-memory DB. |
| `make seed` | Dev database seeder | Executes `python3 -m db.seed_dev` idempotently. |
| `make backfill` | Offline snapshot backfill | Executes `python3 -m backend.jobs.backfill_history --from-snapshots`. |
| `make sync-weekly` | Weekly rolling sync | Executes `python3 -m backend.jobs.sync_weekly`. |
| `make build` | Frontend production build | Executes `npm run build` inside `frontend/` (if present). |
| `make check` | Full pipeline verification | Executes `make lint`, `make test`, and `make build`. Must be 100% green before handoff. |

---

## 5. Agent Handoff Protocol

When completing a roadmap phase or task, every agent MUST follow this protocol:
1. **Self-Verification:** Run `make lint` and `make test`. Ensure all tests pass with zero warnings or errors.
2. **Contract Preservation:** If any API schema changed, verify that [`docs/api-contracts.md`](file:///Users/gregmurray/Documents/git/ff_league_historian/docs/api-contracts.md) and `frontend/src/types/api.ts` are synchronized.
3. **Roadmap Status Update:** Mark the assigned phase in [`ROADMAP.md`](file:///Users/gregmurray/Documents/git/ff_league_historian/ROADMAP.md) as `[x] Completed`.
4. **Context Summary:** Output a concise report specifying:
   - Deliverables created or modified.
   - Verification command results (`make lint`, `make test`).
   - Clear instructions for the next agent picking up the subsequent phase.
