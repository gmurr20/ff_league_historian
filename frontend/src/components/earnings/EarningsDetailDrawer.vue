<script setup lang="ts">
import { computed } from 'vue';
import type { EarningsLeaderboardEntry, ManagerSeasonBreakdown } from '@/types/api';
import SwipeDrawer from '@/components/ui/SwipeDrawer.vue';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';

const props = defineProps<{
  modelValue: boolean;
  entry: EarningsLeaderboardEntry | null;
  isSingleSeason?: boolean;
  seasonYear?: number | null;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void;
}>();

const title = computed(() => props.entry?.team_name ?? 'Team Earnings');
const subtitle = computed(() => {
  if (!props.entry) return '';
  if (props.isSingleSeason) {
    return `${props.entry.display_name} · Season ${props.seasonYear ?? ''}`;
  }
  const inactiveStr = !props.entry.is_active ? ' (Former)' : '';
  return `${props.entry.display_name}${inactiveStr} · ${props.entry.seasons_played} ${props.entry.seasons_played === 1 ? 'season' : 'seasons'}`;
});

// Sorted seasons (most recent first)
const sortedBreakdown = computed<ManagerSeasonBreakdown[]>(() => {
  if (!props.entry?.season_breakdown) return [];
  return [...props.entry.season_breakdown].sort((a, b) => b.season_year - a.season_year);
});

// Selected season breakdown item (if single-season mode)
const currentSeasonItem = computed<ManagerSeasonBreakdown | null>(() => {
  if (!props.entry?.season_breakdown) return null;
  if (props.seasonYear) {
    return (
      props.entry.season_breakdown.find(
        (s) => s.season_year === props.seasonYear
      ) ?? props.entry.season_breakdown[0]
    );
  }
  return props.entry.season_breakdown[0] ?? null;
});

// Points title cash for active view
const currentPointsTitleCash = computed(() => {
  if (props.isSingleSeason && currentSeasonItem.value) {
    return currentSeasonItem.value.points_title_cash ?? 0;
  }
  return props.entry?.points_title_cash ?? 0;
});

// Bounties for the active view (most recent week first)
const displayedBounties = computed(() => {
  const list = (
    props.isSingleSeason && currentSeasonItem.value
      ? currentSeasonItem.value.bounty_receipts ?? []
      : props.entry?.bounty_receipts ?? []
  );
  return [...list].sort((a, b) => b.week - a.week);
});
</script>

