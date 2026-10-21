<script setup lang="ts">
import { ref, computed } from 'vue';
import type { ActiveTrader } from '@/types/api';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import { TrendingUp, TrendingDown, ArrowDownLeft, ArrowUpRight, Flame } from 'lucide-vue-next';

const props = defineProps<{
  traders: ActiveTrader[];
}>();

type SortKey = 'trades' | 'net_points' | 'acquired';
const sortBy = ref<SortKey>('trades');

const sortedTraders = computed(() => {
  const list = [...props.traders];
  if (sortBy.value === 'trades') {
    return list.sort((a, b) => b.total_trades - a.total_trades || b.net_starter_points_gained - a.net_starter_points_gained);
  } else if (sortBy.value === 'net_points') {
    return list.sort((a, b) => b.net_starter_points_gained - a.net_starter_points_gained || b.total_trades - a.total_trades);
  } else if (sortBy.value === 'acquired') {
    return list.sort((a, b) => b.players_acquired - a.players_acquired);
  }
  return list;
});
</script>

<template>
  <div class="space-y-3">
    <!-- Header row with Sort Controls -->
    <div class="flex items-center justify-between gap-2 flex-wrap">
      <div class="flex items-center gap-2">
        <Flame class="w-4 h-4 text-amber-400" />
        <h3 class="text-sm font-bold uppercase tracking-tight text-slate-200">
          Most Active Traders & Realized ROI
        </h3>
      </div>

      <!-- Sort Toggle Pills -->
      <div class="inline-flex items-center rounded-lg bg-slate-900 border border-slate-800 p-0.5 text-xs">
        <button
          type="button"
          class="px-2.5 py-1 rounded-md font-semibold transition-colors"
          :class="sortBy === 'trades' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'"
          @click="sortBy = 'trades'"
        >
          Volume
        </button>
        <button
          type="button"
          class="px-2.5 py-1 rounded-md font-semibold transition-colors"
          :class="sortBy === 'net_points' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'"
          @click="sortBy = 'net_points'"
        >
          Net ROI
        </button>
        <button
          type="button"
          class="px-2.5 py-1 rounded-md font-semibold transition-colors"
          :class="sortBy === 'acquired' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'"
          @click="sortBy = 'acquired'"
        >
          Acquired
        </button>
      </div>
    </div>

    <!-- Active Traders Cards Grid / List -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
      <div
        v-for="(trader, idx) in sortedTraders"
        :key="trader.manager_id"
        class="stadium-card rounded-xl p-3 border border-slate-800 hover:border-slate-700 transition-all flex flex-col justify-between gap-2.5"
      >
        <!-- Manager & Trade Volume Header -->
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-center gap-2 min-w-0">
            <span class="w-5 h-5 rounded-md bg-slate-800 text-[11px] font-bold font-mono text-slate-400 flex items-center justify-center shrink-0">
              {{ idx + 1 }}
            </span>
            <TeamAvatar
              :src="trader.avatar_url"
              :name="trader.team_name || trader.display_name"
              size="sm"
            />
            <div class="min-w-0">
              <div class="font-bold text-xs text-slate-100 truncate" :title="trader.team_name || trader.display_name">
                {{ trader.team_name || trader.display_name }}
              </div>
              <div class="text-[10px] text-slate-400 truncate" :title="trader.display_name">
                {{ trader.display_name }}
              </div>
            </div>
          </div>

          <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-mono font-bold bg-slate-800/80 text-slate-300 border border-slate-700/60 shrink-0">
            {{ trader.total_trades }} {{ trader.total_trades === 1 ? 'trade' : 'trades' }}
          </span>
        </div>

        <!-- Metric Details Row -->
        <div class="grid grid-cols-3 gap-2 pt-1 border-t border-slate-800/60 text-center">
          <!-- Players Acquired -->
          <div class="bg-slate-900/60 rounded-lg py-1.5 px-1 border border-slate-800/60">
            <div class="text-[10px] text-slate-400 flex items-center justify-center gap-0.5 font-medium">
              <ArrowDownLeft class="w-3 h-3 text-emerald-400" />
              <span>In</span>
            </div>
            <div class="text-xs font-mono font-bold text-slate-200 mt-0.5">
              +{{ trader.players_acquired }}
            </div>
          </div>

          <!-- Players Sent Away -->
          <div class="bg-slate-900/60 rounded-lg py-1.5 px-1 border border-slate-800/60">
            <div class="text-[10px] text-slate-400 flex items-center justify-center gap-0.5 font-medium">
              <ArrowUpRight class="w-3 h-3 text-rose-400" />
              <span>Out</span>
            </div>
            <div class="text-xs font-mono font-bold text-slate-200 mt-0.5">
              -{{ trader.players_traded_away }}
            </div>
          </div>

          <!-- Net Starter Points Gained -->
          <div
            class="rounded-lg py-1.5 px-1 border flex flex-col justify-center"
            :class="
              trader.net_starter_points_gained > 0
                ? 'bg-emerald-950/30 border-emerald-500/30 text-emerald-300'
                : trader.net_starter_points_gained < 0
                  ? 'bg-rose-950/30 border-rose-500/30 text-rose-300'
                  : 'bg-slate-900/60 border-slate-800/60 text-slate-400'
            "
          >
            <div class="text-[10px] font-medium flex items-center justify-center gap-0.5">
              <TrendingUp v-if="trader.net_starter_points_gained > 0" class="w-3 h-3 text-emerald-400" />
              <TrendingDown v-else-if="trader.net_starter_points_gained < 0" class="w-3 h-3 text-rose-400" />
              <span>Net ROI</span>
            </div>
            <div class="text-xs font-mono font-bold mt-0.5">
              {{ trader.net_starter_points_gained > 0 ? '+' : '' }}{{ trader.net_starter_points_gained.toFixed(1) }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
