<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useLeagueMeta } from '@/composables/useLeagueMeta';
import { fetchStandings } from '@/api/client';
import type { StandingEntry, StandingsResponse } from '@/types/api';
import WeeklyTrajectoryChart from '@/components/standings/WeeklyTrajectoryChart.vue';
import StandingsDetailDrawer from '@/components/standings/StandingsDetailDrawer.vue';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import LoadingState from '@/components/ui/LoadingState.vue';
import EmptyState from '@/components/ui/EmptyState.vue';

const { selectedSeason } = useLeagueMeta();

const standingsData = ref<StandingsResponse | null>(null);
const loading = ref<boolean>(false);
const error = ref<string | null>(null);

// Primary Table Mode: 'standings' (Official W-L) vs 'power' (Median & All-Play)
type TableMode = 'standings' | 'power';
const tableMode = ref<TableMode>('standings');

// Column sort override within active mode
type SortColumn = 'rank' | 'power_rank' | 'median' | 'points_for' | 'points_against' | 'all_play' | 'luck' | 'efficiency' | 'cash';
const sortCol = ref<SortColumn>('rank');
const sortAsc = ref<boolean>(true);

// Selected team for detail drawer & chart spotlight
const selectedTeam = ref<StandingEntry | null>(null);
const drawerOpen = ref<boolean>(false);
const spotlightTeamId = ref<number | null>(null);

function switchMode(mode: TableMode) {
  tableMode.value = mode;
  if (mode === 'standings') {
    sortCol.value = 'rank';
    sortAsc.value = true;
  } else {
    sortCol.value = 'power_rank';
    sortAsc.value = true;
  }
}

function toggleSort(col: SortColumn) {
  if (sortCol.value === col) {
    sortAsc.value = !sortAsc.value;
  } else {
    sortCol.value = col;
    // Rank columns default ascending (1..12); stat columns default descending (high..low)
    sortAsc.value = col === 'rank' || col === 'power_rank';
  }
}

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

watch(
  () => selectedSeason.value,
  () => {
    spotlightTeamId.value = null;
    loadStandings();
  }
);

onMounted(() => {
  loadStandings();
});

const sortedStandings = computed<StandingEntry[]>(() => {
  if (!standingsData.value?.standings) return [];
  const list = [...standingsData.value.standings];
  const dir = sortAsc.value ? 1 : -1;

  return list.sort((a, b) => {
    switch (sortCol.value) {
      case 'rank':
        return (a.rank - b.rank) * dir;
      case 'power_rank':
        return (a.power_rank - b.power_rank) * dir;
      case 'median': {
        const aTot = a.median_wins + a.median_losses + a.median_ties;
        const bTot = b.median_wins + b.median_losses + b.median_ties;
        const aPct = aTot > 0 ? (a.median_wins + 0.5 * a.median_ties) / aTot : 0;
        const bPct = bTot > 0 ? (b.median_wins + 0.5 * b.median_ties) / bTot : 0;
        return (aPct - bPct || a.all_play_win_pct - b.all_play_win_pct || a.points_for - b.points_for) * dir;
      }
      case 'points_for':
        return (a.points_for - b.points_for) * dir;
      case 'points_against':
        return (a.points_against - b.points_against) * dir;
      case 'all_play':
        return (a.all_play_win_pct - b.all_play_win_pct || a.points_for - b.points_for) * dir;
      case 'luck':
        return (a.luck_index - b.luck_index) * dir;
      case 'efficiency':
        return (a.lineup_efficiency - b.lineup_efficiency) * dir;
      case 'cash':
        return (a.total_earnings - b.total_earnings) * dir;
      default:
        return (a.rank - b.rank) * dir;
    }
  });
});

const playoffCutoff = computed<number>(() => {
  return standingsData.value?.playoff_team_count ?? 6;
});

// Show playoff divider only when sorted by default rank ascending in standings mode
const showPlayoffDivider = computed<boolean>(() => {
  return (
    tableMode.value === 'standings' &&
    sortCol.value === 'rank' &&
    sortAsc.value &&
    !standingsData.value?.is_completed
  );
});

function formatRecord(s: StandingEntry): string {
  return s.ties > 0 ? `${s.wins}-${s.losses}-${s.ties}` : `${s.wins}-${s.losses}`;
}

