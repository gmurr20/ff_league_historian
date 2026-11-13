<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import type { SideBetDetail, SideBetSideSummary, SideBetTeamBreakdown, SideBetPlayerEntry } from '@/types/api';
import SwipeDrawer from '@/components/ui/SwipeDrawer.vue';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import { Trophy, Flame, Users } from 'lucide-vue-next';

const props = defineProps<{
  modelValue: boolean;
  bet: SideBetDetail | null;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void;
}>();

const activeMobileSide = ref<'A' | 'B'>('A');

watch(
  () => props.bet,
  () => {
    activeMobileSide.value = 'A';
  }
);

function formatSpread(spread: number): string {
  if (spread === 0) return 'PK';
  return spread > 0 ? `+${spread.toFixed(1)}` : `${spread.toFixed(1)}`;
}

function getSideDisplayName(side: SideBetSideSummary): string {
  if (side.teams.length === 1) {
    return side.teams[0].team_name;
  }
  if (side.side_name && side.side_name !== 'Side A' && side.side_name !== 'Side B') {
    return side.side_name;
  }
  return side.teams.map((t) => t.team_abbrev || t.manager_name.split(' ')[0]).join(' + ');
}

const drawerTitle = computed(() => {
  if (!props.bet) return 'Side Bet Boxscore';
  if (props.bet.title && props.bet.title.trim()) {
    return props.bet.title;
  }
  return `${getSideDisplayName(props.bet.side_a)} vs. ${getSideDisplayName(props.bet.side_b)}`;
});

const drawerSubtitle = computed(() => {
  if (!props.bet) return '';
  const stakeStr = props.bet.stake_amount > 0 ? ` · $${props.bet.stake_amount.toFixed(0)} Stake` : '';
  const modeStr = props.bet.scoring_mode === 'MAX_PF' ? ' · Max PF' : props.bet.scoring_mode === 'BENCH' ? ' · Bench' : '';
  return `Season ${props.bet.season_year} · Week ${props.bet.week}${stakeStr}${modeStr}`;
});

const activeLeader = computed<'A' | 'B' | 'PUSH' | null>(() => {
  if (!props.bet) return null;
  if (props.bet.is_completed) return props.bet.winning_side;
  if (props.bet.side_a.raw_points === 0 && props.bet.side_b.raw_points === 0) return null;
  return props.bet.currently_covering;
});

const coverMarginBannerText = computed(() => {
  if (!props.bet) return '';
  const absMargin = Math.abs(props.bet.margin_vs_spread).toFixed(2);
  const nameA = getSideDisplayName(props.bet.side_a);
  const nameB = getSideDisplayName(props.bet.side_b);

  if (props.bet.is_completed) {
    if (props.bet.winning_side === 'A') {
      return `${nameA} covered ${formatSpread(props.bet.side_a.spread_applied)} by +${absMargin} pts`;
    }
    if (props.bet.winning_side === 'B') {
      return `${nameB} covered ${formatSpread(props.bet.side_b.spread_applied)} by +${absMargin} pts`;
    }
    return `Final Push — Exact 0.00 spread tie`;
  }

  if (props.bet.currently_covering === 'A') {
    return `${nameA} currently covering ${formatSpread(props.bet.side_a.spread_applied)} by +${absMargin} pts`;
  }
  if (props.bet.currently_covering === 'B') {
    return `${nameB} currently covering ${formatSpread(props.bet.side_b.spread_applied)} by +${absMargin} pts`;
  }
  return `Currently tied against the spread`;
});

const SLOT_ORDER: Record<string, number> = {
  QB: 1,
  RB: 2,
  WR: 3,
  TE: 4,
  FLEX: 5,
  'RB/WR/TE': 5,
  OP: 6,
  'D/ST': 7,
  DST: 7,
  K: 8,
  BE: 9,
  BENCH: 9,
  IR: 10,
};

function sortStarters(players: SideBetPlayerEntry[]): SideBetPlayerEntry[] {
  return [...players].sort((a, b) => {
    const orderA = SLOT_ORDER[a.slot_position] ?? 99;
    const orderB = SLOT_ORDER[b.slot_position] ?? 99;
    return orderA - orderB || b.actual_points - a.actual_points;
  });
}

