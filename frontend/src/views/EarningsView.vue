<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useLeagueMeta } from '@/composables/useLeagueMeta';
import { fetchEarningsLeaderboard } from '@/api/client';
import type { EarningsLeaderboardEntry, EarningsLeaderboardResponse } from '@/types/api';
import WeeklyBounties from '@/components/earnings/WeeklyBounties.vue';
import RegularSeasonPointsCard from '@/components/earnings/RegularSeasonPointsCard.vue';
import EarningsScoreboardTable from '@/components/earnings/EarningsScoreboardTable.vue';
import EarningsDetailDrawer from '@/components/earnings/EarningsDetailDrawer.vue';
import SideBetsSection from '@/components/earnings/SideBetsSection.vue';
import CommissionerSideBetEditor from '@/components/earnings/CommissionerSideBetEditor.vue';
import LoadingState from '@/components/ui/LoadingState.vue';
import EmptyState from '@/components/ui/EmptyState.vue';
import { Lock, ArrowLeft } from 'lucide-vue-next';

const route = useRoute();
const router = useRouter();

const { selectedSeason, availableSeasons } = useLeagueMeta();

const earningsData = ref<EarningsLeaderboardResponse | null>(null);
const loading = ref<boolean>(false);
const error = ref<string | null>(null);

// Ref to SideBetsSection for refreshing when CommissionerSideBetEditor updates
const sideBetsSectionRef = ref<InstanceType<typeof SideBetsSection> | null>(null);

// Selected manager for detail drawer
const selectedManager = ref<EarningsLeaderboardEntry | null>(null);
const drawerOpen = ref<boolean>(false);

// Segmented tab navigation synced with route.query.tab ('standings' | 'side-bets' | 'admin')
type EarningsTab = 'standings' | 'side-bets' | 'admin';
const VALID_TABS: EarningsTab[] = ['standings', 'side-bets', 'admin'];

const tabs: { id: Exclude<EarningsTab, 'admin'>; label: string }[] = [
  { id: 'standings', label: 'Prize Standings' },
  { id: 'side-bets', label: 'Side Bets' },
];

function parseTab(raw: unknown): EarningsTab | null {
  return typeof raw === 'string' && (VALID_TABS as string[]).includes(raw)
    ? (raw as EarningsTab)
    : null;
}

const activeTab = ref<EarningsTab>(parseTab(route.query.tab) ?? 'standings');

watch(
  () => route.query.tab,
  (newTab) => {
    const parsed = parseTab(newTab);
    if (parsed) activeTab.value = parsed;
  }
);

function setActiveTab(tab: EarningsTab) {
  activeTab.value = tab;
  router.replace({ query: { ...route.query, tab } });
}

const isSingleSeason = computed<boolean>(() => selectedSeason.value !== null);

const isSeasonCompleted = computed<boolean>(() => {
  if (selectedSeason.value === null) {
    return true;
  }
  const match = availableSeasons.value.find((s) => s.season_year === selectedSeason.value);
  return match?.is_completed ?? false;
});

const tabSubtitle = computed<string>(() => {
  if (activeTab.value === 'side-bets') {
    return isSingleSeason.value
      ? `Season ${selectedSeason.value} 1v1 & Group Spread Matchups`
      : 'All-Time Side Bets & Live Boxscores';
  }
  if (activeTab.value === 'admin') {
    return 'Commissioner Side Bet Desk & Live ESPN Score Sync';
  }
  return isSingleSeason.value
    ? `Season ${selectedSeason.value} Prize Standings`
    : 'All-Time Bankroll Standings';
});

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
    if (selectedManager.value && res.leaderboard) {
      const updated = res.leaderboard.find((e) => e.manager_id === selectedManager.value?.manager_id);
      if (updated) {
        selectedManager.value = updated;
      }
    }
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

function handleSideBetsUpdated() {
  loadEarnings();
  sideBetsSectionRef.value?.refresh();
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
    <div class="flex items-start justify-between gap-2 flex-wrap">
      <div class="min-w-0">
        <h2 class="text-base sm:text-lg font-black uppercase tracking-tight text-slate-100">
          Earnings &amp; Wagers
        </h2>
        <p class="text-xs text-slate-400 mt-0.5 font-mono">
          {{ tabSubtitle }}
        </p>
      </div>

      <div class="flex items-center gap-2 shrink-0">
        <!-- Inactive Filter Pill (All-Time mode on Prize Standings tab) -->
        <div
          v-if="!isSingleSeason && activeTab === 'standings'"
          class="inline-flex items-center rounded-lg bg-slate-900 border border-slate-800 p-0.5 text-xs font-semibold shrink-0"
        >
          <button
            type="button"
            class="px-2.5 py-1 rounded-md transition-all text-xs font-mono cursor-pointer"
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
            class="px-2.5 py-1 rounded-md transition-all text-xs font-mono cursor-pointer"
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

        <!-- Commissioner Button -->
        <button
          v-if="activeTab !== 'admin'"
          type="button"
          class="shrink-0 inline-flex items-center gap-1.5 h-8 px-2.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-100 hover:bg-slate-900 border border-slate-800 transition-colors cursor-pointer"
          @click="setActiveTab('admin')"
        >
          <Lock class="w-3.5 h-3.5" />
          <span>Commish</span>
        </button>
        <button
          v-else
          type="button"
          class="shrink-0 inline-flex items-center gap-1.5 h-8 px-2.5 rounded-lg text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-900 border border-slate-800 transition-colors cursor-pointer"
          @click="setActiveTab('side-bets')"
        >
          <ArrowLeft class="w-3.5 h-3.5" />
          <span>Back</span>
        </button>
      </div>
    </div>

    <!-- Segmented Tab Control: Prize Standings | Side Bets -->
    <nav
      v-if="activeTab !== 'admin'"
      role="tablist"
      aria-label="Earnings sections"
      class="grid grid-cols-2 gap-1 p-1 rounded-xl bg-slate-900/80 border border-slate-800/80 text-center"
    >
      <button
        v-for="t in tabs"
        :key="t.id"
        type="button"
        role="tab"
        :aria-selected="activeTab === t.id"
        class="min-h-[42px] py-1 px-2 rounded-lg text-xs font-semibold leading-tight transition-colors cursor-pointer flex items-center justify-center text-center"
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

    <!-- TAB 1: PRIZE STANDINGS -->
    <div v-show="activeTab === 'standings'" class="space-y-3.5">
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
          :is-completed="isSeasonCompleted"
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

    <!-- TAB 2: SIDE BETS -->
    <div v-show="activeTab === 'side-bets'">
      <SideBetsSection
        ref="sideBetsSectionRef"
        :season-year="selectedSeason"
        @refresh-earnings="loadEarnings"
      />
    </div>

    <!-- TAB 3: COMMISSIONER SIDE BET DESK -->
    <div v-show="activeTab === 'admin'">
      <CommissionerSideBetEditor
        :selected-season="selectedSeason"
        @updated="handleSideBetsUpdated"
      />
    </div>
  </div>
</template>
