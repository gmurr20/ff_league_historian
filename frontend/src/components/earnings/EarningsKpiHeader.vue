<script setup lang="ts">
import { computed } from 'vue';
import type { EarningsLeaderboardEntry } from '@/types/api';
import { DollarSign, Trophy, Award, Landmark, Flame } from 'lucide-vue-next';

const props = defineProps<{
  leaderboard: EarningsLeaderboardEntry[];
  weeklyWinValue: number;
  seasonFilter: number | null;
}>();

const totalCashAwarded = computed(() => {
  return props.leaderboard.reduce((acc, entry) => acc + entry.total_earnings, 0);
});

const totalPodiumCash = computed(() => {
  return props.leaderboard.reduce((acc, entry) => acc + entry.podium_earnings, 0);
});

const totalWeeklyCash = computed(() => {
  return props.leaderboard.reduce((acc, entry) => acc + entry.weekly_earnings, 0);
});

const totalChampionships = computed(() => {
  return props.leaderboard.reduce((acc, entry) => acc + entry.championships, 0);
});

const totalWeeklyWins = computed(() => {
  return props.leaderboard.reduce((acc, entry) => acc + entry.weekly_wins_count, 0);
});
</script>

<template>
  <div class="space-y-2">
    <!-- Scope Info Strip -->
    <div class="flex items-center justify-between text-xs px-1">
      <div class="flex items-center gap-1.5 text-slate-400 font-mono text-[11px]">
        <Landmark class="w-3 h-3 text-emerald-400" />
        <span>{{ seasonFilter === null ? 'All-Time Financial Ledger' : `Season ${seasonFilter} Ledger` }}</span>
      </div>

      <span class="text-[11px] font-mono text-slate-500">
        {{ leaderboard.length }} Managers
      </span>
    </div>

    <!-- KPI Grid -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
      <!-- Total Cash Awarded -->
      <div class="stadium-card rounded-xl p-3 border border-slate-800/80 flex flex-col justify-between">
        <div class="flex items-center justify-between gap-1 mb-1">
          <span class="text-[10px] uppercase font-bold tracking-wider text-emerald-400">Total Cash</span>
          <DollarSign class="w-3.5 h-3.5 text-emerald-400 shrink-0" />
        </div>
        <div>
          <div class="text-base sm:text-lg font-black font-mono text-emerald-400 tabular-nums">
            ${{ totalCashAwarded.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) }}
          </div>
          <span class="text-[10px] text-slate-500 font-mono">Awarded Prizes</span>
        </div>
      </div>

      <!-- Weekly Win Value -->
      <div class="stadium-card rounded-xl p-3 border border-slate-800/80 flex flex-col justify-between">
        <div class="flex items-center justify-between gap-1 mb-1">
          <span class="text-[10px] uppercase font-bold tracking-wider text-slate-400">Weekly Prize</span>
          <Flame class="w-3.5 h-3.5 text-amber-400 shrink-0" />
        </div>
        <div>
          <div class="text-base sm:text-lg font-black font-mono text-slate-100 tabular-nums">
            ${{ weeklyWinValue.toFixed(0) }}
            <span class="text-[11px] font-normal text-slate-400 font-sans">/wk</span>
          </div>
          <span class="text-[10px] text-slate-500 font-mono">${{ totalWeeklyCash.toFixed(0) }} · {{ totalWeeklyWins }} Wins</span>
        </div>
      </div>

      <!-- Podium Payouts -->
      <div class="stadium-card rounded-xl p-3 border border-slate-800/80 flex flex-col justify-between">
        <div class="flex items-center justify-between gap-1 mb-1">
          <span class="text-[10px] uppercase font-bold tracking-wider text-amber-400">Podium Cash</span>
          <Trophy class="w-3.5 h-3.5 text-amber-400 shrink-0" />
        </div>
        <div>
          <div class="text-base sm:text-lg font-black font-mono text-amber-400 tabular-nums">
            ${{ totalPodiumCash.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) }}
          </div>
          <span class="text-[10px] text-slate-500 font-mono">1st / 2nd / 3rd</span>
        </div>
      </div>

      <!-- Championships -->
      <div class="stadium-card rounded-xl p-3 border border-slate-800/80 flex flex-col justify-between">
        <div class="flex items-center justify-between gap-1 mb-1">
          <span class="text-[10px] uppercase font-bold tracking-wider text-slate-400">Championships</span>
          <Award class="w-3.5 h-3.5 text-slate-300 shrink-0" />
        </div>
        <div>
          <div class="text-base sm:text-lg font-black font-mono text-slate-100 tabular-nums">
            {{ totalChampionships }}
          </div>
          <span class="text-[10px] text-slate-500 font-mono">Banners Raised</span>
        </div>
      </div>
    </div>
  </div>
</template>
