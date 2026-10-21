<script setup lang="ts">
import { computed } from 'vue';
import type { EarningsLeaderboardEntry, ManagerSeasonBreakdown } from '@/types/api';
import SwipeDrawer from '@/components/ui/SwipeDrawer.vue';
import {
  Trophy,
  Medal,
  Calendar,
  Landmark,
} from 'lucide-vue-next';

const props = defineProps<{
  modelValue: boolean;
  entry: EarningsLeaderboardEntry | null;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void;
}>();

const title = computed(() => props.entry?.display_name ?? 'Manager Earnings');
const subtitle = computed(() => {
  if (!props.entry) return '';
  return `Career Ledger · ${props.entry.seasons_played} ${props.entry.seasons_played === 1 ? 'Season' : 'Seasons'}`;
});

// Sorted seasons (most recent first)
const sortedBreakdown = computed<ManagerSeasonBreakdown[]>(() => {
  if (!props.entry?.season_breakdown) return [];
  return [...props.entry.season_breakdown].sort((a, b) => b.season_year - a.season_year);
});

function getTrophyBadge(item: ManagerSeasonBreakdown) {
  if (item.trophy === 'CHAMPION' || item.final_standing === 1) {
    return {
      label: 'Champion',
      icon: Trophy,
      class: 'bg-amber-500/20 text-amber-300 border-amber-500/40 ring-1 ring-amber-500/30',
    };
  }
  if (item.trophy === 'RUNNER_UP' || item.final_standing === 2) {
    return {
      label: 'Runner-Up',
      icon: Medal,
      class: 'bg-slate-400/20 text-slate-200 border-slate-400/40',
    };
  }
  if (item.trophy === 'THIRD_PLACE' || item.final_standing === 3) {
    return {
      label: '3rd Place',
      icon: Medal,
      class: 'bg-amber-800/20 text-amber-500 border-amber-800/40',
    };
  }
  if (item.final_standing) {
    return {
      label: `#${item.final_standing} Final`,
      icon: null,
      class: 'bg-slate-800 text-slate-400 border-slate-700/60',
    };
  }
  return null;
}
</script>

