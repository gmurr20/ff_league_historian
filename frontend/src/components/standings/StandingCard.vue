<script setup lang="ts">
import { computed } from 'vue';
import type { StandingEntry } from '@/types/api';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import { Trophy, Medal, ChevronRight, Flame, DollarSign, Wallet } from 'lucide-vue-next';

const props = withDefaults(
  defineProps<{
    standing: StandingEntry;
    isCompleted: boolean;
    displayRank: number;
    trophyName?: string;
  }>(),
  {
    trophyName: 'The Pauley',
  }
);

defineEmits<{
  (e: 'click'): void;
}>();

// Streak formatting
const streakBadge = computed(() => {
  const type = props.standing.streak_type;
  const len = props.standing.streak_length;
  if (!type || len <= 0) return null;

  const upper = type.toUpperCase();
  if (upper.startsWith('W')) {
    return {
      text: `W${len}`,
      label: `${len} Win Streak`,
      class: 'bg-emerald-950/80 text-emerald-400 border-emerald-800/80',
      isHot: len >= 3,
    };
  } else if (upper.startsWith('L')) {
    return {
      text: `L${len}`,
      label: `${len} Loss Streak`,
      class: 'bg-rose-950/80 text-rose-400 border-rose-800/80',
      isHot: false,
    };
  } else {
    return {
      text: `T${len}`,
      label: `${len} Ties`,
      class: 'bg-slate-800 text-slate-400 border-slate-700',
      isHot: false,
    };
  }
});

// Official Record string
const officialRecord = computed(() => {
  const { wins, losses, ties } = props.standing;
  return ties > 0 ? `${wins}-${losses}-${ties}` : `${wins}-${losses}`;
});

// All-Play string
const allPlayRecord = computed(() => {
  const { all_play_wins, all_play_losses, all_play_ties, all_play_win_pct } = props.standing;
  const pct = Math.abs(all_play_win_pct) <= 1 ? all_play_win_pct * 100 : all_play_win_pct;
  const base = all_play_ties > 0
    ? `${all_play_wins}-${all_play_losses}-${all_play_ties}`
    : `${all_play_wins}-${all_play_losses}`;
  return { record: base, pct: `${pct.toFixed(1)}%` };
});

// Median record
const medianRecord = computed(() => {
  const { median_wins, median_losses, median_ties } = props.standing;
  return median_ties > 0
    ? `${median_wins}-${median_losses}-${median_ties}`
    : `${median_wins}-${median_losses}`;
});

// Luck Index formatting
const luckInfo = computed(() => {
  const val = props.standing.luck_index;
  const pct = Math.abs(val) <= 1 ? val * 100 : val;
  if (pct > 0.05) {
    return {
      text: `+${pct.toFixed(1)}%`,
      label: 'Lucky',
      class: 'bg-emerald-950/60 text-emerald-400 border-emerald-800/60',
    };
  } else if (pct < -0.05) {
    return {
      text: `${pct.toFixed(1)}%`,
      label: 'Robbed',
      class: 'bg-rose-950/60 text-rose-400 border-rose-800/60',
    };
  } else {
    return {
      text: '0.0%',
      label: 'Neutral',
      class: 'bg-slate-800/60 text-slate-400 border-slate-700/60',
    };
  }
});

// Lineup efficiency percentage
const efficiencyFormatted = computed(() => {
  const eff = props.standing.lineup_efficiency;
  if (!eff || eff <= 0) return '—';
  const pct = eff <= 1 ? eff * 100 : eff;
  return `${Math.min(100, Math.max(0, pct)).toFixed(1)}%`;
});

