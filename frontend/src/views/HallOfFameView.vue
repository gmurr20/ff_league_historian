<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { fetchHallOfFame } from '@/api/client';
import type { HallOfFameResponse } from '@/types/api';
import ChampionshipBanners from '@/components/hall_of_fame/ChampionshipBanners.vue';
import ChampionshipSpotlight from '@/components/hall_of_fame/ChampionshipSpotlight.vue';
import LoadingState from '@/components/ui/LoadingState.vue';
import EmptyState from '@/components/ui/EmptyState.vue';
import { Trophy, Crown, RefreshCw, AlertCircle } from 'lucide-vue-next';

const hallOfFameData = ref<HallOfFameResponse | null>(null);
const loading = ref<boolean>(true);
const error = ref<string | null>(null);
const selectedSeasonYear = ref<number | null>(null);

async function loadHallOfFame(season?: number | null): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const res = await fetchHallOfFame(season);
    hallOfFameData.value = res;
    selectedSeasonYear.value = res.selected_season;
  } catch (err: unknown) {
    if (err instanceof Error) {
      error.value = err.message;
    } else {
      error.value = 'Failed to load Hall of Fame records.';
    }
    console.error('Error fetching Hall of Fame data:', err);
  } finally {
    loading.value = false;
  }
}

function handleSelectSeason(seasonYear: number): void {
  if (selectedSeasonYear.value === seasonYear) return;
  loadHallOfFame(seasonYear);
}

onMounted(() => {
  loadHallOfFame();
});
</script>

<template>
  <div class="min-h-screen pb-24 pt-3 px-3 sm:px-6 max-w-5xl mx-auto space-y-6">
    <!-- Header Section -->
    <header class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800/80 pb-4">
      <div class="min-w-0">
        <div class="flex items-center gap-2">
          <div class="w-8 h-8 rounded-xl bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-amber-400 shadow-[0_0_15px_rgba(245,158,11,0.2)] shrink-0">
            <Trophy class="w-4 h-4 fill-amber-400/40" />
          </div>
          <h1 class="text-xl sm:text-2xl font-black text-white tracking-tight">
            Hall of Fame
          </h1>
          <span class="text-[10px] font-mono font-bold text-amber-400 bg-amber-500/15 px-2 py-0.5 rounded-full border border-amber-500/30 uppercase shrink-0">
            Legends
          </span>
        </div>
        <p class="text-xs text-slate-400 mt-1 font-medium truncate sm:truncate-none">
          Championship Banners & Title Game Victory Spotlight
        </p>
      </div>

      <!-- Season Selector Pills -->
      <div
        v-if="hallOfFameData && hallOfFameData.available_seasons.length > 0"
        class="flex items-center gap-1.5 overflow-x-auto py-1 no-scrollbar shrink-0"
      >
        <button
          v-for="year in hallOfFameData.available_seasons"
          :key="year"
          @click="handleSelectSeason(year)"
          class="px-3 py-1.5 rounded-xl text-xs font-mono font-bold transition-all shrink-0 flex items-center gap-1.5 border"
          :class="[
            selectedSeasonYear === year
              ? 'bg-amber-500 text-slate-950 border-amber-400 shadow-sm'
              : 'bg-slate-900 text-slate-400 hover:text-white border-slate-800 hover:border-slate-700',
          ]"
        >
          <Crown class="w-3 h-3 fill-current" />
          <span>{{ year }} {{ year === hallOfFameData.reigning_champion_year ? 'Reigning' : 'Title' }}</span>
        </button>
      </div>
    </header>

    <!-- Loading State -->
    <div v-if="loading && !hallOfFameData" class="py-16">
      <LoadingState message="Entering the Hall of Fame Room..." />
    </div>

    <!-- Error State -->
    <div
      v-else-if="error"
      class="bg-rose-950/30 border border-rose-500/30 rounded-2xl p-6 text-center space-y-3"
    >
      <div class="w-12 h-12 rounded-full bg-rose-500/20 text-rose-400 flex items-center justify-center mx-auto">
        <AlertCircle class="w-6 h-6" />
      </div>
      <h3 class="text-base font-bold text-white">Failed to Load Hall of Fame</h3>
      <p class="text-xs text-slate-400 max-w-sm mx-auto">{{ error }}</p>
      <button
        @click="loadHallOfFame(selectedSeasonYear)"
        class="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white text-xs font-bold transition-colors inline-flex items-center gap-2"
      >
        <RefreshCw class="w-3.5 h-3.5" />
        <span>Try Again</span>
      </button>
    </div>

    <!-- Content View -->
    <div v-else-if="hallOfFameData" class="space-y-6">
      <!-- 1. Stadium Championship Banners Section -->
      <section v-if="hallOfFameData.banners.length > 0">
        <ChampionshipBanners
          :banners="hallOfFameData.banners"
          :selected-season="hallOfFameData.selected_season"
          @select-season="handleSelectSeason"
        />
      </section>

      <!-- 2. Championship Showcase Spotlight -->
      <section v-if="hallOfFameData.featured_champion">
        <ChampionshipSpotlight
          :champion="hallOfFameData.featured_champion"
        />
      </section>

      <!-- Empty State fallback if no champion data -->
      <section v-else>
        <EmptyState
          title="No Champion Crowned Yet"
          description="Championship banners will be hoisted once the playoffs conclude and the final game is played."
        />
      </section>
    </div>
  </div>
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar {
  display: none;
}
.no-scrollbar {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
</style>
