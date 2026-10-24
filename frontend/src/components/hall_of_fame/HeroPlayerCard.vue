<script setup lang="ts">
import { ref, computed } from 'vue';
import type { HallOfFameHeroPlayer } from '@/types/api';

const props = defineProps<{
  player: HallOfFameHeroPlayer;
}>();

const imgFailed = ref(false);

const positionBadge = computed(() => {
  switch (props.player.default_position.toUpperCase()) {
    case 'QB':
      return 'bg-amber-500/20 text-amber-300 border-amber-500/40';
    case 'RB':
      return 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40';
    case 'WR':
      return 'bg-sky-500/20 text-sky-300 border-sky-500/40';
    case 'TE':
      return 'bg-orange-500/20 text-orange-300 border-orange-500/40';
    default:
      return 'bg-purple-500/20 text-purple-300 border-purple-500/40';
  }
});

const barColor = computed(() => {
  switch (props.player.default_position.toUpperCase()) {
    case 'QB':
      return 'bg-amber-400';
    case 'RB':
      return 'bg-emerald-400';
    case 'WR':
      return 'bg-sky-400';
    case 'TE':
      return 'bg-orange-400';
    default:
      return 'bg-purple-400';
  }
});

const initials = computed(() => {
  const parts = props.player.full_name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  }
  return props.player.full_name.slice(0, 2).toUpperCase();
});
</script>

<template>
  <div
    class="relative rounded-2xl bg-slate-900/90 border border-slate-800 p-3.5 sm:p-4 transition-all duration-200 hover:border-slate-700 hover:bg-slate-850 select-none shadow-sm"
  >
    <!-- Top Header: Rank & Role -->
    <div class="flex items-center justify-between gap-2 mb-3">
      <div class="flex items-center gap-2 min-w-0">
        <span
          class="flex items-center justify-center w-5 h-5 rounded-full bg-slate-800 border border-slate-700 text-[10px] font-black text-amber-400 font-mono shrink-0"
        >
          #{{ player.rank }}
        </span>
        <span
          class="text-[10px] font-black font-mono tracking-wider uppercase px-2 py-0.5 rounded border truncate"
          :class="positionBadge"
          :title="player.role_title"
        >
          {{ player.role_title }}
        </span>
      </div>

      <span class="text-[10px] font-mono font-bold text-slate-400 bg-slate-800/80 px-2 py-0.5 rounded border border-slate-700/60 shrink-0">
        {{ player.slot_position }}
      </span>
    </div>

    <!-- Player Info & Headshot -->
    <div class="flex items-center gap-3 sm:gap-3.5">
      <!-- Player Headshot -->
      <div class="relative shrink-0">
        <div
          class="w-14 h-14 sm:w-16 sm:h-16 rounded-2xl bg-slate-950 border border-slate-700/80 p-0.5 overflow-hidden flex items-center justify-center shadow"
        >
          <img
            v-if="player.headshot_url && !imgFailed"
            :src="player.headshot_url"
            :alt="player.full_name"
            class="w-full h-full object-cover object-top"
            loading="lazy"
            @error="imgFailed = true"
          />
          <div
            v-else
            class="w-full h-full bg-slate-800 flex flex-col items-center justify-center font-mono font-black text-slate-400 text-sm"
          >
            <span>{{ initials }}</span>
            <span class="text-[8px] text-slate-500 mt-0.5">{{ player.default_position }}</span>
          </div>
        </div>

        <span
          class="absolute -bottom-1 -right-1 px-1.5 py-0.5 rounded text-[9px] font-black font-mono shadow border border-slate-900"
          :class="positionBadge"
        >
          {{ player.default_position }}
        </span>
      </div>

      <!-- Identity & Points -->
      <div class="flex-1 min-w-0">
        <h4 class="text-sm sm:text-base font-extrabold text-white truncate tracking-tight" :title="player.full_name">
          {{ player.full_name }}
        </h4>

        <div class="text-[11px] font-medium text-slate-400 flex items-center gap-1.5 mt-0.5">
          <span class="font-bold text-slate-300 shrink-0">{{ player.pro_team }}</span>
          <span class="text-slate-600 shrink-0">•</span>
          <span class="text-slate-300 truncate" :title="player.stats_summary">{{ player.stats_summary }}</span>
        </div>

        <!-- Championship Game Points -->
        <div class="mt-2 flex items-baseline justify-between gap-1">
          <div class="flex items-baseline gap-1">
            <span class="text-lg sm:text-xl font-black font-mono text-emerald-400 tracking-tight">
              {{ player.fantasy_points.toFixed(2) }}
            </span>
            <span class="text-[10px] font-bold font-mono text-emerald-500 uppercase">
              PTS
            </span>
          </div>
          <span class="text-[10px] font-mono text-slate-400 font-medium shrink-0">
            {{ player.pct_of_team_points }}% of total
          </span>
        </div>
      </div>
    </div>

    <!-- Impact Progress Bar -->
    <div class="mt-3 pt-2.5 border-t border-slate-800/80">
      <div class="flex items-center justify-between text-[10px] font-mono text-slate-400 mb-1">
        <span class="truncate pr-2">CHAMPIONSHIP CONTRIBUTION</span>
        <span class="text-slate-300 font-bold shrink-0">
          Proj: {{ player.projected_points.toFixed(1) }}
        </span>
      </div>
      <div class="w-full bg-slate-950 rounded-full h-1.5 overflow-hidden p-0.5 border border-slate-800">
        <div
          class="h-full rounded-full transition-all duration-500 ease-out"
          :class="barColor"
          :style="{ width: `${Math.min(100, Math.max(12, player.pct_of_team_points * 2.5))}%` }"
        ></div>
      </div>
    </div>
  </div>
</template>
