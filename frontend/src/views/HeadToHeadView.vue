<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { fetchHeadToHead } from '@/api/client';
import type { HeadToHeadResponse, H2HManagerRef } from '@/types/api';
import RivalryMatrix from '@/components/h2h/RivalryMatrix.vue';
import TaleOfTheTape from '@/components/h2h/TaleOfTheTape.vue';
import SwipeDrawer from '@/components/ui/SwipeDrawer.vue';
import LoadingState from '@/components/ui/LoadingState.vue';
import EmptyState from '@/components/ui/EmptyState.vue';
import {
  Swords,
  Grid3x3,
  ArrowLeftRight,
  Info,
  Maximize2,
  RefreshCw,
  Users,
} from 'lucide-vue-next';

// State
const loading = ref(true);
const loadingPair = ref(false);
const error = ref<string | null>(null);
const h2hData = ref<HeadToHeadResponse | null>(null);

const activeTab = ref<'tape' | 'matrix'>('tape');
const selectedManagerA = ref<number | null>(null);
const selectedManagerB = ref<number | null>(null);
const isDrawerOpen = ref(false);

// Managers available
const managers = computed<H2HManagerRef[]>(() => {
  return h2hData.value?.managers ?? [];
});

// Dropdown options for Manager B (excluding Manager A)
const managerBOptions = computed<H2HManagerRef[]>(() => {
  return managers.value.filter((m) => m.manager_id !== selectedManagerA.value);
});

// Drawer Subtitle
const drawerSubtitle = computed(() => {
  if (!h2hData.value?.pair_detail) return undefined;
  return `${h2hData.value.pair_detail.manager_a.team_name} (${h2hData.value.pair_detail.manager_a.display_name}) vs ${h2hData.value.pair_detail.manager_b.team_name} (${h2hData.value.pair_detail.manager_b.display_name})`;
});

// Initial Data Fetch
async function loadInitialData() {
  loading.value = true;
  error.value = null;

  try {
    const data = await fetchHeadToHead();
    h2hData.value = data;

    if (data.pair_detail) {
      selectedManagerA.value = data.pair_detail.manager_a.manager_id;
      selectedManagerB.value = data.pair_detail.manager_b.manager_id;
    } else if (data.managers.length >= 2) {
      selectedManagerA.value = data.managers[0].manager_id;
      selectedManagerB.value = data.managers[1].manager_id;
      // Fetch pair detail for default pair
      await loadPairDetail(selectedManagerA.value, selectedManagerB.value);
    }
  } catch (err: unknown) {
    if (err instanceof Error) {
      error.value = err.message;
    } else {
      error.value = 'Failed to load Head-to-Head data';
    }
    console.error('Error loading head-to-head records:', err);
  } finally {
    loading.value = false;
  }
}

// Pair Detail Fetch
async function loadPairDetail(managerAId: number, managerBId: number) {
  loadingPair.value = true;
  try {
    const updated = await fetchHeadToHead(managerAId, managerBId);
    // Keep updated matrix & managers, update pair_detail
    h2hData.value = updated;
    selectedManagerA.value = managerAId;
    selectedManagerB.value = managerBId;
  } catch (err: unknown) {
    console.error('Error loading pair detail:', err);
  } finally {
    loadingPair.value = false;
  }
}

// Handle Selector Changes
function onManagerAChange(e: Event) {
  const target = e.target as HTMLSelectElement;
  const newA = Number(target.value);
  if (!newA) return;

  selectedManagerA.value = newA;

  // If Manager B is now the same as Manager A, pick the first other manager
  if (selectedManagerB.value === newA) {
    const fallbackB = managers.value.find((m) => m.manager_id !== newA);
    if (fallbackB) {
      selectedManagerB.value = fallbackB.manager_id;
    }
  }

  if (selectedManagerA.value && selectedManagerB.value) {
    loadPairDetail(selectedManagerA.value, selectedManagerB.value);
  }
}

function onManagerBChange(e: Event) {
  const target = e.target as HTMLSelectElement;
  const newB = Number(target.value);
  if (!newB) return;

  selectedManagerB.value = newB;

  if (selectedManagerA.value && selectedManagerB.value) {
    loadPairDetail(selectedManagerA.value, selectedManagerB.value);
  }
}

