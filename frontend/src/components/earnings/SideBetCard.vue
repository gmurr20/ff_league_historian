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

const hasSomeActualPoints = computed(() => {
  return props.bet.side_a.raw_points > 0 || props.bet.side_b.raw_points > 0;
});

// Which side gets the positive (+) underdog handicap cushion
const underdogSide = computed<'A' | 'B' | null>(() => {
  if (!hasSpread.value) return null;
  return props.bet.spread_side_a > 0 ? 'A' : 'B';
});

const spreadAbs = computed(() => Math.abs(props.bet.spread_side_a));

// Live Projected Base Points (before spread) for each side:
// When completed, uses final actual points. When upcoming/live, uses live projected points (at least actual points).
const sideALiveProjBase = computed(() => {
  if (props.bet.is_completed) return props.bet.side_a.raw_points;
  return Math.max(props.bet.side_a.raw_points, props.bet.side_a.projected_points);
});

const sideBLiveProjBase = computed(() => {
  if (props.bet.is_completed) return props.bet.side_b.raw_points;
  return Math.max(props.bet.side_b.raw_points, props.bet.side_b.projected_points);
});

// Effective Totals (including underdog spread cushion):
const sideAEffectiveActual = computed(() => {
  return props.bet.side_a.raw_points + (underdogSide.value === 'A' ? spreadAbs.value : 0);
});

const sideBEffectiveActual = computed(() => {
  return props.bet.side_b.raw_points + (underdogSide.value === 'B' ? spreadAbs.value : 0);
});

const sideAEffectiveLiveProj = computed(() => {
  return sideALiveProjBase.value + (underdogSide.value === 'A' ? spreadAbs.value : 0);
});

const sideBEffectiveLiveProj = computed(() => {
  return sideBLiveProjBase.value + (underdogSide.value === 'B' ? spreadAbs.value : 0);
});

// Net margin vs spread based on Live Projected (when upcoming/live) or Final Actual (when completed)
const activeTugMargin = computed(() => {
  if (props.bet.is_completed) {
    return props.bet.margin_vs_spread;
  }
  return sideAEffectiveLiveProj.value - sideBEffectiveLiveProj.value;
});

const isPush = computed(() => {
  return (
    (props.bet.is_completed && props.bet.winning_side === 'PUSH') ||
    (!props.bet.is_completed && Math.abs(activeTugMargin.value) < 0.08 && hasSomeActualPoints.value)
  );
});

// Leader based on final result (if completed) or live projected pace (if live/upcoming)
const activeLeader = computed<'A' | 'B' | 'PUSH' | null>(() => {
  if (props.bet.is_completed) {
    return props.bet.winning_side;
  }
  if (Math.abs(activeTugMargin.value) < 0.08) {
    return isUpcoming.value ? null : 'PUSH';
  }
  return activeTugMargin.value > 0 ? 'A' : 'B';
});