function formatMedianRecord(s: StandingEntry): string {
  return s.median_ties > 0
    ? `${s.median_wins}-${s.median_losses}-${s.median_ties}`
    : `${s.median_wins}-${s.median_losses}`;
}

function formatAllPlay(s: StandingEntry): string {
  return s.all_play_ties > 0
    ? `${s.all_play_wins}-${s.all_play_losses}-${s.all_play_ties}`
    : `${s.all_play_wins}-${s.all_play_losses}`;
}

function formatAllPlayPct(s: StandingEntry): string {
  const pct = Math.abs(s.all_play_win_pct) <= 1 ? s.all_play_win_pct * 100 : s.all_play_win_pct;
  return `${pct.toFixed(1)}%`;
}

function formatLuck(val: number): string {
  const pct = Math.abs(val) <= 1 ? val * 100 : val;
  if (Math.abs(pct) < 0.05) return '0.0%';
  return `${pct > 0 ? '+' : ''}${pct.toFixed(1)}%`;
}

function formatStreak(s: StandingEntry): { text: string; isWin: boolean } | null {
  if (!s.streak_type || s.streak_length <= 0) return null;
  const upper = s.streak_type.toUpperCase();
  if (upper.startsWith('W')) return { text: `W${s.streak_length}`, isWin: true };
  if (upper.startsWith('L')) return { text: `L${s.streak_length}`, isWin: false };
  return { text: `T${s.streak_length}`, isWin: false };
}

// Rank delta between Official Standings Rank and All-22 Power Rank
// Positive means Power Rank is BETTER than Official Standings Rank (underrated / unlucky)
function getPowerDelta(s: StandingEntry): number {
  return s.rank - s.power_rank;
}

function openTeamDetail(team: StandingEntry) {
  selectedTeam.value = team;
  drawerOpen.value = true;
}
</script>

