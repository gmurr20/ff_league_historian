<script setup lang="ts">
import { ref, computed } from 'vue';
import type { TradeDetail, TradeSide } from '@/types/api';
import SwipeDrawer from '@/components/ui/SwipeDrawer.vue';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import TradeTrajectoryChart from '@/components/trades/TradeTrajectoryChart.vue';
import {
  Calendar,
  Hash,
  ArrowLeftRight,
  Clock,
  Ticket,
  Layers,
  Scale,
} from 'lucide-vue-next';

const props = defineProps<{
  modelValue: boolean;
  trade: TradeDetail | null;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
}>();

const failedImages = ref<Record<string | number, boolean>>({});

function handleImageError(id: string | number) {
  failedImages.value[id] = true;
}

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

function getGradeBadgeClass(grade: string | null | undefined): string {
  if (!grade) return 'bg-slate-800 text-slate-400 border-slate-700';
  const g = grade.toUpperCase();
  if (g.startsWith('A')) return 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 shadow-sm shadow-emerald-950/40';
  if (g.startsWith('B')) return 'bg-sky-500/20 text-sky-300 border-sky-500/40 shadow-sm shadow-sky-950/40';
  if (g.startsWith('C')) return 'bg-amber-500/20 text-amber-300 border-amber-500/40 shadow-sm shadow-amber-950/40';
  return 'bg-rose-500/20 text-rose-300 border-rose-500/40 shadow-sm shadow-rose-950/40';
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
    case 'D/ST':
    case 'DST':
      return 'bg-slate-500/20 text-slate-300 border-slate-500/40';
    case 'PICK':
      return 'bg-violet-500/20 text-violet-300 border-violet-500/40';
    default:
      return 'bg-slate-700 text-slate-300 border-slate-600';
  }
}

const sideA = computed<TradeSide | null>(() => props.trade?.sides[0] ?? null);
const sideB = computed<TradeSide | null>(() => props.trade?.sides[1] ?? null);

// Overall Score Percentage Distribution (Side A vs Side B)
const overallScorePercentA = computed(() => {
  if (!sideA.value || !sideB.value) return 50;
  const a = Math.max(0, sideA.value.total_trade_score);
  const b = Math.max(0, sideB.value.total_trade_score);
  const sum = a + b;
  if (sum <= 0) return 50;
  return Math.min(95, Math.max(5, (a / sum) * 100));
});
</script>