// Podium & Seed styles
const podiumBadge = computed(() => {
  if (props.isCompleted && props.standing.final_standing) {
    if (props.standing.final_standing === 1) {
      return {
        label: 'Champion',
        icon: Trophy,
        class: 'bg-amber-500/20 text-amber-300 border-amber-500/40 ring-1 ring-amber-500/30',
      };
    }
    if (props.standing.final_standing === 2) {
      return {
        label: 'Runner-Up',
        icon: Medal,
        class: 'bg-slate-400/20 text-slate-200 border-slate-400/40',
      };
    }
    if (props.standing.final_standing === 3) {
      return {
        label: '3rd Place',
        icon: Medal,
        class: 'bg-amber-700/20 text-amber-500 border-amber-700/40',
      };
    }
    return {
      label: `#${props.standing.final_standing} Final`,
      icon: null,
      class: 'bg-slate-800/80 text-slate-400 border-slate-700/60',
    };
  }

  if (props.standing.playoff_seed) {
    const seed = props.standing.playoff_seed;
    const isPlayoffs = seed <= 4;
    return {
      label: `Seed #${seed}`,
      icon: null,
      class: isPlayoffs
        ? 'bg-emerald-950/70 text-emerald-300 border-emerald-800/60'
        : 'bg-slate-800/70 text-slate-400 border-slate-700/50',
    };
  }

  return null;
});

// Manager line
const managerSubtitle = computed(() => {
  if (props.standing.co_manager_name) {
    return `${props.standing.manager_name} & ${props.standing.co_manager_name}`;
  }
  return props.standing.manager_name;
});
</script>

