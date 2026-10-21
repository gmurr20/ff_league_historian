<script setup lang="ts">
import { computed } from 'vue';
import type { EarningsLeaderboardEntry } from '@/types/api';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import { Trophy, Medal, ChevronRight } from 'lucide-vue-next';

const props = defineProps<{
  entry: EarningsLeaderboardEntry;
  rank: number;
  maxEarnings: number;
  isSingleSeason: boolean;
}>();

defineEmits<{
  (e: 'click'): void;
}>();

const weeklyPct = computed(() => {
  if (props.entry.total_earnings <= 0) return 0;
  return (props.entry.weekly_earnings / props.entry.total_earnings) * 100;
});

const podiumPct = computed(() => {
  if (props.entry.total_earnings <= 0) return 0;
  return (props.entry.podium_earnings / props.entry.total_earnings) * 100;
});

// Overall bar width relative to top earner
const relativeSharePct = computed(() => {
  if (props.maxEarnings <= 0) return 0;
  return Math.min(100, Math.max(8, (props.entry.total_earnings / props.maxEarnings) * 100));
});

const totalTrophies = computed(() => {
  return props.entry.championships + props.entry.runner_ups + props.entry.third_places;
});
</script>

<template>
  <div
    class="stadium-card rounded-2xl p-3.5 sm:p-4 border transition-all duration-150 cursor-pointer select-none active:scale-[0.99] hover:border-slate-700"
    :class="[
      rank === 1
        ? 'border-amber-500/40 stadium-glow-amber bg-gradient-to-b from-amber-950/20 via-slate-900/90 to-slate-950/90'
        : rank <= 3
        ? 'border-slate-700/80'
        : 'border-slate-800/80'
    ]"
    role="button"
    tabindex="0"
    @click="$emit('click')"
    @keydown.enter="$emit('click')"
  >
    <!-- Top Row: Rank, Manager Name, Trophy Case, Total Earnings -->
    <div class="flex items-start justify-between gap-2.5">
      <div class="flex items-center gap-2.5 min-w-0">
        <!-- Rank Pill -->
        <div
          class="w-7 h-7 rounded-xl flex items-center justify-center font-black font-mono text-xs shrink-0 shadow-inner"
          :class="[
            rank === 1
              ? 'bg-amber-500 text-slate-950 shadow-amber-500/50'
              : rank === 2
              ? 'bg-slate-300 text-slate-950 shadow-slate-300/40'
              : rank === 3
              ? 'bg-amber-700 text-amber-100 shadow-amber-800/40'
              : 'bg-slate-800 text-slate-300 border border-slate-700/60'
          ]"
        >
          {{ rank }}
        </div>

        <!-- ESPN Team Avatar -->
        <TeamAvatar :src="entry.avatar_url" :name="entry.team_name" size="md" rounded="xl" />

        <!-- Team Name (First Title) & Manager Actual Name Underneath -->
        <div class="min-w-0">
          <div class="flex items-center gap-1.5 flex-wrap">
            <h3 class="text-sm sm:text-base font-bold text-slate-100 truncate tracking-tight">
              {{ entry.team_name }}
            </h3>

            <!-- Championship badge -->
            <span
              v-if="entry.championships > 0"
              class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 ring-1 ring-amber-500/30"
              title="Championships"
            >
              <Trophy class="w-3 h-3 text-amber-400" />
              <span>{{ entry.championships }}x</span>
            </span>

            <!-- Runner up badge -->
            <span
              v-if="entry.runner_ups > 0"
              class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-slate-400/20 text-slate-300 border border-slate-400/40"
              title="Runner-Ups"
            >
              <Medal class="w-3 h-3 text-slate-300" />
              <span>{{ entry.runner_ups }}x</span>
            </span>

            <!-- 3rd place badge -->
            <span
              v-if="entry.third_places > 0"
              class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-800/20 text-amber-500 border border-amber-800/40"
              title="3rd Place Finishes"
            >
              <Medal class="w-3 h-3 text-amber-600" />
              <span>{{ entry.third_places }}x</span>
            </span>
          </div>

          <p class="text-xs text-slate-400 truncate mt-0.5 flex items-center gap-1.5">
            <span class="text-slate-300 font-medium">{{ entry.display_name }}</span>
            <span class="text-slate-600">•</span>
            <span>{{ entry.seasons_played }} {{ entry.seasons_played === 1 ? 'Season' : 'Seasons' }}</span>
            <span v-if="totalTrophies > 0" class="text-slate-600">•</span>
            <span v-if="totalTrophies > 0" class="text-slate-400">{{ totalTrophies }} Total Podiums</span>
          </p>
        </div>
      </div>

      <!-- Total Earnings & Drawer Chevron -->
      <div class="flex items-center gap-2 shrink-0">
        <div class="text-right">
          <div
            class="text-base sm:text-lg font-black font-mono tabular-nums tracking-tight"
            :class="entry.total_earnings > 0 ? 'text-emerald-400' : 'text-slate-400'"
          >
            ${{ entry.total_earnings.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}
          </div>
          <span class="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Net Bankroll</span>
        </div>

        <ChevronRight class="w-4 h-4 text-slate-500 group-hover:text-slate-300 shrink-0" />
      </div>
    </div>

    <!-- Middle: Stacked Visual Progress Bar -->
    <div class="mt-3 pt-2.5 border-t border-slate-800/80 space-y-1.5">
      <!-- Relative Bar Container -->
      <div class="w-full bg-slate-900/90 rounded-full h-2 overflow-hidden flex border border-slate-800">
        <!-- Relative earner width -->
        <div
          class="h-full flex rounded-full overflow-hidden transition-all duration-300"
          :style="{ width: `${relativeSharePct}%` }"
        >
          <!-- Podium Cash Segment (Amber) -->
          <div
            v-if="entry.podium_earnings > 0"
            class="h-full bg-gradient-to-r from-amber-500 to-amber-400 transition-all"
            :style="{ width: `${podiumPct}%` }"
            :title="`Podium Cash: $${entry.podium_earnings.toFixed(2)}`"
          ></div>
          <!-- Weekly Wins Segment (Turf Emerald) -->
          <div
            v-if="entry.weekly_earnings > 0"
            class="h-full bg-gradient-to-r from-emerald-500 to-teal-400 transition-all"
            :style="{ width: `${weeklyPct}%` }"
            :title="`Weekly High Score Cash: $${entry.weekly_earnings.toFixed(2)}`"
          ></div>
        </div>
      </div>

      <!-- Legend & Breakdown Labels -->
      <div class="flex items-center justify-between text-[11px] font-mono text-slate-400">
        <!-- Podium Breakdown -->
        <div class="flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-amber-400 shrink-0"></span>
          <span class="text-slate-300 font-semibold">${{ entry.podium_earnings.toFixed(0) }}</span>
          <span class="text-slate-500 text-[10px]">Podium</span>
        </div>

        <!-- Weekly Wins Breakdown -->
        <div class="flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-emerald-400 shrink-0"></span>
          <span class="text-slate-300 font-semibold">${{ entry.weekly_earnings.toFixed(0) }}</span>
          <span class="text-slate-500 text-[10px]">
            ({{ entry.weekly_wins_count }} {{ entry.weekly_wins_count === 1 ? 'Win' : 'Wins' }}<span v-if="entry.weekly_ties_count > 0">, {{ entry.weekly_ties_count }}T</span>)
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