function getSlotBadgeColor(slot: string): string {
  const normalized = slot.toUpperCase();
  if (normalized === 'QB') return 'bg-rose-500/20 text-rose-300 border-rose-500/35';
  if (normalized === 'RB') return 'bg-emerald-500/20 text-emerald-300 border-emerald-500/35';
  if (normalized === 'WR') return 'bg-sky-500/20 text-sky-300 border-sky-500/35';
  if (normalized === 'TE') return 'bg-amber-500/20 text-amber-300 border-amber-500/35';
  if (normalized === 'FLEX' || normalized === 'RB/WR/TE') return 'bg-violet-500/20 text-violet-300 border-violet-500/35';
  if (normalized === 'D/ST' || normalized === 'DST') return 'bg-teal-500/20 text-teal-300 border-teal-500/35';
  if (normalized === 'K') return 'bg-indigo-500/20 text-indigo-300 border-indigo-500/35';
  return 'bg-slate-800 text-slate-400 border-slate-700';
}

function getDisplaySlot(slot: string): string {
  if (slot === 'RB/WR/TE') return 'FLEX';
  if (slot === 'DST') return 'D/ST';
  return slot;
}

function getInjuryShort(status: string | null): string | null {
  if (!status || status === 'ACTIVE' || status === 'NORMAL') return null;
  if (status === 'QUESTIONABLE') return 'Q';
  if (status === 'DOUBTFUL') return 'D';
  if (status === 'OUT') return 'OUT';
  if (status === 'INJURY_RESERVE' || status === 'IR') return 'IR';
  if (status === 'SUSPENSION') return 'SUSP';
  return status.slice(0, 3).toUpperCase();
}

const sidesList = computed<{ key: 'A' | 'B'; summary: SideBetSideSummary }[]>(() => {
  if (!props.bet) return [];
  return [
    { key: 'A', summary: props.bet.side_a },
    { key: 'B', summary: props.bet.side_b },
  ];
});

function getTeamInitials(team: SideBetTeamBreakdown): string {
  return team.team_abbrev || team.team_name.slice(0, 2).toUpperCase();
}
</script>

