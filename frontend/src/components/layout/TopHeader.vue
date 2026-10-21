<script setup lang="ts">
import { computed } from 'vue';
import { useLeagueMeta } from '@/composables/useLeagueMeta';
import { Calendar, ChevronDown, Radio } from 'lucide-vue-next';

const { meta, selectedSeason, availableSeasons } = useLeagueMeta();

const leagueTitle = computed(() => {
  return meta.value?.league_name || 'FF League Historian';
});

const lastSyncFormatted = computed(() => {
  const sync = meta.value?.last_sync;
  if (!sync) return null;
  const timestamp = sync.last_weekly_sync_at || sync.last_backfill_at;
  if (!timestamp) return null;

  try {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffHours / 24);

    if (diffHours < 1) {
      const diffMins = Math.max(1, Math.floor(diffMs / (1000 * 60)));
      return `${diffMins}m ago`;
    } else if (diffHours < 24) {
      return `${diffHours}h ago`;
    } else if (diffDays < 7) {
      return `${diffDays}d ago`;
    }
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  } catch {
    return null;
  }
});

const isLiveSeason = computed(() => {
  return availableSeasons.value.some(s => s.is_active && (selectedSeason.value === s.season_year || selectedSeason.value === null));
});
</script>

<template>
  <header
    class="sticky top-0 z-40 w-full bg-slate-950/90 backdrop-blur-md border-b border-slate-800/80 pt-safe px-3 sm:px-4 py-2.5 transition-colors"
  >
    <div class="max-w-7xl mx-auto flex items-center justify-between gap-2">
      <!-- League Branding & Sync Status -->
      <div class="flex flex-col min-w-0">
        <div class="flex items-center gap-2">
          <div
            class="w-6 h-6 rounded-md bg-gradient-to-br from-emerald-500 to-teal-700 flex items-center justify-center shrink-0 shadow-sm"
          >
            <span class="text-xs font-black tracking-tight text-slate-950 font-mono">FF</span>
          </div>
          <h1
            class="text-sm sm:text-base font-bold text-slate-100 truncate tracking-tight uppercase"
            :title="leagueTitle"
          >
            {{ leagueTitle }}
          </h1>
        </div>

        <div class="flex items-center gap-2 mt-0.5 text-[11px] text-slate-400">
          <div class="flex items-center gap-1.5">
            <span
              class="relative flex h-2 w-2"
              :title="isLiveSeason ? 'Season Active' : 'Synced'"
            >
              <span
                v-if="isLiveSeason"
                class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"
              ></span>
              <span
                class="relative inline-flex rounded-full h-2 w-2"
                :class="isLiveSeason ? 'bg-emerald-500' : 'bg-slate-500'"
              ></span>
            </span>
            <span class="font-medium text-slate-400">
              {{ isLiveSeason ? 'Active' : 'Archived' }}
            </span>
          </div>

          <span v-if="lastSyncFormatted" class="text-slate-600">•</span>
          <span v-if="lastSyncFormatted" class="flex items-center gap-1 text-slate-400">
            <Radio class="w-3 h-3 text-slate-500" />
            <span>Synced {{ lastSyncFormatted }}</span>
          </span>
        </div>
      </div>

      <!-- Interactive Season Selector Pill -->
      <div class="relative shrink-0 flex items-center">
        <div
          class="flex items-center gap-1.5 bg-slate-900 border border-slate-700/80 hover:border-slate-600 rounded-full px-3 py-1 text-xs font-semibold text-slate-200 shadow-inner group transition-all"
        >
          <Calendar class="w-3.5 h-3.5 text-emerald-400 shrink-0" />
          <span class="tracking-wide">
            {{ selectedSeason === null ? 'All Time' : selectedSeason }}
          </span>
          <ChevronDown class="w-3.5 h-3.5 text-slate-400 group-hover:text-slate-200 transition-colors" />

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
              {{ season.season_year }} {{ season.is_active ? '(Active Season)' : '' }}
            </option>
          </select>
        </div>
      </div>
    </div>
  </header>
</template>
