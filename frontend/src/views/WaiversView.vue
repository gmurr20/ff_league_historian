<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useLeagueMeta } from '@/composables/useLeagueMeta';
import { fetchTransactionsSummary } from '@/api/client';
import type { TransactionsSummaryResponse, BiddingWar } from '@/types/api';
import LoadingState from '@/components/ui/LoadingState.vue';
import EmptyState from '@/components/ui/EmptyState.vue';
import ManagerEfficiencyCard from '@/components/waivers/ManagerEfficiencyCard.vue';
import BiddingWarCard from '@/components/waivers/BiddingWarCard.vue';
import BiddingWarDrawer from '@/components/waivers/BiddingWarDrawer.vue';
import TransactionAuditFeed from '@/components/waivers/TransactionAuditFeed.vue';
import {
  Zap,
  Flame,
  DollarSign,
  History,
  Info,
  SlidersHorizontal,
} from 'lucide-vue-next';

const { selectedSeason, availableSeasons } = useLeagueMeta();

const loading = ref<boolean>(false);
const error = ref<string | null>(null);
const transactionsSummary = ref<TransactionsSummaryResponse | null>(null);

// Selected section tab
const activeTab = ref<'wars' | 'efficiency' | 'audit'>('wars');

// Bidding war drawer state
const selectedWar = ref<BiddingWar | null>(null);
const drawerOpen = ref<boolean>(false);

// Sort option for manager efficiency
type EfficiencySort = 'roi' | 'spent' | 'success' | 'points';
const efficiencySort = ref<EfficiencySort>('roi');

// Check if selected season has transaction data
const lacksTransactionData = computed(() => {
  if (transactionsSummary.value && !transactionsSummary.value.has_transaction_data) return true;
  if (selectedSeason.value !== null) {
    const s = availableSeasons.value.find((x) => x.season_year === selectedSeason.value);
    if (s && !s.has_transaction_data) return true;
  }
  return false;
});

async function loadData() {
  loading.value = true;
  error.value = null;
  try {
    const data = await fetchTransactionsSummary(selectedSeason.value);
    transactionsSummary.value = data;
  } catch (err: unknown) {
    if (err instanceof Error) {
      error.value = err.message;
    } else {
      error.value = 'Failed to load waiver records';
    }
    console.error('Error fetching transactions summary:', err);
  } finally {
    loading.value = false;
  }
}

watch(selectedSeason, () => {
  loadData();
});

onMounted(() => {
  loadData();
});

function openBiddingWar(war: BiddingWar) {
  selectedWar.value = war;
  drawerOpen.value = true;
}

// Sorted manager efficiency list
const sortedManagers = computed(() => {
  if (!transactionsSummary.value?.manager_efficiency) return [];
  const list = [...transactionsSummary.value.manager_efficiency];

  if (efficiencySort.value === 'roi') {
    return list.sort((a, b) => (b.points_per_faab_dollar ?? -1) - (a.points_per_faab_dollar ?? -1));
  } else if (efficiencySort.value === 'spent') {
    return list.sort((a, b) => b.faab_spent - a.faab_spent);
  } else if (efficiencySort.value === 'success') {
    return list.sort((a, b) => b.waiver_success_rate - a.waiver_success_rate);
  } else if (efficiencySort.value === 'points') {
    return list.sort((a, b) => b.total_starter_points_from_waivers - a.total_starter_points_from_waivers);
  }
  return list;
});

const biddingWars = computed(() => transactionsSummary.value?.bidding_wars ?? []);
const failureReasons = computed(() => transactionsSummary.value?.failure_reasons ?? []);
const auditTransactions = computed(() => transactionsSummary.value?.transactions ?? []);
</script>

