<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue';
import type { StandingEntry } from '@/types/api';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';

const props = withDefaults(
  defineProps<{
    standings: StandingEntry[];
    playoffTeamCount: number;
    regularSeasonWeeks?: number;
    trophyName?: string;
    selectedTeamId?: number | null;
  }>(),
  {
    regularSeasonWeeks: 14,
    trophyName: 'The Paulie',
    selectedTeamId: null,
  }
);

const emit = defineEmits<{
  (e: 'update:selectedTeamId', teamId: number | null): void;
  (e: 'openTeamDetail', team: StandingEntry): void;
}>();

// Curated 12-color high-contrast palette (Mario Party / F1 telemetry inspired)
const TEAM_PALETTE = [
  '#f59e0b', // 1. Trophy Amber
  '#06b6d4', // 2. Electric Cyan
  '#10b981', // 3. Turf Emerald
  '#f43f5e', // 4. Coral Rose
  '#a855f7', // 5. Vivid Purple
  '#38bdf8', // 6. Sky Blue
  '#f97316', // 7. Blaze Orange
  '#84cc16', // 8. Volt Lime
  '#ec4899', // 9. Hot Pink
  '#818cf8', // 10. Soft Indigo
  '#2dd4bf', // 11. Mint Teal
  '#eab308', // 12. Gold Yellow
];

// Multi-select spotlight set so users can isolate 1 team or compare 2-3 rivals
const spotlightIds = ref<Set<number>>(new Set());

watch(
  () => props.selectedTeamId,
  (val) => {
    if (val === null || val === undefined) {
      spotlightIds.value = new Set();
    } else if (!spotlightIds.value.has(val)) {
      spotlightIds.value = new Set([val]);
    }
  },
  { immediate: true }
);

const hasSpotlight = computed(() => spotlightIds.value.size > 0);

function isTeamSpotlighted(teamId: number): boolean {
  return spotlightIds.value.has(teamId);
}

function toggleTeamSpotlight(teamId: number) {
  const next = new Set(spotlightIds.value);
  if (next.has(teamId)) {
    next.delete(teamId);
  } else {
    next.add(teamId);
  }
  spotlightIds.value = next;
  const first = next.size === 1 ? Array.from(next)[0] : null;
  emit('update:selectedTeamId', first);
}

function clearSpotlight() {
  spotlightIds.value = new Set();
  emit('update:selectedTeamId', null);
}

// Sort teams by official standings rank
const orderedTeams = computed<StandingEntry[]>(() => {
  return [...props.standings].sort((a, b) => a.rank - b.rank);
});

const teamColorMap = computed<Record<number, string>>(() => {
  const map: Record<number, string> = {};
  orderedTeams.value.forEach((team, idx) => {
    map[team.team_id] = TEAM_PALETTE[idx % TEAM_PALETTE.length];
  });
  return map;
});

function getTeamColor(teamId: number): string {
  return teamColorMap.value[teamId] ?? '#10b981';
}

function getAbbrev(team: StandingEntry): string {
  if (team.team_abbrev && team.team_abbrev.trim().length > 0) {
    return team.team_abbrev.trim().toUpperCase().slice(0, 4);
  }
  return (
    team.team_name
      .replace(/[^A-Za-z0-9 ]/g, '')
      .split(' ')
      .filter(Boolean)
      .map((w) => w[0])
      .join('')
      .toUpperCase()
      .slice(0, 3) || 'TM'
  );
}

// Available weeks across all teams
const weeks = computed<number[]>(() => {
  const weekSet = new Set<number>();
  for (const t of props.standings) {
    for (const pt of t.weekly_history ?? []) {
      weekSet.add(pt.week);
    }
  }
  return Array.from(weekSet).sort((a, b) => a - b);
});

// Continuous playhead (0.0 .. weeks.length - 1) driven by requestAnimationFrame
// so lines draw directly behind the gliding team icons at a relaxed, readable pace.
const playhead = ref<number>(0);
const isPlaying = ref<boolean>(false);
let rafId: number | null = null;
const chartRootRef = ref<HTMLElement | null>(null);
let observer: IntersectionObserver | null = null;
const hasAutoPlayed = ref<boolean>(false);

// Timing constants (ms) — ~1.15s steady glide per week with a crisp 380ms pause between weeks
const GLIDE_DURATION_MS = 1150; // 1.15s transition between weeks
const HOLD_DURATION_MS = 380;   // 380ms pause at each week stop
const TWEEN_DURATION_MS = 800;  // 0.8s smooth tween when tapping a single week

// Gentle sine-blended easing so velocity stays smooth and doesn't stall at week boundaries
function easeGlide(u: number): number {
  const sine = 0.5 - 0.5 * Math.cos(Math.PI * u);
  return 0.35 * u + 0.65 * sine;
}

function cubicBezier(p0: number, p1: number, p2: number, p3: number, t: number): number {
  const mt = 1 - t;
  return (
    mt * mt * mt * p0 +
    3 * mt * mt * t * p1 +
    3 * mt * t * t * p2 +
    t * t * t * p3
  );
}

