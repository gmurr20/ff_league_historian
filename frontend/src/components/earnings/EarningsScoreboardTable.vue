<script setup lang="ts">
import { ref, computed } from 'vue';
import type { EarningsLeaderboardEntry } from '@/types/api';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import { ArrowUpDown } from 'lucide-vue-next';

const props = withDefaults(
  defineProps<{
    leaderboard: EarningsLeaderboardEntry[];
    isSingleSeason: boolean;
    seasonYear: number | null;
    inactiveFilter?: 'active' | 'all';
  }>(),
  {
    inactiveFilter: 'active',
  }
);

const emit = defineEmits<{
  (e: 'open-manager', entry: EarningsLeaderboardEntry): void;
}>();

const isAllTime = computed<boolean>(() => !props.isSingleSeason);

// Sort Column state
type SortColumn = 'rank' | 'cash' | 'wins' | 'bonus' | 'podium' | 'seasons';
const sortCol = ref<SortColumn>('cash');
const sortAsc = ref<boolean>(false);

function toggleSort(col: SortColumn) {
  if (sortCol.value === col) {
    sortAsc.value = !sortAsc.value;
  } else {
    sortCol.value = col;
    // Rank defaults ascending (1..12); financial columns default descending (high..low)
    sortAsc.value = col === 'rank';
  }
}

const activeEntries = computed<EarningsLeaderboardEntry[]>(() => {
  return props.leaderboard.filter((e) => e.is_active);
});

const inactiveEntries = computed<EarningsLeaderboardEntry[]>(() => {
  return props.leaderboard.filter((e) => !e.is_active);
});

// Maps each active manager to their official rank among active members (1..12) based on default career bankroll
const activeRankMap = computed<Map<number, number>>(() => {
  const map = new Map<number, number>();
  activeEntries.value.forEach((e, idx) => {
    map.set(e.manager_id, idx + 1);
  });
  return map;
});

// Contextual rank: in 'active' mode returns 1..12, in 'all' mode returns overall rank (1..19)
function getManagerRank(e: EarningsLeaderboardEntry): number {
  if (isAllTime.value && props.inactiveFilter === 'active') {
    return activeRankMap.value.get(e.manager_id) ?? e.rank;
  }
  return e.rank;
}

function sortList(list: EarningsLeaderboardEntry[]): EarningsLeaderboardEntry[] {
  const dir = sortAsc.value ? 1 : -1;

  return [...list].sort((a, b) => {
    switch (sortCol.value) {
      case 'rank': {
        const aRank = getManagerRank(a);
        const bRank = getManagerRank(b);
        return (aRank - bRank) * dir;
      }
      case 'cash':
        return (a.total_earnings - b.total_earnings) * dir;
      case 'wins':
        return (
          (a.weekly_wins_cash - b.weekly_wins_cash ||
            a.weekly_wins_count - b.weekly_wins_count) * dir
        );
      case 'bonus':
        return (
          (a.weekly_bonus_cash - b.weekly_bonus_cash ||
            a.weekly_high_scores_count + a.weekly_high_score_losses_count -
              (b.weekly_high_scores_count + b.weekly_high_score_losses_count)) * dir
        );
      case 'podium':
        return (
          (a.championships - b.championships ||
            a.runner_ups - b.runner_ups ||
            a.third_places - b.third_places ||
            a.podium_earnings - b.podium_earnings) * dir
        );
      case 'seasons':
        return (a.seasons_played - b.seasons_played) * dir;
      default:
        return (a.total_earnings - b.total_earnings) * dir;
    }
  });
}

// Active / Primary group (single season = all managers, all-time = active managers)
const sortedActiveEntries = computed<EarningsLeaderboardEntry[]>(() => {
  if (props.isSingleSeason) {
    return sortList(props.leaderboard);
  }
  return sortList(activeEntries.value);
});

// Inactive group (shown later in all-time mode when inactiveFilter === 'all')
const sortedInactiveEntries = computed<EarningsLeaderboardEntry[]>(() => {
  if (props.isSingleSeason || props.inactiveFilter !== 'all') {
    return [];
  }
  return sortList(inactiveEntries.value);
});

export type EarningsDisplayRow =
  | { type: 'manager'; entry: EarningsLeaderboardEntry; isInactiveGroup: boolean; activeIndex: number }
  | { type: 'inactive-header'; count: number };