// 5-Segment Proportional Tug-of-War Bar widths:
// [ Side A Actual (Solid) | Side A Rem Proj (Translucent) | Gold Spread (+X.X) | Side B Rem Proj (Translucent) | Side B Actual (Solid) ]
// Operates on Live Projected totals during the week (and Final Actual once completed),
// anchored so 50% of the bar = Favorite's target score.
const tugSegments = computed<{
  sideAPct: number;
  sideAActualPct: number;
  sideARemProjPct: number;
  spreadPct: number;
  sideBPct: number;
  sideBRemProjPct: number;
  sideBActualPct: number;
}>(() => {
  const spread = hasSpread.value ? spreadAbs.value : 0;
  const actualA = props.bet.side_a.raw_points;
  const actualB = props.bet.side_b.raw_points;

  let baseA = sideALiveProjBase.value;
  let baseB = sideBLiveProjBase.value;

  // Fallback baseline if both sides have 0.0 projected and 0.0 actual
  if (baseA <= 0 && baseB <= 0) {
    const teamCount = Math.max(1, props.bet.side_a.teams.length, props.bet.side_b.teams.length);
    baseA = 110 * teamCount;
    baseB = 110 * teamCount;
  }

  let sideAPct = 50;
  let spreadPct = 0;
  let sideBPct = 50;

  if (!hasSpread.value) {
    const total = baseA + baseB;
    if (total > 0) {
      sideAPct = Math.min(92, Math.max(8, (baseA / total) * 100));
      sideBPct = 100 - sideAPct;
    }
  } else if (underdogSide.value === 'A') {
    // Side B is the favorite; 50% of the bar = Side B's live projected score
    const scale = Math.max(2 * baseB, baseA + spread, 20);
    spreadPct = Math.min(35, Math.max(1.8, (spread / scale) * 100));
    const rawSideAPct = (baseA / scale) * 100;
    const totalShareA = Math.min(94, Math.max(6 + spreadPct, rawSideAPct + spreadPct));
    sideAPct = Math.max(4, totalShareA - spreadPct);
    sideBPct = Math.max(4, 100 - sideAPct - spreadPct);
  } else {
    // Side A is the favorite; 50% of the bar = Side A's live projected score
    const scale = Math.max(2 * baseA, baseB + spread, 20);
    spreadPct = Math.min(35, Math.max(1.8, (spread / scale) * 100));
    const rawSideBPct = (baseB / scale) * 100;
    const totalShareB = Math.min(94, Math.max(6 + spreadPct, rawSideBPct + spreadPct));
    sideBPct = Math.max(4, totalShareB - spreadPct);
    sideAPct = Math.max(4, 100 - sideBPct - spreadPct);
  }

  // Split each side's bar into Actual Scored (solid) vs Remaining Projected (translucent)
  const ratioActualA = props.bet.is_completed
    ? 1
    : baseA > 0
    ? Math.min(1, Math.max(0, actualA / baseA))
    : 0;
  const ratioActualB = props.bet.is_completed
    ? 1
    : baseB > 0
    ? Math.min(1, Math.max(0, actualB / baseB))
    : 0;

  const sideAActualPct = sideAPct * ratioActualA;
  const sideARemProjPct = Math.max(0, sideAPct - sideAActualPct);

  const sideBActualPct = sideBPct * ratioActualB;
  const sideBRemProjPct = Math.max(0, sideBPct - sideBActualPct);

  return {
    sideAPct,
    sideAActualPct,
    sideARemProjPct,
    spreadPct,
    sideBPct,
    sideBRemProjPct,
    sideBActualPct,
  };
});

