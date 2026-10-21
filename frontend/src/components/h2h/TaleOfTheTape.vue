<script setup lang="ts">
import { ref, computed } from 'vue';
import type { H2HPairDetail } from '@/types/api';
import MatchupHistoryItem from './MatchupHistoryItem.vue';
import EmptyState from '@/components/ui/EmptyState.vue';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import {
  Swords,
  Flame,
  Zap,
  Activity,
  Trophy,
  Calendar,
  ArrowUpDown,
  Award,
} from 'lucide-vue-next';

const props = defineProps<{
  pairDetail: H2HPairDetail;
  loading?: boolean;
}>();

const sortDescending = ref(true);

const totalGames = computed(() => {
  const { a_wins, b_wins, ties } = props.pairDetail.combined;
  return a_wins + b_wins + ties;
});

const aWinPct = computed(() => {
  if (totalGames.value === 0) return 50;
  return Math.round((props.pairDetail.combined.a_wins / totalGames.value) * 100);
});

const bWinPct = computed(() => {
  if (totalGames.value === 0) return 50;
  return Math.round((props.pairDetail.combined.b_wins / totalGames.value) * 100);
});

const tiesPct = computed(() => {
  if (totalGames.value === 0) return 0;
  return 100 - aWinPct.value - bWinPct.value;
});

const isManagerALeadingSeries = computed(() => {
  return props.pairDetail.combined.a_wins > props.pairDetail.combined.b_wins;
});

const isManagerBLeadingSeries = computed(() => {
  return props.pairDetail.combined.b_wins > props.pairDetail.combined.a_wins;
});

const sortedMatchups = computed(() => {
  if (!props.pairDetail.matchups) return [];
  const list = [...props.pairDetail.matchups];
  return list.sort((x, y) => {
    if (x.season_year !== y.season_year) {
      return sortDescending.value ? y.season_year - x.season_year : x.season_year - y.season_year;
    }
    return sortDescending.value ? y.week - x.week : x.week - y.week;
  });
});
</script>

