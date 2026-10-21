<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useLeagueMeta } from '@/composables/useLeagueMeta';
import { fetchEarningsLeaderboard } from '@/api/client';
import type { EarningsLeaderboardEntry, EarningsLeaderboardResponse } from '@/types/api';
import WeeklyBounties from '@/components/earnings/WeeklyBounties.vue';
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
</script>

<template>
  <div class="max-w-4xl mx-auto space-y-3.5 pb-20">
    <!-- View Header Banner -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-base sm:text-lg font-black uppercase tracking-tight text-slate-100">
          Earnings Standings
        </h2>
        <p class="text-xs text-slate-400 mt-0.5 font-mono">
          {{ isSingleSeason ? `Season ${selectedSeason} Weekly Bounties & Prize Standings` : 'All-Time Career Bankroll Standings' }}
        </p>
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
      <!-- 1. AT THE VERY TOP OF SEASON: Weekly Bounties in 2 Columns -->
      <WeeklyBounties
        v-if="isSingleSeason"
        :payouts="earningsData.weekly_nuanced_payouts"
        :season-year="selectedSeason"
      />

      <!-- 2. Earnings Standings Table (Direct flow matching Home Page) -->
      <EarningsScoreboardTable
        :leaderboard="earningsData.leaderboard"
        :is-single-season="isSingleSeason"
        :season-year="selectedSeason"
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
