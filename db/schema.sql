-- =============================================================================
-- Fantasy Football League Historian — Canonical PostgreSQL 16 Schema
-- =============================================================================
-- Invariant: Dual-dialect compatibility with SQLite 3.9+ local fallback.
-- Invariant: Maximal Upfront ESPN Data Strategy (12 core tables).
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Raw ESPN Payload Archive
-- Keyed by (season_year, view_name, scoring_period) for zero-network re-parsing.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw_espn_snapshots (
    id SERIAL PRIMARY KEY,
    season_year INT NOT NULL,
    view_name VARCHAR(64) NOT NULL,
    scoring_period INT NOT NULL DEFAULT 0,
    payload JSONB NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_raw_espn_snapshots_season_view_period UNIQUE (season_year, view_name, scoring_period)
);

COMMENT ON TABLE raw_espn_snapshots IS 'Immutable raw JSON responses from ESPN Fantasy API views for zero-network backfills.';
COMMENT ON COLUMN raw_espn_snapshots.scoring_period IS 'ESPN scoring period (0 for league-level views, 1-18 for weekly views).';

-- -----------------------------------------------------------------------------
-- 2. Seasons & League Rules
-- League-level settings, financial payout parameters, and capability flags.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS seasons (
    season_year INT PRIMARY KEY,
    league_id VARCHAR(64) NOT NULL,
    league_name VARCHAR(128) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    is_completed BOOLEAN NOT NULL DEFAULT FALSE,
    regular_season_weeks INT NOT NULL DEFAULT 14,
    current_week INT NOT NULL DEFAULT 1,
    playoff_team_count INT NOT NULL DEFAULT 6,
    playoff_matchup_length INT NOT NULL DEFAULT 1,
    scoring_type VARCHAR(32) NOT NULL DEFAULT 'PPR',
    scoring_settings JSONB NOT NULL DEFAULT '{}',
    roster_slots JSONB NOT NULL DEFAULT '{}',
    faab_budget INT NOT NULL DEFAULT 100,
    weekly_win_payout NUMERIC(10,2) NOT NULL DEFAULT 10.00,
    weekly_high_score_payout NUMERIC(10,2) NOT NULL DEFAULT 10.00,
    weekly_high_score_loss_payout NUMERIC(10,2) NOT NULL DEFAULT 10.00,
    champion_payout NUMERIC(10,2) NOT NULL DEFAULT 500.00,
    runner_up_payout NUMERIC(10,2) NOT NULL DEFAULT 300.00,
    third_place_payout NUMERIC(10,2) NOT NULL DEFAULT 200.00,
    fourth_place_payout NUMERIC(10,2) NOT NULL DEFAULT 150.00,
    fifth_place_payout NUMERIC(10,2) NOT NULL DEFAULT 100.00,
    regular_season_most_points_payout NUMERIC(10,2) NOT NULL DEFAULT 30.00,
    has_transaction_data BOOLEAN NOT NULL DEFAULT TRUE,
    has_boxscore_data BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE seasons IS 'Annual league configuration, scoring rules, and payout policies.';
COMMENT ON COLUMN seasons.has_transaction_data IS 'False for pre-2018 seasons where ESPN purged transaction history.';

-- -----------------------------------------------------------------------------
-- 3. Canonical Human Managers
-- Persistent manager identity across years, name changes, and account transitions.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS managers (
    id SERIAL PRIMARY KEY,
    espn_member_id VARCHAR(128) UNIQUE NOT NULL,
    display_name VARCHAR(128) NOT NULL,
    avatar_url TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE managers IS 'Canonical human managers participating in the league across seasons.';
COMMENT ON COLUMN managers.espn_member_id IS 'ESPN member GUID string (e.g. {UUID}).';

-- -----------------------------------------------------------------------------
-- 4. Annual Franchise Teams
-- Annual team instances linking managers to standings, records, and statistics.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS teams (
    id SERIAL PRIMARY KEY,
    season_year INT NOT NULL REFERENCES seasons(season_year) ON DELETE CASCADE,
    espn_team_id INT NOT NULL,
    team_name VARCHAR(128) NOT NULL,
    team_abbrev VARCHAR(32),
    logo_url TEXT,
    manager_id INT NOT NULL REFERENCES managers(id),
    co_manager_id INT REFERENCES managers(id),
    raw_owner_guids JSONB NOT NULL DEFAULT '[]',
    division_id INT,
    division_name VARCHAR(64),
    wins INT NOT NULL DEFAULT 0,
    losses INT NOT NULL DEFAULT 0,
    ties INT NOT NULL DEFAULT 0,
    home_wins INT NOT NULL DEFAULT 0,
    home_losses INT NOT NULL DEFAULT 0,
    home_ties INT NOT NULL DEFAULT 0,
    away_wins INT NOT NULL DEFAULT 0,
    away_losses INT NOT NULL DEFAULT 0,
    away_ties INT NOT NULL DEFAULT 0,
    division_wins INT NOT NULL DEFAULT 0,
    division_losses INT NOT NULL DEFAULT 0,
    division_ties INT NOT NULL DEFAULT 0,
    points_for NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    points_against NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    streak_type VARCHAR(16),
    streak_length INT NOT NULL DEFAULT 0,
    playoff_seed INT,
    final_standing INT,
    faab_remaining INT NOT NULL DEFAULT 100,
    waiver_rank INT,
    acquisitions INT NOT NULL DEFAULT 0,
    drops INT NOT NULL DEFAULT 0,
    trades INT NOT NULL DEFAULT 0,
    ir_moves INT NOT NULL DEFAULT 0,
    CONSTRAINT uq_teams_season_espn_team UNIQUE (season_year, espn_team_id)
);

CREATE INDEX IF NOT EXISTS idx_teams_season_year ON teams(season_year);
CREATE INDEX IF NOT EXISTS idx_teams_manager_id ON teams(manager_id);
CREATE INDEX IF NOT EXISTS idx_teams_co_manager_id ON teams(co_manager_id);

COMMENT ON TABLE teams IS 'Seasonal franchise instances linking managers to yearly performance.';

-- -----------------------------------------------------------------------------
-- 5. Canonical NFL Players
-- Master player registry referenced across lineups, waivers, and trades.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS players (
    espn_player_id INT PRIMARY KEY,
    full_name VARCHAR(128) NOT NULL,
    default_position VARCHAR(16) NOT NULL,
    pro_team VARCHAR(16) NOT NULL DEFAULT 'FA',
    headshot_url TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_players_position ON players(default_position);
CREATE INDEX IF NOT EXISTS idx_players_pro_team ON players(pro_team);

COMMENT ON TABLE players IS 'Canonical registry of NFL players appearing on rosters, lineups, or transactions.';

-- -----------------------------------------------------------------------------
-- 6. Matchups & Weekly Team Scores
-- Regular season, playoff, consolation, and bye matchups with Max PF & bench stats.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS matchups (
    id SERIAL PRIMARY KEY,
    season_year INT NOT NULL REFERENCES seasons(season_year) ON DELETE CASCADE,
    week INT NOT NULL,
    espn_matchup_id INT NOT NULL,
    matchup_type VARCHAR(32) NOT NULL DEFAULT 'REGULAR',
    home_team_id INT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    away_team_id INT REFERENCES teams(id) ON DELETE CASCADE,
    home_score NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    away_score NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    home_projected NUMERIC(10,2),
    away_projected NUMERIC(10,2),
    home_optimal_score NUMERIC(10,2),
    away_optimal_score NUMERIC(10,2),
    home_bench_points NUMERIC(10,2),
    away_bench_points NUMERIC(10,2),
    winner_team_id INT REFERENCES teams(id) ON DELETE SET NULL,
    is_tie BOOLEAN NOT NULL DEFAULT FALSE,
    is_completed BOOLEAN NOT NULL DEFAULT FALSE,
    points_by_scoring_period JSONB NOT NULL DEFAULT '{}',
    CONSTRAINT uq_matchups_season_week_espn_matchup UNIQUE (season_year, week, espn_matchup_id)
);

CREATE INDEX IF NOT EXISTS idx_matchups_season_week ON matchups(season_year, week);
CREATE INDEX IF NOT EXISTS idx_matchups_home_team ON matchups(home_team_id);
CREATE INDEX IF NOT EXISTS idx_matchups_away_team ON matchups(away_team_id);
CREATE INDEX IF NOT EXISTS idx_matchups_matchup_type ON matchups(matchup_type);

COMMENT ON TABLE matchups IS 'Weekly games with optimal scores (Max PF), bench points, and bye support.';
COMMENT ON COLUMN matchups.away_team_id IS 'Nullable to support first-round playoff bye weeks.';

-- -----------------------------------------------------------------------------
-- 7. Weekly Lineups & Player Performance
-- Granular starter/bench boxscore records enabling Trade Autopsies & Coaching ROI.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS weekly_lineups (
    id SERIAL PRIMARY KEY,
    season_year INT NOT NULL REFERENCES seasons(season_year) ON DELETE CASCADE,
    week INT NOT NULL,
    team_id INT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    player_id INT NOT NULL REFERENCES players(espn_player_id),
    slot_position VARCHAR(16) NOT NULL,
    is_starter BOOLEAN NOT NULL DEFAULT FALSE,
    actual_points NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    projected_points NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    acquisition_type VARCHAR(32),
    weekly_stats JSONB NOT NULL DEFAULT '{}',
    CONSTRAINT uq_weekly_lineups_season_week_team_player UNIQUE (season_year, week, team_id, player_id)
);

CREATE INDEX IF NOT EXISTS idx_weekly_lineups_team_week ON weekly_lineups(team_id, week);
CREATE INDEX IF NOT EXISTS idx_weekly_lineups_player ON weekly_lineups(player_id);
CREATE INDEX IF NOT EXISTS idx_weekly_lineups_season_week ON weekly_lineups(season_year, week);

COMMENT ON TABLE weekly_lineups IS 'Weekly player-level start/bench decisions with projected and actual points.';

-- -----------------------------------------------------------------------------
-- 8. Transactions Ledger (Waivers, FAAB Bids & Free Agents)
-- Full transaction history capturing executed and failed waiver bids for Bidding Wars.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    season_year INT NOT NULL REFERENCES seasons(season_year) ON DELETE CASCADE,
    week INT,
    scoring_period INT NOT NULL DEFAULT 0,
    espn_transaction_id VARCHAR(128) NOT NULL,
    transaction_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    team_id INT REFERENCES teams(id) ON DELETE SET NULL,
    bid_amount INT NOT NULL DEFAULT 0,
    waiver_priority INT,
    failure_reason VARCHAR(64),
    proposed_at TIMESTAMPTZ,
    executed_at TIMESTAMPTZ,
    is_commissioner_override BOOLEAN NOT NULL DEFAULT FALSE,
    related_espn_transaction_id VARCHAR(128),
    raw_summary JSONB NOT NULL DEFAULT '{}',
    CONSTRAINT uq_transactions_season_espn_tx UNIQUE (season_year, espn_transaction_id)
);

CREATE INDEX IF NOT EXISTS idx_transactions_season_week ON transactions(season_year, week);
CREATE INDEX IF NOT EXISTS idx_transactions_team ON transactions(team_id);
CREATE INDEX IF NOT EXISTS idx_transactions_related_id ON transactions(related_espn_transaction_id);
CREATE INDEX IF NOT EXISTS idx_transactions_type_status ON transactions(transaction_type, status);

COMMENT ON TABLE transactions IS 'Transaction ledger including executed waivers and failed outbid attempts.';
COMMENT ON COLUMN transactions.related_espn_transaction_id IS 'Links losing waiver bids to winning claim for FAAB Bidding War receipts.';

-- -----------------------------------------------------------------------------
-- 9. Transaction Items (Normalized Player Movement)
-- Individual player movements attached to transactions.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transaction_items (
    id SERIAL PRIMARY KEY,
    transaction_id INT NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    player_id INT NOT NULL REFERENCES players(espn_player_id),
    from_team_id INT REFERENCES teams(id) ON DELETE SET NULL,
    to_team_id INT REFERENCES teams(id) ON DELETE SET NULL,
    item_type VARCHAR(32) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transaction_items_tx_id ON transaction_items(transaction_id);
CREATE INDEX IF NOT EXISTS idx_transaction_items_player ON transaction_items(player_id);
CREATE INDEX IF NOT EXISTS idx_transaction_items_from_team ON transaction_items(from_team_id);
CREATE INDEX IF NOT EXISTS idx_transaction_items_to_team ON transaction_items(to_team_id);

COMMENT ON TABLE transaction_items IS 'Normalized player transfer items per transaction (adds, drops, trades).';

-- -----------------------------------------------------------------------------
-- 10. Trades (Two-Team Franchise Exchanges)
-- Dedicated trade agreements with FAAB transfers for Trade Autopsies & Networks.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    season_year INT NOT NULL REFERENCES seasons(season_year) ON DELETE CASCADE,
    week INT,
    espn_transaction_id VARCHAR(128) NOT NULL,
    proposing_team_id INT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    accepting_team_id INT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    status VARCHAR(32) NOT NULL DEFAULT 'EXECUTED',
    proposed_at TIMESTAMPTZ,
    executed_at TIMESTAMPTZ,
    faab_from_proposer INT NOT NULL DEFAULT 0,
    faab_from_accepter INT NOT NULL DEFAULT 0,
    trade_summary JSONB NOT NULL DEFAULT '{}',
    CONSTRAINT uq_trades_season_espn_tx UNIQUE (season_year, espn_transaction_id)
);

CREATE INDEX IF NOT EXISTS idx_trades_season_year ON trades(season_year);
CREATE INDEX IF NOT EXISTS idx_trades_proposing_team ON trades(proposing_team_id);
CREATE INDEX IF NOT EXISTS idx_trades_accepting_team ON trades(accepting_team_id);

COMMENT ON TABLE trades IS 'Bilateral trade agreements tracking assets and FAAB transferred.';

-- -----------------------------------------------------------------------------
-- 11. Financial Earnings Ledger
-- Reconciled payouts for regular season weekly wins ($10), ties ($5), and podiums.
-- PostgreSQL 15+ UNIQUE NULLS NOT DISTINCT ensures at most one podium payout per entry type.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS earnings_ledger (
    id SERIAL PRIMARY KEY,
    manager_id INT NOT NULL REFERENCES managers(id) ON DELETE CASCADE,
    team_id INT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    season_year INT NOT NULL REFERENCES seasons(season_year) ON DELETE CASCADE,
    week INT,
    entry_type VARCHAR(32) NOT NULL,
    amount NUMERIC(10,2) NOT NULL,
    description VARCHAR(255),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_earnings_entry UNIQUE NULLS NOT DISTINCT (manager_id, season_year, week, entry_type)
);

CREATE INDEX IF NOT EXISTS idx_earnings_manager_season ON earnings_ledger(manager_id, season_year);
CREATE INDEX IF NOT EXISTS idx_earnings_entry_type ON earnings_ledger(entry_type);

-- Enforce at most one weekly win/tie payout per manager per week in a season
CREATE UNIQUE INDEX IF NOT EXISTS uq_earnings_weekly_single
    ON earnings_ledger (manager_id, season_year, week)
    WHERE entry_type IN ('WEEKLY_WIN', 'WEEKLY_TIE');

COMMENT ON TABLE earnings_ledger IS 'Financial ledger tracking weekly win/tie/high score prizes, regular season most points, and playoff placement awards.';
COMMENT ON COLUMN earnings_ledger.week IS 'Null for season-level awards (podiums, placements, regular season most points).';

-- -----------------------------------------------------------------------------
-- 12. Sync Runs Audit Log
-- Ingestion audit trail recording backfill runs, cron syncs, counts, and errors.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sync_runs (
    id SERIAL PRIMARY KEY,
    run_type VARCHAR(32) NOT NULL,
    season_year INT,
    week_range VARCHAR(32),
    status VARCHAR(32) NOT NULL,
    records_processed INT NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_sync_runs_status ON sync_runs(status);
CREATE INDEX IF NOT EXISTS idx_sync_runs_started_at ON sync_runs(started_at);

COMMENT ON TABLE sync_runs IS 'Ingestion audit log tracking run types, affected windows, and outcome status.';
