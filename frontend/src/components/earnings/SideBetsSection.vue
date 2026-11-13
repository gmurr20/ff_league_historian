<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import type { SideBetsResponse, SideBetDetail } from '@/types/api';
import { fetchSideBets } from '@/api/client';
import SideBetCard from '@/components/earnings/SideBetCard.vue';
import SideBetDetailDrawer from '@/components/earnings/SideBetDetailDrawer.vue';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import LoadingState from '@/components/ui/LoadingState.vue';
import EmptyState from '@/components/ui/EmptyState.vue';
import { RefreshCw, Radio, Trophy, Swords } from 'lucide-vue-next';

const props = defineProps<{
  seasonYear: number | null;
}>();

const emit = defineEmits<{
  (e: 'refresh-earnings'): void;
}>();

const sideBetsData = ref<SideBetsResponse | null>(null);
const loading = ref<boolean>(false);
const refreshing = ref<boolean>(false);
const error = ref<string | null>(null);

// Selected week filter: null means "All Weeks"
const selectedWeekFilter = ref<number | null>(null);

// Detail drawer state
const selectedBet = ref<SideBetDetail | null>(null);
const detailDrawerOpen = ref<boolean>(false);

const sortedAvailableWeeks = computed<number[]>(() => {
  const weeks = sideBetsData.value?.available_weeks ?? [];
  return [...weeks].sort((a, b) => b - a);
});

const filteredBets = computed<SideBetDetail[]>(() => {
  const bets = sideBetsData.value?.bets ?? [];
  if (props.seasonYear === null || selectedWeekFilter.value === null) {
    return [...bets].sort((a, b) => b.season_year - a.season_year || b.week - a.week || b.bet_id - a.bet_id);
  }
  return bets
    .filter((b) => b.week === selectedWeekFilter.value)
    .sort((a, b) => b.season_year - a.season_year || b.bet_id - a.bet_id);
});

const hasAnyLiveBets = computed<boolean>(() => {
  return (sideBetsData.value?.bets ?? []).some((b) => b.is_live);
});

const formattedLastSync = computed<string>(() => {
  const raw = sideBetsData.value?.last_live_sync_at;
  if (!raw) return 'Auto-syncs every 10m on game days';
  const dt = new Date(raw);
  if (Number.isNaN(dt.getTime())) return 'Live boxscore sync enabled';
  const diffMin = Math.max(0, Math.round((Date.now() - dt.getTime()) / 60000));
  if (diffMin < 1) return 'Synced just now';
  if (diffMin < 60) return `Synced ${diffMin}m ago`;
  return `Last sync ${dt.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`;
});

function formatSignedCash(amount: number): string {
  if (amount > 0) return `+$${amount.toFixed(0)}`;
  if (amount < 0) return `-$${Math.abs(amount).toFixed(0)}`;
  return '$0';
}

async function loadSideBets(bustCache = false) {
  if (bustCache) {
    refreshing.value = true;
  } else {
    loading.value = true;
  }
  error.value = null;

  try {
    const res = await fetchSideBets(props.seasonYear, undefined, bustCache);
    sideBetsData.value = res;

    // Update open drawer bet if one is selected
    if (selectedBet.value) {
      const updated = res.bets.find((b) => b.bet_id === selectedBet.value?.bet_id);
      if (updated) {
        selectedBet.value = updated;
      }
    }
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Failed to load side bets.';
  } finally {
    loading.value = false;
    refreshing.value = false;
  }
}

watch(
  () => props.seasonYear,
  () => {
    selectedWeekFilter.value = null;
    loadSideBets(false);
  }
);

onMounted(() => {
  loadSideBets(false);
});

function openBetDetail(bet: SideBetDetail) {
  selectedBet.value = bet;
  detailDrawerOpen.value = true;
}

function handleManualRefresh() {
  loadSideBets(true);
  emit('refresh-earnings');
}

defineExpose({
  refresh: () => loadSideBets(true),
});
</script>

