<script setup lang="ts">
import { computed } from 'vue';
import type { SideBetDetail, SideBetSideSummary } from '@/types/api';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import { ChevronRight, Users, Trophy, Flame } from 'lucide-vue-next';

const props = defineProps<{
  bet: SideBetDetail;
  showSeasonBadge?: boolean;
}>();

const emit = defineEmits<{
  (e: 'select', bet: SideBetDetail): void;
}>();

function formatSpread(spread: number): string {
  if (spread === 0) return 'PK';
  return spread > 0 ? `+${spread.toFixed(1)}` : `${spread.toFixed(1)}`;
}

function formatCash(amount: number): string {
  return `$${Math.abs(amount).toFixed(0)}`;
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

function getSideSubtitle(side: SideBetSideSummary): string {
  if (side.teams.length === 1) {
    return side.teams[0].manager_name;
  }
  return `${side.teams.length} Teams · ${side.teams.map((t) => t.manager_name).join(', ')}`;
}

const isPush = computed(() => {
  return (props.bet.is_completed && props.bet.winning_side === 'PUSH') ||
    (!props.bet.is_completed && props.bet.currently_covering === 'PUSH' && (props.bet.side_a.raw_points > 0 || props.bet.side_b.raw_points > 0));
});

const activeLeader = computed<'A' | 'B' | 'PUSH' | null>(() => {
  if (props.bet.is_completed) {
    return props.bet.winning_side;
  }
  if (props.bet.side_a.raw_points === 0 && props.bet.side_b.raw_points === 0) {
    return null;
  }
  return props.bet.currently_covering;
});

// Tug-of-war percentage for Side A (clamped 12% to 88%)
const sideATugPercent = computed<number>(() => {
  const adjA = props.bet.side_a.adjusted_points;
  const rawB = props.bet.side_b.raw_points;
  const total = adjA + rawB;
  if (total <= 0) {
    // Use projected if no live points yet
    const projA = props.bet.side_a.projected_adjusted_points;
    const projB = props.bet.side_b.projected_points;
    const projTotal = projA + projB;
    if (projTotal <= 0) return 50;
    const pDiff = projA - projB;
    return Math.min(88, Math.max(12, 50 + pDiff * 1.25));
  }
  const margin = props.bet.margin_vs_spread;
  return Math.min(88, Math.max(12, 50 + margin * 1.4));
});

const coverSummaryLabel = computed<string>(() => {
  const absMargin = Math.abs(props.bet.margin_vs_spread).toFixed(2);
  const sideAName = getSideDisplayName(props.bet.side_a);
  const sideBName = getSideDisplayName(props.bet.side_b);

  if (props.bet.is_completed) {
    if (props.bet.winning_side === 'A') {
      return `${sideAName} covered by +${absMargin} pts`;
    }
    if (props.bet.winning_side === 'B') {
      return `${sideBName} covered by +${absMargin} pts`;
    }
    return `Exact Push (0.00 margin vs spread)`;
  }

  if (props.bet.side_a.raw_points === 0 && props.bet.side_b.raw_points === 0) {
    const projMargin = Math.abs(props.bet.projected_margin_vs_spread).toFixed(1);
    if (props.bet.projected_margin_vs_spread > 0) {
      return `Proj: ${sideAName} covers by +${projMargin} pts`;
    }
    if (props.bet.projected_margin_vs_spread < 0) {
      return `Proj: ${sideBName} covers by +${projMargin} pts`;
    }
    return `Projected dead even vs spread`;
  }

  if (props.bet.currently_covering === 'A') {
    return `${sideAName} covering by +${absMargin} pts`;
  }
  if (props.bet.currently_covering === 'B') {
    return `${sideBName} covering by +${absMargin} pts`;
  }
  return `Tied vs spread (0.00 margin)`;
});

const displayTitle = computed<string>(() => {
  if (props.bet.title && props.bet.title.trim()) {
    return props.bet.title;
  }
  const countA = props.bet.side_a.teams.length;
  const countB = props.bet.side_b.teams.length;
  if (countA === 1 && countB === 1) {
    return 'Head-to-Head Side Bet';
  }
  return `${countA}v${countB} Team Group Wager`;
});
</script>

<template>
  <div
    role="button"
    tabindex="0"
    class="rounded-2xl border border-slate-800/90 bg-[#0b101b] hover:border-slate-700/90 transition-all shadow-lg overflow-hidden cursor-pointer select-none group"
    @click="emit('select', bet)"
    @keydown.enter="emit('select', bet)"
  >
    <!-- Top Header Strip: Wk Badge, Bet Title, Stake & Status Pill -->
    <div class="px-3.5 py-2.5 bg-slate-900/90 border-b border-slate-800/80 flex items-center justify-between gap-2">
      <div class="flex items-center gap-2 min-w-0">
        <span class="px-2 py-0.5 rounded-md bg-slate-800 text-slate-200 border border-slate-700/70 text-[10px] font-mono font-bold uppercase tracking-wider shrink-0">
          <template v-if="showSeasonBadge">{{ bet.season_year }} · </template>Wk {{ bet.week }}
        </span>

        <span
          v-if="bet.side_a.teams.length > 1 || bet.side_b.teams.length > 1"
          class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 text-[9.5px] font-mono font-bold uppercase shrink-0"
        >
          <Users class="w-2.5 h-2.5" />
          {{ bet.side_a.teams.length }}v{{ bet.side_b.teams.length }}
        </span>

        <h4 class="text-xs sm:text-sm font-black uppercase tracking-tight text-slate-100 truncate">
          {{ displayTitle }}
        </h4>
      </div>

      <div class="flex items-center gap-1.5 shrink-0">
        <!-- Stake Badge -->
        <span
          v-if="bet.stake_amount > 0"
          class="px-2 py-0.5 rounded-md bg-amber-500/15 text-amber-300 border border-amber-500/35 text-[11px] font-mono font-black tabular-nums shadow-sm"
          :title="bet.stake_description || 'Wager Stake per Team'"
        >
          {{ formatCash(bet.stake_amount) }}
        </span>
        <span
          v-else-if="bet.stake_description"
          class="px-2 py-0.5 rounded-md bg-amber-500/15 text-amber-300 border border-amber-500/35 text-[10px] font-mono font-bold truncate max-w-[110px]"
        >
          {{ bet.stake_description }}
        </span>

        <!-- Status Pill -->
        <span
          v-if="bet.is_live"
          class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/40 text-[10px] font-mono font-black uppercase tracking-wider"
        >
          <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
          LIVE
        </span>
        <span
          v-else-if="isPush && bet.is_completed"
          class="px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700 text-[10px] font-mono font-black uppercase tracking-wider"
        >
          PUSH
        </span>
        <span
          v-else-if="bet.is_completed"
          class="px-2 py-0.5 rounded-full bg-slate-800/90 text-slate-300 border border-slate-700/80 text-[10px] font-mono font-bold uppercase tracking-wider"
        >
          FINAL
        </span>
        <span
          v-else
          class="px-2 py-0.5 rounded-full bg-slate-800/60 text-slate-400 border border-slate-700/60 text-[10px] font-mono font-semibold uppercase tracking-wider"
        >
          UPCOMING
        </span>
      </div>
    </div>

    <!-- Main Matchup Split Scoreboard -->
    <div class="p-3.5 grid grid-cols-1 sm:grid-cols-2 gap-2.5">
      <!-- SIDE A BOX -->
      <div
        class="rounded-xl p-3 border transition-colors flex items-center justify-between gap-2.5"
        :class="
          activeLeader === 'A'
            ? 'bg-emerald-950/25 border-emerald-500/45 shadow-[inset_0_0_20px_rgba(16,185,129,0.06)]'
            : activeLeader === 'B' && bet.is_completed
            ? 'bg-slate-900/40 border-slate-800/70 opacity-85'
            : 'bg-slate-900/70 border-slate-800/90'
        "
      >
        <div class="flex items-center gap-2.5 min-w-0">
          <!-- Stacked Avatars for Multi-Team or Single Avatar -->
          <div class="flex items-center -space-x-2 shrink-0">
            <TeamAvatar
              v-for="team in bet.side_a.teams.slice(0, 3)"
              :key="team.team_id"
              :src="team.logo_url"
              :name="team.team_name"
              size="sm"
              rounded="lg"
              class="ring-2 ring-[#0b101b]"
            />
          </div>

          <div class="min-w-0">
            <div class="flex items-center gap-1.5 flex-wrap">
              <span class="text-xs sm:text-sm font-bold text-slate-100 truncate">
                {{ getSideDisplayName(bet.side_a) }}
              </span>
              <!-- Spread Pill -->
              <span
                class="px-1.5 py-0.2 rounded text-[10px] font-mono font-black tabular-nums border shrink-0"
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

              <!-- Winner / Covering Badge -->
              <span
                v-if="bet.is_completed && bet.winning_side === 'A'"
                class="inline-flex items-center gap-0.5 px-1.5 py-0.2 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-[9px] font-mono font-black uppercase shrink-0"
              >
                <Trophy class="w-2.5 h-2.5" />
                WON {{ bet.stake_amount > 0 ? `+$${bet.stake_amount.toFixed(0)}` : '' }}
              </span>
              <span
                v-else-if="bet.is_completed && bet.winning_side === 'B' && bet.stake_amount > 0"
                class="inline-flex items-center px-1.5 py-0.2 rounded bg-rose-500/15 text-rose-400 border border-rose-500/30 text-[9px] font-mono font-black uppercase shrink-0"
              >
                LOST -${{ bet.stake_amount.toFixed(0) }}
              </span>
            </div>

            <div class="text-[10px] text-slate-400 truncate mt-0.5">
              {{ getSideSubtitle(bet.side_a) }}
            </div>
          </div>
        </div>

        <!-- Score Readout -->
        <div class="text-right font-mono tabular-nums shrink-0">
          <div
            class="text-base sm:text-lg font-black leading-none"
            :class="activeLeader === 'A' ? 'text-emerald-400' : 'text-slate-100'"
          >
            {{ bet.side_a.raw_points.toFixed(2) }}
          </div>
          <div class="text-[10px] text-slate-400 mt-1">
            <template v-if="bet.spread_side_a !== 0">
              Adj: <span class="text-slate-200 font-bold">{{ bet.side_a.adjusted_points.toFixed(2) }}</span>
            </template>
            <template v-else>
              Proj: {{ bet.side_a.projected_points.toFixed(1) }}
            </template>
          </div>
        </div>
      </div>

      <!-- SIDE B BOX -->
      <div
        class="rounded-xl p-3 border transition-colors flex items-center justify-between gap-2.5"
        :class="
          activeLeader === 'B'
            ? 'bg-emerald-950/25 border-emerald-500/45 shadow-[inset_0_0_20px_rgba(16,185,129,0.06)]'
            : activeLeader === 'A' && bet.is_completed
            ? 'bg-slate-900/40 border-slate-800/70 opacity-85'
            : 'bg-slate-900/70 border-slate-800/90'
        "
      >
        <div class="flex items-center gap-2.5 min-w-0">
          <!-- Stacked Avatars for Multi-Team or Single Avatar -->
          <div class="flex items-center -space-x-2 shrink-0">
            <TeamAvatar
              v-for="team in bet.side_b.teams.slice(0, 3)"
              :key="team.team_id"
              :src="team.logo_url"
              :name="team.team_name"
              size="sm"
              rounded="lg"
              class="ring-2 ring-[#0b101b]"
            />
          </div>

          <div class="min-w-0">
            <div class="flex items-center gap-1.5 flex-wrap">
              <span class="text-xs sm:text-sm font-bold text-slate-100 truncate">
                {{ getSideDisplayName(bet.side_b) }}
              </span>
              <!-- Spread Pill -->
              <span
                class="px-1.5 py-0.2 rounded text-[10px] font-mono font-black tabular-nums border shrink-0"
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

              <!-- Winner / Covering Badge -->
              <span
                v-if="bet.is_completed && bet.winning_side === 'B'"
                class="inline-flex items-center gap-0.5 px-1.5 py-0.2 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-[9px] font-mono font-black uppercase shrink-0"
              >
                <Trophy class="w-2.5 h-2.5" />
                WON {{ bet.stake_amount > 0 ? `+$${bet.stake_amount.toFixed(0)}` : '' }}
              </span>
              <span
                v-else-if="bet.is_completed && bet.winning_side === 'A' && bet.stake_amount > 0"
                class="inline-flex items-center px-1.5 py-0.2 rounded bg-rose-500/15 text-rose-400 border border-rose-500/30 text-[9px] font-mono font-black uppercase shrink-0"
              >
                LOST -${{ bet.stake_amount.toFixed(0) }}
              </span>
            </div>

            <div class="text-[10px] text-slate-400 truncate mt-0.5">
              {{ getSideSubtitle(bet.side_b) }}
            </div>
          </div>
        </div>

        <!-- Score Readout -->
        <div class="text-right font-mono tabular-nums shrink-0">
          <div
            class="text-base sm:text-lg font-black leading-none"
            :class="activeLeader === 'B' ? 'text-emerald-400' : 'text-slate-100'"
          >
            {{ bet.side_b.raw_points.toFixed(2) }}
          </div>
          <div class="text-[10px] text-slate-400 mt-1">
            Proj: {{ bet.side_b.projected_points.toFixed(1) }}
          </div>
        </div>
      </div>
    </div>

    <!-- Live Cover Tug-of-War Bar & Footer Action -->
    <div class="px-3.5 pb-3 pt-0.5 space-y-2">
      <!-- Tug-of-War Progress Bar -->
      <div class="space-y-1">
        <div class="h-2 rounded-full bg-slate-900 border border-slate-800 overflow-hidden flex relative">
          <!-- Center 50% marker line -->
          <div class="absolute left-1/2 inset-y-0 w-[2px] -translate-x-1/2 bg-slate-400/60 z-10"></div>

          <div
            class="h-full transition-all duration-500"
            :class="
              activeLeader === 'A'
                ? 'bg-gradient-to-r from-emerald-600 to-emerald-400'
                : 'bg-slate-700/70'
            "
            :style="{ width: `${sideATugPercent}%` }"
          ></div>
          <div
            class="h-full flex-1 transition-all duration-500"
            :class="
              activeLeader === 'B'
                ? 'bg-gradient-to-l from-emerald-600 to-emerald-400'
                : 'bg-slate-800/80'
            "
          ></div>
        </div>
      </div>

      <!-- Bottom Row: Cover Verdict & View Players CTA -->
      <div class="flex items-center justify-between gap-2 text-[11px] font-mono">
        <div class="flex items-center gap-1.5 min-w-0 truncate">
          <Flame
            class="w-3.5 h-3.5 shrink-0"
            :class="activeLeader ? 'text-emerald-400' : 'text-slate-500'"
          />
          <span
            class="truncate font-semibold"
            :class="activeLeader ? 'text-emerald-300' : 'text-slate-400'"
          >
            {{ coverSummaryLabel }}
          </span>
        </div>

        <span class="inline-flex items-center gap-1 text-[11px] font-bold text-indigo-400 group-hover:text-indigo-300 shrink-0">
          <span>View Players &amp; Points</span>
          <ChevronRight class="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5" />
        </span>
      </div>
    </div>
  </div>
</template>
