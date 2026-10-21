<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useLeagueMeta } from '@/composables/useLeagueMeta';
import { fetchStandings } from '@/api/client';
import type { StandingEntry, StandingsResponse } from '@/types/api';
import StandingsKpiStrip from '@/components/standings/StandingsKpiStrip.vue';
import StandingCard from '@/components/standings/StandingCard.vue';
import StandingsDetailDrawer from '@/components/standings/StandingsDetailDrawer.vue';
import LoadingState from '@/components/ui/LoadingState.vue';
import EmptyState from '@/components/ui/EmptyState.vue';
import {
  Trophy,
  ArrowUpDown,
  TrendingUp,
  DollarSign,
  Sparkles,
  Percent,
} from 'lucide-vue-next';

const { selectedSeason } = useLeagueMeta();

const standingsData = ref<StandingsResponse | null>(null);
const loading = ref<boolean>(false);
const error = ref<string | null>(null);

// Selected team for drawer
const selectedTeam = ref<StandingEntry | null>(null);
const drawerOpen = ref<boolean>(false);

// Interactive Sort Modes
type SortMode = 'rank' | 'points_for' | 'all_play' | 'luck' | 'cash' | 'efficiency';
const sortMode = ref<SortMode>('rank');

const sortOptions: { id: SortMode; label: string; icon: typeof Trophy }[] = [
  { id: 'rank', label: 'Rank', icon: Trophy },
  { id: 'points_for', label: 'Points', icon: ArrowUpDown },
  { id: 'all_play', label: 'All-Play', icon: TrendingUp },
  { id: 'luck', label: 'Luck', icon: Sparkles },
  { id: 'cash', label: 'Cash', icon: DollarSign },
  { id: 'efficiency', label: 'Efficiency', icon: Percent },
];

async function loadStandings(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const res = await fetchStandings(selectedSeason.value);
    standingsData.value = res;
  } catch (err: unknown) {
    if (err instanceof Error) {
      error.value = err.message;
    } else {
      error.value = 'Failed to load standings data.';
    }
    console.error('Error fetching standings:', err);
  } finally {
    loading.value = false;
  }
}

// Watch selectedSeason from header
watch(
  () => selectedSeason.value,
  () => {
    loadStandings();
  }
);

onMounted(() => {
  loadStandings();
});

// Sorted standings list
const sortedStandings = computed<StandingEntry[]>(() => {
  if (!standingsData.value?.standings) return [];
  const list = [...standingsData.value.standings];

  switch (sortMode.value) {
    case 'rank':
      return list.sort((a, b) => a.rank - b.rank);
    case 'points_for':
      return list.sort((a, b) => b.points_for - a.points_for);
    case 'all_play':
      return list.sort((a, b) => b.all_play_win_pct - a.all_play_win_pct);
    case 'luck':
      return list.sort((a, b) => b.luck_index - a.luck_index);
    case 'cash':
      return list.sort((a, b) => b.total_earnings - a.total_earnings);
    case 'efficiency':
      return list.sort((a, b) => b.lineup_efficiency - a.lineup_efficiency);
    default:
      return list;
  }
});

function openTeamDetail(team: StandingEntry) {
  selectedTeam.value = team;
  drawerOpen.value = true;
}
</script>

<template>
  <div class="space-y-4 pb-20">
    <!-- View Header Banner -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-xl font-black uppercase tracking-tight text-slate-100 flex items-center gap-2">
          <Trophy class="w-5 h-5 text-amber-400" />
          <span>Standings & Performance</span>
        </h2>
        <p class="text-xs text-slate-400 mt-0.5">
          {{ standingsData ? `Season ${standingsData.season_year}` : 'Season' }} Standings, All-Play, Luck Index & Efficiency
        </p>
      </div>
    </div>

    <!-- Loading State -->
    <LoadingState
      v-if="loading && !standingsData"
      message="Calculating standings and all-play analytics..."
      variant="cards"
      :rows="5"
    />

    <!-- Error State -->
    <EmptyState
      v-else-if="error"
      title="Failed to Load Standings"
      :description="error"
      :is-error="true"
      action-text="Retry"
      @action="loadStandings"
    />

    <!-- Content State -->
    <div v-else-if="standingsData && sortedStandings.length > 0" class="space-y-4">
      <!-- KPI Strip -->
      <StandingsKpiStrip
        :standings="standingsData.standings"
        :season-year="standingsData.season_year"
        :is-active="standingsData.is_active"
        :is-completed="standingsData.is_completed"
        :current-week="standingsData.current_week"
      />

      <!-- Interactive Sort Pill Strip -->
      <div class="flex items-center justify-between gap-2 pt-1">
        <span class="text-[11px] uppercase font-bold tracking-wider text-slate-400 shrink-0">
          Sort by:
        </span>

        <div class="flex items-center gap-1.5 overflow-x-auto no-scrollbar py-1">
          <button
            v-for="opt in sortOptions"
            :key="opt.id"
            type="button"
            class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold whitespace-nowrap transition-all border active:scale-95"
            :class="
              sortMode === opt.id
                ? 'bg-emerald-500 text-slate-950 border-emerald-400 shadow-sm shadow-emerald-950/60 font-bold'
                : 'bg-slate-900/80 text-slate-400 border-slate-800 hover:text-slate-200 hover:border-slate-700'
            "
            @click="sortMode = opt.id"
          >
            <component :is="opt.icon" class="w-3 h-3" />
            <span>{{ opt.label }}</span>
          </button>
        </div>
      </div>

      <!-- Standings Cards List -->
      <div class="space-y-2.5">
        <StandingCard
          v-for="(standing, idx) in sortedStandings"
          :key="standing.team_id"
          :standing="standing"
          :is-completed="standingsData.is_completed"
          :display-rank="idx + 1"
          @click="openTeamDetail(standing)"
        />
      </div>

      <!-- Detail SwipeDrawer -->
      <StandingsDetailDrawer
        v-model="drawerOpen"
        :standing="selectedTeam"
        :is-completed="standingsData.is_completed"
        :season-year="standingsData.season_year"
      />
    </div>

    <!-- Empty State -->
    <EmptyState
      v-else
      title="No Standings Available"
      description="No team records or standings were found for the selected season."
      action-text="Refresh"
      @action="loadStandings"
    />
  </div>
</template>