<template>
  <div class="space-y-4">
    <!-- Top Live Status & Week Filter Bar -->
    <div class="rounded-2xl border border-slate-800/90 bg-[#0b101b] p-3 space-y-3 shadow-md">
      <!-- Live Sync Status Row -->
      <div class="flex items-center justify-between gap-2 flex-wrap">
        <div class="flex items-center gap-2 min-w-0">
          <span
            class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase tracking-wider border shrink-0"
            :class="
              hasAnyLiveBets
                ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40'
                : 'bg-slate-800/90 text-slate-400 border-slate-700/80'
            "
          >
            <span
              class="w-1.5 h-1.5 rounded-full"
              :class="hasAnyLiveBets ? 'bg-emerald-400 animate-ping' : 'bg-slate-500'"
            ></span>
            <Radio class="w-3 h-3" />
            <span>{{ hasAnyLiveBets ? 'Live Scoring Active' : 'Boxscore Feed' }}</span>
          </span>

          <span class="text-[11px] font-mono text-slate-400 truncate">
            {{ formattedLastSync }}
          </span>
        </div>

        <div class="flex items-center gap-1.5 shrink-0">
          <button
            type="button"
            class="h-8 px-2.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs font-mono font-semibold text-slate-200 flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50"
            :disabled="refreshing || loading"
            @click="handleManualRefresh"
          >
            <RefreshCw class="w-3.5 h-3.5 text-emerald-400" :class="refreshing ? 'animate-spin' : ''" />
            <span>{{ refreshing ? 'Syncing...' : 'Refresh Live Scores' }}</span>
          </button>
        </div>
      </div>

      <!-- Week Selector Pill Strip (Single-Season Mode Only) -->
      <div v-if="seasonYear !== null && sortedAvailableWeeks.length > 0" class="flex items-center gap-1.5 overflow-x-auto pb-0.5 no-scrollbar">
        <button
          type="button"
          class="px-3 py-1.5 rounded-lg text-xs font-mono font-bold whitespace-nowrap transition-colors cursor-pointer shrink-0 border"
          :class="
            selectedWeekFilter === null
              ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 shadow-sm'
              : 'bg-slate-900/80 text-slate-400 border-slate-800 hover:text-slate-200'
          "
          @click="selectedWeekFilter = null"
        >
          All Weeks ({{ sideBetsData?.bets.length ?? 0 }})
        </button>

        <button
          v-for="wk in sortedAvailableWeeks"
          :key="wk"
          type="button"
          class="px-3 py-1.5 rounded-lg text-xs font-mono font-bold whitespace-nowrap transition-colors cursor-pointer shrink-0 border flex items-center gap-1.5"
          :class="
            selectedWeekFilter === wk
              ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 shadow-sm'
              : 'bg-slate-900/80 text-slate-400 border-slate-800 hover:text-slate-200'
          "
          @click="selectedWeekFilter = wk"
        >
          <span>Week {{ wk }}</span>
          <span
            v-if="wk === sideBetsData?.current_week && hasAnyLiveBets"
            class="w-1.5 h-1.5 rounded-full bg-emerald-400"
          ></span>
        </button>
      </div>
    </div>

    <!-- Loading State -->
    <LoadingState
      v-if="loading && !sideBetsData"
      message="Loading side bets & player boxscores..."
      variant="cards"
      :rows="3"
    />

    <!-- Error State -->
    <EmptyState
      v-else-if="error"
      title="Failed to Load Side Bets"
      :description="error"
      :is-error="true"
      action-text="Retry"
      @action="() => loadSideBets(true)"
    />

    <!-- Content State -->
    <template v-else-if="sideBetsData">
      <!-- Side Bet Net P&L Leaderboard Card -->
      <div
        v-if="sideBetsData.leaderboard && sideBetsData.leaderboard.length > 0"
        class="rounded-2xl border border-slate-800/90 bg-[#0b101b] overflow-hidden shadow-lg"
      >
        <div class="px-3.5 py-2.5 bg-slate-900/95 border-b border-slate-800/90 flex items-center justify-between gap-2">
          <div class="flex items-center gap-2 min-w-0">
            <Trophy class="w-4 h-4 text-amber-400 shrink-0" />
            <h3 class="text-xs sm:text-sm font-black uppercase tracking-tight text-slate-100 truncate">
              Side Bet Net P&amp;L Leaderboard
            </h3>
          </div>
          <span class="text-[10px] font-mono text-slate-500 uppercase tracking-wider shrink-0">
            {{ seasonYear ? `Season ${seasonYear}` : 'All-Time' }}
          </span>
        </div>

        <div class="divide-y divide-slate-800/60">
          <div
            v-for="(mgr, idx) in sideBetsData.leaderboard"
            :key="mgr.manager_id"
            class="px-3.5 py-2.5 flex items-center justify-between gap-2 hover:bg-slate-900/60 transition-colors"
          >
            <div class="flex items-center gap-2.5 min-w-0">
              <span
                class="w-5 font-mono text-xs font-black tabular-nums shrink-0"
                :class="idx === 0 && mgr.net_earnings > 0 ? 'text-amber-400' : 'text-slate-500'"
              >
                {{ idx + 1 }}
              </span>
              <TeamAvatar :src="mgr.avatar_url" :name="mgr.team_name" size="xs" rounded="lg" />
              <div class="min-w-0">
                <div class="text-xs sm:text-sm font-bold text-slate-100 truncate leading-tight">
                  {{ mgr.team_name }}
                </div>
                <div class="text-[10px] text-slate-400 font-mono truncate mt-0.5">
                  {{ mgr.manager_name }} · {{ mgr.wins }}W-{{ mgr.losses }}L<template v-if="mgr.pushes > 0">-{{ mgr.pushes }}P</template>
                  <template v-if="mgr.pending > 0"> ({{ mgr.pending }} live)</template>
                </div>
              </div>
            </div>

            <div class="text-right font-mono tabular-nums shrink-0">
              <span
                class="text-xs sm:text-sm font-black px-2 py-0.5 rounded-md border"
                :class="
                  mgr.net_earnings > 0
                    ? 'text-emerald-400 bg-emerald-950/60 border-emerald-500/30'
                    : mgr.net_earnings < 0
                    ? 'text-rose-400 bg-rose-950/60 border-rose-500/30'
                    : 'text-slate-400 bg-slate-900 border-slate-800'
                "
              >
                {{ formatSignedCash(mgr.net_earnings) }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- List of SideBetCard items -->
      <div v-if="filteredBets.length > 0" class="space-y-3">
        <div class="flex items-center justify-between px-1">
          <div class="flex items-center gap-1.5">
            <Swords class="w-3.5 h-3.5 text-indigo-400" />
            <h3 class="text-xs font-mono font-black uppercase tracking-wider text-slate-300">
              {{ selectedWeekFilter ? `Week ${selectedWeekFilter} Matchups` : 'All Side Bet Matchups' }}
              ({{ filteredBets.length }})
            </h3>
          </div>
          <span class="text-[10px] font-mono text-slate-500">
            Tap any matchup for team &amp; player boxscores
          </span>
        </div>

        <SideBetCard
          v-for="bet in filteredBets"
          :key="bet.bet_id"
          :bet="bet"
          :show-season-badge="seasonYear === null"
          @select="openBetDetail"
        />
      </div>

      <!-- Empty State when no side bets exist -->
      <EmptyState
        v-else
        title="No Side Bets Logged Yet"
        :description="
          selectedWeekFilter
            ? `No side bets recorded for Week ${selectedWeekFilter}.`
            : 'No 1v1 or group side bets have been created for this selection yet.'
        "
      />
    </template>

    <!-- Expandable Team/Player Boxscore Drawer -->
    <SideBetDetailDrawer
      v-model="detailDrawerOpen"
      :bet="selectedBet"
    />
  </div>
</template>