<template>
  <SwipeDrawer
    :model-value="modelValue"
    max-height="max-h-[92vh]"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template #header>
      <div class="flex items-center gap-2.5">
        <div class="w-8 h-8 rounded-lg bg-indigo-500/20 border border-indigo-500/40 text-indigo-400 flex items-center justify-center shrink-0">
          <ArrowLeftRight class="w-4 h-4" />
        </div>
        <div>
          <h2 class="text-base font-black tracking-tight text-slate-100 uppercase flex items-center gap-2">
            <span>Trade Autopsy Report</span>
          </h2>
          <p class="text-xs text-slate-400">
            Realized post-trade output, player production & valuation analysis
          </p>
        </div>
      </div>
    </template>

    <div v-if="trade && sideA && sideB" class="space-y-5 pb-8">
      <!-- 1. TOP SECTION: THE TRADE WITH TEAMS, PLAYERS & LETTER GRADES -->
      <div class="stadium-card rounded-2xl border border-indigo-500/40 bg-slate-900/90 overflow-hidden shadow-xl">
        <!-- Trade Meta Header Bar -->
        <div class="px-4 py-2.5 bg-slate-950/80 border-b border-slate-800 flex items-center justify-between gap-2 flex-wrap">
          <div class="flex items-center gap-2 flex-wrap">
            <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md text-xs font-mono font-bold bg-slate-800 text-slate-200 border border-slate-700">
              <Calendar class="w-3.5 h-3.5 text-indigo-400" />
              <span>Season {{ trade.season_year }}</span>
              <span v-if="trade.week != null">• {{ trade.week === 0 ? 'Preseason / Draft' : `Week ${trade.week}` }}</span>
            </span>

            <span
              v-if="trade.verdict_label"
              class="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30"
            >
              {{ trade.verdict_label }}
            </span>

            <span
              v-if="trade.is_projected"
              class="px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 animate-pulse"
            >
              Live / Projected Form
            </span>
          </div>

          <span v-if="trade.executed_at" class="flex items-center gap-1.5 font-mono text-xs text-slate-400">
            <Clock class="w-3.5 h-3.5 text-slate-500" />
            <span>{{ formatDate(trade.executed_at) }}</span>
          </span>
        </div>

        <!-- The Two Sides with Players Exchanged -->
        <div class="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-slate-800">
          <div
            v-for="side in trade.sides"
            :key="side.manager_id"
            class="p-4 sm:p-5 flex flex-col justify-between gap-3 bg-slate-900/60"
          >
            <!-- Team Info & Current Letter Grade -->
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-2.5 min-w-0">
                <TeamAvatar
                  :src="side.logo_url"
                  :name="side.team_name || side.manager_name"
                  size="md"
                />
                <div class="min-w-0">
                  <div class="font-bold text-sm text-slate-100 truncate" :title="side.team_name">
                    {{ side.team_name }}
                  </div>
                  <div class="text-xs text-slate-400 truncate mt-0.5" :title="side.manager_name">
                    {{ side.manager_name }}
                  </div>
                </div>
              </div>

              <!-- Standout Grade Badge -->
              <div class="text-right shrink-0">
                <div class="text-[9px] font-mono font-bold uppercase tracking-wider text-slate-400">
                  Current Grade
                </div>
                <div
                  class="text-xs font-mono font-black px-2.5 py-1 rounded-lg border inline-flex items-center gap-1 mt-0.5 shadow-sm"
                  :class="getGradeBadgeClass(side.grade)"
                >
                  <span>Grade {{ side.grade }}</span>
                </div>
              </div>
            </div>

            <!-- Acquired Assets with Headshots & Tags -->
            <div class="space-y-2 mt-1">
              <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center justify-between">
                <span>Acquired Assets ({{ side.assets_received.length }})</span>
                <span v-if="side.faab_received > 0" class="text-amber-400 font-mono text-[10px] font-bold">
                  +${{ side.faab_received }} FAAB
                </span>
              </div>

              <!-- Fallback if empty -->
              <div
                v-if="side.assets_received.length === 0 && side.faab_received <= 0"
                class="text-xs text-slate-500 italic py-2 text-center bg-slate-950/40 rounded-lg border border-slate-800/60"
              >
                Draft picks or FAAB only
              </div>

              <!-- Assets Cards -->
              <div class="space-y-2">
                <div
                  v-for="asset in side.assets_received"
                  :key="asset.player_id"
                >
                  <!-- DRAFT PICK ASSET CARD -->
                  <div
                    v-if="asset.asset_type === 'PICK'"
                    class="bg-gradient-to-r from-violet-950/30 to-slate-900/80 rounded-xl p-2.5 border border-violet-500/30 flex flex-col gap-1.5"
                  >
                    <div class="flex items-center justify-between gap-2">
                      <div class="flex items-center gap-2.5 min-w-0">
                        <div class="w-8 h-8 rounded-lg bg-violet-900/40 border border-violet-500/40 flex items-center justify-center shrink-0 text-violet-300">
                          <Ticket class="w-4 h-4" />
                        </div>
                        <div class="min-w-0">
                          <div class="font-bold text-xs text-violet-200 truncate">{{ asset.full_name }}</div>
                          <div class="flex items-center gap-1.5 mt-0.5 flex-wrap">
                            <span
                              v-if="asset.pick_round != null"
                              class="px-1.5 py-0.2 rounded text-[10px] font-mono font-bold bg-violet-500/20 text-violet-300 border border-violet-500/40"
                            >
                              Round {{ asset.pick_round }}
                            </span>
                            <span v-if="asset.tier_label" class="text-indigo-300 text-[10px] font-mono">{{ asset.tier_label }}</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    <!-- Drafted player badge -->
                    <div
                      v-if="asset.drafted_player_name"
                      class="flex items-center gap-2 bg-slate-950/60 rounded-lg p-1.5 border border-violet-500/20 text-xs"
                    >
                      <div class="relative w-6 h-6 rounded-full bg-slate-800 border border-slate-700 overflow-hidden shrink-0 flex items-center justify-center">
                        <img
                          v-if="asset.drafted_player_headshot_url && !failedImages[`pick-${asset.drafted_player_id}`]"
                          :src="asset.drafted_player_headshot_url"
                          :alt="asset.drafted_player_name"
                          class="w-full h-full object-cover"
                          loading="lazy"
                          @error="handleImageError(`pick-${asset.drafted_player_id}`)"
                        />
                        <Ticket v-else class="w-3 h-3 text-violet-400" />
                      </div>
                      <div class="flex-1 min-w-0 flex items-center gap-1.5 truncate">
                        <span class="text-slate-400 text-[10px]">Drafted:</span>
                        <span class="font-bold text-slate-200 text-xs truncate">{{ asset.drafted_player_name }}</span>
                        <span
                          v-if="asset.drafted_player_position"
                          class="px-1 rounded text-[9px] font-mono font-bold border"
                          :class="getPositionClass(asset.drafted_player_position)"
                        >
                          {{ asset.drafted_player_position }}
                        </span>
                      </div>
                    </div>
                  </div>

                  <!-- PLAYER ASSET CARD -->
                  <div
                    v-else
                    class="bg-slate-900/90 rounded-xl p-2.5 border border-slate-800/80 flex items-center justify-between gap-2.5"
                  >
                    <!-- Player Headshot + Info & Tags -->
                    <div class="flex items-center gap-2.5 min-w-0 flex-1">
                      <div class="relative w-9 h-9 rounded-full bg-slate-800 border border-slate-700 overflow-hidden shrink-0 flex items-center justify-center">
                        <img
                          v-if="asset.headshot_url && !failedImages[asset.player_id]"
                          :src="asset.headshot_url"
                          :alt="asset.full_name"
                          class="w-full h-full object-cover"
                          loading="lazy"
                          @error="handleImageError(asset.player_id)"
                        />
                        <div
                          v-else
                          class="w-full h-full flex items-center justify-center font-bold text-xs font-mono"
                          :class="getPositionClass(asset.default_position)"
                        >
                          {{ asset.default_position }}
                        </div>
                      </div>

                      <div class="min-w-0 flex-1">
                        <div class="font-bold text-xs text-slate-100 truncate" :title="asset.full_name">
                          {{ asset.full_name }}
                        </div>

                        <!-- Tags: Position, Pro Team, Positional Rank, Tier Tag -->
                        <div class="flex items-center gap-1.5 mt-1 flex-wrap">
                          <span
                            class="px-1.5 py-0.2 rounded text-[10px] font-mono font-bold border"
                            :class="getPositionClass(asset.default_position)"
                          >
                            {{ asset.default_position }}
                          </span>

                          <span class="text-[10px] text-slate-400 font-semibold font-mono">
                            {{ asset.pro_team }}
                          </span>

                          <span
                            v-if="asset.positional_rank"
                            class="px-1.5 py-0.2 rounded text-[10px] font-mono font-bold bg-amber-500/15 text-amber-300 border border-amber-500/30"
                          >
                            #{{ asset.positional_rank }} {{ asset.default_position }}
                          </span>

                          <span
                            v-if="asset.tier_label"
                            class="px-2 py-0.2 rounded-full text-[10px] font-mono font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 shadow-xs"
                          >
                            {{ asset.tier_label }}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 2. VALUE COMPARISON SECTION: Starter Points & Total Trade Score -->
      <div class="stadium-card rounded-2xl p-4 sm:p-5 border border-slate-800 bg-slate-900/60 space-y-4">
        <div class="flex items-center justify-between text-xs text-slate-400 font-mono">
          <div class="flex items-center gap-2">
            <Scale class="w-4 h-4 text-indigo-400" />
            <span class="font-bold uppercase tracking-wider text-slate-200">Head-to-Head Value Comparison</span>
          </div>
          <span v-if="trade.score_differential >= 1.0" class="text-slate-400">
            Margin: Δ {{ trade.score_differential.toFixed(1) }} Score
          </span>
          <span v-else class="text-slate-400">Even Value</span>
        </div>

        <!-- Unified Side-by-Side Comparison Grid (Indigo for Side A, Sky for Side B) -->
        <div class="grid grid-cols-2 gap-3 sm:gap-4">
          <!-- Side A Summary Column -->
          <div class="p-3.5 rounded-xl bg-slate-950/60 border border-indigo-500/30 space-y-2.5">
            <div class="flex items-center gap-2 min-w-0">
              <TeamAvatar :src="sideA.logo_url" :name="sideA.team_name" size="sm" />
              <span class="font-bold text-xs text-indigo-300 truncate">{{ sideA.team_name }}</span>
            </div>

            <div class="space-y-1.5 pt-1 border-t border-slate-800/80 font-mono">
              <div class="flex items-center justify-between text-xs">
                <span class="text-slate-400">Starter Points:</span>
                <span class="font-bold text-slate-100">{{ sideA.total_starter_points_gained.toFixed(1) }} pts</span>
              </div>
              <div class="flex items-center justify-between text-xs">
                <span class="text-slate-400">Total Trade Score:</span>
                <span class="font-black text-indigo-400">{{ sideA.total_trade_score.toFixed(1) }}</span>
              </div>
              <div v-if="sideA.total_roster_depth_points_gained > 0 || sideA.faab_received > 0 || sideA.total_pick_value_gained > 0" class="flex items-center justify-between text-[11px] text-slate-500 pt-0.5">
                <span>Depth / Assets:</span>
                <span>
                  {{ sideA.total_roster_depth_points_gained > 0 ? `+${sideA.total_roster_depth_points_gained.toFixed(1)} depth` : '' }}
                  {{ sideA.faab_received > 0 ? `+$${sideA.faab_received} FAAB` : '' }}
                </span>
              </div>
            </div>
          </div>

          <!-- Side B Summary Column -->
          <div class="p-3.5 rounded-xl bg-slate-950/60 border border-sky-500/30 space-y-2.5">
            <div class="flex items-center gap-2 min-w-0">
              <TeamAvatar :src="sideB.logo_url" :name="sideB.team_name" size="sm" />
              <span class="font-bold text-xs text-sky-300 truncate">{{ sideB.team_name }}</span>
            </div>

            <div class="space-y-1.5 pt-1 border-t border-slate-800/80 font-mono">
              <div class="flex items-center justify-between text-xs">
                <span class="text-slate-400">Starter Points:</span>
                <span class="font-bold text-slate-100">{{ sideB.total_starter_points_gained.toFixed(1) }} pts</span>
              </div>
              <div class="flex items-center justify-between text-xs">
                <span class="text-slate-400">Total Trade Score:</span>
                <span class="font-black text-sky-400">{{ sideB.total_trade_score.toFixed(1) }}</span>
              </div>
              <div v-if="sideB.total_roster_depth_points_gained > 0 || sideB.faab_received > 0 || sideB.total_pick_value_gained > 0" class="flex items-center justify-between text-[11px] text-slate-500 pt-0.5">
                <span>Depth / Assets:</span>
                <span>
                  {{ sideB.total_roster_depth_points_gained > 0 ? `+${sideB.total_roster_depth_points_gained.toFixed(1)} depth` : '' }}
                  {{ sideB.faab_received > 0 ? `+$${sideB.faab_received} FAAB` : '' }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- Unified Proportional Trade Value Share Bar -->
        <div class="space-y-1 pt-1">
          <div class="flex items-center justify-between text-[11px] font-mono text-slate-400">
            <span class="text-indigo-400 font-bold truncate max-w-[150px]">{{ sideA.team_name }} ({{ overallScorePercentA.toFixed(0) }}%)</span>
            <span class="text-slate-500 font-semibold uppercase text-[10px]">Trade Value Share</span>
            <span class="text-sky-400 font-bold truncate max-w-[150px] text-right">{{ sideB.team_name }} ({{ (100 - overallScorePercentA).toFixed(0) }}%)</span>
          </div>
          <div class="w-full h-2.5 rounded-full bg-slate-800 overflow-hidden flex border border-slate-700/60">
            <div
              class="h-full bg-indigo-500 transition-all duration-500"
              :style="{ width: `${overallScorePercentA}%` }"
            ></div>
            <div
              class="h-full bg-sky-500 transition-all duration-500"
              :style="{ width: `${100 - overallScorePercentA}%` }"
            ></div>
          </div>
        </div>
      </div>

      <!-- 3. INTERACTIVE WEEK-BY-WEEK TRAJECTORY CHART (Visual Story Over Time) -->
      <div class="stadium-card rounded-2xl p-4 border border-slate-800 bg-slate-900/60 space-y-3">
        <TradeTrajectoryChart :trade="trade" />
      </div>

      <!-- 4. DETAILED PLAYER PRODUCTION, ROSTER DEPTH & GAME LOGS -->
      <div class="space-y-4">
        <div class="text-xs font-black uppercase tracking-wider text-slate-300 flex items-center gap-2">
          <Layers class="w-4 h-4 text-indigo-400" />
          <span>Player Production & Starter Deployment</span>
        </div>

        <div
          v-for="side in trade.sides"
          :key="side.manager_id"
          class="stadium-card rounded-xl p-4 border border-slate-800 space-y-3 bg-slate-900/70"
        >
          <!-- Side Header -->
          <div class="flex items-center justify-between border-b border-slate-800/80 pb-2.5 flex-wrap gap-2">
            <div class="flex items-center gap-2.5 min-w-0">
              <TeamAvatar
                :src="side.logo_url"
                :name="side.team_name || side.manager_name"
                size="md"
              />
              <div class="min-w-0">
                <div class="font-bold text-sm text-slate-100 truncate">{{ side.team_name }}</div>
                <div class="text-xs text-slate-400 truncate">{{ side.manager_name }}</div>
              </div>
            </div>

            <!-- Grade & Total Starter Pts -->
            <div class="flex items-center gap-2 shrink-0">
              <div class="text-right font-mono">
                <div class="text-xs font-bold text-emerald-400">
                  {{ side.total_starter_points_gained.toFixed(1) }} Starter Pts
                </div>
                <div class="text-[10px] text-slate-400">
                  +{{ side.total_roster_depth_points_gained.toFixed(1) }} depth
                </div>
              </div>

              <span
                class="px-2.5 py-0.5 rounded-lg text-xs font-mono font-black border"
                :class="getGradeBadgeClass(side.grade)"
              >
                Grade {{ side.grade }}
              </span>
            </div>
          </div>

          <!-- Assets List -->
          <div class="space-y-3">
            <div
              v-if="side.assets_received.length === 0"
              class="text-xs text-slate-500 italic py-3 text-center bg-slate-900/40 rounded-lg"
            >
              Draft picks or FAAB only
            </div>

            <div
              v-for="asset in side.assets_received"
              :key="asset.player_id"
              class="bg-slate-900/90 rounded-xl p-3 border border-slate-800 space-y-2.5"
            >
              <!-- DRAFT PICK ASSET DETAILS -->
              <div v-if="asset.asset_type === 'PICK'" class="space-y-2">
                <div class="flex items-center justify-between gap-2">
                  <div class="flex items-center gap-3 min-w-0">
                    <div class="w-9 h-9 rounded-full bg-violet-900/40 border border-violet-500/40 flex items-center justify-center font-mono font-bold text-xs text-violet-300 shrink-0">
                      <Ticket class="w-4 h-4" />
                    </div>
                    <div class="min-w-0">
                      <div class="font-bold text-xs text-violet-200 truncate">{{ asset.full_name }}</div>
                      <div class="flex items-center gap-2 mt-0.5 text-[11px] font-mono text-slate-400 flex-wrap">
                        <span v-if="asset.pick_round != null" class="text-violet-300 font-bold">Round {{ asset.pick_round }}</span>
                        <span v-if="asset.tier_label" class="text-indigo-300">{{ asset.tier_label }}</span>
                      </div>
                    </div>
                  </div>

                  <div class="text-right font-mono shrink-0">
                    <div class="text-xs font-bold text-violet-300">
                      {{ asset.trade_score.toFixed(1) }} value
                    </div>
                  </div>
                </div>

                <!-- Drafted Player output if pick was exercised -->
                <div
                  v-if="asset.drafted_player_name"
                  class="bg-slate-950/70 rounded-lg p-2.5 border border-violet-500/30 flex items-center justify-between gap-2"
                >
                  <div class="flex items-center gap-2.5 min-w-0">
                    <div class="relative w-8 h-8 rounded-full bg-slate-800 border border-slate-700 overflow-hidden shrink-0 flex items-center justify-center">
                      <img
                        v-if="asset.drafted_player_headshot_url && !failedImages[`pick-drawer-${asset.drafted_player_id}`]"
                        :src="asset.drafted_player_headshot_url"
                        :alt="asset.drafted_player_name"
                        class="w-full h-full object-cover"
                        loading="lazy"
                        @error="handleImageError(`pick-drawer-${asset.drafted_player_id}`)"
                      />
                      <Ticket v-else class="w-3.5 h-3.5 text-violet-400" />
                    </div>
                    <div class="min-w-0">
                      <div class="flex items-center gap-1.5">
                        <span class="text-[10px] text-slate-400 uppercase font-mono">Drafted Player:</span>
                        <span class="text-xs font-bold text-slate-200 truncate">{{ asset.drafted_player_name }}</span>
                      </div>
                      <div class="text-[10px] text-slate-400 font-mono mt-0.5">
                        {{ asset.drafted_player_position }}
                      </div>
                    </div>
                  </div>

                  <div class="text-right font-mono shrink-0">
                    <div class="text-xs font-bold text-emerald-400">
                      {{ asset.drafted_player_points.toFixed(1) }} pts
                    </div>
                  </div>
                </div>
              </div>

              <!-- PLAYER ASSET DETAILS -->
              <div v-else class="space-y-2.5">
                <!-- Player Header & Tags -->
                <div class="flex items-center justify-between gap-2">
                  <div class="flex items-center gap-3 min-w-0">
                    <div class="relative w-10 h-10 rounded-full bg-slate-800 border border-slate-700 overflow-hidden shrink-0 flex items-center justify-center">
                      <img
                        v-if="asset.headshot_url && !failedImages[`player-drawer-${asset.player_id}`]"
                        :src="asset.headshot_url"
                        :alt="asset.full_name"
                        class="w-full h-full object-cover"
                        loading="lazy"
                        @error="handleImageError(`player-drawer-${asset.player_id}`)"
                      />
                      <div
                        v-else
                        class="w-full h-full flex items-center justify-center font-bold text-xs font-mono"
                        :class="getPositionClass(asset.default_position)"
                      >
                        {{ asset.default_position }}
                      </div>
                    </div>

                    <div class="min-w-0">
                      <div class="font-bold text-xs text-slate-100 truncate">{{ asset.full_name }}</div>
                      <div class="text-[11px] text-slate-400 font-mono flex items-center gap-1.5 flex-wrap mt-0.5">
                        <span
                          class="px-1.5 py-0.2 rounded text-[10px] font-bold border"
                          :class="getPositionClass(asset.default_position)"
                        >
                          {{ asset.default_position }}
                        </span>
                        <span>{{ asset.pro_team }}</span>
                        <span
                          v-if="asset.positional_rank"
                          class="px-1.5 py-0.2 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40"
                        >
                          #{{ asset.positional_rank }} {{ asset.default_position }}
                        </span>
                        <span
                          v-if="asset.tier_label"
                          class="px-2 py-0.2 rounded-full text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/40"
                        >
                          {{ asset.tier_label }}
                        </span>
                      </div>
                    </div>
                  </div>

                  <!-- Starter Pts Output -->
                  <div class="text-right font-mono shrink-0">
                    <div class="text-xs font-bold text-emerald-400">
                      {{ asset.post_trade_starter_points.toFixed(1) }} starter pts
                    </div>
                    <div class="text-[10px] text-slate-400">
                      {{ asset.post_trade_weeks_started }} {{ asset.post_trade_weeks_started === 1 ? 'start' : 'starts' }}
                    </div>
                  </div>
                </div>

                <!-- Visual Deployment Strip: Starts vs Bench & Depth -->
                <div class="grid grid-cols-3 gap-2 text-center font-mono text-[11px]">
                  <div class="bg-slate-950/60 rounded-lg py-1.5 px-2 border border-slate-800">
                    <div class="text-[9px] text-slate-400 uppercase font-semibold">Starter Output</div>
                    <div class="font-bold text-emerald-400 mt-0.5">{{ asset.post_trade_starter_points.toFixed(1) }} pts</div>
                  </div>
                  <div class="bg-slate-950/60 rounded-lg py-1.5 px-2 border border-slate-800">
                    <div class="text-[9px] text-slate-400 uppercase font-semibold">Bench Insurance</div>
                    <div class="font-bold text-slate-300 mt-0.5">{{ asset.post_trade_bench_points.toFixed(1) }} pts</div>
                  </div>
                  <div class="bg-slate-950/60 rounded-lg py-1.5 px-2 border border-indigo-500/30">
                    <div class="text-[9px] text-indigo-300 uppercase font-bold">Roster Depth</div>
                    <div class="font-bold text-indigo-400 mt-0.5">+{{ asset.roster_depth_points.toFixed(1) }} pts</div>
                  </div>
                </div>

                <!-- Week-by-Week Game Log -->
                <div class="pt-1.5 border-t border-slate-800/60 space-y-1.5">
                  <div class="text-[10px] font-semibold uppercase tracking-wider text-slate-400 flex items-center justify-between">
                    <span>Weekly Game Log</span>
                    <span v-if="asset.weekly_breakdown?.length" class="text-[10px] font-mono text-slate-400">
                      {{ asset.weekly_breakdown.length }} {{ asset.weekly_breakdown.length === 1 ? 'game' : 'games' }}
                    </span>
                  </div>

                  <div v-if="asset.weekly_breakdown && asset.weekly_breakdown.length > 0" class="flex flex-wrap gap-1.5">
                    <div
                      v-for="wk in asset.weekly_breakdown"
                      :key="`${asset.player_id}-wk-${wk.week}`"
                      class="px-2 py-1 rounded-md text-[10px] font-mono font-medium border flex items-center gap-1.5"
                      :class="
                        !wk.on_acquiring_team
                          ? 'bg-slate-950/50 text-slate-500 border-slate-800 line-through'
                          : wk.slot_position === 'IR' || wk.injury_status === 'INJURY_RESERVE'
                            ? 'bg-rose-950/40 text-rose-300 border-rose-500/50'
                            : wk.injury_status === 'OUT'
                              ? 'bg-amber-950/40 text-amber-300 border-amber-500/40'
                              : wk.is_starter
                                ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30 font-bold'
                                : 'bg-slate-800/80 text-slate-400 border-slate-700/60'
                      "
                    >
                      <span>Wk {{ wk.week }}:</span>
                      <span v-if="!wk.on_acquiring_team">Flipped</span>
                      <span v-else class="flex items-center gap-1">
                        <span>{{ wk.points.toFixed(1) }} pts</span>
                        <span
                          v-if="wk.slot_position === 'IR' || wk.injury_status === 'INJURY_RESERVE'"
                          class="text-[9px] font-bold text-rose-400 uppercase bg-rose-500/20 px-1 py-0.2 rounded"
                        >
                          IR
                        </span>
                        <span
                          v-else-if="wk.injury_status === 'OUT'"
                          class="text-[9px] font-bold text-amber-400 uppercase bg-amber-500/20 px-1 py-0.2 rounded"
                        >
                          OUT
                        </span>
                        <span v-else class="text-[9px] opacity-75">
                          [{{ wk.is_starter ? 'Start' : 'Bench' }}]
                        </span>
                      </span>
                    </div>
                  </div>

                  <div
                    v-else
                    class="text-[11px] text-slate-400 italic py-1 px-2 bg-slate-950/40 rounded-md border border-slate-800/60"
                  >
                    <span v-if="trade.is_projected">Live in-progress season — post-trade game logs accumulate weekly.</span>
                    <span v-else>No weekly post-trade scoring periods recorded for this asset.</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Transaction Meta Footer -->
      <div class="text-[11px] font-mono text-slate-400 text-center pt-2 flex items-center justify-center gap-2">
        <Hash class="w-3.5 h-3.5 text-slate-500" />
        <span>ESPN Transaction ID: {{ trade.espn_transaction_id }}</span>
      </div>
    </div>
  </SwipeDrawer>
</template>
