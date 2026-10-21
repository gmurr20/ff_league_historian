# ADR 001: Maximal Upfront ESPN Data Ingestion, Two-Tier Architecture & Dialect Compatibility

- **Status:** Accepted
- **Date:** 2026-10-21
- **Deciders:** Staff TL, AI Engineering Harness

---

## 1. Context & Problem Statement

Fantasy football league history platforms frequently suffer from architectural regret: systems initially capture only high-level weekly scores and season standings. When users later request richer analytical features—such as **Trade Autopsies** (who really won a blockbuster trade based on subsequent starter performance), **Waiver Wire ROI** (points produced per FAAB dollar spent), **All-Play & Weekly Median Luck Indices**, or **FAAB Bidding War Receipts** (revealing who was outbid and by how much)—the engineering team discovers that the historical data was never stored and may be permanently inaccessible from ESPN's API.

Furthermore, ESPN's Fantasy API is notoriously idiosyncratic:
1. Past completed seasons (`is_completed = TRUE`) are immutable on ESPN, but fetching them requires dozens of network calls across multiple view endpoints (`mSettings`, `mBoxscore`, `mTransactions2`, etc.).
2. In-progress seasons experience Tuesday post-MNF score changes and Thursday Elias Sports Bureau official stat corrections that can flip matchup outcomes and weekly cash payouts.
3. Legacy seasons (pre-2018) often lack transaction logs and member GUIDs, requiring graceful degradation.
4. Autonomous AI agents working on this codebase need to run full end-to-end integration tests without live ESPN credentials or live PostgreSQL database servers.

---

## 2. Decision Drivers

- **Zero Future Schema Surgery:** Persist everything ESPN exposes on the first pass so that future analytical features require only new queries, not schema alterations.
- **Rate-Limit Politeness & Speed:** Never repeatedly crawl immutable historical seasons in periodic background cron jobs.
- **Replayability & Zero-Network Recovery:** Storing raw ESPN JSON responses guarantees the database can be rebuilt from scratch without making any external HTTP calls if parsers are revised.
- **Stat-Correction Resilience:** Financial payouts ($10 weekly win, $5 tie) must reconcile idempotently when stat corrections flip scores.
- **100% Offline Testability:** Any AI agent or developer must be able to verify models, migrations, queries, and APIs using SQLite in-memory without requiring Docker or PostgreSQL.

---

## 3. Considered Options

1. **Option A: Minimal Ingestion (Store aggregate team scores and final standings only).**
   - *Pros:* Simple initial schema; fast scraping.
   - *Cons:* Precludes Trade Autopsies, Bidding Wars, Optimal Lineups, and Player Profiles. Irreversible data loss.
2. **Option B: Query-Time ESPN Scraping (Fetch on-demand from ESPN when a user visits the page).**
   - *Pros:* No database required.
   - *Cons:* Extremely slow response times (>5-10s), breaks offline PWA capabilities, vulnerable to ESPN rate-limiting and cookie expiration.
3. **Option C (Selected): Maximal Upfront Ingestion with Two-Tier Pipeline, Raw Archive & Dual-Dialect Support.**
   - *Pros:* Captures all 8 data domains (settings, teams, managers, canonical players, weekly boxscore lineups, deep transactions with failed bids, and financial payouts); isolates backfill from weekly cron; archives raw JSON for replayability; enables local SQLite testing and PostgreSQL 16 production parity.
   - *Cons:* Larger initial schema and upfront modeling effort.

---

## 4. Architectural Decisions

### 4.1 Maximal Data Domain Coverage
From Phase 2 onwards, the database persists:
1. `raw_espn_snapshots`: Immutable raw JSON payloads keyed by `(season_year, view_name, scoring_period)`.
2. `seasons`: Rules, scoring settings, roster slot allocations, and data-availability flags (`has_transaction_data`, `has_boxscore_data`).
3. `managers` & `teams`: Identity reconciliation supporting ESPN GUIDs, co-owners, and overrides via `db/manager_overrides.json`.
4. `players`: Canonical NFL player registry (`espn_player_id`, position, NFL team, headshot URL).
5. `matchups`: Scores, optimal scores (Max PF), bench points, and bracket types (`REGULAR`, `WINNERS_BRACKET`, consolation ladders, and byes).
6. `weekly_lineups`: Every rostered player's starter/bench status, actual points, projected points, and raw weekly stat maps.
7. `transactions`, `transaction_items`, & `trades`: Free agents, waivers, drops, and trades, including failed bids (`WAIVER_ERROR`) and `related_espn_transaction_id` for FAAB Bidding Wars.
8. `earnings_ledger`: Financial payouts for regular-season wins ($10), ties ($5), and podium finishes.

### 4.2 Two-Tier Ingestion Pipeline
- **Tier 1 — One-Time Historical Backfill (`backend/jobs/backfill_history.py`):**
  - Crawls historical completed seasons once.
  - Supports `--from-snapshots` to re-parse stored database snapshots without network access.
- **Tier 2 — Incremental Active-Season Rolling Sync (`backend/jobs/sync_weekly.py`):**
  - Scheduled via Railway Cron on Tuesday and Thursday mornings (`0 10 * * 2,4`).
  - Restricts its query scope strictly to `is_active = TRUE` and a rolling 2-week window (`current_week - 1` and `current_week`).
  - Reconciles earnings payouts to handle Thursday Elias stat corrections.
  - Automatically transitions `is_completed = TRUE` and triggers podium payouts upon championship conclusion; becomes a no-op (<1s) during the offseason.

### 4.3 Database Dialect Parity (PostgreSQL 16 & SQLite Fallback)
- **Production:** PostgreSQL 16 on Railway / Docker.
- **Local Testing & CI:** SQLite in-memory or file-based (`sqlite:///ff_historian.db`).
- **Compatibility Invariants:**
  - SQLAlchemy `JSON` types with `with_variant(JSONB, "postgresql")`.
  - SQLite foreign key enforcement enabled via `PRAGMA foreign_keys=ON` on connection.
  - Constraint equivalence: PostgreSQL `UNIQUE NULLS NOT DISTINCT` on `earnings_ledger` mirrored in SQLite using `COALESCE(week, -1)` unique indexing.

---

## 5. Consequences & Trade-offs

- **Positive:**
  - Future features (Waiver ROI, Trade Heists, All-Play Bad Beats, Player Roster History) require zero schema migrations or ESPN backfills.
  - Complete protection against ESPN API schema deprecation via immutable `raw_espn_snapshots`.
  - Tests run in milliseconds using in-memory SQLite without requiring live network or Docker daemons.
  - High availability: The Flask API is strictly read-only and decoupled from ingestion failures.
- **Negative / Considerations:**
  - Initial ingestion of 10+ years of history takes several minutes due to polite rate-limiting.
  - Pre-2018 seasons require defensive fallback handling for missing box score and transaction payloads (`has_transaction_data = FALSE`).
