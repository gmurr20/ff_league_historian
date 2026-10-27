<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useLeagueMeta } from '@/composables/useLeagueMeta';
import { fetchStandings } from '@/api/client';
import type { StandingEntry, StandingsResponse } from '@/types/api';
import WeeklyTrajectoryChart from '@/components/standings/WeeklyTrajectoryChart.vue';
import StandingsDetailDrawer from '@/components/standings/StandingsDetailDrawer.vue';
import PlayoffBracket from '@/components/standings/PlayoffBracket.vue';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import LoadingState from '@/components/ui/LoadingState.vue';
import EmptyState from '@/components/ui/EmptyState.vue';

const { selectedSeason, meta } = useLeagueMeta();

const standingsData = ref<StandingsResponse | null>(null);
const loading = ref<boolean>(false);
const error = ref<string | null>(null);

// Dynamic Trophy / Championship Title (generic across leagues, defaulting to "The Pauley" if not set)
const trophyTitle = computed<string>(() => {
  const envTrophy = (import.meta.env.VITE_TROPHY_NAME as string | undefined)?.trim();
  if (envTrophy) return envTrophy;
  const league = meta.value?.league_name || '';
  if (league.toLowerCase().includes('pauley')) return 'The Pauley';
  return 'The Pauley';
});

// All-Time vs Single Season Mode
const isAllTime = computed<boolean>(() => {
  return selectedSeason.value === null || standingsData.value?.season_year === null;
});

// Franchise status filter in All-Time mode: 'active' vs 'all' (default: 'active' first)
type InactiveFilterMode = 'active' | 'all';
const inactiveFilter = ref<InactiveFilterMode>('active');

const totalFranchisesCount = computed<number>(() => {
  return standingsData.value?.standings.length ?? 0;
});

const activeStandings = computed<StandingEntry[]>(() => {
  if (!standingsData.value?.standings) return [];
  return standingsData.value.standings.filter((s) => s.is_active);
});

const inactiveStandings = computed<StandingEntry[]>(() => {
  if (!standingsData.value?.standings) return [];
  return standingsData.value.standings.filter((s) => !s.is_active);
});

const activeFranchisesCount = computed<number>(() => {
  return activeStandings.value.length;
});

// Maps each active team to their official rank among active members (1..12)
const activeRankMap = computed<Map<number, number>>(() => {
  const map = new Map<number, number>();
  activeStandings.value.forEach((s, idx) => {
    map.set(s.team_id, idx + 1);
  });
  return map;
});

// Maps each active team to their power rank among active members (1..12)
const activePowerRankMap = computed<Map<number, number>>(() => {
  const map = new Map<number, number>();
  const sorted = [...activeStandings.value].sort((a, b) => {
    return (
      b.all_play_win_pct - a.all_play_win_pct ||
      b.median_wins - a.median_wins ||
      b.points_for - a.points_for
    );
  });
  sorted.forEach((s, idx) => {
    map.set(s.team_id, idx + 1);
  });
  return map;
});

// Returns contextual official rank: in 'active' mode returns 1..12, in 'all' mode returns overall rank (1..19)
function getTeamRank(s: StandingEntry): number {
  if (isAllTime.value && inactiveFilter.value === 'active') {
    return activeRankMap.value.get(s.team_id) ?? s.rank;
  }
  return s.rank;
}

// Returns contextual power rank: in 'active' mode returns 1..12, in 'all' mode returns overall power rank (1..19)
function getTeamPowerRank(s: StandingEntry): number {
  if (isAllTime.value && inactiveFilter.value === 'active') {
    return activePowerRankMap.value.get(s.team_id) ?? s.power_rank;
  }
  return s.power_rank;
}

// Rank delta between official standings rank and power rank (positive = underrated)
function getPowerDelta(s: StandingEntry): number {
  return getTeamRank(s) - getTeamPowerRank(s);
}

// Primary Table Mode: 'standings' (Official W-L) vs 'power' (Median & All-Play)
type TableMode = 'standings' | 'power';
const tableMode = ref<TableMode>('standings');

// Column sort override within active mode
type SortColumn = 'rank' | 'power_rank' | 'median' | 'points_for' | 'points_against' | 'all_play' | 'luck' | 'efficiency' | 'cash' | 'titles';
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
    inactiveFilter.value = 'active'; // Default to active first!
    loadStandings();
  }
);

