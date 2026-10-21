<script setup lang="ts">
import { computed } from 'vue';
import type { TradeDetail } from '@/types/api';
import SwipeDrawer from '@/components/ui/SwipeDrawer.vue';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import { Trophy, Calendar, Scale, Hash, ArrowLeftRight, Clock } from 'lucide-vue-next';

const props = defineProps<{
  modelValue: boolean;
  trade: TradeDetail | null;
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

const sideA = computed(() => props.trade?.sides[0] ?? null);
const sideB = computed(() => props.trade?.sides[1] ?? null);

const sideAPercent = computed(() => {
  if (!sideA.value || !sideB.value) return 50;
  const total = sideA.value.total_starter_points_gained + sideB.value.total_starter_points_gained;
  if (total <= 0) return 50;
  return Math.min(95, Math.max(5, (sideA.value.total_starter_points_gained / total) * 100));
});

const winnerSide = computed(() => {
  if (!props.trade?.winner_manager_id) return null;
  return props.trade.sides.find((s) => s.manager_id === props.trade?.winner_manager_id) ?? null;
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
        <div class="w-8 h-8 rounded-lg bg-indigo-500/20 border border-indigo-500/40 text-indigo-400 flex items-center justify-center">
          <ArrowLeftRight class="w-4 h-4" />
        </div>
        <div>
          <h2 class="text-base font-black tracking-tight text-slate-100 uppercase">
            Trade Autopsy Receipt
          </h2>
          <p class="text-xs text-slate-400">
            Realized starter fantasy points realized post-trade
          </p>
        </div>
      </div>
    </template>

    <div v-if="trade" class="space-y-5 pb-6">
      <!-- Top Overview Card -->
      <div class="stadium-card rounded-xl p-4 border border-slate-800 space-y-3">
        <div class="flex items-center justify-between text-xs text-slate-400 border-b border-slate-800/80 pb-2.5">
          <span class="flex items-center gap-1.5 font-mono">
            <Calendar class="w-3.5 h-3.5 text-slate-400" />
            <span>Season {{ trade.season_year }}</span>
            <span v-if="trade.week != null">• Week {{ trade.week }}</span>
          </span>
          <span v-if="trade.executed_at" class="flex items-center gap-1.5">
            <Clock class="w-3.5 h-3.5 text-slate-400" />
            <span>{{ formatDate(trade.executed_at) }}</span>
          </span>
        </div>

        <!-- Trade Verdict -->
        <div class="text-center py-1">
          <div v-if="winnerSide" class="space-y-1">
            <div class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold font-mono bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm">
              <Trophy class="w-4 h-4 text-amber-400" />
              <span>Verdict: {{ winnerSide.team_name || winnerSide.manager_name }} Won (+{{ trade.point_differential.toFixed(1) }} pts)</span>
            </div>
            <p class="text-xs text-slate-400">
              {{ winnerSide.team_name || winnerSide.manager_name }} ({{ winnerSide.manager_name }}) realized {{ trade.point_differential.toFixed(1) }} more points from starters acquired than the opposing side.
            </p>
          </div>
          <div v-else class="space-y-1">
            <div class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold font-mono bg-slate-800 text-slate-300 border border-slate-700">
              <Scale class="w-4 h-4 text-slate-400" />
              <span>Verdict: Even Realized Trade Value</span>
            </div>
            <p class="text-xs text-slate-400">
              Both sides gained equivalent starter fantasy points post-trade.
            </p>
          </div>
        </div>

        <!-- Tug-of-war Bar -->
        <div v-if="sideA && sideB" class="space-y-1.5 pt-1">
          <div class="flex items-center justify-between text-xs font-mono font-bold">
            <span :class="sideA.manager_id === trade.winner_manager_id ? 'text-emerald-400' : 'text-slate-300'">
              {{ sideA.team_name || sideA.manager_name }}: {{ sideA.total_starter_points_gained.toFixed(1) }} pts
            </span>
            <span :class="sideB.manager_id === trade.winner_manager_id ? 'text-emerald-400' : 'text-slate-300'">
              {{ sideB.total_starter_points_gained.toFixed(1) }} pts: {{ sideB.team_name || sideB.manager_name }}
            </span>
          </div>

          <div class="w-full h-3 rounded-full bg-slate-800 overflow-hidden flex border border-slate-700/80">
            <div
              class="h-full transition-all duration-500"
              :class="sideA.manager_id === trade.winner_manager_id ? 'bg-emerald-500' : 'bg-indigo-600'"
              :style="{ width: `${sideAPercent}%` }"
            ></div>
            <div
              class="h-full transition-all duration-500"
              :class="sideB.manager_id === trade.winner_manager_id ? 'bg-emerald-500' : 'bg-slate-600'"
              :style="{ width: `${100 - sideAPercent}%` }"
            ></div>
          </div>
        </div>
      </div>

      <!-- Deep Sides Breakdown -->
      <div class="space-y-4">
        <div
          v-for="side in trade.sides"
          :key="side.manager_id"
          class="stadium-card rounded-xl p-4 border border-slate-800 space-y-3"
          :class="side.manager_id === trade.winner_manager_id ? 'border-emerald-500/40' : ''"
        >
          <!-- Side Header -->
          <div class="flex items-center justify-between border-b border-slate-800/80 pb-2">
            <div class="flex items-center gap-2.5 min-w-0">
              <TeamAvatar
                :src="side.logo_url"
                :name="side.team_name || side.manager_name"
                size="md"
              />
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <span class="font-bold text-sm text-slate-100 truncate">{{ side.team_name }}</span>
                  <span
                    v-if="side.manager_id === trade.winner_manager_id"
                    class="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase font-mono bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                  >
                    Trade Winner
                  </span>
                </div>
                <div class="text-xs text-slate-400 truncate">{{ side.manager_name }}</div>
              </div>
            </div>

            <div class="text-right">
              <div class="text-sm font-mono font-black text-emerald-400">
                +{{ side.total_starter_points_gained.toFixed(1) }} pts
              </div>
              <div v-if="side.faab_received > 0" class="text-xs font-mono text-amber-400 font-semibold">
                +${{ side.faab_received }} FAAB
              </div>
            </div>
          </div>

          <!-- Assets Table / List -->
          <div class="space-y-2">
            <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Players Received
            </div>

            <div
              v-for="asset in side.assets_received"
              :key="asset.player_id"
              class="bg-slate-900/90 rounded-lg p-3 border border-slate-800 flex items-center justify-between gap-2"
            >
              <div class="flex items-center gap-3 min-w-0">
                <div class="w-10 h-10 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center font-mono font-bold text-xs" :class="getPositionClass(asset.default_position)">
                  {{ asset.default_position }}
                </div>
                <div class="min-w-0">
                  <div class="font-bold text-xs text-slate-100 truncate">{{ asset.full_name }}</div>
                  <div class="text-[11px] text-slate-400 font-mono">{{ asset.default_position }} • {{ asset.pro_team }}</div>
                </div>
              </div>

              <div class="text-right font-mono shrink-0">
                <div class="text-xs font-bold text-slate-100">
                  {{ asset.post_trade_starter_points.toFixed(1) }} pts
                </div>
                <div class="text-[11px] text-slate-400">
                  {{ asset.post_trade_weeks_started }} starts
                  <span v-if="asset.post_trade_weeks_started > 0" class="text-slate-500">
                    ({{ (asset.post_trade_starter_points / asset.post_trade_weeks_started).toFixed(1) }}/gm)
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Transaction Meta Footer -->
      <div class="text-[11px] font-mono text-slate-500 text-center pt-2 flex items-center justify-center gap-2">
        <Hash class="w-3.5 h-3.5 text-slate-600" />
        <span>ESPN Transaction ID: {{ trade.espn_transaction_id }}</span>
      </div>
    </div>
  </SwipeDrawer>
</template>
