<script setup lang="ts">
import { ref, computed } from 'vue';
import type { FutureDraftData, DraftTeamRef, FutureDraftTradeLogEntry } from '@/types/api';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import SwipeDrawer from '@/components/ui/SwipeDrawer.vue';
import { ChevronRight, ArrowRight } from 'lucide-vue-next';

const props = defineProps<{
  draftData: FutureDraftData;
}>();

// Sub-view toggle: 'trades' (Traded Picks) | 'team' (16-Pick Audit) | 'round' (By Round)
const activeSubView = ref<'trades' | 'team' | 'round'>('trades');

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

// ---------------------------------------------------------------------------
// Chain of Custody resolution
// ---------------------------------------------------------------------------
function openPickTrace(round: number, originalTeam: DraftTeamRef, currentTeam?: DraftTeamRef) {
  // Find all trades involving this exact pick (round + original team) in chronological order
  const matchingTrades = props.draftData.traded_picks_log.filter(
    (entry) =>
      entry.round === round && entry.original_team.team_id === originalTeam.team_id
  );

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
}

interface CleanTradeGroup {
  transactionId: string;
  week: number | null;
  executedAt: string | null;
  sides: CleanTradeSide[];
  rawEntries: FutureDraftTradeLogEntry[];
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
    const teamMap = new Map<number, CleanTradeSide>();

    for (const entry of entries) {
      if (entry.from_team) {
        if (!teamMap.has(entry.from_team.team_id)) {
          teamMap.set(entry.from_team.team_id, {
            team: entry.from_team,
            lost: [],
            gained: [],
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
        });
      }
      teamMap.get(entry.to_team.team_id)!.gained.push({
        round: entry.round,
        originalTeam: entry.original_team,
      });
    }

    result.push({
      transactionId: txId,
      week: first.week,
      executedAt: first.executed_at,
      sides: Array.from(teamMap.values()),
      rawEntries: entries,
    });
  }

  return result;
});

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

