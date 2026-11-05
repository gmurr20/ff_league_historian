<script setup lang="ts">
import { ref, computed } from 'vue';
import type {
  FutureDraftData,
  DraftTeamRef,
  FutureDraftTradeLogEntry,
  FutureDraftTeamSummary,
  FutureDraftRosterPlayer,
  TradeDetail,
  TradeSide,
  TradePlayerAsset,
} from '@/types/api';
import { fetchTradeTrends } from '@/api/client';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import SwipeDrawer from '@/components/ui/SwipeDrawer.vue';
import TradeAutopsyDrawer from '@/components/trades/TradeAutopsyDrawer.vue';
import { ChevronLeft, ChevronRight, ArrowRight, ArrowUpRight } from 'lucide-vue-next';

const props = defineProps<{
  draftData: FutureDraftData;
}>();

// Sub-view toggle: 'team' (Team Picks & Market Status) | 'trades' (Traded Picks) | 'round' (By Round)
const activeSubView = ref<'team' | 'trades' | 'round'>('team');

// Selected round filter for 'round' view (null = all rounds)
const selectedRound = ref<number | null>(null);

// Drawer state for Pick Lineage & Chain of Custody
const drawerOpen = ref<boolean>(false);
const selectedPickTrace = ref<{
  round: number;
  originalTeam: DraftTeamRef;
  currentTeam: DraftTeamRef;
  hops: {
    step: number;
    action: 'ORIGIN' | 'TRADE';
    fromTeam: DraftTeamRef | null;
    toTeam: DraftTeamRef;
    week: number | null;
    executedAt: string | null;
    espnTransactionId: string | null;
  }[];
} | null>(null);

// Drawer state for Full Trade Autopsy
const fullTradeDrawerOpen = ref<boolean>(false);
const selectedFullTrade = ref<TradeDetail | null>(null);

// Format date helper
function formatDate(dateStr: string | null): string {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return dateStr;
  }
}

