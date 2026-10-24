# Canonical REST API Contract Specification

> **Single Source of Truth:** This document defines the canonical TypeScript interfaces and JSON payload schemas for all `/api/v1/*` endpoints. Backend services (`backend/services/`, `backend/routes/`) and Frontend clients (`frontend/src/types/api.ts`, `frontend/src/api/client.ts`) MUST adhere to these exact structures.

---

## TypeScript Definitions (`frontend/src/types/api.ts`)

```typescript
// ==========================================
// 1. Health & Meta
// ==========================================

export interface HealthResponse {
  status: "ok" | "degraded" | "error";
  database: "connected" | "disconnected";
  timestamp: string; // ISO 8601
}

export interface SeasonMeta {
  season_year: number;
  is_active: boolean;
  is_completed: boolean;
  regular_season_weeks: number;
  current_week: number;
  has_transaction_data: boolean;
  has_boxscore_data: boolean;
}

export interface ManagerMeta {
  id: number;
  espn_member_id: string;
  display_name: string;
  avatar_url: string | null;
  is_active: boolean;
}

export interface SyncStatus {
  last_backfill_at: string | null;
  last_weekly_sync_at: string | null;
  last_sync_status: string | null;
}

export interface MetaResponse {
  league_name: string;
  current_season: number | null;
  available_seasons: SeasonMeta[];
  managers: ManagerMeta[];
  last_sync: SyncStatus;
}

// ==========================================
// 2. Earnings Leaderboard
// ==========================================

export type TrophyType = "CHAMPION" | "RUNNER_UP" | "THIRD_PLACE" | null;

export interface ManagerBountyReceipt {
  week: number;
  entry_type: string;
  amount: number;
  points: number;
  description: string;
}

export interface ManagerSeasonBreakdown {
  season_year: number;
  team_name: string;
  logo_url: string | null;
  weekly_earnings: number;
  podium_earnings: number;
  points_title_cash: number;
  total_earnings: number;
  weekly_wins: number;
  weekly_ties: number;
  weekly_wins_cash: number;
  weekly_bonus_cash: number;
  weekly_high_scores: number;
  weekly_high_score_losses: number;
  bounty_receipts: ManagerBountyReceipt[];
  final_standing: number | null;
  trophy: TrophyType;
}

export interface EarningsLeaderboardEntry {
  manager_id: number;
  display_name: string;
  team_name: string;
  avatar_url: string | null;
  total_earnings: number;
  weekly_earnings: number;
  podium_earnings: number;
  points_title_cash: number;
  weekly_wins_count: number;
  weekly_ties_count: number;
  weekly_wins_cash: number;
  weekly_bonus_cash: number;
  weekly_high_scores_count: number;
  weekly_high_score_losses_count: number;
  bounty_receipts: ManagerBountyReceipt[];
  championships: number;
  championship_years: number[];
  is_defending_champion: boolean;
  runner_ups: number;
  third_places: number;
  seasons_played: number;
  season_breakdown: ManagerSeasonBreakdown[];
}

export interface WeeklyNuancedPayoutEntry {
  week: number;
  high_score_team_name: string;
  high_score_manager_name: string;
  high_score_avatar_url: string | null;
  high_score_points: number;
  high_score_amount: number;
  high_score_is_tie: boolean;
  high_loser_team_name: string;
  high_loser_manager_name: string;
  high_loser_avatar_url: string | null;
  high_loser_points: number;
  high_loser_amount: number;
  high_loser_is_tie: boolean;
}

export interface RegularSeasonPointsWinner {
  manager_id: number;
  manager_name: string;
  team_id: number;
  team_name: string;
  avatar_url: string | null;
  points: number;
  amount: number;
  is_tie: boolean;
  description: string;
}

export interface EarningsLeaderboardResponse {
  season_filter: number | null;
  weekly_win_value: number;
  leaderboard: EarningsLeaderboardEntry[];
  weekly_nuanced_payouts: WeeklyNuancedPayoutEntry[];
  regular_season_points_winner: RegularSeasonPointsWinner | null;
}

// ==========================================
// 3. Standings & Performance
// ==========================================

export interface WeeklyStandingPoint {
  week: number;
  standings_rank: number;
  power_rank: number;
  wins: number;
  losses: number;
  ties: number;
  points_for: number;
  weekly_score: number;
  all_play_wins: number;
  all_play_losses: number;
  all_play_ties: number;
  all_play_win_pct: number;
  opponent_team_id: number | null;
  opponent_team_name: string | null;
  opponent_team_abbrev: string | null;
  opponent_logo_url: string | null;
  opponent_manager_name: string | null;
  opponent_score: number | null;
  result: "WIN" | "LOSS" | "TIE" | "BYE" | null;
  is_home: boolean | null;
}

export interface StandingEntry {
  rank: number;
  power_rank: number;
  team_id: number;
  team_name: string;
  team_abbrev: string | null;
  logo_url: string | null;
  manager_id: number;
  manager_name: string;
  co_manager_name: string | null;
  is_active: boolean;
  wins: number;
  losses: number;
  ties: number;
  points_for: number;
  points_against: number;
  streak_type: string | null;
  streak_length: number;
  playoff_seed: number | null;
  final_standing: number | null;
  all_play_wins: number;
  all_play_losses: number;
  all_play_ties: number;
  all_play_win_pct: number;
  median_wins: number;
  median_losses: number;
  median_ties: number;
  luck_index: number;
  optimal_points_for: number;
  bench_points: number;
  lineup_efficiency: number;
  weekly_earnings: number;
  podium_earnings: number;
  total_earnings: number;
  faab_remaining: number;
  championships: number;
  championship_years: number[];
  runner_ups: number;
  runner_up_years: number[];
  third_places: number;
  third_place_years: number[];
  scoring_champs: number;
  scoring_champ_years: number[];
  is_defending_champion: boolean;
  weekly_history: WeeklyStandingPoint[];
}

export interface BracketTeamRef {
  team_id: number;
  team_name: string;
  team_abbrev: string | null;
  logo_url: string | null;
  manager_id: number;
  manager_name: string;
  playoff_seed: number | null;
  final_standing: number | null;
}

export interface PlayoffMatchupItem {
  id: number;
  week: number;
  matchup_type: string;
  round_label: string;
  home_team: BracketTeamRef;
  away_team: BracketTeamRef | null;
  home_score: number;
  away_score: number;
  winner_team_id: number | null;
  is_completed: boolean;
  is_bye: boolean;
}

export interface PlayoffRound {
  week: number;
  round_label: string;
  winners_bracket: PlayoffMatchupItem[];
  consolation: PlayoffMatchupItem[];
}

export interface PlayoffBracket {
  season_year: number;
  is_available: boolean;
  championship_round_week: number;
  rounds: PlayoffRound[];
  champion: BracketTeamRef | null;
  runner_up: BracketTeamRef | null;
  third_place: BracketTeamRef | null;
}

export interface StandingsResponse {
  season_year: number | null;
  is_active: boolean;
  is_completed: boolean;
  current_week: number;
  regular_season_weeks: number;
  playoff_team_count: number;
  defending_champion_manager_id: number | null;
  defending_champion_team_id: number | null;
  playoff_bracket: PlayoffBracket | null;
  standings: StandingEntry[];
}

// ==========================================
// 4. Hall of Fame & Legends
// ==========================================

export interface HallOfFameBanner {
  season_year: number;
  team_id: number;
  team_name: string;
  team_abbrev: string;
  logo_url: string | null;
  manager_id: number;
  manager_name: string;
  avatar_url: string | null;
  co_manager_id: number | null;
  co_manager_name: string | null;
  wins: number;
  losses: number;
  ties: number;
  points_for: number;
  points_against: number;
  regular_season_finish: string;
  championship_score: number;
  runner_up_team_id: number | null;
  runner_up_team_name: string;
  runner_up_manager_name: string | null;
  runner_up_score: number;
  margin_of_victory: number;
  total_earnings: number;
  payout_amount: number;
}

export interface ChampionshipMatchupDetail {
  week: number;
  matchup_id: number | null;
  winning_score: number;
  runner_up_team_id: number | null;
  runner_up_team_name: string;
  runner_up_manager_name: string | null;
  runner_up_logo_url: string | null;
  runner_up_score: number;
  margin_of_victory: number;
}

export interface HallOfFameHeroPlayer {
  rank: number;
  player_id: number;
  full_name: string;
  default_position: string;
  pro_team: string;
  headshot_url: string | null;
  slot_position: string;
  fantasy_points: number;
  projected_points: number;
  stats_summary: string;
  role_title: string;
  pct_of_team_points: number;
}

export interface FeaturedChampion {
  season_year: number;
  team_id: number;
  team_name: string;
  team_abbrev: string;
  logo_url: string | null;
  manager_id: number;
  manager_name: string;
  avatar_url: string | null;
  co_manager_id: number | null;
  co_manager_name: string | null;
  regular_season_finish: string;
  hall_of_fame_number: number;
  record: string;
  total_earnings: number;
  championship_matchup: ChampionshipMatchupDetail;
  top_players: HallOfFameHeroPlayer[];
}

export interface HallOfFameResponse {
  reigning_champion_year: number;
  selected_season: number;
  available_seasons: number[];
  banners: HallOfFameBanner[];
  featured_champion: FeaturedChampion | null;
}

// ==========================================
// 5. Trades & Realized Value
// ==========================================

export interface TradeTimelineEvent {
  week: number;
  player_id: number;
  player_name: string;
  team_id: number;
  team_name: string;
  event_type: "INJURY_IR" | "INJURY_OUT" | "BIG_GAME" | "BENCH_BOOM" | "FLIPPED" | "TRADE_EXECUTED";
  severity: "info" | "warning" | "danger" | "success";
  title: string;
  description: string;
}

export interface TradeWeeklyTrajectoryPoint {
  week: number;
  side_a_starter_points: number;
  side_a_bench_points: number;
  side_a_depth_points: number;
  side_a_cumulative_starter_points: number;
  side_a_cumulative_total_points: number;
  side_a_cumulative_score: number;
  side_b_starter_points: number;
  side_b_bench_points: number;
  side_b_depth_points: number;
  side_b_cumulative_starter_points: number;
  side_b_cumulative_total_points: number;
  side_b_cumulative_score: number;
  cumulative_score_differential: number;
  leading_team_id: number | null;
  events: TradeTimelineEvent[];
}

export interface TradeAssetWeeklyPoint {
  week: number;
  points: number;
  is_starter: boolean;
  slot_position: string;
  on_acquiring_team: boolean;
  injury_status: string | null;
  is_injured: boolean;
}

export interface TradePlayerAsset {
  player_id: number;
  full_name: string;
  default_position: string;
  pro_team: string;
  headshot_url: string | null;
  asset_type: "PLAYER" | "PICK";
  post_trade_starter_points: number;
  post_trade_weeks_started: number;
  post_trade_total_points: number;
  post_trade_bench_points: number;
  post_trade_weeks_played: number;
  roster_depth_points: number;
  pre_trade_points: number;
  pre_trade_ppg: number;
  season_total_points: number;
  season_ppg: number;
  positional_rank: number | null;
  tier_label: string | null;
  vorp_per_game: number;
  pick_round: number | null;
  pick_number: number | null;
  pick_round_value: number;
  drafted_player_id: number | null;
  drafted_player_name: string | null;
  drafted_player_position: string | null;
  drafted_player_headshot_url: string | null;
  drafted_player_points: number;
  trade_score: number;
  weekly_breakdown: TradeAssetWeeklyPoint[];
}

export interface TradeSide {
  team_id: number;
  team_name: string;
  logo_url: string | null;
  manager_id: number;
  manager_name: string;
  assets_received: TradePlayerAsset[];
  faab_received: number;
  faab_value: number;
  total_starter_points_gained: number;
  total_ros_points_gained: number;
  total_roster_depth_points_gained: number;
  slot_equalization_points: number;
  total_pick_value_gained: number;
  total_trade_score: number;
  grade: string;
}

export interface TradeDetail {
  trade_id: number;
  season_year: number;
  week: number | null;
  executed_at: string | null;
  espn_transaction_id: string;
  sides: TradeSide[];
  winner_manager_id: number | null;
  point_differential: number;
  score_differential: number;
  verdict_label: string;
  is_projected: boolean;
  weekly_trajectory: TradeWeeklyTrajectoryPoint[];
  timeline_events: TradeTimelineEvent[];
}

export interface TopTradePartner {
  manager_a_id: number;
  manager_a_name: string;
  manager_a_team_name: string;
  manager_a_avatar_url: string | null;
  manager_b_id: number;
  manager_b_name: string;
  manager_b_team_name: string;
  manager_b_avatar_url: string | null;
  trade_count: number;
  total_assets_exchanged: number;
  total_trade_score_volume: number;
  net_winner_manager_id: number | null;
  net_score_differential: number;
}

export interface ActiveTrader {
  manager_id: number;
  display_name: string;
  team_name: string;
  avatar_url: string | null;
  is_active?: boolean;
  total_trades: number;
  trades_won: number;
  trades_lost: number;
  trades_tied: number;
  win_rate: number;
  players_acquired: number;
  players_traded_away: number;
  picks_acquired: number;
  picks_traded_away: number;
  faab_net: number;
  net_starter_points_gained: number;
  net_ros_points_gained: number;
  net_roster_depth_points_gained: number;
  net_trade_score_gained: number;
  average_grade: string;
  executed_waivers: number;
  free_agent_adds: number;
}

export interface TradesTrendsResponse {
  season_filter: number | null;
  has_transaction_data: boolean;
  top_partners: TopTradePartner[];
  active_traders: ActiveTrader[];
  trades: TradeDetail[];
}

// ==========================================
// 6. Transactions & FAAB Bidding Wars
// ==========================================

export interface ManagerEfficiency {
  manager_id: number;
  display_name: string;
  team_name: string;
  logo_url: string | null;
  faab_budget: number;
  faab_spent: number;
  faab_remaining: number;
  executed_waivers: number;
  failed_waivers: number;
  waiver_success_rate: number;
  free_agent_adds: number;
  drops: number;
  total_starter_points_from_waivers: number;
  points_per_faab_dollar: number | null;
}

export interface FailureReasonCount {
  reason: string;
  count: number;
}

export interface TransactionPlayerRef {
  player_id: number;
  full_name: string;
  default_position: string;
  pro_team: string;
  headshot_url: string | null;
}

export interface WinningBidder {
  team_id: number;
  team_name: string;
  logo_url: string | null;
  manager_id: number;
  manager_name: string;
  bid_amount: number;
  post_claim_starter_points: number;
}

export interface LosingBid {
  transaction_id: number;
  team_id: number;
  team_name: string;
  logo_url: string | null;
  manager_id: number;
  manager_name: string;
  bid_amount: number;
  failure_reason: string;
  waiver_priority: number | null;
}

export interface BiddingWar {
  winning_transaction_id: number;
  espn_transaction_id: string;
  season_year: number;
  week: number | null;
  executed_at: string | null;
  player: TransactionPlayerRef;
  winner: WinningBidder;
  losing_bids: LosingBid[];
}

export interface TransactionItem {
  player_id: number;
  full_name: string;
  default_position: string;
  pro_team: string;
  headshot_url: string | null;
  item_type: "ADD" | "DROP" | "TRADE";
  from_team_id?: number | null;
  to_team_id?: number | null;
  from_team_name?: string | null;
  to_team_name?: string | null;
  from_manager_id?: number | null;
  to_manager_id?: number | null;
  from_manager_name?: string | null;
  to_manager_name?: string | null;
}

export interface TransactionAuditItem {
  transaction_id: number;
  espn_transaction_id: string;
  season_year: number;
  week: number | null;
  transaction_type: "FREE_AGENT" | "WAIVER" | "DROP" | "TRADE";
  status: "EXECUTED" | "FAILED" | "CANCELED" | "VETOED";
  team_id: number | null;
  team_name: string | null;
  logo_url: string | null;
  manager_id: number | null;
  manager_name: string | null;
  bid_amount: number | null;
  waiver_priority: number | null;
  failure_reason: string | null;
  executed_at: string | null;
  related_espn_transaction_id: string | null;
  items: TransactionItem[];
}

export interface TransactionsSummaryResponse {
  season_year: number;
  has_transaction_data: boolean;
  manager_efficiency: ManagerEfficiency[];
  failure_reasons: FailureReasonCount[];
  bidding_wars: BiddingWar[];
  transactions: TransactionAuditItem[];
}
```

