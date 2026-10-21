<script setup lang="ts">
import { computed } from 'vue';
import type { StandingEntry } from '@/types/api';
import SwipeDrawer from '@/components/ui/SwipeDrawer.vue';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';

const props = defineProps<{
  modelValue: boolean;
  standing: StandingEntry | null;
  isCompleted: boolean;
  seasonYear: number;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void;
}>();

const teamName = computed(() => props.standing?.team_name ?? 'Team Breakdown');
const managerSubtitle = computed(() => {
  if (!props.standing) return '';
  if (props.standing.co_manager_name) {
    return `${props.standing.manager_name} & ${props.standing.co_manager_name} · ${props.seasonYear}`;
  }
  return `${props.standing.manager_name} · ${props.seasonYear}`;
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
  return raw <= 1 ? raw * 100 : raw;
});

const benchLostPoints = computed(() => {
  if (!props.standing) return 0;
  return Math.max(0, props.standing.optimal_points_for - props.standing.points_for);
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
          <TeamAvatar :src="standing.logo_url" :name="standing.team_name" size="md" rounded="xl" />
          <div class="min-w-0">
            <h3 class="text-sm sm:text-base font-black text-slate-100 truncate">{{ standing.team_name }}</h3>
            <p class="text-xs text-slate-400 truncate">{{ managerSubtitle }}</p>
          </div>
        </div>

        <div class="flex items-center gap-2 shrink-0 font-mono">
          <div class="text-right">
            <div class="text-[10px] uppercase text-slate-500">Standings</div>
            <div class="text-sm font-black text-amber-400">#{{ standing.rank }}</div>
          </div>
          <div class="w-px h-6 bg-slate-800"></div>
          <div class="text-right">
            <div class="text-[10px] uppercase text-slate-500">Power Rank</div>
            <div
              class="text-sm font-black"
              :class="standing.power_rank === 1 ? 'text-amber-400' : 'text-slate-100'"
            >
              #{{ standing.power_rank }}
            </div>
          </div>
        </div>
      </div>

      <!-- Weekly Standings Progression Strip -->
      <div
        v-if="standing.weekly_history && standing.weekly_history.length > 0"
        class="rounded-xl p-3 bg-[#0b101b] border border-slate-800/90 space-y-2"
      >
        <div class="flex items-center justify-between">
          <span class="text-[10px] uppercase font-mono font-bold tracking-wider text-slate-400">
            Weekly Standings Log
          </span>
          <span class="text-[10px] font-mono text-slate-500">
            Rank & Weekly Score
          </span>
        </div>

        <div class="flex items-center gap-1.5 overflow-x-auto no-scrollbar pb-0.5">
          <div
            v-for="pt in standing.weekly_history"
            :key="pt.week"
            class="px-2 py-1.5 rounded-lg bg-slate-900/90 border border-slate-800/80 text-center shrink-0 min-w-[54px] font-mono"
          >
            <div class="text-[9px] text-slate-500 uppercase">W{{ pt.week }}</div>
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
            {{ officialWinPct.toFixed(1) }}% Win Rate
          </span>
        </div>

        <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <div class="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800/80">
            <span class="text-[10px] text-slate-500 uppercase font-mono">Record</span>
            <div class="text-base font-bold font-mono text-slate-100 tabular-nums">
              {{ officialRecordStr }}
            </div>
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
            <span class="text-[10px] text-slate-400 font-mono">{{ allPlayPct.toFixed(1) }}% win rate</span>
          </div>
        </div>
      </div>

      <!-- Section 3: Lineup Efficiency & Bankroll -->
      <div class="grid grid-cols-2 gap-2.5">
        <div class="rounded-xl p-3 bg-[#0b101b] border border-slate-800/90 space-y-1">
          <span class="text-[10px] uppercase font-mono font-bold text-slate-400">Lineup Efficiency</span>
          <div class="text-base font-bold font-mono text-slate-100 tabular-nums">
            {{ efficiencyPct.toFixed(1) }}%
          </div>
          <div class="text-[10px] font-mono text-slate-500">
            {{ benchLostPoints.toFixed(1) }} pts left on bench
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