<template>
  <div class="space-y-4">
    <!-- 1. Head-to-Head Banner (Tale of the Tape Hero) -->
    <div
      class="stadium-card rounded-2xl p-4 sm:p-5 border border-slate-800 shadow-xl overflow-hidden relative"
    >
      <!-- Background Ambient Glow -->
      <div
        class="absolute -top-24 -left-24 w-60 h-60 rounded-full bg-emerald-500/10 blur-3xl pointer-events-none"
      ></div>
      <div
        class="absolute -bottom-24 -right-24 w-60 h-60 rounded-full bg-rose-500/10 blur-3xl pointer-events-none"
      ></div>

      <!-- Top Label & Active Streak -->
      <div class="flex items-center justify-between gap-2 mb-4 pb-3 border-b border-slate-800/80">
        <div class="flex items-center gap-2">
          <div class="w-7 h-7 rounded-lg bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400">
            <Swords class="w-4 h-4" />
          </div>
          <span class="text-xs font-bold uppercase tracking-wider text-slate-300">
            Tale of the Tape
          </span>
        </div>

        <!-- Current Streak Badge -->
        <div>
          <span
            v-if="pairDetail.current_streak.type === 'WIN' && pairDetail.current_streak.length > 0"
            class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-amber-500/15 text-amber-300 border border-amber-500/30"
          >
            <Flame class="w-3.5 h-3.5 text-amber-400 fill-amber-400/20" />
            <span>{{ pairDetail.current_streak.display_name }} W{{ pairDetail.current_streak.length }}</span>
          </span>
          <span
            v-else-if="pairDetail.current_streak.type === 'TIE'"
            class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-800 text-slate-300 border border-slate-700"
          >
            Tied Last Meeting
          </span>
          <span
            v-else
            class="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-slate-800/80 text-slate-400 border border-slate-800"
          >
            Series Deadlocked
          </span>
        </div>
      </div>

      <!-- Managers Confrontation Row -->
      <div class="grid grid-cols-2 gap-4 items-center">
        <!-- Manager A -->
        <div
          class="p-3 rounded-xl border transition-all text-center sm:text-left"
          :class="[
            isManagerALeadingSeries
              ? 'bg-emerald-950/20 border-emerald-500/30 text-emerald-300'
              : 'bg-slate-900/60 border-slate-800/80 text-slate-300',
          ]"
        >
          <div class="flex items-center justify-center sm:justify-start gap-2 mb-1.5">
            <TeamAvatar
              :src="pairDetail.manager_a.avatar_url"
              :name="pairDetail.manager_a.team_name"
              size="md"
              rounded="xl"
            />
            <div class="min-w-0 text-left">
              <div class="flex items-center gap-1">
                <Award
                  v-if="isManagerALeadingSeries"
                  class="w-3.5 h-3.5 text-emerald-400 shrink-0"
                />
                <span class="text-[10px] font-extrabold tracking-wider uppercase truncate" :class="isManagerALeadingSeries ? 'text-emerald-400' : 'text-slate-400'">
                  Franchise A
                </span>
              </div>
              <h3 class="text-sm sm:text-base font-black text-slate-100 truncate leading-tight" :title="pairDetail.manager_a.team_name">
                {{ pairDetail.manager_a.team_name }}
              </h3>
              <p class="text-xs text-slate-400 truncate leading-tight" :title="pairDetail.manager_a.display_name">
                {{ pairDetail.manager_a.display_name }}
              </p>
            </div>
          </div>
          <div class="mt-2 flex items-baseline justify-center sm:justify-start gap-1.5">
            <span class="font-mono text-2xl sm:text-3xl font-black text-slate-100">
              {{ pairDetail.combined.a_wins }}
            </span>
            <span class="text-xs text-slate-400 uppercase font-semibold">Wins</span>
          </div>
          <div class="mt-1 text-xs font-mono text-slate-400 truncate">
            {{ pairDetail.combined.a_points.toFixed(1) }} pts
          </div>
        </div>

        <!-- Manager B -->
        <div
          class="p-3 rounded-xl border transition-all text-center sm:text-right"
          :class="[
            isManagerBLeadingSeries
              ? 'bg-emerald-950/20 border-emerald-500/30 text-emerald-300'
              : 'bg-slate-900/60 border-slate-800/80 text-slate-300',
          ]"
        >
          <div class="flex items-center justify-center sm:justify-end gap-2 mb-1.5">
            <div class="min-w-0 text-right">
              <div class="flex items-center justify-end gap-1">
                <span class="text-[10px] font-extrabold tracking-wider uppercase truncate" :class="isManagerBLeadingSeries ? 'text-emerald-400' : 'text-slate-400'">
                  Franchise B
                </span>
                <Award
                  v-if="isManagerBLeadingSeries"
                  class="w-3.5 h-3.5 text-emerald-400 shrink-0"
                />
              </div>
              <h3 class="text-sm sm:text-base font-black text-slate-100 truncate leading-tight" :title="pairDetail.manager_b.team_name">
                {{ pairDetail.manager_b.team_name }}
              </h3>
              <p class="text-xs text-slate-400 truncate leading-tight" :title="pairDetail.manager_b.display_name">
                {{ pairDetail.manager_b.display_name }}
              </p>
            </div>
            <TeamAvatar
              :src="pairDetail.manager_b.avatar_url"
              :name="pairDetail.manager_b.team_name"
              size="md"
              rounded="xl"
            />
          </div>
          <div class="mt-2 flex items-baseline justify-center sm:justify-end gap-1.5">
            <span class="text-xs text-slate-400 uppercase font-semibold">Wins</span>
            <span class="font-mono text-2xl sm:text-3xl font-black text-slate-100">
              {{ pairDetail.combined.b_wins }}
            </span>
          </div>
          <div class="mt-1 text-xs font-mono text-slate-400 truncate">
            {{ pairDetail.combined.b_points.toFixed(1) }} pts
          </div>
        </div>
      </div>

      <!-- Combined Series Stats Bar -->
      <div class="mt-4 pt-3 border-t border-slate-800/80 space-y-2">
        <!-- Visual Win Share Bar -->
        <div class="w-full h-2 rounded-full bg-slate-800 overflow-hidden flex">
          <div
            class="h-full bg-emerald-500 transition-all duration-500"
            :style="{ width: `${aWinPct}%` }"
            :title="`${pairDetail.manager_a.display_name}: ${aWinPct}%`"
          ></div>
          <div
            v-if="tiesPct > 0"
            class="h-full bg-amber-500/70 transition-all duration-500"
            :style="{ width: `${tiesPct}%` }"
            title="Ties"
          ></div>
          <div
            class="h-full bg-rose-500 transition-all duration-500"
            :style="{ width: `${bWinPct}%` }"
            :title="`${pairDetail.manager_b.display_name}: ${bWinPct}%`"
          ></div>
        </div>

        <!-- Series Summary Line -->
        <div class="flex items-center justify-between text-xs font-medium text-slate-400">
          <span>
            Series Record:
            <strong class="text-slate-100 font-mono">
              {{ pairDetail.combined.a_wins }}-{{ pairDetail.combined.b_wins }}<template v-if="pairDetail.combined.ties > 0">-{{ pairDetail.combined.ties }}</template>
            </strong>
            <span class="text-slate-500 ml-1">({{ totalGames }} games)</span>
          </span>

          <!-- Point Differential -->
          <div>
            <span v-if="pairDetail.combined.point_differential > 0" class="text-emerald-400 font-mono font-semibold">
              +{{ pairDetail.combined.point_differential.toFixed(1) }} pts diff ({{ pairDetail.manager_a.display_name }})
            </span>
            <span v-else-if="pairDetail.combined.point_differential < 0" class="text-emerald-400 font-mono font-semibold">
              +{{ Math.abs(pairDetail.combined.point_differential).toFixed(1) }} pts diff ({{ pairDetail.manager_b.display_name }})
            </span>
            <span v-else class="text-slate-400 font-mono">
              Even (0.0 differential)
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- 2. Split Cards (Regular Season vs Championship Playoffs) -->
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <!-- Regular Season Split -->
      <div class="stadium-card rounded-xl p-4 border border-slate-800 space-y-2">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <Calendar class="w-4 h-4 text-slate-400" />
            <span class="text-xs font-bold uppercase tracking-wider text-slate-300">
              Regular Season
            </span>
          </div>
          <span class="font-mono text-sm font-black text-slate-100">
            {{ pairDetail.regular_season.a_wins }}-{{ pairDetail.regular_season.b_wins }}<template v-if="pairDetail.regular_season.ties > 0">-{{ pairDetail.regular_season.ties }}</template>
          </span>
        </div>

        <div class="flex items-center justify-between text-xs text-slate-400 font-mono pt-1">
          <span>{{ pairDetail.regular_season.a_points.toFixed(1) }} pts</span>
          <span class="text-slate-600">vs</span>
          <span>{{ pairDetail.regular_season.b_points.toFixed(1) }} pts</span>
        </div>

        <div class="text-[11px] text-slate-500 text-center pt-0.5">
          {{ pairDetail.regular_season.a_wins + pairDetail.regular_season.b_wins + pairDetail.regular_season.ties }} regular season matchups
        </div>
      </div>

      <!-- Championship Playoffs Split -->
      <div class="stadium-card rounded-xl p-4 border border-slate-800 space-y-2">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <Trophy class="w-4 h-4 text-amber-400" />
            <span class="text-xs font-bold uppercase tracking-wider text-amber-300">
              Championship Playoffs
            </span>
          </div>
          <span class="font-mono text-sm font-black text-amber-300">
            {{ pairDetail.playoffs.a_wins }}-{{ pairDetail.playoffs.b_wins }}<template v-if="pairDetail.playoffs.ties > 0">-{{ pairDetail.playoffs.ties }}</template>
          </span>
        </div>

        <div
          v-if="pairDetail.playoffs.a_wins + pairDetail.playoffs.b_wins + pairDetail.playoffs.ties > 0"
          class="flex items-center justify-between text-xs text-slate-400 font-mono pt-1"
        >
          <span>{{ pairDetail.playoffs.a_points.toFixed(1) }} pts</span>
          <span class="text-slate-600">vs</span>
          <span>{{ pairDetail.playoffs.b_points.toFixed(1) }} pts</span>
        </div>
        <div
          v-else
          class="text-xs text-slate-500 italic text-center pt-1"
        >
          No championship playoff meetings yet
        </div>

        <div class="text-[11px] text-slate-500 text-center pt-0.5">
          {{ pairDetail.playoffs.a_wins + pairDetail.playoffs.b_wins + pairDetail.playoffs.ties }} postseason battles
        </div>
      </div>
    </div>

    <!-- 3. Superlatives (Biggest Blowout & Closest Nailbiter) -->
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <!-- Biggest Blowout -->
      <div class="stadium-card rounded-xl p-4 border border-slate-800 space-y-2">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <div class="w-6 h-6 rounded-md bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400">
              <Zap class="w-3.5 h-3.5" />
            </div>
            <span class="text-xs font-bold uppercase tracking-wider text-slate-300">
              Biggest Blowout
            </span>
          </div>
          <span
            v-if="pairDetail.biggest_blowout"
            class="text-xs font-mono font-bold text-rose-400 px-2 py-0.5 rounded bg-rose-500/10 border border-rose-500/20"
          >
            +{{ pairDetail.biggest_blowout.margin.toFixed(1) }} pts
          </span>
        </div>

        <div v-if="pairDetail.biggest_blowout" class="space-y-1 pt-1">
          <div class="flex items-baseline justify-between text-sm">
            <span class="font-bold text-slate-100 truncate">
              {{ pairDetail.biggest_blowout.winner_name || 'Winner' }}
            </span>
            <span class="font-mono text-xs text-slate-300">
              {{ pairDetail.biggest_blowout.winner_score.toFixed(1) }} - {{ pairDetail.biggest_blowout.loser_score.toFixed(1) }}
            </span>
          </div>
          <div class="text-[11px] text-slate-500 flex items-center justify-between">
            <span>{{ pairDetail.biggest_blowout.season_year }} · Week {{ pairDetail.biggest_blowout.week }}</span>
            <span class="uppercase tracking-wider text-[10px]">
              {{ pairDetail.biggest_blowout.matchup_type === 'WINNERS_BRACKET' ? 'Playoffs' : 'Regular' }}
            </span>
          </div>
        </div>
        <div v-else class="text-xs text-slate-500 italic py-2 text-center">
          No blowout recorded
        </div>
      </div>

      <!-- Closest Nailbiter -->
      <div class="stadium-card rounded-xl p-4 border border-slate-800 space-y-2">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <div class="w-6 h-6 rounded-md bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
              <Activity class="w-3.5 h-3.5" />
            </div>
            <span class="text-xs font-bold uppercase tracking-wider text-slate-300">
              Closest Nailbiter
            </span>
          </div>
          <span
            v-if="pairDetail.closest_game"
            class="text-xs font-mono font-bold text-amber-400 px-2 py-0.5 rounded bg-amber-500/10 border border-amber-500/20"
          >
            ±{{ pairDetail.closest_game.margin.toFixed(1) }} pts
          </span>
        </div>

        <div v-if="pairDetail.closest_game" class="space-y-1 pt-1">
          <div class="flex items-baseline justify-between text-sm">
            <span class="font-bold text-slate-100 truncate">
              {{ pairDetail.closest_game.winner_name || 'Winner' }}
            </span>
            <span class="font-mono text-xs text-slate-300">
              {{ pairDetail.closest_game.winner_score.toFixed(1) }} - {{ pairDetail.closest_game.loser_score.toFixed(1) }}
            </span>
          </div>
          <div class="text-[11px] text-slate-500 flex items-center justify-between">
            <span>{{ pairDetail.closest_game.season_year }} · Week {{ pairDetail.closest_game.week }}</span>
            <span class="uppercase tracking-wider text-[10px]">
              {{ pairDetail.closest_game.matchup_type === 'WINNERS_BRACKET' ? 'Playoffs' : 'Regular' }}
            </span>
          </div>
        </div>
        <div v-else class="text-xs text-slate-500 italic py-2 text-center">
          No games recorded
        </div>
      </div>
    </div>

    <!-- 4. Chronological Matchup History List -->
    <div class="space-y-3 pt-2">
      <div class="flex items-center justify-between px-1">
        <div>
          <h4 class="text-sm font-bold text-slate-200 uppercase tracking-wider">
            Matchup History
          </h4>
          <p class="text-[11px] text-slate-400">
            {{ sortedMatchups.length }} career head-to-head meetings
          </p>
        </div>

        <button
          type="button"
          class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium text-slate-400 bg-slate-900 border border-slate-800 hover:text-slate-200 transition-colors"
          @click="sortDescending = !sortDescending"
        >
          <ArrowUpDown class="w-3.5 h-3.5" />
          <span>{{ sortDescending ? 'Newest First' : 'Oldest First' }}</span>
        </button>
      </div>

      <div v-if="sortedMatchups.length > 0" class="space-y-2.5">
        <MatchupHistoryItem
          v-for="game in sortedMatchups"
          :key="game.matchup_id"
          :matchup="game"
          :manager-a-id="pairDetail.manager_a.manager_id"
          :manager-b-id="pairDetail.manager_b.manager_id"
          :manager-a-name="pairDetail.manager_a.display_name"
          :manager-b-name="pairDetail.manager_b.display_name"
        />
      </div>

      <EmptyState
        v-else
        title="No Matchups Recorded"
        description="These two managers have not played each other in official regular season or championship playoff matchups."
      />
    </div>
  </div>
</template>
