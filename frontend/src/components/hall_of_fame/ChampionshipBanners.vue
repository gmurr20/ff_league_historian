<script setup lang="ts">
import type { HallOfFameBanner } from '@/types/api';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import { Trophy, Crown, Check } from 'lucide-vue-next';

defineProps<{
  banners: HallOfFameBanner[];
  selectedSeason: number;
}>();

const emit = defineEmits<{
  (e: 'selectSeason', seasonYear: number): void;
}>();
</script>

<template>
  <div class="relative">
    <!-- Stadium Arena Rafters Steel Truss (Ceiling structure) -->
    <div class="relative bg-gradient-to-r from-slate-900 via-slate-850 to-slate-900 rounded-2xl border border-slate-700/80 p-3 mb-2 shadow-lg">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2.5">
          <div class="w-7 h-7 rounded-lg bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-amber-400">
            <Trophy class="w-3.5 h-3.5 fill-amber-400/30" />
          </div>
          <div>
            <h3 class="text-xs sm:text-sm font-black font-mono tracking-wider uppercase text-white">
              STADIUM RAFTERS
            </h3>
            <p class="text-[10px] text-slate-400 font-medium">
              Championship Banners Hanging in Arena Rafters
            </p>
          </div>
        </div>

        <span class="text-[11px] font-mono font-bold text-amber-400 bg-amber-500/10 px-2.5 py-1 rounded-md border border-amber-500/30">
          {{ banners.length }} BANNERS HOISTED
        </span>
      </div>

      <!-- Industrial Steel Truss Rivets across the rafter beam -->
      <div class="mt-2.5 pt-2 border-t border-slate-700/60 flex items-center justify-around opacity-40">
        <span v-for="i in 12" :key="i" class="w-1.5 h-1.5 rounded-full bg-slate-400 shadow-inner"></span>
      </div>
    </div>

    <!-- Suspension Cables & Banners Row -->
    <div
      class="flex items-start gap-4 overflow-x-auto pb-4 pt-1 px-2 -mx-2 snap-x snap-mandatory scroll-smooth no-scrollbar select-none"
    >
      <div
        v-for="banner in banners"
        :key="banner.season_year"
        @click="emit('selectSeason', banner.season_year)"
        class="group relative shrink-0 w-[175px] sm:w-[195px] snap-center cursor-pointer flex flex-col items-center transition-transform duration-200 hover:-translate-y-1"
      >
        <!-- Authentic Steel Suspension Cables connecting banner to ceiling rafters -->
        <div class="w-full flex justify-between px-6 mb-[-1px] z-10">
          <!-- Left Suspension Cable & Clip -->
          <div class="flex flex-col items-center">
            <span class="w-1.5 h-4 bg-gradient-to-b from-slate-400 to-slate-500 shadow-sm rounded-t-sm"></span>
            <span class="w-2.5 h-2.5 rounded-full bg-slate-300 border border-slate-600 shadow-inner"></span>
          </div>

          <!-- Right Suspension Cable & Clip -->
          <div class="flex flex-col items-center">
            <span class="w-1.5 h-4 bg-gradient-to-b from-slate-400 to-slate-500 shadow-sm rounded-t-sm"></span>
            <span class="w-2.5 h-2.5 rounded-full bg-slate-300 border border-slate-600 shadow-inner"></span>
          </div>
        </div>

        <!-- The Rafter Championship Banner (Authentic Fabric Pennant with Stitched Border) -->
        <div
          class="relative w-full rounded-b-2xl pt-4 pb-6 px-3 flex flex-col items-center text-center overflow-hidden transition-all duration-300 banner-shadow"
          :class="[
            selectedSeason === banner.season_year
              ? 'bg-gradient-to-b from-amber-950 via-slate-900 to-slate-950 border-2 border-amber-400 shadow-[0_12px_28px_rgba(245,158,11,0.3)] ring-1 ring-amber-300/40'
              : 'bg-gradient-to-b from-slate-850 via-slate-900 to-slate-950 border-2 border-slate-700/80 hover:border-slate-500/80 shadow-md',
          ]"
        >
          <!-- Embroidered Inset Stitched Border (heavy athletic felt embroidery look) -->
          <div
            class="absolute inset-1.5 rounded-b-xl border border-dashed pointer-events-none transition-colors"
            :class="selectedSeason === banner.season_year ? 'border-amber-400/50' : 'border-slate-700/60'"
          ></div>

          <!-- Top Grommet Holes Graphic -->
          <div class="w-full flex justify-between px-3 mb-2 z-10">
            <span class="w-2 h-2 rounded-full bg-slate-800 border border-slate-600"></span>
            <span class="w-2 h-2 rounded-full bg-slate-800 border border-slate-600"></span>
          </div>

          <!-- Season Year in Bold Varsity Athletic Block Letters -->
          <div class="relative z-10 my-0.5">
            <span
              class="font-black font-mono text-xl sm:text-2xl tracking-tighter transition-colors"
              :class="selectedSeason === banner.season_year ? 'text-amber-400 drop-shadow-[0_2px_4px_rgba(0,0,0,0.8)]' : 'text-slate-200'"
            >
              {{ banner.season_year }}
            </span>
          </div>

          <!-- Varsity CHAMPIONS Ribbon / Header -->
          <div
            class="relative z-10 px-3 py-0.5 rounded text-[10px] font-black tracking-widest uppercase font-mono my-1 border transition-colors"
            :class="[
              selectedSeason === banner.season_year
                ? 'bg-amber-500 text-slate-950 border-amber-400'
                : 'bg-slate-800 text-amber-300 border-slate-700',
            ]"
          >
            CHAMPIONS
          </div>

          <!-- Centered Championship Crest & Franchise Logo -->
          <div class="relative z-10 my-2">
            <div
              class="w-14 h-14 rounded-2xl bg-gradient-to-b from-slate-800 to-slate-950 p-0.5 border shadow-inner flex items-center justify-center transition-colors"
              :class="selectedSeason === banner.season_year ? 'border-amber-400/80 shadow-[0_0_12px_rgba(245,158,11,0.25)]' : 'border-slate-700'"
            >
              <TeamAvatar
                :src="banner.logo_url || banner.avatar_url"
                :name="banner.team_name"
                size="md"
                rounded="lg"
                class="!w-full !h-full"
              />
            </div>
            <span
              class="absolute -bottom-1 -right-1 p-1 rounded-full shadow transition-colors"
              :class="selectedSeason === banner.season_year ? 'bg-amber-400 text-slate-950' : 'bg-slate-700 text-slate-300'"
            >
              <Crown class="w-3 h-3 fill-current" />
            </span>
          </div>

          <!-- Franchise Name in Bold Athletic condensed text -->
          <h4 class="relative z-10 font-black text-sm text-white tracking-tight uppercase line-clamp-1 mt-1">
            {{ banner.team_name }}
          </h4>
          <p class="relative z-10 text-[11px] font-bold text-amber-300/90 truncate max-w-full">
            {{ banner.manager_name }}
          </p>

          <!-- Banner Bottom Stats (Record, Finals, Total Earnings) -->
          <div class="relative z-10 w-full mt-3 pt-2.5 border-t border-slate-800/80 text-[10px] font-mono text-slate-400 flex flex-col gap-1">
            <div class="flex items-center justify-between">
              <span class="tracking-wider">RECORD</span>
              <span class="font-bold text-slate-200">{{ banner.wins }}-{{ banner.losses }}</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="tracking-wider">FINALS</span>
              <span class="font-bold text-emerald-400">{{ banner.championship_score.toFixed(1) }} pts</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="tracking-wider">PRIZE</span>
              <span class="font-bold text-amber-400">${{ banner.payout_amount.toFixed(0) }}</span>
            </div>
          </div>

          <!-- Bottom Banner Tail Detail: Gold Fringe / Hem Trim -->
          <div class="absolute bottom-0 inset-x-0 h-1.5 flex items-center justify-center gap-1 opacity-80">
            <span
              v-for="j in 8"
              :key="j"
              class="w-1.5 h-1.5 rounded-b-sm transition-colors"
              :class="selectedSeason === banner.season_year ? 'bg-amber-400' : 'bg-slate-700'"
            ></span>
          </div>

          <!-- Active Spotlight Selection Pill -->
          <div
            v-if="selectedSeason === banner.season_year"
            class="relative z-10 mt-3 w-full py-1 rounded-md bg-amber-500/20 border border-amber-500/50 text-amber-300 text-[10px] font-mono font-bold flex items-center justify-center gap-1"
          >
            <Check class="w-3 h-3 stroke-[3]" />
            <span>SPOTLIGHTED</span>
          </div>
          <div
            v-else
            class="relative z-10 mt-3 w-full py-1 text-[10px] font-mono text-slate-500 group-hover:text-slate-300 transition-colors"
          >
            Inspect Banner
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar {
  display: none;
}
.no-scrollbar {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
.banner-shadow {
  box-shadow:
    0 10px 15px -3px rgba(0, 0, 0, 0.4),
    0 4px 6px -2px rgba(0, 0, 0, 0.2);
}
</style>
