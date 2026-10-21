<script setup lang="ts">
import { computed } from 'vue';
import type { BiddingWar } from '@/types/api';
import SwipeDrawer from '@/components/ui/SwipeDrawer.vue';
import { Flame, Trophy, Calendar, Hash, DollarSign, TrendingUp } from 'lucide-vue-next';

const props = defineProps<{
  modelValue: boolean;
  war: BiddingWar | null;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
}>();

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateStr;
  }
}

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

// Full bid ladder sorted descending by bid amount
const bidLadder = computed(() => {
  if (!props.war) return [];
  const entries = [
    {
      isWinner: true,
      manager_name: props.war.winner.manager_name,
      team_name: props.war.winner.team_name,
      bid_amount: props.war.winner.bid_amount,
      failure_reason: null as string | null,
      waiver_priority: null as number | null,
      starter_points: props.war.winner.post_claim_starter_points,
    },
    ...props.war.losing_bids.map((b) => ({
      isWinner: false,
      manager_name: b.manager_name,
      team_name: b.team_name,
      bid_amount: b.bid_amount,
      failure_reason: b.failure_reason,
      waiver_priority: b.waiver_priority,
      starter_points: null as number | null,
    })),
  ];

  return entries.sort((a, b) => b.bid_amount - a.bid_amount);
});

// Points per FAAB dollar on this claim
const claimRoi = computed(() => {
  if (!props.war || props.war.winner.bid_amount <= 0) return null;
  return (props.war.winner.post_claim_starter_points / props.war.winner.bid_amount).toFixed(2);
});
</script>