---

## REST Endpoints Specification

### 1. `GET /api/v1/health`
Checks backend service availability and database connectivity.
- **Parameters:** None.
- **Response Schema:** `HealthResponse`
- **Example Response:**
  ```json
  {
    "status": "ok",
    "database": "connected",
    "timestamp": "2026-10-21T00:00:00Z"
  }
  ```

---

### 2. `GET /api/v1/meta`
Returns league metadata, all available seasons, active/historical managers, and sync timestamps.
- **Parameters:** None.
- **Response Schema:** `MetaResponse`
- **Example Response:**
  ```json
  {
    "league_name": "Apex Fantasy Football League",
    "current_season": 2026,
    "available_seasons": [
      {
        "season_year": 2026,
        "is_active": true,
        "is_completed": false,
        "regular_season_weeks": 14,
        "current_week": 7,
        "has_transaction_data": true,
        "has_boxscore_data": true
      },
      {
        "season_year": 2025,
        "is_active": false,
        "is_completed": true,
        "regular_season_weeks": 14,
        "current_week": 17,
        "has_transaction_data": true,
        "has_boxscore_data": true
      }
    ],
    "managers": [
      {
        "id": 1,
        "espn_member_id": "{ABC-123}",
        "display_name": "Greg Murray",
        "is_active": true
      }
    ],
    "last_sync": {
      "last_backfill_at": "2026-09-01T12:00:00Z",
      "last_weekly_sync_at": "2026-10-20T10:00:00Z",
      "last_sync_status": "SUCCESS"
    }
  }
  ```

