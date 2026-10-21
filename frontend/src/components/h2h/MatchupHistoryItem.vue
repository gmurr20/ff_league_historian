<script setup lang="ts">
import { computed } from 'vue';
import type { H2HMatchupGame } from '@/types/api';
import { Trophy, Calendar, Check, Minus } from 'lucide-vue-next';

const props = defineProps<{
  matchup: H2HMatchupGame;
  managerAId: number;
  managerBId: number;
  managerAName?: string;
  managerBName?: string;
}>();

const isPlayoffs = computed(() => {
  return props.matchup.matchup_type === 'WINNERS_BRACKET';
});

const isManagerAWinner = computed(() => {
  return props.matchup.winner_manager_id === props.managerAId;
});

const isManagerBWinner = computed(() => {
  return props.matchup.winner_manager_id === props.managerBId;
});

const isTie = computed(() => {
  return props.matchup.winner_manager_id === null;
});

const margin = computed(() => {
  return Math.abs(props.matchup.manager_a_score - props.matchup.manager_b_score).toFixed(1);
});
</script>

<template>
  <div
    class="p-3.5 sm:p-4 rounded-xl border transition-all"
    :class="[
      isPlayoffs
        ? 'bg-gradient-to-r from-amber-950/20 via-slate-900/80 to-slate-900/90 border-amber-500/30 shadow-sm shadow-amber-950/30'
        : 'bg-slate-900/70 border-slate-800/80 hover:border-slate-700/80',
    ]"
  >
    <!-- Top Row: Season / Week & Matchup Type -->
    <div class="flex items-center justify-between gap-2 mb-2.5 pb-2 border-b border-slate-800/60 text-xs">
      <div class="flex items-center gap-1.5 text-slate-400 font-medium">
        <Calendar class="w-3.5 h-3.5 text-slate-500" />
        <span>{{ matchup.season_year }}</span>
        <span class="text-slate-600">•</span>
        <span class="text-slate-300 font-semibold">Week {{ matchup.week }}</span>
      </div>

      <div class="flex items-center gap-2">
        <span
          v-if="isPlayoffs"
          class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-amber-500/15 text-amber-400 border border-amber-500/30"
        >
          <Trophy class="w-3 h-3 text-amber-400" />
          <span>Championship Playoff</span>
        </span>
        <span
          v-else
          class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-wider bg-slate-800/80 text-slate-400 border border-slate-700/60"
        >
          Regular Season
        </span>

        <span
          v-if="!isTie"
          class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400"
        >
          ±{{ margin }}
        </span>
      </div>
    </div>

    <!-- Matchup Score Grid (2 Teams) -->
    <div class="grid grid-cols-2 gap-2 sm:gap-3 items-stretch">
      <!-- Team A Box -->
      <div
        class="p-2.5 rounded-lg border flex flex-col justify-between transition-colors"
        :class="[
          isManagerAWinner
            ? 'bg-emerald-950/30 border-emerald-500/40 text-emerald-100 shadow-sm shadow-emerald-950/40'
            : isTie
              ? 'bg-slate-800/40 border-slate-700/50 text-slate-300'
              : 'bg-slate-900/40 border-slate-800/60 text-slate-400 opacity-80',
        ]"
      >
        <div class="flex items-start justify-between gap-1 mb-1">
          <div class="min-w-0 flex-1">
            <span
              v-if="managerAName"
              class="text-[10px] font-bold uppercase tracking-wider block truncate"
              :class="isManagerAWinner ? 'text-emerald-400' : 'text-slate-400'"
            >
              {{ managerAName }}
            </span>
            <div class="text-xs font-semibold text-slate-200 truncate mt-0.5">
              {{ matchup.manager_a_team_name }}
            </div>
          </div>
          <span
            v-if="isManagerAWinner"
            class="shrink-0 inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-extrabold bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 uppercase"
          >
            <Check class="w-2.5 h-2.5 stroke-[3]" />
            W
          </span>
          <span
            v-else-if="isTie"
            class="shrink-0 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-700/50 text-slate-400"
          >
            <Minus class="w-2.5 h-2.5" />
          </span>
        </div>

        <div class="text-right mt-1">
          <span
            class="font-mono text-base sm:text-lg font-black tracking-tight"
            :class="isManagerAWinner ? 'text-emerald-300' : 'text-slate-300'"
          >
            {{ matchup.manager_a_score.toFixed(1) }}
          </span>
        </div>
      </div>

      <!-- Team B Box -->
      <div
        class="p-2.5 rounded-lg border flex flex-col justify-between transition-colors"
        :class="[
          isManagerBWinner
            ? 'bg-emerald-950/30 border-emerald-500/40 text-emerald-100 shadow-sm shadow-emerald-950/40'
            : isTie
              ? 'bg-slate-800/40 border-slate-700/50 text-slate-300'
              : 'bg-slate-900/40 border-slate-800/60 text-slate-400 opacity-80',
        ]"
      >
        <div class="flex items-start justify-between gap-1 mb-1">
          <div class="min-w-0 flex-1">
            <span
              v-if="managerBName"
              class="text-[10px] font-bold uppercase tracking-wider block truncate"
              :class="isManagerBWinner ? 'text-emerald-400' : 'text-slate-400'"
            >
              {{ managerBName }}
            </span>
            <div class="text-xs font-semibold text-slate-200 truncate mt-0.5">
              {{ matchup.manager_b_team_name }}
            </div>
          </div>
          <span
            v-if="isManagerBWinner"
            class="shrink-0 inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-extrabold bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 uppercase"
          >
            <Check class="w-2.5 h-2.5 stroke-[3]" />
            W
          </span>
          <span
            v-else-if="isTie"
            class="shrink-0 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-700/50 text-slate-400"
          >
            <Minus class="w-2.5 h-2.5" />
          </span>
        </div>

        <div class="text-right mt-1">
          <span
            class="font-mono text-base sm:text-lg font-black tracking-tight"
            :class="isManagerBWinner ? 'text-emerald-300' : 'text-slate-300'"
          >
            {{ matchup.manager_b_score.toFixed(1) }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
