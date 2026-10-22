<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useLeagueMeta } from '@/composables/useLeagueMeta';
import { fetchTradeTrends } from '@/api/client';
import type { TradesTrendsResponse, TradeDetail } from '@/types/api';
import LoadingState from '@/components/ui/LoadingState.vue';
import EmptyState from '@/components/ui/EmptyState.vue';
import TradePartnerAllianceCard from '@/components/trades/TradePartnerAllianceCard.vue';
import ActiveTradersLeaderboard from '@/components/trades/ActiveTradersLeaderboard.vue';
import TradeAutopsyCard from '@/components/trades/TradeAutopsyCard.vue';
import TradeAutopsyDrawer from '@/components/trades/TradeAutopsyDrawer.vue';
import {
  ArrowLeftRight,
  Users,
  Search,
  Info,
  TrendingUp,
} from 'lucide-vue-next';

const { selectedSeason, availableSeasons } = useLeagueMeta();

const loading = ref<boolean>(false);
const error = ref<string | null>(null);
const tradeTrends = ref<TradesTrendsResponse | null>(null);

// Season filter mode: 'season' (selectedSeason) or 'all' (null)
const seasonMode = ref<'all' | 'season'>('all');

// Autopsy Drawer state
const selectedTrade = ref<TradeDetail | null>(null);
const drawerOpen = ref<boolean>(false);

// Search query for trades
const searchQuery = ref<string>('');

// Active tab in TradesView: 'trades' | 'partners' | 'leaderboard'
const activeTab = ref<'trades' | 'partners' | 'leaderboard'>('trades');

// Effective season filter to pass to API
const effectiveSeasonFilter = computed<number | null>(() => {
  if (seasonMode.value === 'all') return null;
  return selectedSeason.value;
});

// Check if the current season lacks transaction data
const lacksTransactionData = computed(() => {
  if (tradeTrends.value && !tradeTrends.value.has_transaction_data) return true;
  if (effectiveSeasonFilter.value !== null) {
    const s = availableSeasons.value.find((x) => x.season_year === effectiveSeasonFilter.value);
    if (s && !s.has_transaction_data) return true;
  }
  return false;
});

async function loadData() {
  loading.value = true;
  error.value = null;
  try {
    const data = await fetchTradeTrends(effectiveSeasonFilter.value);
    tradeTrends.value = data;
  } catch (err: unknown) {
    if (err instanceof Error) {
      error.value = err.message;
    } else {
      error.value = 'Failed to load trade records';
    }
    console.error('Error fetching trade trends:', err);
  } finally {
    loading.value = false;
  }
}

// Watch season filter changes
watch(
  [effectiveSeasonFilter, selectedSeason],
  () => {
    loadData();
  },
  { immediate: false }
);

onMounted(() => {
  loadData();
});

function openAutopsy(trade: TradeDetail) {
  selectedTrade.value = trade;
  drawerOpen.value = true;
}

// Filtered trades by search query
const filteredTrades = computed(() => {
  if (!tradeTrends.value || !tradeTrends.value.trades) return [];
  const q = searchQuery.value.trim().toLowerCase();
  if (!q) return tradeTrends.value.trades;

  return tradeTrends.value.trades.filter((trade) => {
    // Match manager names or team names
    const managerMatch = trade.sides.some(
      (side) =>
        side.manager_name.toLowerCase().includes(q) ||
        side.team_name.toLowerCase().includes(q)
    );
    if (managerMatch) return true;

    // Match player names
    const playerMatch = trade.sides.some((side) =>
      side.assets_received.some(
        (asset) =>
          asset.full_name.toLowerCase().includes(q) ||
          asset.pro_team.toLowerCase().includes(q) ||
          asset.default_position.toLowerCase().includes(q)
      )
    );
    return playerMatch;
  });
});

const topPartners = computed(() => tradeTrends.value?.top_partners ?? []);
const activeTraders = computed(() => tradeTrends.value?.active_traders ?? []);
</script>