<template>
  <SwipeDrawer
    :model-value="modelValue"
    max-height="max-h-[90vh]"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template #header>
      <div class="flex items-center gap-2">
        <div class="w-8 h-8 rounded-lg bg-amber-500/20 border border-amber-500/40 text-amber-400 flex items-center justify-center">
          <Flame class="w-4 h-4" />
        </div>
        <div>
          <h2 class="text-base font-black tracking-tight text-slate-100 uppercase">
            FAAB Bidding War Receipt
          </h2>
          <p class="text-xs text-slate-400">
            Contested waiver auction bids & post-claim starter realization
          </p>
        </div>
      </div>
    </template>

    <div v-if="war" class="space-y-5 pb-6">
      <!-- Player Header Card -->
      <div class="stadium-card rounded-xl p-4 border border-slate-800 space-y-3">
        <div class="flex items-center justify-between text-xs text-slate-400 border-b border-slate-800/80 pb-2.5">
          <span class="flex items-center gap-1.5 font-mono">
            <Calendar class="w-3.5 h-3.5 text-slate-400" />
            <span>Season {{ war.season_year }}</span>
            <span v-if="war.week != null">• Week {{ war.week }} Waiver Run</span>
          </span>
          <span v-if="war.executed_at">
            {{ formatDate(war.executed_at) }}
          </span>
        </div>

        <div class="flex items-center gap-3">
          <div class="w-12 h-12 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center font-mono font-bold text-sm" :class="getPositionClass(war.player.default_position)">
            {{ war.player.default_position }}
          </div>
          <div>
            <h3 class="font-bold text-base text-slate-100">
              {{ war.player.full_name }}
            </h3>
            <div class="flex items-center gap-2 text-xs text-slate-400 mt-0.5">
              <span class="font-mono font-semibold">{{ war.player.default_position }}</span>
              <span>•</span>
              <span class="font-mono font-semibold">{{ war.player.pro_team }}</span>
              <span>•</span>
              <span class="text-amber-400 font-semibold">{{ war.losing_bids.length + 1 }} Managers Competed</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Realized ROI Analysis Card -->
      <div class="grid grid-cols-2 gap-2.5">
        <div class="stadium-card rounded-xl p-3 border border-emerald-500/30 bg-emerald-950/20 text-center">
          <div class="text-[11px] font-semibold text-emerald-300 uppercase tracking-wide flex items-center justify-center gap-1">
            <TrendingUp class="w-3.5 h-3.5" />
            <span>Realized Starter Pts</span>
          </div>
          <div class="text-xl font-mono font-black text-emerald-400 mt-1">
            +{{ war.winner.post_claim_starter_points.toFixed(1) }}
          </div>
          <div class="text-[10px] text-emerald-300/80 mt-0.5">
            Post-claim starter points gained
          </div>
        </div>

        <div class="stadium-card rounded-xl p-3 border border-slate-800 bg-slate-900/60 text-center">
          <div class="text-[11px] font-semibold text-slate-300 uppercase tracking-wide flex items-center justify-center gap-1">
            <DollarSign class="w-3.5 h-3.5 text-amber-400" />
            <span>Claim Value ROI</span>
          </div>
          <div class="text-xl font-mono font-black text-amber-300 mt-1">
            {{ claimRoi != null ? `${claimRoi} pts/$` : '—' }}
          </div>
          <div class="text-[10px] text-slate-400 mt-0.5">
            Points per FAAB dollar spent
          </div>
        </div>
      </div>

      <!-- Complete Bid Ladder -->
      <div class="space-y-2">
        <div class="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center justify-between">
          <span>Complete Bidding Ladder</span>
          <span class="text-[10px] font-mono text-slate-500">Ranked by Bid Amount</span>
        </div>

        <div class="space-y-2">
          <div
            v-for="(bid, index) in bidLadder"
            :key="`${bid.manager_name}-${bid.bid_amount}-${index}`"
            class="rounded-xl p-3 border transition-all flex items-center justify-between gap-3"
            :class="
              bid.isWinner
                ? 'bg-emerald-950/30 border-emerald-500/40 stadium-glow-emerald'
                : 'bg-slate-900/80 border-slate-800'
            "
          >
            <div class="flex items-center gap-3 min-w-0">
              <div
                class="w-7 h-7 rounded-lg text-xs font-mono font-bold flex items-center justify-center shrink-0"
                :class="
                  bid.isWinner
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                    : 'bg-slate-800 text-slate-400 border border-slate-700'
                "
              >
                #{{ index + 1 }}
              </div>

              <div class="min-w-0">
                <div class="flex items-center gap-1.5">
                  <span class="font-bold text-xs text-slate-100 truncate" :title="bid.manager_name">
                    {{ bid.manager_name }}
                  </span>
                  <span
                    v-if="bid.isWinner"
                    class="px-1.5 py-0.2 rounded text-[10px] font-mono font-bold uppercase tracking-wider bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center gap-0.5"
                  >
                    <Trophy class="w-2.5 h-2.5" />
                    <span>Claim Won</span>
                  </span>
                </div>
                <div class="text-[11px] text-slate-400 truncate mt-0.5" :title="bid.team_name">
                  {{ bid.team_name }}
                </div>
              </div>
            </div>

            <!-- Bid Amount & Reason -->
            <div class="text-right shrink-0">
              <div
                class="text-sm font-mono font-black"
                :class="bid.isWinner ? 'text-emerald-400' : 'text-slate-300'"
              >
                ${{ bid.bid_amount }} FAAB
              </div>

              <div v-if="!bid.isWinner" class="flex items-center gap-1 justify-end mt-0.5">
                <span
                  class="px-1.5 py-0.2 rounded text-[10px] font-mono font-bold border"
                  :class="
                    bid.failure_reason === 'OUTBID'
                      ? 'bg-rose-500/15 text-rose-300 border-rose-500/30'
                      : 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                  "
                >
                  {{ bid.failure_reason || 'OUTBID' }}
                </span>
                <span class="text-[10px] font-mono text-rose-400">
                  (-${{ war.winner.bid_amount - bid.bid_amount }})
                </span>
              </div>

              <div v-if="bid.waiver_priority != null" class="text-[10px] font-mono text-slate-500 mt-0.5">
                Priority: #{{ bid.waiver_priority }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Transaction Meta Footer -->
      <div class="text-[11px] font-mono text-slate-500 text-center pt-2 flex items-center justify-center gap-2">
        <Hash class="w-3.5 h-3.5 text-slate-600" />
        <span>ESPN Transaction ID: {{ war.espn_transaction_id }}</span>
      </div>
    </div>
  </SwipeDrawer>
</template>