---

### 3. `GET /api/v1/earnings/leaderboard`
Returns all-time financial earnings or filtered by season.
- **Query Parameters:**
  - `season` (optional, integer): e.g. `?season=2025`. If omitted, returns all-time totals.
- **Response Schema:** `EarningsLeaderboardResponse`
- **Example Response:**
  ```json
  {
    "season_filter": null,
    "weekly_win_value": 10.0,
    "leaderboard": [
      {
        "rank": 1,
        "is_active": true,
        "manager_id": 1,
        "display_name": "Greg Murray",
        "total_earnings": 420.0,
        "weekly_earnings": 120.0,
        "podium_earnings": 300.0,
        "weekly_wins_count": 12,
        "weekly_ties_count": 0,
        "championships": 1,
        "runner_ups": 1,
        "third_places": 0,
        "seasons_played": 3,
        "season_breakdown": [
          {
            "season_year": 2025,
            "team_name": "Show Me the Murray",
            "weekly_earnings": 80.0,
            "podium_earnings": 300.0,
            "total_earnings": 380.0,
            "weekly_wins": 8,
            "weekly_ties": 0,
            "final_standing": 1,
            "trophy": "CHAMPION"
          }
        ]
      }
    ]
  }
  ```

---

### 4. `GET /api/v1/standings/current`
Returns regular season standings, official records, All-Play records, Median records, Schedule Luck index, and Lineup Efficiency.
- **Query Parameters:**
  - `season` (optional, integer): Defaults to current active season or latest completed season.