<template>
  <div
    class="stadium-card rounded-2xl p-3.5 sm:p-4 border transition-all duration-150 cursor-pointer select-none active:scale-[0.99] hover:border-slate-700"
    :class="[
      displayRank === 1
        ? 'border-amber-500/40 stadium-glow-amber bg-gradient-to-b from-amber-950/20 via-slate-900/90 to-slate-950/90'
        : displayRank <= 3
        ? 'border-slate-700/80'
        : 'border-slate-800/80'
    ]"
    role="button"
    tabindex="0"
    @click="$emit('click')"
    @keydown.enter="$emit('click')"
  >
    <!-- Top Row: Rank, Seed/Podium, Team & Manager, Streak -->
    <div class="flex items-start justify-between gap-2.5">
      <div class="flex items-center gap-2.5 min-w-0">
        <!-- Rank Pill -->
        <div
          class="w-7 h-7 rounded-xl flex items-center justify-center font-black font-mono text-xs shrink-0 shadow-inner"
          :class="[
            displayRank === 1
              ? 'bg-amber-500 text-slate-950 shadow-amber-500/50'
              : displayRank === 2
              ? 'bg-slate-300 text-slate-950 shadow-slate-300/40'
              : displayRank === 3
              ? 'bg-amber-700 text-amber-100 shadow-amber-800/40'
              : 'bg-slate-800 text-slate-300 border border-slate-700/60'
          ]"
        >
          {{ displayRank }}
        </div>

        <!-- ESPN Team Avatar -->
        <TeamAvatar :src="standing.logo_url" :name="standing.team_name" size="md" rounded="xl" />

        <!-- Team Name & Manager Info -->
        <div class="min-w-0">
          <div class="flex items-center gap-1.5 flex-wrap">
            <h3 class="text-sm sm:text-base font-bold text-slate-100 truncate tracking-tight">
              {{ standing.team_name }}
            </h3>

            <!-- Championship Stars (Soccer / World Cup style: 1 star per title) -->
            <div
              v-if="standing.championships > 0"
              class="inline-flex items-center gap-0.5 shrink-0"
              :title="`${standing.championships}x Champion (${standing.championship_years.join(', ')})`"
            >
              <span
                v-for="yr in standing.championship_years"
                :key="yr"
                class="text-amber-400 text-xs sm:text-sm leading-none drop-shadow-[0_0_5px_rgba(251,191,36,0.6)] select-none"
              >
                ★
              </span>
            </div>

            <!-- Defending Champion (Previous Season Champion) -->
            <span
              v-if="standing.is_defending_champion"
              class="inline-flex items-center gap-1 text-[9px] font-mono font-black uppercase px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/35 shrink-0 shadow-sm"
              :title="`Defending Champion — Current Holder of ${props.trophyName}`"
            >
              <span class="text-[10px]">🏆</span>
              <span>DEFENDING CHAMP</span>
            </span>

            <!-- Podium or Seed badge -->
            <span
              v-if="podiumBadge"
              class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold border"
              :class="podiumBadge.class"
            >
              <component :is="podiumBadge.icon" v-if="podiumBadge.icon" class="w-3 h-3 shrink-0" />
              <span>{{ podiumBadge.label }}</span>
            </span>
          </div>

          <p class="text-xs text-slate-400 truncate mt-0.5">
            {{ managerSubtitle }}
          </p>
        </div>
      </div>

      <!-- Streak & Drawer Arrow -->
      <div class="flex items-center gap-2 shrink-0">
        <div
          v-if="streakBadge"
          class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-mono font-bold border"
          :class="streakBadge.class"
          :title="streakBadge.label"
        >
          <Flame v-if="streakBadge.isHot" class="w-3 h-3 text-amber-400 animate-pulse shrink-0" />
          <span>{{ streakBadge.text }}</span>
        </div>

        <ChevronRight class="w-4 h-4 text-slate-500 group-hover:text-slate-300 shrink-0" />
      </div>
    </div>

    <!-- Middle Row: Official Record, PF / PA, Financial Cash -->
    <div class="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between gap-2">
      <!-- Record & PF / PA -->
      <div class="flex items-baseline gap-2 min-w-0">
        <span class="text-base sm:text-lg font-black font-mono text-slate-100 tabular-nums tracking-tight">
          {{ officialRecord }}
        </span>

        <div class="text-[11px] font-mono text-slate-400 tabular-nums truncate">
          <span class="text-slate-200 font-semibold">{{ standing.points_for.toFixed(1) }}</span> PF
          <span class="text-slate-600">·</span>
          <span>{{ standing.points_against.toFixed(1) }}</span> PA
        </div>
      </div>

      <!-- Financial Pill & FAAB -->
      <div class="flex items-center gap-1.5 shrink-0">
        <span
          v-if="standing.total_earnings > 0"
          class="inline-flex items-center gap-0.5 px-2 py-0.5 rounded-md text-[11px] font-mono font-bold bg-emerald-950/80 text-emerald-400 border border-emerald-800/60"
        >
          <DollarSign class="w-3 h-3 -mr-0.5" />
          <span>{{ standing.total_earnings.toFixed(0) }}</span>
        </span>

        <span
          class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono text-slate-400 bg-slate-800/60 border border-slate-700/50"
          title="FAAB Remaining"
        >
          <Wallet class="w-2.5 h-2.5 text-slate-500" />
          <span>${{ standing.faab_remaining }}</span>
        </span>
      </div>
    </div>

    <!-- Bottom Row: All-Play, Median, Luck, Lineup Efficiency -->
    <div class="mt-2.5 pt-2 border-t border-slate-800/50 grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
      <!-- All-Play Record -->
      <div class="flex flex-col">
        <span class="text-[10px] uppercase font-bold text-slate-500 tracking-wider">All-Play</span>
        <div class="font-mono text-slate-300 tabular-nums">
          {{ allPlayRecord.record }} <span class="text-slate-500">({{ allPlayRecord.pct }})</span>
        </div>
      </div>

      <!-- Weekly Median -->
      <div class="flex flex-col">
        <span class="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Median</span>
        <div class="font-mono text-slate-300 tabular-nums">
          {{ medianRecord }}
        </div>
      </div>

      <!-- Luck Index Pill -->
      <div class="flex flex-col">
        <span class="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Luck Index</span>
        <div class="flex items-center gap-1">
          <span
            class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono font-bold border"
            :class="luckInfo.class"
          >
            {{ luckInfo.text }} {{ luckInfo.label }}
          </span>
        </div>
      </div>

      <!-- Lineup Efficiency -->
      <div class="flex flex-col">
        <span class="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Efficiency</span>
        <div class="font-mono text-slate-300 tabular-nums">
          <span class="text-slate-200 font-semibold">{{ efficiencyFormatted }}</span>
          <span v-if="standing.optimal_points_for > 0" class="text-[10px] text-slate-500 ml-1">({{ standing.bench_points.toFixed(0) }} bch)</span>
        </div>
      </div>
    </div>
  </div>
</template>