<template>
  <div class="space-y-4 pb-20">
    <!-- View Header Banner -->
    <div class="flex items-center justify-between gap-2 flex-wrap">
      <div>
        <h2 class="text-xl font-black uppercase tracking-tight text-slate-100 flex items-center gap-2">
          <Zap class="w-5 h-5 text-amber-400" />
          <span>Waivers & FAAB Wars</span>
        </h2>
        <p class="text-xs text-slate-400 mt-0.5">
          Season {{ selectedSeason === null ? 'All-Time' : selectedSeason }} Bidding Wars, Failed Claims & FAAB Efficiency
        </p>
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
          ESPN did not preserve FAAB bids or waiver logs for seasons prior to 2018. Bidding war receipts and waiver efficiency metrics are unavailable for Season {{ selectedSeason }}.
        </p>
      </div>
    </div>

    <!-- Loading State -->
    <LoadingState v-if="loading" variant="cards" :rows="3" message="Auditing FAAB bids and contested claims..." />

    <!-- Error State -->
    <EmptyState
      v-else-if="error"
      title="Error Loading Waivers"
      :description="error"
      :is-error="true"
      action-text="Retry"
      @action="loadData"
    />

    <!-- Main Content -->
    <div v-else-if="transactionsSummary" class="space-y-5">
      <!-- Section Navigation Tabs -->
      <div class="flex items-center gap-2 border-b border-slate-800 pb-2 overflow-x-auto">
        <button
          type="button"
          class="px-3 py-1.5 rounded-lg text-xs font-bold tracking-tight uppercase transition-colors shrink-0 flex items-center gap-1.5"
          :class="
            activeTab === 'wars'
              ? 'bg-slate-800 text-amber-400 border border-amber-500/40 shadow-sm'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
          "
          @click="activeTab = 'wars'"
        >
          <Flame class="w-3.5 h-3.5 text-amber-400" />
          <span>Bidding Wars ({{ biddingWars.length }})</span>
        </button>

        <button
          type="button"
          class="px-3 py-1.5 rounded-lg text-xs font-bold tracking-tight uppercase transition-colors shrink-0 flex items-center gap-1.5"
          :class="
            activeTab === 'efficiency'
              ? 'bg-slate-800 text-emerald-400 border border-emerald-500/40 shadow-sm'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
          "
          @click="activeTab = 'efficiency'"
        >
          <DollarSign class="w-3.5 h-3.5 text-emerald-400" />
          <span>FAAB Efficiency ({{ sortedManagers.length }})</span>
        </button>

        <button
          type="button"
          class="px-3 py-1.5 rounded-lg text-xs font-bold tracking-tight uppercase transition-colors shrink-0 flex items-center gap-1.5"
          :class="
            activeTab === 'audit'
              ? 'bg-slate-800 text-indigo-400 border border-indigo-500/40 shadow-sm'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
          "
          @click="activeTab = 'audit'"
        >
          <History class="w-3.5 h-3.5 text-indigo-400" />
          <span>Transaction Audit ({{ auditTransactions.length }})</span>
        </button>
      </div>

      <!-- TAB 1: FAAB Bidding War Receipts -->
      <div v-show="activeTab === 'wars'" class="space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-bold uppercase tracking-tight text-slate-200 flex items-center gap-1.5">
              <Flame class="w-4 h-4 text-amber-400" />
              <span>Contested FAAB Bidding Wars</span>
            </h3>
            <p class="text-xs text-slate-400">
              Contested waiver claims where multiple managers submitted bids on the same player
            </p>
          </div>
        </div>

        <div v-if="biddingWars.length > 0" class="grid grid-cols-1 md:grid-cols-2 gap-3.5">
          <BiddingWarCard
            v-for="war in biddingWars"
            :key="war.winning_transaction_id"
            :war="war"
            @select="openBiddingWar"
          />
        </div>

        <EmptyState
          v-else
          title="No Contested Bidding Wars"
          :description="
            selectedSeason != null
              ? `No multi-bid contested waiver claims were found in Season ${selectedSeason}.`
              : 'No contested bidding wars recorded.'
          "
        />
      </div>

      <!-- TAB 2: Manager FAAB & Waiver Efficiency -->
      <div v-show="activeTab === 'efficiency'" class="space-y-4">
        <!-- Sort Controls Row -->
        <div class="flex items-center justify-between gap-2 flex-wrap">
          <div>
            <h3 class="text-sm font-bold uppercase tracking-tight text-slate-200 flex items-center gap-1.5">
              <DollarSign class="w-4 h-4 text-emerald-400" />
              <span>Manager Waiver & FAAB Efficiency</span>
            </h3>
            <p class="text-xs text-slate-400">
              FAAB budget utilization, success rates, and realized starter points per dollar spent
            </p>
          </div>

          <div class="inline-flex items-center rounded-lg bg-slate-900 border border-slate-800 p-0.5 text-xs">
            <button
              type="button"
              class="px-2.5 py-1 rounded-md font-semibold transition-colors flex items-center gap-1"
              :class="efficiencySort === 'roi' ? 'bg-emerald-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'"
              @click="efficiencySort = 'roi'"
            >
              <SlidersHorizontal class="w-3 h-3" />
              <span>ROI</span>
            </button>
            <button
              type="button"
              class="px-2.5 py-1 rounded-md font-semibold transition-colors"
              :class="efficiencySort === 'spent' ? 'bg-emerald-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'"
              @click="efficiencySort = 'spent'"
            >
              Spent
            </button>
            <button
              type="button"
              class="px-2.5 py-1 rounded-md font-semibold transition-colors"
              :class="efficiencySort === 'success' ? 'bg-emerald-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'"
              @click="efficiencySort = 'success'"
            >
              Success
            </button>
            <button
              type="button"
              class="px-2.5 py-1 rounded-md font-semibold transition-colors"
              :class="efficiencySort === 'points' ? 'bg-emerald-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'"
              @click="efficiencySort = 'points'"
            >
              Starter Pts
            </button>
          </div>
        </div>

        <div v-if="sortedManagers.length > 0" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          <ManagerEfficiencyCard
            v-for="(mgr, idx) in sortedManagers"
            :key="mgr.manager_id"
            :manager="mgr"
            :rank="idx + 1"
          />
        </div>

        <EmptyState
          v-else
          title="No Manager Efficiency Records"
          description="No waiver activity recorded for this season."
        />
      </div>

      <!-- TAB 3: Filterable Transaction Audit Feed -->
      <div v-show="activeTab === 'audit'" class="space-y-4">
        <TransactionAuditFeed
          :transactions="auditTransactions"
          :failure-reasons="failureReasons"
        />
      </div>
    </div>

    <!-- Contested Bidding War Drawer -->
    <BiddingWarDrawer
      v-model="drawerOpen"
      :war="selectedWar"
    />
  </div>
</template>
