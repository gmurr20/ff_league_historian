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

const hasSpread = computed(() => Math.abs(props.bet.spread_side_a) > 0.001);

const isUpcoming = computed(() => {
  return !props.bet.is_completed && props.bet.side_a.raw_points === 0 && props.bet.side_b.raw_points === 0;
});

const isPush = computed(() => {
  return (
    (props.bet.is_completed && props.bet.winning_side === 'PUSH') ||
    (!props.bet.is_completed && !isUpcoming.value && props.bet.currently_covering === 'PUSH')
  );
});

const activeLeader = computed<'A' | 'B' | 'PUSH' | null>(() => {
  if (props.bet.is_completed) {
    return props.bet.winning_side;
  }
  if (isUpcoming.value) {
    return null;
  }
  return props.bet.currently_covering;
});

// Which side gets the positive (+) underdog handicap cushion
const underdogSide = computed<'A' | 'B' | null>(() => {
  if (!hasSpread.value) return null;
  return props.bet.spread_side_a > 0 ? 'A' : 'B';
});

const spreadAbs = computed(() => Math.abs(props.bet.spread_side_a));

// Display-friendly "Effective Score (w/ Spread Cushion)" where the underdog gets +spreadAbs added to their score
const sideAEffectiveScore = computed(() => {
  if (underdogSide.value === 'A') {
    return props.bet.side_a.raw_points + spreadAbs.value;
  }
  return props.bet.side_a.raw_points;
});

const sideBEffectiveScore = computed(() => {
  if (underdogSide.value === 'B') {
    return props.bet.side_b.raw_points + spreadAbs.value;
  }
  return props.bet.side_b.raw_points;
});

const sideAEffectiveProj = computed(() => {
  if (underdogSide.value === 'A') {
    return props.bet.side_a.projected_points + spreadAbs.value;
  }
  return props.bet.side_a.projected_points;
});

const sideBEffectiveProj = computed(() => {
  if (underdogSide.value === 'B') {
    return props.bet.side_b.projected_points + spreadAbs.value;
  }
  return props.bet.side_b.projected_points;
});

// 3-Segment Proportional Color-Coded Tug-of-War Bar widths:
// By anchoring 50% of the bar to the Favorite's score (scale = 2 * favoriteScore):
// 1. If raw scores tie (A == B), the underdog's raw bar reaches 50.0% and the ENTIRE gold spread segment pushes past the 50% midline.
// 2. If spread-adjusted scores tie (Underdog + Spread == Favorite), [Underdog + Gold Spread] lands at 50.0% right on the midline.
// 3. If Favorite beats the spread, [Underdog + Gold Spread] falls short of 50.0% and Favorite crosses past the midline.
const tugSegments = computed<{
  sideAPct: number;
  spreadPct: number;
  sideBPct: number;
}>(() => {
  const spread = hasSpread.value ? spreadAbs.value : 0;
  const useProj = isUpcoming.value;
  let baseA = useProj ? props.bet.side_a.projected_points : props.bet.side_a.raw_points;
  let baseB = useProj ? props.bet.side_b.projected_points : props.bet.side_b.raw_points;

  // If both sides are 0.0 (e.g. upcoming week before projections are posted), use a 110-pt per-team baseline
  // so the two raw bars tie at 50% and the proportional gold spread segment pushes past the 50% midline.
  if (baseA <= 0 && baseB <= 0) {
    const teamCount = Math.max(1, props.bet.side_a.teams.length, props.bet.side_b.teams.length);
    baseA = 110 * teamCount;
    baseB = 110 * teamCount;
  }

  if (!hasSpread.value) {
    const total = baseA + baseB;
    if (total <= 0) return { sideAPct: 50, spreadPct: 0, sideBPct: 50 };
    const sideAPct = Math.min(92, Math.max(8, (baseA / total) * 100));
    return {
      sideAPct,
      spreadPct: 0,
      sideBPct: 100 - sideAPct,
    };
  }

  if (underdogSide.value === 'A') {
    // Side B is the favorite; 50% of the bar = Side B's score
    const scale = Math.max(2 * baseB, baseA + spread, 20);
    const spreadPct = Math.min(35, Math.max(1.8, (spread / scale) * 100));
    const rawSideAPct = (baseA / scale) * 100;
    const totalShareA = Math.min(94, Math.max(6 + spreadPct, rawSideAPct + spreadPct));
    const sideAPct = Math.max(4, totalShareA - spreadPct);
    const sideBPct = Math.max(4, 100 - sideAPct - spreadPct);
    return { sideAPct, spreadPct, sideBPct };
  } else {
    // Side A is the favorite; 50% of the bar = Side A's score
    const scale = Math.max(2 * baseA, baseB + spread, 20);
    const spreadPct = Math.min(35, Math.max(1.8, (spread / scale) * 100));
    const rawSideBPct = (baseB / scale) * 100;
    const totalShareB = Math.min(94, Math.max(6 + spreadPct, rawSideBPct + spreadPct));
    const sideBPct = Math.max(4, totalShareB - spreadPct);
    const sideAPct = Math.max(4, 100 - sideBPct - spreadPct);
    return { sideAPct, spreadPct, sideBPct };
  }
});

