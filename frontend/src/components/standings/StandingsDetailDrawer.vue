<script setup lang="ts">
import { computed } from 'vue';
import type { StandingEntry } from '@/types/api';
import SwipeDrawer from '@/components/ui/SwipeDrawer.vue';
import {
  Sparkles,
  ShieldAlert,
  Percent,
  DollarSign,
  TrendingUp,
  Activity,
} from 'lucide-vue-next';

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
  return `${props.standing.manager_name} · Season ${props.seasonYear}`;
});

// Official Record & Games
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

// All-Play & Luck
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

// Lineup efficiency
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
    <div v-if="standing" class="space-y-4 pb-4">
      <!-- Section 1: Record & Scoring Summary -->
      <div class="stadium-card rounded-2xl p-4 border border-slate-800 space-y-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <Activity class="w-4 h-4 text-emerald-400" />
            <h4 class="text-xs uppercase font-bold tracking-wider text-slate-300">
              Official Record & Scoring
            </h4>
          </div>

          <span
            v-if="standing.final_standing"
            class="text-[11px] font-mono px-2 py-0.5 rounded font-bold"
            :class="
              standing.final_standing === 1
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                : 'bg-slate-800 text-slate-300'
            "
          >
            {{ standing.final_standing === 1 ? '🏆 Champion' : `#${standing.final_standing} Final` }}
          </span>
          <span
            v-else-if="standing.playoff_seed"
            class="text-[11px] font-mono px-2 py-0.5 rounded font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-800/60"
          >
            Seed #{{ standing.playoff_seed }}
          </span>
        </div>

        <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
          <div class="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800/80">
            <span class="text-[10px] text-slate-400 uppercase font-semibold">Official Record</span>
            <div class="text-base font-bold font-mono text-slate-100 tabular-nums">
              {{ officialRecordStr }}
            </div>
            <span class="text-[10px] text-slate-500 font-mono">{{ officialWinPct.toFixed(1) }}% W-L</span>
          </div>

          <div class="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800/80">
            <span class="text-[10px] text-slate-400 uppercase font-semibold">Points For (PF)</span>
            <div class="text-base font-bold font-mono text-emerald-400 tabular-nums">
              {{ standing.points_for.toFixed(1) }}
            </div>
            <span class="text-[10px] text-slate-500 font-mono">{{ pointsPerGame.toFixed(1) }} PPG</span>
          </div>

          <div class="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800/80">
            <span class="text-[10px] text-slate-400 uppercase font-semibold">Points Against (PA)</span>
            <div class="text-base font-bold font-mono text-rose-400 tabular-nums">
              {{ standing.points_against.toFixed(1) }}
            </div>
            <span class="text-[10px] text-slate-500 font-mono">Opp PPG</span>
          </div>

          <div class="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800/80">
            <span class="text-[10px] text-slate-400 uppercase font-semibold">Point Differential</span>
            <div
              class="text-base font-bold font-mono tabular-nums"
              :class="pointDiff >= 0 ? 'text-emerald-400' : 'text-rose-400'"
            >
              {{ pointDiff >= 0 ? `+${pointDiff.toFixed(1)}` : pointDiff.toFixed(1) }}
            </div>
            <span class="text-[10px] text-slate-500 font-mono">Net Margins</span>
          </div>
        </div>
      </div>

      <!-- Section 2: All-Play & Schedule Luck Deep-Dive -->
      <div class="stadium-card rounded-2xl p-4 border border-slate-800 space-y-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <TrendingUp class="w-4 h-4 text-emerald-400" />
            <h4 class="text-xs uppercase font-bold tracking-wider text-slate-300">
              All-Play & Schedule Luck
            </h4>
          </div>

          <span
            class="text-[11px] font-mono px-2 py-0.5 rounded font-bold border"
            :class="
              standing.luck_index > 0.05
                ? 'bg-emerald-950/80 text-emerald-400 border-emerald-800/80'
                : standing.luck_index < -0.05
                ? 'bg-rose-950/80 text-rose-400 border-rose-800/80'
                : 'bg-slate-800 text-slate-400 border-slate-700'
            "
          >
            {{ standing.luck_index > 0 ? '+' : '' }}{{ luckPct.toFixed(1) }}% Luck Index
          </span>
        </div>

        <div class="grid grid-cols-2 gap-2">
          <div class="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800/80">
            <span class="text-[10px] text-slate-400 uppercase font-semibold">All-Play Record</span>
            <div class="text-base font-bold font-mono text-slate-100 tabular-nums">
              {{ standing.all_play_wins }}-{{ standing.all_play_losses }}
              <span v-if="standing.all_play_ties > 0">-{{ standing.all_play_ties }}</span>
            </div>
            <span class="text-[10px] text-slate-400 font-mono">{{ allPlayPct.toFixed(1) }}% true strength</span>
          </div>

          <div class="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800/80">
            <span class="text-[10px] text-slate-400 uppercase font-semibold">Weekly Median Record</span>
            <div class="text-base font-bold font-mono text-slate-100 tabular-nums">
              {{ standing.median_wins }}-{{ standing.median_losses }}
              <span v-if="standing.median_ties > 0">-{{ standing.median_ties }}</span>
            </div>
            <span class="text-[10px] text-slate-400 font-mono">Top half finishes</span>
          </div>
        </div>

        <!-- Luck Explanation Note -->
        <div class="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80 text-xs leading-relaxed space-y-1">
          <div class="flex items-center gap-1.5 font-semibold" :class="standing.luck_index >= 0 ? 'text-emerald-400' : 'text-rose-400'">
            <Sparkles v-if="standing.luck_index >= 0" class="w-3.5 h-3.5" />
            <ShieldAlert v-else class="w-3.5 h-3.5" />
            <span>{{ standing.luck_index >= 0 ? 'Favorable Schedule Impact' : 'Unlucky Matchup Draw' }}</span>
          </div>
          <p class="text-slate-400 text-[11px]">
            {{
              standing.luck_index >= 0
                ? `Actual Win Rate (${officialWinPct.toFixed(1)}%) is ${luckPct.toFixed(1)}% higher than league-wide all-play strength (${allPlayPct.toFixed(1)}%). Opponents frequently underperformed during matchups.`
                : `Actual Win Rate (${officialWinPct.toFixed(1)}%) is ${Math.abs(luckPct).toFixed(1)}% lower than league-wide all-play strength (${allPlayPct.toFixed(1)}%). Faced unusually difficult opponent scoring draws.`
            }}
          </p>
        </div>
      </div>

      <!-- Section 3: Lineup Optimization & Bench Leftovers -->
      <div class="stadium-card rounded-2xl p-4 border border-slate-800 space-y-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <Percent class="w-4 h-4 text-emerald-400" />
            <h4 class="text-xs uppercase font-bold tracking-wider text-slate-300">
              Lineup Optimization & Bench
            </h4>
          </div>

          <span class="text-[11px] font-mono px-2 py-0.5 rounded font-bold bg-slate-800 text-slate-300">
            {{ efficiencyPct.toFixed(1) }}% Efficient
          </span>
        </div>

        <!-- Efficiency Visual Bar -->
        <div class="space-y-1">
          <div class="flex items-center justify-between text-[11px] font-mono text-slate-400">
            <span>Started Points: {{ standing.points_for.toFixed(1) }}</span>
            <span>Max Optimal: {{ standing.optimal_points_for.toFixed(1) }}</span>
          </div>
          <div class="w-full h-2 rounded-full bg-slate-800 overflow-hidden flex">
            <div
              class="h-full bg-gradient-to-r from-emerald-500 to-teal-400 rounded-full"
              :style="{ width: `${Math.min(100, Math.max(0, efficiencyPct))}%` }"
            ></div>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-2 pt-1">
          <div class="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800/80">
            <span class="text-[10px] text-slate-400 uppercase font-semibold">Total Bench Points</span>
            <div class="text-base font-bold font-mono text-slate-200 tabular-nums">
              {{ standing.bench_points.toFixed(1) }}
            </div>
            <span class="text-[10px] text-slate-500 font-mono">Benched production</span>
          </div>

          <div class="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800/80">
            <span class="text-[10px] text-slate-400 uppercase font-semibold">Sub-Optimal Points Lost</span>
            <div class="text-base font-bold font-mono text-rose-400 tabular-nums">
              {{ benchLostPoints.toFixed(1) }}
            </div>
            <span class="text-[10px] text-slate-500 font-mono">Wrong start/sits</span>
          </div>
        </div>
      </div>

      <!-- Section 4: Financial Prize Ledger & FAAB Budget -->
      <div class="stadium-card rounded-2xl p-4 border border-slate-800 space-y-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <DollarSign class="w-4 h-4 text-emerald-400" />
            <h4 class="text-xs uppercase font-bold tracking-wider text-slate-300">
              Season Bankroll & FAAB
            </h4>
          </div>

          <span
            class="text-[11px] font-mono px-2 py-0.5 rounded font-bold bg-emerald-950/80 text-emerald-400 border border-emerald-800/60"
          >
            Total ${{ standing.total_earnings.toFixed(2) }}
          </span>
        </div>

        <div class="grid grid-cols-3 gap-2">
          <div class="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800/80">
            <span class="text-[10px] text-slate-400 uppercase font-semibold">Weekly Wins</span>
            <div class="text-sm sm:text-base font-bold font-mono text-emerald-400 tabular-nums">
              ${{ standing.weekly_earnings.toFixed(2) }}
            </div>
            <span class="text-[10px] text-slate-500 font-mono">High scores</span>
          </div>

          <div class="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800/80">
            <span class="text-[10px] text-slate-400 uppercase font-semibold">Podium Cash</span>
            <div class="text-sm sm:text-base font-bold font-mono text-amber-400 tabular-nums">
              ${{ standing.podium_earnings.toFixed(2) }}
            </div>
            <span class="text-[10px] text-slate-500 font-mono">1st / 2nd / 3rd</span>
          </div>

          <div class="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800/80">
            <span class="text-[10px] text-slate-400 uppercase font-semibold">FAAB Remaining</span>
            <div class="text-sm sm:text-base font-bold font-mono text-slate-200 tabular-nums">
              ${{ standing.faab_remaining }}
            </div>
            <span class="text-[10px] text-slate-500 font-mono">Waiver budget</span>
          </div>
        </div>
      </div>
    </div>
  </SwipeDrawer>
</template>
