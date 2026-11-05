<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { useLeagueMeta } from '@/composables/useLeagueMeta';
import { fetchDrafts } from '@/api/client';
import type { DraftsResponse } from '@/types/api';
import LoadingState from '@/components/ui/LoadingState.vue';
import EmptyState from '@/components/ui/EmptyState.vue';
import FutureDraftBoard from '@/components/drafts/FutureDraftBoard.vue';
import HistoricalDraftBoard from '@/components/drafts/HistoricalDraftBoard.vue';

const route = useRoute();
const { meta, selectedSeason, setSelectedSeason } = useLeagueMeta();

const loading = ref<boolean>(true);
const error = ref<string | null>(null);
const draftResponse = ref<DraftsResponse | null>(null);

const currentSeasonYear = computed<number>(() => {
  return meta.value?.current_season ?? 2026;
});

const futureSeasonYear = computed<number>(() => {
  return currentSeasonYear.value + 1;
});

/**
 * True when the top-level global season selector is on the current active season (e.g. 2026)
 * or 'All Time' (null). In this state, we default to the Future Pick Trade Market view.
 */
const isCurrentSeasonContext = computed<boolean>(() => {
  return selectedSeason.value === null || selectedSeason.value === currentSeasonYear.value;
});

/**
 * Mode toggle when viewing the current season:
 * - 'market' (default): Shows upcoming draft pick trade market & team inventories (e.g. 2027 Picks)
 * - 'board': Shows the current season's completed draft board (e.g. 2026 Draft Results)
 */
const currentYearMode = ref<'market' | 'board'>('market');

function parseSeasonQuery(raw: unknown): number | null {
  if (typeof raw === 'string') {
    const parsed = parseInt(raw, 10);
    if (!isNaN(parsed) && parsed > 2000) return parsed;
  }
  return null;
}

async function loadDraft(seasonYear?: number | null) {
  loading.value = true;
  error.value = null;

  try {
    const data = await fetchDrafts(seasonYear);
    draftResponse.value = data;
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

function resolveTargetSeason(): number | null {
  if (isCurrentSeasonContext.value) {
    return currentYearMode.value === 'market' ? null : currentSeasonYear.value;
  }
  return selectedSeason.value;
}

function setCurrentYearMode(mode: 'market' | 'board') {
  if (currentYearMode.value === mode) return;
  currentYearMode.value = mode;
  loadDraft(resolveTargetSeason());
}

// React to the top-level global season dropdown in TopHeader.vue
watch(
  () => selectedSeason.value,
  () => {
    if (isCurrentSeasonContext.value) {
      // Always default to the Trade Market view when switching to the current year
      currentYearMode.value = 'market';
      loadDraft(null);
    } else {
      loadDraft(selectedSeason.value);
    }
  }
);

onMounted(() => {
  const querySeason = parseSeasonQuery(route.query.season);
  if (querySeason !== null) {
    if (querySeason >= futureSeasonYear.value) {
      currentYearMode.value = 'market';
      loadDraft(null);
      return;
    } else if (querySeason === currentSeasonYear.value) {
      currentYearMode.value = 'board';
      loadDraft(currentSeasonYear.value);
      return;
    } else {
      setSelectedSeason(querySeason);
      loadDraft(querySeason);
      return;
    }
  }
  loadDraft(resolveTargetSeason());
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
        <div class="flex items-center gap-2 flex-wrap">
          <span class="w-1.5 h-4 rounded-full bg-emerald-500 shrink-0"></span>
          <h1 class="text-base sm:text-lg font-black text-white tracking-tight uppercase">
            Draft Central
          </h1>
          <span
            v-if="isFuture"
            class="text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-500/40"
          >
            {{ futureSeasonYear }} Trade Market
          </span>
          <span
            v-else
            class="text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded bg-slate-900 text-slate-300 border border-slate-700"
          >
            {{ draftResponse?.selected_season || selectedSeason }} Official Board
          </span>
        </div>
        <p class="text-xs text-slate-400">
          {{
            isFuture
              ? `${currentSeasonYear} trade market status, ${futureSeasonYear} draft capital & team rosters by tier`
              : `Complete 192-pick ${draftResponse?.selected_season || selectedSeason} draft board with player headshots & keeper selections`
          }}
        </p>
      </div>

      <!-- Current-Season Mode Switcher (Only shown when Top Dropdown is on Current Year / All Time) -->
      <div
        v-if="isCurrentSeasonContext"
        class="inline-flex flex-wrap rounded-xl bg-slate-900 p-1 border border-slate-800/80 self-start sm:self-auto shrink-0 gap-1"
      >
        <button
          type="button"
          class="px-3 py-1.5 rounded-lg text-xs font-mono font-bold transition-all cursor-pointer min-h-[34px] flex items-center gap-1.5"
          :class="
            currentYearMode === 'market'
              ? 'bg-emerald-500 text-slate-950 shadow-sm font-black'
              : 'text-slate-400 hover:text-white'
          "
          @click="setCurrentYearMode('market')"
        >
          <span>{{ futureSeasonYear }} Pick Market</span>
        </button>

        <button
          type="button"
          class="px-3 py-1.5 rounded-lg text-xs font-mono font-bold transition-all cursor-pointer min-h-[34px] flex items-center gap-1.5"
          :class="
            currentYearMode === 'board'
              ? 'bg-emerald-500 text-slate-950 shadow-sm font-black'
              : 'text-slate-400 hover:text-white'
          "
          @click="setCurrentYearMode('board')"
        >
          <span>{{ currentSeasonYear }} Draft Board</span>
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
        @action="loadDraft(resolveTargetSeason())"
      />
    </div>

    <!-- Active Draft Content -->
    <div v-else-if="draftResponse">
      <!-- 1. Future Draft View (Traded Picks & Team Scouting) -->
      <FutureDraftBoard
        v-if="isFuture && draftResponse.future_draft"
        :draft-data="draftResponse.future_draft"
      />

      <!-- 2. Historical Draft Board View (2026, 2025, etc.) -->
      <HistoricalDraftBoard
        v-else-if="!isFuture && draftResponse.historical_draft && draftResponse.historical_draft.picks.length > 0"
        :draft-data="draftResponse.historical_draft"
      />

      <!-- Fallback when a legacy season has no draft picks archived -->
      <div
        v-else
        class="py-12 text-center bg-slate-900/40 border border-slate-800/80 rounded-2xl p-6 space-y-3"
      >
        <div class="text-sm font-bold text-slate-200">
          No Draft Board Archived for {{ draftResponse.selected_season }}
        </div>
        <p class="text-xs text-slate-400 font-mono max-w-md mx-auto">
          Draft board selections are available for modern seasons (2025–{{ currentSeasonYear }}), or switch back to {{ currentSeasonYear }} in the top bar to view the {{ futureSeasonYear }} Pick Market.
        </p>
        <button
          type="button"
          class="px-3.5 py-1.5 rounded-xl text-xs font-mono font-bold bg-emerald-500 text-slate-950 hover:bg-emerald-400 transition-colors cursor-pointer"
          @click="setSelectedSeason(currentSeasonYear)"
        >
          Back to {{ currentSeasonYear }} Season ({{ futureSeasonYear }} Pick Market)
        </button>
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