const activeWeekIdx = computed<number>(() => {
  if (!weeks.value.length) return 0;
  return Math.min(Math.max(0, Math.round(playhead.value)), weeks.value.length - 1);
});

const activeWeek = computed<number>(() => {
  if (!weeks.value.length) return 1;
  return weeks.value[activeWeekIdx.value] ?? 1;
});

const activeWeekLabel = computed<string>(() => {
  const w = activeWeek.value;
  const regW = props.regularSeasonWeeks;
  const maxW = weeks.value.length ? weeks.value[weeks.value.length - 1] : regW;
  if (w <= regW) return `WEEK ${w}`;
  if (w === maxW) return `WEEK ${w} · THE SHIP`;
  if (w === maxW - 1) return `WEEK ${w} · SEMIFINALS`;
  if (w === maxW - 2) return `WEEK ${w} · QUARTERFINALS`;
  return `WEEK ${w} · PLAYOFFS`;
});

function formatScrubWeek(w: number): string {
  const regW = props.regularSeasonWeeks;
  const maxW = weeks.value.length ? weeks.value[weeks.value.length - 1] : regW;
  if (w <= regW) return `W${w}`;
  if (w === maxW) return '🏆 Final';
  if (w === maxW - 1) return 'SF';
  if (w === maxW - 2) return 'QF';
  return `R${w - regW}`;
}

function stopAnimation() {
  if (rafId !== null) {
    cancelAnimationFrame(rafId);
    rafId = null;
  }
  isPlaying.value = false;
}

// Smoothly tween playhead from current position to a target week index
function tweenToWeekIndex(targetIdx: number) {
  stopAnimation();
  const maxIdx = Math.max(0, weeks.value.length - 1);
  const clampedTarget = Math.min(Math.max(0, targetIdx), maxIdx);
  const startVal = playhead.value;
  const diff = clampedTarget - startVal;
  if (Math.abs(diff) < 0.005) {
    playhead.value = clampedTarget;
    return;
  }

  const duration = Math.min(1200, Math.max(550, Math.abs(diff) * TWEEN_DURATION_MS));
  const startTime = performance.now();

  const step = (now: number) => {
    const u = Math.min(1, (now - startTime) / duration);
    playhead.value = startVal + diff * easeGlide(u);
    if (u < 1) {
      rafId = requestAnimationFrame(step);
    } else {
      playhead.value = clampedTarget;
      rafId = null;
    }
  };
  rafId = requestAnimationFrame(step);
}

// Full Mario Party race playback: glides week-to-week with a brief readable hold on each week
function startPlayback(fromStart = false) {
  stopAnimation();
  const maxIdx = weeks.value.length - 1;
  if (maxIdx <= 0) return;

  if (fromStart || playhead.value >= maxIdx - 0.02) {
    playhead.value = 0;
  }

  isPlaying.value = true;
  let currentFromWeek = Math.floor(playhead.value);
  let phase: 'hold' | 'glide' =
    Math.abs(playhead.value - currentFromWeek) < 0.01 ? 'hold' : 'glide';
  let phaseStartTime = performance.now();
  const initialFrac = playhead.value - currentFromWeek;

  const loop = (now: number) => {
    if (!isPlaying.value) return;

    if (phase === 'hold') {
      const holdElapsed = now - phaseStartTime;
      const holdTarget = currentFromWeek === 0 ? 60 : HOLD_DURATION_MS;
      if (holdElapsed >= holdTarget) {
        if (currentFromWeek >= maxIdx) {
          playhead.value = maxIdx;
          stopAnimation();
          return;
        }
        phase = 'glide';
        phaseStartTime = now;
      }
    } else {
      const glideElapsed = now - phaseStartTime;
      const rawU = Math.min(1, glideElapsed / GLIDE_DURATION_MS);
      const easedT = easeGlide(rawU);
      const startOffset = currentFromWeek + (rawU === 0 ? initialFrac : 0);
      playhead.value = Math.min(
        maxIdx,
        currentFromWeek + easedT * (1 - (startOffset - currentFromWeek))
      );

      if (rawU >= 1) {
        currentFromWeek += 1;
        playhead.value = currentFromWeek;
        if (currentFromWeek >= maxIdx) {
          stopAnimation();
          return;
        }
        phase = 'hold';
        phaseStartTime = now;
      }
    }

    rafId = requestAnimationFrame(loop);
  };

  rafId = requestAnimationFrame(loop);
}

function togglePlayback() {
  if (isPlaying.value) {
    stopAnimation();
  } else {
    startPlayback(playhead.value >= weeks.value.length - 1.02);
  }
}

function selectWeekIdx(idx: number) {
  tweenToWeekIndex(idx);
}

function stepWeek(delta: number) {
  const target = activeWeekIdx.value + delta;
  if (target >= 0 && target < weeks.value.length) {
    tweenToWeekIndex(target);
  }
}

watch(
  () => weeks.value,
  (newWeeks) => {
    stopAnimation();
    if (newWeeks.length > 0) {
      playhead.value = newWeeks.length - 1;
    }
  },
  { immediate: true }
);

