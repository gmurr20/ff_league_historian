<script setup lang="ts">
import { computed } from 'vue';
import type { StandingEntry } from '@/types/api';
import { Crown, Sparkles, ShieldAlert, Radio, Calendar } from 'lucide-vue-next';

const props = defineProps<{
  standings: StandingEntry[];
  seasonYear: number;
  isActive: boolean;
  isCompleted: boolean;
  currentWeek: number;
}>();

const topScorer = computed(() => {
  if (!props.standings.length) return null;
  return [...props.standings].sort((a, b) => b.points_for - a.points_for)[0];
});

const luckiest = computed(() => {
  if (!props.standings.length) return null;
  const sorted = [...props.standings].sort((a, b) => b.luck_index - a.luck_index);
  return sorted[0];
});

const mostRobbed = computed(() => {
  if (!props.standings.length) return null;
  const sorted = [...props.standings].sort((a, b) => a.luck_index - b.luck_index);
  return sorted[0];
});

function formatLuck(val: number): string {
  const pct = Math.abs(val) <= 1 ? val * 100 : val;
  const sign = pct > 0 ? '+' : '';
  return `${sign}${pct.toFixed(1)}%`;
}
</script>

<template>
  <div class="space-y-2">
    <!-- Status & Week Strip -->
    <div class="flex items-center justify-between text-xs px-1">
      <div class="flex items-center gap-2">
        <span
          class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold tracking-wide uppercase"
          :class="
            isActive
              ? 'bg-emerald-950/80 text-emerald-400 border border-emerald-800/60 shadow-sm shadow-emerald-950/50'
              : 'bg-slate-800/80 text-slate-300 border border-slate-700/60'
          "
        >
          <span v-if="isActive" class="relative flex h-2 w-2">
            <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
          <Radio v-else class="w-3 h-3 text-slate-400" />
          <span>{{ isActive ? 'Season Active' : isCompleted ? 'Season Final' : 'Archived' }}</span>
        </span>

        <span class="text-slate-600">•</span>

        <span class="text-slate-400 font-mono flex items-center gap-1 text-[11px]">
          <Calendar class="w-3 h-3 text-slate-500" />
          <span>{{ isCompleted ? 'Completed Season' : `Week ${currentWeek}` }}</span>
        </span>
      </div>

      <span class="text-[11px] font-mono text-slate-500">
        {{ standings.length }} Franchises
      </span>
    </div>

    <!-- KPI Cards Grid -->
    <div class="grid grid-cols-3 gap-2">
      <!-- Top Scorer -->
      <div
        class="stadium-card rounded-xl p-2.5 sm:p-3 border border-slate-800/80 flex flex-col justify-between"
      >
        <div class="flex items-center justify-between gap-1 mb-1">
          <span class="text-[10px] uppercase font-bold tracking-wider text-slate-400">Top Scorer</span>
          <Crown class="w-3.5 h-3.5 text-amber-400 shrink-0" />
        </div>
        <div v-if="topScorer">
          <div class="text-xs sm:text-sm font-bold text-slate-100 truncate" :title="topScorer.team_name">
            {{ topScorer.team_name }}
          </div>
          <div class="text-[11px] font-mono text-amber-400 font-semibold tabular-nums mt-0.5">
            {{ topScorer.points_for.toFixed(1) }} <span class="text-[9px] text-slate-400 uppercase">PF</span>
          </div>
        </div>
        <div v-else class="text-xs text-slate-500">—</div>
      </div>

      <!-- Luckiest Manager -->
      <div
        class="stadium-card rounded-xl p-2.5 sm:p-3 border border-slate-800/80 flex flex-col justify-between"
      >
        <div class="flex items-center justify-between gap-1 mb-1">
          <span class="text-[10px] uppercase font-bold tracking-wider text-emerald-400">Luckiest</span>
          <Sparkles class="w-3.5 h-3.5 text-emerald-400 shrink-0" />
        </div>
        <div v-if="luckiest">
          <div class="text-xs sm:text-sm font-bold text-slate-100 truncate" :title="luckiest.team_name">
            {{ luckiest.manager_name }}
          </div>
          <div class="text-[11px] font-mono text-emerald-400 font-semibold tabular-nums mt-0.5">
            {{ formatLuck(luckiest.luck_index) }} <span class="text-[9px] text-emerald-500 uppercase">Luck</span>
          </div>
        </div>
        <div v-else class="text-xs text-slate-500">—</div>
      </div>

      <!-- Most Robbed Manager -->
      <div
        class="stadium-card rounded-xl p-2.5 sm:p-3 border border-slate-800/80 flex flex-col justify-between"
      >
        <div class="flex items-center justify-between gap-1 mb-1">
          <span class="text-[10px] uppercase font-bold tracking-wider text-rose-400">Most Robbed</span>
          <ShieldAlert class="w-3.5 h-3.5 text-rose-400 shrink-0" />
        </div>
        <div v-if="mostRobbed">
          <div class="text-xs sm:text-sm font-bold text-slate-100 truncate" :title="mostRobbed.team_name">
            {{ mostRobbed.manager_name }}
          </div>
          <div class="text-[11px] font-mono text-rose-400 font-semibold tabular-nums mt-0.5">
            {{ formatLuck(mostRobbed.luck_index) }} <span class="text-[9px] text-rose-500 uppercase">Luck</span>
          </div>
        </div>
        <div v-else class="text-xs text-slate-500">—</div>
      </div>
    </div>
  </div>
</template>
