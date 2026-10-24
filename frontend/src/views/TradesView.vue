<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useLeagueMeta } from '@/composables/useLeagueMeta';
import { fetchTradeTrends, fetchTransactionsSummary } from '@/api/client';
import type {
  TradesTrendsResponse,
  TradeDetail,
  TransactionsSummaryResponse,
  ActiveTrader,
  ManagerEfficiency,
} from '@/types/api';
import LoadingState from '@/components/ui/LoadingState.vue';
import EmptyState from '@/components/ui/EmptyState.vue';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import TradePartnerNetwork from '@/components/trades/TradePartnerNetwork.vue';
import ActiveTradersLeaderboard from '@/components/trades/ActiveTradersLeaderboard.vue';
import TradeAutopsyCard from '@/components/trades/TradeAutopsyCard.vue';
import TradeAutopsyDrawer from '@/components/trades/TradeAutopsyDrawer.vue';
import CommissionerTradeEditor from '@/components/trades/CommissionerTradeEditor.vue';
import TransactionAuditFeed from '@/components/waivers/TransactionAuditFeed.vue';
import { Search, X, ChevronDown, Lock, ArrowLeft } from 'lucide-vue-next';

/** One row per franchise: drives the team filter picker on the Trades tab. */
interface TeamActivityItem {
  manager_id: number;
  team_name: string;
  manager_name: string;
  logo_url: string | null;
  total_trades: number;
  executed_waivers: number;
  free_agent_adds: number;
  average_grade: string | null;
}

const route = useRoute();
const router = useRouter();

const { selectedSeason, availableSeasons, managers, setSelectedSeason } = useLeagueMeta();

const loading = ref<boolean>(false);
const error = ref<string | null>(null);
const tradeTrends = ref<TradesTrendsResponse | null>(null);
const transactionsSummary = ref<TransactionsSummaryResponse | null>(null);

// Breakdown drawer state
const selectedTrade = ref<TradeDetail | null>(null);
const drawerOpen = ref<boolean>(false);

// Commissioner edit target trade
const tradeToEdit = ref<TradeDetail | null>(null);

// Search & team filter for the Trades tab
const searchQuery = ref<string>('');
const selectedManagerFilter = ref<number | null>(null);

// Tab order is intentional: Trades -> Alliances Flow -> Trader ROI -> Waivers & Activity. 'admin' is reached from the header.
type TradeTab = 'trades' | 'partners' | 'leaderboard' | 'waivers' | 'admin';
const VALID_TABS: TradeTab[] = ['trades', 'partners', 'leaderboard', 'waivers', 'admin'];

const tabs: { id: Exclude<TradeTab, 'admin'>; label: string }[] = [
  { id: 'trades', label: 'Trades' },
  { id: 'partners', label: 'Alliances Flow' },
  { id: 'leaderboard', label: 'Trader ROI' },
  { id: 'waivers', label: 'Waivers & Activity' },
];

function parseTab(raw: unknown): TradeTab | null {
  return typeof raw === 'string' && (VALID_TABS as string[]).includes(raw) ? (raw as TradeTab) : null;
}

const activeTab = ref<TradeTab>(parseTab(route.query.tab) ?? 'trades');

watch(
  () => route.query.tab,
  (newTab) => {
    const parsed = parseTab(newTab);
    if (parsed) activeTab.value = parsed;
  }
);

function setActiveTab(tab: TradeTab) {
  activeTab.value = tab;
  router.replace({ query: { ...route.query, tab } });
}

const scopeLabel = computed<string>(() => {
  return selectedSeason.value === null ? 'All-Time Career' : `Season ${selectedSeason.value}`;
});

const tabSubtitle = computed<string>(() => {
  switch (activeTab.value) {
    case 'partners':
      return 'Who trades with whom, replayed in order';
    case 'leaderboard':
      return 'Net points gained from every deal';
    case 'waivers':
      return 'Waiver claims, FAAB bids and roster moves';
    case 'admin':
      return 'Commissioner tools';
    default:
      return 'Every deal, graded on what it actually produced';
  }
});

