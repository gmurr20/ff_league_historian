<script setup lang="ts">
import { ref, computed } from 'vue';
import type { TradeDetail, TradeWeeklyTrajectoryPoint } from '@/types/api';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import {
  TrendingUp,
  AlertTriangle,
  Zap,
  RotateCcw,
  Scale,
  Calendar,
  Sparkles,
  Info,
} from 'lucide-vue-next';

const props = defineProps<{
  trade: TradeDetail;
}>();

const trajectory = computed<TradeWeeklyTrajectoryPoint[]>(() => {
  return props.trade.weekly_trajectory || [];
});

const sideA = computed(() => props.trade.sides[0] ?? null);
const sideB = computed(() => props.trade.sides[1] ?? null);

// Selected week index on the trajectory scrubber (defaults to latest available week)
const selectedWeekIndex = ref<number | null>(null);

const activePoint = computed<TradeWeeklyTrajectoryPoint | null>(() => {
  if (trajectory.value.length === 0) return null;
  const idx =
    selectedWeekIndex.value !== null &&
    selectedWeekIndex.value >= 0 &&
    selectedWeekIndex.value < trajectory.value.length
      ? selectedWeekIndex.value
      : trajectory.value.length - 1;
  return trajectory.value[idx] ?? null;
});

// Chart coordinate calculations
const width = 640;
const height = 220;
const padLeft = 45;
const padRight = 35;
const padTop = 30;
const padBottom = 35;

const plotWidth = width - padLeft - padRight;
const plotHeight = height - padTop - padBottom;

const maxScore = computed(() => {
  if (trajectory.value.length === 0) return 20;
  let maxVal = 0;
  for (const pt of trajectory.value) {
    maxVal = Math.max(maxVal, pt.side_a_cumulative_score, pt.side_b_cumulative_score);
  }
  return Math.ceil(Math.max(15, maxVal * 1.15));
});

function getX(index: number): number {
  const n = trajectory.value.length;
  if (n <= 1) return padLeft + plotWidth / 2;
  return padLeft + (index / (n - 1)) * plotWidth;
}

function getY(val: number): number {
  const m = maxScore.value || 1;
  const ratio = Math.max(0, Math.min(1, val / m));
  return padTop + plotHeight - ratio * plotHeight;
}

// Side A line path
const pathA = computed(() => {
  if (trajectory.value.length === 0) return '';
  return trajectory.value
    .map((pt, i) => `${i === 0 ? 'M' : 'L'} ${getX(i).toFixed(1)} ${getY(pt.side_a_cumulative_score).toFixed(1)}`)
    .join(' ');
});

// Side B line path
const pathB = computed(() => {
  if (trajectory.value.length === 0) return '';
  return trajectory.value
    .map((pt, i) => `${i === 0 ? 'M' : 'L'} ${getX(i).toFixed(1)} ${getY(pt.side_b_cumulative_score).toFixed(1)}`)
    .join(' ');
});

// Area between curves for filled trajectory
const fillPath = computed(() => {
  if (trajectory.value.length < 2) return '';
  const pts = trajectory.value;
  const forward = pts.map((pt, i) => `${i === 0 ? 'M' : 'L'} ${getX(i).toFixed(1)} ${getY(pt.side_a_cumulative_score).toFixed(1)}`).join(' ');
  const backward = pts
    .slice()
    .reverse()
    .map((pt, i) => `L ${getX(pts.length - 1 - i).toFixed(1)} ${getY(pt.side_b_cumulative_score).toFixed(1)}`)
    .join(' ');
  return `${forward} ${backward} Z`;
});

// Grid lines (3 horizontal guides)
const yGuides = computed(() => {
  const m = maxScore.value;
  return [
    { val: Math.round(m), y: getY(m) },
    { val: Math.round(m / 2), y: getY(m / 2) },
    { val: 0, y: getY(0) },
  ];
});