- **Response Schema:** `StandingsResponse`
- **Example Response:**
  ```json
  {
    "season_year": 2026,
    "is_active": true,
    "is_completed": false,
    "current_week": 7,
    "regular_season_weeks": 14,
    "playoff_team_count": 6,
    "defending_champion_manager_id": 1,
    "defending_champion_team_id": 101,
    "playoff_bracket": null,
    "standings": [
      {
        "rank": 1,
        "power_rank": 1,
        "team_id": 101,
        "team_name": "Show Me the Murray",
        "team_abbrev": "MURR",
        "logo_url": null,
        "manager_id": 1,
        "manager_name": "Greg Murray",
        "co_manager_name": null,
        "wins": 6,
        "losses": 1,
        "ties": 0,
        "points_for": 892.4,
        "points_against": 745.2,
        "streak_type": "WIN",
        "streak_length": 4,
        "playoff_seed": 1,
        "final_standing": null,
        "all_play_wins": 55,
        "all_play_losses": 15,
        "all_play_ties": 0,
        "all_play_win_pct": 0.786,
        "median_wins": 6,
        "median_losses": 1,
        "median_ties": 0,
        "luck_index": 0.071,
        "optimal_points_for": 960.0,
        "bench_points": 240.5,
        "lineup_efficiency": 0.930,
        "weekly_earnings": 60.0,
        "podium_earnings": 0.0,
        "total_earnings": 60.0,
        "faab_remaining": 45,
        "championships": 2,
        "championship_years": [2024, 2025],
        "is_defending_champion": true,
        "weekly_history": []
      }
    ]
  }
  ```

