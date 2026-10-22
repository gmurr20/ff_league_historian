<script setup lang="ts">
import { computed } from 'vue';
import type { StandingEntry } from '@/types/api';
import SwipeDrawer from '@/components/ui/SwipeDrawer.vue';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';

const props = withDefaults(
  defineProps<{
    modelValue: boolean;
    standing: StandingEntry | null;
    isCompleted?: boolean;
    seasonYear?: number | null;
    trophyName?: string;
    displayRank?: number;
    displayPowerRank?: number;
    overallRank?: number;
    overallPowerRank?: number;
    activeRank?: number;
    isAllTime?: boolean;
  }>(),
  {
    isCompleted: false,
    seasonYear: undefined,
    trophyName: 'The Paulie',
    isAllTime: false,
  }
);

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void;
}>();

const seasonsCount = computed(() => props.standing?.weekly_history?.length || 1);

function formatSportsPct(pct: number): string {
  const formatted = pct.toFixed(3);
  return formatted.startsWith('0.') ? formatted.slice(1) : formatted;
}

const teamName = computed(() => props.standing?.team_name ?? 'Team Breakdown');
const managerSubtitle = computed(() => {
  if (!props.standing) return '';
  const yr = props.seasonYear ? ` · ${props.seasonYear}` : '';
  const co = props.standing.co_manager_name ? ` & ${props.standing.co_manager_name}` : '';
  const inactiveStr = !props.standing.is_active ? ' (Former)' : '';
  const seasonStr = props.isAllTime
    ? ` · ${seasonsCount.value} ${seasonsCount.value === 1 ? 'season' : 'seasons'}`
    : yr;
  return `${props.standing.manager_name}${co}${inactiveStr}${seasonStr}`;
});

const totalGames = computed(() => {
  if (!props.standing) return 0;
  return props.standing.wins + props.standing.losses + props.standing.ties;
});

const officialRecordStr = computed(() => {
  if (!props.standing) return '0-0';
  const { wins, losses, ties } = props.standing;
  return ties > 0 ? `${wins}-${losses}-${ties}` : `${wins}-${losses}`;
});

const officialWinPct = computed(() => {
  if (!props.standing || totalGames.value === 0) return 0;
  return ((props.standing.wins + 0.5 * props.standing.ties) / totalGames.value) * 100;
});

const pointDiff = computed(() => {
  if (!props.standing) return 0;
  return props.standing.points_for - props.standing.points_against;
});

const pointsPerGame = computed(() => {
  if (!props.standing || totalGames.value === 0) return 0;
  return props.standing.points_for / totalGames.value;
});

const allPlayPct = computed(() => {
  if (!props.standing) return 0;
  const raw = props.standing.all_play_win_pct;
  return Math.abs(raw) <= 1 ? raw * 100 : raw;
});

const luckPct = computed(() => {
  if (!props.standing) return 0;
  const raw = props.standing.luck_index;
  return Math.abs(raw) <= 1 ? raw * 100 : raw;
});

const efficiencyPct = computed(() => {
  if (!props.standing) return 0;
  const raw = props.standing.lineup_efficiency;
  if (!raw || raw <= 0) return 0;
  const pct = raw <= 1 ? raw * 100 : raw;
  return Math.min(100, Math.max(0, pct));
});

const benchLostPoints = computed(() => {
  if (!props.standing || !props.standing.optimal_points_for || !efficiencyPct.value) return 0;
  return Math.max(0, props.standing.optimal_points_for * (1 - efficiencyPct.value / 100));
});

const hasHardware = computed(() => {
  if (!props.standing) return false;
  return (
    props.standing.championships > 0 ||
    props.standing.runner_ups > 0 ||
    props.standing.third_places > 0 ||
    props.standing.scoring_champs > 0 ||
    props.standing.is_defending_champion
  );
});

const totalHonorsCount = computed(() => {
  if (!props.standing) return 0;
  return (
    props.standing.championships +
    props.standing.runner_ups +
    props.standing.third_places +
    props.standing.scoring_champs
  );
});
</script>

