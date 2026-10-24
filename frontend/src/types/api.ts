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
  rank: number;
  is_active: boolean;
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

export type TradeAssetReceived = TradePlayerAsset;
export type TradeHistoryCard = TradeDetail;
export type TradePartnerPair = TopTradePartner;
export type ActiveTraderRow = ActiveTrader;
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
  from_team_id?: number | null;
  to_team_id?: number | null;
  from_team_name?: string | null;
  to_team_name?: string | null;
  from_manager_id?: number | null;
  to_manager_id?: number | null;
  from_manager_name?: string | null;
  to_manager_name?: string | null;
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
