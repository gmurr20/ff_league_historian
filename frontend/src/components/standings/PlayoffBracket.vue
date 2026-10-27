<script setup lang="ts">
import { ref, computed } from 'vue';
import type { PlayoffBracket, PlayoffMatchupItem } from '@/types/api';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';

const props = withDefaults(
  defineProps<{
    bracket: PlayoffBracket;
    trophyName?: string;
  }>(),
  {
    trophyName: 'The Pauley',
  }
);

const emit = defineEmits<{
  (e: 'openTeam', teamId: number): void;
}>();

// Bracket View Lens: 'winners' (Championship) vs 'consolation' (Ladders / Toilet Bowl)
type BracketLens = 'winners' | 'consolation';
const activeLens = ref<BracketLens>('winners');

const activeRounds = computed(() => {
  return props.bracket.rounds.map((r) => {
    return {
      week: r.week,
      round_label: r.round_label,
      matchups: activeLens.value === 'winners' ? r.winners_bracket : r.consolation,
    };
  }).filter((r) => r.matchups.length > 0);
});

function isWinner(m: PlayoffMatchupItem, teamId: number): boolean {
  return m.winner_team_id === teamId;
}

function isEliminated(m: PlayoffMatchupItem, teamId: number): boolean {
  return m.is_completed && m.winner_team_id !== null && m.winner_team_id !== teamId;
}

// Static Tailwind class lookup ensuring full JIT compilation:
// Mobile: reversed vertical stack (Championship at top: order-1)
// Desktop (md+): chronological horizontal progression (Quarterfinals left: md:order-1)
const ORDER_CLASSES: Record<number, Record<number, string>> = {
  1: {
    0: 'order-1 md:order-1',
  },
  2: {
    0: 'order-2 md:order-1',
    1: 'order-1 md:order-2',
  },
  3: {
    0: 'order-3 md:order-1',
    1: 'order-2 md:order-2',
    2: 'order-1 md:order-3',
  },
  4: {
    0: 'order-4 md:order-1',
    1: 'order-3 md:order-2',
    2: 'order-2 md:order-3',
    3: 'order-1 md:order-4',
  },
};

function getRoundOrderClass(idx: number, total: number): string {
  return ORDER_CLASSES[total]?.[idx] ?? (idx === total - 1 ? 'order-1' : 'order-2');
}
</script>

