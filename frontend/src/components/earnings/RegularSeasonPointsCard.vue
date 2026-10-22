<script setup lang="ts">
import { computed } from 'vue';
import type { RegularSeasonPointsWinner } from '@/types/api';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import { ChevronRight } from 'lucide-vue-next';

const props = defineProps<{
  winner: RegularSeasonPointsWinner;
  seasonYear: number | null;
}>();

const emit = defineEmits<{
  (e: 'open-manager', managerId: number): void;
}>();

const ppg = computed(() => {
  if (!props.winner?.points) return null;
  // Standard regular season is 14 weeks
  const avg = props.winner.points / 14;
  return avg.toFixed(1);
});
</script>

<template>
  <div
    class="relative rounded-xl border border-purple-500/30 bg-gradient-to-b from-[#131124] via-[#0b101b] to-[#070b12] overflow-hidden shadow-xl hover:border-purple-400/50 transition-all duration-200 cursor-pointer group select-none"
    role="button"
    tabindex="0"
    @click="emit('open-manager', winner.manager_id)"
    @keydown.enter="emit('open-manager', winner.manager_id)"
  >
    <!-- Top Accent Bar (Ravens Purple & Gold) -->
    <div class="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-transparent via-purple-400 to-transparent opacity-90"></div>

    <!-- Header Strip -->
    <div class="flex items-center justify-between px-3.5 py-2.5 bg-slate-900/90 border-b border-purple-500/20">
      <div class="flex items-center gap-2.5 min-w-0">
        <!-- Lamar Jackson Headshot: The King of the Regular Season -->
        <div class="w-7 h-7 sm:w-8 sm:h-8 rounded-full overflow-hidden shrink-0 border border-purple-500/40 bg-purple-950/80 shadow-md flex items-center justify-center">
          <img
            src="https://a.espncdn.com/i/headshots/nfl/players/full/3916387.png"
            alt="Lamar Jackson - King of the Regular Season"
            class="w-full h-full object-cover object-top scale-110"
            loading="lazy"
          />
        </div>

        <div class="min-w-0">
          <div class="flex items-center gap-1.5">
            <h3 class="text-xs sm:text-sm font-black uppercase tracking-tight text-purple-200 truncate">
              The Lamar Jackson Award
            </h3>
            <span class="text-[9px] font-mono font-bold uppercase tracking-wider px-1.5 py-0.2 rounded bg-purple-500/15 text-purple-300 border border-purple-500/30 hidden xs:inline shrink-0">
              Season {{ seasonYear ?? '' }}
            </span>
          </div>
          <div class="text-[10px] text-slate-400 truncate font-mono">
            King of the Regular Season · Highest PF
          </div>
        </div>
      </div>

      <div class="flex items-center gap-1.5 shrink-0 font-mono text-xs">
        <span class="font-bold text-emerald-400 tabular-nums text-xs sm:text-sm">
          +${{ winner.amount.toFixed(0) }}
        </span>
        <span class="text-slate-500 text-[10px] hidden xs:inline">Prize</span>
      </div>
    </div>

    <!-- Card Body -->
    <div class="p-3 sm:p-4 flex items-center justify-between gap-3">
      <!-- Winner Manager & Team -->
      <div class="flex items-center gap-3 min-w-0">
        <TeamAvatar
          :src="winner.avatar_url"
          :name="winner.team_name"
          size="md"
          rounded="xl"
        />
        <div class="min-w-0">
          <div class="flex items-center gap-1.5 flex-wrap">
            <span class="text-xs sm:text-sm font-black text-slate-100 truncate group-hover:text-purple-300 transition-colors">
              {{ winner.team_name }}
            </span>
            <span
              v-if="winner.is_tie"
              class="text-[9px] font-mono font-bold uppercase px-1 py-0.2 rounded bg-slate-800 text-slate-400 shrink-0"
            >
              Tie
            </span>
          </div>
          <div class="text-[11px] text-slate-400 truncate mt-0.5 font-medium flex items-center gap-1.5">
            <span>{{ winner.manager_name }}</span>
            <span class="text-slate-600">•</span>
            <span class="text-purple-400/90 text-[10px] font-mono inline-flex items-center gap-0.5 font-semibold">
              👑 Most Points
            </span>
          </div>
        </div>
      </div>

      <!-- Total Points Scored & PPG -->
      <div class="flex items-center gap-3 shrink-0 text-right font-mono">
        <div>
          <div class="text-base sm:text-lg font-black text-purple-300 tabular-nums leading-none">
            {{ winner.points.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}
            <span class="text-[10px] font-bold text-purple-400/80 uppercase ml-0.5">PF</span>
          </div>
          <span v-if="ppg" class="text-[10px] text-slate-400 tabular-nums mt-1 block">
            {{ ppg }} pts/wk
          </span>
        </div>

        <ChevronRight class="w-4 h-4 text-slate-500 group-hover:text-purple-300 group-hover:translate-x-0.5 transition-all" />
      </div>
    </div>
  </div>
</template>