<template>
  <SwipeDrawer
    :model-value="modelValue"
    :title="teamName"
    :subtitle="managerSubtitle"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-if="standing" class="space-y-3.5 pb-4">
      <!-- Team & Rank Summary Banner -->
      <div class="rounded-xl p-3 bg-slate-900/90 border border-slate-800 flex items-center justify-between gap-3">
        <div class="flex items-center gap-3 min-w-0">
          <div class="relative shrink-0">
            <TeamAvatar :src="standing.logo_url" :name="standing.team_name" size="md" rounded="xl" />
            <!-- Defending Champion Mini Trophy Badge on Avatar -->
            <span
              v-if="standing.is_defending_champion"
              class="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-amber-500 text-slate-950 flex items-center justify-center text-[10px] shadow-md border border-slate-900"
              :title="`Defending ${props.trophyName} Champion`"
            >
              🏆
            </span>
          </div>
          <div class="min-w-0">
            <div class="flex items-center gap-1.5 flex-wrap">
              <h3 class="text-sm sm:text-base font-black text-slate-100 truncate">
                {{ standing.team_name }}
              </h3>
              <!-- Former / Inactive Franchise Badge -->
              <span
                v-if="!standing.is_active"
                class="inline-flex items-center text-[9px] font-mono font-bold uppercase px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700/80 shrink-0 select-none"
                title="Former Franchise Manager — No longer active in current season"
              >
                FORMER
              </span>
              <!-- World Cup style Championship Stars (1 star per title) -->
              <div
                v-if="standing.championships > 0"
                class="inline-flex items-center gap-0.5 shrink-0"
                :title="`${standing.championships}x Champion (${standing.championship_years.join(', ')})`"
              >
                <span
                  v-for="yr in standing.championship_years"
                  :key="yr"
                  class="text-amber-400 text-sm leading-none drop-shadow-[0_0_6px_rgba(251,191,36,0.7)] select-none"
                >
                  ★
                </span>
              </div>
            </div>
            <p class="text-xs text-slate-400 truncate">{{ managerSubtitle }}</p>
          </div>
        </div>

        <div class="flex items-center gap-2 shrink-0 font-mono">
          <div class="text-right">
            <div class="text-[10px] uppercase text-slate-500">Standings</div>
            <div class="text-sm font-black text-amber-400">#{{ props.displayRank ?? standing.rank }}</div>
            <div
              v-if="props.isAllTime && standing.is_active && props.overallRank && props.activeRank && props.overallRank !== props.activeRank"
              class="text-[9px] text-slate-400 font-medium"
            >
              {{ (props.displayRank ?? standing.rank) === props.activeRank ? `#${props.overallRank} Overall` : `#${props.activeRank} Active` }}
            </div>
          </div>
          <div class="w-px h-6 bg-slate-800"></div>
          <div class="text-right">
            <div class="text-[10px] uppercase text-slate-500">Power Rank</div>
            <div
              class="text-sm font-black"
              :class="(props.displayPowerRank ?? standing.power_rank) === 1 ? 'text-amber-400' : 'text-slate-100'"
            >
              #{{ props.displayPowerRank ?? standing.power_rank }}
            </div>
            <div
              v-if="props.isAllTime && standing.is_active && props.overallPowerRank && props.displayPowerRank && props.overallPowerRank !== props.displayPowerRank"
              class="text-[9px] text-slate-400 font-medium"
            >
              #{{ props.overallPowerRank }} Overall
            </div>
          </div>
        </div>
      </div>

      <!-- Trophy Room / Pedigree Card -->
      <div
        v-if="hasHardware"
        class="rounded-xl p-3 sm:p-3.5 bg-gradient-to-b from-[#161d2d] via-[#0e1422] to-[#0a0e18] border border-amber-500/35 space-y-3 shadow-md"
      >
        <!-- Card Header -->
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span class="text-base sm:text-lg">🏛️</span>
            <div>
              <span class="text-xs font-mono uppercase font-black tracking-wider text-amber-300">
                Trophy Room
              </span>
              <span class="hidden xs:inline text-[10px] text-slate-400 font-mono ml-2">
                Franchise Hardware & Honors
              </span>
            </div>
          </div>
          <!-- Total Hardware Count Pill -->
          <div
            v-if="totalHonorsCount > 0"
            class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/15 border border-amber-500/35 text-amber-300 text-[10px] font-mono font-bold"
          >
            <span>{{ totalHonorsCount }} {{ totalHonorsCount === 1 ? 'Honor' : 'Honors' }}</span>
          </div>
        </div>

        <!-- Defending Champion Highlight Banner (if applicable) -->
        <div
          v-if="standing.is_defending_champion"
          class="flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-gradient-to-r from-amber-500/25 via-amber-500/15 to-transparent border border-amber-500/50 text-amber-200 text-xs font-bold font-mono shadow-sm"
        >
          <div class="flex items-center gap-2">
            <span class="text-sm">🏆</span>
            <span>Reigning {{ props.trophyName }} Champion</span>
          </div>
          <span class="text-[9px] uppercase tracking-wider text-amber-400 font-black">Defending Title</span>
        </div>

        <!-- Accolades Shelf (Grid of Hardware Won) -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono">
          <!-- 1st Place / Championship Titles -->
          <div
            v-if="standing.championships > 0"
            class="rounded-lg p-2.5 bg-slate-900/90 border border-amber-500/35 space-y-1.5"
          >
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-1.5 text-amber-300 font-bold">
                <span class="text-sm">🏆</span>
                <span class="text-[11px] uppercase tracking-wider">1st Place · Champion</span>
              </div>
              <span class="text-[10px] text-amber-400 font-bold px-1.5 py-0.2 rounded bg-amber-500/20">
                {{ standing.championships }}x
              </span>
            </div>
            <div class="flex items-center gap-1 flex-wrap pt-0.5">
              <span
                v-for="yr in standing.championship_years"
                :key="yr"
                class="px-2 py-0.5 rounded bg-amber-500/15 border border-amber-500/40 text-amber-200 text-[10px] font-bold"
              >
                {{ yr }}
              </span>
            </div>
          </div>

          <!-- 2nd Place / Runner-Up Medals -->
          <div
            v-if="standing.runner_ups > 0"
            class="rounded-lg p-2.5 bg-slate-900/90 border border-slate-600/50 space-y-1.5"
          >
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-1.5 text-slate-200 font-bold">
                <span class="text-sm">🥈</span>
                <span class="text-[11px] uppercase tracking-wider">2nd Place · Runner-Up</span>
              </div>
              <span class="text-[10px] text-slate-300 font-bold px-1.5 py-0.2 rounded bg-slate-700/50">
                {{ standing.runner_ups }}x
              </span>
            </div>
            <div class="flex items-center gap-1 flex-wrap pt-0.5">
              <span
                v-for="yr in standing.runner_up_years"
                :key="yr"
                class="px-2 py-0.5 rounded bg-slate-800 border border-slate-600/60 text-slate-300 text-[10px] font-bold"
              >
                {{ yr }}
              </span>
            </div>
          </div>

          <!-- 3rd Place Medals -->
          <div
            v-if="standing.third_places > 0"
            class="rounded-lg p-2.5 bg-slate-900/90 border border-amber-800/50 space-y-1.5"
          >
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-1.5 text-amber-600 font-bold">
                <span class="text-sm">🥉</span>
                <span class="text-[11px] uppercase tracking-wider">3rd Place Podium</span>
              </div>
              <span class="text-[10px] text-amber-500 font-bold px-1.5 py-0.2 rounded bg-amber-900/30">
                {{ standing.third_places }}x
              </span>
            </div>
            <div class="flex items-center gap-1 flex-wrap pt-0.5">
              <span
                v-for="yr in standing.third_place_years"
                :key="yr"
                class="px-2 py-0.5 rounded bg-slate-900 border border-amber-700/40 text-amber-500 text-[10px] font-bold"
              >
                {{ yr }}
              </span>
            </div>
          </div>

          <!-- Lamar Jackson Regular Season Champ Award -->
          <div
            v-if="standing.scoring_champs > 0"
            class="rounded-lg p-2.5 bg-gradient-to-r from-purple-950/40 via-purple-900/20 to-slate-900/90 border border-purple-500/40 space-y-1.5 shadow-sm"
          >
            <div class="flex items-center justify-between gap-1.5">
              <div class="flex items-center gap-2 min-w-0">
                <!-- Lamar Jackson Headshot: King of the Regular Season -->
                <div class="relative shrink-0">
                  <div class="w-6 h-6 sm:w-7 sm:h-7 rounded-full overflow-hidden border border-purple-400/60 bg-purple-950 shadow-sm flex items-center justify-center">
                    <img
                      src="https://a.espncdn.com/i/headshots/nfl/players/full/3916387.png"
                      alt="Lamar Jackson - King of the Regular Season"
                      class="w-full h-full object-cover object-top scale-110"
                      loading="lazy"
                    />
                  </div>
                  <span
                    class="absolute -bottom-1 -right-1 text-[8px] leading-none"
                    title="King of the Regular Season"
                  >
                    👑
                  </span>
                </div>
                <div class="min-w-0">
                  <div class="text-[11px] font-black uppercase tracking-wider text-purple-200 truncate leading-tight">
                    The Lamar Jackson Award
                  </div>
                  <div class="text-[9px] text-purple-300/70 font-mono truncate leading-none mt-0.5">
                    Regular Season Champ (Most PF)
                  </div>
                </div>
              </div>
              <span class="text-[10px] text-purple-200 font-bold px-1.5 py-0.5 rounded bg-purple-500/25 border border-purple-500/40 shrink-0">
                {{ standing.scoring_champs }}x
              </span>
            </div>
            <div class="flex items-center gap-1 flex-wrap pt-0.5">
              <span
                v-for="yr in standing.scoring_champ_years"
                :key="yr"
                class="px-2 py-0.5 rounded bg-purple-900/40 border border-purple-500/40 text-purple-200 text-[10px] font-bold"
              >
                {{ yr }}
              </span>
            </div>
          </div>
        </div>
      </div>
      <div
        v-else
        class="rounded-xl px-3.5 py-3 bg-slate-900/50 border border-slate-800/80 flex items-center justify-between text-xs font-mono"
      >
        <div class="flex items-center gap-2 text-slate-400">
          <span class="text-base">🏆</span>
          <div>
            <div class="text-[10px] uppercase font-bold text-slate-300 tracking-wider">Race for {{ props.trophyName }}</div>
            <div class="text-[9.5px] text-slate-500">Trophy room awaiting its first hardware</div>
          </div>
        </div>
        <span class="text-[10px] text-amber-400/80 font-bold px-2 py-0.5 rounded bg-amber-500/10 border border-amber-500/20 shrink-0">
          Chasing Title #1
        </span>
      </div>

      <!-- Weekly Standings Progression Strip -->
      <div
        v-if="standing.weekly_history && standing.weekly_history.length > 0"
        class="rounded-xl p-3 bg-[#0b101b] border border-slate-800/90 space-y-2"
      >
        <div class="flex items-center justify-between">
          <span class="text-[10px] uppercase font-mono font-bold tracking-wider text-slate-400">
            {{ props.isAllTime ? 'Seasonal History Log' : 'Weekly Standings Log' }}
          </span>
          <span class="text-[10px] font-mono text-slate-500">
            {{ props.isAllTime ? 'Final Rank & Avg Score' : 'Rank & Weekly Score' }}
          </span>
        </div>

        <div class="flex items-center gap-1.5 overflow-x-auto no-scrollbar pb-0.5">
          <div
            v-for="pt in standing.weekly_history"
            :key="pt.week"
            class="px-2 py-1.5 rounded-lg bg-slate-900/90 border border-slate-800/80 text-center shrink-0 min-w-[54px] font-mono"
          >
            <div class="text-[9px] text-slate-500 uppercase">
              {{ props.isAllTime ? pt.week : `W${pt.week}` }}
            </div>
            <div
              class="text-xs font-black mt-0.5"
              :class="pt.standings_rank === 1 ? 'text-amber-400' : pt.standings_rank <= 4 ? 'text-emerald-400' : 'text-slate-200'"
            >
              #{{ pt.standings_rank }}
            </div>
            <div class="text-[9px] text-slate-400 tabular-nums mt-0.5">
              {{ pt.weekly_score.toFixed(1) }}
            </div>
          </div>
        </div>
      </div>

      <!-- Section 1: Record & Scoring Summary -->
      <div class="rounded-xl p-3.5 bg-[#0b101b] border border-slate-800/90 space-y-2.5">
        <div class="flex items-center justify-between">
          <h4 class="text-[10px] uppercase font-mono font-bold tracking-wider text-slate-400">
            Official Record & Scoring
          </h4>
          <span class="text-[11px] font-mono text-slate-400">
            {{ props.isAllTime ? `${formatSportsPct(officialWinPct / 100)} Win Pct` : `${officialWinPct.toFixed(1)}% Win Rate` }}
          </span>
        </div>

        <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <div class="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800/80">
            <span class="text-[10px] text-slate-500 uppercase font-mono">Record</span>
            <div class="text-base font-bold font-mono text-slate-100 tabular-nums">
              {{ officialRecordStr }}
            </div>
            <span v-if="props.isAllTime" class="text-[10px] text-slate-400 font-mono">
              {{ seasonsCount }} {{ seasonsCount === 1 ? 'season' : 'seasons' }}
            </span>
          </div>

          <div class="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800/80">
            <span class="text-[10px] text-slate-500 uppercase font-mono">Points For</span>
            <div class="text-base font-bold font-mono text-slate-100 tabular-nums">
              {{ standing.points_for.toFixed(1) }}
            </div>
            <span class="text-[10px] text-slate-500 font-mono">{{ pointsPerGame.toFixed(1) }}/wk</span>
          </div>

          <div class="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800/80">
            <span class="text-[10px] text-slate-500 uppercase font-mono">Points Against</span>
            <div class="text-base font-bold font-mono text-slate-300 tabular-nums">
              {{ standing.points_against.toFixed(1) }}
            </div>
          </div>

          <div class="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800/80">
            <span class="text-[10px] text-slate-500 uppercase font-mono">Differential</span>
            <div
              class="text-base font-bold font-mono tabular-nums"
              :class="pointDiff >= 0 ? 'text-emerald-400' : 'text-rose-400'"
            >
              {{ pointDiff >= 0 ? `+${pointDiff.toFixed(1)}` : pointDiff.toFixed(1) }}
            </div>
          </div>
        </div>
      </div>

      <!-- Section 2: Power Rankings: Median & All-22 -->
      <div class="rounded-xl p-3.5 bg-[#0b101b] border border-slate-800/90 space-y-2.5">
        <div class="flex items-center justify-between">
          <h4 class="text-[10px] uppercase font-mono font-bold tracking-wider text-slate-400">
            Power Rankings: Median & All-22
          </h4>
          <span
            class="text-[11px] font-mono font-bold"
            :class="
              standing.luck_index > 0.05
                ? 'text-emerald-400'
                : standing.luck_index < -0.05
                ? 'text-rose-400'
                : 'text-slate-400'
            "
          >
            {{ standing.luck_index > 0 ? '+' : '' }}{{ luckPct.toFixed(1) }}% Luck
          </span>
        </div>

        <div class="grid grid-cols-2 gap-2">
          <div class="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800/80">
            <span class="text-[10px] text-slate-500 uppercase font-mono">Vs Weekly Median</span>
            <div class="text-base font-bold font-mono text-slate-100 tabular-nums">
              {{ standing.median_wins }}-{{ standing.median_losses }}
              <span v-if="standing.median_ties > 0">-{{ standing.median_ties }}</span>
            </div>
            <span class="text-[10px] text-slate-400 font-mono">Top-half consistency</span>
          </div>

          <div class="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800/80">
            <span class="text-[10px] text-slate-500 uppercase font-mono">All-22 Record</span>
            <div class="text-base font-bold font-mono text-slate-100 tabular-nums">
              {{ standing.all_play_wins }}-{{ standing.all_play_losses }}
              <span v-if="standing.all_play_ties > 0">-{{ standing.all_play_ties }}</span>
            </div>
            <span class="text-[10px] text-slate-400 font-mono">{{ props.isAllTime ? `${formatSportsPct(allPlayPct / 100)} win pct` : `${allPlayPct.toFixed(1)}% win rate` }}</span>
          </div>
        </div>
      </div>

      <!-- Section 3: Lineup Efficiency & Bankroll -->
      <div class="grid grid-cols-2 gap-2.5">
        <div class="rounded-xl p-3 bg-[#0b101b] border border-slate-800/90 space-y-1">
          <span class="text-[10px] uppercase font-mono font-bold text-slate-400">Lineup Efficiency</span>
          <div class="text-base font-bold font-mono text-slate-100 tabular-nums">
            <template v-if="efficiencyPct > 0">
              {{ efficiencyPct.toFixed(1) }}%
            </template>
            <template v-else>
              <span class="text-slate-500 font-medium text-xs sm:text-sm select-none">No Data</span>
            </template>
          </div>
          <div class="text-[10px] font-mono text-slate-500">
            <template v-if="efficiencyPct > 0">
              {{ benchLostPoints.toFixed(1) }} pts left on bench
            </template>
            <template v-else>
              No start/sit tracking
            </template>
          </div>
        </div>

        <div class="rounded-xl p-3 bg-[#0b101b] border border-slate-800/90 space-y-1">
          <span class="text-[10px] uppercase font-mono font-bold text-slate-400">Cash & FAAB</span>
          <div class="text-base font-bold font-mono text-emerald-400 tabular-nums">
            ${{ standing.total_earnings.toFixed(0) }}
            <span class="text-xs text-slate-400 font-normal">won</span>
          </div>
          <div class="text-[10px] font-mono text-slate-500">
            ${{ standing.faab_remaining }} FAAB remaining
          </div>
        </div>
      </div>
    </div>
  </SwipeDrawer>
</template>