// Swap Managers Perspective
function swapManagers() {
  if (!selectedManagerA.value || !selectedManagerB.value) return;
  const tempA = selectedManagerA.value;
  const tempB = selectedManagerB.value;
  selectedManagerA.value = tempB;
  selectedManagerB.value = tempA;

  loadPairDetail(selectedManagerA.value, selectedManagerB.value);
}

// Handle Matrix Cell Tap
async function onSelectMatrixPair(managerAId: number, managerBId: number) {
  selectedManagerA.value = managerAId;
  selectedManagerB.value = managerBId;

  // Open drawer immediately so user gets feedback
  isDrawerOpen.value = true;

  // Load the pair detail
  await loadPairDetail(managerAId, managerBId);
}

// Switch from drawer to full view
function openInFullView() {
  isDrawerOpen.value = false;
  activeTab.value = 'tape';
}

onMounted(() => {
  loadInitialData();
});
</script>

<template>
  <div class="space-y-4 pb-20">
    <!-- View Header Banner -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
      <div>
        <h2 class="text-xl font-black uppercase tracking-tight text-slate-100 flex items-center gap-2">
          <Swords class="w-5 h-5 text-rose-400" />
          <span>Head-to-Head Rivalries</span>
        </h2>
        <p class="text-xs text-slate-400 mt-0.5">
          Career Records, Rivalry Matrix & Tale of the Tape across {{ managers.length }} Managers
        </p>
      </div>

      <!-- Tab Switcher Pills -->
      <div class="flex items-center p-1 rounded-xl bg-slate-900 border border-slate-800 self-start sm:self-auto shrink-0 shadow-inner">
        <button
          type="button"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all"
          :class="[
            activeTab === 'tape'
              ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40 shadow-sm'
              : 'text-slate-400 hover:text-slate-200',
          ]"
          @click="activeTab = 'tape'"
        >
          <Swords class="w-3.5 h-3.5" />
          <span>Tale of the Tape</span>
        </button>

        <button
          type="button"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all"
          :class="[
            activeTab === 'matrix'
              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm'
              : 'text-slate-400 hover:text-slate-200',
          ]"
          @click="activeTab = 'matrix'"
        >
          <Grid3x3 class="w-3.5 h-3.5" />
          <span>Win-Rate Matrix</span>
        </button>
      </div>
    </div>

    <!-- Mandatory Note Reminder Banner (Engineering Guardrail #4) -->
    <div
      class="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800 flex items-start gap-2.5 text-xs text-slate-300 shadow-sm"
    >
      <Info class="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
      <div class="leading-relaxed">
        <strong class="text-slate-100 font-semibold">Matchup Accounting Rule:</strong>
        Career Head-to-Head strictly counts
        <span class="text-emerald-400 font-mono font-medium">REGULAR</span> season and Championship Bracket
        (<span class="text-amber-400 font-mono font-medium">WINNERS_BRACKET</span>) games, excluding consolation and toilet bowl matchups.
      </div>
    </div>

    <!-- Loading State -->
    <LoadingState
      v-if="loading"
      message="Loading Career Rivalry History..."
      variant="cards"
      :rows="3"
    />

    <!-- Error State -->
    <EmptyState
      v-else-if="error"
      title="Failed to Load Head-to-Head Records"
      :description="error"
      :is-error="true"
      action-text="Retry"
      @action="loadInitialData"
    />

    <!-- Main Content Body -->
    <div v-else-if="h2hData" class="space-y-4">
      <!-- 1-on-1 Rivalry Selector Bar (Always accessible on Tale of the Tape tab) -->
      <div
        v-if="activeTab === 'tape'"
        class="stadium-card rounded-2xl p-3 sm:p-4 border border-slate-800 space-y-3"
      >
        <div class="flex items-center justify-between">
          <span class="text-[11px] font-extrabold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <Users class="w-3.5 h-3.5 text-slate-500" />
            <span>Select Rivalry Matchup</span>
          </span>
          <span v-if="loadingPair" class="text-[11px] text-emerald-400 font-mono flex items-center gap-1 animate-pulse">
            <RefreshCw class="w-3 h-3 animate-spin" />
            <span>Updating Tale...</span>
          </span>
        </div>

        <div class="flex items-center gap-2 sm:gap-3">
          <!-- Manager A Selector -->
          <div class="flex-1 min-w-0">
            <label class="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1 truncate">
              Manager A
            </label>
            <div class="relative">
              <select
                :value="selectedManagerA"
                class="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-3 py-2 text-xs sm:text-sm font-semibold text-slate-100 focus:outline-none focus:border-emerald-500 transition-colors truncate"
                @change="onManagerAChange"
              >
                <option
                  v-for="mgr in managers"
                  :key="mgr.manager_id"
                  :value="mgr.manager_id"
                >
                  {{ mgr.team_name }} ({{ mgr.display_name }})
                </option>
              </select>
            </div>
          </div>

          <!-- Swap Perspective Button -->
          <button
            type="button"
            class="mt-4 p-2.5 rounded-xl bg-slate-800/80 hover:bg-slate-700 border border-slate-700/60 text-slate-300 hover:text-white transition-all active:scale-95 shrink-0 shadow-sm"
            title="Swap Perspective"
            aria-label="Swap Managers"
            @click="swapManagers"
          >
            <ArrowLeftRight class="w-4 h-4" />
          </button>

          <!-- Manager B Selector -->
          <div class="flex-1 min-w-0">
            <label class="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1 truncate">
              Manager B
            </label>
            <div class="relative">
              <select
                :value="selectedManagerB"
                class="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-3 py-2 text-xs sm:text-sm font-semibold text-slate-100 focus:outline-none focus:border-emerald-500 transition-colors truncate"
                @change="onManagerBChange"
              >
                <option
                  v-for="mgr in managerBOptions"
                  :key="mgr.manager_id"
                  :value="mgr.manager_id"
                >
                  {{ mgr.team_name }} ({{ mgr.display_name }})
                </option>
              </select>
            </div>
          </div>
        </div>
      </div>

      <!-- Tab View: 1-on-1 Tale of the Tape -->
      <div v-if="activeTab === 'tape'" class="space-y-4">
        <TaleOfTheTape
          v-if="h2hData.pair_detail"
          :pair-detail="h2hData.pair_detail"
          :loading="loadingPair"
        />

        <EmptyState
          v-else
          title="Select Two Managers"
          description="Choose Manager A and Manager B above to view their head-to-head rivalry history and Tale of the Tape breakdown."
        />
      </div>

      <!-- Tab View: N×N Win-Rate Matrix -->
      <div v-else-if="activeTab === 'matrix'">
        <RivalryMatrix
          :managers="h2hData.managers"
          :matrix="h2hData.matrix"
          :selected-manager-a="selectedManagerA"
          :selected-manager-b="selectedManagerB"
          @select-pair="onSelectMatrixPair"
        />
      </div>
    </div>

    <!-- Mobile Bottom Sheet / SwipeDrawer for Quick Tale of the Tape Inspection -->
    <SwipeDrawer
      v-model="isDrawerOpen"
      title="Rivalry Tale of the Tape"
      :subtitle="drawerSubtitle"
      max-height="max-h-[90vh]"
    >
      <div v-if="loadingPair" class="py-8">
        <LoadingState message="Fetching Rivalry Tale..." variant="spinner" />
      </div>

      <div v-else-if="h2hData?.pair_detail" class="space-y-4">
        <!-- Quick Action: Switch to Full View -->
        <div class="flex justify-end">
          <button
            type="button"
            class="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold bg-rose-500/15 text-rose-300 border border-rose-500/30 hover:bg-rose-500/25 transition-colors"
            @click="openInFullView"
          >
            <Maximize2 class="w-3.5 h-3.5" />
            <span>Open in Full View</span>
          </button>
        </div>

        <!-- Inline Tale of the Tape -->
        <TaleOfTheTape :pair-detail="h2hData.pair_detail" />
      </div>

      <template #footer>
        <div class="flex items-center justify-between gap-2">
          <button
            type="button"
            class="px-4 py-2 rounded-xl text-xs font-semibold text-slate-300 bg-slate-800 hover:bg-slate-700 transition-colors"
            @click="isDrawerOpen = false"
          >
            Close
          </button>
          <button
            type="button"
            class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold text-slate-950 bg-emerald-500 hover:bg-emerald-400 transition-colors shadow-md"
            @click="openInFullView"
          >
            <Swords class="w-3.5 h-3.5" />
            <span>Full Tale of the Tape</span>
          </button>
        </div>
      </template>
    </SwipeDrawer>
  </div>
</template>
