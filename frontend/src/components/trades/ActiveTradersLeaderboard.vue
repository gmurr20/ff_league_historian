<script setup lang="ts">
import { ref, computed } from 'vue';
import type { ActiveTrader, TradeDetail } from '@/types/api';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import TradeAutopsyCard from '@/components/trades/TradeAutopsyCard.vue';
import { Info } from 'lucide-vue-next';
import { signed, signedClass, gradeTileClass } from '@/components/trades/tradeUi';
import { useLeagueMeta } from '@/composables/useLeagueMeta';

const props = withDefaults(
  defineProps<{
    traders: ActiveTrader[];
    trades?: TradeDetail[];
    seasonLabel?: string;
    isAllTime?: boolean;
  }>(),
  {
    trades: () => [],
    seasonLabel: 'All-Time Career',
    isAllTime: true,
  }
);

const emit = defineEmits<{
  (e: 'select-trade', trade: TradeDetail): void;
}>();

const { managers } = useLeagueMeta();

const activeManagerMap = computed<Map<number, boolean>>(() => {
  const map = new Map<number, boolean>();
  for (const m of managers.value) {
    map.set(m.id, m.is_active);
  }
  return map;
});

function isTraderActive(t: ActiveTrader): boolean {
  if (t.is_active !== undefined) return t.is_active;
  return activeManagerMap.value.get(t.manager_id) ?? true;
}

// Letter grade rank value for proper sorting (A+ -> 13 down to F -> 1)
const GRADE_RANK: Record<string, number> = {
  'A+': 13,
  A: 12,
  'A-': 11,
  'B+': 10,
  B: 9,
  'B-': 8,
  'C+': 7,
  C: 6,
  'C-': 5,
  'D+': 4,
  D: 3,
  'D-': 2,
  F: 1,
};

function gradeScore(grade: string | null | undefined): number {
  if (!grade) return 0;
  return GRADE_RANK[grade.toUpperCase().trim()] ?? 0;
}

type SortCol = 'rank' | 'franchise' | 'grade' | 'starters' | 'ros' | 'value' | 'volume';
const sortCol = ref<SortCol>('grade');
const sortAsc = ref<boolean>(false);

function toggleSort(col: SortCol) {
  if (sortCol.value === col) {
    sortAsc.value = !sortAsc.value;
  } else {
    sortCol.value = col;
    // Rank & Franchise default ascending; statistical columns default descending (highest is best)
    sortAsc.value = col === 'rank' || col === 'franchise';
  }
}

const sortedTraders = computed(() => {
  const list = [...props.traders];
  list.sort((a, b) => {
    let diff = 0;
    switch (sortCol.value) {
      case 'starters':
        diff = a.net_starter_points_gained - b.net_starter_points_gained || a.total_trades - b.total_trades;
        break;
      case 'ros':
        diff = a.net_ros_points_gained - b.net_ros_points_gained || a.total_trades - b.total_trades;
        break;
      case 'value':
        diff = a.net_trade_score_gained - b.net_trade_score_gained || a.total_trades - b.total_trades;
        break;
      case 'volume':
        diff = a.total_trades - b.total_trades || a.net_trade_score_gained - b.net_trade_score_gained;
        break;
      case 'grade':
        diff =
          gradeScore(a.average_grade) - gradeScore(b.average_grade) ||
          a.net_starter_points_gained - b.net_starter_points_gained ||
          a.total_trades - b.total_trades;
        break;
      case 'franchise': {
        const nameA = a.team_name || a.display_name;
        const nameB = b.team_name || b.display_name;
        diff = nameA.localeCompare(nameB);
        return sortAsc.value ? diff : -diff;
      }
      case 'rank':
      default:
        diff = b.net_starter_points_gained - a.net_starter_points_gained || b.total_trades - a.total_trades;
        return sortAsc.value ? -diff : diff;
    }
    return sortAsc.value ? diff : -diff;
  });
  return list;
});

// Inline accordion
const expandedId = ref<number | null>(null);
const expandedSeason = ref<number | null>(null);

function toggle(managerId: number) {
  expandedId.value = expandedId.value === managerId ? null : managerId;
  expandedSeason.value = null;
}

function tradesFor(managerId: number): TradeDetail[] {
  return (props.trades ?? []).filter((t) => t.sides.some((s) => s.manager_id === managerId));
}

function seasonsFor(managerId: number): number[] {
  return Array.from(new Set(tradesFor(managerId).map((t) => t.season_year))).sort((a, b) => b - a);
}

function visibleTradesFor(managerId: number): TradeDetail[] {
  const list = tradesFor(managerId);
  return expandedSeason.value == null ? list : list.filter((t) => t.season_year === expandedSeason.value);
}