// Responsive mobile detection to expand vertical height on phones
const isMobile = ref<boolean>(
  typeof window !== 'undefined' ? window.innerWidth < 640 : false
);

let mediaQueryList: MediaQueryList | null = null;

function handleMediaChange(e: MediaQueryListEvent | MediaQueryList) {
  isMobile.value = e.matches;
}

onMounted(() => {
  if (typeof window !== 'undefined') {
    mediaQueryList = window.matchMedia('(max-width: 640px)');
    isMobile.value = mediaQueryList.matches;
    if (mediaQueryList.addEventListener) {
      mediaQueryList.addEventListener('change', handleMediaChange);
    } else {
      mediaQueryList.addListener(handleMediaChange);
    }
  }

  if (typeof IntersectionObserver !== 'undefined' && chartRootRef.value) {
    observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (entry && entry.isIntersecting && !hasAutoPlayed.value && weeks.value.length > 1) {
          hasAutoPlayed.value = true;
          startPlayback(true);
        }
      },
      { threshold: 0.35 }
    );
    observer.observe(chartRootRef.value);
  }
});

onBeforeUnmount(() => {
  stopAnimation();
  if (mediaQueryList) {
    if (mediaQueryList.removeEventListener) {
      mediaQueryList.removeEventListener('change', handleMediaChange);
    } else {
      mediaQueryList.removeListener(handleMediaChange);
    }
    mediaQueryList = null;
  }
  if (observer) {
    observer.disconnect();
    observer = null;
  }
});

const teamCount = computed(() => Math.max(1, props.standings.length));

// Responsive SVG geometry: taller on mobile so logos and tags never overlap vertically,
// compact widescreen on tablet/desktop for easy viewing.
const svgWidth = 720;
const svgHeight = computed(() => {
  const count = teamCount.value;
  if (isMobile.value) {
    // Generous vertical spacing on mobile: ~50px per rank in SVG coordinate space
    return Math.max(420, count * 50 + 44);
  }
  return Math.max(220, count * 24 + 36);
});
const padLeft = 28;
const padRight = computed(() => (isMobile.value ? 116 : 96));
const padTop = 18;
const padBottom = 22;

const plotWidth = computed(() => svgWidth - padLeft - padRight.value);
const plotHeight = computed(() => svgHeight.value - padTop - padBottom);

function xForWeekIndex(idx: number): number {
  const total = weeks.value.length;
  if (total <= 1) return padLeft + plotWidth.value / 2;
  return padLeft + (idx / (total - 1)) * plotWidth.value;
}

function yForRank(rank: number): number {
  const n = teamCount.value;
  if (n <= 1) return padTop + plotHeight.value / 2;
  return padTop + ((rank - 1) / (n - 1)) * plotHeight.value;
}

// Current X coordinate of the moving playhead (used to clip active SVG lines right behind the avatars)
const currentHeadX = computed<number>(() => {
  const total = weeks.value.length;
  if (total <= 1) return svgWidth;
  const maxIdx = total - 1;
  const clamped = Math.min(Math.max(0, playhead.value), maxIdx);
  const k = Math.min(Math.floor(clamped), maxIdx - 1);
  const t = clamped - k;
  const x0 = xForWeekIndex(k);
  const x3 = xForWeekIndex(k + 1);
  const dx = (x3 - x0) * 0.4;
  return cubicBezier(x0, x0 + dx, x3 - dx, x3, t);
});

// Playoff cutoff Y coordinate (halfway between playoffTeamCount and playoffTeamCount + 1)
const playoffLineY = computed<number | null>(() => {
  const cutoff = props.playoffTeamCount;
  if (!cutoff || cutoff <= 0 || cutoff >= teamCount.value) return null;
  return (yForRank(cutoff) + yForRank(cutoff + 1)) / 2;
});

interface PlotNode {
  week: number;
  weekIdx: number;
  x: number;
  y: number;
  rank: number;
  prevRank: number | null;
  rankDelta: number; // positive = climbed up in this week
  weeklyScore: number;
  recordStr: string;
}

interface TeamSeries {
  team: StandingEntry;
  color: string;
  abbrev: string;
  nodes: PlotNode[];
  fullPathD: string;
  activeNode: PlotNode | null;
  headX: number;
  headY: number;
}

function buildSmoothBumpPath(nodes: PlotNode[]): string {
  if (nodes.length === 0) return '';
  if (nodes.length === 1) {
    return `M ${nodes[0].x} ${nodes[0].y}`;
  }
  let d = `M ${nodes[0].x.toFixed(1)} ${nodes[0].y.toFixed(1)}`;
  for (let i = 0; i < nodes.length - 1; i++) {
    const curr = nodes[i];
    const next = nodes[i + 1];
    const dx = (next.x - curr.x) * 0.4;
    const c1x = curr.x + dx;
    const c1y = curr.y;
    const c2x = next.x - dx;
    const c2y = next.y;
    d += ` C ${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(1)} ${c2y.toFixed(1)}, ${next.x.toFixed(1)} ${next.y.toFixed(1)}`;
  }
  return d;
}

