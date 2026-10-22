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

export type SeasonEarningsBreakdown = ManagerSeasonBreakdown;

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

export type ManagerEarningsRow = EarningsLeaderboardEntry;

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

export type StandingRow = StandingEntry;

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

export type TradeHistoryCard = TradeDetail;

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

export type TradePartnerPair = TopTradePartner;

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

export type TransactionFeedRow = TransactionAuditItem;

export interface TransactionsSummaryResponse {
  season_year: number;
  has_transaction_data: boolean;
  manager_efficiency: ManagerEfficiency[];
  failure_reasons: FailureReasonCount[];
  bidding_wars: BiddingWar[];
  transactions: TransactionAuditItem[];
}