const displayRows = computed<EarningsDisplayRow[]>(() => {
  const rows: EarningsDisplayRow[] = [];
  sortedActiveEntries.value.forEach((e, idx) => {
    rows.push({ type: 'manager', entry: e, isInactiveGroup: false, activeIndex: idx });
  });

  if (isAllTime.value && props.inactiveFilter === 'all' && sortedInactiveEntries.value.length > 0) {
    rows.push({ type: 'inactive-header', count: sortedInactiveEntries.value.length });
    sortedInactiveEntries.value.forEach((e) => {
      rows.push({ type: 'manager', entry: e, isInactiveGroup: true, activeIndex: -1 });
    });
  }

  return rows;
});

const displayedFranchisesCount = computed<number>(() => {
  if (props.isSingleSeason) return props.leaderboard.length;
  return props.inactiveFilter === 'all' ? props.leaderboard.length : activeEntries.value.length;
});
</script>

<template>
  <div class="rounded-xl border border-slate-800/90 bg-[#0b101b] overflow-hidden shadow-lg">
    <!-- Scoreboard Table Title & Controls Bar -->
    <div class="flex items-center justify-between px-3.5 py-2.5 bg-slate-900/95 border-b border-slate-800/90">
      <div class="flex items-baseline gap-2 min-w-0">
        <h3 class="text-xs sm:text-sm font-black uppercase tracking-tight text-slate-100 truncate">
          {{ isSingleSeason ? 'Earnings Standings' : 'All-Time Bankroll' }}
        </h3>
        <span class="text-[11px] font-mono text-slate-500 uppercase tracking-wider truncate">
          ({{ displayedFranchisesCount }} Franchises)
        </span>
      </div>

      <div class="flex items-center gap-1 text-[11px] font-mono text-slate-400">
        <ArrowUpDown class="w-3 h-3 text-slate-500" />
        <span class="hidden sm:inline">Tap header to sort</span>
      </div>
    </div>

    <!-- COLUMN HEADERS: SINGLE SEASON MODE -->
    <div
      v-if="isSingleSeason"
      class="grid grid-cols-[20px_1fr_46px_44px_52px] sm:grid-cols-[28px_1fr_56px_64px_68px_68px_72px] items-center px-2.5 sm:px-3.5 py-2 bg-slate-900/90 border-b border-slate-800/90 text-[10px] font-mono uppercase tracking-tight sm:tracking-wider text-slate-400 select-none"
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
        :class="sortCol === 'wins' ? 'text-amber-400' : ''"
        @click="toggleSort('wins')"
        title="Weekly Matchup Wins Cash"
      >
        Wins
      </button>
      <button
        type="button"
        class="text-right font-bold hover:text-slate-200 transition-colors"
        :class="sortCol === 'bonus' ? 'text-amber-400' : ''"
        @click="toggleSort('bonus')"
        title="Weekly Bounties: High Score ($10) & High Loser ($10)"
      >
        Bonus
      </button>
      <button
        type="button"
        class="hidden sm:block text-right font-bold hover:text-slate-200 transition-colors"
        :class="sortCol === 'podium' ? 'text-amber-400' : ''"
        @click="toggleSort('podium')"
        title="Playoff Podium & Placement Cash"
      >
        Podium
      </button>
      <button
        type="button"
        class="text-right font-bold hover:text-slate-200 transition-colors"
        :class="sortCol === 'cash' ? 'text-emerald-400' : ''"
        @click="toggleSort('cash')"
      >
        Total
      </button>
    </div>

    <!-- COLUMN HEADERS: ALL-TIME CAREER MODE -->
    <div
      v-else
      class="grid grid-cols-[20px_1fr_44px_56px_60px] sm:grid-cols-[28px_1fr_56px_64px_68px_72px_76px] items-center px-2.5 sm:px-3.5 py-2 bg-slate-900/90 border-b border-slate-800/90 text-[10px] font-mono uppercase tracking-tight sm:tracking-wider text-slate-400 select-none"
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
        :class="sortCol === 'wins' ? 'text-amber-400' : ''"
        @click="toggleSort('wins')"
        title="Career Matchup Wins"
      >
        Wins
      </button>
      <button
        type="button"
        class="hidden sm:block text-right font-bold hover:text-slate-200 transition-colors"
        :class="sortCol === 'bonus' ? 'text-amber-400' : ''"
        @click="toggleSort('bonus')"
        title="Career High Score & Loser Bounties"
      >
        Bonus
      </button>
      <button
        type="button"
        class="hidden sm:block text-right font-bold hover:text-slate-200 transition-colors"
        :class="sortCol === 'podium' ? 'text-amber-400' : ''"
        @click="toggleSort('podium')"
        title="Career Podium Cash"
      >
        Podium
      </button>
      <button
        type="button"
        class="text-right font-bold hover:text-slate-200 transition-colors"
        :class="sortCol === 'podium' ? 'text-amber-400' : ''"
        @click="toggleSort('podium')"
        title="Championships"
      >
        Titles
      </button>
      <button
        type="button"
        class="text-right font-bold hover:text-slate-200 transition-colors"
        :class="sortCol === 'cash' ? 'text-emerald-400' : ''"
        @click="toggleSort('cash')"
      >
        Bankroll
      </button>
    </div>

    <!-- ROWS LIST -->
    <div class="divide-y divide-slate-800/60">
      <template v-for="row in displayRows" :key="row.type === 'inactive-header' ? 'inactive-header' : row.entry.manager_id">
        <!-- Former / Inactive Franchises Divider Header (Shown in all-time mode when toggle is 'all') -->
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

        <!-- Manager Row Item -->
        <div
          v-else
          role="button"
          tabindex="0"
          class="relative transition-colors cursor-pointer select-none active:bg-slate-800/70 hover:bg-slate-900/70"
          :class="row.isInactiveGroup ? 'opacity-65 hover:opacity-100 bg-slate-950/40' : ''"
          @click="emit('open-manager', row.entry)"
          @keydown.enter="emit('open-manager', row.entry)"
        >
          <!-- Left Edge Rank Status Accent Bar (Amber for #1, Emerald for top 3/earners) -->
          <span
            class="absolute left-0 inset-y-0 w-[3px]"
            :class="
              row.isInactiveGroup
                ? 'bg-transparent'
                : getManagerRank(row.entry) === 1
                ? 'bg-amber-400'
                : getManagerRank(row.entry) <= 3
                ? 'bg-emerald-500/80'
                : row.entry.total_earnings > 0
                ? 'bg-emerald-600/40'
                : 'bg-transparent'
            "
          ></span>

          <!-- ROW: SINGLE SEASON MODE -->
          <div
            v-if="isSingleSeason"
            class="grid grid-cols-[20px_1fr_46px_44px_52px] sm:grid-cols-[28px_1fr_56px_64px_68px_68px_72px] items-center px-2.5 sm:px-3.5 py-2.5"
          >
            <!-- Rank -->
            <div
              class="font-mono text-xs font-black tabular-nums"
              :class="
                row.activeIndex === 0
                  ? 'text-amber-400'
                  : row.activeIndex < 3
                  ? 'text-slate-200'
                  : 'text-slate-500'
              "
            >
              {{ row.activeIndex + 1 }}
            </div>

            <!-- Franchise Cell -->
            <div class="flex items-center gap-2 min-w-0 pr-1">
              <TeamAvatar :src="row.entry.avatar_url" :name="row.entry.team_name" size="xs" rounded="lg" />
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-1.5 min-w-0">
                  <span class="text-[13px] sm:text-sm font-bold text-slate-100 truncate leading-tight">
                    {{ row.entry.team_name }}
                  </span>
                  <!-- Championship Stars (Soccer / World Cup style: 1 star per title) -->
                  <div
                    v-if="row.entry.championships > 0"
                    class="inline-flex items-center gap-0.5 shrink-0"
                    :title="`${row.entry.championships}x Champion${row.entry.championship_years && row.entry.championship_years.length ? ` (${row.entry.championship_years.join(', ')})` : ''}`"
                  >
                    <span
                      v-for="yr in (row.entry.championship_years && row.entry.championship_years.length ? row.entry.championship_years : row.entry.championships)"
                      :key="yr"
                      class="text-amber-400 text-xs sm:text-sm leading-none drop-shadow-[0_0_5px_rgba(251,191,36,0.6)] select-none"
                    >
                      ★
                    </span>
                  </div>
                  <!-- Special Symbol / Indicator for Previous Champion (Defending Champion) -->
                  <span
                    v-if="row.entry.is_defending_champion"
                    class="inline-flex items-center gap-1 text-[9px] font-mono font-black uppercase px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/35 shrink-0 shadow-sm"
                    title="Defending Champion"
                  >
                    <span class="text-[10px]">🏆</span>
                    <span class="hidden xs:inline">DEFENDING</span> CHAMP
                  </span>
                  <span
                    v-if="row.entry.points_title_cash > 0"
                    class="inline-flex items-center gap-0.5 text-[9px] font-mono font-black uppercase px-1.5 py-0.2 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30 shrink-0"
                    title="The Lamar Jackson Award · Regular Season Scoring King"
                  >
                    👑 REG KING
                  </span>
                </div>
                <div class="text-[10px] text-slate-400 leading-tight mt-0.5 truncate">
                  {{ row.entry.display_name }}
                </div>
              </div>
            </div>

            <!-- Weekly Wins Cash -->
            <div class="text-right font-mono tabular-nums">
              <div class="text-xs sm:text-sm font-bold text-slate-200">
                ${{ row.entry.weekly_wins_cash.toFixed(0) }}
              </div>
              <div class="text-[9px] text-slate-500">
                {{ row.entry.weekly_wins_count }}W
              </div>
            </div>

            <!-- Bonus Cash -->
            <div class="text-right font-mono tabular-nums">
              <span
                class="text-xs sm:text-sm font-bold"
                :class="row.entry.weekly_bonus_cash > 0 ? 'text-amber-400' : 'text-slate-600'"
              >
                ${{ row.entry.weekly_bonus_cash.toFixed(0) }}
              </span>
            </div>

            <!-- Podium Cash (Hidden on mobile) -->
            <div class="hidden sm:block text-right font-mono tabular-nums">
              <span
                class="text-xs sm:text-sm font-bold"
                :class="row.entry.podium_earnings > 0 ? 'text-amber-400' : 'text-slate-600'"
              >
                ${{ row.entry.podium_earnings.toFixed(0) }}
              </span>
            </div>

            <!-- Total Season Cash (Prominent Emerald) -->
            <div class="text-right font-mono tabular-nums">
              <span
                class="text-xs sm:text-sm font-black"
                :class="row.entry.total_earnings > 0 ? 'text-emerald-400' : 'text-slate-600'"
              >
                ${{ row.entry.total_earnings.toFixed(0) }}
              </span>
            </div>
          </div>

          <!-- ROW: ALL-TIME CAREER MODE -->
          <div
            v-else
            class="grid grid-cols-[20px_1fr_44px_56px_60px] sm:grid-cols-[28px_1fr_56px_64px_68px_72px_76px] items-center px-2.5 sm:px-3.5 py-2.5"
          >
            <!-- Rank -->
            <div
              class="font-mono text-xs font-black tabular-nums"
              :class="
                getManagerRank(row.entry) === 1 && !row.isInactiveGroup
                  ? 'text-amber-400'
                  : getManagerRank(row.entry) <= 3 && !row.isInactiveGroup
                  ? 'text-slate-200'
                  : 'text-slate-500'
              "
            >
              {{ getManagerRank(row.entry) }}
            </div>

            <!-- Franchise Cell -->
            <div class="flex items-center gap-2 min-w-0 pr-1">
              <TeamAvatar :src="row.entry.avatar_url" :name="row.entry.team_name" size="xs" rounded="lg" />
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-1.5 min-w-0">
                  <span class="text-[13px] sm:text-sm font-bold text-slate-100 truncate leading-tight">
                    {{ row.entry.team_name || row.entry.display_name }}
                  </span>
                  <!-- Former / Inactive Franchise Badge -->
                  <span
                    v-if="!row.entry.is_active"
                    class="inline-flex items-center text-[8.5px] font-mono font-bold uppercase px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 border border-slate-700/80 shrink-0 select-none"
                    title="Former Franchise Manager — No longer active in current season"
                  >
                    INACTIVE
                  </span>
                  <!-- Championship Stars (Soccer / World Cup style: 1 star per title) -->
                  <div
                    v-if="row.entry.championships > 0"
                    class="inline-flex items-center gap-0.5 shrink-0"
                    :title="`${row.entry.championships}x Champion${row.entry.championship_years && row.entry.championship_years.length ? ` (${row.entry.championship_years.join(', ')})` : ''}`"
                  >
                    <span
                      v-for="yr in (row.entry.championship_years && row.entry.championship_years.length ? row.entry.championship_years : row.entry.championships)"
                      :key="yr"
                      class="text-amber-400 text-xs sm:text-sm leading-none drop-shadow-[0_0_5px_rgba(251,191,36,0.6)] select-none"
                    >
                      ★
                    </span>
                  </div>
                  <!-- Special Symbol / Indicator for Previous Champion (Defending Champion) -->
                  <span
                    v-if="row.entry.is_defending_champion"
                    class="inline-flex items-center gap-1 text-[9px] font-mono font-black uppercase px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/35 shrink-0 shadow-sm"
                    title="Defending Champion"
                  >
                    <span class="text-[10px]">🏆</span>
                    <span class="hidden xs:inline">DEFENDING</span> CHAMP
                  </span>
                </div>
                <div class="flex items-center gap-1.5 text-[10px] text-slate-400 leading-tight mt-0.5 min-w-0">
                  <span v-if="row.entry.team_name && row.entry.team_name !== row.entry.display_name" class="truncate">{{ row.entry.display_name }}</span>
                  <span v-if="row.entry.team_name && row.entry.team_name !== row.entry.display_name" class="text-slate-600 shrink-0">·</span>
                  <span
                    class="text-[9.5px] font-mono text-slate-400 shrink-0 select-none"
                    :title="`${row.entry.seasons_played} ${row.entry.seasons_played === 1 ? 'season' : 'seasons'} in league history`"
                  >
                    {{ row.entry.seasons_played }} {{ row.entry.seasons_played === 1 ? 'season' : 'seasons' }}
                  </span>
                  <template v-if="inactiveFilter === 'all' && row.entry.is_active && activeRankMap.get(row.entry.manager_id)">
                    <span class="text-slate-600 shrink-0">·</span>
                    <span class="font-mono text-[9.5px] text-emerald-400/90 font-medium shrink-0">#{{ activeRankMap.get(row.entry.manager_id) }} Active</span>
                  </template>
                </div>
              </div>
            </div>

            <!-- Total Career Wins -->
            <div class="text-right font-mono tabular-nums">
              <div class="text-xs sm:text-sm font-bold text-slate-200">
                {{ row.entry.weekly_wins_count }}W
              </div>
              <div class="text-[9px] text-slate-500">
                ${{ row.entry.weekly_wins_cash.toFixed(0) }}
              </div>
            </div>

            <!-- Career Nuanced Bonus (Hidden on mobile) -->
            <div class="hidden sm:block text-right font-mono tabular-nums">
              <span
                class="text-xs sm:text-sm font-bold"
                :class="row.entry.weekly_bonus_cash > 0 ? 'text-amber-400' : 'text-slate-600'"
              >
                ${{ row.entry.weekly_bonus_cash.toFixed(0) }}
              </span>
            </div>

            <!-- Career Podium Cash (Hidden on mobile) -->
            <div class="hidden sm:block text-right font-mono tabular-nums">
              <span
                class="text-xs sm:text-sm font-bold"
                :class="row.entry.podium_earnings > 0 ? 'text-amber-400' : 'text-slate-600'"
              >
                ${{ row.entry.podium_earnings.toFixed(0) }}
              </span>
            </div>

            <!-- Trophy Case (1st, 2nd, 3rd Titles & Podiums) -->
            <div class="text-right font-mono tabular-nums flex items-center justify-end gap-1 text-[11px] sm:text-xs">
              <span
                v-if="row.entry.championships > 0"
                class="font-bold text-amber-400 select-none whitespace-nowrap"
                :title="`${row.entry.championships}x Champion (1st Place)`"
              >
                🏆{{ row.entry.championships }}
              </span>
              <span
                v-if="row.entry.runner_ups > 0"
                class="font-medium text-slate-300 select-none whitespace-nowrap"
                :title="`${row.entry.runner_ups}x Runner-Up (2nd Place)`"
              >
                🥈{{ row.entry.runner_ups }}
              </span>
              <span
                v-if="row.entry.third_places > 0"
                class="font-medium text-amber-600 select-none whitespace-nowrap"
                :title="`${row.entry.third_places}x 3rd Place`"
              >
                🥉{{ row.entry.third_places }}
              </span>
              <span
                v-if="row.entry.championships === 0 && row.entry.runner_ups === 0 && row.entry.third_places === 0"
                class="text-slate-600 select-none"
              >
                —
              </span>
            </div>

            <!-- Career Total Bankroll (Prominent Emerald) -->
            <div class="text-right font-mono tabular-nums">
              <span
                class="text-xs sm:text-sm font-black"
                :class="row.entry.total_earnings > 0 ? 'text-emerald-400' : 'text-slate-600'"
              >
                ${{ row.entry.total_earnings.toFixed(0) }}
              </span>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