const seriesList = computed<TeamSeries[]>(() => {
  const wList = weeks.value;
  const currentPlayhead = playhead.value;
  const nearestIdx = activeWeekIdx.value;

  return orderedTeams.value.map((team) => {
    const historyMap = new Map(
      (team.weekly_history ?? []).map((h) => [h.week, h])
    );
    const nodes: PlotNode[] = [];
    let prevRank: number | null = null;

    wList.forEach((w, idx) => {
      const pt = historyMap.get(w);
      if (!pt) return;
      const rank = pt.standings_rank;
      const rankDelta = prevRank !== null ? prevRank - rank : 0;
      nodes.push({
        week: w,
        weekIdx: idx,
        x: xForWeekIndex(idx),
        y: yForRank(rank),
        rank,
        prevRank,
        rankDelta,
        weeklyScore: pt.weekly_score,
        recordStr: `${pt.wins}-${pt.losses}`,
      });
      prevRank = rank;
    });

    const activeNode = nodes[nearestIdx] ?? nodes[nodes.length - 1] ?? null;

    // Interpolate exact (headX, headY) along the cubic bezier segment at `playhead`
    let headX = activeNode?.x ?? 0;
    let headY = activeNode?.y ?? 0;
    if (nodes.length > 1) {
      const maxIdx = nodes.length - 1;
      const clamped = Math.min(Math.max(0, currentPlayhead), maxIdx);
      const k = Math.min(Math.floor(clamped), maxIdx - 1);
      const t = clamped - k;
      const n0 = nodes[k];
      const n1 = nodes[k + 1];
      if (n0 && n1) {
        const dx = (n1.x - n0.x) * 0.4;
        headX = cubicBezier(n0.x, n0.x + dx, n1.x - dx, n1.x, t);
        headY = cubicBezier(n0.y, n0.y, n1.y, n1.y, t);
      }
    }

    return {
      team,
      color: getTeamColor(team.team_id),
      abbrev: getAbbrev(team),
      nodes,
      fullPathD: buildSmoothBumpPath(nodes),
      activeNode,
      headX,
      headY,
    };
  });
});

// Sort SVG render order so spotlighted teams and top ranks draw cleanly on top
const renderOrderedSeries = computed<TeamSeries[]>(() => {
  return [...seriesList.value].sort((a, b) => {
    const aSpot = isTeamSpotlighted(a.team.team_id) ? 1 : 0;
    const bSpot = isTeamSpotlighted(b.team.team_id) ? 1 : 0;
    if (aSpot !== bSpot) return aSpot - bSpot;
    const aRank = a.activeNode?.rank ?? a.team.rank;
    const bRank = b.activeNode?.rank ?? b.team.rank;
    return bRank - aRank;
  });
});

// Weekly Storyline Callouts for the currently active week (Leader, Biggest Climber, Biggest Fall)
const activeWeekStorylines = computed(() => {
  const activeItems = seriesList.value
    .map((s) => ({ series: s, node: s.activeNode }))
    .filter((x): x is { series: TeamSeries; node: PlotNode } => x.node !== null);

  if (!activeItems.length) return null;

  const leader = [...activeItems].sort((a, b) => a.node.rank - b.node.rank)[0];
  const highScorer = [...activeItems].sort((a, b) => b.node.weeklyScore - a.node.weeklyScore)[0];

  const climbers = activeItems
    .filter((x) => x.node.rankDelta > 0)
    .sort((a, b) => b.node.rankDelta - a.node.rankDelta || a.node.rank - b.node.rank);
  const fallers = activeItems
    .filter((x) => x.node.rankDelta < 0)
    .sort((a, b) => a.node.rankDelta - b.node.rankDelta || b.node.rank - a.node.rank);

  return {
    leader,
    highScorer,
    biggestClimber: climbers[0] ?? null,
    biggestFaller: fallers[0] ?? null,
  };
});

// Single spotlighted team detail when exactly 1 team is selected
const singleSpotlight = computed<TeamSeries | null>(() => {
  if (spotlightIds.value.size !== 1) return null;
  const id = Array.from(spotlightIds.value)[0];
  return seriesList.value.find((s) => s.team.team_id === id) ?? null;
});
</script>