onMounted(() => {
  loadStandings();
});

function sortList(list: StandingEntry[]): StandingEntry[] {
  const dir = sortAsc.value ? 1 : -1;
  return [...list].sort((a, b) => {
    switch (sortCol.value) {
      case 'rank': {
        const aRank = getTeamRank(a);
        const bRank = getTeamRank(b);
        return (aRank - bRank) * dir;
      }
      case 'power_rank': {
        const aPwr = getTeamPowerRank(a);
        const bPwr = getTeamPowerRank(b);
        return (aPwr - bPwr) * dir;
      }
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
      case 'titles':
        return (
          (a.championships - b.championships ||
            a.runner_ups - b.runner_ups ||
            a.third_places - b.third_places ||
            a.total_earnings - b.total_earnings) * dir
        );
      default: {
        const aRank = getTeamRank(a);
        const bRank = getTeamRank(b);
        return (aRank - bRank) * dir;
      }
    }
  });
}

// Active / Primary group (single season = all teams, all-time = active teams)
const sortedActiveStandings = computed<StandingEntry[]>(() => {
  if (!standingsData.value?.standings) return [];
  if (!isAllTime.value) {
    return sortList(standingsData.value.standings);
  }
  return sortList(activeStandings.value);
});

// Inactive group (shown later in all-time mode when inactiveFilter === 'all')
const sortedInactiveStandings = computed<StandingEntry[]>(() => {
  if (!standingsData.value?.standings || !isAllTime.value || inactiveFilter.value !== 'all') {
    return [];
  }
  return sortList(inactiveStandings.value);
});

export type TableDisplayRow =
  | { type: 'team'; standing: StandingEntry; isInactiveGroup: boolean; activeIndex: number }
  | { type: 'inactive-header'; count: number };

const displayRows = computed<TableDisplayRow[]>(() => {
  const rows: TableDisplayRow[] = [];
  sortedActiveStandings.value.forEach((s, idx) => {
    rows.push({ type: 'team', standing: s, isInactiveGroup: false, activeIndex: idx });
  });

  if (isAllTime.value && inactiveFilter.value === 'all' && sortedInactiveStandings.value.length > 0) {
    rows.push({ type: 'inactive-header', count: sortedInactiveStandings.value.length });
    sortedInactiveStandings.value.forEach((s) => {
      rows.push({ type: 'team', standing: s, isInactiveGroup: true, activeIndex: -1 });
    });
  }

  return rows;
});

const playoffCutoff = computed<number>(() => {
  return standingsData.value?.playoff_team_count ?? 6;
});

// Unified grid column tracks ensuring zero layout shift between Standings and Power Rankings
const gridColsClass = computed<string>(() => {
  if (isAllTime.value) {
    return tableMode.value === 'standings'
      ? 'grid-cols-[34px_1fr_44px_56px_48px] sm:grid-cols-[44px_1fr_56px_72px_64px_68px_68px_68px]'
      : 'grid-cols-[34px_1fr_44px_56px_48px] sm:grid-cols-[44px_1fr_56px_72px_68px_60px_60px]';
  }
  return tableMode.value === 'standings'
    ? 'grid-cols-[34px_1fr_44px_48px_48px] sm:grid-cols-[44px_1fr_56px_68px_68px_68px_68px]'
    : 'grid-cols-[34px_1fr_44px_48px_48px] sm:grid-cols-[44px_1fr_56px_68px_68px_60px_60px]';
});

function getRankColor(standing: StandingEntry, isInactiveGroup: boolean): string {
  const rank = tableMode.value === 'standings' ? getTeamRank(standing) : getTeamPowerRank(standing);
  if (rank === 1) return 'text-amber-400';
  if (isInactiveGroup) return 'text-slate-500';
  if (!isAllTime.value && tableMode.value === 'standings' && standing.rank <= playoffCutoff.value) {
    return 'text-slate-200';
  }
  return tableMode.value === 'power' ? 'text-slate-200' : 'text-slate-300';
}

// Show playoff divider only when sorted by default rank ascending in single season standings mode
const showPlayoffDivider = computed<boolean>(() => {
  return (
    tableMode.value === 'standings' &&
    sortCol.value === 'rank' &&
    sortAsc.value &&
    !isAllTime.value &&
    !standingsData.value?.is_completed
  );
});

