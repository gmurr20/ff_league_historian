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
  weekly_wins_count: number;
  weekly_ties_count: number;
  weekly_wins_cash: number;
  weekly_bonus_cash: number;
  weekly_high_scores_count: number;
  weekly_high_score_losses_count: number;
  bounty_receipts: ManagerBountyReceipt[];
  championships: number;
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

export interface EarningsLeaderboardResponse {
  season_filter: number | null;
  weekly_win_value: number;
  leaderboard: EarningsLeaderboardEntry[];
  weekly_nuanced_payouts: WeeklyNuancedPayoutEntry[];
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
  weekly_history: WeeklyStandingPoint[];
}

export interface StandingsResponse {
  season_year: number;
  is_active: boolean;
  is_completed: boolean;
  current_week: number;
  regular_season_weeks: number;
  playoff_team_count: number;
  standings: StandingEntry[];
}

// ==========================================
// 4. Head-to-Head Rivalry
// ==========================================

export interface H2HManagerRef {
  manager_id: number;
  display_name: string;
  team_name: string;
  avatar_url: string | null;
}

export interface H2HMatrixEntry {
  manager_a_id: number;
  manager_a_name: string;
  manager_b_id: number;
  manager_b_name: string;
  wins: number;
  losses: number;
  ties: number;
  win_pct: number;
  points_for: number;
  points_against: number;
  total_games: number;
}

export interface H2HRecordSplit {
  a_wins: number;
  b_wins: number;
  ties: number;
  a_points: number;
  b_points: number;
}

export interface H2HCombinedSplit extends H2HRecordSplit {
  point_differential: number;
}

export interface H2HStreak {
  manager_id: number | null;
  display_name: string | null;
  length: number;
  type: "WIN" | "TIE" | "NONE";
}

export interface H2HGameHighlight {
  season_year: number;
  week: number;
  matchup_type: string;
  winner_manager_id: number | null;
  winner_name: string | null;
  winner_score: number;
  loser_score: number;
  margin: number;
}

export interface H2HMatchupGame {
  matchup_id: number;
  season_year: number;
  week: number;
  matchup_type: string;
  manager_a_team_name: string;
  manager_b_team_name: string;
  manager_a_logo_url: string | null;
  manager_b_logo_url: string | null;
  manager_a_score: number;
  manager_b_score: number;
  winner_manager_id: number | null;
}

export interface H2HPairDetail {
  manager_a: H2HManagerRef;
  manager_b: H2HManagerRef;
  regular_season: H2HRecordSplit;
  playoffs: H2HRecordSplit;
  combined: H2HCombinedSplit;
  current_streak: H2HStreak;
  biggest_blowout: H2HGameHighlight | null;
  closest_game: H2HGameHighlight | null;
  matchups: H2HMatchupGame[];
}

export interface HeadToHeadResponse {
  managers: H2HManagerRef[];
  matrix: H2HMatrixEntry[];
  pair_detail: H2HPairDetail | null;
}

// ==========================================
// 5. Trades & Realized Value
// ==========================================

export interface TradePlayerAsset {
  player_id: number;
  full_name: string;
  default_position: string;
  pro_team: string;
  headshot_url: string | null;
  post_trade_starter_points: number;
  post_trade_weeks_started: number;
}

export interface TradeSide {
  team_id: number;
  team_name: string;
  logo_url: string | null;
  manager_id: number;
  manager_name: string;
  assets_received: TradePlayerAsset[];
  faab_received: number;
  total_starter_points_gained: number;
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
}

export interface ActiveTrader {
  manager_id: number;
  display_name: string;
  team_name: string;
  avatar_url: string | null;
  total_trades: number;
  players_acquired: number;
  players_traded_away: number;
  net_starter_points_gained: number;
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
    "standings": [
      {
        "rank": 1,
        "team_id": 101,
        "team_name": "Show Me the Murray",
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
        "faab_remaining": 45
      }
    ]
  }
  ```

---

### 5. `GET /api/v1/history/head-to-head`
Returns the complete N×N career rivalry matrix, and optionally deep pairwise comparison when `managerA` and `managerB` are supplied.
- **Query Parameters:**
  - `managerA` (optional, integer): First manager ID.
  - `managerB` (optional, integer): Second manager ID.
- **Response Schema:** `HeadToHeadResponse`
- **Example Response:**
  ```json
  {
    "managers": [
      { "manager_id": 1, "display_name": "Greg Murray" },
      { "manager_id": 2, "display_name": "John Doe" }
    ],
    "matrix": [
      {
        "manager_a_id": 1,
        "manager_a_name": "Greg Murray",
        "manager_b_id": 2,
        "manager_b_name": "John Doe",
        "wins": 5,
        "losses": 2,
        "ties": 0,
        "win_pct": 0.714,
        "points_for": 845.2,
        "points_against": 760.1,
        "total_games": 7
      }
    ],
    "pair_detail": {
      "manager_a": { "manager_id": 1, "display_name": "Greg Murray" },
      "manager_b": { "manager_id": 2, "display_name": "John Doe" },
      "regular_season": {
        "a_wins": 4,
        "b_wins": 2,
        "ties": 0,
        "a_points": 710.2,
        "b_points": 650.1
      },
      "playoffs": {
        "a_wins": 1,
        "b_wins": 0,
        "ties": 0,
        "a_points": 135.0,
        "b_points": 110.0
      },
      "combined": {
        "a_wins": 5,
        "b_wins": 2,
        "ties": 0,
        "a_points": 845.2,
        "b_points": 760.1,
        "point_differential": 85.1
      },
      "current_streak": {
        "manager_id": 1,
        "display_name": "Greg Murray",
        "length": 3,
        "type": "WIN"
      },
      "biggest_blowout": {
        "season_year": 2024,
        "week": 6,
        "matchup_type": "REGULAR",
        "winner_manager_id": 1,
        "winner_name": "Greg Murray",
        "winner_score": 142.5,
        "loser_score": 88.0,
        "margin": 54.5
      },
      "closest_game": {
        "season_year": 2025,
        "week": 11,
        "matchup_type": "REGULAR",
        "winner_manager_id": 1,
        "winner_name": "Greg Murray",
        "winner_score": 112.4,
        "loser_score": 110.2,
        "margin": 2.2
      },
      "matchups": [
        {
          "matchup_id": 1001,
          "season_year": 2025,
          "week": 11,
          "matchup_type": "REGULAR",
          "manager_a_team_name": "Show Me the Murray",
          "manager_b_team_name": "Doe A Deer",
          "manager_a_score": 112.4,
          "manager_b_score": 110.2,
          "winner_manager_id": 1
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