---

### 4. `GET /api/v1/hall-of-fame`
Returns all-time championship banners and the featured champion's Pokémon-inspired Elite Four Hall of Fame spotlight, with top 4 championship heroes, player photos, and margin of victory.
- **Query Parameters:**
  - `season` (optional, integer): Filter featured champion to a specific championship year, defaulting to the latest reigning champion.
- **Aliases:** `GET /api/v1/history/hall-of-fame`
- **Response Schema:** `HallOfFameResponse`
- **Example Response:**
  ```json
  {
    "reigning_champion_year": 2023,
    "selected_season": 2023,
    "available_seasons": [2023, 2022],
    "banners": [
      {
        "season_year": 2023,
        "team_id": 9,
        "team_name": "Archer Assassins",
        "team_abbrev": "ARC",
        "logo_url": "https://fantasy.espn.com/logos/arc.png",
        "manager_id": 1,
        "manager_name": "Alice Archer",
        "avatar_url": null,
        "co_manager_id": null,
        "co_manager_name": null,
        "wins": 9,
        "losses": 5,
        "ties": 0,
        "points_for": 1670.5,
        "points_against": 1565.25,
        "regular_season_finish": "Seed #1",
        "championship_score": 145.5,
        "runner_up_team_id": 10,
        "runner_up_team_name": "Baker's Dozen",
        "runner_up_manager_name": "Bob Baker",
        "runner_up_score": 138.2,
        "margin_of_victory": 7.3,
        "total_earnings": 580.0,
        "payout_amount": 600.0
      }
    ],
    "featured_champion": {
      "season_year": 2023,
      "team_id": 9,
      "team_name": "Archer Assassins",
      "team_abbrev": "ARC",
      "logo_url": "https://fantasy.espn.com/logos/arc.png",
      "manager_id": 1,
      "manager_name": "Alice Archer",
      "avatar_url": null,
      "co_manager_id": null,
      "co_manager_name": null,
      "regular_season_finish": "Seed #1",
      "hall_of_fame_number": 2,
      "record": "9-5",
      "total_earnings": 580.0,
      "championship_matchup": {
        "week": 17,
        "matchup_id": 157,
        "winning_score": 145.5,
        "runner_up_team_id": 10,
        "runner_up_team_name": "Baker's Dozen",
        "runner_up_manager_name": "Bob Baker",
        "runner_up_logo_url": "https://fantasy.espn.com/logos/bak.png",
        "runner_up_score": 138.2,
        "margin_of_victory": 7.3
      },
      "top_players": [
        {
          "rank": 1,
          "player_id": 103,
          "full_name": "Josh Allen",
          "default_position": "QB",
          "pro_team": "BUF",
          "headshot_url": "https://a.espncdn.com/i/headshots/nfl/players/full/103.png",
          "slot_position": "WR",
          "fantasy_points": 36.0,
          "projected_points": 20.0,
          "stats_summary": "2 TDs • 250 Pass Yds",
          "role_title": "CHAMPION MVP",
          "pct_of_team_points": 24.7
        }
      ]
    }
  }
  ```

