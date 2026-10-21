<script setup lang="ts">
import type { TopTradePartner } from '@/types/api';
import { ArrowLeftRight, Users } from 'lucide-vue-next';

defineProps<{
  partner: TopTradePartner;
  rank: number;
}>();
</script>

<template>
  <div
    class="stadium-card rounded-xl p-3.5 border border-slate-800 hover:border-slate-700 transition-all flex flex-col justify-between gap-3 shadow-sm group"
  >
    <!-- Top row: Rank badge + Trade count pill -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2">
        <span
          class="w-6 h-6 rounded-lg text-xs font-black flex items-center justify-center font-mono"
          :class="
            rank === 1
              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm shadow-amber-950'
              : rank === 2
                ? 'bg-slate-300/20 text-slate-200 border border-slate-300/30'
                : rank === 3
                  ? 'bg-amber-700/20 text-amber-500 border border-amber-700/30'
                  : 'bg-slate-800 text-slate-400 border border-slate-700/50'
          "
        >
          #{{ rank }}
        </span>
        <span class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1">
          <Users class="w-3.5 h-3.5 text-indigo-400" />
          <span>Alliance</span>
        </span>
      </div>

      <div class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold font-mono bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">
        <ArrowLeftRight class="w-3 h-3 text-indigo-400" />
        <span>{{ partner.trade_count }} {{ partner.trade_count === 1 ? 'Trade' : 'Trades' }}</span>
      </div>
    </div>

    <!-- Manager Connection Display -->
    <div class="bg-slate-900/60 rounded-lg p-2.5 border border-slate-800/80 flex items-center justify-between gap-2">
      <!-- Manager A -->
      <div class="flex items-center gap-2 min-w-0 flex-1">
        <div class="w-7 h-7 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center shrink-0 text-slate-300 font-bold text-xs">
          {{ partner.manager_a_name.charAt(0) }}
        </div>
        <span class="text-xs font-bold text-slate-200 truncate tracking-tight" :title="partner.manager_a_name">
          {{ partner.manager_a_name }}
        </span>
      </div>

      <!-- Connecting Icon -->
      <div class="flex items-center justify-center w-6 h-6 rounded-full bg-slate-800/90 text-indigo-400 shrink-0">
        <ArrowLeftRight class="w-3 h-3" />
      </div>

      <!-- Manager B -->
      <div class="flex items-center gap-2 min-w-0 flex-1 justify-end text-right">
        <span class="text-xs font-bold text-slate-200 truncate tracking-tight" :title="partner.manager_b_name">
          {{ partner.manager_b_name }}
        </span>
        <div class="w-7 h-7 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center shrink-0 text-slate-300 font-bold text-xs">
          {{ partner.manager_b_name.charAt(0) }}
        </div>
      </div>
    </div>
  </div>
</template>
