<script setup lang="ts">
import type { FeaturedChampion } from '@/types/api';
import HeroPlayerCard from '@/components/hall_of_fame/HeroPlayerCard.vue';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import {
  Trophy,
  Crown,
  Swords,
  Sparkles,
} from 'lucide-vue-next';

defineProps<{
  champion: FeaturedChampion;
}>();
</script>

<template>
  <div class="relative rounded-3xl overflow-hidden border border-slate-800 bg-slate-950 shadow-2xl p-5 sm:p-7">
    <!-- Top Header Bar -->
    <div class="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-slate-800">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-2xl bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-amber-400 shadow-sm">
          <Trophy class="w-5 h-5 fill-amber-400/30" />
        </div>
        <div>
          <span class="text-[10px] font-black font-mono tracking-widest text-amber-400 uppercase">
            CHAMPIONSHIP SPOTLIGHT
          </span>
          <h2 class="text-lg sm:text-xl font-black text-white tracking-tight flex items-center gap-2">
            <span>{{ champion.season_year }} League Champion</span>
            <span class="text-xs font-mono font-bold text-slate-400 bg-slate-900 px-2.5 py-0.5 rounded-md border border-slate-800">
              Title #{{ champion.hall_of_fame_number }}
            </span>
          </h2>
        </div>
      </div>
    </div>

    <!-- Champion Franchise Identity Card -->
    <div class="mt-5 rounded-2xl bg-slate-900/80 border border-slate-800 p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <!-- Franchise Crest & Manager -->
      <div class="flex items-center gap-3.5">
        <div class="relative shrink-0">
          <div class="w-14 h-14 sm:w-16 sm:h-16 rounded-2xl bg-gradient-to-tr from-amber-500 to-amber-300 p-0.5 shadow-md">
            <div class="w-full h-full rounded-[14px] bg-slate-950 overflow-hidden flex items-center justify-center">
              <TeamAvatar
                :src="champion.avatar_url || champion.logo_url"
                :name="champion.team_name"
                size="md"
                rounded="lg"
                class="!w-full !h-full"
              />
            </div>
          </div>
          <span class="absolute -bottom-1 -right-1 bg-amber-500 text-slate-950 p-1 rounded-full shadow">
            <Crown class="w-3 h-3 fill-slate-950" />
          </span>
        </div>

        <div>
          <div class="flex items-center gap-2">
            <span class="text-xs font-mono font-bold text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/30">
              {{ champion.regular_season_finish }}
            </span>
            <span v-if="champion.co_manager_name" class="text-[11px] font-medium text-slate-400">
              Co-Mgr: {{ champion.co_manager_name }}
            </span>
          </div>
          <h3 class="text-lg sm:text-xl font-extrabold text-white tracking-tight mt-0.5">
            {{ champion.team_name }}
          </h3>
          <p class="text-xs font-medium text-slate-300">
            Manager: <span class="text-white font-semibold">{{ champion.manager_name }}</span>
          </p>
        </div>
      </div>

      <!-- Quick Stats Chips -->
      <div class="grid grid-cols-2 sm:flex sm:items-center gap-2.5 sm:gap-4 shrink-0 pt-2 sm:pt-0 border-t sm:border-t-0 border-slate-800/80">
        <div class="bg-slate-950/80 border border-slate-800 rounded-xl px-3.5 py-2 text-center sm:text-right">
          <div class="text-[10px] font-mono text-slate-400 uppercase tracking-wider">
            RECORD
          </div>
          <div class="text-sm font-black font-mono text-white mt-0.5">
            {{ champion.record }}
          </div>
        </div>

        <div class="bg-slate-950/80 border border-slate-800 rounded-xl px-3.5 py-2 text-center sm:text-right">
          <div class="text-[10px] font-mono text-slate-400 uppercase tracking-wider">
            TOTAL EARNINGS
          </div>
          <div class="text-sm font-black font-mono text-emerald-400 mt-0.5">
            ${{ champion.total_earnings.toFixed(2) }}
          </div>
        </div>
      </div>
    </div>

    <!-- Championship Finals Matchup Recap -->
    <div class="mt-4 rounded-2xl bg-slate-900/60 border border-slate-800/80 p-4">
      <div class="flex items-center justify-between text-xs font-mono text-slate-400 mb-2.5">
        <span class="flex items-center gap-1.5 font-bold text-amber-300">
          <Swords class="w-3.5 h-3.5 text-amber-400" />
          <span>CHAMPIONSHIP GAME FINAL • WEEK {{ champion.championship_matchup.week }}</span>
        </span>
        <span class="text-emerald-400 font-bold">
          +{{ champion.championship_matchup.margin_of_victory.toFixed(2) }} Margin
        </span>
      </div>

      <!-- VS Scoreboard -->
      <div class="grid grid-cols-2 gap-3 items-center">
        <!-- Winner Column -->
        <div class="bg-emerald-950/30 border border-emerald-500/40 rounded-xl p-3 flex items-center justify-between">
          <div class="min-w-0 pr-2">
            <span class="text-[9px] font-black font-mono uppercase text-emerald-400 tracking-wider">
              CHAMPION
            </span>
            <div class="text-xs sm:text-sm font-bold text-white truncate">
              {{ champion.team_name }}
            </div>
          </div>
          <div class="text-right shrink-0">
            <div class="text-base sm:text-xl font-black font-mono text-emerald-400">
              {{ champion.championship_matchup.winning_score.toFixed(2) }}
            </div>
          </div>
        </div>

        <!-- Runner-up Column -->
        <div class="bg-slate-950/60 border border-slate-800 rounded-xl p-3 flex items-center justify-between opacity-80">
          <div class="min-w-0 pr-2">
            <span class="text-[9px] font-black font-mono uppercase text-slate-400 tracking-wider">
              RUNNER-UP
            </span>
            <div class="text-xs sm:text-sm font-bold text-slate-300 truncate">
              {{ champion.championship_matchup.runner_up_team_name }}
            </div>
          </div>
          <div class="text-right shrink-0">
            <div class="text-base sm:text-xl font-black font-mono text-slate-400">
              {{ champion.championship_matchup.runner_up_score.toFixed(2) }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Top 4 Championship Game Performers -->
    <div class="mt-6">
      <div class="flex items-center justify-between mb-3.5">
        <div>
          <h3 class="text-sm sm:text-base font-extrabold text-white flex items-center gap-2">
            <Sparkles class="w-4 h-4 text-amber-400" />
            <span>Top 4 Championship Game Performers</span>
          </h3>
          <p class="text-[11px] text-slate-400 mt-0.5">
            The 4 marquee starters who led {{ champion.team_name }} to victory in Week {{ champion.championship_matchup.week }}
          </p>
        </div>
        <span class="text-[10px] font-mono font-bold text-amber-400 bg-amber-500/10 px-2.5 py-1 rounded-full border border-amber-500/30">
          TITLE SQUAD
        </span>
      </div>

      <!-- 2x2 Grid of Top 4 Performers -->
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
        <HeroPlayerCard
          v-for="player in champion.top_players"
          :key="player.player_id"
          :player="player"
        />
      </div>
    </div>
  </div>
</template>