<template>
  <SwipeDrawer
    :model-value="modelValue"
    :title="drawerTitle"
    :subtitle="drawerSubtitle"
    max-height="max-h-[90vh]"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-if="bet" class="space-y-4 pb-6">
      <!-- Top Scoreboard & Spread Adjustment Summary Card -->
      <div class="rounded-2xl border border-slate-800 bg-[#0b101b] p-3.5 space-y-3 shadow-lg">
        <div class="grid grid-cols-2 gap-3">
          <!-- Side A Summary -->
          <div
            class="rounded-xl p-3 border transition-colors"
            :class="
              activeLeader === 'A'
                ? 'bg-emerald-950/30 border-emerald-500/45'
                : 'bg-slate-900/75 border-slate-800'
            "
          >
            <div class="flex items-center justify-between gap-1.5">
              <span class="text-[10px] font-mono font-bold uppercase tracking-wider text-slate-400">
                Side A · {{ bet.side_a.teams.length }} {{ bet.side_a.teams.length === 1 ? 'Team' : 'Teams' }}
              </span>
              <span
                class="px-1.5 py-0.2 rounded text-[10px] font-mono font-black border"
                :class="
                  bet.side_a.spread_applied < 0
                    ? 'bg-indigo-500/15 text-indigo-300 border-indigo-500/35'
                    : bet.side_a.spread_applied > 0
                    ? 'bg-amber-500/15 text-amber-300 border-amber-500/35'
                    : 'bg-slate-800 text-slate-400 border-slate-700'
                "
              >
                {{ formatSpread(bet.side_a.spread_applied) }}
              </span>
            </div>

            <div class="text-xs sm:text-sm font-bold text-slate-100 truncate mt-1">
              {{ getSideDisplayName(bet.side_a) }}
            </div>

            <div class="mt-2 flex items-baseline justify-between gap-2 font-mono tabular-nums">
              <div>
                <div
                  class="text-lg sm:text-xl font-black leading-none"
                  :class="activeLeader === 'A' ? 'text-emerald-400' : 'text-slate-100'"
                >
                  {{ bet.side_a.raw_points.toFixed(2) }}
                </div>
                <div class="text-[10px] text-slate-500 mt-0.5">Raw Starter Pts</div>
              </div>

              <div v-if="bet.spread_side_a !== 0" class="text-right">
                <div class="text-xs sm:text-sm font-bold text-slate-200 leading-none">
                  {{ bet.side_a.adjusted_points.toFixed(2) }}
                </div>
                <div class="text-[10px] text-slate-500 mt-0.5">w/ Spread</div>
              </div>
            </div>
          </div>

          <!-- Side B Summary -->
          <div
            class="rounded-xl p-3 border transition-colors"
            :class="
              activeLeader === 'B'
                ? 'bg-emerald-950/30 border-emerald-500/45'
                : 'bg-slate-900/75 border-slate-800'
            "
          >
            <div class="flex items-center justify-between gap-1.5">
              <span class="text-[10px] font-mono font-bold uppercase tracking-wider text-slate-400">
                Side B · {{ bet.side_b.teams.length }} {{ bet.side_b.teams.length === 1 ? 'Team' : 'Teams' }}
              </span>
              <span
                class="px-1.5 py-0.2 rounded text-[10px] font-mono font-black border"
                :class="
                  bet.side_b.spread_applied < 0
                    ? 'bg-indigo-500/15 text-indigo-300 border-indigo-500/35'
                    : bet.side_b.spread_applied > 0
                    ? 'bg-amber-500/15 text-amber-300 border-amber-500/35'
                    : 'bg-slate-800 text-slate-400 border-slate-700'
                "
              >
                {{ formatSpread(bet.side_b.spread_applied) }}
              </span>
            </div>

            <div class="text-xs sm:text-sm font-bold text-slate-100 truncate mt-1">
              {{ getSideDisplayName(bet.side_b) }}
            </div>

            <div class="mt-2 flex items-baseline justify-between gap-2 font-mono tabular-nums">
              <div>
                <div
                  class="text-lg sm:text-xl font-black leading-none"
                  :class="activeLeader === 'B' ? 'text-emerald-400' : 'text-slate-100'"
                >
                  {{ bet.side_b.raw_points.toFixed(2) }}
                </div>
                <div class="text-[10px] text-slate-500 mt-0.5">Raw Starter Pts</div>
              </div>

              <div class="text-right">
                <div class="text-xs sm:text-sm font-bold text-slate-300 leading-none">
                  {{ bet.side_b.projected_points.toFixed(1) }}
                </div>
                <div class="text-[10px] text-slate-500 mt-0.5">Projected</div>
              </div>
            </div>
          </div>
        </div>

        <!-- Cover Verdict Strip -->
        <div
          class="rounded-xl px-3 py-2 border flex items-center justify-between gap-2 text-xs font-mono"
          :class="
            activeLeader
              ? 'bg-emerald-950/30 border-emerald-500/35 text-emerald-300'
              : 'bg-slate-900 border-slate-800 text-slate-300'
          "
        >
          <div class="flex items-center gap-1.5 min-w-0">
            <Trophy v-if="bet.is_completed && activeLeader" class="w-3.5 h-3.5 text-amber-400 shrink-0" />
            <Flame v-else class="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            <span class="font-bold truncate">{{ coverMarginBannerText }}</span>
          </div>

          <span
            v-if="bet.stake_amount > 0"
            class="px-2 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30 text-[10px] font-black shrink-0"
          >
            ${{ bet.stake_amount.toFixed(0) }} / Team
          </span>
        </div>
      </div>

      <!-- Mobile Side A / Side B Switcher (Hidden on sm: where 2-column grid displays both) -->
      <div class="sm:hidden grid grid-cols-2 gap-1.5 p-1 rounded-xl bg-slate-900/90 border border-slate-800">
        <button
          type="button"
          class="min-h-[42px] px-2.5 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center justify-between gap-1.5 cursor-pointer"
          :class="
            activeMobileSide === 'A'
              ? 'bg-slate-800 text-white border border-slate-700 shadow-sm'
              : 'text-slate-400 hover:text-slate-200'
          "
          @click="activeMobileSide = 'A'"
        >
          <span class="truncate">{{ getSideDisplayName(bet.side_a) }}</span>
          <span class="font-mono text-[11px] text-emerald-400 shrink-0">
            {{ bet.side_a.raw_points.toFixed(1) }}
          </span>
        </button>

        <button
          type="button"
          class="min-h-[42px] px-2.5 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center justify-between gap-1.5 cursor-pointer"
          :class="
            activeMobileSide === 'B'
              ? 'bg-slate-800 text-white border border-slate-700 shadow-sm'
              : 'text-slate-400 hover:text-slate-200'
          "
          @click="activeMobileSide = 'B'"
        >
          <span class="truncate">{{ getSideDisplayName(bet.side_b) }}</span>
          <span class="font-mono text-[11px] text-emerald-400 shrink-0">
            {{ bet.side_b.raw_points.toFixed(1) }}
          </span>
        </button>
      </div>

      <!-- Team-Grouped Player Boxscores (1 col on mobile toggled by switcher, 2 cols on sm:) -->
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 items-start">
        <div
          v-for="sideItem in sidesList"
          :key="sideItem.key"
          class="space-y-3"
          :class="activeMobileSide === sideItem.key ? 'block' : 'hidden sm:block'"
        >
          <!-- Side Column Header -->
          <div class="flex items-center justify-between px-1">
            <div class="flex items-center gap-1.5 min-w-0">
              <Users class="w-3.5 h-3.5 text-indigo-400 shrink-0" />
              <h3 class="text-xs font-mono font-black uppercase tracking-wider text-slate-200 truncate">
                Side {{ sideItem.key }} · {{ getSideDisplayName(sideItem.summary) }}
              </h3>
            </div>
            <span class="text-xs font-mono font-bold text-slate-400 tabular-nums shrink-0">
              {{ sideItem.summary.raw_points.toFixed(2) }} pts
            </span>
          </div>

          <!-- Participating Teams in this Side -->
          <div
            v-for="team in sideItem.summary.teams"
            :key="team.team_id"
            class="rounded-xl border border-slate-800/90 bg-[#0b101b] overflow-hidden shadow-md"
          >
            <!-- Prominent Franchise Header -->
            <div class="px-3 py-2.5 bg-slate-900/95 border-b border-slate-800/90 flex items-center justify-between gap-2">
              <div class="flex items-center gap-2.5 min-w-0">
                <TeamAvatar :src="team.logo_url" :name="team.team_name" size="sm" rounded="lg" />
                <div class="min-w-0">
                  <div class="flex items-center gap-1.5">
                    <span class="text-xs sm:text-sm font-bold text-slate-100 truncate">
                      {{ team.team_name }}
                    </span>
                    <span class="text-[9.5px] font-mono text-slate-500 uppercase">
                      ({{ getTeamInitials(team) }})
                    </span>
                  </div>
                  <div class="text-[10px] text-slate-400 truncate">
                    {{ team.manager_name }}
                  </div>
                </div>
              </div>

              <div class="text-right font-mono tabular-nums shrink-0">
                <div class="text-sm font-black text-emerald-400 leading-none">
                  {{ team.starter_points.toFixed(2) }}
                </div>
                <div class="text-[10px] text-slate-500 mt-0.5">
                  Proj {{ team.projected_points.toFixed(1) }}
                </div>
              </div>
            </div>

            <!-- Starters List -->
            <div v-if="team.starters && team.starters.length > 0" class="divide-y divide-slate-800/60">
              <div
                v-for="player in sortStarters(team.starters)"
                :key="`${team.team_id}-${player.player_id}-${player.slot_position}`"
                class="px-3 py-2 flex items-center justify-between gap-2 hover:bg-slate-900/50 transition-colors"
              >
                <div class="flex items-center gap-2 min-w-0">
                  <!-- Position Slot Badge -->
                  <span
                    class="w-10 text-center py-0.5 rounded text-[9.5px] font-mono font-black uppercase border shrink-0"
                    :class="getSlotBadgeColor(player.slot_position)"
                  >
                    {{ getDisplaySlot(player.slot_position) }}
                  </span>

                  <!-- Player Headshot -->
                  <div class="w-7 h-7 rounded-full bg-slate-800 border border-slate-700/80 overflow-hidden shrink-0 flex items-center justify-center">
                    <img
                      v-if="player.headshot_url"
                      :src="player.headshot_url"
                      :alt="player.full_name"
                      class="w-full h-full object-cover"
                      loading="lazy"
                    />
                    <span v-else class="text-[9px] font-mono font-bold text-slate-400">
                      {{ player.default_position }}
                    </span>
                  </div>

                  <!-- Player Name, NFL Team & Injury Status -->
                  <div class="min-w-0">
                    <div class="flex items-center gap-1.5 min-w-0">
                      <span class="text-xs font-bold text-slate-100 truncate">
                        {{ player.full_name }}
                      </span>
                      <span
                        v-if="getInjuryShort(player.injury_status)"
                        class="px-1 py-0.1 rounded text-[8.5px] font-mono font-black uppercase bg-rose-500/20 text-rose-300 border border-rose-500/35 shrink-0"
                      >
                        {{ getInjuryShort(player.injury_status) }}
                      </span>
                    </div>
                    <div class="text-[10px] font-mono text-slate-500">
                      {{ player.pro_team }} · {{ player.default_position }}
                    </div>
                  </div>
                </div>

                <!-- Player Points (Projected & Actual) -->
                <div class="text-right font-mono tabular-nums shrink-0">
                  <div
                    class="text-xs sm:text-sm font-bold leading-none"
                    :class="player.actual_points > 0 ? 'text-slate-100' : 'text-slate-400'"
                  >
                    {{ player.actual_points.toFixed(2) }}
                  </div>
                  <div class="text-[9.5px] text-slate-500 mt-0.5">
                    Proj {{ player.projected_points.toFixed(1) }}
                  </div>
                </div>
              </div>
            </div>

            <div v-else class="p-4 text-center text-xs font-mono text-slate-500">
              No starting lineup data recorded for this week.
            </div>
          </div>
        </div>
      </div>
    </div>
  </SwipeDrawer>
</template>