// Check if the current season lacks transaction data
const lacksTransactionData = computed(() => {
  if (tradeTrends.value && !tradeTrends.value.has_transaction_data) return true;
  if (selectedSeason.value !== null) {
    const s = availableSeasons.value.find((x) => x.season_year === selectedSeason.value);
    if (s && !s.has_transaction_data) return true;
  }
  return false;
});

// Most recent season that still has ESPN transaction logs (for the "jump to" shortcut)
const latestSeasonWithTransactions = computed<number | null>(() => {
  const years = availableSeasons.value
    .filter((s) => s.has_transaction_data)
    .map((s) => s.season_year);
  return years.length ? Math.max(...years) : null;
});

async function loadData() {
  loading.value = true;
  error.value = null;
  try {
    const [trendsData, txData] = await Promise.all([
      fetchTradeTrends(selectedSeason.value),
      fetchTransactionsSummary(selectedSeason.value).catch(() => null),
    ]);
    tradeTrends.value = trendsData;
    transactionsSummary.value = txData;
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

// Watch top-level season filter changes
watch(selectedSeason, () => {
  selectedManagerFilter.value = null;
  loadData();
});

onMounted(() => {
  loadData();
});

function openAutopsy(trade: TradeDetail) {
  selectedTrade.value = trade;
  drawerOpen.value = true;
}

// Build unified franchise list combining all teams, trade counts, waiver counts and grades
const teamActivityBoard = computed<TeamActivityItem[]>(() => {
  const traderMap = new Map<number, ActiveTrader>();
  for (const tr of tradeTrends.value?.active_traders ?? []) {
    traderMap.set(tr.manager_id, tr);
  }

  const effMap = new Map<number, ManagerEfficiency>();
  for (const me of transactionsSummary.value?.manager_efficiency ?? []) {
    effMap.set(me.manager_id, me);
  }

  const managerIds = new Set<number>();
  if (transactionsSummary.value?.manager_efficiency?.length) {
    for (const me of transactionsSummary.value.manager_efficiency) {
      managerIds.add(me.manager_id);
    }
  } else {
    for (const tr of tradeTrends.value?.active_traders ?? []) {
      managerIds.add(tr.manager_id);
    }
    for (const m of managers.value) {
      if (selectedSeason.value === null || m.is_active) {
        managerIds.add(m.id);
      }
    }
  }

  const items: TeamActivityItem[] = [];
  for (const mid of managerIds) {
    const trader = traderMap.get(mid);
    const eff = effMap.get(mid);
    const metaMgr = managers.value.find((m) => m.id === mid);

    items.push({
      manager_id: mid,
      team_name: trader?.team_name || eff?.team_name || metaMgr?.display_name || `Franchise ${mid}`,
      manager_name: trader?.display_name || eff?.display_name || metaMgr?.display_name || '',
      logo_url: trader?.avatar_url || eff?.logo_url || metaMgr?.avatar_url || null,
      total_trades: trader?.total_trades ?? 0,
      executed_waivers: eff?.executed_waivers ?? (trader?.executed_waivers ?? 0),
      free_agent_adds: eff?.free_agent_adds ?? (trader?.free_agent_adds ?? 0),
      average_grade: trader?.average_grade ? trader.average_grade : null,
    });
  }

  // Most trades first, then most waiver claims
  items.sort((a, b) => b.total_trades - a.total_trades || b.executed_waivers - a.executed_waivers);
  return items;
});

const activeFilteredTeam = computed(() => {
  if (selectedManagerFilter.value === null) return null;
  return teamActivityBoard.value.find((t) => t.manager_id === selectedManagerFilter.value) ?? null;
});

// Filtered trades by search query and team filter
const filteredTrades = computed(() => {
  if (!tradeTrends.value || !tradeTrends.value.trades) return [];
  let list = tradeTrends.value.trades;

  if (selectedManagerFilter.value !== null) {
    list = list.filter((trade) => trade.sides.some((s) => s.manager_id === selectedManagerFilter.value));
  }

  const q = searchQuery.value.trim().toLowerCase();
  if (!q) return list;

  return list.filter((trade) => {
    const managerMatch = trade.sides.some(
      (side) => side.manager_name.toLowerCase().includes(q) || side.team_name.toLowerCase().includes(q)
    );
    if (managerMatch) return true;

    return trade.sides.some((side) =>
      side.assets_received.some(
        (asset) =>
          asset.full_name.toLowerCase().includes(q) ||
          asset.pro_team.toLowerCase().includes(q) ||
          asset.default_position.toLowerCase().includes(q) ||
          (asset.drafted_player_name && asset.drafted_player_name.toLowerCase().includes(q))
      )
    );
  });
});

const topPartners = computed(() => tradeTrends.value?.top_partners ?? []);
const activeTraders = computed(() => tradeTrends.value?.active_traders ?? []);

function resetTradeFilters() {
  searchQuery.value = '';
  selectedManagerFilter.value = null;
}
</script>

<template>
  <div class="space-y-4 pb-20">
    <!-- Page header -->
    <header class="flex items-start justify-between gap-3">
      <div class="min-w-0">
        <h2 class="text-xl font-black uppercase tracking-tight text-slate-100 leading-none">
          Trades
          <span class="ml-1 text-xs font-mono font-semibold tracking-normal text-slate-500 normal-case align-middle">
            {{ selectedSeason ?? 'All time' }}
          </span>
        </h2>
        <p class="text-xs text-slate-500 mt-1.5">{{ tabSubtitle }}</p>
      </div>

      <button
        v-if="activeTab !== 'admin'"
        type="button"
        class="shrink-0 inline-flex items-center gap-1.5 h-9 px-3 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-100 hover:bg-slate-900 border border-slate-800 transition-colors cursor-pointer"
        @click="setActiveTab('admin')"
      >
        <Lock class="w-3.5 h-3.5" />
        <span>Commish</span>
      </button>
      <button
        v-else
        type="button"
        class="shrink-0 inline-flex items-center gap-1.5 h-9 px-3 rounded-lg text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-900 border border-slate-800 transition-colors cursor-pointer"
        @click="setActiveTab('trades')"
      >
        <ArrowLeft class="w-3.5 h-3.5" />
        <span>Back</span>
      </button>
    </header>

    <!-- Segmented tab control: four equal columns, never scrolls -->
    <nav
      v-if="activeTab !== 'admin'"
      role="tablist"
      aria-label="Trades sections"
      class="grid grid-cols-4 gap-1 p-1 rounded-xl bg-slate-900/80 border border-slate-800/80 text-center"
    >
      <button
        v-for="t in tabs"
        :key="t.id"
        type="button"
        role="tab"
        :aria-selected="activeTab === t.id"
        class="min-h-[44px] py-1 px-1 rounded-lg text-[11px] sm:text-xs font-semibold leading-tight transition-colors cursor-pointer flex items-center justify-center text-center"
        :class="
          activeTab === t.id
            ? 'bg-slate-700/80 text-white shadow-sm'
            : 'text-slate-400 hover:text-slate-200'
        "
        @click="setActiveTab(t.id)"
      >
        <span>{{ t.label }}</span>
      </button>
    </nav>

    <!-- ESPN archival limitation notice -->
    <div
      v-if="lacksTransactionData && activeTab !== 'admin'"
      class="rounded-xl border-l-2 border-amber-500/70 bg-amber-500/5 px-3.5 py-3 text-xs text-amber-100/90 leading-relaxed"
    >
      <p>
        ESPN purges transaction logs for archived seasons, so trades here may be incomplete.
      </p>
      <div class="flex items-center gap-4 mt-2 font-semibold">
        <button type="button" class="text-amber-300 hover:text-white cursor-pointer" @click="setSelectedSeason(null)">
          View all-time
        </button>
        <button type="button" class="text-amber-300 hover:text-white cursor-pointer" @click="setActiveTab('admin')">
          Add a trade manually
        </button>
      </div>
    </div>

    <!-- Loading State -->
    <LoadingState v-if="loading" variant="cards" :rows="3" message="Loading trades..." />

    <!-- Error State -->
    <EmptyState
      v-else-if="error"
      title="Couldn't load trades"
      :description="error"
      :is-error="true"
      action-text="Retry"
      @action="loadData"
    />

    <!-- Main Content -->
    <div v-else-if="tradeTrends" class="space-y-4">
      <!-- TAB 1: Trades -->
      <div v-show="activeTab === 'trades'" class="space-y-3">
        <!-- Toolbar: search + team picker -->
        <div class="space-y-2">
          <div class="relative">
            <Search class="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              v-model="searchQuery"
              type="search"
              placeholder="Search players, teams, managers"
              class="w-full h-11 bg-slate-900/80 border border-slate-800 rounded-xl pl-9 pr-10 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-slate-600 transition-colors"
            />
            <button
              v-if="searchQuery"
              type="button"
              aria-label="Clear search"
              class="absolute right-1 top-1/2 -translate-y-1/2 w-9 h-9 flex items-center justify-center text-slate-500 hover:text-slate-200 cursor-pointer"
              @click="searchQuery = ''"
            >
              <X class="w-4 h-4" />
            </button>
          </div>

          <div class="flex items-center gap-2">
            <!-- Native select overlay keeps the OS picker on mobile -->
            <label class="relative flex-1 min-w-0 h-11 flex items-center gap-2.5 px-3 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-slate-700 transition-colors cursor-pointer">
              <TeamAvatar
                v-if="activeFilteredTeam"
                :src="activeFilteredTeam.logo_url"
                :name="activeFilteredTeam.team_name"
                size="xs"
                rounded="lg"
              />
              <span class="text-sm truncate" :class="activeFilteredTeam ? 'text-slate-100 font-medium' : 'text-slate-400'">
                {{ activeFilteredTeam ? activeFilteredTeam.team_name : 'All teams' }}
              </span>
              <ChevronDown class="w-4 h-4 text-slate-500 ml-auto shrink-0" />
              <select
                v-model="selectedManagerFilter"
                aria-label="Filter by team"
                class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
              >
                <option :value="null">All teams</option>
                <option v-for="t in teamActivityBoard" :key="t.manager_id" :value="t.manager_id">
                  {{ t.team_name }} ({{ t.total_trades }})
                </option>
              </select>
            </label>
            <button
              v-if="activeFilteredTeam"
              type="button"
              aria-label="Clear team filter"
              class="w-11 h-11 shrink-0 rounded-xl border border-slate-800 text-slate-400 hover:text-white hover:bg-slate-900 flex items-center justify-center cursor-pointer"
              @click="selectedManagerFilter = null"
            >
              <X class="w-4 h-4" />
            </button>
          </div>
        </div>

        <!-- Result summary -->
        <div class="flex items-baseline justify-between px-0.5 pt-1">
          <h3 class="text-[11px] font-bold uppercase tracking-wider text-slate-400">
            {{ filteredTrades.length }} {{ filteredTrades.length === 1 ? 'trade' : 'trades' }}
          </h3>
          <span v-if="activeFilteredTeam && activeFilteredTeam.average_grade" class="text-[11px] text-slate-500">
            Avg grade <span class="text-slate-200 font-semibold">{{ activeFilteredTeam.average_grade }}</span>
          </span>
        </div>

        <!-- Trades list -->
        <div v-if="filteredTrades.length > 0" class="space-y-3">
          <TradeAutopsyCard
            v-for="trade in filteredTrades"
            :key="trade.trade_id"
            :trade="trade"
            @select="openAutopsy"
          />
        </div>

        <!-- Team selected but no trades -->
        <div
          v-else-if="activeFilteredTeam && activeFilteredTeam.total_trades === 0 && !searchQuery"
          class="rounded-2xl border border-slate-800/80 px-5 py-8 text-center"
        >
          <p class="text-sm font-semibold text-slate-200">{{ activeFilteredTeam.team_name }} hasn't made a trade</p>
          <p class="text-xs text-slate-500 mt-1">
            {{ activeFilteredTeam.executed_waivers }} waiver claims and {{ activeFilteredTeam.free_agent_adds }} free-agent adds in {{ scopeLabel.toLowerCase() }}.
          </p>
          <button
            type="button"
            class="mt-4 h-9 px-4 rounded-lg text-xs font-semibold text-slate-200 bg-slate-800 hover:bg-slate-700 cursor-pointer"
            @click="selectedManagerFilter = null"
          >
            Show all trades
          </button>
        </div>

        <EmptyState
          v-else
          title="No trades"
          :description="
            searchQuery || selectedManagerFilter !== null
              ? 'Nothing matches the current search or team filter.'
              : selectedSeason != null
                ? `No trades were made in ${selectedSeason}.`
                : 'No trades have been recorded yet.'
          "
          :action-text="searchQuery || selectedManagerFilter !== null ? 'Reset filters' : undefined"
          @action="resetTradeFilters"
        />
      </div>

      <!-- TAB 2: Partners (network graph + replay) -->
      <div v-show="activeTab === 'partners'">
        <TradePartnerNetwork
          v-if="topPartners.length > 0 || tradeTrends.trades.length > 0"
          :partners="topPartners"
          :trades="tradeTrends.trades"
          :season-label="scopeLabel"
          :is-all-time="selectedSeason === null"
          :season-year="selectedSeason"
          :available-seasons="availableSeasons"
          @select-trade="openAutopsy"
        />
        <EmptyState
          v-else
          title="No trade partners yet"
          description="Not enough trades in this scope to map who deals with whom."
        />
      </div>

      <!-- TAB 3: Trader ROI -->
      <div v-show="activeTab === 'leaderboard'">
        <ActiveTradersLeaderboard
          v-if="activeTraders.length > 0"
          :traders="activeTraders"
          :trades="tradeTrends.trades"
          :season-label="scopeLabel"
          :is-all-time="selectedSeason === null"
          @select-trade="openAutopsy"
        />
        <EmptyState v-else title="No traders" description="No trade data for this selection." />
      </div>

      <!-- TAB 4: Waivers & activity log -->
      <div v-show="activeTab === 'waivers'" class="space-y-4">
        <div
          v-if="transactionsSummary && !transactionsSummary.has_transaction_data"
          class="rounded-xl border-l-2 border-amber-500/70 bg-amber-500/5 px-3.5 py-3 text-xs text-amber-100/90 leading-relaxed"
        >
          <p>ESPN doesn't keep waiver or FAAB history for archived seasons.</p>
          <div class="flex items-center gap-4 mt-2 font-semibold">
            <button
              v-if="latestSeasonWithTransactions !== null && latestSeasonWithTransactions !== selectedSeason"
              type="button"
              class="text-amber-300 hover:text-white cursor-pointer"
              @click="setSelectedSeason(latestSeasonWithTransactions)"
            >
              Go to {{ latestSeasonWithTransactions }}
            </button>
            <button type="button" class="text-amber-300 hover:text-white cursor-pointer" @click="setSelectedSeason(null)">
              View all-time
            </button>
          </div>
        </div>

        <TransactionAuditFeed
          v-else
          :transactions="transactionsSummary?.transactions ?? []"
          :bidding-wars="transactionsSummary?.bidding_wars ?? []"
          :failure-reasons="transactionsSummary?.failure_reasons ?? []"
          :selected-manager-id="selectedManagerFilter"
          :page-size="50"
          initial-type-filter="WAIVER"
          @clear-manager-filter="selectedManagerFilter = null"
        />
      </div>

      <!-- Commissioner trade editor (password protected) -->
      <div v-show="activeTab === 'admin'" class="space-y-4">
        <CommissionerTradeEditor
          :trades="tradeTrends.trades"
          :initial-trade-to-edit="tradeToEdit"
          @updated="loadData"
        />
      </div>
    </div>

    <!-- Trade breakdown drawer -->
    <TradeAutopsyDrawer v-model="drawerOpen" :trade="selectedTrade" />
  </div>
</template>