<template>
  <div class="rounded-xl border border-slate-800/90 bg-[#0b101b] overflow-hidden shadow-lg space-y-3 p-3.5">
    <!-- Header with Trophy Callout & Lens Selector -->
    <div class="flex items-center justify-between gap-2 flex-wrap border-b border-slate-800/80 pb-3">
      <div class="flex items-center gap-2 min-w-0">
        <span class="text-base sm:text-lg">🏆</span>
        <div>
          <h3 class="text-xs sm:text-sm font-black uppercase tracking-tight text-amber-400 font-mono">
            Playoff Bracket
          </h3>
          <p class="text-[10px] text-slate-400 font-mono">
            {{ activeLens === 'winners' ? `${props.trophyName} Championship Tournament` : 'Consolation Placements & Toilet Bowl' }}
          </p>
        </div>
      </div>

      <!-- Segmented Lens Switcher -->
      <div class="inline-flex items-center rounded-lg bg-slate-900 border border-slate-800 p-0.5 text-xs font-semibold shrink-0">
        <button
          type="button"
          class="px-2.5 py-1 rounded-md transition-all text-xs font-mono"
          :class="
            activeLens === 'winners'
              ? 'bg-amber-500/20 text-amber-300 font-bold border border-amber-500/40 shadow-sm'
              : 'text-slate-400 hover:text-slate-200'
          "
          @click="activeLens = 'winners'"
        >
          🏆 Championship
        </button>
        <button
          type="button"
          class="px-2.5 py-1 rounded-md transition-all text-xs font-mono"
          :class="
            activeLens === 'consolation'
              ? 'bg-slate-800 text-slate-100 font-bold border border-slate-700 shadow-sm'
              : 'text-slate-400 hover:text-slate-200'
          "
          @click="activeLens = 'consolation'"
        >
          Consolation
        </button>
      </div>
    </div>

    <!-- Champion Banner (if season completed and champion crowned) -->
    <div
      v-if="bracket.champion && activeLens === 'winners'"
      class="rounded-xl p-3 bg-gradient-to-r from-amber-950/40 via-amber-900/20 to-slate-900/90 border border-amber-500/40 flex items-center justify-between gap-3 shadow-md select-none"
    >
      <div class="flex items-center gap-3 min-w-0">
        <div class="relative shrink-0">
          <TeamAvatar
            :src="bracket.champion.logo_url"
            :name="bracket.champion.team_name"
            size="md"
            rounded="xl"
          />
          <span class="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-amber-500 text-slate-950 flex items-center justify-center text-[11px] shadow border border-slate-900">
            🏆
          </span>
        </div>
        <div class="min-w-0">
          <div class="text-[9px] font-mono uppercase tracking-widest text-amber-400/90 font-black">
            {{ props.trophyName }} Champion · Season {{ bracket.season_year }}
          </div>
          <div class="text-sm sm:text-base font-black text-slate-100 truncate">
            {{ bracket.champion.team_name }}
          </div>
          <div class="text-[11px] text-slate-400 font-mono truncate">
            {{ bracket.champion.manager_name }}
            <span v-if="bracket.champion.playoff_seed" class="text-amber-400/80">
              · Seed #{{ bracket.champion.playoff_seed }}
            </span>
          </div>
        </div>
      </div>

      <div v-if="bracket.runner_up" class="text-right shrink-0 hidden sm:block font-mono">
        <div class="text-[9px] uppercase text-slate-500">Runner-Up</div>
        <div class="text-xs font-bold text-slate-300 truncate max-w-[140px]">
          {{ bracket.runner_up.team_name }}
        </div>
        <div v-if="bracket.third_place" class="text-[10px] text-amber-600/90 mt-0.5">
          3rd: {{ bracket.third_place.team_name }}
        </div>
      </div>
    </div>

    <!-- Tournament Bracket Rounds Grid (Generic columns: 1 col if 1 round, 2 cols if 2 rounds, 3 cols if 3+ rounds) -->
    <div
      class="grid gap-3"
      :class="
        activeRounds.length === 1
          ? 'grid-cols-1'
          : activeRounds.length === 2
          ? 'grid-cols-1 md:grid-cols-2'
          : 'grid-cols-1 md:grid-cols-3'
      "
    >
      <div
        v-for="(round, idx) in activeRounds"
        :key="`round-${round.week}`"
        class="space-y-2 rounded-xl bg-slate-950/70 border p-2.5 flex flex-col transition-all"
        :class="[
          getRoundOrderClass(idx, activeRounds.length),
          round.round_label.includes('Championship') && activeLens === 'winners'
            ? 'border-amber-500/40 bg-gradient-to-b from-amber-950/20 to-slate-950/80 shadow-[0_0_12px_rgba(251,191,36,0.06)]'
            : 'border-slate-800/80',
        ]"
      >
        <!-- Round Header -->
        <div class="flex items-center justify-between border-b border-slate-800/80 pb-1.5 font-mono">
          <span
            class="text-xs font-black uppercase tracking-wider flex items-center gap-1.5"
            :class="round.round_label.includes('Championship') && activeLens === 'winners' ? 'text-amber-400' : 'text-slate-200'"
          >
            <span v-if="round.round_label.includes('Championship') && activeLens === 'winners'">🏆</span>
            {{ round.round_label }}
          </span>
          <span class="text-[10px] text-slate-500 uppercase tracking-widest">
            Week {{ round.week }}
          </span>
        </div>

        <!-- Matchups in this Round -->
        <div class="space-y-2 flex-1 flex flex-col justify-around">
          <div
            v-for="m in round.matchups"
            :key="`match-${m.id}`"
            class="rounded-lg bg-slate-900/90 border border-slate-800/90 overflow-hidden shadow-sm transition-all hover:border-slate-700"
          >
            <!-- Matchup Sub-Label Badge -->
            <div class="px-2 py-0.5 bg-slate-950/80 border-b border-slate-800/60 flex items-center justify-between text-[9px] font-mono">
              <span
                class="font-bold uppercase tracking-wider"
                :class="
                  m.round_label.includes('Championship')
                    ? 'text-amber-400'
                    : m.round_label.includes('3rd Place')
                    ? 'text-amber-500/80'
                    : 'text-slate-400'
                "
              >
                {{ m.round_label }}
              </span>
              <span
                v-if="m.is_completed"
                class="text-emerald-400/90 font-bold uppercase"
              >
                Final
              </span>
              <span v-else class="text-slate-500 uppercase">
                Upcoming
              </span>
            </div>

            <!-- Home Team Slot -->
            <div
              class="px-2.5 py-1.5 flex items-center justify-between gap-2 border-b border-slate-800/60 cursor-pointer select-none transition-colors"
              :class="[
                isWinner(m, m.home_team.team_id)
                  ? 'bg-amber-500/10 font-bold'
                  : isEliminated(m, m.home_team.team_id)
                  ? 'opacity-60'
                  : '',
              ]"
              @click="emit('openTeam', m.home_team.team_id)"
            >
              <div class="flex items-center gap-1.5 min-w-0">
                <span
                  v-if="m.home_team.playoff_seed"
                  class="font-mono text-[9px] font-bold px-1 rounded bg-slate-800 text-slate-400 shrink-0"
                >
                  #{{ m.home_team.playoff_seed }}
                </span>
                <TeamAvatar
                  :src="m.home_team.logo_url"
                  :name="m.home_team.team_name"
                  size="xs"
                  rounded="lg"
                />
                <span
                  class="text-xs truncate leading-tight"
                  :class="isWinner(m, m.home_team.team_id) ? 'text-amber-300 font-bold' : 'text-slate-200'"
                >
                  {{ m.home_team.team_name }}
                </span>
              </div>
              <div class="flex items-center gap-1 shrink-0 font-mono">
                <span
                  v-if="m.is_completed && isWinner(m, m.home_team.team_id)"
                  class="text-[10px] text-amber-400"
                >
                  ✓
                </span>
                <span
                  class="text-xs tabular-nums"
                  :class="isWinner(m, m.home_team.team_id) ? 'text-amber-300 font-bold' : 'text-slate-400'"
                >
                  {{ m.home_score.toFixed(1) }}
                </span>
              </div>
            </div>

            <!-- Away Team Slot -->
            <div
              v-if="m.away_team"
              class="px-2.5 py-1.5 flex items-center justify-between gap-2 cursor-pointer select-none transition-colors"
              :class="[
                isWinner(m, m.away_team.team_id)
                  ? 'bg-amber-500/10 font-bold'
                  : isEliminated(m, m.away_team.team_id)
                  ? 'opacity-60'
                  : '',
              ]"
              @click="emit('openTeam', m.away_team.team_id)"
            >
              <div class="flex items-center gap-1.5 min-w-0">
                <span
                  v-if="m.away_team.playoff_seed"
                  class="font-mono text-[9px] font-bold px-1 rounded bg-slate-800 text-slate-400 shrink-0"
                >
                  #{{ m.away_team.playoff_seed }}
                </span>
                <TeamAvatar
                  :src="m.away_team.logo_url"
                  :name="m.away_team.team_name"
                  size="xs"
                  rounded="lg"
                />
                <span
                  class="text-xs truncate leading-tight"
                  :class="isWinner(m, m.away_team.team_id) ? 'text-amber-300 font-bold' : 'text-slate-200'"
                >
                  {{ m.away_team.team_name }}
                </span>
              </div>
              <div class="flex items-center gap-1 shrink-0 font-mono">
                <span
                  v-if="m.is_completed && isWinner(m, m.away_team.team_id)"
                  class="text-[10px] text-amber-400"
                >
                  ✓
                </span>
                <span
                  class="text-xs tabular-nums"
                  :class="isWinner(m, m.away_team.team_id) ? 'text-amber-300 font-bold' : 'text-slate-400'"
                >
                  {{ m.away_score.toFixed(1) }}
                </span>
              </div>
            </div>

            <!-- BYE Slot -->
            <div
              v-else
              class="px-2.5 py-1.5 flex items-center justify-between text-xs font-mono text-slate-500 bg-slate-950/40"
            >
              <span class="italic text-[10px]">BYE WEEK ADVANCEMENT</span>
              <span class="text-[10px] font-bold text-emerald-400/80">AUTOMATIC WIN</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