function getEventIcon(eventType: string) {
  switch (eventType) {
    case 'INJURY_IR':
    case 'INJURY_OUT':
      return AlertTriangle;
    case 'BIG_GAME':
      return Sparkles;
    case 'BENCH_BOOM':
      return Zap;
    case 'FLIPPED':
      return RotateCcw;
    default:
      return Scale;
  }
}

function getEventBadgeClass(severity: string) {
  switch (severity) {
    case 'danger':
      return 'bg-rose-500/20 text-rose-300 border-rose-500/40';
    case 'warning':
      return 'bg-amber-500/20 text-amber-300 border-amber-500/40';
    case 'success':
      return 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40';
    default:
      return 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40';
  }
}
</script>

<template>
  <div class="space-y-3.5">
    <!-- Header: Legend & Value Trajectory Summary -->
    <div class="flex items-center justify-between gap-2 flex-wrap">
      <div class="flex items-center gap-2">
        <div class="w-7 h-7 rounded-lg bg-indigo-500/15 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
          <TrendingUp class="w-4 h-4" />
        </div>
        <div>
          <h4 class="text-xs font-black uppercase tracking-wider text-slate-200 flex items-center gap-2">
            <span>Trade Value Trajectory Over Time</span>
            <span class="text-[10px] font-mono font-semibold px-2 py-0.2 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
              Week-by-Week
            </span>
          </h4>
          <p class="text-[11px] text-slate-400">
            Track how trade balance shifted as injuries, benchings, and breakouts occurred
          </p>
        </div>
      </div>

      <!-- Legend Pills -->
      <div v-if="sideA && sideB" class="flex items-center gap-2 text-xs font-mono font-bold">
        <div class="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-950/40 border border-emerald-500/40 text-emerald-300">
          <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
          <span class="truncate max-w-[120px]" :title="sideA.team_name">{{ sideA.team_name }}</span>
        </div>
        <div class="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-sky-950/40 border border-sky-500/40 text-sky-300">
          <span class="w-2 h-2 rounded-full bg-sky-400"></span>
          <span class="truncate max-w-[120px]" :title="sideB.team_name">{{ sideB.team_name }}</span>
        </div>
      </div>
    </div>

    <!-- Empty Trajectory State -->
    <div
      v-if="trajectory.length === 0"
      class="p-6 rounded-xl bg-slate-950/50 border border-slate-800 text-center text-xs text-slate-400 space-y-1"
    >
      <Info class="w-5 h-5 mx-auto text-slate-500" />
      <p class="font-semibold text-slate-300">No Post-Trade Trajectory Yet</p>
      <p>This trade was executed recently. Trajectory points accumulate as post-trade games are played.</p>
    </div>

    <!-- Interactive SVG Trajectory Canvas -->
    <div
      v-else
      class="rounded-xl border border-slate-800 bg-slate-950/80 p-3 relative overflow-hidden shadow-inner"
    >
      <svg
        :viewBox="`0 0 ${width} ${height}`"
        class="w-full h-auto max-h-[260px] block select-none"
      >
        <defs>
          <linearGradient id="traj-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#10b981" stop-opacity="0.15" />
            <stop offset="100%" stop-color="#0284c7" stop-opacity="0.15" />
          </linearGradient>
          <filter id="glow-point" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <!-- Y-Axis Guides & Labels -->
        <g class="guides">
          <g v-for="g in yGuides" :key="g.val">
            <line
              :x1="padLeft"
              :y1="g.y"
              :x2="width - padRight"
              :y2="g.y"
              stroke="#334155"
              stroke-width="1"
              stroke-dasharray="3, 3"
              stroke-opacity="0.5"
            />
            <text
              :x="padLeft - 6"
              :y="g.y"
              text-anchor="end"
              dominant-baseline="central"
              class="font-mono text-[9px] fill-slate-500 font-bold"
            >
              {{ g.val }}
            </text>
          </g>
        </g>

        <!-- Shaded Differential Area between curves -->
        <path
          v-if="fillPath"
          :d="fillPath"
          fill="url(#traj-fill)"
          opacity="0.8"
        />

        <!-- Side A Line (Emerald) -->
        <path
          :d="pathA"
          fill="none"
          stroke="#10b981"
          stroke-width="2.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />

        <!-- Side B Line (Sky) -->
        <path
          :d="pathB"
          fill="none"
          stroke="#0284c7"
          stroke-width="2.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />

        <!-- Data Points & Milestone Pins on Curves -->
        <g v-for="(pt, idx) in trajectory" :key="`pt-${pt.week}`">
          <!-- Side A Point Circle -->
          <circle
            :cx="getX(idx)"
            :cy="getY(pt.side_a_cumulative_score)"
            r="4"
            fill="#10b981"
            stroke="#0f172a"
            stroke-width="1.5"
            class="transition-transform duration-200 hover:scale-125 cursor-pointer"
            @click="selectedWeekIndex = idx"
          />

          <!-- Side B Point Circle -->
          <circle
            :cx="getX(idx)"
            :cy="getY(pt.side_b_cumulative_score)"
            r="4"
            fill="#0284c7"
            stroke="#0f172a"
            stroke-width="1.5"
            class="transition-transform duration-200 hover:scale-125 cursor-pointer"
            @click="selectedWeekIndex = idx"
          />

          <!-- Event Pins (Alert / Star / Pin above highest point) -->
          <g
            v-if="pt.events && pt.events.length > 0"
            :transform="`translate(${getX(idx)}, ${Math.min(getY(pt.side_a_cumulative_score), getY(pt.side_b_cumulative_score)) - 14})`"
            class="cursor-pointer"
            @click="selectedWeekIndex = idx"
          >
            <!-- Pin badge -->
            <circle
              cx="0"
              cy="0"
              r="7.5"
              :fill="pt.events.some(e => e.severity === 'danger') ? '#e11d48' : pt.events.some(e => e.severity === 'success') ? '#10b981' : '#6366f1'"
              stroke="#0f172a"
              stroke-width="1.5"
              filter="url(#glow-point)"
            />
            <text
              x="0"
              y="0"
              text-anchor="middle"
              dominant-baseline="central"
              class="font-mono text-[8px] font-black fill-white pointer-events-none select-none"
            >
              !
            </text>
          </g>

          <!-- Week Label on X Axis -->
          <text
            :x="getX(idx)"
            :y="height - 12"
            text-anchor="middle"
            class="font-mono text-[10px] font-bold cursor-pointer select-none"
            :class="
              (selectedWeekIndex === idx || (selectedWeekIndex === null && idx === trajectory.length - 1))
                ? 'fill-indigo-300 underline font-black'
                : 'fill-slate-400 hover:fill-slate-200'
            "
            @click="selectedWeekIndex = idx"
          >
            Wk {{ pt.week }}
          </text>
        </g>

        <!-- Active Scrubber Vertical Line -->
        <g v-if="activePoint">
          <line
            :x1="getX(trajectory.findIndex(p => p.week === activePoint?.week))"
            :y1="padTop"
            :x2="getX(trajectory.findIndex(p => p.week === activePoint?.week))"
            :y2="height - padBottom"
            stroke="#6366f1"
            stroke-width="1.5"
            stroke-dasharray="2, 2"
            opacity="0.8"
          />
        </g>
      </svg>
    </div>

    <!-- Active Week Snapshot Card & Event Details -->
    <div
      v-if="activePoint && sideA && sideB"
      class="bg-slate-950/70 rounded-xl p-3.5 border border-slate-800 space-y-3"
    >
      <div class="flex items-center justify-between border-b border-slate-800/80 pb-2 flex-wrap gap-2">
        <div class="flex items-center gap-2">
          <Calendar class="w-3.5 h-3.5 text-indigo-400" />
          <span class="text-xs font-mono font-bold text-slate-200">
            Week {{ activePoint.week }} Snapshot
          </span>
          <span
            v-if="activePoint.cumulative_score_differential >= 1.0"
            class="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700"
          >
            Margin: Δ {{ activePoint.cumulative_score_differential.toFixed(1) }} pts
          </span>
          <span
            v-else
            class="text-[10px] font-mono text-slate-400 bg-slate-800/60 px-2 py-0.5 rounded-full"
          >
            Even Balance
          </span>
        </div>

        <span class="text-[11px] font-mono text-slate-400">
          Click any week above to scrub timeline
        </span>
      </div>

      <!-- Side A vs Side B Snapshot at this Week -->
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono">
        <!-- Side A -->
        <div
          class="p-2.5 rounded-lg border flex items-center justify-between gap-2"
          :class="activePoint.leading_team_id === sideA.team_id ? 'bg-emerald-950/20 border-emerald-500/30' : 'bg-slate-900/60 border-slate-800'"
        >
          <div class="flex items-center gap-2 min-w-0">
            <TeamAvatar :src="sideA.logo_url" :name="sideA.team_name" size="sm" />
            <div class="min-w-0">
              <div class="font-bold text-slate-200 truncate">{{ sideA.team_name }}</div>
              <div class="text-[10px] text-slate-400">
                Wk {{ activePoint.week }}: +{{ activePoint.side_a_starter_points.toFixed(1) }} start • +{{ activePoint.side_a_bench_points.toFixed(1) }} bench
              </div>
            </div>
          </div>
          <div class="text-right shrink-0">
            <div class="text-xs font-black text-emerald-400">
              {{ activePoint.side_a_cumulative_score.toFixed(1) }} cum
            </div>
            <div class="text-[9px] text-slate-400">
              {{ activePoint.side_a_cumulative_starter_points.toFixed(1) }} total start
            </div>
          </div>
        </div>

        <!-- Side B -->
        <div
          class="p-2.5 rounded-lg border flex items-center justify-between gap-2"
          :class="activePoint.leading_team_id === sideB.team_id ? 'bg-sky-950/20 border-sky-500/30' : 'bg-slate-900/60 border-slate-800'"
        >
          <div class="flex items-center gap-2 min-w-0">
            <TeamAvatar :src="sideB.logo_url" :name="sideB.team_name" size="sm" />
            <div class="min-w-0">
              <div class="font-bold text-slate-200 truncate">{{ sideB.team_name }}</div>
              <div class="text-[10px] text-slate-400">
                Wk {{ activePoint.week }}: +{{ activePoint.side_b_starter_points.toFixed(1) }} start • +{{ activePoint.side_b_bench_points.toFixed(1) }} bench
              </div>
            </div>
          </div>
          <div class="text-right shrink-0">
            <div class="text-xs font-black text-sky-400">
              {{ activePoint.side_b_cumulative_score.toFixed(1) }} cum
            </div>
            <div class="text-[9px] text-slate-400">
              {{ activePoint.side_b_cumulative_starter_points.toFixed(1) }} total start
            </div>
          </div>
        </div>
      </div>

      <!-- Events in Active Week (Injuries, Big Games, Flips) -->
      <div v-if="activePoint.events && activePoint.events.length > 0" class="space-y-1.5 pt-1">
        <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400">
          Week {{ activePoint.week }} Turning Points & Events:
        </div>
        <div class="space-y-1.5">
          <div
            v-for="(ev, eIdx) in activePoint.events"
            :key="`${ev.event_type}-${eIdx}`"
            class="flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-xs"
            :class="getEventBadgeClass(ev.severity)"
          >
            <component :is="getEventIcon(ev.event_type)" class="w-4 h-4 shrink-0" />
            <div class="min-w-0 flex-1">
              <span class="font-bold">{{ ev.title }}:</span>
              <span class="ml-1 opacity-90">{{ ev.description }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>