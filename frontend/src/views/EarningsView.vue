<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useLeagueMeta } from '@/composables/useLeagueMeta';
import { fetchEarningsLeaderboard } from '@/api/client';
import type { EarningsLeaderboardEntry, EarningsLeaderboardResponse } from '@/types/api';
import WeeklyBounties from '@/components/earnings/WeeklyBounties.vue';
import RegularSeasonPointsCard from '@/components/earnings/RegularSeasonPointsCard.vue';
import EarningsScoreboardTable from '@/components/earnings/EarningsScoreboardTable.vue';
import EarningsDetailDrawer from '@/components/earnings/EarningsDetailDrawer.vue';
import LoadingState from '@/components/ui/LoadingState.vue';
import EmptyState from '@/components/ui/EmptyState.vue';

const { selectedSeason } = useLeagueMeta();

const earningsData = ref<EarningsLeaderboardResponse | null>(null);
const loading = ref<boolean>(false);
const error = ref<string | null>(null);

// Selected manager for detail drawer
const selectedManager = ref<EarningsLeaderboardEntry | null>(null);
const drawerOpen = ref<boolean>(false);

const isSingleSeason = computed<boolean>(() => selectedSeason.value !== null);

// Franchise status filter in All-Time mode: 'active' vs 'all' (default: 'active' first)
type InactiveFilterMode = 'active' | 'all';
const inactiveFilter = ref<InactiveFilterMode>('active');

const totalFranchisesCount = computed<number>(() => {
  return earningsData.value?.leaderboard.length ?? 0;
});

const activeFranchisesCount = computed<number>(() => {
  return earningsData.value?.leaderboard.filter((e) => e.is_active).length ?? 0;
});

async function loadEarnings(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const res = await fetchEarningsLeaderboard(selectedSeason.value);
    earningsData.value = res;
  } catch (err: unknown) {
    if (err instanceof Error) {
      error.value = err.message;
    } else {
      error.value = 'Failed to load earnings data.';
    }
    console.error('Error fetching earnings data:', err);
  } finally {
    loading.value = false;
  }
}

watch(
  () => selectedSeason.value,
  () => {
    inactiveFilter.value = 'active'; // Default to active first!
    loadEarnings();
  }
);

onMounted(() => {
  loadEarnings();
});

function openManagerDetail(entry: EarningsLeaderboardEntry) {
  selectedManager.value = entry;
  drawerOpen.value = true;
}

function openManagerById(managerId: number) {
  const match = earningsData.value?.leaderboard.find((e) => e.manager_id === managerId);
  if (match) {
    openManagerDetail(match);
  }
}
</script>

<template>
  <div class="max-w-4xl mx-auto space-y-3.5 pb-20">
    <!-- View Header Banner / Editorial Control Bar -->
    <div class="flex items-center justify-between gap-2 flex-wrap">
      <div>
        <h2 class="text-base sm:text-lg font-black uppercase tracking-tight text-slate-100">
          Earnings Standings
        </h2>
        <p class="text-xs text-slate-400 mt-0.5 font-mono">
          {{ isSingleSeason ? `Season ${selectedSeason} Prize Standings` : 'All-Time Bankroll Standings' }}
        </p>
      </div>

      <!-- Inactive Filter Pill (All-Time mode only) -->
      <div
        v-if="!isSingleSeason"
        class="inline-flex items-center rounded-lg bg-slate-900 border border-slate-800 p-0.5 text-xs font-semibold shrink-0"
      >
        <button
          type="button"
          class="px-2.5 py-1 rounded-md transition-all text-xs font-mono"
          :class="
            inactiveFilter === 'active'
              ? 'bg-emerald-500/20 text-emerald-300 font-bold border border-emerald-500/40 shadow-sm'
              : 'text-slate-400 hover:text-slate-200'
          "
          @click="inactiveFilter = 'active'"
        >
          Active ({{ activeFranchisesCount }})
        </button>
        <button
          type="button"
          class="px-2.5 py-1 rounded-md transition-all text-xs font-mono"
          :class="
            inactiveFilter === 'all'
              ? 'bg-slate-800 text-slate-100 font-bold border border-slate-700/60 shadow-sm'
              : 'text-slate-400 hover:text-slate-200'
          "
          @click="inactiveFilter = 'all'"
        >
          All ({{ totalFranchisesCount }})
        </button>
      </div>
    </div>

    <!-- Loading State -->
    <LoadingState
      v-if="loading && !earningsData"
      message="Loading earnings standings..."
      variant="cards"
      :rows="5"
    />

    <!-- Error State -->
    <EmptyState
      v-else-if="error"
      title="Failed to Load Earnings"
      :description="error"
      :is-error="true"
      action-text="Retry"
      @action="loadEarnings"
    />

    <!-- Content State -->
    <div v-else-if="earningsData && earningsData.leaderboard.length > 0" class="space-y-3.5">
      <!-- 1. AT THE VERY TOP OF SEASON: Regular Season Scoring Champion Award (when awarded) -->
      <RegularSeasonPointsCard
        v-if="isSingleSeason && earningsData.regular_season_points_winner"
        :winner="earningsData.regular_season_points_winner"
        :season-year="selectedSeason"
        @open-manager="openManagerById"
      />

      <!-- 2. Weekly Bounties in 2 Columns -->
      <WeeklyBounties
        v-if="isSingleSeason"
        :payouts="earningsData.weekly_nuanced_payouts"
        :season-year="selectedSeason"
      />

      <!-- 3. Earnings Standings Table (Direct flow matching Home Page) -->
      <EarningsScoreboardTable
        :leaderboard="earningsData.leaderboard"
        :is-single-season="isSingleSeason"
        :season-year="selectedSeason"
        :inactive-filter="inactiveFilter"
        @open-manager="openManagerDetail"
      />

      <!-- Detail Drawer with itemized weekly receipts -->
      <EarningsDetailDrawer
        v-model="drawerOpen"
        :entry="selectedManager"
        :is-single-season="isSingleSeason"
        :season-year="selectedSeason"
      />
    </div>

    <!-- Empty State -->
    <EmptyState
      v-else
      title="No Earnings Found"
      description="No cash payouts or prize standings recorded for this selection."
      action-text="Refresh"
      @action="loadEarnings"
    />
  </div>
</template>