<template>
  <div
    ref="chartRootRef"
    class="rounded-xl border border-slate-800/90 bg-[#0b101b] overflow-hidden shadow-lg"
  >
    <!-- Top Header & Playback Controls -->
    <div class="px-3.5 py-2.5 border-b border-slate-800/80 flex items-center justify-between gap-2">
      <div class="flex items-center gap-2 min-w-0">
        <span class="inline-flex items-center gap-1.5 text-xs sm:text-sm font-black tracking-tight text-amber-400 uppercase">
          <span class="text-sm">🏆</span>
          <span>Race for {{ props.trophyName }}</span>
        </span>
        <span class="text-slate-700">·</span>
        <span class="text-xs font-mono font-bold text-slate-300">
          {{ activeWeekLabel }}
        </span>
      </div>

      <!-- Replay / Step Controls -->
      <div class="flex items-center gap-1.5 shrink-0">
        <button
          type="button"
          class="px-2.5 py-1 rounded-md text-[11px] font-mono font-bold transition-all border flex items-center gap-1 active:scale-95"
          :class="
            isPlaying
              ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
              : 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30 hover:bg-emerald-500/25'
          "
          @click="togglePlayback"
        >
          <span>{{ isPlaying ? '⏸ Pause' : '▶ Play Race' }}</span>
        </button>

        <div class="inline-flex items-center rounded-md bg-slate-900 border border-slate-800 font-mono text-xs">
          <button
            type="button"
            class="px-2 py-0.5 text-slate-400 hover:text-slate-100 disabled:opacity-30"
            :disabled="activeWeekIdx <= 0"
            aria-label="Previous Week"
            @click="stepWeek(-1)"
          >
            ‹
          </button>
          <span class="text-[10px] text-slate-400 px-1 select-none">
            W{{ activeWeek }}
          </span>
          <button
            type="button"
            class="px-2 py-0.5 text-slate-400 hover:text-slate-100 disabled:opacity-30"
            :disabled="activeWeekIdx >= weeks.length - 1"
            aria-label="Next Week"
            @click="stepWeek(1)"
          >
            ›
          </button>
        </div>
      </div>
    </div>

    <!-- Live Week Storylines Bar (Updates dynamically as week plays/scrubs) -->
    <div
      v-if="activeWeekStorylines"
      class="px-3 py-1.5 bg-slate-900/75 border-b border-slate-800/70 grid grid-cols-3 gap-2 text-[10px] font-mono"
    >
      <!-- #1 Leader that week -->
      <div class="flex items-center gap-1.5 min-w-0">
        <TeamAvatar
          :src="activeWeekStorylines.leader.series.team.logo_url"
          :name="activeWeekStorylines.leader.series.team.team_name"
          size="xs"
          rounded="full"
        />
        <div class="min-w-0">
          <div class="text-[9px] uppercase text-slate-500 leading-none">#1 Seed</div>
          <div class="text-slate-200 font-bold truncate leading-tight mt-0.5">
            {{ activeWeekStorylines.leader.series.abbrev }}
            <span class="text-amber-400">({{ activeWeekStorylines.leader.node.recordStr }})</span>
          </div>
        </div>
      </div>

      <!-- Biggest Climber that week (or Week High Scorer in Week 1) -->
      <div v-if="activeWeekStorylines.biggestClimber" class="flex items-center gap-1.5 min-w-0">
        <TeamAvatar
          :src="activeWeekStorylines.biggestClimber.series.team.logo_url"
          :name="activeWeekStorylines.biggestClimber.series.team.team_name"
          size="xs"
          rounded="full"
        />
        <div class="min-w-0">
          <div class="text-[9px] uppercase text-slate-500 leading-none">Riser</div>
          <div class="text-slate-200 font-bold truncate leading-tight mt-0.5">
            {{ activeWeekStorylines.biggestClimber.series.abbrev }}
            <span class="text-emerald-400">▲{{ activeWeekStorylines.biggestClimber.node.rankDelta }}</span>
          </div>
        </div>
      </div>
      <div v-else class="flex items-center gap-1.5 min-w-0">
        <TeamAvatar
          :src="activeWeekStorylines.highScorer.series.team.logo_url"
          :name="activeWeekStorylines.highScorer.series.team.team_name"
          size="xs"
          rounded="full"
        />
        <div class="min-w-0">
          <div class="text-[9px] uppercase text-slate-500 leading-none">Wk High</div>
          <div class="text-slate-200 font-bold truncate leading-tight mt-0.5">
            {{ activeWeekStorylines.highScorer.series.abbrev }}
            <span class="text-emerald-400">{{ activeWeekStorylines.highScorer.node.weeklyScore.toFixed(1) }}</span>
          </div>
        </div>
      </div>

      <!-- Biggest Faller that week (or High Scorer if no faller) -->
      <div v-if="activeWeekStorylines.biggestFaller" class="flex items-center gap-1.5 min-w-0">
        <TeamAvatar
          :src="activeWeekStorylines.biggestFaller.series.team.logo_url"
          :name="activeWeekStorylines.biggestFaller.series.team.team_name"
          size="xs"
          rounded="full"
        />
        <div class="min-w-0">
          <div class="text-[9px] uppercase text-slate-500 leading-none">Faller</div>
          <div class="text-slate-200 font-bold truncate leading-tight mt-0.5">
            {{ activeWeekStorylines.biggestFaller.series.abbrev }}
            <span class="text-rose-400">▼{{ Math.abs(activeWeekStorylines.biggestFaller.node.rankDelta) }}</span>
          </div>
        </div>
      </div>
      <div v-else class="flex items-center gap-1.5 min-w-0">
        <div class="min-w-0">
          <div class="text-[9px] uppercase text-slate-500 leading-none">Status</div>
          <div class="text-slate-400 truncate leading-tight mt-0.5">Opening Week</div>
        </div>
      </div>
    </div>

    <!-- Spotlight Telemetry Banner (When 1 or more teams are tapped) -->
    <div
      v-if="hasSpotlight"
      class="px-3.5 py-2 bg-slate-900/95 border-b border-slate-800/80 flex items-center justify-between gap-2"
    >
      <div v-if="singleSpotlight" class="flex items-center gap-2 min-w-0">
        <span
          class="w-2.5 h-2.5 rounded-full shrink-0"
          :style="{ backgroundColor: singleSpotlight.color }"
        ></span>
        <span class="text-xs font-bold text-slate-100 truncate flex items-center gap-1">
          <span v-if="singleSpotlight.team.is_defending_champion" class="text-amber-400 text-xs shrink-0" :title="`Defending ${props.trophyName} Champion`">🏆</span>
          <span class="truncate">{{ singleSpotlight.team.team_name }}</span>
          <span
            v-if="singleSpotlight.team.championships > 0"
            class="text-amber-400 text-xs leading-none shrink-0"
            :title="`${singleSpotlight.team.championships}x Champion`"
          >
            {{ '★'.repeat(Math.min(singleSpotlight.team.championships, 3)) }}
          </span>
        </span>
        <span class="text-[10px] font-mono text-slate-400 shrink-0">
          W{{ activeWeek }}: #{{ singleSpotlight.activeNode?.rank ?? singleSpotlight.team.rank }}
          ({{ singleSpotlight.activeNode?.recordStr ?? '' }})
        </span>
      </div>
      <div v-else class="text-xs font-mono text-slate-300 truncate">
        Comparing <strong class="text-emerald-400">{{ spotlightIds.size }}</strong> franchises
      </div>

      <div class="flex items-center gap-1.5 shrink-0">
        <button
          v-if="singleSpotlight"
          type="button"
          class="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-slate-800 text-slate-200 hover:bg-slate-700 border border-slate-700/70"
          @click="emit('openTeamDetail', singleSpotlight.team)"
        >
          Team Card
        </button>
        <button
          type="button"
          class="px-2 py-0.5 rounded text-[10px] font-mono text-slate-400 hover:text-slate-200 bg-slate-900 border border-slate-800"
          @click="clearSpotlight"
        >
          Show All
        </button>
      </div>
    </div>

    <!-- Mario Party SVG Canvas + Gliding Team Avatar Icons Overlay -->
    <div v-if="weeks.length > 0" class="px-1.5 pt-2 pb-1 select-none">
      <div
        class="relative w-full"
        :style="{ aspectRatio: `${svgWidth} / ${svgHeight}` }"
      >
        <svg
          :viewBox="`0 0 ${svgWidth} ${svgHeight}`"
          class="w-full h-full block overflow-visible"
          role="img"
          :aria-label="`Race for ${props.trophyName} Trajectory Chart`"
        >
          <defs>
            <!-- Continuous playhead clip path so lines draw right out of the moving team avatars -->
            <clipPath id="race-playhead-clip">
              <rect x="0" y="0" :width="currentHeadX" :height="svgHeight" />
            </clipPath>
          </defs>

          <!-- Horizontal Rank Grid Tracks (1 .. N) -->
          <g v-for="r in teamCount" :key="`rank-row-${r}`">
            <line
              :x1="padLeft"
              :y1="yForRank(r)"
              :x2="svgWidth - padRight"
              :y2="yForRank(r)"
              stroke="#1e293b"
              stroke-width="1"
              :stroke-dasharray="r === 1 ? 'none' : '2,4'"
              opacity="0.6"
            />
            <!-- Left Y-Axis Rank Label -->
            <text
              :x="padLeft - 10"
              :y="yForRank(r) + 3.5"
              text-anchor="end"
              class="font-mono text-[10px] font-bold"
              :fill="r === 1 ? '#fbbf24' : r <= playoffTeamCount ? '#94a3b8' : '#475569'"
            >
              {{ r }}
            </text>
          </g>

          <!-- Playoff Cutoff Divider Line -->
          <g v-if="playoffLineY !== null">
            <line
              :x1="padLeft"
              :y1="playoffLineY"
              :x2="svgWidth - padRight"
              :y2="playoffLineY"
              stroke="#10b981"
              stroke-width="1.2"
              stroke-dasharray="5,4"
              opacity="0.55"
            />
            <text
              :x="padLeft + 4"
              :y="playoffLineY - 4"
              class="font-mono text-[8.5px] uppercase tracking-widest fill-emerald-400/80 font-bold"
            >
              PLAYOFF CUTLINE
            </text>
          </g>

          <!-- Vertical Week Grid Lines & X-Axis Labels -->
          <g
            v-for="(w, wIdx) in weeks"
            :key="`week-col-${w}`"
            class="cursor-pointer"
            @click="selectWeekIdx(wIdx)"
          >
            <!-- Active Week Highlight Column Band -->
            <rect
              v-if="wIdx === activeWeekIdx"
              :x="xForWeekIndex(wIdx) - 12"
              :y="padTop - 10"
              width="24"
              :height="plotHeight + 20"
              rx="6"
              fill="#1e293b"
              opacity="0.35"
            />
            <line
              :x1="xForWeekIndex(wIdx)"
              :y1="padTop - 6"
              :x2="xForWeekIndex(wIdx)"
              :y2="svgHeight - padBottom + 6"
              :stroke="wIdx === activeWeekIdx ? '#38bdf8' : '#1e293b'"
              :stroke-width="wIdx === activeWeekIdx ? 1.5 : 1"
              :opacity="wIdx === activeWeekIdx ? 0.5 : 0.45"
            />
            <text
              :x="xForWeekIndex(wIdx)"
              :y="svgHeight - 8"
              text-anchor="middle"
              class="font-mono text-[9px] font-bold"
              :fill="wIdx === activeWeekIdx ? '#f8fafc' : '#64748b'"
            >
              {{ formatScrubWeek(w) }}
            </text>
          </g>

          <!-- Team Trajectory Lines -->
          <g
            v-for="s in renderOrderedSeries"
            :key="`series-${s.team.team_id}`"
            class="cursor-pointer transition-opacity duration-200"
            :opacity="
              !hasSpotlight
                ? (s.activeNode?.rank ?? s.team.rank) <= 3
                  ? 0.92
                  : 0.68
                : isTeamSpotlighted(s.team.team_id)
                ? 1
                : 0.12
            "
            @click="toggleTeamSpotlight(s.team.team_id)"
          >
            <!-- Faint future ghost path across all weeks -->
            <path
              :d="s.fullPathD"
              fill="none"
              :stroke="s.color"
              stroke-width="1.2"
              stroke-dasharray="3,3"
              opacity="0.16"
            />

            <!-- Wide invisible touch target path -->
            <path
              :d="s.fullPathD"
              fill="none"
              stroke="transparent"
              stroke-width="14"
              stroke-linecap="round"
            />

            <!-- Clipped active trail that draws smoothly behind the moving avatar -->
            <g clip-path="url(#race-playhead-clip)">
              <!-- Dark casing under-stroke so line crossings have crisp depth -->
              <path
                :d="s.fullPathD"
                fill="none"
                stroke="#0b101b"
                :stroke-width="isTeamSpotlighted(s.team.team_id) ? 6.5 : 4.2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />

              <!-- Active colored trajectory path -->
              <path
                :d="s.fullPathD"
                fill="none"
                :stroke="s.color"
                :stroke-width="
                  isTeamSpotlighted(s.team.team_id)
                    ? 3.8
                    : !hasSpotlight && (s.activeNode?.rank ?? s.team.rank) <= 3
                    ? 2.8
                    : 2.1
                "
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </g>

            <!-- Past Week Vertex Dots (for weeks already passed by the playhead) -->
            <g
              v-for="node in s.nodes.filter((n) => n.weekIdx < playhead - 0.15)"
              :key="`node-${s.team.team_id}-${node.week}`"
            >
              <circle
                :cx="node.x"
                :cy="node.y"
                :r="isTeamSpotlighted(s.team.team_id) ? 6 : 2.8"
                :fill="isTeamSpotlighted(s.team.team_id) ? '#0b101b' : s.color"
                :stroke="isTeamSpotlighted(s.team.team_id) ? s.color : '#0b101b'"
                :stroke-width="isTeamSpotlighted(s.team.team_id) ? 2 : 1.2"
              />
              <text
                v-if="isTeamSpotlighted(s.team.team_id)"
                :x="node.x"
                :y="node.y + 3"
                text-anchor="middle"
                class="font-mono text-[8px] font-black fill-slate-100"
              >
                {{ node.rank }}
              </text>
            </g>
          </g>
        </svg>

        <!-- Gliding Team Avatar Icons Centered Exactly on (headX, headY) -->
        <button
          v-for="s in seriesList"
          v-show="s.activeNode !== null"
          :key="`racer-${s.team.team_id}`"
          type="button"
          class="absolute -translate-x-1/2 -translate-y-1/2 w-[18px] h-[18px] sm:w-5 sm:h-5 flex items-center justify-center group focus:outline-none transition-opacity duration-200"
          :style="{
            left: `${(s.headX / svgWidth) * 100}%`,
            top: `${(s.headY / svgHeight) * 100}%`,
            zIndex: isTeamSpotlighted(s.team.team_id)
              ? 30
              : 20 - (s.activeNode?.rank ?? 12),
            opacity: !hasSpotlight || isTeamSpotlighted(s.team.team_id) ? 1 : 0.18,
          }"
          :title="`${s.team.team_name} (#${s.activeNode?.rank} in Week ${activeWeek})`"
          @click.stop="toggleTeamSpotlight(s.team.team_id)"
        >
          <!-- Circular Team Logo with Team Color Ring (Centered at headX, headY) -->
          <div
            class="w-full h-full rounded-full p-[1.5px] shadow-md transition-transform group-hover:scale-110"
            :class="[
              isTeamSpotlighted(s.team.team_id)
                ? 'scale-125 ring-2 ring-white/80'
                : s.team.is_defending_champion
                ? 'ring-2 ring-amber-400/90 shadow-[0_0_8px_rgba(251,191,36,0.6)]'
                : '',
            ]"
            :style="{ backgroundColor: s.color }"
          >
            <TeamAvatar
              :src="s.team.logo_url"
              :name="s.team.team_name"
              size="xs"
              rounded="full"
              class="!w-full !h-full !border-0 text-[8px]"
            />
          </div>

          <!-- Right-Side Live Tag (Positioned outside button box so avatar stays dead-center on line) -->
          <div
            class="
              absolute left-full ml-1.5 top-1/2 -translate-y-1/2
              px-1.5 py-0.5 rounded bg-[#0f172a]/95 border
              text-[9px] sm:text-[10px] font-mono font-bold whitespace-nowrap
              flex items-center gap-1 shadow-sm pointer-events-none
            "
            :style="{
              borderColor: isTeamSpotlighted(s.team.team_id) ? s.color : 'rgba(51, 65, 85, 0.8)',
            }"
          >
            <span class="text-slate-400">#{{ s.activeNode?.rank }}</span>
            <span v-if="s.team.is_defending_champion" class="hidden sm:inline text-amber-400 text-[10px]" title="Defending Champion">🏆</span>
            <span class="text-slate-100">{{ s.abbrev }}</span>
            <span
              v-if="s.team.championships > 0"
              class="hidden sm:inline text-amber-400 text-[8px] leading-none select-none"
              :title="`${s.team.championships}x Champion`"
            >
              {{ '★'.repeat(Math.min(s.team.championships, 3)) }}
            </span>
            <span
              v-if="s.activeNode && s.activeNode.rankDelta > 0"
              class="text-[8px] text-emerald-400 font-black"
            >
              ▲{{ s.activeNode.rankDelta }}
            </span>
            <span
              v-else-if="s.activeNode && s.activeNode.rankDelta < 0"
              class="text-[8px] text-rose-400 font-black"
            >
              ▼{{ Math.abs(s.activeNode.rankDelta) }}
            </span>
          </div>
        </button>
      </div>
    </div>

    <!-- Interactive Week Scrubber Bar -->
    <div class="px-3 py-2 bg-slate-900/60 border-t border-slate-800/70 flex items-center justify-between gap-2 flex-wrap">
      <span class="text-[9px] font-mono uppercase tracking-wider text-slate-500 shrink-0">
        Scrub Week:
      </span>
      <div class="flex items-center gap-1 flex-wrap justify-end">
        <button
          v-for="(w, wIdx) in weeks"
          :key="`scrub-w-${w}`"
          type="button"
          class="px-2 py-0.5 rounded text-[10px] font-mono font-bold transition-all"
          :class="
            wIdx === activeWeekIdx
              ? 'bg-amber-400 text-slate-950 shadow-sm'
              : wIdx < activeWeekIdx
              ? 'bg-slate-800/90 text-slate-300 hover:bg-slate-700'
              : 'bg-slate-900 text-slate-500 hover:text-slate-300 border border-slate-800'
          "
          @click="selectWeekIdx(wIdx)"
        >
          {{ formatScrubWeek(w) }}
        </button>
      </div>
    </div>

    <!-- Interactive Team Avatar Grid (Wraps cleanly across screen: 4 cols on mobile, 6 on desktop) -->
    <div class="p-2.5 bg-slate-950/80 border-t border-slate-800/70">
      <div class="grid grid-cols-4 sm:grid-cols-6 gap-1.5">
        <button
          v-for="s in seriesList"
          :key="`chip-${s.team.team_id}`"
          type="button"
          class="flex items-center gap-1.5 px-1.5 py-1 rounded-lg text-[10px] font-mono transition-all border min-w-0"
          :class="
            isTeamSpotlighted(s.team.team_id)
              ? 'bg-slate-800 text-white border-slate-500 font-bold shadow-sm'
              : s.team.is_defending_champion
              ? 'bg-amber-950/30 text-amber-200 border-amber-500/40 hover:border-amber-400'
              : hasSpotlight
              ? 'bg-slate-900/40 text-slate-500 border-slate-800/60 opacity-55 hover:opacity-100'
              : 'bg-slate-900/80 text-slate-300 border-slate-800/80 hover:border-slate-700'
          "
          :title="s.team.is_defending_champion ? `${s.team.team_name} (Defending ${props.trophyName} Champion)` : s.team.team_name"
          @click="toggleTeamSpotlight(s.team.team_id)"
        >
          <span
            class="w-4 h-4 rounded-full p-[1px] shrink-0"
            :style="{ backgroundColor: s.color }"
          >
            <TeamAvatar
              :src="s.team.logo_url"
              :name="s.team.team_name"
              size="xs"
              rounded="full"
              class="!w-full !h-full !border-0 text-[7px]"
            />
          </span>
          <span class="text-slate-500 shrink-0">#{{ s.activeNode?.rank ?? s.team.rank }}</span>
          <span class="truncate flex items-center gap-0.5">
            <span v-if="s.team.is_defending_champion" class="text-[9px] text-amber-400 shrink-0">🏆</span>
            <span class="truncate">{{ s.abbrev }}</span>
            <span
              v-if="s.team.championships > 0"
              class="text-amber-400 text-[8px] leading-none shrink-0"
            >
              {{ '★'.repeat(Math.min(s.team.championships, 3)) }}
            </span>
          </span>
        </button>
      </div>
    </div>
  </div>
</template>