// Where the underdog's combined reach (Base + Spread) lands relative to 50%
const sideATotalReachPct = computed(() => {
  if (underdogSide.value === 'A') {
    return tugSegments.value.sideAPct + tugSegments.value.spreadPct;
  }
  return tugSegments.value.sideAPct;
});

const coverSummaryLabel = computed<string>(() => {
  const absMargin = Math.abs(props.bet.margin_vs_spread).toFixed(2);
  const sideAName = getSideDisplayName(props.bet.side_a);
  const sideBName = getSideDisplayName(props.bet.side_b);

  if (props.bet.is_completed) {
    if (props.bet.winning_side === 'A') {
      return hasSpread.value
        ? `${sideAName} (${formatSpread(props.bet.side_a.spread_applied)}) covered by +${absMargin} pts`
        : `${sideAName} won by +${absMargin} pts`;
    }
    if (props.bet.winning_side === 'B') {
      return hasSpread.value
        ? `${sideBName} (${formatSpread(props.bet.side_b.spread_applied)}) covered by +${absMargin} pts`
        : `${sideBName} won by +${absMargin} pts`;
    }
    return `Exact Push (0.00 margin vs spread)`;
  }

  if (isUpcoming.value) {
    const pMargin = props.bet.projected_margin_vs_spread;
    const absProjMargin = Math.abs(pMargin);
    if (absProjMargin < 0.08) {
      return hasSpread.value
        ? `Projected dead even w/ spread (${sideAEffectiveProj.value.toFixed(1)} vs ${sideBEffectiveProj.value.toFixed(1)})`
        : `Projected dead even (${props.bet.side_a.projected_points.toFixed(1)} vs ${props.bet.side_b.projected_points.toFixed(1)})`;
    }
    if (pMargin > 0) {
      return `Proj: ${sideAName} covers by +${absProjMargin.toFixed(1)} pts (${sideAEffectiveProj.value.toFixed(1)} vs ${sideBEffectiveProj.value.toFixed(1)})`;
    }
    return `Proj: ${sideBName} covers by +${absProjMargin.toFixed(1)} pts (${sideBEffectiveProj.value.toFixed(1)} vs ${sideAEffectiveProj.value.toFixed(1)})`;
  }

  if (props.bet.currently_covering === 'A') {
    return hasSpread.value
      ? `${sideAName} covering ${formatSpread(props.bet.side_a.spread_applied)} by +${absMargin} pts`
      : `${sideAName} leading by +${absMargin} pts`;
  }
  if (props.bet.currently_covering === 'B') {
    return hasSpread.value
      ? `${sideBName} covering ${formatSpread(props.bet.side_b.spread_applied)} by +${absMargin} pts`
      : `${sideBName} leading by +${absMargin} pts`;
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
    <!-- Top Header Strip: Wraps cleanly on mobile so title is never cut off -->
    <div class="px-3.5 py-2.5 bg-slate-900/90 border-b border-slate-800/80 flex items-center justify-between gap-2 flex-wrap">
      <div class="flex items-center gap-2 min-w-0 flex-wrap">
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

        <h4 class="text-xs sm:text-sm font-black uppercase tracking-tight text-slate-100 break-words leading-snug">
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
          class="px-2 py-0.5 rounded-md bg-amber-500/15 text-amber-300 border border-amber-500/35 text-[10px] font-mono font-bold break-words"
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
        class="rounded-xl p-3 border transition-colors flex items-start justify-between gap-2.5"
        :class="
          activeLeader === 'A'
            ? 'bg-emerald-950/25 border-emerald-500/45 shadow-[inset_0_0_20px_rgba(16,185,129,0.06)]'
            : activeLeader === 'B' && bet.is_completed
            ? 'bg-slate-900/40 border-slate-800/70 opacity-85'
            : 'bg-slate-900/70 border-slate-800/90'
        "
      >
        <div class="flex items-start gap-2.5 min-w-0 flex-1">
          <div class="flex items-center -space-x-2 shrink-0 mt-0.5">
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

          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-1.5 flex-wrap">
              <span class="text-xs sm:text-sm font-bold text-slate-100 break-words leading-snug">
                {{ getSideDisplayName(bet.side_a) }}
              </span>
              <!-- Spread Pill -->
              <span
                class="px-1.5 py-0.2 rounded text-[10px] font-mono font-black tabular-nums border shrink-0"
                :class="
                  bet.side_a.spread_applied < 0
                    ? 'bg-indigo-500/15 text-indigo-300 border-indigo-500/35'
                    : bet.side_a.spread_applied > 0
                    ? 'bg-amber-500/20 text-amber-300 border-amber-500/45'
                    : 'bg-slate-800 text-slate-400 border-slate-700'
                "
              >
                {{ formatSpread(bet.side_a.spread_applied) }}
              </span>

              <!-- Winner / Lost Badge -->
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

            <div class="text-[10px] text-slate-400 break-words leading-snug mt-0.5">
              {{ getSideSubtitle(bet.side_a) }}
            </div>
          </div>
        </div>

        <!-- Symmetrical Score Readout -->
        <div class="text-right font-mono tabular-nums shrink-0">
          <div
            class="text-base sm:text-lg font-black leading-none"
            :class="activeLeader === 'A' ? 'text-emerald-400' : 'text-slate-100'"
          >
            {{ bet.side_a.raw_points.toFixed(2) }}
          </div>
          <div class="text-[10px] text-slate-400 mt-1 space-y-0.5">
            <div>Proj: <span class="text-slate-300 font-semibold">{{ bet.side_a.projected_points.toFixed(1) }}</span></div>
            <div v-if="underdogSide === 'A'" class="text-amber-300 font-bold">
              w/ Spread: {{ isUpcoming ? sideAEffectiveProj.toFixed(1) : sideAEffectiveScore.toFixed(2) }}
            </div>
          </div>
        </div>
      </div>

      <!-- SIDE B BOX -->
      <div
        class="rounded-xl p-3 border transition-colors flex items-start justify-between gap-2.5"
        :class="
          activeLeader === 'B'
            ? 'bg-emerald-950/25 border-emerald-500/45 shadow-[inset_0_0_20px_rgba(16,185,129,0.06)]'
            : activeLeader === 'A' && bet.is_completed
            ? 'bg-slate-900/40 border-slate-800/70 opacity-85'
            : 'bg-slate-900/70 border-slate-800/90'
        "
      >
        <div class="flex items-start gap-2.5 min-w-0 flex-1">
          <div class="flex items-center -space-x-2 shrink-0 mt-0.5">
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

          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-1.5 flex-wrap">
              <span class="text-xs sm:text-sm font-bold text-slate-100 break-words leading-snug">
                {{ getSideDisplayName(bet.side_b) }}
              </span>
              <!-- Spread Pill -->
              <span
                class="px-1.5 py-0.2 rounded text-[10px] font-mono font-black tabular-nums border shrink-0"
                :class="
                  bet.side_b.spread_applied < 0
                    ? 'bg-indigo-500/15 text-indigo-300 border-indigo-500/35'
                    : bet.side_b.spread_applied > 0
                    ? 'bg-amber-500/20 text-amber-300 border-amber-500/45'
                    : 'bg-slate-800 text-slate-400 border-slate-700'
                "
              >
                {{ formatSpread(bet.side_b.spread_applied) }}
              </span>

              <!-- Winner / Lost Badge -->
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

            <div class="text-[10px] text-slate-400 break-words leading-snug mt-0.5">
              {{ getSideSubtitle(bet.side_b) }}
            </div>
          </div>
        </div>

        <!-- Symmetrical Score Readout -->
        <div class="text-right font-mono tabular-nums shrink-0">
          <div
            class="text-base sm:text-lg font-black leading-none"
            :class="activeLeader === 'B' ? 'text-emerald-400' : 'text-slate-100'"
          >
            {{ bet.side_b.raw_points.toFixed(2) }}
          </div>
          <div class="text-[10px] text-slate-400 mt-1 space-y-0.5">
            <div>Proj: <span class="text-slate-300 font-semibold">{{ bet.side_b.projected_points.toFixed(1) }}</span></div>
            <div v-if="underdogSide === 'B'" class="text-amber-300 font-bold">
              w/ Spread: {{ isUpcoming ? sideBEffectiveProj.toFixed(1) : sideBEffectiveScore.toFixed(2) }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Broadcast-Grade Stadium Tug-of-War Meter -->
    <div class="px-3.5 pb-3.5 pt-0.5 space-y-2.5">
      <div class="rounded-xl bg-slate-900/80 border border-slate-800/90 p-2.5 space-y-2 shadow-inner">
        <!-- Top Equation & Color Key Header (Wraps cleanly on mobile) -->
        <div class="flex items-center justify-between gap-2 flex-wrap text-[10px] font-mono">
          <!-- Side A Key -->
          <div class="flex items-center gap-1.5 flex-wrap">
            <span class="inline-flex items-center gap-1.5 font-bold text-sky-300">
              <span class="w-2.5 h-2.5 rounded-sm bg-gradient-to-br from-sky-400 to-cyan-500 shadow-sm shrink-0"></span>
              <span>{{ getSideDisplayName(bet.side_a) }} ({{ (isUpcoming ? bet.side_a.projected_points : bet.side_a.raw_points).toFixed(1) }})</span>
            </span>

            <template v-if="hasSpread && underdogSide === 'A'">
              <span class="text-slate-500 font-black">+</span>
              <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-400/40 font-black shadow-sm">
                <span class="w-2 h-2 rounded-xs bg-amber-400 shrink-0"></span>
                <span>+{{ spreadAbs.toFixed(1) }} SPREAD</span>
              </span>
              <span class="text-slate-400">= <strong class="text-white">{{ (isUpcoming ? sideAEffectiveProj : sideAEffectiveScore).toFixed(1) }}</strong></span>
            </template>
          </div>

          <!-- Side B Key -->
          <div class="flex items-center gap-1.5 flex-wrap ml-auto">
            <template v-if="hasSpread && underdogSide === 'B'">
              <span class="text-slate-400"><strong class="text-white">{{ (isUpcoming ? sideBEffectiveProj : sideBEffectiveScore).toFixed(1) }}</strong> =</span>
              <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-400/40 font-black shadow-sm">
                <span class="w-2 h-2 rounded-xs bg-amber-400 shrink-0"></span>
                <span>+{{ spreadAbs.toFixed(1) }} SPREAD</span>
              </span>
              <span class="text-slate-500 font-black">+</span>
            </template>

            <span class="inline-flex items-center gap-1.5 font-bold text-indigo-300">
              <span>{{ getSideDisplayName(bet.side_b) }} ({{ (isUpcoming ? bet.side_b.projected_points : bet.side_b.raw_points).toFixed(1) }})</span>
              <span class="w-2.5 h-2.5 rounded-sm bg-gradient-to-br from-indigo-400 to-violet-500 shadow-sm shrink-0"></span>
            </span>
          </div>
        </div>

        <!-- Tactile 3-Segment Tug-of-War Bar with 50% Win Line Pin -->
        <div class="relative py-1">
          <!-- Center 50% Win Line Pin & Notch -->
          <div
            class="absolute left-1/2 -top-0.5 -bottom-0.5 -translate-x-1/2 z-30 flex flex-col items-center pointer-events-none"
            title="50% Cover Midline"
          >
            <div class="w-1.5 h-1.5 rotate-45 bg-white shadow"></div>
            <div class="w-[2px] flex-1 bg-white/90 shadow-[0_0_8px_rgba(255,255,255,0.8)]"></div>
            <div class="w-1.5 h-1.5 rotate-45 bg-white shadow"></div>
          </div>

          <!-- Recessed Bar Track (No inline text inside segments; purely proportional visual) -->
          <div class="h-3.5 rounded-full bg-slate-950 p-0.5 border border-slate-800/90 shadow-inner flex items-stretch overflow-hidden relative">
            <!-- Segment 1: Side A Base Score -->
            <div
              class="h-full transition-all duration-500 first:rounded-l-full"
              :class="
                activeLeader === 'A'
                  ? 'bg-gradient-to-r from-emerald-600 via-emerald-500 to-teal-400 shadow-[inset_0_1px_0_rgba(255,255,255,0.3)]'
                  : 'bg-gradient-to-r from-sky-600 via-sky-500 to-cyan-400 shadow-[inset_0_1px_0_rgba(255,255,255,0.25)]'
              "
              :style="{ width: `${tugSegments.sideAPct}%` }"
            ></div>

            <!-- Segment 2: Proportional Color-Coded Gold/Amber Spread Cushion -->
            <div
              v-if="hasSpread && tugSegments.spreadPct > 0"
              class="h-full transition-all duration-500 border-x border-slate-950/90 shrink-0"
              style="
                background: repeating-linear-gradient(
                  -45deg,
                  rgba(245, 158, 11, 0.95),
                  rgba(245, 158, 11, 0.95) 4px,
                  rgba(251, 191, 36, 0.95) 4px,
                  rgba(251, 191, 36, 0.95) 8px
                );
              "
              :style="{ width: `${tugSegments.spreadPct}%` }"
              :title="`Spread Cushion: +${spreadAbs.toFixed(1)} pts`"
            ></div>

            <!-- Segment 3: Side B Base Score -->
            <div
              class="h-full flex-1 transition-all duration-500 last:rounded-r-full"
              :class="
                activeLeader === 'B'
                  ? 'bg-gradient-to-l from-emerald-600 via-emerald-500 to-teal-400 shadow-[inset_0_1px_0_rgba(255,255,255,0.3)]'
                  : 'bg-gradient-to-l from-indigo-600 via-indigo-500 to-violet-400 shadow-[inset_0_1px_0_rgba(255,255,255,0.25)]'
              "
            ></div>
          </div>
        </div>

        <!-- Subtle Scale Caption under the bar -->
        <div class="flex items-center justify-between text-[9.5px] font-mono text-slate-400">
          <span>
            {{ getSideDisplayName(bet.side_a) }} Total:
            <strong class="text-slate-200">{{ (isUpcoming ? sideAEffectiveProj : sideAEffectiveScore).toFixed(1) }}</strong>
          </span>
          <span class="text-slate-500 uppercase tracking-wider font-bold">
            {{ Math.abs(sideATotalReachPct - 50) < 1.5 ? 'Dead Even at Midline' : '50% Win Line' }}
          </span>
          <span>
            {{ getSideDisplayName(bet.side_b) }} Total:
            <strong class="text-slate-200">{{ (isUpcoming ? sideBEffectiveProj : sideBEffectiveScore).toFixed(1) }}</strong>
          </span>
        </div>
      </div>

      <!-- Bottom Row: Cover Verdict & View Players CTA (Wraps cleanly on mobile so nothing is cut off) -->
      <div class="flex items-center justify-between gap-2 flex-wrap text-[11px] font-mono">
        <div class="flex items-start gap-1.5 min-w-0 flex-1">
          <Flame
            class="w-3.5 h-3.5 shrink-0 mt-0.5"
            :class="activeLeader ? 'text-emerald-400' : 'text-amber-400'"
          />
          <span
            class="font-semibold break-words leading-snug"
            :class="activeLeader ? 'text-emerald-300' : 'text-slate-300'"
          >
            {{ coverSummaryLabel }}
          </span>
        </div>

        <span class="inline-flex items-center gap-1 text-[11px] font-bold text-indigo-400 group-hover:text-indigo-300 shrink-0 ml-auto">
          <span>View Players &amp; Points</span>
          <ChevronRight class="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5" />
        </span>
      </div>
    </div>
  </div>
</template>
