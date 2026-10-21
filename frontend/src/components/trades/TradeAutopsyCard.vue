<script setup lang="ts">
import { ref } from 'vue';
import type { TradeDetail } from '@/types/api';
import { Trophy, Calendar, ChevronRight, Scale } from 'lucide-vue-next';

const props = defineProps<{
  trade: TradeDetail;
}>();

const emit = defineEmits<{
  (e: 'select', trade: TradeDetail): void;
}>();

// Track headshots that fail to load
const failedImages = ref<Record<number, boolean>>({});

function handleImageError(playerId: number) {
  failedImages.value[playerId] = true;
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
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
    case 'D/ST':
    case 'DST':
      return 'bg-slate-500/20 text-slate-300 border-slate-500/40';
    default:
      return 'bg-slate-700 text-slate-300 border-slate-600';
  }
}

function getWinnerName(winnerId: number | null): string | null {
  if (winnerId == null) return null;
  const winnerSide = props.trade.sides.find((s) => s.manager_id === winnerId);
  return winnerSide ? winnerSide.manager_name : null;
}
</script>

<template>
  <div
    class="stadium-card rounded-2xl border border-slate-800 hover:border-slate-700/80 transition-all overflow-hidden shadow-lg"
  >
    <!-- Trade Card Header -->
    <div
      class="px-4 py-3 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between gap-2 flex-wrap"
    >
      <div class="flex items-center gap-2">
        <span
          class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-xs font-mono font-bold bg-slate-800 text-slate-200 border border-slate-700"
        >
          <Calendar class="w-3 h-3 text-slate-400" />
          <span>{{ trade.season_year }}</span>
          <span v-if="trade.week != null">• Wk {{ trade.week }}</span>
        </span>
        <span v-if="trade.executed_at" class="text-xs text-slate-400">
          {{ formatDate(trade.executed_at) }}
        </span>
      </div>

      <!-- Trade Winner & Point Differential Banner -->
      <div class="flex items-center gap-2">
        <div
          v-if="trade.winner_manager_id != null"
          class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold font-mono bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
        >
          <Trophy class="w-3.5 h-3.5 text-amber-400" />
          <span>{{ getWinnerName(trade.winner_manager_id) }} won (+{{ trade.point_differential.toFixed(1) }} pts)</span>
        </div>
        <div
          v-else
          class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold font-mono bg-slate-800 text-slate-400 border border-slate-700/60"
        >
          <Scale class="w-3 h-3 text-slate-400" />
          <span>Even Value</span>
        </div>

        <button
          type="button"
          class="text-xs text-indigo-400 hover:text-indigo-300 inline-flex items-center gap-0.5 font-medium cursor-pointer"
          @click="emit('select', trade)"
        >
          <span>Autopsy</span>
          <ChevronRight class="w-3.5 h-3.5" />
        </button>
      </div>
    </div>

    <!-- Trade Sides Container (Side-by-side on tablet/desktop, stacked on mobile) -->
    <div class="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-slate-800">
      <div
        v-for="side in trade.sides"
        :key="side.manager_id"
        class="p-4 flex flex-col justify-between gap-3"
        :class="side.manager_id === trade.winner_manager_id ? 'bg-emerald-950/10' : 'bg-transparent'"
      >
        <!-- Side Manager & Total Realized Points Header -->
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <div class="flex items-center gap-1.5">
              <span class="font-bold text-sm text-slate-100 truncate" :title="side.manager_name">
                {{ side.manager_name }}
              </span>
              <span
                v-if="side.manager_id === trade.winner_manager_id"
                class="px-1.5 py-0.2 rounded text-[10px] font-bold uppercase tracking-wider bg-amber-500/20 text-amber-300 border border-amber-500/30"
              >
                Winner
              </span>
            </div>
            <div class="text-xs text-slate-400 truncate mt-0.5" :title="side.team_name">
              {{ side.team_name }}
            </div>
          </div>

          <!-- Total Starter Points Gained Badge -->
          <div class="text-right shrink-0">
            <div class="text-xs font-mono font-black text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-md">
              +{{ side.total_starter_points_gained.toFixed(1) }} pts
            </div>
            <div v-if="side.faab_received > 0" class="text-[10px] font-mono text-amber-400 font-semibold mt-1">
              +${{ side.faab_received }} FAAB
            </div>
          </div>
        </div>

        <!-- Player Assets Acquired -->
        <div class="space-y-2 mt-1">
          <div class="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center justify-between">
            <span>Acquired Assets ({{ side.assets_received.length }})</span>
            <span class="text-[10px] font-mono text-slate-500">Post-Trade Starter Impact</span>
          </div>

          <div
            v-if="side.assets_received.length === 0"
            class="text-xs text-slate-500 italic py-2 text-center bg-slate-900/40 rounded-lg"
          >
            Draft picks or FAAB only
          </div>

          <div
            v-for="asset in side.assets_received"
            :key="asset.player_id"
            class="bg-slate-900/80 rounded-xl p-2.5 border border-slate-800/80 flex items-center justify-between gap-2"
          >
            <!-- Player Headshot + Info -->
            <div class="flex items-center gap-2.5 min-w-0">
              <div class="relative w-10 h-10 rounded-full bg-slate-800 border border-slate-700 overflow-hidden shrink-0 flex items-center justify-center">
                <img
                  v-if="asset.headshot_url && !failedImages[asset.player_id]"
                  :src="asset.headshot_url"
                  :alt="asset.full_name"
                  class="w-full h-full object-cover"
                  loading="lazy"
                  @error="handleImageError(asset.player_id)"
                />
                <!-- Fallback Avatar -->
                <div
                  v-else
                  class="w-full h-full flex items-center justify-center font-bold text-xs font-mono"
                  :class="getPositionClass(asset.default_position)"
                >
                  {{ asset.default_position }}
                </div>
              </div>

              <div class="min-w-0">
                <div class="font-bold text-xs text-slate-100 truncate" :title="asset.full_name">
                  {{ asset.full_name }}
                </div>
                <div class="flex items-center gap-1.5 mt-0.5">
                  <span
                    class="px-1.5 py-0.2 rounded text-[10px] font-mono font-bold border"
                    :class="getPositionClass(asset.default_position)"
                  >
                    {{ asset.default_position }}
                  </span>
                  <span class="text-[10px] text-slate-400 font-semibold font-mono">
                    {{ asset.pro_team }}
                  </span>
                </div>
              </div>
            </div>

            <!-- Realized Starter Value -->
            <div class="text-right shrink-0">
              <div class="text-xs font-mono font-bold text-slate-100">
                {{ asset.post_trade_starter_points.toFixed(1) }} pts
              </div>
              <div class="text-[10px] font-mono text-slate-400">
                {{ asset.post_trade_weeks_started }} {{ asset.post_trade_weeks_started === 1 ? 'start' : 'starts' }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