<template>
  <SwipeDrawer
    :model-value="modelValue"
    :title="title"
    :subtitle="subtitle"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-if="entry" class="space-y-3.5 pb-4">
      <!-- Team & Manager Identity Card -->
      <div class="rounded-xl border border-slate-800 bg-[#0b101b] p-3.5 flex items-center justify-between gap-3 shadow-md">
        <div class="flex items-center gap-3 min-w-0">
          <TeamAvatar :src="entry.avatar_url" :name="entry.team_name" size="md" rounded="lg" />
          <div class="min-w-0">
            <div class="flex items-center gap-1.5 flex-wrap">
              <h3 class="text-sm sm:text-base font-bold text-slate-100 truncate">{{ entry.team_name }}</h3>
              <!-- Former / Inactive Franchise Badge -->
              <span
                v-if="!isSingleSeason && !entry.is_active"
                class="inline-flex items-center text-[9px] font-mono font-bold uppercase px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700/80 shrink-0 select-none"
                title="Former Franchise Manager — No longer active in current season"
              >
                FORMER
              </span>
              <!-- Championship Stars -->
              <div
                v-if="entry.championships > 0"
                class="inline-flex items-center gap-0.5 shrink-0"
                :title="`${entry.championships}x Champion${entry.championship_years && entry.championship_years.length ? ` (${entry.championship_years.join(', ')})` : ''}`"
              >
                <span
                  v-for="yr in (entry.championship_years && entry.championship_years.length ? entry.championship_years : entry.championships)"
                  :key="yr"
                  class="text-amber-400 text-sm leading-none drop-shadow-[0_0_6px_rgba(251,191,36,0.7)] select-none"
                >
                  ★
                </span>
              </div>
              <!-- Defending Champion -->
              <span
                v-if="entry.is_defending_champion"
                class="inline-flex items-center gap-1 text-[9px] font-mono font-black uppercase px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/35 shrink-0 shadow-sm"
                title="Defending Champion"
              >
                <span class="text-[10px]">🏆</span>
                <span>DEFENDING CHAMP</span>
              </span>
            </div>
            <p class="text-xs text-slate-400 truncate mt-0.5">{{ entry.display_name }}</p>
          </div>
        </div>

        <div class="text-right shrink-0">
          <span class="text-xs sm:text-sm font-mono font-black text-emerald-400 bg-emerald-950/80 border border-emerald-800/80 px-2.5 py-1 rounded-lg tabular-nums shadow-sm">
            ${{ entry.total_earnings.toFixed(2) }}
          </span>
        </div>
      </div>

      <!-- Financial Category Breakdown Strip -->
      <div class="grid grid-cols-3 gap-2">
        <div class="rounded-lg bg-slate-900/80 border border-slate-800/80 p-2.5 text-center">
          <span class="text-[10px] text-slate-400 uppercase font-mono font-bold block">Wins Cash</span>
          <div class="text-xs sm:text-sm font-bold font-mono text-slate-200 tabular-nums mt-0.5">
            ${{ entry.weekly_wins_cash.toFixed(2) }}
          </div>
          <span class="text-[10px] text-slate-500 font-mono">
            {{ entry.weekly_wins_count }}W<span v-if="entry.weekly_ties_count > 0">, {{ entry.weekly_ties_count }}T</span>
          </span>
        </div>

        <div class="rounded-lg bg-slate-900/80 border border-slate-800/80 p-2.5 text-center">
          <span class="text-[10px] text-slate-400 uppercase font-mono font-bold block">Bonus Cash</span>
          <div class="text-xs sm:text-sm font-bold font-mono text-emerald-400 tabular-nums mt-0.5">
            ${{ entry.weekly_bonus_cash.toFixed(2) }}
          </div>
          <span class="text-[10px] text-slate-500 font-mono">
            {{ entry.weekly_high_scores_count + entry.weekly_high_score_losses_count }} Bounties
          </span>
        </div>

        <div class="rounded-lg bg-slate-900/80 border border-slate-800/80 p-2.5 text-center">
          <span class="text-[10px] text-slate-400 uppercase font-mono font-bold block">Podium Cash</span>
          <div class="text-xs sm:text-sm font-bold font-mono text-amber-400 tabular-nums mt-0.5">
            ${{ entry.podium_earnings.toFixed(2) }}
          </div>
          <span class="text-[10px] text-slate-500 font-mono">
            {{ entry.championships > 0 ? `${entry.championships} Titles` : 'Placements' }}
          </span>
        </div>
      </div>

      <!-- The Lamar Jackson Award Banner (Regular Season Scoring King) -->
      <div
        v-if="currentPointsTitleCash > 0"
        class="rounded-xl bg-gradient-to-r from-purple-950/40 via-purple-900/20 to-slate-900/80 border border-purple-500/30 p-2.5 sm:p-3 flex items-center justify-between gap-2"
      >
        <div class="flex items-center gap-2.5 min-w-0">
          <div class="w-7 h-7 sm:w-8 sm:h-8 rounded-full overflow-hidden shrink-0 border border-purple-500/40 bg-purple-950/80 shadow-md flex items-center justify-center">
            <img
              src="https://a.espncdn.com/i/headshots/nfl/players/full/3916387.png"
              alt="Lamar Jackson - King of the Regular Season"
              class="w-full h-full object-cover object-top scale-110"
              loading="lazy"
            />
          </div>
          <div class="min-w-0">
            <div class="text-xs font-black uppercase text-purple-200 font-mono tracking-tight">
              The Lamar Jackson Award
            </div>
            <div class="text-[10px] text-slate-400 truncate font-mono">
              King of the Regular Season · Highest PF
            </div>
          </div>
        </div>

        <div class="text-right font-mono shrink-0">
          <div class="text-xs sm:text-sm font-bold text-emerald-400 tabular-nums">
            +${{ currentPointsTitleCash.toFixed(2) }}
          </div>
          <span class="text-[9px] uppercase font-bold text-purple-400/80 tracking-wider">
            Scoring Title
          </span>
        </div>
      </div>

      <!-- ITEMIZE EACH WEEK THEY GOT A WEEKLY BOUNTY -->
      <div class="rounded-xl border border-slate-800 bg-[#0b101b] overflow-hidden shadow-md">
        <div class="flex items-center justify-between px-3.5 py-2.5 bg-slate-900/90 border-b border-slate-800/80">
          <h4 class="text-xs font-mono font-black uppercase tracking-wider text-slate-200">
            Weekly Bounties Won ({{ displayedBounties.length }})
          </h4>
          <span class="text-[11px] font-mono text-emerald-400 font-bold tabular-nums">
            ${{ entry.weekly_bonus_cash.toFixed(0) }} Total
          </span>
        </div>

        <!-- List of specific weeks they won a bounty -->
        <div v-if="displayedBounties.length > 0" class="divide-y divide-slate-800/60 p-2 sm:p-2.5 space-y-1.5">
          <div
            v-for="b in displayedBounties"
            :key="`${b.week}-${b.entry_type}`"
            class="rounded-lg bg-slate-900/60 border border-slate-800/80 p-2 sm:p-2.5 flex items-center justify-between gap-2"
          >
            <div class="flex items-center gap-2 min-w-0">
              <span class="text-[10px] font-mono font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 shrink-0">
                Wk {{ b.week }}
              </span>

              <span
                class="text-[9px] font-mono font-black uppercase tracking-wider px-1.5 py-0.2 rounded shrink-0"
                :class="
                  b.entry_type === 'WEEKLY_HIGH_SCORE'
                    ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                    : 'bg-rose-500/15 text-rose-300 border border-rose-500/30'
                "
              >
                {{ b.entry_type === 'WEEKLY_HIGH_SCORE' ? 'High Score' : 'High Loser' }}
              </span>

              <span class="text-xs font-mono text-slate-300 truncate">
                {{ b.points.toFixed(2) }} pts
              </span>
            </div>

            <div class="font-mono text-xs font-bold text-emerald-400 tabular-nums shrink-0">
              +${{ b.amount.toFixed(0) }}
            </div>
          </div>
        </div>

        <div v-else class="p-5 text-center text-xs font-mono text-slate-500">
          No weekly high score or high loser bounties won this season.
        </div>
      </div>

      <!-- ALL-TIME SEASON BREAKDOWN (When viewing career all-time) -->
      <div v-if="!isSingleSeason && sortedBreakdown.length > 0" class="space-y-2 pt-1">
        <h4 class="text-xs uppercase font-mono font-black tracking-wider text-slate-300 px-1">
          Season-by-Season History
        </h4>

        <div class="space-y-2">
          <div
            v-for="item in sortedBreakdown"
            :key="item.season_year"
            class="rounded-xl bg-[#0b101b] p-3 border border-slate-800/80 space-y-2"
          >
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-2 min-w-0">
                <span class="text-xs font-black font-mono text-slate-200 bg-slate-800 px-1.5 py-0.5 rounded shrink-0">
                  {{ item.season_year }}
                </span>
                <span class="text-xs font-bold text-slate-100 truncate">
                  {{ item.team_name }}
                </span>
              </div>

              <div class="text-right font-mono text-xs font-bold text-emerald-400 tabular-nums">
                ${{ item.total_earnings.toFixed(2) }}
              </div>
            </div>

            <div class="grid grid-cols-4 gap-1.5 text-[11px] font-mono border-t border-slate-800/60 pt-1.5 text-slate-400">
              <div>
                <span class="text-[9px] uppercase text-slate-500 block">Wins</span>
                <span class="text-slate-200 font-bold">${{ item.weekly_wins_cash.toFixed(0) }}</span>
                <span class="text-[10px] text-slate-500 ml-0.5">({{ item.weekly_wins }}W)</span>
              </div>

              <div>
                <span class="text-[9px] uppercase text-slate-500 block">Bounties</span>
                <span class="text-emerald-400 font-bold">${{ item.weekly_bonus_cash.toFixed(0) }}</span>
                <span class="text-[10px] text-slate-500 ml-0.5">({{ item.bounty_receipts?.length || 0 }})</span>
              </div>

              <div>
                <span class="text-[9px] uppercase text-slate-500 block">PF Title</span>
                <span
                  class="font-bold"
                  :class="item.points_title_cash > 0 ? 'text-amber-400' : 'text-slate-600'"
                >
                  ${{ item.points_title_cash.toFixed(0) }}
                </span>
              </div>

              <div>
                <span class="text-[9px] uppercase text-slate-500 block">Podium</span>
                <span
                  class="font-bold"
                  :class="item.podium_earnings > 0 ? 'text-amber-400' : 'text-slate-600'"
                >
                  ${{ item.podium_earnings.toFixed(0) }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </SwipeDrawer>
</template>
