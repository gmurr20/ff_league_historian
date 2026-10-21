<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useLeagueMeta } from '@/composables/useLeagueMeta';
import { fetchEarningsLeaderboard } from '@/api/client';
import type { EarningsLeaderboardEntry, EarningsLeaderboardResponse } from '@/types/api';
import EarningsKpiHeader from '@/components/earnings/EarningsKpiHeader.vue';
import EarningsCard from '@/components/earnings/EarningsCard.vue';
import EarningsDetailDrawer from '@/components/earnings/EarningsDetailDrawer.vue';
import LoadingState from '@/components/ui/LoadingState.vue';
import EmptyState from '@/components/ui/EmptyState.vue';
import { DollarSign, Globe, Calendar, ArrowUpDown } from 'lucide-vue-next';

const { selectedSeason } = useLeagueMeta();

const earningsData = ref<EarningsLeaderboardResponse | null>(null);
const loading = ref<boolean>(false);
const error = ref<string | null>(null);

// Scope mode: 'all-time' vs 'season'
const scopeMode = ref<'all-time' | 'season'>('all-time');

// Selected manager for drawer
const selectedManager = ref<EarningsLeaderboardEntry | null>(null);
const drawerOpen = ref<boolean>(false);

// Active season parameter for API
const effectiveSeasonFilter = computed<number | null>(() => {
  if (scopeMode.value === 'all-time') {
    return null;
  }
  return selectedSeason.value;
});

async function loadEarnings(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const res = await fetchEarningsLeaderboard(effectiveSeasonFilter.value);
    earningsData.value = res;
  } catch (err: unknown) {
    if (err instanceof Error) {
      error.value = err.message;
    } else {
      error.value = 'Failed to load earnings leaderboard.';
    }
    console.error('Error fetching earnings leaderboard:', err);
  } finally {
    loading.value = false;
  }
}

// Watch scopeMode and selectedSeason
watch(
  () => [scopeMode.value, selectedSeason.value],
  () => {
    loadEarnings();
  }
);

onMounted(() => {
  loadEarnings();
});

// Sorted Leaderboard (highest earnings first)
const sortedLeaderboard = computed<EarningsLeaderboardEntry[]>(() => {
  if (!earningsData.value?.leaderboard) return [];
  return [...earningsData.value.leaderboard].sort((a, b) => b.total_earnings - a.total_earnings);
});

// Max earnings for relative bar visual
const maxEarnings = computed<number>(() => {
  if (!sortedLeaderboard.value.length) return 0;
  return sortedLeaderboard.value[0].total_earnings;
});

function openManagerDetail(entry: EarningsLeaderboardEntry) {
  selectedManager.value = entry;
  drawerOpen.value = true;
}
</script>

<template>
  <div class="space-y-4 pb-20">
    <!-- View Header Banner -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-xl font-black uppercase tracking-tight text-slate-100 flex items-center gap-2">
          <DollarSign class="w-5 h-5 text-emerald-400" />
          <span>Earnings & Bankroll</span>
        </h2>
        <p class="text-xs text-slate-400 mt-0.5">
          {{ scopeMode === 'all-time' ? 'All-Time Career Bankroll' : `Season ${selectedSeason ?? ''} Ledger` }} · Weekly High Scores & Podiums
        </p>
      </div>
    </div>

    <!-- Toggle Strip: All-Time vs Selected Season -->
    <div class="flex items-center justify-between gap-2 bg-slate-900/90 p-1 rounded-xl border border-slate-800">
      <button
        type="button"
        class="flex-1 flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg text-xs font-bold transition-all min-h-[36px]"
        :class="
          scopeMode === 'all-time'
            ? 'bg-emerald-500 text-slate-950 shadow-md shadow-emerald-950/60'
            : 'text-slate-400 hover:text-slate-200'
        "
        @click="scopeMode = 'all-time'"
      >
        <Globe class="w-3.5 h-3.5" />
        <span>All-Time Career</span>
      </button>

      <button
        type="button"
        class="flex-1 flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg text-xs font-bold transition-all min-h-[36px]"
        :class="
          scopeMode === 'season'
            ? 'bg-emerald-500 text-slate-950 shadow-md shadow-emerald-950/60'
            : 'text-slate-400 hover:text-slate-200'
        "
        @click="scopeMode = 'season'"
      >
        <Calendar class="w-3.5 h-3.5" />
        <span>{{ selectedSeason === null ? 'Active Season' : `Season ${selectedSeason}` }}</span>
      </button>
    </div>

    <!-- Loading State -->
    <LoadingState
      v-if="loading && !earningsData"
      message="Calculating financial ledger and prize pools..."
      variant="cards"
      :rows="5"
    />

    <!-- Error State -->
    <EmptyState
      v-else-if="error"
      title="Failed to Load Financial Ledger"
      :description="error"
      :is-error="true"
      action-text="Retry"
      @action="loadEarnings"
    />

    <!-- Content State -->
    <div v-else-if="earningsData && sortedLeaderboard.length > 0" class="space-y-4">
      <!-- Financial KPI Header -->
      <EarningsKpiHeader
        :leaderboard="earningsData.leaderboard"
        :weekly-win-value="earningsData.weekly_win_value"
        :season-filter="earningsData.season_filter"
      />

      <!-- Leaderboard Header -->
      <div class="flex items-center justify-between px-1 pt-1">
        <h3 class="text-xs uppercase font-bold tracking-wider text-slate-400">
          Ranked Bankroll ({{ sortedLeaderboard.length }} Managers)
        </h3>
        <span class="text-[11px] font-mono text-slate-500 flex items-center gap-1">
          <ArrowUpDown class="w-3 h-3 text-slate-500" />
          <span>High to Low</span>
        </span>
      </div>

      <!-- Manager Cards List -->
      <div class="space-y-2.5">
        <EarningsCard
          v-for="(entry, idx) in sortedLeaderboard"
          :key="entry.manager_id"
          :entry="entry"
          :rank="idx + 1"
          :max-earnings="maxEarnings"
          :is-single-season="scopeMode === 'season'"
          @click="openManagerDetail(entry)"
        />
      </div>

      <!-- Detail SwipeDrawer -->
      <EarningsDetailDrawer
        v-model="drawerOpen"
        :entry="selectedManager"
      />
    </div>

    <!-- Empty State -->
    <EmptyState
      v-else
      title="No Financial Records Found"
      description="No cash payouts or prize ledger entries exist for the selected scope."
      action-text="Refresh"
      @action="loadEarnings"
    />
  </div>
</template>