function movementLine(t: ActiveTrader): string {
  const parts = [`+${t.players_acquired}/\u2212${t.players_traded_away} players`];
  if (t.picks_acquired || t.picks_traded_away) parts.push(`+${t.picks_acquired}/\u2212${t.picks_traded_away} picks`);
  if (t.faab_net) parts.push(`${t.faab_net > 0 ? '+' : '\u2212'}$${Math.abs(t.faab_net)} FAAB`);
  return parts.join(' · ');
}
</script>

<template>
  <div class="space-y-4">
    <!-- Standings-Style Trader ROI Table -->
    <div class="rounded-xl border border-slate-800/90 bg-[#0b101b] overflow-hidden shadow-lg">
      <!-- Column Headers -->
      <div
        class="grid items-center px-2.5 sm:px-3.5 py-2.5 bg-slate-900/90 border-b border-slate-800/90 text-[10px] font-mono uppercase tracking-wider text-slate-400 select-none grid-cols-[18px_1fr_28px_46px_44px_42px_28px] sm:grid-cols-[28px_1fr_48px_68px_68px_64px_52px] gap-1 sm:gap-2"
      >
        <button
          type="button"
          class="text-left font-bold transition-colors cursor-pointer"
          :class="sortCol === 'rank' ? 'text-amber-400' : 'hover:text-slate-200'"
          @click="toggleSort('rank')"
          title="Sort by Rank"
        >
          #<span v-if="sortCol === 'rank'" class="text-[9px] ml-0.5">{{ sortAsc ? '▲' : '▼' }}</span>
        </button>

        <button
          type="button"
          class="text-left font-bold transition-colors cursor-pointer truncate"
          :class="sortCol === 'franchise' ? 'text-amber-400' : 'hover:text-slate-200'"
          @click="toggleSort('franchise')"
        >
          Franchise<span v-if="sortCol === 'franchise'" class="text-[9px] ml-0.5">{{ sortAsc ? '▲' : '▼' }}</span>
        </button>

        <button
          type="button"
          class="text-center font-bold transition-colors cursor-pointer"
          :class="sortCol === 'grade' ? 'text-amber-400' : 'hover:text-slate-200'"
          @click="toggleSort('grade')"
          title="Average Trade Letter Grade"
        >
          <span class="sm:hidden">Grd</span>
          <span class="hidden sm:inline">Grade</span>
          <span v-if="sortCol === 'grade'" class="text-[9px] ml-0.5">{{ sortAsc ? '▲' : '▼' }}</span>
        </button>

        <button
          type="button"
          class="text-right font-bold transition-colors cursor-pointer"
          :class="sortCol === 'starters' ? 'text-emerald-400' : 'hover:text-slate-200'"
          @click="toggleSort('starters')"
          title="Net Points Scored While in Starting Lineup"
        >
          <span class="sm:hidden">Start</span>
          <span class="hidden sm:inline">Starters</span>
          <span v-if="sortCol === 'starters'" class="text-[9px] ml-0.5">{{ sortAsc ? '▲' : '▼' }}</span>
        </button>

        <button
          type="button"
          class="text-right font-bold transition-colors cursor-pointer"
          :class="sortCol === 'ros' ? 'text-cyan-400' : 'hover:text-slate-200'"
          @click="toggleSort('ros')"
          title="Net Rest-of-Season Total Points (Starters + Bench)"
        >
          <span class="sm:hidden">ROS</span>
          <span class="hidden sm:inline">ROS Pts</span>
          <span v-if="sortCol === 'ros'" class="text-[9px] ml-0.5">{{ sortAsc ? '▲' : '▼' }}</span>
        </button>

        <button
          type="button"
          class="text-right font-bold transition-colors cursor-pointer"
          :class="sortCol === 'value' ? 'text-amber-400' : 'hover:text-slate-200'"
          @click="toggleSort('value')"
          title="Composite Trade Value Index Score"
        >
          Value<span v-if="sortCol === 'value'" class="text-[9px] ml-0.5">{{ sortAsc ? '▲' : '▼' }}</span>
        </button>

        <button
          type="button"
          class="text-right font-bold transition-colors cursor-pointer"
          :class="sortCol === 'volume' ? 'text-purple-400' : 'hover:text-slate-200'"
          @click="toggleSort('volume')"
          title="Total Completed Bilateral Trades"
        >
          <span class="sm:hidden">Vol</span>
          <span class="hidden sm:inline">Trades</span>
          <span v-if="sortCol === 'volume'" class="text-[9px] ml-0.5">{{ sortAsc ? '▲' : '▼' }}</span>
        </button>
      </div>

      <!-- Trader Rows -->
      <div class="divide-y divide-slate-800/60">
        <template v-for="(trader, idx) in sortedTraders" :key="trader.manager_id">
          <div
            role="button"
            tabindex="0"
            :aria-expanded="expandedId === trader.manager_id"
            class="relative transition-colors cursor-pointer select-none active:bg-slate-800/70 hover:bg-slate-900/70"
            :class="[
              isAllTime && !isTraderActive(trader) ? 'opacity-65 hover:opacity-100 bg-slate-950/40' : '',
              expandedId === trader.manager_id ? 'bg-slate-800/40' : '',
            ]"
            @click="toggle(trader.manager_id)"
            @keydown.enter="toggle(trader.manager_id)"
            @keydown.space.prevent="toggle(trader.manager_id)"
          >
            <!-- Left edge accent: Amber for #1, Emerald for top 3 -->
            <span
              class="absolute left-0 inset-y-0 w-[3px]"
              :class="
                isAllTime && !isTraderActive(trader)
                  ? 'bg-transparent'
                  : idx === 0
                    ? 'bg-amber-400'
                    : idx < 3
                      ? 'bg-emerald-500/80'
                      : 'bg-transparent'
              "
            />

            <!-- Row content grid -->
            <div
              class="grid items-center min-h-[46px] px-2.5 sm:px-3.5 py-2.5 grid-cols-[18px_1fr_28px_46px_44px_42px_28px] sm:grid-cols-[28px_1fr_48px_68px_68px_64px_52px] gap-1 sm:gap-2"
            >
              <!-- Rank -->
              <span
                class="font-mono text-xs font-bold tabular-nums"
                :class="
                  idx === 0
                    ? 'text-amber-300'
                    : idx === 1
                      ? 'text-slate-300'
                      : idx === 2
                        ? 'text-amber-600'
                        : 'text-slate-500'
                "
              >
                {{ idx + 1 }}
              </span>

              <!-- Franchise -->
              <div class="flex items-center gap-2 min-w-0 pr-1">
                <TeamAvatar
                  :src="trader.avatar_url"
                  :name="trader.team_name || trader.display_name"
                  size="xs"
                  rounded="lg"
                />
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-1.5 min-w-0">
                    <span class="text-xs sm:text-sm font-semibold text-slate-100 truncate leading-tight">
                      {{ trader.team_name || trader.display_name }}
                    </span>
                    <!-- Inactive Badge in All-Time Mode -->
                    <span
                      v-if="isAllTime && !isTraderActive(trader)"
                      class="inline-flex items-center text-[8px] font-mono font-bold uppercase px-1 py-0.2 rounded bg-slate-800 text-slate-400 border border-slate-700/80 shrink-0"
                    >
                      Inactive
                    </span>
                  </div>
                  <div class="text-[10px] text-slate-500 truncate leading-tight mt-0.5">
                    {{ trader.display_name }}
                  </div>
                </div>
              </div>

              <!-- Grade -->
              <div class="flex items-center justify-center">
                <span
                  class="w-6 h-5 sm:w-7 sm:h-6 rounded flex items-center justify-center text-[10px] sm:text-xs font-black tracking-tight shrink-0 font-mono"
                  :class="gradeTileClass(trader.average_grade)"
                  :title="`Avg Grade ${trader.average_grade || '–'}`"
                >
                  {{ trader.average_grade || '–' }}
                </span>
              </div>

              <!-- Starters -->
              <div
                class="text-right font-mono font-semibold tabular-nums text-xs sm:text-sm"
                :class="signedClass(trader.net_starter_points_gained)"
              >
                {{ signed(trader.net_starter_points_gained) }}
              </div>

              <!-- ROS -->
              <div
                class="text-right font-mono font-semibold tabular-nums text-xs sm:text-sm"
                :class="signedClass(trader.net_ros_points_gained)"
              >
                {{ signed(trader.net_ros_points_gained) }}
              </div>

              <!-- Value -->
              <div
                class="text-right font-mono font-semibold tabular-nums text-xs sm:text-sm"
                :class="signedClass(trader.net_trade_score_gained)"
              >
                {{ signed(trader.net_trade_score_gained) }}
              </div>

              <!-- Volume -->
              <div class="text-right font-mono font-semibold tabular-nums text-xs sm:text-sm text-slate-200">
                {{ trader.total_trades }}
              </div>
            </div>
          </div>

          <!-- Expanded Accordion: Individual trade autopsy list & breakdown -->
          <div v-if="expandedId === trader.manager_id" class="px-3 sm:px-4 py-3 space-y-3 bg-slate-950/70 border-t border-slate-800/60">
            <!-- Summary bar -->
            <div class="flex flex-wrap items-center justify-between gap-2 p-2.5 rounded-xl bg-slate-900/80 border border-slate-800/80 text-xs">
              <div class="flex items-center gap-3">
                <span class="font-mono text-slate-300 font-semibold">
                  {{ trader.trades_won }}W - {{ trader.trades_lost }}L - {{ trader.trades_tied }}T
                </span>
                <span class="text-slate-500">·</span>
                <span class="text-slate-400 font-mono">{{ (trader.win_rate * 100).toFixed(0) }}% win rate</span>
              </div>
              <span class="text-[11px] font-mono text-slate-400 tabular-nums">
                {{ movementLine(trader) }}
              </span>
            </div>

            <!-- Season filter pills (wraps, never scrolls horizontally) -->
            <div v-if="seasonsFor(trader.manager_id).length > 1" class="flex flex-wrap gap-1.5 pt-1">
              <button
                type="button"
                class="h-7 px-2.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer"
                :class="expandedSeason == null ? 'bg-slate-700 text-white' : 'bg-slate-900 text-slate-400 hover:text-slate-200'"
                @click="expandedSeason = null"
              >
                All ({{ tradesFor(trader.manager_id).length }})
              </button>
              <button
                v-for="year in seasonsFor(trader.manager_id)"
                :key="year"
                type="button"
                class="h-7 px-2.5 rounded-lg text-xs font-mono font-semibold transition-colors cursor-pointer"
                :class="expandedSeason === year ? 'bg-slate-700 text-white' : 'bg-slate-900 text-slate-400 hover:text-slate-200'"
                @click="expandedSeason = year"
              >
                {{ year }}
              </button>
            </div>

            <!-- Trade autopsy cards for this franchise (no edit button) -->
            <div v-if="visibleTradesFor(trader.manager_id).length > 0" class="space-y-2.5 pt-1">
              <TradeAutopsyCard
                v-for="trade in visibleTradesFor(trader.manager_id)"
                :key="trade.trade_id"
                :trade="trade"
                @select="emit('select-trade', $event)"
              />
            </div>
            <p v-else class="text-xs text-slate-500 italic py-2">
              No individual trade autopsies available for this filter.
            </p>
          </div>
        </template>
      </div>
    </div>

    <!-- Metric Explanations Footer -->
    <footer class="rounded-xl border border-slate-800/90 bg-slate-900/40 p-3.5 sm:p-4 space-y-3">
      <div class="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-300">
        <Info class="w-4 h-4 text-emerald-400 shrink-0" />
        <span>Understanding Trader ROI Metrics</span>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs">
        <!-- Value -->
        <div class="p-3 rounded-lg bg-slate-950/60 border border-slate-800/60 space-y-1">
          <div class="font-semibold text-slate-200 flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-wide">
            <span class="w-2 h-2 rounded-full bg-amber-400 shrink-0" />
            Value (Trade Index)
          </div>
          <p class="text-slate-400 text-[11px] leading-relaxed">
            Composite trade performance rating evaluating realized value. Incorporates starter points weighted by positional scarcity (VORP), tier multipliers, roster depth/holding time, draft pick capital, and injury/IR penalties.
          </p>
        </div>

        <!-- ROS -->
        <div class="p-3 rounded-lg bg-slate-950/60 border border-slate-800/60 space-y-1">
          <div class="font-semibold text-slate-200 flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-wide">
            <span class="w-2 h-2 rounded-full bg-cyan-400 shrink-0" />
            ROS (Rest of Season)
          </div>
          <p class="text-slate-400 text-[11px] leading-relaxed">
            Total post-trade scoring impact across all remaining weeks. Measures the net total fantasy points produced by incoming assets versus outgoing assets across both starting lineups and bench depth.
          </p>
        </div>

        <!-- Starters -->
        <div class="p-3 rounded-lg bg-slate-950/60 border border-slate-800/60 space-y-1">
          <div class="font-semibold text-slate-200 flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-wide">
            <span class="w-2 h-2 rounded-full bg-emerald-400 shrink-0" />
            Starters Net
          </div>
          <p class="text-slate-400 text-[11px] leading-relaxed">
            Direct lineup impact. Only counts fantasy points scored while actively placed in a starting lineup post-trade, minus starter points scored by players traded away.
          </p>
        </div>

        <!-- Volume / Count -->
        <div class="p-3 rounded-lg bg-slate-950/60 border border-slate-800/60 space-y-1">
          <div class="font-semibold text-slate-200 flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-wide">
            <span class="w-2 h-2 rounded-full bg-purple-400 shrink-0" />
            Volume (Trades)
          </div>
          <p class="text-slate-400 text-[11px] leading-relaxed">
            Total completed bilateral trades. Tapping any franchise row expands their individual deal autopsies, win-loss trade record, and asset movements.
          </p>
        </div>
      </div>
    </footer>
  </div>
</template>