const coverSummaryLabel = computed<string>(() => {
  const sideAName = getSideDisplayName(props.bet.side_a);
  const sideBName = getSideDisplayName(props.bet.side_b);

  if (props.bet.is_completed) {
    const absFinalMargin = Math.abs(props.bet.margin_vs_spread).toFixed(2);
    if (props.bet.winning_side === 'A') {
      return hasSpread.value
        ? `${sideAName} (${formatSpread(props.bet.side_a.spread_applied)}) covered by +${absFinalMargin} pts`
        : `${sideAName} won by +${absFinalMargin} pts`;
    }
    if (props.bet.winning_side === 'B') {
      return hasSpread.value
        ? `${sideBName} (${formatSpread(props.bet.side_b.spread_applied)}) covered by +${absFinalMargin} pts`
        : `${sideBName} won by +${absFinalMargin} pts`;
    }
    return `Exact Push (0.00 margin vs spread)`;
  }

  const pMargin = activeTugMargin.value;
  const absProjMargin = Math.abs(pMargin);
  const prefix = props.bet.is_live ? 'Live Proj' : 'Proj';

  if (absProjMargin < 0.08) {
    return hasSpread.value
      ? `${prefix}: Dead even w/ spread (${sideAEffectiveLiveProj.value.toFixed(1)} vs ${sideBEffectiveLiveProj.value.toFixed(1)})`
      : `${prefix}: Dead even (${sideALiveProjBase.value.toFixed(1)} vs ${sideBLiveProjBase.value.toFixed(1)})`;
  }
  if (pMargin > 0) {
    return `${prefix}: ${sideAName} covers by +${absProjMargin.toFixed(1)} pts (${sideAEffectiveLiveProj.value.toFixed(1)} vs ${sideBEffectiveLiveProj.value.toFixed(1)})`;
  }
  return `${prefix}: ${sideBName} covers by +${absProjMargin.toFixed(1)} pts (${sideBEffectiveLiveProj.value.toFixed(1)} vs ${sideAEffectiveLiveProj.value.toFixed(1)})`;
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
            <div>Proj: <span class="text-slate-300 font-semibold">{{ sideALiveProjBase.toFixed(1) }}</span></div>
            <div v-if="underdogSide === 'A'" class="text-amber-300 font-bold">
              w/ Spread: {{ (bet.is_completed ? sideAEffectiveActual : sideAEffectiveLiveProj).toFixed(1) }}
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
            <div>Proj: <span class="text-slate-300 font-semibold">{{ sideBLiveProjBase.toFixed(1) }}</span></div>
            <div v-if="underdogSide === 'B'" class="text-amber-300 font-bold">
              w/ Spread: {{ (bet.is_completed ? sideBEffectiveActual : sideBEffectiveLiveProj).toFixed(1) }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Broadcast-Grade Stadium Tug-of-War Meter (Live Projected + Actual vs. Projected Split) -->
    <div class="px-3.5 pb-3.5 pt-0.5 space-y-2.5">
      <div class="rounded-xl bg-slate-900/80 border border-slate-800/90 p-2.5 space-y-2 shadow-inner">
        <!-- Top Equation & Color Key Header (Wraps cleanly on mobile) -->
        <div class="flex items-center justify-between gap-2 flex-wrap text-[10px] font-mono">
          <!-- Side A Key -->
          <div class="flex items-center gap-1.5 flex-wrap">
            <span class="inline-flex items-center gap-1.5 font-bold text-sky-300">
              <span class="w-2.5 h-2.5 rounded-sm bg-gradient-to-br from-sky-400 to-cyan-500 shadow-sm shrink-0"></span>
              <span>
                {{ getSideDisplayName(bet.side_a) }}
                <template v-if="bet.is_live">
                  ({{ bet.side_a.raw_points.toFixed(1) }} / Proj {{ sideALiveProjBase.toFixed(1) }})
                </template>
                <template v-else>
                  ({{ (bet.is_completed ? bet.side_a.raw_points : sideALiveProjBase).toFixed(1) }})
                </template>
              </span>
            </span>

            <template v-if="hasSpread && underdogSide === 'A'">
              <span class="text-slate-500 font-black">+</span>
              <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-400/40 font-black shadow-sm">
                <span class="w-2 h-2 rounded-xs bg-amber-400 shrink-0"></span>
                <span>+{{ spreadAbs.toFixed(1) }} SPREAD</span>
              </span>
              <span class="text-slate-400">= <strong class="text-white">{{ (bet.is_completed ? sideAEffectiveActual : sideAEffectiveLiveProj).toFixed(1) }}</strong></span>
            </template>
          </div>

          <!-- Side B Key -->
          <div class="flex items-center gap-1.5 flex-wrap ml-auto">
            <template v-if="hasSpread && underdogSide === 'B'">
              <span class="text-slate-400"><strong class="text-white">{{ (bet.is_completed ? sideBEffectiveActual : sideBEffectiveLiveProj).toFixed(1) }}</strong> =</span>
              <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-400/40 font-black shadow-sm">
                <span class="w-2 h-2 rounded-xs bg-amber-400 shrink-0"></span>
                <span>+{{ spreadAbs.toFixed(1) }} SPREAD</span>
              </span>
              <span class="text-slate-500 font-black">+</span>
            </template>

            <span class="inline-flex items-center gap-1.5 font-bold text-indigo-300">
              <span>
                {{ getSideDisplayName(bet.side_b) }}
                <template v-if="bet.is_live">
                  ({{ bet.side_b.raw_points.toFixed(1) }} / Proj {{ sideBLiveProjBase.toFixed(1) }})
                </template>
                <template v-else>
                  ({{ (bet.is_completed ? bet.side_b.raw_points : sideBLiveProjBase).toFixed(1) }})
                </template>
              </span>
              <span class="w-2.5 h-2.5 rounded-sm bg-gradient-to-br from-indigo-400 to-violet-500 shadow-sm shrink-0"></span>
            </span>
          </div>
        </div>

        <!-- Tactile 5-Segment Tug-of-War Bar (Actual Solid + Remaining Proj Translucent + Gold Spread) -->
        <div class="relative py-1">
          <!-- Center 50% Win Line Pin & Notch -->
          <div
            class="absolute left-1/2 -top-0.5 -bottom-0.5 -translate-x-1/2 z-30 flex flex-col items-center pointer-events-none"
            title="50% Tie / Cover Midline"
          >
            <div class="w-1.5 h-1.5 rotate-45 bg-white shadow"></div>
            <div class="w-[2px] flex-1 bg-white/90 shadow-[0_0_8px_rgba(255,255,255,0.8)]"></div>
            <div class="w-1.5 h-1.5 rotate-45 bg-white shadow"></div>
          </div>

          <!-- Recessed Bar Track -->
          <div class="h-4 rounded-full bg-slate-950 p-0.5 border border-slate-800/90 shadow-inner flex items-stretch overflow-hidden relative">
            <!-- Segment 1A: Side A Actual Points Scored (Solid Vibrant Sky Fill) -->
            <div
              v-if="tugSegments.sideAActualPct > 0"
              class="h-full transition-all duration-500 first:rounded-l-full bg-gradient-to-r from-sky-600 via-sky-500 to-cyan-400 shadow-[inset_0_1px_0_rgba(255,255,255,0.35)]"
              :class="tugSegments.sideARemProjPct > 0 ? 'border-r-2 border-white/85' : ''"
              :style="{ width: `${tugSegments.sideAActualPct}%` }"
              :title="`${getSideDisplayName(bet.side_a)} Actual Scored: ${bet.side_a.raw_points.toFixed(2)} pts`"
            ></div>

            <!-- Segment 1B: Side A Remaining Projected Points (Fainter Translucent Sky Fill) -->
            <div
              v-if="tugSegments.sideARemProjPct > 0"
              class="h-full transition-all duration-500 first:rounded-l-full bg-sky-400/25 border-y border-sky-400/35"
              :style="{ width: `${tugSegments.sideARemProjPct}%` }"
              :title="`${getSideDisplayName(bet.side_a)} Remaining Projected: ${Math.max(0, sideALiveProjBase - bet.side_a.raw_points).toFixed(1)} pts`"
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

            <!-- Segment 3A: Side B Remaining Projected Points (Fainter Translucent Indigo Fill toward center) -->
            <div
              v-if="tugSegments.sideBRemProjPct > 0"
              class="h-full transition-all duration-500 last:rounded-r-full bg-indigo-400/25 border-y border-indigo-400/35"
              :style="{ width: `${tugSegments.sideBRemProjPct}%` }"
              :title="`${getSideDisplayName(bet.side_b)} Remaining Projected: ${Math.max(0, sideBLiveProjBase - bet.side_b.raw_points).toFixed(1)} pts`"
            ></div>

            <!-- Segment 3B: Side B Actual Points Scored (Solid Vibrant Indigo Fill anchored on right edge) -->
            <div
              v-if="tugSegments.sideBActualPct > 0"
              class="h-full transition-all duration-500 last:rounded-r-full bg-gradient-to-l from-indigo-600 via-indigo-500 to-violet-400 shadow-[inset_0_1px_0_rgba(255,255,255,0.35)]"
              :class="tugSegments.sideBRemProjPct > 0 ? 'border-l-2 border-white/85' : ''"
              :style="{ width: `${tugSegments.sideBActualPct}%` }"
              :title="`${getSideDisplayName(bet.side_b)} Actual Scored: ${bet.side_b.raw_points.toFixed(2)} pts`"
            ></div>
          </div>
        </div>

        <!-- Subtle Scale Caption under the bar: Actual vs Projected Totals -->
        <div class="flex items-center justify-between gap-2 flex-wrap text-[10px] font-mono text-slate-400">
          <span>
            Actual: <strong class="text-slate-200">{{ bet.side_a.raw_points.toFixed(1) }}</strong>
            <span class="text-slate-600 mx-1">·</span>
            Proj{{ underdogSide === 'A' ? ' (w/ Spread)' : '' }}: <strong class="text-sky-300">{{ sideAEffectiveLiveProj.toFixed(1) }}</strong>
          </span>
          <span v-if="!bet.is_completed" class="text-[9.5px] text-slate-500 uppercase tracking-wider font-bold">
            Solid = Actual · Shaded = Proj
          </span>
          <span class="ml-auto">
            Actual: <strong class="text-slate-200">{{ bet.side_b.raw_points.toFixed(1) }}</strong>
            <span class="text-slate-600 mx-1">·</span>
            Proj{{ underdogSide === 'B' ? ' (w/ Spread)' : '' }}: <strong class="text-indigo-300">{{ sideBEffectiveLiveProj.toFixed(1) }}</strong>
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