<template>
  <div class="max-w-4xl mx-auto space-y-4 pb-20">
    <!-- Compact Editorial Control Bar -->
    <div class="flex items-center justify-between gap-2">
      <div class="flex items-baseline gap-2 min-w-0">
        <h2 class="text-base sm:text-lg font-black uppercase tracking-tight text-slate-100">
          {{ tableMode === 'standings' ? 'Standings' : 'Power Rankings' }}
        </h2>
        <span
          v-if="standingsData"
          class="text-[11px] font-mono text-slate-500 uppercase tracking-wider truncate"
        >
          {{ standingsData.is_completed ? `${standingsData.season_year} Final` : `Wk ${standingsData.current_week}` }}
        </span>
      </div>

      <!-- Segmented Lens Switcher: Standings vs Power Rankings -->
      <div class="inline-flex items-center rounded-lg bg-slate-900 border border-slate-800 p-0.5 text-xs font-semibold shrink-0">
        <button
          type="button"
          class="px-2.5 py-1 rounded-md transition-all"
          :class="
            tableMode === 'standings'
              ? 'bg-slate-800 text-slate-100 shadow-sm border border-slate-700/60'
              : 'text-slate-400 hover:text-slate-200'
          "
          @click="switchMode('standings')"
        >
          Standings
        </button>
        <button
          type="button"
          class="px-2.5 py-1 rounded-md transition-all"
          :class="
            tableMode === 'power'
              ? 'bg-slate-800 text-slate-100 shadow-sm border border-slate-700/60'
              : 'text-slate-400 hover:text-slate-200'
          "
          @click="switchMode('power')"
        >
          Power Ranks
        </button>
      </div>
    </div>

    <!-- Loading State -->
    <LoadingState
      v-if="loading && !standingsData"
      message="Loading league table..."
      variant="cards"
      :rows="6"
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

    <!-- Main Content: Standings Table followed by Standings Race Graph -->
    <div v-else-if="standingsData && sortedStandings.length > 0" class="space-y-4">
      <!-- High-Density Mobile-First Scoreboard Table -->
      <div class="rounded-xl border border-slate-800/90 bg-[#0b101b] overflow-hidden shadow-lg">
        <!-- Column Headers: STANDINGS MODE -->
        <div
          v-if="tableMode === 'standings'"
          class="grid grid-cols-[26px_1fr_46px_50px_56px] sm:grid-cols-[32px_1fr_56px_68px_72px_72px_68px] items-center px-2.5 sm:px-3.5 py-2 bg-slate-900/90 border-b border-slate-800/90 text-[10px] font-mono uppercase tracking-wider text-slate-400 select-none"
        >
          <button
            type="button"
            class="text-left font-bold hover:text-slate-200 transition-colors"
            :class="sortCol === 'rank' ? 'text-amber-400' : ''"
            @click="toggleSort('rank')"
          >
            #
          </button>
          <div class="font-bold">Franchise</div>
          <button
            type="button"
            class="text-right font-bold hover:text-slate-200 transition-colors"
            :class="sortCol === 'rank' ? 'text-slate-200' : ''"
            @click="toggleSort('rank')"
          >
            W-L
          </button>
          <button
            type="button"
            class="text-right font-bold hover:text-slate-200 transition-colors"
            :class="sortCol === 'cash' ? 'text-emerald-400' : ''"
            @click="toggleSort('cash')"
          >
            Cash
          </button>
          <button
            type="button"
            class="text-right font-bold hover:text-slate-200 transition-colors"
            :class="sortCol === 'points_for' ? 'text-amber-400' : ''"
            @click="toggleSort('points_for')"
          >
            PF
          </button>
          <button
            type="button"
            class="hidden sm:block text-right font-bold hover:text-slate-200 transition-colors"
            :class="sortCol === 'points_against' ? 'text-amber-400' : ''"
            @click="toggleSort('points_against')"
          >
            PA
          </button>
          <button
            type="button"
            class="hidden sm:block text-right font-bold hover:text-slate-200 transition-colors"
            :class="sortCol === 'all_play' ? 'text-amber-400' : ''"
            @click="toggleSort('all_play')"
          >
            All-22
          </button>
        </div>

        <!-- Column Headers: POWER MODE (Median & All-Play Tiebreaker) -->
        <div
          v-else
          class="grid grid-cols-[40px_1fr_46px_54px_54px] sm:grid-cols-[48px_1fr_56px_72px_68px_60px_60px] items-center px-2.5 sm:px-3.5 py-2 bg-slate-900/90 border-b border-slate-800/90 text-[10px] font-mono uppercase tracking-wider text-slate-400 select-none"
        >
          <button
            type="button"
            class="text-left font-bold hover:text-slate-200 transition-colors"
            :class="sortCol === 'power_rank' ? 'text-amber-400' : ''"
            @click="toggleSort('power_rank')"
          >
            PWR
          </button>
          <div class="font-bold">Franchise</div>
          <button
            type="button"
            class="text-right font-bold hover:text-slate-200 transition-colors"
            :class="sortCol === 'median' ? 'text-amber-400' : ''"
            @click="toggleSort('median')"
            title="Vs Weekly Median Record (Consistency Metric)"
          >
            Median
          </button>
          <button
            type="button"
            class="text-right font-bold hover:text-slate-200 transition-colors"
            :class="sortCol === 'all_play' ? 'text-amber-400' : ''"
            @click="toggleSort('all_play')"
            title="All-22 All-Play Record (Tiebreaker Metric)"
          >
            All-22
          </button>
          <button
            type="button"
            class="text-right font-bold hover:text-slate-200 transition-colors"
            :class="sortCol === 'points_for' ? 'text-amber-400' : ''"
            @click="toggleSort('points_for')"
          >
            PF
          </button>
          <button
            type="button"
            class="hidden sm:block text-right font-bold hover:text-slate-200 transition-colors"
            :class="sortCol === 'luck' ? 'text-amber-400' : ''"
            @click="toggleSort('luck')"
            title="Schedule Luck Index"
          >
            Luck
          </button>
          <button
            type="button"
            class="hidden sm:block text-right font-bold hover:text-slate-200 transition-colors"
            :class="sortCol === 'efficiency' ? 'text-amber-400' : ''"
            @click="toggleSort('efficiency')"
            title="Lineup Efficiency"
          >
            Eff
          </button>
        </div>

        <!-- Compact Team Rows -->
        <div class="divide-y divide-slate-800/60">
          <template v-for="(s, idx) in sortedStandings" :key="s.team_id">
            <!-- Row Item -->
            <div
              role="button"
              tabindex="0"
              class="relative transition-colors cursor-pointer select-none active:bg-slate-800/70 hover:bg-slate-900/70"
              :class="[
                spotlightTeamId === s.team_id ? 'bg-slate-800/50' : '',
              ]"
              @click="openTeamDetail(s)"
              @keydown.enter="openTeamDetail(s)"
            >
              <!-- Left Edge Status Accent Bar -->
              <span
                class="absolute left-0 inset-y-0 w-[3px]"
                :class="
                  (tableMode === 'standings' ? s.rank : s.power_rank) === 1
                    ? 'bg-amber-400'
                    : s.rank <= playoffCutoff
                    ? 'bg-emerald-500/70'
                    : 'bg-transparent'
                "
              ></span>

              <!-- ROW LAYOUT: STANDINGS MODE -->
              <div
                v-if="tableMode === 'standings'"
                class="grid grid-cols-[26px_1fr_46px_50px_56px] sm:grid-cols-[32px_1fr_56px_68px_72px_72px_68px] items-center px-2.5 sm:px-3.5 py-2.5"
              >
                <!-- Rank -->
                <div
                  class="font-mono text-xs font-black tabular-nums"
                  :class="
                    s.rank === 1
                      ? 'text-amber-400'
                      : s.rank <= playoffCutoff
                      ? 'text-slate-200'
                      : 'text-slate-500'
                  "
                >
                  {{ s.rank }}
                </div>

                <!-- Franchise Cell -->
                <div class="flex items-center gap-2 min-w-0 pr-2">
                  <TeamAvatar :src="s.logo_url" :name="s.team_name" size="xs" rounded="lg" />
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center gap-1.5 min-w-0">
                      <span class="text-[13px] sm:text-sm font-bold text-slate-100 truncate leading-tight">
                        {{ s.team_name }}
                      </span>
                      <span
                        v-if="standingsData.is_completed && s.final_standing === 1"
                        class="text-[9px] font-mono font-black uppercase px-1 py-0.2 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 shrink-0"
                      >
                        CHAMP
                      </span>
                    </div>
                    <div class="flex items-center gap-1.5 text-[10px] text-slate-400 leading-tight mt-0.5 truncate">
                      <span class="truncate">{{ s.manager_name }}</span>
                      <template v-if="formatStreak(s)">
                        <span class="text-slate-700">·</span>
                        <span
                          class="font-mono font-semibold"
                          :class="formatStreak(s)?.isWin ? 'text-emerald-400/90' : 'text-rose-400/80'"
                        >
                          {{ formatStreak(s)?.text }}
                        </span>
                      </template>
                    </div>
                  </div>
                </div>

                <!-- Official W-L Record -->
                <div class="text-right font-mono text-xs sm:text-sm font-bold text-slate-100 tabular-nums">
                  {{ formatRecord(s) }}
                </div>

                <!-- Cash Earnings Column (Right after W-L) -->
                <div class="text-right font-mono tabular-nums">
                  <span
                    class="text-xs sm:text-sm font-bold"
                    :class="s.total_earnings > 0 ? 'text-emerald-400' : 'text-slate-600'"
                  >
                    ${{ s.total_earnings.toFixed(0) }}
                  </span>
                </div>

                <!-- Points For (Clean number, no bar) -->
                <div class="text-right font-mono text-xs sm:text-sm text-slate-200 font-semibold tabular-nums">
                  {{ s.points_for.toFixed(1) }}
                </div>

                <!-- Points Against (Desktop/Tablet) -->
                <div class="hidden sm:block text-right font-mono text-xs text-slate-400 tabular-nums">
                  {{ s.points_against.toFixed(1) }}
                </div>

                <!-- All-22 Record (Desktop/Tablet) -->
                <div class="hidden sm:block text-right font-mono tabular-nums">
                  <div class="text-[11px] text-slate-300 font-medium">
                    {{ formatAllPlay(s) }}
                  </div>
                  <div class="text-[9px] text-slate-500">
                    Pwr #{{ s.power_rank }}
                  </div>
                </div>
              </div>

              <!-- ROW LAYOUT: POWER MODE -->
              <div
                v-else
                class="grid grid-cols-[40px_1fr_46px_54px_54px] sm:grid-cols-[48px_1fr_56px_72px_68px_60px_60px] items-center px-2.5 sm:px-3.5 py-2.5"
              >
                <!-- Power Rank + Delta vs Official Standings -->
                <div class="flex items-center gap-1 font-mono tabular-nums">
                  <span
                    class="text-xs font-black w-4"
                    :class="s.power_rank === 1 ? 'text-amber-400' : 'text-slate-200'"
                  >
                    {{ s.power_rank }}
                  </span>
                  <span
                    v-if="getPowerDelta(s) > 0"
                    class="text-[9px] font-bold text-emerald-400"
                    :title="`Power Rank is ${getPowerDelta(s)} spots higher than Standings (#${s.rank})`"
                  >
                    ▲{{ getPowerDelta(s) }}
                  </span>
                  <span
                    v-else-if="getPowerDelta(s) < 0"
                    class="text-[9px] font-bold text-rose-400"
                    :title="`Power Rank is ${Math.abs(getPowerDelta(s))} spots lower than Standings (#${s.rank})`"
                  >
                    ▼{{ Math.abs(getPowerDelta(s)) }}
                  </span>
                  <span v-else class="text-[9px] text-slate-600">—</span>
                </div>

                <!-- Franchise Cell -->
                <div class="flex items-center gap-2 min-w-0 pr-2">
                  <TeamAvatar :src="s.logo_url" :name="s.team_name" size="xs" rounded="lg" />
                  <div class="min-w-0 flex-1">
                    <div class="text-[13px] sm:text-sm font-bold text-slate-100 truncate leading-tight">
                      {{ s.team_name }}
                    </div>
                    <div class="flex items-center gap-1.5 text-[10px] text-slate-400 leading-tight mt-0.5 truncate">
                      <span class="truncate">{{ s.manager_name }}</span>
                      <span class="text-slate-700">·</span>
                      <span class="font-mono text-slate-400">
                        {{ formatRecord(s) }} (#{{ s.rank }})
                      </span>
                    </div>
                  </div>
                </div>

                <!-- Median Record (Primary Metric) -->
                <div class="text-right font-mono text-xs sm:text-sm font-bold text-slate-100 tabular-nums">
                  {{ formatMedianRecord(s) }}
                </div>

                <!-- All-22 Record (Tiebreaker Metric) -->
                <div class="text-right font-mono tabular-nums">
                  <div class="text-xs font-semibold text-slate-200">
                    {{ formatAllPlay(s) }}
                  </div>
                  <div class="text-[9px] text-slate-400">
                    {{ formatAllPlayPct(s) }}
                  </div>
                </div>

                <!-- Points For -->
                <div class="text-right font-mono text-xs sm:text-sm text-slate-200 font-semibold tabular-nums">
                  {{ s.points_for.toFixed(1) }}
                </div>

                <!-- Schedule Luck Index (Desktop/Tablet) -->
                <div class="hidden sm:block text-right font-mono tabular-nums">
                  <span
                    class="text-[11px] font-semibold"
                    :class="
                      s.luck_index > 0.05
                        ? 'text-emerald-400'
                        : s.luck_index < -0.05
                        ? 'text-rose-400'
                        : 'text-slate-400'
                    "
                  >
                    {{ formatLuck(s.luck_index) }}
                  </span>
                </div>

                <!-- Lineup Efficiency (Desktop/Tablet) -->
                <div class="hidden sm:block text-right font-mono text-xs text-slate-300 tabular-nums">
                  {{ (s.lineup_efficiency <= 1 ? s.lineup_efficiency * 100 : s.lineup_efficiency).toFixed(1) }}%
                </div>
              </div>
            </div>

            <!-- Playoff Cutoff Line -->
            <div
              v-if="showPlayoffDivider && idx + 1 === playoffCutoff && idx + 1 < sortedStandings.length"
              class="px-3 py-1 bg-slate-950/90 border-y border-emerald-500/30 flex items-center justify-between text-[9px] font-mono uppercase tracking-widest text-emerald-400/90"
            >
              <span>▲ Playoff Cutline (Top {{ playoffCutoff }})</span>
              <span class="text-slate-500">Elimination Zone ▼</span>
            </div>
          </template>
        </div>
      </div>

      <!-- Mario Party Style Weekly Standings Race Graphic (Below Standings) -->
      <WeeklyTrajectoryChart
        v-model:selected-team-id="spotlightTeamId"
        :standings="standingsData.standings"
        :playoff-team-count="playoffCutoff"
        @open-team-detail="openTeamDetail"
      />

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