// Teams with pick imbalances
const teamsWithImbalance = computed(() => {
  return teamsSummary.value.filter((t) => t.total_picks !== 16);
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
    <!-- 1. League Rule Banner: 16-Pick Roster Target -->
    <div
      class="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 text-xs text-slate-300 shadow-lg space-y-3"
    >
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800/80 pb-3">
        <div>
          <div class="flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
            <span class="font-black text-white text-sm uppercase tracking-tight font-mono">
              {{ draftData.season_year }} Draft Capital & 16-Pick Roster Audit
            </span>
          </div>
          <p class="text-xs text-slate-400 mt-1">
            Draft order is determined closer to the draft. By league rule, every franchise must hold exactly 16 draft picks to field a complete roster on draft day.
          </p>
        </div>

        <div class="text-[11px] font-mono text-slate-400 bg-slate-950 px-2.5 py-1 rounded-lg border border-slate-800 self-start sm:self-auto shrink-0">
          Target: <strong class="text-white">16 Picks / Team</strong>
        </div>
      </div>

      <!-- Athletic KPI Summary -->
      <div class="grid grid-cols-3 gap-2.5">
        <div class="bg-slate-950 border border-slate-800/80 rounded-xl p-2.5 text-center">
          <div class="text-[10px] font-mono uppercase text-slate-400 tracking-wider">Required Roster</div>
          <div class="text-sm sm:text-base font-black font-mono text-slate-100 mt-0.5">
            16 Picks
          </div>
        </div>

        <div class="bg-slate-950 border border-slate-800/80 rounded-xl p-2.5 text-center">
          <div class="text-[10px] font-mono uppercase text-slate-400 tracking-wider">Traded Picks</div>
          <div class="text-sm sm:text-base font-black font-mono text-emerald-400 mt-0.5">
            {{ tradedPicksCount }} Assets
          </div>
        </div>

        <div class="bg-slate-950 border border-slate-800/80 rounded-xl p-2.5 text-center">
          <div class="text-[10px] font-mono uppercase text-slate-400 tracking-wider">Roster Compliance</div>
          <div
            class="text-sm sm:text-base font-black font-mono mt-0.5"
            :class="teamsWithImbalance.length === 0 ? 'text-emerald-400' : 'text-amber-400'"
          >
            {{ teamsWithImbalance.length === 0 ? '12 of 12 Even' : `${teamsWithImbalance.length} Imbalanced` }}
          </div>
        </div>
      </div>
    </div>

    <!-- 2. Sub-Navigation Tabs: Traded Picks | 16-Pick Audit | By Round -->
    <div class="flex items-center justify-between gap-2 border-b border-slate-800/80 pb-3">
      <div class="inline-flex rounded-xl bg-slate-900 p-1 border border-slate-800/80">
        <button
          type="button"
          class="px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer min-h-[36px]"
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
          class="px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer min-h-[36px]"
          :class="
            activeSubView === 'team'
              ? 'bg-slate-800 text-white shadow-sm border border-slate-700'
              : 'text-slate-400 hover:text-white'
          "
          @click="activeSubView = 'team'"
        >
          <span>16-Pick Audit</span>
        </button>

        <button
          type="button"
          class="px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer min-h-[36px]"
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
    <!-- VIEW A: TRADED PICKS (CLEAN LIST OF CHANGES)                          -->
    <!-- ===================================================================== -->
    <div v-if="activeSubView === 'trades'" class="space-y-3.5">
      <div
        v-if="groupedTrades.length === 0"
        class="py-12 text-center bg-slate-900/40 border border-slate-800/80 rounded-2xl p-6 space-y-2"
      >
        <div class="text-sm font-bold text-slate-300">No Traded Picks for {{ draftData.season_year }}</div>
        <p class="text-xs text-slate-500 font-mono">
          All 12 franchises currently hold their original 16 draft picks (Rounds 1–16).
        </p>
      </div>

      <!-- Trade Cards Grouped by Transaction with Clear Sentences -->
      <div
        v-for="trade in groupedTrades"
        :key="trade.transactionId"
        class="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 shadow-md space-y-3.5 transition-all"
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

          <span class="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-slate-950 text-slate-400 border border-slate-800">
            Pick Exchange
          </span>
        </div>

        <!-- Cleanly List the Changes per Franchise -->
        <div class="space-y-2.5">
          <div
            v-for="side in trade.sides"
            :key="side.team.team_id"
            class="bg-slate-950/80 border border-slate-800/90 rounded-xl p-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5"
          >
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

            <!-- Changes: Lost and Gained -->
            <div class="flex flex-wrap items-center gap-2 text-xs font-mono">
              <!-- Lost Pick Pill(s) -->
              <button
                v-for="lostPick in side.lost"
                :key="`lost-${lostPick.round}-${lostPick.originalTeam.team_id}`"
                type="button"
                class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-rose-950/40 text-rose-300 border border-rose-500/40 hover:border-rose-400 transition-colors cursor-pointer text-left"
                @click="openPickTrace(lostPick.round, lostPick.originalTeam)"
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
                @click="openPickTrace(gainedPick.round, gainedPick.originalTeam)"
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
        </div>

        <div class="text-[10px] font-mono text-slate-500 flex items-center justify-between pt-1">
          <span>Tap any pick to trace its complete trade lineage</span>
          <span class="text-slate-600 truncate max-w-[120px]">{{ trade.transactionId.slice(0, 8) }}</span>
        </div>
      </div>
    </div>

    <!-- ===================================================================== -->
    <!-- VIEW B: 16-PICK ROSTER AUDIT                                          -->
    <!-- ===================================================================== -->
    <div v-else-if="activeSubView === 'team'" class="space-y-4">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3.5">
        <div
          v-for="teamSummary in teamsSummary"
          :key="teamSummary.team_id"
          class="bg-slate-900/80 border border-slate-800 rounded-2xl p-3.5 sm:p-4 space-y-3.5 shadow-md"
        >
          <!-- Team Header & 16-Pick Compliance -->
          <div class="flex items-center justify-between gap-2 border-b border-slate-800/80 pb-2.5">
            <div class="flex items-center gap-2.5 min-w-0">
              <TeamAvatar
                :src="teamSummary.logo_url"
                :name="teamSummary.team_name"
                size="md"
                rounded="xl"
              />
              <div class="min-w-0 leading-tight">
                <div class="text-sm font-bold text-white truncate">
                  {{ teamSummary.team_name }}
                </div>
                <div class="text-xs text-slate-400 truncate">
                  {{ teamSummary.manager_name }}
                </div>
              </div>
            </div>

            <!-- Total Picks vs 16 Target -->
            <div class="text-right shrink-0">
              <div class="text-sm sm:text-base font-black font-mono text-white">
                {{ teamSummary.total_picks }} <span class="text-xs font-normal text-slate-400">/ 16 Picks</span>
              </div>

              <!-- Status Badge -->
              <span
                class="inline-block text-[10px] font-mono font-bold px-2 py-0.5 rounded border mt-0.5 uppercase tracking-wide"
                :class="
                  teamSummary.total_picks === 16
                    ? 'bg-emerald-950/40 text-emerald-400 border-emerald-500/30'
                    : teamSummary.total_picks > 16
                    ? 'bg-slate-800 text-slate-200 border-slate-700'
                    : 'bg-amber-950/40 text-amber-300 border-amber-500/30'
                "
              >
                {{
                  teamSummary.total_picks === 16
                    ? 'Roster Complete'
                    : teamSummary.total_picks > 16
                    ? `+${teamSummary.total_picks - 16} Surplus`
                    : `${teamSummary.total_picks - 16} Deficit`
                }}
              </span>
            </div>
          </div>

          <!-- 16-Round Draft Capital Inventory in Proper Round Order -->
          <div class="space-y-2">
            <div class="text-[10px] font-mono uppercase text-slate-400 font-semibold tracking-wider">
              Draft Capital Inventory (16 Rounds)
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
                    ? 'line-through font-black bg-rose-950/40 text-rose-400 border-rose-500/50 shadow-sm hover:border-rose-400'
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
                <span>Rd {{ slot.round }}</span>
                <span
                  v-if="slot.isAcquired"
                  class="text-[10px] text-emerald-400 font-sans font-medium"
                >
                  ({{ slot.originalTeam.manager_name?.split(' ')[0] || slot.originalTeam.team_name }})
                </span>
              </button>
            </div>
          </div>

          <!-- Picks Traded Away: Highlight Who Currently Has It -->
          <div
            v-if="teamSummary.picks_traded_away.length > 0"
            class="pt-3 border-t border-slate-800/80 space-y-2"
          >
            <div class="text-[10px] font-mono uppercase text-slate-400 font-semibold tracking-wider">
              Picks Traded Away ({{ teamSummary.picks_traded_away.length }})
            </div>

            <div class="space-y-1.5">
              <button
                v-for="awayPick in teamSummary.picks_traded_away"
                :key="`${awayPick.round}-${awayPick.original_team.team_id}`"
                type="button"
                class="w-full flex items-center justify-between gap-3 p-2.5 rounded-xl bg-slate-950 border border-rose-500/30 hover:border-rose-500/60 transition-all cursor-pointer text-left"
                @click="openPickTrace(awayPick.round, awayPick.original_team, awayPick.current_team)"
              >
                <!-- Traded Pick Badge -->
                <div class="flex items-center gap-2">
                  <span class="px-2 py-0.5 rounded-md text-xs font-mono font-bold bg-rose-950/60 text-rose-400 border border-rose-500/40 line-through">
                    Round {{ awayPick.round }}
                  </span>
                  <span class="text-xs text-slate-300 font-medium">Original Pick</span>
                </div>

                <!-- Currently Held By Franchise -->
                <div class="flex items-center gap-2 text-right">
                  <div class="min-w-0 leading-tight">
                    <div class="text-[9.5px] font-mono uppercase text-emerald-400 font-semibold">Currently Held By</div>
                    <div class="text-xs font-bold text-white truncate">
                      {{ awayPick.current_team.team_name }}
                    </div>
                    <div class="text-[10px] text-slate-400 truncate">
                      {{ awayPick.current_team.manager_name }}
                    </div>
                  </div>
                  <TeamAvatar
                    :src="awayPick.current_team.logo_url"
                    :name="awayPick.current_team.team_name"
                    size="xs"
                    rounded="lg"
                  />
                  <ChevronRight class="w-3.5 h-3.5 text-slate-500 shrink-0 ml-0.5" />
                </div>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ===================================================================== -->
    <!-- VIEW C: BY ROUND (ROUNDS 1–16)                                        -->
    <!-- ===================================================================== -->
    <div v-else class="space-y-4">
      <!-- Round Carousel Pills -->
      <div class="flex items-center gap-1.5 overflow-x-auto py-1 no-scrollbar select-none">
        <button
          type="button"
          class="px-3 py-1.5 rounded-lg text-xs font-mono font-bold transition-all border shrink-0 cursor-pointer min-h-[32px]"
          :class="
            selectedRound === null
              ? 'bg-slate-800 text-white border-slate-700 shadow-sm'
              : 'bg-slate-900 text-slate-400 hover:text-slate-200 border-slate-800'
          "
          @click="selectRoundPill(null)"
        >
          All Rounds
        </button>

        <button
          v-for="r in draftData.total_rounds"
          :key="r"
          type="button"
          class="px-2.5 py-1.5 rounded-lg text-xs font-mono font-bold transition-all border shrink-0 flex items-center gap-1 cursor-pointer min-h-[32px]"
          :class="
            selectedRound === r
              ? 'bg-slate-800 text-white border-slate-700 shadow-sm'
              : 'bg-slate-900 text-slate-400 hover:text-slate-200 border-slate-800'
          "
          @click="selectRoundPill(r)"
        >
          <span>Rd {{ r }}</span>
          <span
            v-if="draftData.rounds[r - 1]?.picks.some((p) => p.is_traded)"
            class="w-1.5 h-1.5 rounded-full bg-emerald-400"
            title="Has Traded Pick"
          ></span>
        </button>
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
    <!-- DRAWER: PICK LINEAGE & CHAIN OF CUSTODY (TRACE PICK THROUGH TRADES)   -->
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
          <div class="grid grid-cols-2 gap-3 pt-1">
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
                <div v-else class="space-y-1 pt-0.5">
                  <div class="flex items-center gap-2 text-xs">
                    <span class="text-rose-400 font-semibold">{{ hop.fromTeam?.manager_name || hop.fromTeam?.team_name }}</span>
                    <ArrowRight class="w-3.5 h-3.5 text-slate-500 shrink-0" />
                    <span class="text-emerald-400 font-semibold">{{ hop.toTeam.manager_name || hop.toTeam.team_name }}</span>
                  </div>
                  <div v-if="hop.espnTransactionId" class="text-[10px] font-mono text-slate-500">
                    Transaction Receipt: {{ hop.espnTransactionId }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </SwipeDrawer>
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