<template>
  <div class="space-y-4 pb-20">
    <!-- View Header Banner -->
    <div class="flex items-center justify-between gap-2 flex-wrap">
      <div>
        <h2 class="text-xl font-black uppercase tracking-tight text-slate-100 flex items-center gap-2">
          <ArrowLeftRight class="w-5 h-5 text-indigo-400" />
          <span>Trades & Realized ROI</span>
        </h2>
        <p class="text-xs text-slate-400 mt-0.5">
          {{ effectiveSeasonFilter === null ? 'All-Time Career' : `Season ${effectiveSeasonFilter}` }} Trade Network & Post-Trade Starter Points
        </p>
      </div>

      <!-- Quick Scope Filter (All-Time vs Season) -->
      <div class="inline-flex items-center rounded-xl bg-slate-900 border border-slate-800 p-0.5 text-xs font-semibold">
        <button
          type="button"
          class="px-3 py-1.5 rounded-lg transition-all"
          :class="seasonMode === 'all' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'"
          @click="seasonMode = 'all'"
        >
          All-Time
        </button>
        <button
          type="button"
          class="px-3 py-1.5 rounded-lg transition-all"
          :class="seasonMode === 'season' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'"
          @click="seasonMode = 'season'"
        >
          {{ selectedSeason != null ? `Season ${selectedSeason}` : 'Season' }}
        </button>
      </div>
    </div>

    <!-- Pre-2018 Historical Notice Banner (ESPN limitation) -->
    <div
      v-if="lacksTransactionData"
      class="rounded-xl p-4 bg-amber-950/30 border border-amber-800/50 flex items-start gap-3 text-amber-200"
    >
      <Info class="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
      <div class="space-y-1">
        <h3 class="text-xs font-bold uppercase tracking-wide text-amber-300">
          Historical Transaction Notice
        </h3>
        <p class="text-xs text-amber-200/90 leading-relaxed">
          ESPN does not preserve transaction logs for completed historical seasons once archived. Historical trade data and realized starter points are unavailable for Season {{ effectiveSeasonFilter }}.
        </p>
        <button
          type="button"
          class="mt-2 text-xs font-semibold underline hover:text-white"
          @click="seasonMode = 'all'"
        >
          Switch to All-Time records
        </button>
      </div>
    </div>

    <!-- Loading State -->
    <LoadingState v-if="loading" variant="cards" :rows="3" message="Crunching realized post-trade starter points..." />

    <!-- Error State -->
    <EmptyState
      v-else-if="error"
      title="Error Loading Trades"
      :description="error"
      :is-error="true"
      action-text="Retry"
      @action="loadData"
    />

    <!-- Main Content -->
    <div v-else-if="tradeTrends" class="space-y-5">
      <!-- High-Level Navigation Tabs -->
      <div class="flex items-center gap-2 border-b border-slate-800 pb-2 overflow-x-auto">
        <button
          type="button"
          class="px-3 py-1.5 rounded-lg text-xs font-bold tracking-tight uppercase transition-colors shrink-0 flex items-center gap-1.5"
          :class="
            activeTab === 'trades'
              ? 'bg-slate-800 text-indigo-400 border border-indigo-500/40 shadow-sm'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
          "
          @click="activeTab = 'trades'"
        >
          <ArrowLeftRight class="w-3.5 h-3.5" />
          <span>Trade Autopsies ({{ tradeTrends.trades.length }})</span>
        </button>

        <button
          type="button"
          class="px-3 py-1.5 rounded-lg text-xs font-bold tracking-tight uppercase transition-colors shrink-0 flex items-center gap-1.5"
          :class="
            activeTab === 'partners'
              ? 'bg-slate-800 text-indigo-400 border border-indigo-500/40 shadow-sm'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
          "
          @click="activeTab = 'partners'"
        >
          <Users class="w-3.5 h-3.5" />
          <span>Partner Alliances ({{ topPartners.length }})</span>
        </button>

        <button
          type="button"
          class="px-3 py-1.5 rounded-lg text-xs font-bold tracking-tight uppercase transition-colors shrink-0 flex items-center gap-1.5"
          :class="
            activeTab === 'leaderboard'
              ? 'bg-slate-800 text-indigo-400 border border-indigo-500/40 shadow-sm'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
          "
          @click="activeTab = 'leaderboard'"
        >
          <TrendingUp class="w-3.5 h-3.5" />
          <span>Active Traders & ROI</span>
        </button>
      </div>

      <!-- TAB 1: Chronological Trade Autopsy Cards -->
      <div v-show="activeTab === 'trades'" class="space-y-4">
        <!-- Search & Filter Controls -->
        <div class="relative">
          <Search class="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search trades by manager, player, or NFL team..."
            class="w-full bg-slate-900/90 border border-slate-800 rounded-xl pl-9 pr-4 py-2.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
          />
        </div>

        <!-- Trades List -->
        <div v-if="filteredTrades.length > 0" class="space-y-3">
          <TradeAutopsyCard
            v-for="trade in filteredTrades"
            :key="trade.trade_id"
            :trade="trade"
            @select="openAutopsy"
          />
        </div>

        <!-- Empty Trades State -->
        <EmptyState
          v-else
          title="No Trades Recorded"
          :description="
            searchQuery
              ? `No trades found matching '${searchQuery}'.`
              : effectiveSeasonFilter != null
                ? `No trades occurred in Season ${effectiveSeasonFilter}.`
                : 'No historical trades have been recorded in the league archive.'
          "
        />
      </div>

      <!-- TAB 2: Top Trading Partner Alliances -->
      <div v-show="activeTab === 'partners'" class="space-y-3">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-bold uppercase tracking-tight text-slate-200 flex items-center gap-1.5">
              <Users class="w-4 h-4 text-indigo-400" />
              <span>Top Trading Partner Alliances</span>
            </h3>
            <p class="text-xs text-slate-400">
              Pairs of managers who trade most frequently with each other
            </p>
          </div>
        </div>

        <div v-if="topPartners.length > 0" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          <TradePartnerAllianceCard
            v-for="(partner, index) in topPartners"
            :key="`${partner.manager_a_id}-${partner.manager_b_id}`"
            :partner="partner"
            :rank="index + 1"
          />
        </div>

        <EmptyState
          v-else
          title="No Trading Alliances Found"
          description="Not enough trades have occurred in this scope to establish frequent partner alliances."
        />
      </div>

      <!-- TAB 3: Most Active Traders & Net Realized ROI -->
      <div v-show="activeTab === 'leaderboard'" class="space-y-4">
        <ActiveTradersLeaderboard
          v-if="activeTraders.length > 0"
          :traders="activeTraders"
        />
        <EmptyState
          v-else
          title="No Active Traders"
          description="No trade data available for this selection."
        />
      </div>
    </div>

    <!-- Trade Autopsy Deep Dive Drawer -->
    <TradeAutopsyDrawer
      v-model="drawerOpen"
      :trade="selectedTrade"
    />
  </div>
</template>