---

### 6. `GET /api/v1/trades/trends`
Returns trade partner networks, trade volumes, realized post-trade starter points, and trade autopsies.
- **Query Parameters:**
  - `season` (optional, integer): Filter to a specific season or null for all-time.
- **Response Schema:** `TradesTrendsResponse`
- **Example Response:**
  ```json
  {
    "season_filter": 2025,
    "has_transaction_data": true,
    "top_partners": [
      {
        "manager_a_id": 1,
        "manager_a_name": "Greg Murray",
        "manager_b_id": 2,
        "manager_b_name": "John Doe",
        "trade_count": 3
      }
    ],
    "active_traders": [
      {
        "manager_id": 1,
        "display_name": "Greg Murray",
        "total_trades": 4,
        "players_acquired": 6,
        "players_traded_away": 5,
        "net_starter_points_gained": 74.5
      }
    ],
    "trades": [
      {
        "trade_id": 401,
        "season_year": 2025,
        "week": 8,
        "executed_at": "2025-10-29T14:30:00Z",
        "espn_transaction_id": "trade-9912",
        "sides": [
          {
            "team_id": 101,
            "team_name": "Show Me the Murray",
            "manager_id": 1,
            "manager_name": "Greg Murray",
            "assets_received": [
              {
                "player_id": 3117251,
                "full_name": "Christian McCaffrey",
                "default_position": "RB",
                "pro_team": "SF",
                "headshot_url": "https://a.espncdn.com/i/headshots/nfl/players/full/3117251.png",
                "post_trade_starter_points": 142.6,
                "post_trade_weeks_started": 7
              }
            ],
            "faab_received": 0,
            "total_starter_points_gained": 142.6
          },
          {
            "team_id": 102,
            "team_name": "Doe A Deer",
            "manager_id": 2,
            "manager_name": "John Doe",
            "assets_received": [
              {
                "player_id": 4241457,
                "full_name": "Garrett Wilson",
                "default_position": "WR",
                "pro_team": "NYJ",
                "headshot_url": "https://a.espncdn.com/i/headshots/nfl/players/full/4241457.png",
                "post_trade_starter_points": 88.2,
                "post_trade_weeks_started": 7
              }
            ],
            "faab_received": 15,
            "total_starter_points_gained": 88.2
          }
        ],
        "winner_manager_id": 1,
        "point_differential": 54.4
      }
    ]
  }
  ```

