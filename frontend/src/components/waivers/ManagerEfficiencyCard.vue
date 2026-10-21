<script setup lang="ts">
import { computed } from 'vue';
import type { ManagerEfficiency } from '@/types/api';
import { DollarSign, CheckCircle2, XCircle, TrendingUp, Sparkles, UserPlus, UserMinus } from 'lucide-vue-next';

const props = defineProps<{
  manager: ManagerEfficiency;
  rank?: number;
}>();

const spentPercent = computed(() => {
  if (props.manager.faab_budget <= 0) return 0;
  return Math.min(100, Math.max(0, (props.manager.faab_spent / props.manager.faab_budget) * 100));
});

const successRatePercent = computed(() => {
  return (props.manager.waiver_success_rate * 100).toFixed(0);
});
</script>

<template>
  <div
    class="stadium-card rounded-2xl p-4 border border-slate-800 hover:border-slate-700/80 transition-all flex flex-col justify-between gap-3 shadow-md"
  >
    <!-- Header: Manager Identity & Points / FAAB Dollar ROI Badge -->
    <div class="flex items-start justify-between gap-2">
      <div class="flex items-center gap-2.5 min-w-0">
        <span
          v-if="rank != null"
          class="w-6 h-6 rounded-lg text-xs font-mono font-bold flex items-center justify-center shrink-0"
          :class="
            rank === 1
              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
              : rank === 2
                ? 'bg-slate-300/20 text-slate-200 border border-slate-300/30'
                : rank === 3
                  ? 'bg-amber-700/20 text-amber-500 border border-amber-700/30'
                  : 'bg-slate-800 text-slate-400 border border-slate-700/60'
          "
        >
          #{{ rank }}
        </span>
        <div class="min-w-0">
          <div class="font-bold text-sm text-slate-100 truncate" :title="manager.display_name">
            {{ manager.display_name }}
          </div>
          <div class="text-xs text-slate-400 truncate mt-0.5" :title="manager.team_name">
            {{ manager.team_name }}
          </div>
        </div>
      </div>

      <!-- FAAB ROI Badge (pts per $1 spent) -->
      <div class="shrink-0 text-right">
        <div
          class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-mono font-bold border"
          :class="
            manager.points_per_faab_dollar != null && manager.points_per_faab_dollar >= 2.0
              ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40 stadium-glow-emerald'
              : manager.points_per_faab_dollar != null && manager.points_per_faab_dollar > 0
                ? 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30'
                : 'bg-slate-800 text-slate-400 border-slate-700'
          "
        >
          <Sparkles class="w-3 h-3 text-emerald-400" />
          <span>{{ manager.points_per_faab_dollar != null ? `${manager.points_per_faab_dollar.toFixed(2)} pts/$` : 'N/A' }}</span>
        </div>
        <div class="text-[10px] text-slate-500 font-medium mt-0.5">
          FAAB Value ROI
        </div>
      </div>
    </div>

    <!-- FAAB Budget Utilization Bar -->
    <div class="bg-slate-900/80 rounded-xl p-3 border border-slate-800/80 space-y-2">
      <div class="flex items-center justify-between text-xs font-mono">
        <span class="text-slate-300 flex items-center gap-1 font-semibold">
          <DollarSign class="w-3.5 h-3.5 text-amber-400" />
          <span>${{ manager.faab_spent }} Spent / ${{ manager.faab_budget }} Budget</span>
        </span>
        <span class="text-emerald-400 font-bold">
          ${{ manager.faab_remaining }} left
        </span>
      </div>

      <!-- Visual Budget Bar -->
      <div class="w-full h-2 rounded-full bg-slate-800 overflow-hidden border border-slate-700/60">
        <div
          class="h-full rounded-full transition-all duration-500"
          :class="spentPercent >= 90 ? 'bg-rose-500' : spentPercent >= 60 ? 'bg-amber-500' : 'bg-emerald-500'"
          :style="{ width: `${spentPercent}%` }"
        ></div>
      </div>
    </div>

    <!-- Key Metrics Grid -->
    <div class="grid grid-cols-4 gap-2 text-center text-xs">
      <!-- Waiver Success Rate -->
      <div class="bg-slate-900/60 rounded-xl p-2 border border-slate-800/60">
        <div class="text-[10px] text-slate-400 font-medium">Success Rate</div>
        <div class="font-mono font-bold text-slate-100 mt-0.5 text-sm">
          {{ successRatePercent }}%
        </div>
        <div class="text-[10px] text-slate-500 flex items-center justify-center gap-1 mt-0.5">
          <span class="text-emerald-400 flex items-center gap-0.5">
            <CheckCircle2 class="w-2.5 h-2.5" />{{ manager.executed_waivers }}
          </span>
          <span>/</span>
          <span class="text-rose-400 flex items-center gap-0.5">
            <XCircle class="w-2.5 h-2.5" />{{ manager.failed_waivers }}
          </span>
        </div>
      </div>

      <!-- Realized Starter Points -->
      <div class="bg-slate-900/60 rounded-xl p-2 border border-slate-800/60">
        <div class="text-[10px] text-slate-400 font-medium">Starter Pts</div>
        <div class="font-mono font-bold text-emerald-400 mt-0.5 text-sm flex items-center justify-center gap-0.5">
          <TrendingUp class="w-3 h-3 text-emerald-400" />
          <span>{{ manager.total_starter_points_from_waivers.toFixed(1) }}</span>
        </div>
        <div class="text-[10px] text-slate-500 mt-0.5">
          from claims
        </div>
      </div>

      <!-- Free Agent Adds -->
      <div class="bg-slate-900/60 rounded-xl p-2 border border-slate-800/60">
        <div class="text-[10px] text-slate-400 font-medium">FA Adds</div>
        <div class="font-mono font-bold text-sky-400 mt-0.5 text-sm flex items-center justify-center gap-0.5">
          <UserPlus class="w-3 h-3 text-sky-400" />
          <span>{{ manager.free_agent_adds }}</span>
        </div>
        <div class="text-[10px] text-slate-500 mt-0.5">
          free pickups
        </div>
      </div>

      <!-- Drops -->
      <div class="bg-slate-900/60 rounded-xl p-2 border border-slate-800/60">
        <div class="text-[10px] text-slate-400 font-medium">Drops</div>
        <div class="font-mono font-bold text-slate-300 mt-0.5 text-sm flex items-center justify-center gap-0.5">
          <UserMinus class="w-3 h-3 text-slate-400" />
          <span>{{ manager.drops }}</span>
        </div>
        <div class="text-[10px] text-slate-500 mt-0.5">
          churned
        </div>
      </div>
    </div>
  </div>
</template>
