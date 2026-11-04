<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { fetchDrafts } from '@/api/client';
import type { DraftsResponse } from '@/types/api';
import LoadingState from '@/components/ui/LoadingState.vue';
import EmptyState from '@/components/ui/EmptyState.vue';
import FutureDraftBoard from '@/components/drafts/FutureDraftBoard.vue';
import HistoricalDraftBoard from '@/components/drafts/HistoricalDraftBoard.vue';

const route = useRoute();
const router = useRouter();

const loading = ref<boolean>(true);
const error = ref<string | null>(null);
const draftResponse = ref<DraftsResponse | null>(null);

function parseSeasonQuery(raw: unknown): number | null {
  if (typeof raw === 'string') {
    const parsed = parseInt(raw, 10);
    if (!isNaN(parsed) && parsed > 2000) return parsed;
  }
  return null;
}

const activeSeason = ref<number | null>(parseSeasonQuery(route.query.season));

async function loadDraft(seasonYear?: number | null) {
  loading.value = true;
  error.value = null;

  try {
    const data = await fetchDrafts(seasonYear);
    draftResponse.value = data;
    activeSeason.value = data.selected_season;
  } catch (err: unknown) {
    if (err instanceof Error) {
      error.value = err.message;
    } else {
      error.value = 'Failed to load draft data';
    }
  } finally {
    loading.value = false;
  }
}

function handleSeasonChange(year: number) {
  if (activeSeason.value === year) return;
  activeSeason.value = year;
  router.replace({
    query: {
      ...route.query,
      season: year.toString(),
    },
  });
  loadDraft(year);
}

// Watch URL query for browser navigation
watch(
  () => route.query.season,
  (newSeason) => {
    const parsed = parseSeasonQuery(newSeason);
    if (parsed && parsed !== activeSeason.value) {
      activeSeason.value = parsed;
      loadDraft(parsed);
    }
  }
);

onMounted(() => {
  loadDraft(activeSeason.value);
});

const availableSeasons = computed(() => {
  return draftResponse.value?.available_seasons || [];
});

const isFuture = computed(() => {
  return Boolean(draftResponse.value?.is_future_draft);
});
</script>

<template>
  <div class="space-y-4">
    <!-- Top Stadium Editorial Header -->
    <header class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800/80">
      <div class="space-y-1">
        <div class="flex items-center gap-2">
          <span class="w-1.5 h-4 rounded-full bg-emerald-500 shrink-0"></span>
          <h1 class="text-base sm:text-lg font-black text-white tracking-tight uppercase">
            Draft Central
          </h1>
          <span
            v-if="isFuture"
            class="text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded bg-slate-900 text-slate-300 border border-slate-700"
          >
            Traded Capital
          </span>
          <span
            v-else
            class="text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded bg-slate-900 text-slate-400 border border-slate-800"
          >
            Official Board
          </span>
        </div>
        <p class="text-xs text-slate-400">
          {{ isFuture ? 'Future draft capital, traded pick assets & 16-man roster balance' : 'Complete 192-pick draft board with player headshots & keeper selections' }}
        </p>
      </div>

      <!-- Athletic Season Selector Pills -->
      <div
        v-if="availableSeasons.length > 0"
        class="flex items-center gap-1.5 overflow-x-auto py-1 no-scrollbar select-none"
      >
        <button
          v-for="year in availableSeasons"
          :key="year"
          type="button"
          class="px-3 py-1.5 rounded-xl text-xs font-mono font-bold transition-all border shrink-0 flex items-center gap-1.5 cursor-pointer min-h-[38px]"
          :class="
            activeSeason === year
              ? 'bg-emerald-500 text-slate-950 border-emerald-400 shadow-sm'
              : 'bg-slate-900 text-slate-400 hover:text-white border-slate-800 hover:border-slate-700'
          "
          @click="handleSeasonChange(year)"
        >
          <span>{{ year }}</span>
          <span
            v-if="year >= 2027"
            class="text-[9px] uppercase font-sans font-black px-1.5 py-0.2 rounded"
            :class="activeSeason === year ? 'bg-slate-950/20 text-slate-950' : 'bg-slate-800 text-slate-300 border border-slate-700'"
          >
            Future
          </span>
        </button>
      </div>
    </header>

    <!-- Loading State -->
    <div v-if="loading" class="py-16">
      <LoadingState message="Loading draft records..." variant="spinner" />
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="py-12">
      <EmptyState
        title="Could Not Load Draft"
        :description="error"
        :is-error="true"
        action-text="Retry"
        @action="loadDraft(activeSeason)"
      />
    </div>

    <!-- Active Draft Content -->
    <div v-else-if="draftResponse">
      <!-- 1. Future Draft View (Traded Picks & 16-Roster Balance) -->
      <FutureDraftBoard
        v-if="isFuture && draftResponse.future_draft"
        :draft-data="draftResponse.future_draft"
      />

      <!-- 2. Historical Draft Board View (2026, 2025) -->
      <HistoricalDraftBoard
        v-else-if="!isFuture && draftResponse.historical_draft"
        :draft-data="draftResponse.historical_draft"
      />

      <!-- Fallback when no draft data returned -->
      <div v-else class="py-16 text-center text-slate-500 text-xs font-mono">
        No draft information found for {{ activeSeason }}.
      </div>
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
