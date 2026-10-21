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
  is_active: boolean;
}

export interface SyncStatus {
  last_backfill_at: string | null;
  last_weekly_sync_at: string | null;
  last_sync_status: string | null;
}

export type SyncStatusMeta = SyncStatus;

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

export interface ManagerSeasonBreakdown {
  season_year: number;
  team_name: string;
  weekly_earnings: number;
  podium_earnings: number;
  total_earnings: number;
  weekly_wins: number;
  weekly_ties: number;
  final_standing: number | null;
  trophy: TrophyType;
}

export type SeasonEarningsBreakdown = ManagerSeasonBreakdown;

export interface EarningsLeaderboardEntry {
  manager_id: number;
  display_name: string;
  total_earnings: number;
  weekly_earnings: number;
  podium_earnings: number;
  weekly_wins_count: number;
  weekly_ties_count: number;
  championships: number;
  runner_ups: number;
  third_places: number;
  seasons_played: number;
  season_breakdown: ManagerSeasonBreakdown[];
}

export type ManagerEarningsRow = EarningsLeaderboardEntry;

export interface EarningsLeaderboardResponse {
  season_filter: number | null;
  weekly_win_value: number;
  leaderboard: EarningsLeaderboardEntry[];
}

// ==========================================
// 3. Standings & Performance
// ==========================================

export interface StandingEntry {
  rank: number;
  team_id: number;
  team_name: string;
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
}

export type StandingRow = StandingEntry;

export interface StandingsResponse {
  season_year: number;
  is_active: boolean;
  is_completed: boolean;
  current_week: number;
  standings: StandingEntry[];
}

// ==========================================
// 4. Head-to-Head Rivalry
// ==========================================

export interface H2HManagerRef {
  manager_id: number;
  display_name: string;
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

export type HeadToHeadMatrixCell = H2HMatrixEntry;

export interface H2HRecordSplit {
  a_wins: number;
  b_wins: number;
  ties: number;
  a_points: number;
  b_points: number;
}

export type HeadToHeadSeriesSplit = H2HRecordSplit;

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

export type HeadToHeadHighlightGame = H2HGameHighlight;

export interface H2HMatchupGame {
  matchup_id: number;
  season_year: number;
  week: number;
  matchup_type: string;
  manager_a_team_name: string;
  manager_b_team_name: string;
  manager_a_score: number;
  manager_b_score: number;
  winner_manager_id: number | null;
}

export type HeadToHeadMatchupItem = H2HMatchupGame;

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

export type HeadToHeadPairDetail = H2HPairDetail;

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

export type TradeAssetReceived = TradePlayerAsset;

export interface TradeSide {
  team_id: number;
  team_name: string;
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

export type TradeHistoryCard = TradeDetail;

export interface TopTradePartner {
  manager_a_id: number;
  manager_a_name: string;
  manager_b_id: number;
  manager_b_name: string;
  trade_count: number;
}

export type TradePartnerPair = TopTradePartner;

export interface ActiveTrader {
  manager_id: number;
  display_name: string;
  total_trades: number;
  players_acquired: number;
  players_traded_away: number;
  net_starter_points_gained: number;
}

export type ActiveTraderRow = ActiveTrader;

export interface TradesTrendsResponse {
  season_filter: number | null;
  has_transaction_data: boolean;
  top_partners: TopTradePartner[];
  active_traders: ActiveTrader[];
  trades: TradeDetail[];
}

export type TradeTrendsResponse = TradesTrendsResponse;

// ==========================================
// 6. Transactions & FAAB Bidding Wars
// ==========================================

export interface ManagerEfficiency {
  manager_id: number;
  display_name: string;
  team_name: string;
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

export type ManagerWaiverEfficiency = ManagerEfficiency;

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
  manager_id: number;
  manager_name: string;
  bid_amount: number;
  post_claim_starter_points: number;
}

export interface LosingBid {
  transaction_id: number;
  team_id: number;
  team_name: string;
  manager_id: number;
  manager_name: string;
  bid_amount: number;
  failure_reason: string;
  waiver_priority: number | null;
}

export type BiddingWarLosingBid = LosingBid;

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

export type BiddingWarReceipt = BiddingWar;

export interface TransactionItem {
  player_id: number;
  full_name: string;
  default_position: string;
  pro_team: string;
  headshot_url: string | null;
  item_type: "ADD" | "DROP" | "TRADE";
}

export type TransactionItemDetail = TransactionItem;

export interface TransactionAuditItem {
  transaction_id: number;
  espn_transaction_id: string;
  season_year: number;
  week: number | null;
  transaction_type: "FREE_AGENT" | "WAIVER" | "DROP" | "TRADE";
  status: "EXECUTED" | "FAILED" | "CANCELED" | "VETOED";
  team_id: number | null;
  team_name: string | null;
  manager_id: number | null;
  manager_name: string | null;
  bid_amount: number | null;
  waiver_priority: number | null;
  failure_reason: string | null;
  executed_at: string | null;
  related_espn_transaction_id: string | null;
  items: TransactionItem[];
}

export type TransactionFeedRow = TransactionAuditItem;

export interface TransactionsSummaryResponse {
  season_year: number;
  has_transaction_data: boolean;
  manager_efficiency: ManagerEfficiency[];
  failure_reasons: FailureReasonCount[];
  bidding_wars: BiddingWar[];
  transactions: TransactionAuditItem[];
}
