# db/AGENTS.md — Database Architecture & SQL Invariants

> **Scope:** This guide governs the database schema (`db/schema.sql`), SQLAlchemy models (`backend/models/`), seed data generation (`db/seed_dev.py`), and SQL query rules for derived metrics.

---

## 1. Schema Invariants (`db/schema.sql`)

The database schema supports eight primary data domains with strict referential integrity:

1. **`raw_espn_snapshots`**: Immutable raw JSON payloads keyed by `(season_year, view_name, scoring_period)`. Enables zero-network re-parsing via `backfill_history.py --from-snapshots`.
2. **`seasons`**: Season settings (`regular_season_weeks`, `playoff_team_count`, `scoring_type`, `scoring_settings`, `roster_slots`, `faab_budget`, `is_active`, `is_completed`, `has_transaction_data`, `has_boxscore_data`).
3. **`managers`**: Canonical human managers with `espn_member_id` (GUID) and `display_name`.
4. **`teams`**: Annual franchise instances linking `manager_id`, optional `co_manager_id`, `season_year`, team name, divisional and overall records, PF, PA, streaks, seeds, final standings, and FAAB balances.
5. **`players`**: Canonical NFL player registry (`espn_player_id`, `full_name`, `default_position`, `pro_team`, `headshot_url`).
6. **`matchups`**: Weekly games with `matchup_type` (`REGULAR`, `WINNERS_BRACKET`, `WINNERS_CONSOLATION_LADDER`, `LOSERS_CONSOLATION_LADDER`, `BYE`), actual scores, projected scores, optimal lineup scores (Max PF), and bench points.
7. **`weekly_lineups`**: Weekly player-level start/bench entries (`slot_position`, `is_starter`, `actual_points`, `projected_points`, `weekly_stats`).
8. **`transactions` & `transaction_items` & `trades`**: Complete transaction ledger capturing free agents, executed waivers, failed waiver bids (`WAIVER_ERROR`) with `failure_reason`, and `related_espn_transaction_id` for FAAB Bidding Wars.
9. **`earnings_ledger`**: Financial payouts ($10 weekly win, $5 tie, 1st/2nd/3rd podium awards).
10. **`sync_runs`**: Audit log recording ingestion runs (`run_type` = `'BACKFILL'` | `'WEEKLY_CRON'`, `season_year`, `week_range`, `status`, `started_at`, `completed_at`, `error_message`).

---

## 2. Dialect Compatibility (PostgreSQL 16 & SQLite Fallback)

To ensure agents can run 100% offline verification using in-memory or file-based SQLite while maintaining production parity with PostgreSQL 16:

### 2.1 JSON / JSONB Compatibility
- In SQLAlchemy models, use `JSON` with dialect-specific compilation:
  ```python
  from sqlalchemy import JSON
  from sqlalchemy.dialects.postgresql import JSONB

  JsonType = JSON().with_variant(JSONB, "postgresql")
  ```
- Do not use Postgres-specific operators like `?&` or `->>` in raw queries unless wrapped in dialect-agnostic SQLAlchemy abstractions.

### 2.2 SQLite Foreign Key Enforcement
- SQLite disables foreign keys by default. `backend/database.py` must register an `engine_connect` hook:
  ```python
  from sqlalchemy import event
  from sqlalchemy.engine import Engine

  @event.listens_for(Engine, "connect")
  def set_sqlite_pragma(dbapi_connection, connection_record):
      if dbapi_connection.__class__.__module__.startswith("sqlite3"):
          cursor = dbapi_connection.cursor()
          cursor.execute("PRAGMA foreign_keys=ON")
          cursor.close()
  ```

### 2.3 `NULL` Uniqueness on `earnings_ledger`
- In PostgreSQL 15+:
  ```sql
  CONSTRAINT uq_earnings_entry UNIQUE NULLS NOT DISTINCT (manager_id, season_year, week, entry_type)
  ```
- In SQLite, `NULL != NULL` allows duplicate entries when `week IS NULL` (podium payouts). To maintain dialect compatibility in SQLAlchemy models and migrations, create a unique partial index or use a coalesced index:
  ```sql
  CREATE UNIQUE INDEX uq_earnings_ledger_coalesce ON earnings_ledger (
      manager_id,
      season_year,
      COALESCE(week, -1),
      entry_type
  );
  ```

---

## 3. Manager Overrides (`db/manager_overrides.json`)

ESPN accounts change, and early seasons may lack member GUIDs. Ingestion jobs must check `db/manager_overrides.json` before resolving manager identities:

```json
{
  "_comment": "Declarative manager identity overrides",
  "overrides": [
    {
      "source_espn_member_id": "{OLD-GUID-OR-NAME}",
      "target_manager_id": 1,
      "target_display_name": "Official Manager Name",
      "notes": "Merged 2017 historical account"
    }
  ]
}
```

Rules:
1. Exact match on `espn_member_id` takes precedence.
2. If `espn_member_id` is empty (pre-2018), match by normalized team owner name.
3. If an override specifies `target_manager_id`, attach the season franchise to that manager.

---

## 4. SQL Rules for Derived Metrics

### 4.1 All-Play Record
- **Definition:** For every week in a season, each team is compared against every other active team playing in that same week (excluding byes).
- **Rule:**
  - If Team A score > Team B score: +1 All-Play Win.
  - If Team A score < Team B score: +1 All-Play Loss.
  - If Team A score = Team B score: +1 All-Play Tie.
- **SQL Logic:** Cross join matchups in the same `(season_year, week)` where `matchup_type = 'REGULAR'` and both teams are non-null.

### 4.2 Weekly Median Record
- **Definition:** For each regular season week, compute the median score among all teams playing that week.
- **Rule:**
  - Team score > Median: +1 Median Win.
  - Team score < Median: +1 Median Loss.
  - Team score = Median: +1 Median Tie.
- **Luck Index Formula:**
  $$\text{Luck Index} = \text{Actual Win Pct} - \text{All-Play Win Pct}$$
  (Positive indicates good schedule luck / easier opponents; negative indicates bad schedule luck / tough opponents).

### 4.3 Head-to-Head Series Rules
- **Matchup Filtering:** Only include matchups where:
  `matchup_type IN ('REGULAR', 'WINNERS_BRACKET')`
- **Exclusion:** Explicitly exclude `WINNERS_CONSOLATION_LADDER`, `LOSERS_CONSOLATION_LADDER`, and `BYE` from career H2H counts.
- **Pairwise Ordering:** Always query manager pairs with `manager_a_id < manager_b_id` for matrix consistency, but support bi-directional lookups in the 1-on-1 comparator.

### 4.4 Trade Post-Acquisition Starter Points
- **Definition:** Realized value of a trade equals the actual starter fantasy points scored by acquired players *after* the trade was executed.
- **Rule:** Join `weekly_lineups` on `player_id` where:
  - `weekly_lineups.team_id = trade_side.team_id`
  - `weekly_lineups.season_year = trades.season_year`
  - `weekly_lineups.week > trades.week`
  - `weekly_lineups.is_starter = TRUE`

---

## 5. Seed Harness (`db/seed_dev.py`)

- Must run deterministically with `python3 -m db.seed_dev`.
- Generates 3 full seasons:
  - 1 completed historical season without transactions (legacy era).
  - 1 completed modern season with full box scores, FAAB bidding wars, and trades.
  - 1 active/in-progress season with mid-season standings and pending payouts.
- Verifies idempotency: re-running `make seed` clears or updates without violating constraints or generating duplicate payouts.