---

### 7. `GET /api/v1/transactions/summary`
Returns manager FAAB efficiency, waiver success rates, breakdown of failure reasons, bidding war receipts (losing bids linked to winning claims), and the raw transaction audit log.
- **Query Parameters:**
  - `season` (optional, integer): Defaults to current active or latest season.
- **Response Schema:** `TransactionsSummaryResponse`
- **Example Response:**
  ```json
  {
    "season_year": 2026,
    "has_transaction_data": true,
    "manager_efficiency": [
      {
        "manager_id": 1,
        "display_name": "Greg Murray",
        "team_name": "Show Me the Murray",
        "faab_budget": 100,
        "faab_spent": 55,
        "faab_remaining": 45,
        "executed_waivers": 6,
        "failed_waivers": 2,
        "waiver_success_rate": 0.75,
        "free_agent_adds": 8,
        "drops": 14,
        "total_starter_points_from_waivers": 112.4,
        "points_per_faab_dollar": 2.04
      }
    ],
    "failure_reasons": [
      { "reason": "OUTBID", "count": 14 },
      { "reason": "ROSTER_LIMIT_EXCEEDED", "count": 2 }
    ],
    "bidding_wars": [
      {
        "winning_transaction_id": 701,
        "espn_transaction_id": "tx-88210",
        "season_year": 2026,
        "week": 4,
        "executed_at": "2026-10-01T08:02:14Z",
        "player": {
          "player_id": 4361579,
          "full_name": "Puka Nacua",
          "default_position": "WR",
          "pro_team": "LAR",
          "headshot_url": "https://a.espncdn.com/i/headshots/nfl/players/full/4361579.png"
        },
        "winner": {
          "team_id": 101,
          "team_name": "Show Me the Murray",
          "manager_id": 1,
          "manager_name": "Greg Murray",
          "bid_amount": 34,
          "post_claim_starter_points": 98.4
        },
        "losing_bids": [
          {
            "transaction_id": 702,
            "team_id": 102,
            "team_name": "Doe A Deer",
            "manager_id": 2,
            "manager_name": "John Doe",
            "bid_amount": 27,
            "failure_reason": "OUTBID",
            "waiver_priority": 3
          }
        ]
      }
    ],
    "transactions": [
      {
        "transaction_id": 701,
        "espn_transaction_id": "tx-88210",
        "season_year": 2026,
        "week": 4,
        "transaction_type": "WAIVER",
        "status": "EXECUTED",
        "team_id": 101,
        "team_name": "Show Me the Murray",
        "manager_id": 1,
        "manager_name": "Greg Murray",
        "bid_amount": 34,
        "waiver_priority": null,
        "failure_reason": null,
        "executed_at": "2026-10-01T08:02:14Z",
        "related_espn_transaction_id": null,
        "items": [
          {
            "player_id": 4361579,
            "full_name": "Puka Nacua",
            "default_position": "WR",
            "pro_team": "LAR",
            "headshot_url": "https://a.espncdn.com/i/headshots/nfl/players/full/4361579.png",
            "item_type": "ADD"
          }
        ]
      }
    ]
  }
  ```