function getSeasonsCount(s: StandingEntry): number {
  return s.weekly_history?.length || 1;
}

function formatSportsPct(pct: number): string {
  const formatted = pct.toFixed(3);
  return formatted.startsWith('0.') ? formatted.slice(1) : formatted;
}

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
  const pct = Math.abs(s.all_play_win_pct) <= 1 ? s.all_play_win_pct : s.all_play_win_pct / 100;
  if (isAllTime.value) {
    return formatSportsPct(pct);
  }
  return `${(pct * 100).toFixed(1)}%`;
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

function openTeamDetail(team: StandingEntry) {
  selectedTeam.value = team;
  drawerOpen.value = true;
}

function handleOpenTeamById(teamId: number) {
  const found = standingsData.value?.standings.find((s) => s.team_id === teamId);
  if (found) {
    openTeamDetail(found);
  }
}
</script>

<template>
  <div class="max-w-4xl mx-auto space-y-4 pb-20">
    <!-- Playoff Bracket (Featured at top when available: after regular season or completed season) -->
    <PlayoffBracket
      v-if="standingsData && standingsData.playoff_bracket && standingsData.playoff_bracket.is_available"
      :bracket="standingsData.playoff_bracket"
      :trophy-name="trophyTitle"
      @open-team="handleOpenTeamById"
    />

    <!-- Compact Editorial Control Bar -->
    <div class="flex items-center justify-between gap-1.5 sm:gap-2 min-w-0">
      <div class="flex items-baseline gap-1.5 sm:gap-2 min-w-0 flex-1">
        <h2 class="text-sm sm:text-lg font-black uppercase tracking-tight text-slate-100 truncate">
          {{ isAllTime ? 'All-Time Standings' : (tableMode === 'standings' ? 'Standings' : 'Power Rankings') }}
        </h2>
        <span
          v-if="standingsData && !isAllTime"
          class="text-[10px] sm:text-[11px] font-mono text-slate-500 uppercase tracking-wider shrink-0"
        >
          {{ standingsData.is_completed ? `${standingsData.season_year} Final` : `Wk ${standingsData.current_week}` }}
        </span>
      </div>

      <div class="flex items-center gap-1.5 sm:gap-2 shrink-0">
        <!-- Inactive Filter Pill (All-Time mode only) -->
        <div
          v-if="isAllTime"
          class="inline-flex items-center rounded-lg bg-slate-900 border border-slate-800 p-0.5 text-xs font-semibold shrink-0"
        >
          <button
            type="button"
            class="px-2 sm:px-2.5 py-1 rounded-md transition-all text-xs font-mono"
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
            class="px-2 sm:px-2.5 py-1 rounded-md transition-all text-xs font-mono"
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

        <!-- Segmented Lens Switcher: Standings vs Power Rankings -->
        <div class="inline-flex items-center rounded-lg bg-slate-900 border border-slate-800 p-0.5 text-xs font-semibold shrink-0">
          <button
            type="button"
            class="px-2 sm:px-2.5 py-1 rounded-md transition-all"
            :class="
              tableMode === 'standings'
                ? 'bg-slate-800 text-slate-100 shadow-sm border border-slate-700/60 font-bold'
                : 'text-slate-400 hover:text-slate-200'
            "
            @click="switchMode('standings')"
          >
            Standings
          </button>
          <button
            type="button"
            class="px-2 sm:px-2.5 py-1 rounded-md transition-all"
            :class="
              tableMode === 'power'
                ? 'bg-slate-800 text-slate-100 shadow-sm border border-slate-700/60 font-bold'
                : 'text-slate-400 hover:text-slate-200'
            "
            @click="switchMode('power')"
          >
            Power Rankings
          </button>
        </div>
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
    <div v-else-if="standingsData && displayRows.length > 0" class="space-y-4">
      <!-- High-Density Mobile-First Scoreboard Table -->
      <div class="rounded-xl border border-slate-800/90 bg-[#0b101b] overflow-hidden shadow-lg">
        <!-- Column Headers -->
        <div
          class="grid items-center px-2.5 sm:px-3.5 py-2 bg-slate-900/90 border-b border-slate-800/90 text-[10px] font-mono uppercase tracking-wider text-slate-400 select-none"
          :class="gridColsClass"
        >
          <!-- Col 1: # or PWR -->
          <button
            type="button"
            class="text-left font-bold hover:text-slate-200 transition-colors"
            :class="(tableMode === 'standings' ? sortCol === 'rank' : sortCol === 'power_rank') ? 'text-amber-400' : ''"
            @click="toggleSort(tableMode === 'standings' ? 'rank' : 'power_rank')"
            :title="tableMode === 'standings' ? 'Official Standings Rank' : 'Analytical Power Rank'"
          >
            {{ tableMode === 'standings' ? '#' : 'PWR' }}
          </button>

          <!-- Col 2: Franchise -->
          <div class="font-bold">Franchise</div>

          <!-- Col 3: W-L (Standings) or Median (Power) -->
          <button
            type="button"
            class="text-right font-bold hover:text-slate-200 transition-colors"
            :class="(tableMode === 'standings' ? sortCol === 'rank' : sortCol === 'median') ? 'text-slate-200' : ''"
            @click="toggleSort(tableMode === 'standings' ? 'rank' : 'median')"
            :title="tableMode === 'standings' ? 'Official W-L Record' : 'Vs Weekly Median Record'"
          >
            {{ tableMode === 'standings' ? 'W-L' : 'Median' }}
          </button>

          <!-- Col 4: Cash (Single-Season Standings) | Titles (All-Time Standings) | All-Play (Power) -->
          <template v-if="tableMode === 'standings'">
            <button
              v-if="isAllTime"
              type="button"
              class="text-right font-bold hover:text-slate-200 transition-colors"
              :class="sortCol === 'titles' ? 'text-amber-400' : ''"
              @click="toggleSort('titles')"
              title="Podium Titles & Finishes (1st, 2nd, 3rd)"
            >
              Titles
            </button>
            <button
              v-else
              type="button"
              class="text-right font-bold hover:text-slate-200 transition-colors"
              :class="sortCol === 'cash' ? 'text-emerald-400' : ''"
              @click="toggleSort('cash')"
              title="Total Cash Earnings"
            >
              Cash
            </button>
          </template>
          <template v-else>
            <button
              type="button"
              class="text-right font-bold hover:text-slate-200 transition-colors"
              :class="sortCol === 'all_play' ? 'text-amber-400' : ''"
              @click="toggleSort('all_play')"
              title="All-Play Win Percentage (Tiebreaker Metric)"
            >
              All-Play
            </button>
          </template>

          <!-- Col 5: Cash (All-Time Standings) | PF (Single-Season Standings & Power) -->
          <template v-if="tableMode === 'standings' && isAllTime">
            <button
              type="button"
              class="text-right font-bold hover:text-slate-200 transition-colors"
              :class="sortCol === 'cash' ? 'text-emerald-400' : ''"
              @click="toggleSort('cash')"
              title="Career Cash Earnings"
            >
              Cash
            </button>
          </template>
          <template v-else>
            <button
              type="button"
              class="text-right font-bold hover:text-slate-200 transition-colors"
              :class="sortCol === 'points_for' ? 'text-amber-400' : ''"
              @click="toggleSort('points_for')"
              title="Points For"
            >
              PF
            </button>
          </template>

          <!-- Desktop Columns (sm:block) -->
          <template v-if="tableMode === 'standings'">
            <!-- Single-Season Desktop: PA, All-Play -->
            <template v-if="!isAllTime">
              <button
                type="button"
                class="hidden sm:block text-right font-bold hover:text-slate-200 transition-colors"
                :class="sortCol === 'points_against' ? 'text-amber-400' : ''"
                @click="toggleSort('points_against')"
                title="Points Against"
              >
                PA
              </button>
              <button
                type="button"
                class="hidden sm:block text-right font-bold hover:text-slate-200 transition-colors"
                :class="sortCol === 'all_play' ? 'text-amber-400' : ''"
                @click="toggleSort('all_play')"
                title="All-Play Record & Power Rank"
              >
                All-Play
              </button>
            </template>
            <!-- All-Time Desktop: PF, PA, All-Play -->
            <template v-else>
              <button
                type="button"
                class="hidden sm:block text-right font-bold hover:text-slate-200 transition-colors"
                :class="sortCol === 'points_for' ? 'text-amber-400' : ''"
                @click="toggleSort('points_for')"
                title="Career Points For"
              >
                PF
              </button>
              <button
                type="button"
                class="hidden sm:block text-right font-bold hover:text-slate-200 transition-colors"
                :class="sortCol === 'points_against' ? 'text-amber-400' : ''"
                @click="toggleSort('points_against')"
                title="Career Points Against"
              >
                PA
              </button>
              <button
                type="button"
                class="hidden sm:block text-right font-bold hover:text-slate-200 transition-colors"
                :class="sortCol === 'all_play' ? 'text-amber-400' : ''"
                @click="toggleSort('all_play')"
                title="Career All-Play Record & Win Percentage"
              >
                All-Play
              </button>
            </template>
          </template>
          <template v-else>
            <!-- Power Mode Desktop: Luck, Eff -->
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
          </template>
        </div>

        <!-- Compact Team Rows -->
        <div class="divide-y divide-slate-800/60">
          <template v-for="row in displayRows" :key="row.type === 'inactive-header' ? 'inactive-header' : row.standing.team_id">
            <!-- Former / Inactive Franchises Divider Header (Shown later when toggle is 'all') -->
            <div
              v-if="row.type === 'inactive-header'"
              class="px-3 sm:px-3.5 py-2 bg-slate-950/95 border-y border-slate-800/90 flex items-center justify-between gap-2 text-xs font-mono select-none"
            >
              <div class="flex items-center gap-2 min-w-0">
                <span class="text-xs">🏛️</span>
                <span class="text-[11px] font-bold uppercase tracking-wider text-slate-300 truncate">
                  Former / Inactive Franchises ({{ row.count }})
                </span>
                <span class="hidden sm:inline text-[10px] text-slate-500">
                  · Past competitors no longer active in current season
                </span>
              </div>
              <span class="text-[9.5px] text-slate-500 uppercase tracking-widest shrink-0 font-semibold">
                All-Time
              </span>
            </div>

            <!-- Team Row Item -->
            <div
              v-else
              role="button"
              tabindex="0"
              class="relative transition-colors cursor-pointer select-none active:bg-slate-800/70 hover:bg-slate-900/70"
              :class="[
                spotlightTeamId === row.standing.team_id ? 'bg-slate-800/50' : '',
                row.isInactiveGroup ? 'opacity-65 hover:opacity-100 bg-slate-950/40' : '',
              ]"
              @click="openTeamDetail(row.standing)"
              @keydown.enter="openTeamDetail(row.standing)"
            >
              <!-- Left Edge Status Accent Bar -->
              <span
                class="absolute left-0 inset-y-0 w-[3px]"
                :class="
                  (tableMode === 'standings' ? getTeamRank(row.standing) : getTeamPowerRank(row.standing)) === 1
                    ? 'bg-amber-400'
                    : row.standing.is_defending_champion
                    ? 'bg-amber-400/80 shadow-[0_0_8px_rgba(251,191,36,0.4)]'
                    : (!isAllTime && tableMode === 'standings' && row.standing.rank <= playoffCutoff)
                    ? 'bg-emerald-500/70'
                    : 'bg-transparent'
                "
              ></span>

              <div
                class="grid items-center px-2.5 sm:px-3.5 py-2.5"
                :class="gridColsClass"
              >
                <!-- Col 1: Rank Number + Delta Indicator -->
                <div class="flex items-center gap-1 font-mono tabular-nums">
                  <span
                    class="text-xs font-black w-4 text-left"
                    :class="getRankColor(row.standing, row.isInactiveGroup)"
                  >
                    {{ tableMode === 'standings' ? getTeamRank(row.standing) : getTeamPowerRank(row.standing) }}
                  </span>
                  <span
                    v-if="getPowerDelta(row.standing) > 0"
                    class="text-[9px] font-bold text-emerald-400"
                    :title="`Power Rank (#${getTeamPowerRank(row.standing)}) is ${getPowerDelta(row.standing)} spots higher than Standings (#${getTeamRank(row.standing)})`"
                  >
                    ▲{{ getPowerDelta(row.standing) }}
                  </span>
                  <span
                    v-else-if="getPowerDelta(row.standing) < 0"
                    class="text-[9px] font-bold text-rose-400"
                    :title="`Power Rank (#${getTeamPowerRank(row.standing)}) is ${Math.abs(getPowerDelta(row.standing))} spots lower than Standings (#${getTeamRank(row.standing)})`"
                  >
                    ▼{{ Math.abs(getPowerDelta(row.standing)) }}
                  </span>
                  <span v-else class="text-[9px] text-slate-600">—</span>
                </div>

                <!-- Col 2: Franchise Cell -->
                <div class="flex items-center gap-2 min-w-0 pr-1">
                  <TeamAvatar :src="row.standing.logo_url" :name="row.standing.team_name" size="xs" rounded="lg" />
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center gap-1.5 min-w-0">
                      <span class="text-[13px] sm:text-sm font-bold text-slate-100 truncate leading-tight">
                        {{ row.standing.team_name }}
                      </span>
                      <!-- Former / Inactive Franchise Badge -->
                      <span
                        v-if="isAllTime && !row.standing.is_active"
                        class="inline-flex items-center text-[8.5px] font-mono font-bold uppercase px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 border border-slate-700/80 shrink-0 select-none"
                        title="Former Franchise Manager — No longer active in current season"
                      >
                        INACTIVE
                      </span>
                      <!-- Championship Stars (Soccer / World Cup style: 1 star per title) -->
                      <div
                        v-if="row.standing.championships > 0"
                        class="inline-flex items-center gap-0.5 shrink-0"
                        :title="`${row.standing.championships}x Champion (${row.standing.championship_years.join(', ')})`"
                      >
                        <span
                          v-for="yr in row.standing.championship_years"
                          :key="yr"
                          class="text-amber-400 text-xs sm:text-sm leading-none drop-shadow-[0_0_5px_rgba(251,191,36,0.6)] select-none"
                        >
                          ★
                        </span>
                      </div>
                      <!-- Special Symbol / Indicator for Previous Champion (Defending Champion) -->
                      <span
                        v-if="row.standing.is_defending_champion"
                        class="inline-flex items-center gap-1 text-[9px] font-mono font-black uppercase px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/35 shrink-0 shadow-sm"
                        :title="`Defending Champion — Current Holder of ${trophyTitle}`"
                      >
                        <span class="text-[10px]">🏆</span>
                        <span class="hidden xs:inline">DEFENDING</span> CHAMP
                      </span>
                      <!-- Completed Season Winner Badge -->
                      <span
                        v-else-if="standingsData.is_completed && row.standing.final_standing === 1"
                        class="inline-flex items-center gap-1 text-[9px] font-mono font-black uppercase px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 shrink-0"
                      >
                        <span class="text-[10px]">🏆</span>
                        <span>CHAMP</span>
                      </span>
                    </div>
                    <div class="flex items-center gap-1.5 text-[10px] text-slate-400 leading-tight mt-0.5 min-w-0">
                      <span class="truncate">{{ row.standing.manager_name }}</span>
                      <template v-if="tableMode === 'power'">
                        <span class="text-slate-700 shrink-0">·</span>
                        <span class="font-mono text-slate-400 shrink-0">
                          {{ formatRecord(row.standing) }} (#{{ getTeamRank(row.standing) }})
                        </span>
                      </template>
                      <template v-else-if="!isAllTime && formatStreak(row.standing)">
                        <span class="text-slate-700 shrink-0">·</span>
                        <span
                          class="font-mono font-semibold shrink-0"
                          :class="formatStreak(row.standing)?.isWin ? 'text-emerald-400/90' : 'text-rose-400/80'"
                        >
                          {{ formatStreak(row.standing)?.text }}
                        </span>
                      </template>
                      <template v-if="isAllTime">
                        <span class="text-slate-700 shrink-0">·</span>
                        <span
                          class="text-[9.5px] font-mono text-slate-400 shrink-0 select-none"
                          :title="`${getSeasonsCount(row.standing)} ${getSeasonsCount(row.standing) === 1 ? 'season' : 'seasons'} in league history`"
                        >
                          {{ getSeasonsCount(row.standing) }} {{ getSeasonsCount(row.standing) === 1 ? 'season' : 'seasons' }}
                        </span>
                      </template>
                      <template v-if="isAllTime && inactiveFilter === 'all' && row.standing.is_active && activeRankMap.get(row.standing.team_id)">
                        <span class="text-slate-700 shrink-0">·</span>
                        <span class="font-mono text-[9.5px] text-emerald-400/90 font-medium shrink-0">#{{ activeRankMap.get(row.standing.team_id) }} Active</span>
                      </template>
                    </div>
                  </div>
                </div>

                <!-- Col 3: W-L or Median Record -->
                <div class="text-right font-mono text-xs sm:text-sm font-bold text-slate-100 tabular-nums">
                  {{ tableMode === 'standings' ? formatRecord(row.standing) : formatMedianRecord(row.standing) }}
                </div>

                <!-- Col 4: Titles (All-Time Standings) | Cash (Single-Season Standings) | All-Play (Power Mode) -->
                <template v-if="tableMode === 'standings'">
                  <!-- Titles Column (All-Time mode only: 1st, 2nd, 3rd) -->
                  <div
                    v-if="isAllTime"
                    class="text-right font-mono tabular-nums flex items-center justify-end gap-1 text-[11px] sm:text-xs"
                  >
                    <span
                      v-if="row.standing.championships > 0"
                      class="font-bold text-amber-400 select-none whitespace-nowrap"
                      :title="`${row.standing.championships}x Champion (${row.standing.championship_years.join(', ')})`"
                    >
                      🏆{{ row.standing.championships }}
                    </span>
                    <span
                      v-if="row.standing.runner_ups > 0"
                      class="font-medium text-slate-300 select-none whitespace-nowrap"
                      :title="`${row.standing.runner_ups}x Runner-Up (${row.standing.runner_up_years.join(', ')})`"
                    >
                      🥈{{ row.standing.runner_ups }}
                    </span>
                    <span
                      v-if="row.standing.third_places > 0"
                      class="font-medium text-amber-600 select-none whitespace-nowrap"
                      :title="`${row.standing.third_places}x 3rd Place (${row.standing.third_place_years.join(', ')})`"
                    >
                      🥉{{ row.standing.third_places }}
                    </span>
                    <span
                      v-if="row.standing.championships === 0 && row.standing.runner_ups === 0 && row.standing.third_places === 0"
                      class="text-slate-600 select-none"
                    >
                      —
                    </span>
                  </div>
                  <!-- Cash Earnings Column (Single-Season mode) -->
                  <div v-else class="text-right font-mono tabular-nums">
                    <span
                      class="text-xs sm:text-sm font-bold"
                      :class="row.standing.total_earnings > 0 ? 'text-emerald-400' : 'text-slate-600'"
                    >
                      ${{ row.standing.total_earnings.toFixed(0) }}
                    </span>
                  </div>
                </template>
                <template v-else>
                  <!-- All-Play Column (Power Mode: single-line on mobile, 2-line on desktop) -->
                  <div class="text-right font-mono tabular-nums">
                    <div class="hidden sm:block text-xs font-semibold text-slate-200">
                      {{ formatAllPlay(row.standing) }}
                    </div>
                    <div class="text-xs sm:text-[9px] font-semibold sm:font-normal text-slate-200 sm:text-slate-400">
                      {{ formatAllPlayPct(row.standing) }}
                    </div>
                  </div>
                </template>

                <!-- Col 5: Cash (All-Time Standings) | PF (Single-Season Standings & Power Mode) -->
                <template v-if="tableMode === 'standings' && isAllTime">
                  <div class="text-right font-mono tabular-nums">
                    <span
                      class="text-xs sm:text-sm font-bold"
                      :class="row.standing.total_earnings > 0 ? 'text-emerald-400' : 'text-slate-600'"
                    >
                      ${{ row.standing.total_earnings.toFixed(0) }}
                    </span>
                  </div>
                </template>
                <template v-else>
                  <div class="text-right font-mono text-xs sm:text-sm text-slate-200 font-semibold tabular-nums">
                    {{ row.standing.points_for.toFixed(1) }}
                  </div>
                </template>

                <!-- Desktop Columns (sm:block) -->
                <template v-if="tableMode === 'standings'">
                  <!-- Single-Season Desktop: PA, All-Play -->
                  <template v-if="!isAllTime">
                    <!-- Points Against (Desktop/Tablet) -->
                    <div class="hidden sm:block text-right font-mono text-xs text-slate-400 tabular-nums">
                      {{ row.standing.points_against.toFixed(1) }}
                    </div>
                    <!-- All-22 Record (Desktop/Tablet) -->
                    <div class="hidden sm:block text-right font-mono tabular-nums">
                      <div class="text-[11px] text-slate-300 font-medium">
                        {{ formatAllPlay(row.standing) }}
                      </div>
                      <div class="text-[9px] text-slate-500">
                        Pwr #{{ getTeamPowerRank(row.standing) }}
                      </div>
                    </div>
                  </template>
                  <!-- All-Time Desktop: PF, PA, All-Play -->
                  <template v-else>
                    <!-- Points For (Desktop/Tablet in All-Time) -->
                    <div class="hidden sm:block text-right font-mono text-xs sm:text-sm text-slate-200 font-semibold tabular-nums">
                      {{ row.standing.points_for.toFixed(1) }}
                    </div>
                    <!-- Points Against (Desktop/Tablet) -->
                    <div class="hidden sm:block text-right font-mono text-xs text-slate-400 tabular-nums">
                      {{ row.standing.points_against.toFixed(1) }}
                    </div>
                    <!-- All-22 Record (Desktop/Tablet) -->
                    <div class="hidden sm:block text-right font-mono tabular-nums">
                      <div class="text-[11px] text-slate-300 font-medium">
                        {{ formatAllPlay(row.standing) }}
                      </div>
                      <div class="text-[9px] text-slate-500">
                        Pwr #{{ getTeamPowerRank(row.standing) }}
                      </div>
                    </div>
                  </template>
                </template>
                <template v-else>
                  <!-- Power Mode Desktop: Luck, Eff -->
                  <!-- Schedule Luck Index (Desktop/Tablet) -->
                  <div class="hidden sm:block text-right font-mono tabular-nums">
                    <span
                      class="text-[11px] font-semibold"
                      :class="
                        row.standing.luck_index > 0.05
                          ? 'text-emerald-400'
                          : row.standing.luck_index < -0.05
                          ? 'text-rose-400'
                          : 'text-slate-400'
                      "
                    >
                      {{ formatLuck(row.standing.luck_index) }}
                    </span>
                  </div>
                  <!-- Lineup Efficiency (Desktop/Tablet) -->
                  <div class="hidden sm:block text-right font-mono text-xs text-slate-300 tabular-nums">
                    <span v-if="!row.standing.lineup_efficiency || row.standing.lineup_efficiency <= 0" class="text-slate-500 select-none">—</span>
                    <span v-else>{{ Math.min(100, Math.max(0, row.standing.lineup_efficiency <= 1 ? row.standing.lineup_efficiency * 100 : row.standing.lineup_efficiency)).toFixed(1) }}%</span>
                  </div>
                </template>
              </div>
            </div>

            <!-- Playoff Cutoff Line -->
            <div
              v-if="showPlayoffDivider && row.type === 'team' && !row.isInactiveGroup && row.activeIndex + 1 === playoffCutoff && row.activeIndex + 1 < sortedActiveStandings.length"
              class="px-3 py-1 bg-slate-950/90 border-y border-emerald-500/30 flex items-center justify-between text-[9px] font-mono uppercase tracking-widest text-emerald-400/90"
            >
              <span>▲ Playoff Cutline (Top {{ playoffCutoff }})</span>
              <span class="text-slate-500">Elimination Zone ▼</span>
            </div>
          </template>
        </div>
      </div>

      <!-- Weekly Standings Race Graphic (Single-Season only) -->
      <WeeklyTrajectoryChart
        v-if="!isAllTime"
        v-model:selected-team-id="spotlightTeamId"
        :standings="standingsData.standings"
        :playoff-team-count="playoffCutoff"
        :regular-season-weeks="standingsData.regular_season_weeks"
        :trophy-name="trophyTitle"
        @open-team-detail="openTeamDetail"
      />

      <!-- Detail SwipeDrawer -->
      <StandingsDetailDrawer
        v-model="drawerOpen"
        :standing="selectedTeam"
        :is-completed="standingsData.is_completed"
        :season-year="standingsData.season_year ?? undefined"
        :trophy-name="trophyTitle"
        :display-rank="selectedTeam ? getTeamRank(selectedTeam) : undefined"
        :display-power-rank="selectedTeam ? getTeamPowerRank(selectedTeam) : undefined"
        :overall-rank="selectedTeam ? selectedTeam.rank : undefined"
        :overall-power-rank="selectedTeam ? selectedTeam.power_rank : undefined"
        :active-rank="selectedTeam && selectedTeam.is_active ? activeRankMap.get(selectedTeam.team_id) : undefined"
        :is-all-time="isAllTime"
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
