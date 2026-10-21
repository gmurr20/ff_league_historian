<script setup lang="ts">
import { ref } from 'vue';
import type { BiddingWar } from '@/types/api';
import { Flame, Trophy, ChevronRight, XCircle } from 'lucide-vue-next';

defineProps<{
  war: BiddingWar;
}>();

const emit = defineEmits<{
  (e: 'select', war: BiddingWar): void;
}>();

const imgFailed = ref<boolean>(false);

function getPositionClass(pos: string): string {
  switch (pos?.toUpperCase()) {
    case 'QB':
      return 'bg-rose-500/20 text-rose-300 border-rose-500/40';
    case 'RB':
      return 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40';
    case 'WR':
      return 'bg-sky-500/20 text-sky-300 border-sky-500/40';
    case 'TE':
      return 'bg-amber-500/20 text-amber-300 border-amber-500/40';
    case 'K':
      return 'bg-purple-500/20 text-purple-300 border-purple-500/40';
    default:
      return 'bg-slate-700 text-slate-300 border-slate-600';
  }
}

function getFailureBadgeClass(reason: string): string {
  switch (reason?.toUpperCase()) {
    case 'OUTBID':
      return 'bg-rose-500/15 text-rose-300 border-rose-500/30';
    case 'INSUFFICIENT_FUNDS':
      return 'bg-amber-500/15 text-amber-300 border-amber-500/30';
    case 'ROSTER_LIMIT_EXCEEDED':
      return 'bg-purple-500/15 text-purple-300 border-purple-500/30';
    default:
      return 'bg-slate-800 text-slate-300 border-slate-700';
  }
}
</script>

<template>
  <div
    class="stadium-card rounded-2xl border border-slate-800 hover:border-slate-700 transition-all overflow-hidden shadow-lg"
  >
    <!-- Header: Player + Contest Details -->
    <div class="p-3.5 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between gap-3">
      <div class="flex items-center gap-3 min-w-0">
        <!-- Player Avatar / Headshot -->
        <div class="relative w-11 h-11 rounded-xl bg-slate-800 border border-slate-700 overflow-hidden shrink-0 flex items-center justify-center">
          <img
            v-if="war.player.headshot_url && !imgFailed"
            :src="war.player.headshot_url"
            :alt="war.player.full_name"
            class="w-full h-full object-cover"
            loading="lazy"
            @error="imgFailed = true"
          />
          <div
            v-else
            class="w-full h-full flex items-center justify-center font-bold text-xs font-mono"
            :class="getPositionClass(war.player.default_position)"
          >
            {{ war.player.default_position }}
          </div>
        </div>

        <!-- Player Name, Position & Pro Team -->
        <div class="min-w-0">
          <div class="flex items-center gap-1.5">
            <span class="font-bold text-sm text-slate-100 truncate" :title="war.player.full_name">
              {{ war.player.full_name }}
            </span>
          </div>
          <div class="flex items-center gap-1.5 mt-0.5">
            <span
              class="px-1.5 py-0.2 rounded text-[10px] font-mono font-bold border"
              :class="getPositionClass(war.player.default_position)"
            >
              {{ war.player.default_position }}
            </span>
            <span class="text-xs text-slate-400 font-semibold font-mono">
              {{ war.player.pro_team }}
            </span>
            <span v-if="war.week != null" class="text-slate-600">•</span>
            <span v-if="war.week != null" class="text-[11px] font-mono text-slate-400">
              Week {{ war.week }}
            </span>
          </div>
        </div>
      </div>

      <!-- Action Button / Receipt tag -->
      <button
        type="button"
        class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-bold text-amber-400 hover:text-amber-300 bg-amber-500/10 border border-amber-500/20 hover:bg-amber-500/20 transition-colors shrink-0"
        @click="emit('select', war)"
      >
        <Flame class="w-3.5 h-3.5 text-amber-400" />
        <span>Receipt</span>
        <ChevronRight class="w-3.5 h-3.5" />
      </button>
    </div>

    <!-- Body: Winning Claim vs Losing Bids -->
    <div class="p-3.5 space-y-3">
      <!-- Winning Bid Card -->
      <div class="bg-emerald-950/20 rounded-xl p-3 border border-emerald-500/30 flex items-center justify-between gap-2 shadow-sm">
        <div class="flex items-center gap-2.5 min-w-0">
          <div class="w-8 h-8 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center shrink-0 border border-emerald-500/30">
            <Trophy class="w-4 h-4 text-emerald-400" />
          </div>
          <div class="min-w-0">
            <div class="flex items-center gap-1.5">
              <span class="font-bold text-xs text-slate-100 truncate" :title="war.winner.manager_name">
                {{ war.winner.manager_name }}
              </span>
              <span class="text-[10px] font-bold uppercase tracking-wider text-emerald-400 bg-emerald-500/20 px-1.5 py-0.2 rounded font-mono">
                Won
              </span>
            </div>
            <div class="text-[11px] text-slate-400 truncate mt-0.5" :title="war.winner.team_name">
              {{ war.winner.team_name }}
            </div>
          </div>
        </div>

        <div class="text-right shrink-0">
          <div class="text-sm font-mono font-black text-emerald-400">
            ${{ war.winner.bid_amount }} FAAB
          </div>
          <div class="text-[11px] font-mono text-emerald-300 font-semibold">
            +{{ war.winner.post_claim_starter_points.toFixed(1) }} starter pts
          </div>
        </div>
      </div>

      <!-- Losing Bids Section -->
      <div class="space-y-1.5">
        <div class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center justify-between">
          <span class="flex items-center gap-1">
            <XCircle class="w-3.5 h-3.5 text-rose-400" />
            <span>Outbid Contenders ({{ war.losing_bids.length }})</span>
          </span>
          <span class="text-[10px] text-slate-500 font-mono">Lost by Margin</span>
        </div>

        <div class="space-y-1.5">
          <div
            v-for="loser in war.losing_bids"
            :key="loser.transaction_id"
            class="bg-slate-900/70 rounded-lg p-2.5 border border-slate-800/80 flex items-center justify-between gap-2"
          >
            <div class="flex items-center gap-2 min-w-0">
              <div class="w-6 h-6 rounded-md bg-slate-800 text-slate-400 text-xs font-bold font-mono flex items-center justify-center shrink-0">
                -
              </div>
              <div class="min-w-0">
                <div class="font-semibold text-xs text-slate-200 truncate" :title="loser.manager_name">
                  {{ loser.manager_name }}
                </div>
                <div class="text-[10px] text-slate-500 truncate" :title="loser.team_name">
                  {{ loser.team_name }}
                </div>
              </div>
            </div>

            <div class="flex items-center gap-2 shrink-0">
              <!-- Failure Reason Badge -->
              <span
                class="px-2 py-0.5 rounded text-[10px] font-mono font-bold border"
                :class="getFailureBadgeClass(loser.failure_reason)"
              >
                {{ loser.failure_reason }}
              </span>

              <div class="text-right font-mono">
                <div class="text-xs font-bold text-slate-300">
                  ${{ loser.bid_amount }}
                </div>
                <div class="text-[10px] text-rose-400">
                  -${{ war.winner.bid_amount - loser.bid_amount }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