// Ordinal helper: 1st, 2nd, 3rd, 4th, 16th...
function getOrdinal(n: number): string {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

// Position styling helper for player assets in trade cards
function getPositionClass(pos: string | undefined): string {
  switch (pos?.toUpperCase()) {
    case 'QB':
      return 'bg-rose-500/20 text-rose-300 border border-rose-500/40';
    case 'RB':
      return 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40';
    case 'WR':
      return 'bg-sky-500/20 text-sky-300 border border-sky-500/40';
    case 'TE':
      return 'bg-amber-500/20 text-amber-300 border border-amber-500/40';
    case 'K':
      return 'bg-purple-500/20 text-purple-300 border border-purple-500/40';
    case 'D/ST':
    case 'DST':
      return 'bg-slate-500/20 text-slate-300 border border-slate-500/40';
    default:
      return 'bg-slate-700 text-slate-300 border border-slate-600';
  }
}

// ---------------------------------------------------------------------------
// Chain of Custody resolution
// ---------------------------------------------------------------------------
function openPickTrace(round: number, originalTeam: DraftTeamRef, currentTeam?: DraftTeamRef) {
  // Find all trades involving this exact pick (round + original team) in chronological order
  const matchingTrades = props.draftData.traded_picks_log
    .filter(
      (entry) =>
        entry.round === round && entry.original_team.team_id === originalTeam.team_id
    )
    .sort((a, b) => {
      if (a.executed_at && b.executed_at) {
        return new Date(a.executed_at).getTime() - new Date(b.executed_at).getTime();
      }
      return (a.week ?? 0) - (b.week ?? 0);
    });

  const hops: {
    step: number;
    action: 'ORIGIN' | 'TRADE';
    fromTeam: DraftTeamRef | null;
    toTeam: DraftTeamRef;
    week: number | null;
    executedAt: string | null;
    espnTransactionId: string | null;
  }[] = [];

  // Step 1: Origin
  hops.push({
    step: 1,
    action: 'ORIGIN',
    fromTeam: null,
    toTeam: originalTeam,
    week: null,
    executedAt: null,
    espnTransactionId: null,
  });

  // Subsequent hops through all trades
  matchingTrades.forEach((tx, idx) => {
    hops.push({
      step: idx + 2,
      action: 'TRADE',
      fromTeam: tx.from_team,
      toTeam: tx.to_team,
      week: tx.week,
      executedAt: tx.executed_at,
      espnTransactionId: tx.espn_transaction_id,
    });
  });

  const latestTeam =
    currentTeam ||
    (matchingTrades.length > 0
      ? matchingTrades[matchingTrades.length - 1].to_team
      : originalTeam);

  selectedPickTrace.value = {
    round,
    originalTeam,
    currentTeam: latestTeam,
    hops,
  };

  drawerOpen.value = true;
}

// ---------------------------------------------------------------------------
// Grouped Trades & Human-Readable Changes
// ---------------------------------------------------------------------------
interface CleanTradeSide {
  team: DraftTeamRef;
  lost: { round: number; originalTeam: DraftTeamRef }[];
  gained: { round: number; originalTeam: DraftTeamRef }[];
  playersGained: TradePlayerAsset[];
}

interface CleanTradeGroup {
  transactionId: string;
  week: number | null;
  executedAt: string | null;
  sides: CleanTradeSide[];
  rawEntries: FutureDraftTradeLogEntry[];
  tradeDetail: TradeDetail | null;
}

const groupedTrades = computed<CleanTradeGroup[]>(() => {
  const map = new Map<string, FutureDraftTradeLogEntry[]>();
  for (const entry of props.draftData.traded_picks_log) {
    const key = entry.espn_transaction_id || `tx-${entry.round}-${entry.original_team.team_id}`;
    if (!map.has(key)) {
      map.set(key, []);
    }
    map.get(key)!.push(entry);
  }

  const result: CleanTradeGroup[] = [];

  for (const [txId, entries] of map.entries()) {
    const first = entries[0];
    const txDetail: TradeDetail | null =
      first.trade_detail ||
      props.draftData.trades?.find((t) => t.espn_transaction_id === txId) ||
      null;

    const teamMap = new Map<number, CleanTradeSide>();

    for (const entry of entries) {
      if (entry.from_team) {
        if (!teamMap.has(entry.from_team.team_id)) {
          teamMap.set(entry.from_team.team_id, {
            team: entry.from_team,
            lost: [],
            gained: [],
            playersGained: [],
          });
        }
        teamMap.get(entry.from_team.team_id)!.lost.push({
          round: entry.round,
          originalTeam: entry.original_team,
        });
      }

      if (!teamMap.has(entry.to_team.team_id)) {
        teamMap.set(entry.to_team.team_id, {
          team: entry.to_team,
          lost: [],
          gained: [],
          playersGained: [],
        });
      }
      teamMap.get(entry.to_team.team_id)!.gained.push({
        round: entry.round,
        originalTeam: entry.original_team,
      });
    }

    // Attach players involved for each side from rich TradeDetail
    if (txDetail && txDetail.sides) {
      for (const side of txDetail.sides) {
        let cleanSide = teamMap.get(side.team_id);
        if (!cleanSide) {
          for (const s of teamMap.values()) {
            if (s.team.manager_id === side.manager_id || s.team.team_name === side.team_name) {
              cleanSide = s;
              break;
            }
          }
        }
        if (cleanSide) {
          cleanSide.playersGained = (side.assets_received || []).filter(
            (a) => a.asset_type === 'PLAYER' || (a.asset_type !== 'PICK' && a.player_id != null)
          );
        }
      }
    }

    result.push({
      transactionId: txId,
      week: first.week,
      executedAt: first.executed_at,
      sides: Array.from(teamMap.values()),
      rawEntries: entries,
      tradeDetail: txDetail,
    });
  }

  // Trades ordered with most recent first
  return result.sort((a, b) => {
    if (a.executedAt && b.executedAt) {
      return new Date(b.executedAt).getTime() - new Date(a.executedAt).getTime();
    }
    if (a.executedAt) return -1;
    if (b.executedAt) return 1;
    const aWeek = a.week ?? 0;
    const bWeek = b.week ?? 0;
    return bWeek - aWeek;
  });
});

// Fallback builder if TradeDetail was not attached by backend
function buildFallbackTradeDetail(group: CleanTradeGroup): TradeDetail {
  const sides: TradeSide[] = group.sides.map((s) => ({
    team_id: s.team.team_id,
    team_name: s.team.team_name,
    logo_url: s.team.logo_url,
    manager_id: s.team.manager_id,
    manager_name: s.team.manager_name,
    assets_received: [
      ...s.gained.map((g) => ({
        player_id: 0,
        full_name: `${props.draftData.season_year} Round ${g.round} Pick`,
        default_position: 'PICK',
        pro_team: '',
        headshot_url: null,
        asset_type: 'PICK' as const,
        post_trade_starter_points: 0,
        post_trade_weeks_started: 0,
        post_trade_total_points: 0,
        post_trade_bench_points: 0,
        post_trade_weeks_played: 0,
        roster_depth_points: 0,
        pre_trade_points: 0,
        pre_trade_ppg: 0,
        season_total_points: 0,
        season_ppg: 0,
        positional_rank: null,
        tier_label: null,
        vorp_per_game: 0,
        pick_round: g.round,
        pick_number: null,
        pick_round_value: 0,
        original_team_id: g.originalTeam.team_id,
        original_team_name: g.originalTeam.team_name,
        original_manager_name: g.originalTeam.manager_name,
        drafted_player_id: null,
        drafted_player_name: null,
        drafted_player_position: null,
        drafted_player_headshot_url: null,
        drafted_player_points: 0,
        trade_score: 0,
        weekly_breakdown: [],
      })),
      ...s.playersGained,
    ],
    faab_received: 0,
    faab_value: 0,
    total_starter_points_gained: 0,
    total_ros_points_gained: 0,
    total_roster_depth_points_gained: 0,
    slot_equalization_points: 0,
    total_pick_value_gained: 0,
    total_trade_score: 0,
    grade: 'C',
  }));

  return {
    trade_id: 0,
    espn_transaction_id: group.transactionId,
    season_year: props.draftData.reference_season_year || props.draftData.season_year,
    week: group.week,
    executed_at: group.executedAt,
    verdict_label: 'Draft Pick Swap',
    winner_manager_id: null,
    point_differential: 0,
    score_differential: 0,
    is_projected: false,
    weekly_trajectory: [],
    timeline_events: [],
    sides,
  };
}

// Open whole trade drawer
async function openFullTrade(group: CleanTradeGroup) {
  if (group.tradeDetail) {
    selectedFullTrade.value = group.tradeDetail;
    fullTradeDrawerOpen.value = true;
    return;
  }
  if (props.draftData.trades) {
    const found = props.draftData.trades.find(
      (t) => t.espn_transaction_id === group.transactionId
    );
    if (found) {
      selectedFullTrade.value = found;
      fullTradeDrawerOpen.value = true;
      return;
    }
  }
  try {
    const trends = await fetchTradeTrends(null);
    const found = trends.trades.find(
      (t) => t.espn_transaction_id === group.transactionId
    );
    if (found) {
      selectedFullTrade.value = found;
      fullTradeDrawerOpen.value = true;
      return;
    }
  } catch {
    // fallback below
  }
  selectedFullTrade.value = buildFallbackTradeDetail(group);
  fullTradeDrawerOpen.value = true;
}

async function openFullTradeById(txId: string) {
  const matchingGroup = groupedTrades.value.find((g) => g.transactionId === txId);
  if (matchingGroup) {
    await openFullTrade(matchingGroup);
    return;
  }
  const fromProps = props.draftData.trades?.find((t) => t.espn_transaction_id === txId);
  if (fromProps) {
    selectedFullTrade.value = fromProps;
    fullTradeDrawerOpen.value = true;
    return;
  }
  try {
    const trends = await fetchTradeTrends(null);
    const found = trends.trades.find((t) => t.espn_transaction_id === txId);
    if (found) {
      selectedFullTrade.value = found;
      fullTradeDrawerOpen.value = true;
      return;
    }
  } catch {
    // ignore
  }
}

// ---------------------------------------------------------------------------
// Market Segmentation: Buyers, Sellers & Ready to Trade (1-Swap Rule Active)
// ---------------------------------------------------------------------------
type PickTradeRole = 'READY' | 'BUYER' | 'SELLER';

function getTeamRole(team: FutureDraftTeamSummary): PickTradeRole {
  const acq = team.picks_acquired || [];
  const away = team.picks_traded_away || [];
  if (acq.length === 0 && away.length === 0) {
    return 'READY';
  }
  // Lower round = higher value pick (e.g. Round 1-4 vs Round 16)
  const minAcq = acq.length > 0 ? Math.min(...acq.map((p) => p.round)) : 999;
  const minAway = away.length > 0 ? Math.min(...away.map((p) => p.round)) : 999;
  if (minAway < minAcq) {
    // Traded away earlier pick than acquired -> Buyer
    return 'BUYER';
  } else if (minAcq < minAway) {
    // Acquired earlier pick than traded away -> Seller
    return 'SELLER';
  }
  return team.net_picks > 0 ? 'SELLER' : 'BUYER';
}

const teamsReadyToTrade = computed(() => {
  return props.draftData.teams_summary.filter((t) => getTeamRole(t) === 'READY');
});

const buyerTeams = computed(() => {
  return props.draftData.teams_summary.filter((t) => getTeamRole(t) === 'BUYER');
});

const sellerTeams = computed(() => {
  return props.draftData.teams_summary.filter((t) => getTeamRole(t) === 'SELLER');
});

function getTeamPickDelta(team: FutureDraftTeamSummary): { plus: number[]; minus: number[] } {
  const plus = (team.picks_acquired || []).map((p) => p.round).sort((a, b) => a - b);
  const minus = (team.picks_traded_away || []).map((p) => p.round).sort((a, b) => a - b);
  return { plus, minus };
}

const displayedTeamsSummary = computed(() => {
  return teamsSummary.value;
});

// Slide-Up Team Scouting Drawer State (Option A: Mobile-First Drawer)
const teamDrawerOpen = ref<boolean>(false);
const selectedTeamId = ref<number | null>(null);

const selectedDrawerTeam = computed<FutureDraftTeamSummary | null>(() => {
  if (selectedTeamId.value == null) return null;
  return (
    props.draftData.teams_summary.find((t) => t.team_id === selectedTeamId.value) ?? null
  );
});

function openTeamDrawer(teamId: number) {
  selectedTeamId.value = teamId;
  teamDrawerOpen.value = true;
}

function stepDrawerTeam(direction: -1 | 1) {
  const list = displayedTeamsSummary.value;
  if (list.length === 0 || selectedTeamId.value == null) return;
  const idx = list.findIndex((t) => t.team_id === selectedTeamId.value);
  if (idx === -1) return;
  const nextIdx = (idx + direction + list.length) % list.length;
  selectedTeamId.value = list[nextIdx].team_id;
}

function getTeamTrades(teamId: number): CleanTradeGroup[] {
  return groupedTrades.value.filter((gt) =>
    gt.sides.some((s) => s.team.team_id === teamId)
  );
}

// ---------------------------------------------------------------------------
// Ordered 16-Round Inventory for Each Team
// ---------------------------------------------------------------------------
type TeamSummaryItem = (typeof props.draftData.teams_summary)[0];

interface RoundInventorySlot {
  round: number;
  isOwnPick: boolean;
  isTradedAway: boolean;
  isAcquired: boolean;
  originalTeam: DraftTeamRef;
  currentTeam: DraftTeamRef;
}

/**
 * Returns all rounds held and traded in strict round order (1 to 16).
 * Acquired picks for Round R appear immediately after Round R!
 */
function getOrderedTeamInventory(team: TeamSummaryItem): RoundInventorySlot[] {
  const result: RoundInventorySlot[] = [];

  for (let r = 1; r <= 16; r++) {
    // 1. Team's own pick in round r
    const tradedAway = team.picks_traded_away.find(
      (p) => p.round === r && p.original_team.team_id === team.team_id
    );

    if (tradedAway) {
      result.push({
        round: r,
        isOwnPick: true,
        isTradedAway: true,
        isAcquired: false,
        originalTeam: tradedAway.original_team,
        currentTeam: tradedAway.current_team,
      });
    } else {
      const ownHeld = team.picks_held.find(
        (p) => p.round === r && p.original_team.team_id === team.team_id
      );
      if (ownHeld) {
        result.push({
          round: r,
          isOwnPick: true,
          isTradedAway: false,
          isAcquired: false,
          originalTeam: ownHeld.original_team,
          currentTeam: ownHeld.current_team,
        });
      }
    }

    // 2. Acquired picks in this same round r (placed in-place directly after Round r)
    const acquiredInRound = team.picks_acquired.filter((p) => p.round === r);
    for (const acq of acquiredInRound) {
      result.push({
        round: r,
        isOwnPick: false,
        isTradedAway: false,
        isAcquired: true,
        originalTeam: acq.original_team,
        currentTeam: acq.current_team,
      });
    }
  }

  return result;
}

// ---------------------------------------------------------------------------
// Roster Tier Highlighting Helpers (T1 Elite -> T5 Depth)
// ---------------------------------------------------------------------------
const ROSTER_POSITIONS = ['QB', 'RB', 'WR', 'TE', 'D/ST', 'K'] as const;

function getPlayersByPosition(
  team: FutureDraftTeamSummary,
  pos: string
): FutureDraftRosterPlayer[] {
  return (team.roster_players || []).filter((p) => p.default_position === pos);
}

function getTeamPositions(team: FutureDraftTeamSummary): string[] {
  return ROSTER_POSITIONS.filter((pos) => getPlayersByPosition(team, pos).length > 0);
}

function getTierPillClass(tier: number): string {
  switch (tier) {
    case 1:
      return 'bg-amber-500/15 text-amber-100 border-amber-400/50 shadow-xs hover:border-amber-300';
    case 2:
      return 'bg-emerald-500/15 text-emerald-100 border-emerald-500/45 hover:border-emerald-400';
    case 3:
      return 'bg-sky-500/15 text-sky-100 border-sky-500/40 hover:border-sky-400';
    case 4:
      return 'bg-indigo-500/15 text-indigo-100 border-indigo-500/40 hover:border-indigo-400';
    default:
      return 'bg-slate-950/90 text-slate-400 border-slate-800/80 hover:border-slate-700';
  }
}

function getTierBadgeClass(tier: number): string {
  switch (tier) {
    case 1:
      return 'bg-amber-400/25 text-amber-300 border-amber-400/50';
    case 2:
      return 'bg-emerald-500/25 text-emerald-300 border-emerald-500/50';
    case 3:
      return 'bg-sky-500/25 text-sky-300 border-sky-500/50';
    case 4:
      return 'bg-indigo-500/25 text-indigo-300 border-indigo-500/50';
    default:
      return 'bg-slate-900 text-slate-500 border-slate-800';
  }
}

function getTeamTierCounts(team: FutureDraftTeamSummary): {
  t1: number;
  t2: number;
  t3: number;
  t4: number;
} {
  const players = team.roster_players || [];
  return {
    t1: players.filter((p) => p.tier === 1).length,
    t2: players.filter((p) => p.tier === 2).length,
    t3: players.filter((p) => p.tier === 3).length,
    t4: players.filter((p) => p.tier === 4).length,
  };
}

// Teams summary list sorted by imbalance first, then alphabetically
const teamsSummary = computed(() => {
  return [...props.draftData.teams_summary].sort((a, b) => {
    const aImbalance = Math.abs(a.net_picks);
    const bImbalance = Math.abs(b.net_picks);
    if (bImbalance !== aImbalance) {
      return bImbalance - aImbalance;
    }
    return a.team_name.localeCompare(b.team_name);
  });
});

// Traded picks count
const tradedPicksCount = computed(() => {
  return props.draftData.traded_picks_log.length;
});

// Filtered rounds for 'round' view
const filteredRounds = computed(() => {
  if (selectedRound.value !== null) {
    return props.draftData.rounds.filter((r) => r.round === selectedRound.value);
  }
  return props.draftData.rounds;
});

function selectRoundPill(r: number | null) {
  selectedRound.value = r;
}
</script>

<template>
  <div class="space-y-4">
    <!-- Sub-Navigation Tabs: Team Picks | Traded Picks | By Round -->
    <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-3">
      <div class="inline-flex flex-wrap rounded-xl bg-slate-900 p-1 border border-slate-800/80 gap-1">
        <button
          type="button"
          class="px-3 sm:px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer min-h-[36px]"
          :class="
            activeSubView === 'team'
              ? 'bg-slate-800 text-white shadow-sm border border-slate-700'
              : 'text-slate-400 hover:text-white'
          "
          @click="activeSubView = 'team'"
        >
          <span>Team Picks</span>
        </button>

        <button
          type="button"
          class="px-3 sm:px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer min-h-[36px]"
          :class="
            activeSubView === 'trades'
              ? 'bg-slate-800 text-white shadow-sm border border-slate-700'
              : 'text-slate-400 hover:text-white'
          "
          @click="activeSubView = 'trades'"
        >
          <span>Traded Picks ({{ tradedPicksCount }})</span>
        </button>

        <button
          type="button"
          class="px-3 sm:px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer min-h-[36px]"
          :class="
            activeSubView === 'round'
              ? 'bg-slate-800 text-white shadow-sm border border-slate-700'
              : 'text-slate-400 hover:text-white'
          "
          @click="activeSubView = 'round'"
        >
          <span>By Round</span>
        </button>
      </div>

      <div class="text-[11px] font-mono text-slate-500 hidden sm:block">
        16 Rounds · 192 League Selections
      </div>
    </div>

    <!-- ===================================================================== -->
    <!-- VIEW A: TEAM PICKS (DEFAULT FRONT PAGE WITH TRADE MARKET STATUS)      -->
    <!-- ===================================================================== -->
    <div v-if="activeSubView === 'team'" class="space-y-4">
      <!-- 1. Highlight Card: Trade Market Segmentation (Ready to Trade, Buyers, Sellers) -->
      <div
        class="bg-gradient-to-br from-slate-900 via-slate-900 to-slate-950 border border-slate-800 rounded-2xl p-3.5 sm:p-5 shadow-lg space-y-4"
      >
        <!-- Header -->
        <div class="space-y-1 border-b border-slate-800/80 pb-3">
          <div class="flex flex-wrap items-center gap-2">
            <span class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
            <h3 class="text-sm sm:text-base font-black text-white uppercase tracking-tight font-mono">
              Trade Market Status
            </h3>
            <span class="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-slate-950 text-slate-300 border border-slate-800">
              1-Swap Limit
            </span>
          </div>
          <p class="text-xs text-slate-400">
            League rules allow only 1 round of draft pick swaps per season. Tap any franchise below to open their roster &amp; draft capital drawer.
          </p>
        </div>

        <!-- Section A: Ready to Trade -->
        <div
          v-if="teamsReadyToTrade.length > 0"
          class="space-y-2.5"
        >
          <div class="flex flex-wrap items-center justify-between gap-1">
            <div class="text-xs font-mono font-bold uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
              <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              <span>Ready to Trade ({{ teamsReadyToTrade.length }} Franchises)</span>
            </div>
            <span class="text-[10px] font-mono text-slate-400">Full capital intact · Can buy or sell</span>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            <button
              v-for="team in teamsReadyToTrade"
              :key="team.team_id"
              type="button"
              class="bg-slate-950/80 border border-emerald-500/20 hover:border-emerald-500/50 rounded-xl p-2.5 flex items-center justify-between gap-2 transition-all group text-left cursor-pointer"
              @click="openTeamDrawer(team.team_id)"
              title="Tap to scout roster and draft picks"
            >
              <div class="flex items-center gap-2 min-w-0">
                <TeamAvatar
                  :src="team.logo_url"
                  :name="team.team_name"
                  size="xs"
                  rounded="lg"
                />
                <div class="min-w-0 leading-tight">
                  <div class="text-xs font-bold text-white truncate group-hover:text-emerald-300 transition-colors">
                    {{ team.team_name }}
                  </div>
                  <div class="flex items-center gap-1.5 text-[10px] text-slate-400 truncate mt-0.5">
                    <span class="truncate">{{ team.manager_name }}</span>
                    <span class="text-slate-600">·</span>
                    <span class="font-mono font-bold text-slate-200 shrink-0">{{ team.record }}</span>
                  </div>
                </div>
              </div>
              <div class="flex items-center gap-1 shrink-0">
                <span class="text-[9.5px] font-mono font-bold px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/40">
                  Ready to Trade
                </span>
                <ChevronRight class="w-3.5 h-3.5 text-slate-500 group-hover:text-emerald-300 transition-colors" />
              </div>
            </button>
          </div>
        </div>

        <!-- Section B: Buyers (Win-Now Contenders) -->
        <div
          v-if="buyerTeams.length > 0"
          class="space-y-2.5 pt-3 border-t border-slate-800/80"
        >
          <div class="flex flex-wrap items-center justify-between gap-1">
            <div class="text-xs font-mono font-bold uppercase tracking-wider text-cyan-300 flex items-center gap-1.5">
              <span class="w-2 h-2 rounded-full bg-cyan-400"></span>
              <span>Buyers ({{ buyerTeams.length }} Contenders · Capital Spent)</span>
            </div>
            <span class="text-[10px] font-mono text-slate-400">+Gained / -Lost Round</span>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            <button
              v-for="team in buyerTeams"
              :key="team.team_id"
              type="button"
              class="bg-slate-950/80 border border-cyan-500/20 hover:border-cyan-500/50 rounded-xl p-2.5 flex items-center justify-between gap-2 transition-all group text-left cursor-pointer"
              @click="openTeamDrawer(team.team_id)"
              title="Tap to scout roster and draft picks"
            >
              <div class="flex items-center gap-2 min-w-0">
                <TeamAvatar
                  :src="team.logo_url"
                  :name="team.team_name"
                  size="xs"
                  rounded="lg"
                />
                <div class="min-w-0 leading-tight">
                  <div class="text-xs font-bold text-white truncate group-hover:text-cyan-300 transition-colors">
                    {{ team.team_name }}
                  </div>
                  <div class="flex items-center gap-1.5 text-[10px] text-slate-400 truncate mt-0.5">
                    <span class="truncate">{{ team.manager_name }}</span>
                    <span class="text-slate-600">·</span>
                    <span class="font-mono font-bold text-slate-200 shrink-0">{{ team.record }}</span>
                  </div>
                </div>
              </div>

              <div class="flex items-center gap-1.5 shrink-0">
                <span class="text-[9.5px] font-mono font-bold px-2 py-0.5 rounded bg-cyan-500/15 text-cyan-300 border border-cyan-500/40">
                  Buyer
                </span>
                <!-- Quick Delta: +X -Y -->
                <span
                  v-for="r in getTeamPickDelta(team).plus"
                  :key="`b-plus-${r}`"
                  class="px-1.5 py-0.5 rounded bg-emerald-950/60 text-emerald-400 border border-emerald-500/40 text-[10.5px] font-mono font-bold"
                  :title="`Acquired Round ${r} pick`"
                >
                  +{{ r }}
                </span>
                <span
                  v-for="r in getTeamPickDelta(team).minus"
                  :key="`b-minus-${r}`"
                  class="px-1.5 py-0.5 rounded bg-rose-950/60 text-rose-400 border border-rose-500/40 text-[10.5px] font-mono font-bold"
                  :title="`Traded away Round ${r} pick`"
                >
                  -{{ r }}
                </span>
                <ChevronRight class="w-3.5 h-3.5 text-slate-500 group-hover:text-cyan-300 transition-colors" />
              </div>
            </button>
          </div>
        </div>

        <!-- Section C: Sellers (Rebuilders Accumulating Picks) -->
        <div
          v-if="sellerTeams.length > 0"
          class="space-y-2.5 pt-3 border-t border-slate-800/80"
        >
          <div class="flex flex-wrap items-center justify-between gap-1">
            <div class="text-xs font-mono font-bold uppercase tracking-wider text-purple-300 flex items-center gap-1.5">
              <span class="w-2 h-2 rounded-full bg-purple-400"></span>
              <span>Sellers ({{ sellerTeams.length }} Rebuilders · Capital Acquired)</span>
            </div>
            <span class="text-[10px] font-mono text-slate-400">+Gained / -Lost Round</span>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            <button
              v-for="team in sellerTeams"
              :key="team.team_id"
              type="button"
              class="bg-slate-950/80 border border-purple-500/20 hover:border-purple-500/50 rounded-xl p-2.5 flex items-center justify-between gap-2 transition-all group text-left cursor-pointer"
              @click="openTeamDrawer(team.team_id)"
              title="Tap to scout roster and draft picks"
            >
              <div class="flex items-center gap-2 min-w-0">
                <TeamAvatar
                  :src="team.logo_url"
                  :name="team.team_name"
                  size="xs"
                  rounded="lg"
                />
                <div class="min-w-0 leading-tight">
                  <div class="text-xs font-bold text-white truncate group-hover:text-purple-300 transition-colors">
                    {{ team.team_name }}
                  </div>
                  <div class="flex items-center gap-1.5 text-[10px] text-slate-400 truncate mt-0.5">
                    <span class="truncate">{{ team.manager_name }}</span>
                    <span class="text-slate-600">·</span>
                    <span class="font-mono font-bold text-slate-200 shrink-0">{{ team.record }}</span>
                  </div>
                </div>
              </div>

              <div class="flex items-center gap-1.5 shrink-0">
                <span class="text-[9.5px] font-mono font-bold px-2 py-0.5 rounded bg-purple-500/15 text-purple-300 border border-purple-500/40">
                  Seller
                </span>
                <!-- Quick Delta: +X -Y -->
                <span
                  v-for="r in getTeamPickDelta(team).plus"
                  :key="`s-plus-${r}`"
                  class="px-1.5 py-0.5 rounded bg-emerald-950/60 text-emerald-400 border border-emerald-500/40 text-[10.5px] font-mono font-bold"
                  :title="`Acquired Round ${r} pick`"
                >
                  +{{ r }}
                </span>
                <span
                  v-for="r in getTeamPickDelta(team).minus"
                  :key="`s-minus-${r}`"
                  class="px-1.5 py-0.5 rounded bg-rose-950/60 text-rose-400 border border-rose-500/40 text-[10.5px] font-mono font-bold"
                  :title="`Traded away Round ${r} pick`"
                >
                  -{{ r }}
                </span>
                <ChevronRight class="w-3.5 h-3.5 text-slate-500 group-hover:text-purple-300 transition-colors" />
              </div>
            </button>
          </div>
        </div>
      </div>

      <!-- Position Tier Legend -->
      <div
        class="bg-slate-900/70 border border-slate-800 rounded-2xl px-3.5 py-2.5 flex flex-wrap items-center gap-1.5 text-[10px] font-mono"
      >
        <span class="uppercase font-bold text-slate-400 mr-1">Position Tiers:</span>
        <span class="px-2 py-0.5 rounded border bg-amber-500/15 text-amber-200 border-amber-400/50 font-bold">
          T1 Elite (#1–3)
        </span>
        <span class="px-2 py-0.5 rounded border bg-emerald-500/15 text-emerald-200 border-emerald-500/45 font-bold">
          T2 High-End (#4–8)
        </span>
        <span class="px-2 py-0.5 rounded border bg-sky-500/15 text-sky-200 border-sky-500/40 font-bold">
          T3 Starter (#9–16)
        </span>
        <span class="px-2 py-0.5 rounded border bg-indigo-500/15 text-indigo-200 border-indigo-500/40 font-bold">
          T4 Flex (#17–24)
        </span>
        <span class="px-2 py-0.5 rounded border bg-slate-950/90 text-slate-400 border-slate-800 font-bold">
          T5 Depth (#25+)
        </span>
      </div>

      <!-- 2. Team Cards Grid (1 Column on Mobile & Tablet, 2 Columns on Desktop) -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-3.5">
        <div
          v-for="teamSummary in displayedTeamsSummary"
          :id="`team-card-${teamSummary.team_id}`"
          :key="teamSummary.team_id"
          class="bg-slate-900/80 border border-slate-800 rounded-2xl p-3.5 sm:p-4 space-y-3.5 shadow-md transition-all"
        >
          <!-- Team Header & Market Classification (Tap to Open Drawer) -->
          <button
            type="button"
            class="w-full flex items-center justify-between gap-2 border-b border-slate-800/80 pb-2.5 text-left cursor-pointer group"
            @click="openTeamDrawer(teamSummary.team_id)"
          >
            <div class="flex items-center gap-2.5 min-w-0">
              <TeamAvatar
                :src="teamSummary.logo_url"
                :name="teamSummary.team_name"
                size="md"
                rounded="xl"
              />
              <div class="min-w-0 leading-tight">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="text-sm font-bold text-white truncate group-hover:text-emerald-300 transition-colors">
                    {{ teamSummary.team_name }}
                  </span>
                  <span class="px-2 py-0.5 rounded-md bg-slate-950 border border-slate-700/80 text-[11px] font-mono font-black text-white shrink-0">
                    {{ teamSummary.record }}
                  </span>
                </div>
                <div class="flex items-center gap-1.5 text-xs text-slate-400 truncate mt-0.5">
                  <span class="truncate">{{ teamSummary.manager_name }}</span>
                  <span class="text-slate-600">·</span>
                  <span class="font-mono text-[11px] text-slate-400 shrink-0">{{ teamSummary.points_for.toFixed(1) }} PF</span>
                </div>
              </div>
            </div>

            <!-- Market Role & Quick Deltas -->
            <div class="flex items-center gap-1.5 shrink-0 flex-wrap justify-end">
              <span
                v-if="getTeamRole(teamSummary) === 'READY'"
                class="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/40"
              >
                Ready to Trade
              </span>
              <span
                v-else-if="getTeamRole(teamSummary) === 'BUYER'"
                class="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-cyan-500/15 text-cyan-300 border border-cyan-500/40"
              >
                Buyer
              </span>
              <span
                v-else-if="getTeamRole(teamSummary) === 'SELLER'"
                class="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-purple-500/15 text-purple-300 border border-purple-500/40"
              >
                Seller
              </span>

              <!-- Quick Delta Chips: +X -Y -->
              <span
                v-for="r in getTeamPickDelta(teamSummary).plus"
                :key="`card-plus-${r}`"
                class="px-1.5 py-0.5 rounded bg-emerald-950/60 text-emerald-400 border border-emerald-500/40 text-[10px] font-mono font-bold"
                :title="`Acquired Round ${r} pick`"
              >
                +{{ r }}
              </span>
              <span
                v-for="r in getTeamPickDelta(teamSummary).minus"
                :key="`card-minus-${r}`"
                class="px-1.5 py-0.5 rounded bg-rose-950/60 text-rose-400 border border-rose-500/40 text-[10px] font-mono font-bold"
                :title="`Traded away Round ${r} pick`"
              >
                -{{ r }}
              </span>
              <ChevronRight class="w-4 h-4 text-slate-500 group-hover:text-white transition-colors" />
            </div>
          </button>

          <!-- 16-Round Draft Capital Inventory in Proper Round Order -->
          <div class="space-y-2">
            <div class="flex items-center justify-between gap-2">
              <div class="text-[10px] font-mono uppercase text-slate-400 font-semibold tracking-wider">
                Draft Capital Inventory (16 Rounds)
              </div>
              <span class="text-[10px] font-mono text-slate-500">Tap pick to trace</span>
            </div>

            <!-- All Picks Sorted in Strict Round Order (Acquired Picks sit right after their round!) -->
            <div class="flex flex-wrap gap-1.5">
              <button
                v-for="(slot, sIdx) in getOrderedTeamInventory(teamSummary)"
                :key="`${teamSummary.team_id}-${slot.round}-${slot.originalTeam.team_id}-${sIdx}`"
                type="button"
                class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-mono border transition-all cursor-pointer text-left"
                :class="
                  slot.isTradedAway
                    ? 'bg-rose-950/40 text-rose-300 border-rose-500/50 shadow-sm hover:border-rose-400'
                    : slot.isAcquired
                    ? 'font-bold bg-emerald-950/40 text-emerald-300 border-emerald-500/40 shadow-sm hover:border-emerald-400'
                    : 'bg-slate-950 text-slate-300 border-slate-800 hover:border-slate-700'
                "
                @click="openPickTrace(slot.round, slot.originalTeam, slot.currentTeam)"
                :title="
                  slot.isTradedAway
                    ? `Round ${slot.round} pick traded away to ${slot.currentTeam.manager_name || slot.currentTeam.team_name}. Click to trace.`
                    : slot.isAcquired
                    ? `Acquired from ${slot.originalTeam.manager_name || slot.originalTeam.team_name}. Click to trace.`
                    : `Round ${slot.round} pick owned. Click to inspect.`
                "
              >
                <span v-if="slot.isAcquired">+</span>
                <span :class="{ 'line-through font-black text-rose-400': slot.isTradedAway }">
                  Rd {{ slot.round }}
                </span>
                <span
                  v-if="slot.isAcquired"
                  class="text-[10px] text-emerald-400 font-sans font-medium"
                >
                  ({{ slot.originalTeam.manager_name?.split(' ')[0] || slot.originalTeam.team_name }})
                </span>
                <span
                  v-else-if="slot.isTradedAway"
                  class="text-[10px] text-rose-300 font-sans font-medium"
                >
                  → {{ slot.currentTeam.manager_name?.split(' ')[0] || slot.currentTeam.team_name }}
                </span>
              </button>
            </div>
          </div>

          <!-- Active Roster Highlighted by Position Tier (QB / RB / WR / TE / D/ST / K) -->
          <div
            v-if="teamSummary.roster_players && teamSummary.roster_players.length > 0"
            class="bg-slate-950/60 border border-slate-800/80 rounded-xl p-2.5 sm:p-3 space-y-2"
          >
            <div class="flex items-center justify-between gap-2">
              <div class="text-[10px] font-mono uppercase text-slate-400 font-semibold tracking-wider">
                Roster by Position Tier
              </div>
              <div class="flex items-center gap-1 text-[9.5px] font-mono">
                <span
                  v-if="getTeamTierCounts(teamSummary).t1 > 0"
                  class="px-1.5 py-0.2 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30 font-bold"
                >
                  {{ getTeamTierCounts(teamSummary).t1 }} T1
                </span>
                <span
                  v-if="getTeamTierCounts(teamSummary).t2 > 0"
                  class="px-1.5 py-0.2 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 font-bold"
                >
                  {{ getTeamTierCounts(teamSummary).t2 }} T2
                </span>
                <span
                  v-if="getTeamTierCounts(teamSummary).t3 > 0"
                  class="px-1.5 py-0.2 rounded bg-sky-500/15 text-sky-300 border border-sky-500/30 font-bold"
                >
                  {{ getTeamTierCounts(teamSummary).t3 }} T3
                </span>
                <span
                  v-if="getTeamTierCounts(teamSummary).t4 > 0"
                  class="px-1.5 py-0.2 rounded bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 font-bold"
                >
                  {{ getTeamTierCounts(teamSummary).t4 }} T4
                </span>
              </div>
            </div>

            <div class="space-y-1.5">
              <div
                v-for="pos in getTeamPositions(teamSummary)"
                :key="pos"
                class="flex items-start gap-2"
              >
                <span
                  class="w-9 shrink-0 text-center py-0.5 rounded text-[10px] font-mono font-bold mt-0.5"
                  :class="getPositionClass(pos)"
                >
                  {{ pos }}
                </span>

                <div class="flex flex-wrap gap-1.5 flex-1">
                  <div
                    v-for="player in getPlayersByPosition(teamSummary, pos)"
                    :key="player.player_id"
                    class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg border text-xs transition-colors"
                    :class="getTierPillClass(player.tier)"
                    :title="`${player.full_name} (${player.pro_team || 'FA'}) · ${player.tier_label || 'Depth'} · ${player.ppg.toFixed(1)} PPG (${player.total_points.toFixed(1)} total pts)`"
                  >
                    <span
                      class="px-1 py-0.2 rounded text-[9px] font-mono font-black border"
                      :class="getTierBadgeClass(player.tier)"
                    >
                      T{{ player.tier }}
                    </span>
                    <span class="font-semibold truncate max-w-[115px] sm:max-w-[140px]">
                      {{ player.full_name }}
                    </span>
                    <span
                      v-if="player.positional_rank"
                      class="text-[10px] font-mono opacity-85"
                    >
                      #{{ player.positional_rank }}
                    </span>
                    <span class="text-[10px] font-mono opacity-75">
                      {{ player.ppg.toFixed(1) }}
                    </span>
                    <span
                      v-if="player.slot_position === 'IR'"
                      class="px-1 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40 text-[8.5px] font-mono font-bold"
                    >
                      IR
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ===================================================================== -->
    <!-- VIEW B: TRADED PICKS (PURE TRADE FEED: MOST RECENT FIRST)             -->
    <!-- ===================================================================== -->
    <div v-else-if="activeSubView === 'trades'" class="space-y-4">
      <!-- Section Header -->
      <div class="flex items-center justify-between gap-2 bg-slate-900/60 border border-slate-800 rounded-xl px-4 py-2.5">
        <div class="flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
          <span class="text-xs font-mono font-bold text-white uppercase tracking-wider">
            All Traded Pick Transactions
          </span>
          <span class="text-[11px] font-mono text-slate-400">
            ({{ groupedTrades.length }} confirmed · most recent first)
          </span>
        </div>
        <span class="text-[10px] font-mono text-slate-500 hidden sm:inline">
          Click any trade to open full details
        </span>
      </div>

      <!-- Empty State for Traded Picks -->
      <div
        v-if="groupedTrades.length === 0"
        class="py-12 text-center bg-slate-900/40 border border-slate-800/80 rounded-2xl p-6 space-y-2"
      >
        <div class="text-sm font-bold text-slate-300">No Traded Picks for {{ draftData.season_year }}</div>
        <p class="text-xs text-slate-500 font-mono">
          All 12 franchises currently hold their original 16 draft picks (Rounds 1–16).
        </p>
      </div>

      <!-- Trade Cards Grouped by Transaction (Most Recent First) -->
      <div
        v-for="trade in groupedTrades"
        :key="trade.transactionId"
        class="bg-slate-900/90 border border-slate-800 hover:border-slate-700 hover:bg-slate-900/95 rounded-2xl p-4 shadow-md space-y-3.5 transition-all cursor-pointer group"
        @click="openFullTrade(trade)"
      >
        <!-- Trade Context Header -->
        <div class="flex items-center justify-between gap-2 border-b border-slate-800/80 pb-2.5">
          <div class="flex items-center gap-2">
            <span class="w-1.5 h-3.5 rounded-full bg-emerald-500 shrink-0"></span>
            <span class="text-xs font-mono font-bold text-white uppercase">
              {{ trade.week ? `Week ${trade.week} Trade` : 'Preseason Trade' }}
            </span>
            <span v-if="trade.executedAt" class="text-[11px] text-slate-400 font-mono">
              · {{ formatDate(trade.executedAt) }}
            </span>
          </div>

          <div class="flex items-center gap-2">
            <button
              type="button"
              class="inline-flex items-center gap-1 text-[11px] font-mono font-bold px-2 py-0.5 rounded bg-indigo-950/60 text-indigo-300 border border-indigo-500/30 group-hover:border-indigo-400/60 transition-colors cursor-pointer"
              @click.stop="openFullTrade(trade)"
            >
              <span>View Full Trade</span>
              <ArrowUpRight class="w-3 h-3 text-indigo-400" />
            </button>
          </div>
        </div>

        <!-- Cleanly List the Changes per Franchise -->
        <div class="space-y-2.5">
          <div
            v-for="side in trade.sides"
            :key="side.team.team_id"
            class="bg-slate-950/80 border border-slate-800/90 rounded-xl p-3 space-y-2.5"
          >
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
              <!-- Franchise Identity -->
              <div class="flex items-center gap-2.5 min-w-0">
                <TeamAvatar
                  :src="side.team.logo_url"
                  :name="side.team.team_name"
                  size="sm"
                  rounded="lg"
                />
                <div class="min-w-0 leading-tight">
                  <div class="text-xs sm:text-sm font-bold text-white truncate">
                    {{ side.team.team_name }}
                  </div>
                  <div class="text-[11px] text-slate-400 truncate">
                    {{ side.team.manager_name }}
                  </div>
                </div>
              </div>

              <!-- Changes: Lost and Gained Picks -->
              <div class="flex flex-wrap items-center gap-2 text-xs font-mono">
                <!-- Lost Pick Pill(s) -->
                <button
                  v-for="lostPick in side.lost"
                  :key="`lost-${lostPick.round}-${lostPick.originalTeam.team_id}`"
                  type="button"
                  class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-rose-950/40 text-rose-300 border border-rose-500/40 hover:border-rose-400 transition-colors cursor-pointer text-left"
                  @click.stop="openPickTrace(lostPick.round, lostPick.originalTeam)"
                  :title="`Click to trace Round ${lostPick.round} pick lineage`"
                >
                  <span class="text-rose-400 font-bold uppercase text-[10px]">Lost</span>
                  <span class="font-bold">
                    {{ lostPick.originalTeam.team_id === side.team.team_id ? `their ${getOrdinal(lostPick.round)}` : `${lostPick.originalTeam.manager_name?.split(' ')[0] || lostPick.originalTeam.team_name}'s ${getOrdinal(lostPick.round)}` }}
                  </span>
                  <ChevronRight class="w-3 h-3 text-rose-400 shrink-0 opacity-70" />
                </button>

                <!-- Gained Pick Pill(s) -->
                <button
                  v-for="gainedPick in side.gained"
                  :key="`gained-${gainedPick.round}-${gainedPick.originalTeam.team_id}`"
                  type="button"
                  class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-emerald-950/40 text-emerald-300 border border-emerald-500/40 hover:border-emerald-400 transition-colors cursor-pointer text-left"
                  @click.stop="openPickTrace(gainedPick.round, gainedPick.originalTeam)"
                  :title="`Click to trace Round ${gainedPick.round} pick lineage`"
                >
                  <span class="text-emerald-400 font-bold uppercase text-[10px]">Gained</span>
                  <span class="font-bold">
                    {{ gainedPick.originalTeam.team_id === side.team.team_id ? `their ${getOrdinal(gainedPick.round)}` : `${gainedPick.originalTeam.manager_name?.split(' ')[0] || gainedPick.originalTeam.team_name}'s ${getOrdinal(gainedPick.round)}` }}
                  </span>
                  <ChevronRight class="w-3 h-3 text-emerald-400 shrink-0 opacity-70" />
                </button>
              </div>
            </div>

            <!-- Also Show Players Involved in this swap! -->
            <div
              v-if="side.playersGained.length > 0"
              class="pt-2 border-t border-slate-800/80 flex items-center gap-1.5 flex-wrap"
            >
              <span class="text-[10px] font-mono uppercase text-slate-400 font-semibold tracking-wider mr-1">
                Players Involved:
              </span>
              <span
                v-for="player in side.playersGained"
                :key="player.player_id ?? player.full_name"
                class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-200"
              >
                <span
                  class="px-1 py-0.2 rounded text-[9.5px] font-mono font-bold"
                  :class="getPositionClass(player.default_position)"
                >
                  {{ player.default_position || 'FLEX' }}
                </span>
                <span class="font-semibold text-white">{{ player.full_name }}</span>
                <span v-if="player.pro_team" class="text-[10px] text-slate-400 font-mono">{{ player.pro_team }}</span>
              </span>
            </div>
          </div>
        </div>

        <div class="text-[10px] font-mono text-slate-500 flex items-center justify-between pt-1">
          <span class="text-indigo-400/80 group-hover:text-indigo-300 transition-colors">
            Tap anywhere to view the complete trade autopsy & player stats
          </span>
          <span class="text-slate-600 truncate max-w-[120px]">{{ trade.transactionId.slice(0, 8) }}</span>
        </div>
      </div>
    </div>

    <!-- ===================================================================== -->
    <!-- VIEW C: BY ROUND (ROUNDS 1–16)                                        -->
    <!-- ===================================================================== -->
    <div v-else class="space-y-4">
      <!-- Round Filter Pills (Wrapping for Mobile-Friendly Touch) -->
      <div class="bg-slate-900/70 border border-slate-800 rounded-2xl p-3 sm:p-3.5 space-y-2.5">
        <div class="flex items-center justify-between text-xs font-mono text-slate-400">
          <div class="flex items-center gap-2">
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
            <span class="font-bold uppercase tracking-wider text-slate-200">Rounds 1–16</span>
          </div>
          <div class="text-[10px] text-slate-400 flex items-center gap-1.5">
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            <span>Traded Pick</span>
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-1.5 select-none">
          <button
            type="button"
            class="px-3 py-1.5 rounded-xl text-xs font-mono font-bold transition-all border cursor-pointer min-h-[34px] flex items-center justify-center"
            :class="
              selectedRound === null
                ? 'bg-emerald-500 text-slate-950 border-emerald-400 shadow-sm font-black'
                : 'bg-slate-950 text-slate-300 hover:text-white border-slate-800 hover:border-slate-700'
            "
            @click="selectRoundPill(null)"
          >
            All Rounds
          </button>

          <button
            v-for="r in draftData.total_rounds"
            :key="r"
            type="button"
            class="px-2.5 py-1.5 rounded-xl text-xs font-mono font-bold transition-all border flex items-center justify-center gap-1.5 cursor-pointer min-h-[34px]"
            :class="
              selectedRound === r
                ? 'bg-emerald-500 text-slate-950 border-emerald-400 shadow-sm font-black'
                : draftData.rounds[r - 1]?.picks.some((p) => p.is_traded)
                ? 'bg-slate-950 text-emerald-300 border-emerald-500/40 hover:border-emerald-400'
                : 'bg-slate-950 text-slate-300 hover:text-white border-slate-800 hover:border-slate-700'
            "
            @click="selectRoundPill(r)"
          >
            <span>Rd {{ r }}</span>
            <span
              v-if="draftData.rounds[r - 1]?.picks.some((p) => p.is_traded)"
              class="w-1.5 h-1.5 rounded-full"
              :class="selectedRound === r ? 'bg-slate-950' : 'bg-emerald-400'"
              title="Has Traded Pick"
            ></span>
          </button>
        </div>
      </div>

      <!-- Rounds List -->
      <div class="space-y-4">
        <section
          v-for="roundObj in filteredRounds"
          :key="roundObj.round"
          class="bg-slate-900/60 border border-slate-800/90 rounded-2xl p-3 sm:p-4 space-y-3"
        >
          <div class="flex items-center justify-between border-b border-slate-800/80 pb-2">
            <div class="flex items-center gap-2">
              <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
              <h3 class="text-sm sm:text-base font-black text-white uppercase tracking-tight font-mono">
                Round {{ roundObj.round }} Picks
              </h3>
            </div>

            <div class="text-[11px] font-mono text-slate-400">
              <span v-if="roundObj.picks.some((p) => p.is_traded)" class="text-emerald-400 font-bold">
                {{ roundObj.picks.filter((p) => p.is_traded).length }} Traded Pick
              </span>
              <span v-else class="text-slate-500">All 12 Original</span>
            </div>
          </div>

          <!-- Franchise Pick Holders -->
          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            <button
              v-for="(pick, pIdx) in roundObj.picks"
              :key="pIdx"
              type="button"
              class="rounded-xl p-2.5 transition-all flex items-center justify-between gap-2 border bg-slate-900/90 text-left cursor-pointer"
              :class="
                pick.is_traded
                  ? 'border-emerald-500/40 bg-emerald-950/15 hover:border-emerald-500/70'
                  : 'border-slate-800/90 hover:border-slate-700'
              "
              @click="openPickTrace(pick.round, pick.original_team, pick.current_team)"
            >
              <div class="flex items-center gap-2 min-w-0">
                <TeamAvatar
                  :src="pick.current_team.logo_url"
                  :name="pick.current_team.team_name"
                  size="xs"
                  rounded="lg"
                />
                <div class="min-w-0 leading-tight">
                  <div class="text-xs font-bold text-white truncate">
                    {{ pick.current_team.team_name }}
                  </div>
                  <div class="text-[10px] text-slate-400 truncate">
                    {{ pick.current_team.manager_name }}
                  </div>
                </div>
              </div>

              <!-- Traded pill or Original pill -->
              <div class="shrink-0 text-right">
                <span
                  v-if="pick.is_traded"
                  class="inline-block text-[9.5px] font-mono font-bold px-1.5 py-0.5 rounded bg-emerald-950/50 text-emerald-400 border border-emerald-500/30"
                  :title="`Originally belonging to ${pick.original_team.manager_name || pick.original_team.team_name}`"
                >
                  From {{ pick.original_team.manager_name?.split(' ')[0] || 'Team' }}
                </span>
                <span
                  v-else
                  class="text-[10px] font-mono text-slate-500"
                >
                  Own Pick
                </span>
              </div>
            </button>
          </div>
        </section>
      </div>
    </div>

    <!-- ===================================================================== -->
    <!-- DRAWER 1: SLIDE-UP TEAM SCOUTING & PICK INVENTORY DRAWER              -->
    <!-- ===================================================================== -->
    <SwipeDrawer
      v-model="teamDrawerOpen"
      :title="selectedDrawerTeam ? selectedDrawerTeam.team_name : 'Team Scouting'"
      :subtitle="selectedDrawerTeam ? `${selectedDrawerTeam.manager_name} · ${selectedDrawerTeam.record} (${selectedDrawerTeam.points_for.toFixed(1)} PF)` : ''"
      max-height="max-h-[88vh]"
    >
      <div v-if="selectedDrawerTeam" class="p-4 sm:p-5 space-y-4">
        <!-- 1. Quick Franchise Switcher & Market Status Bar -->
        <div class="bg-slate-900 border border-slate-800 rounded-2xl p-3.5 space-y-3">
          <div class="flex items-center justify-between gap-2">
            <button
              type="button"
              class="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl bg-slate-950 border border-slate-800 hover:border-slate-700 text-xs font-mono font-bold text-slate-300 hover:text-white transition-colors cursor-pointer"
              @click="stepDrawerTeam(-1)"
            >
              <ChevronLeft class="w-3.5 h-3.5" />
              <span>Prev Team</span>
            </button>

            <div class="flex items-center gap-1.5 flex-wrap justify-center">
              <span
                v-if="getTeamRole(selectedDrawerTeam) === 'READY'"
                class="text-[10.5px] font-mono font-bold px-2.5 py-0.5 rounded-lg bg-emerald-500/15 text-emerald-300 border border-emerald-500/40"
              >
                Ready to Trade
              </span>
              <span
                v-else-if="getTeamRole(selectedDrawerTeam) === 'BUYER'"
                class="text-[10.5px] font-mono font-bold px-2.5 py-0.5 rounded-lg bg-cyan-500/15 text-cyan-300 border border-cyan-500/40"
              >
                Buyer
              </span>
              <span
                v-else-if="getTeamRole(selectedDrawerTeam) === 'SELLER'"
                class="text-[10.5px] font-mono font-bold px-2.5 py-0.5 rounded-lg bg-purple-500/15 text-purple-300 border border-purple-500/40"
              >
                Seller
              </span>

              <span
                v-for="r in getTeamPickDelta(selectedDrawerTeam).plus"
                :key="`d-plus-${r}`"
                class="px-1.5 py-0.5 rounded bg-emerald-950/60 text-emerald-400 border border-emerald-500/40 text-xs font-mono font-bold"
              >
                +{{ r }}
              </span>
              <span
                v-for="r in getTeamPickDelta(selectedDrawerTeam).minus"
                :key="`d-minus-${r}`"
                class="px-1.5 py-0.5 rounded bg-rose-950/60 text-rose-400 border border-rose-500/40 text-xs font-mono font-bold"
              >
                -{{ r }}
              </span>
            </div>

            <button
              type="button"
              class="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl bg-slate-950 border border-slate-800 hover:border-slate-700 text-xs font-mono font-bold text-slate-300 hover:text-white transition-colors cursor-pointer"
              @click="stepDrawerTeam(1)"
            >
              <span>Next Team</span>
              <ChevronRight class="w-3.5 h-3.5" />
            </button>
          </div>

          <!-- Franchise Identity Row -->
          <div class="flex items-center justify-between gap-3 pt-2.5 border-t border-slate-800/80">
            <div class="flex items-center gap-2.5 min-w-0">
              <TeamAvatar
                :src="selectedDrawerTeam.logo_url"
                :name="selectedDrawerTeam.team_name"
                size="md"
                rounded="xl"
              />
              <div class="min-w-0">
                <div class="text-sm sm:text-base font-bold text-white truncate">
                  {{ selectedDrawerTeam.team_name }}
                </div>
                <div class="text-xs text-slate-400 truncate">
                  {{ selectedDrawerTeam.manager_name }}
                </div>
              </div>
            </div>

            <div class="flex items-center gap-2 shrink-0">
              <div class="text-right">
                <div class="text-xs font-mono font-black text-white px-2.5 py-1 rounded-lg bg-slate-950 border border-slate-800">
                  {{ selectedDrawerTeam.record }} · {{ selectedDrawerTeam.points_for.toFixed(1) }} PF
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 2. Season Pick Swap Summary (Shown for Buyers & Sellers) -->
        <div
          v-if="selectedDrawerTeam.picks_acquired.length > 0 || selectedDrawerTeam.picks_traded_away.length > 0"
          class="bg-slate-900/90 border border-slate-800 rounded-2xl p-3.5 space-y-2.5"
        >
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="text-[10.5px] font-mono uppercase text-slate-300 font-bold tracking-wider">
              {{ draftData.season_year }} Pick Swap Summary
            </div>
            <button
              v-for="tGroup in getTeamTrades(selectedDrawerTeam.team_id)"
              :key="tGroup.transactionId"
              type="button"
              class="inline-flex items-center gap-1 text-[11px] font-mono font-bold px-2.5 py-1 rounded-lg bg-indigo-950/60 text-indigo-300 border border-indigo-500/40 hover:border-indigo-400 cursor-pointer"
              @click="openFullTrade(tGroup)"
            >
              <span>View Full Trade Details</span>
              <ArrowUpRight class="w-3.5 h-3.5 text-indigo-400" />
            </button>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <!-- Acquired Picks -->
            <button
              v-for="acqPick in selectedDrawerTeam.picks_acquired"
              :key="`d-acq-${acqPick.round}-${acqPick.original_team.team_id}`"
              type="button"
              class="flex items-center justify-between gap-2 p-2.5 rounded-xl bg-slate-950 border border-emerald-500/30 hover:border-emerald-500/60 text-left cursor-pointer transition-all"
              @click="openPickTrace(acqPick.round, acqPick.original_team, acqPick.current_team)"
            >
              <div>
                <div class="text-[9.5px] font-mono uppercase text-emerald-400 font-bold">Acquired Pick</div>
                <div class="text-xs font-mono font-black text-white mt-0.5">
                  +Round {{ acqPick.round }}
                </div>
              </div>
              <div class="text-right min-w-0">
                <div class="text-[9.5px] font-mono uppercase text-slate-400">From</div>
                <div class="text-xs font-bold text-slate-200 truncate">
                  {{ acqPick.original_team.team_name }}
                </div>
              </div>
            </button>

            <!-- Traded Away Picks -->
            <button
              v-for="awayPick in selectedDrawerTeam.picks_traded_away"
              :key="`d-away-${awayPick.round}-${awayPick.original_team.team_id}`"
              type="button"
              class="flex items-center justify-between gap-2 p-2.5 rounded-xl bg-slate-950 border border-rose-500/30 hover:border-rose-500/60 text-left cursor-pointer transition-all"
              @click="openPickTrace(awayPick.round, awayPick.original_team, awayPick.current_team)"
            >
              <div>
                <div class="text-[9.5px] font-mono uppercase text-rose-400 font-bold">Traded Away</div>
                <div class="text-xs font-mono font-black text-rose-300 line-through mt-0.5">
                  -Round {{ awayPick.round }}
                </div>
              </div>
              <div class="text-right min-w-0">
                <div class="text-[9.5px] font-mono uppercase text-emerald-400">Held By</div>
                <div class="text-xs font-bold text-slate-200 truncate">
                  {{ awayPick.current_team.team_name }}
                </div>
              </div>
            </button>
          </div>
        </div>

        <!-- 3. 16-Round Draft Capital Inventory -->
        <div class="bg-slate-900 border border-slate-800 rounded-2xl p-3.5 space-y-2.5">
          <div class="flex items-center justify-between gap-2">
            <div class="text-xs font-mono uppercase text-white font-bold tracking-wider">
              {{ draftData.season_year }} Draft Capital Inventory (16 Rounds)
            </div>
            <span class="text-[10px] font-mono text-slate-400">Tap any pick to trace</span>
          </div>

          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="(slot, sIdx) in getOrderedTeamInventory(selectedDrawerTeam)"
              :key="`drawer-slot-${selectedDrawerTeam.team_id}-${slot.round}-${slot.originalTeam.team_id}-${sIdx}`"
              type="button"
              class="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-mono border transition-all cursor-pointer text-left"
              :class="
                slot.isTradedAway
                  ? 'bg-rose-950/40 text-rose-300 border-rose-500/50 shadow-sm hover:border-rose-400'
                  : slot.isAcquired
                  ? 'font-bold bg-emerald-950/40 text-emerald-300 border-emerald-500/40 shadow-sm hover:border-emerald-400'
                  : 'bg-slate-950 text-slate-300 border-slate-800 hover:border-slate-700'
              "
              @click="openPickTrace(slot.round, slot.originalTeam, slot.currentTeam)"
            >
              <span v-if="slot.isAcquired">+</span>
              <span :class="{ 'line-through font-black text-rose-400': slot.isTradedAway }">
                Rd {{ slot.round }}
              </span>
              <span
                v-if="slot.isAcquired"
                class="text-[10px] text-emerald-400 font-sans font-medium"
              >
                ({{ slot.originalTeam.manager_name?.split(' ')[0] || slot.originalTeam.team_name }})
              </span>
              <span
                v-else-if="slot.isTradedAway"
                class="text-[10px] text-rose-300 font-sans font-medium"
              >
                → {{ slot.currentTeam.manager_name?.split(' ')[0] || slot.currentTeam.team_name }}
              </span>
            </button>
          </div>
        </div>

        <!-- 4. Active Roster Highlighted by Position Tier -->
        <div
          v-if="selectedDrawerTeam.roster_players && selectedDrawerTeam.roster_players.length > 0"
          class="bg-slate-900 border border-slate-800 rounded-2xl p-3.5 space-y-3"
        >
          <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-2">
            <div class="text-xs font-mono uppercase text-white font-bold tracking-wider">
              Full Roster by Position Tier
            </div>
            <div class="flex flex-wrap items-center gap-1 text-[9.5px] font-mono">
              <span class="px-1.5 py-0.5 rounded border bg-amber-500/15 text-amber-200 border-amber-400/50 font-bold">
                T1 Elite
              </span>
              <span class="px-1.5 py-0.5 rounded border bg-emerald-500/15 text-emerald-200 border-emerald-500/45 font-bold">
                T2 High
              </span>
              <span class="px-1.5 py-0.5 rounded border bg-sky-500/15 text-sky-200 border-sky-500/40 font-bold">
                T3 Starter
              </span>
              <span class="px-1.5 py-0.5 rounded border bg-indigo-500/15 text-indigo-200 border-indigo-500/40 font-bold">
                T4 Flex
              </span>
              <span class="px-1.5 py-0.5 rounded border bg-slate-950 text-slate-400 border-slate-800 font-bold">
                T5 Depth
              </span>
            </div>
          </div>

          <div class="space-y-2">
            <div
              v-for="pos in getTeamPositions(selectedDrawerTeam)"
              :key="`drawer-pos-${pos}`"
              class="flex items-start gap-2"
            >
              <span
                class="w-9 shrink-0 text-center py-0.5 rounded text-[10px] font-mono font-bold mt-0.5"
                :class="getPositionClass(pos)"
              >
                {{ pos }}
              </span>

              <div class="flex flex-wrap gap-1.5 flex-1">
                <div
                  v-for="player in getPlayersByPosition(selectedDrawerTeam, pos)"
                  :key="`drawer-p-${player.player_id}`"
                  class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs transition-colors"
                  :class="getTierPillClass(player.tier)"
                >
                  <span
                    class="px-1 py-0.2 rounded text-[9px] font-mono font-black border"
                    :class="getTierBadgeClass(player.tier)"
                  >
                    T{{ player.tier }}
                  </span>
                  <span class="font-semibold text-white">
                    {{ player.full_name }}
                  </span>
                  <span
                    v-if="player.positional_rank"
                    class="text-[10px] font-mono opacity-85"
                  >
                    #{{ player.positional_rank }}
                  </span>
                  <span class="text-[10px] font-mono opacity-80">
                    {{ player.ppg.toFixed(1) }} PPG
                  </span>
                  <span
                    v-if="player.slot_position === 'IR'"
                    class="px-1 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40 text-[8.5px] font-mono font-bold"
                  >
                    IR
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </SwipeDrawer>

    <!-- ===================================================================== -->
    <!-- DRAWER 2: PICK LINEAGE & CHAIN OF CUSTODY (TRACE PICK THROUGH TRADES) -->
    <!-- ===================================================================== -->
    <SwipeDrawer
      v-model="drawerOpen"
      :title="selectedPickTrace ? `2027 Round ${selectedPickTrace.round} Pick Lineage` : 'Pick Lineage'"
      subtitle="Chain of custody across all trades"
      max-height="max-h-[85vh]"
    >
      <div v-if="selectedPickTrace" class="p-4 sm:p-5 space-y-4">
        <!-- Pick Overview Card -->
        <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-3">
          <div class="flex items-center justify-between gap-2 border-b border-slate-800/80 pb-2.5">
            <div>
              <div class="text-[10px] font-mono uppercase text-slate-400">Asset Identity</div>
              <div class="text-base sm:text-lg font-black text-white font-mono">
                2027 Round {{ selectedPickTrace.round }} Pick
              </div>
            </div>

            <span class="px-2.5 py-1 rounded-lg text-xs font-mono font-bold bg-emerald-950/60 text-emerald-400 border border-emerald-500/40">
              {{ selectedPickTrace.hops.length > 1 ? `${selectedPickTrace.hops.length - 1} Trade Hop${selectedPickTrace.hops.length - 1 > 1 ? 's' : ''}` : 'Untraded' }}
            </span>
          </div>

          <!-- Origin & Current Owner Comparison -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
            <div class="bg-slate-950 p-2.5 rounded-xl border border-slate-800">
              <div class="text-[10px] font-mono uppercase text-slate-400 font-semibold">Original Owner</div>
              <div class="text-xs font-bold text-white truncate mt-1">
                {{ selectedPickTrace.originalTeam.team_name }}
              </div>
              <div class="text-[11px] text-slate-400 truncate">
                {{ selectedPickTrace.originalTeam.manager_name }}
              </div>
            </div>

            <div class="bg-slate-950 p-2.5 rounded-xl border border-emerald-500/30">
              <div class="text-[10px] font-mono uppercase text-emerald-400 font-semibold">Current Holder</div>
              <div class="text-xs font-bold text-white truncate mt-1">
                {{ selectedPickTrace.currentTeam.team_name }}
              </div>
              <div class="text-[11px] text-slate-400 truncate">
                {{ selectedPickTrace.currentTeam.manager_name }}
              </div>
            </div>
          </div>
        </div>

        <!-- Step-by-Step Movement Stepper (Chain of Custody) -->
        <div class="space-y-2">
          <div class="text-xs font-mono font-bold uppercase text-slate-400 tracking-wider">
            Movement History (Chain of Custody)
          </div>

          <div class="relative pl-6 space-y-4 before:content-[''] before:absolute before:left-2.5 before:top-3 before:bottom-3 before:w-0.5 before:bg-slate-800">
            <div
              v-for="hop in selectedPickTrace.hops"
              :key="hop.step"
              class="relative space-y-1.5"
            >
              <!-- Timeline Pin -->
              <span
                class="absolute -left-6 top-1 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-mono font-bold border"
                :class="
                  hop.action === 'ORIGIN'
                    ? 'bg-slate-800 text-slate-300 border-slate-700'
                    : 'bg-emerald-500 text-slate-950 border-emerald-400'
                "
              >
                {{ hop.step }}
              </span>

              <!-- Hop Content Card -->
              <div class="bg-slate-900 border border-slate-800 rounded-xl p-3 space-y-1.5">
                <div class="flex items-center justify-between text-xs font-mono">
                  <span
                    class="font-bold uppercase tracking-wider text-[10px]"
                    :class="hop.action === 'ORIGIN' ? 'text-slate-400' : 'text-emerald-400'"
                  >
                    {{ hop.action === 'ORIGIN' ? 'Step 1: Original Asset Allocation' : `Step ${hop.step}: Trade Execution` }}
                  </span>
                  <span v-if="hop.week" class="text-slate-400 text-[10px]">
                    Week {{ hop.week }} ({{ formatDate(hop.executedAt) }})
                  </span>
                </div>

                <!-- Origin Details -->
                <div v-if="hop.action === 'ORIGIN'" class="flex items-center gap-2 pt-0.5">
                  <TeamAvatar
                    :src="hop.toTeam.logo_url"
                    :name="hop.toTeam.team_name"
                    size="xs"
                    rounded="lg"
                  />
                  <div class="text-xs text-slate-300">
                    Allocated to <strong class="text-white">{{ hop.toTeam.team_name }}</strong> ({{ hop.toTeam.manager_name }}) as their natural Round {{ selectedPickTrace.round }} pick.
                  </div>
                </div>

                <!-- Trade Hop Details -->
                <div v-else class="space-y-1.5 pt-0.5">
                  <div class="flex items-center gap-2 text-xs">
                    <span class="text-rose-400 font-semibold">{{ hop.fromTeam?.manager_name || hop.fromTeam?.team_name }}</span>
                    <ArrowRight class="w-3.5 h-3.5 text-slate-500 shrink-0" />
                    <span class="text-emerald-400 font-semibold">{{ hop.toTeam.manager_name || hop.toTeam.team_name }}</span>
                  </div>
                  <div class="flex items-center justify-between text-[10px] font-mono text-slate-500">
                    <span v-if="hop.espnTransactionId">Receipt: {{ hop.espnTransactionId.slice(0, 8) }}</span>
                    <button
                      v-if="hop.espnTransactionId"
                      type="button"
                      class="inline-flex items-center gap-1 text-[10px] font-mono font-bold text-indigo-400 hover:text-indigo-300 cursor-pointer"
                      @click="openFullTradeById(hop.espnTransactionId)"
                    >
                      <span>View full trade swap</span>
                      <ArrowUpRight class="w-3 h-3" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </SwipeDrawer>

    <!-- 4. Drawer: Complete Trade Autopsy (All Players & Picks Exchanged) -->
    <TradeAutopsyDrawer
      v-model="fullTradeDrawerOpen"
      :trade="selectedFullTrade"
    />
  </div>
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar {
  display: none;
}
.no-scrollbar {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
</style>
