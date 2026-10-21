<script setup lang="ts">
import { computed } from 'vue';
import { useLeagueMeta } from '@/composables/useLeagueMeta';

const { meta, selectedSeason, availableSeasons } = useLeagueMeta();

const leagueTitle = computed(() => {
  return meta.value?.league_name || 'League Historian';
});
</script>

<template>
  <header
    class="sticky top-0 z-40 w-full bg-[#060911]/95 backdrop-blur-md border-b border-slate-800/80 pt-safe px-3 sm:px-4 py-2 transition-colors"
  >
    <div class="max-w-7xl mx-auto flex items-center justify-between gap-2">
      <!-- Editorial League Wordmark -->
      <div class="flex items-center gap-2 min-w-0">
        <span class="w-1.5 h-4 rounded-full bg-emerald-500 shrink-0"></span>
        <h1
          class="text-sm sm:text-base font-black text-slate-100 truncate tracking-tight uppercase"
          :title="leagueTitle"
        >
          {{ leagueTitle }}
        </h1>
      </div>

      <!-- Minimalist Season Selector Pill -->
      <div class="relative shrink-0 flex items-center">
        <div
          class="flex items-center gap-1.5 bg-slate-900 border border-slate-800 hover:border-slate-700 rounded-lg px-2.5 py-1 text-xs font-mono font-bold text-slate-200 transition-all"
        >
          <span>
            {{ selectedSeason === null ? 'ALL TIME' : selectedSeason }}
          </span>
          <span class="text-[10px] text-slate-500">▾</span>

          <!-- Native Mobile-Optimized Overlay Select -->
          <select
            v-model="selectedSeason"
            aria-label="Select Season"
            class="absolute inset-0 opacity-0 w-full h-full cursor-pointer bg-transparent text-slate-900"
          >
            <option :value="null">All Time</option>
            <option
              v-for="season in availableSeasons"
              :key="season.season_year"
              :value="season.season_year"
            >
              {{ season.season_year }}
            </option>
          </select>
        </div>
      </div>
    </div>
  </header>
</template>