<template>
  <SwipeDrawer
    :model-value="modelValue"
    :title="title"
    :subtitle="subtitle"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-if="entry" class="space-y-4 pb-4">
      <!-- Top Overview KPI Strip -->
      <div class="stadium-card rounded-2xl p-4 border border-slate-800 space-y-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <Landmark class="w-4 h-4 text-emerald-400" />
            <h4 class="text-xs uppercase font-bold tracking-wider text-slate-300">
              Career Financial Summary
            </h4>
          </div>

          <span
            class="text-xs font-mono px-2.5 py-0.5 rounded font-black bg-emerald-950/90 text-emerald-300 border border-emerald-800/80 shadow-sm"
          >
            ${{ entry.total_earnings.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }} Net
          </span>
        </div>

        <div class="grid grid-cols-3 gap-2 pt-1">
          <div class="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800/80">
            <span class="text-[10px] text-slate-400 uppercase font-semibold">Podium Cash</span>
            <div class="text-sm sm:text-base font-bold font-mono text-amber-400 tabular-nums">
              ${{ entry.podium_earnings.toFixed(2) }}
            </div>
            <span class="text-[10px] text-slate-500 font-mono">1st / 2nd / 3rd</span>
          </div>

          <div class="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800/80">
            <span class="text-[10px] text-slate-400 uppercase font-semibold">Weekly Wins Cash</span>
            <div class="text-sm sm:text-base font-bold font-mono text-emerald-400 tabular-nums">
              ${{ entry.weekly_earnings.toFixed(2) }}
            </div>
            <span class="text-[10px] text-slate-500 font-mono">
              {{ entry.weekly_wins_count }} {{ entry.weekly_wins_count === 1 ? 'Win' : 'Wins' }}
              <span v-if="entry.weekly_ties_count > 0">, {{ entry.weekly_ties_count }}T</span>
            </span>
          </div>

          <div class="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800/80">
            <span class="text-[10px] text-slate-400 uppercase font-semibold">Trophies</span>
            <div class="text-sm sm:text-base font-bold font-mono text-slate-200 tabular-nums">
              {{ entry.championships + entry.runner_ups + entry.third_places }}
            </div>
            <span class="text-[10px] text-slate-500 font-mono">{{ entry.championships }} 🏆 Titles</span>
          </div>
        </div>
      </div>

      <!-- Season Breakdown Title -->
      <div class="flex items-center justify-between px-1">
        <h4 class="text-xs uppercase font-bold tracking-wider text-slate-300 flex items-center gap-1.5">
          <Calendar class="w-3.5 h-3.5 text-emerald-400" />
          <span>Season-by-Season Breakdown</span>
        </h4>
        <span class="text-[11px] font-mono text-slate-500">
          {{ sortedBreakdown.length }} {{ sortedBreakdown.length === 1 ? 'Season' : 'Seasons' }}
        </span>
      </div>

      <!-- Season Breakdown Cards -->
      <div class="space-y-2">
        <div
          v-for="item in sortedBreakdown"
          :key="item.season_year"
          class="stadium-card rounded-xl p-3 border border-slate-800/80 space-y-2 hover:border-slate-700/80 transition-colors"
        >
          <!-- Season Year & Team Name -->
          <div class="flex items-center justify-between gap-2">
            <div class="flex items-center gap-2 min-w-0">
              <span class="text-xs font-black font-mono text-slate-200 bg-slate-800 px-2 py-0.5 rounded">
                {{ item.season_year }}
              </span>
              <span class="text-xs sm:text-sm font-bold text-slate-100 truncate" :title="item.team_name">
                {{ item.team_name }}
              </span>
            </div>

            <!-- Trophy or Final standing badge -->
            <span
              v-if="getTrophyBadge(item)"
              class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold border shrink-0"
              :class="getTrophyBadge(item)?.class"
            >
              <component
                :is="getTrophyBadge(item)?.icon"
                v-if="getTrophyBadge(item)?.icon"
                class="w-3 h-3 shrink-0"
              />
              <span>{{ getTrophyBadge(item)?.label }}</span>
            </span>
          </div>

          <!-- Earnings Breakdown for this season -->
          <div class="pt-2 border-t border-slate-800/60 grid grid-cols-3 gap-2 text-xs">
            <!-- Weekly Wins -->
            <div>
              <span class="text-[10px] uppercase font-semibold text-slate-400 block">Weekly Cash</span>
              <div class="font-mono text-emerald-400 font-semibold tabular-nums">
                ${{ item.weekly_earnings.toFixed(2) }}
              </div>
              <span class="text-[10px] text-slate-500 font-mono">
                {{ item.weekly_wins }}W<span v-if="item.weekly_ties > 0">, {{ item.weekly_ties }}T</span>
              </span>
            </div>

            <!-- Podium Cash -->
            <div>
              <span class="text-[10px] uppercase font-semibold text-slate-400 block">Podium Cash</span>
              <div class="font-mono text-amber-400 font-semibold tabular-nums">
                ${{ item.podium_earnings.toFixed(2) }}
              </div>
              <span class="text-[10px] text-slate-500 font-mono">
                {{ item.final_standing ? `Finish #${item.final_standing}` : 'No Podium' }}
              </span>
            </div>

            <!-- Total Season Earnings -->
            <div class="text-right">
              <span class="text-[10px] uppercase font-semibold text-slate-400 block">Season Total</span>
              <div
                class="font-mono font-bold tabular-nums text-sm"
                :class="item.total_earnings > 0 ? 'text-emerald-300' : 'text-slate-400'"
              >
                ${{ item.total_earnings.toFixed(2) }}
              </div>
              <span class="text-[10px] text-slate-500 font-mono">Net Prize</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </SwipeDrawer>
</template>
