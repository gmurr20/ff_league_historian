<script setup lang="ts">
import { computed } from 'vue';
import type { StandingEntry } from '@/types/api';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import { Crown, Sparkles, ShieldAlert, Calendar } from 'lucide-vue-next';

const props = defineProps<{
  standings: StandingEntry[];
  seasonYear: number;
  isActive: boolean;
  isCompleted: boolean;
  currentWeek: number;
}>();

const topScorer = computed(() => {
  if (!props.standings.length) return null;
  return [...props.standings].sort((a, b) => b.points_for - a.points_for)[0];
});

const luckiest = computed(() => {
  if (!props.standings.length) return null;
  const sorted = [...props.standings].sort((a, b) => b.luck_index - a.luck_index);
  return sorted[0];
});

const mostRobbed = computed(() => {
  if (!props.standings.length) return null;
  const sorted = [...props.standings].sort((a, b) => a.luck_index - b.luck_index);
  return sorted[0];
});

function formatLuck(val: number): string {
  const pct = Math.abs(val) <= 1 ? val * 100 : val;
  const sign = pct > 0 ? '+' : '';
  return `${sign}${pct.toFixed(1)}%`;
}
</script>

<template>
  <div class="space-y-2">
    <!-- Week & Franchise Count Strip -->
    <div class="flex items-center justify-between text-xs px-1">
      <div class="flex items-center gap-2">
        <span class="text-slate-400 font-mono flex items-center gap-1 text-[11px]">
          <Calendar class="w-3 h-3 text-slate-500" />
          <span>{{ isCompleted ? 'Completed Season' : `Week ${currentWeek}` }}</span>
        </span>
      </div>

      <span class="text-[11px] font-mono text-slate-500">
        {{ standings.length }} Franchises
      </span>
    </div>

    <!-- KPI Cards Grid -->
    <div class="grid grid-cols-3 gap-2">
      <!-- Top Scorer -->
      <div
        class="stadium-card rounded-xl p-2.5 sm:p-3 border border-slate-800/80 flex flex-col justify-between"
      >
        <div class="flex items-center justify-between gap-1 mb-1.5">
          <span class="text-[10px] uppercase font-bold tracking-wider text-slate-400">Top Scorer</span>
          <Crown class="w-3.5 h-3.5 text-amber-400 shrink-0" />
        </div>
        <div v-if="topScorer" class="space-y-1">
          <div class="flex items-center gap-2 min-w-0">
            <TeamAvatar :src="topScorer.logo_url" :name="topScorer.team_name" size="xs" rounded="lg" />
            <div class="min-w-0">
              <div class="text-xs font-bold text-slate-100 truncate leading-tight" :title="topScorer.team_name">
                {{ topScorer.team_name }}
              </div>
              <div class="text-[10px] text-slate-400 truncate leading-tight" :title="topScorer.manager_name">
                {{ topScorer.manager_name }}
              </div>
            </div>
          </div>
          <div class="text-[11px] font-mono text-amber-400 font-semibold tabular-nums">
            {{ topScorer.points_for.toFixed(1) }} <span class="text-[9px] text-slate-400 uppercase">PF</span>
          </div>
        </div>
        <div v-else class="text-xs text-slate-500">—</div>
      </div>

      <!-- Luckiest Manager -->
      <div
        class="stadium-card rounded-xl p-2.5 sm:p-3 border border-slate-800/80 flex flex-col justify-between"
      >
        <div class="flex items-center justify-between gap-1 mb-1.5">
          <span class="text-[10px] uppercase font-bold tracking-wider text-emerald-400">Luckiest</span>
          <Sparkles class="w-3.5 h-3.5 text-emerald-400 shrink-0" />
        </div>
        <div v-if="luckiest" class="space-y-1">
          <div class="flex items-center gap-2 min-w-0">
            <TeamAvatar :src="luckiest.logo_url" :name="luckiest.team_name" size="xs" rounded="lg" />
            <div class="min-w-0">
              <div class="text-xs font-bold text-slate-100 truncate leading-tight" :title="luckiest.team_name">
                {{ luckiest.team_name }}
              </div>
              <div class="text-[10px] text-slate-400 truncate leading-tight" :title="luckiest.manager_name">
                {{ luckiest.manager_name }}
              </div>
            </div>
          </div>
          <div class="text-[11px] font-mono text-emerald-400 font-semibold tabular-nums">
            {{ formatLuck(luckiest.luck_index) }} <span class="text-[9px] text-emerald-500 uppercase">Luck</span>
          </div>
        </div>
        <div v-else class="text-xs text-slate-500">—</div>
      </div>

      <!-- Most Robbed Manager -->
      <div
        class="stadium-card rounded-xl p-2.5 sm:p-3 border border-slate-800/80 flex flex-col justify-between"
      >
        <div class="flex items-center justify-between gap-1 mb-1.5">
          <span class="text-[10px] uppercase font-bold tracking-wider text-rose-400">Most Robbed</span>
          <ShieldAlert class="w-3.5 h-3.5 text-rose-400 shrink-0" />
        </div>
        <div v-if="mostRobbed" class="space-y-1">
          <div class="flex items-center gap-2 min-w-0">
            <TeamAvatar :src="mostRobbed.logo_url" :name="mostRobbed.team_name" size="xs" rounded="lg" />
            <div class="min-w-0">
              <div class="text-xs font-bold text-slate-100 truncate leading-tight" :title="mostRobbed.team_name">
                {{ mostRobbed.team_name }}
              </div>
              <div class="text-[10px] text-slate-400 truncate leading-tight" :title="mostRobbed.manager_name">
                {{ mostRobbed.manager_name }}
              </div>
            </div>
          </div>
          <div class="text-[11px] font-mono text-rose-400 font-semibold tabular-nums">
            {{ formatLuck(mostRobbed.luck_index) }} <span class="text-[9px] text-rose-500 uppercase">Luck</span>
          </div>
        </div>
        <div v-else class="text-xs text-slate-500">—</div>
      </div>
    </div>
  </div>
</template>
