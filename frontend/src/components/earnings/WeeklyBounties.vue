<script setup lang="ts">
import { ref, computed } from 'vue';
import type { WeeklyNuancedPayoutEntry } from '@/types/api';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import { ChevronDown, ChevronUp } from 'lucide-vue-next';

const props = defineProps<{
  payouts: WeeklyNuancedPayoutEntry[];
  seasonYear: number | null;
}>();

// Collapse state when weeks accumulate (threshold = 4 weeks)
const isExpanded = ref<boolean>(false);

// Sort reverse-chronological (most recent week first: Week 6, Week 5, ...)
const sortedPayouts = computed(() => {
  return [...props.payouts].sort((a, b) => b.week - a.week);
});

// Displayed payouts accounting for collapse
const visiblePayouts = computed(() => {
  if (isExpanded.value || sortedPayouts.value.length <= 4) {
    return sortedPayouts.value;
  }
  return sortedPayouts.value.slice(0, 4);
});

// Split into 2 vertical columns so Week 1 and Week 2 appear in the first column
const col1 = computed(() => {
  const list = visiblePayouts.value;
  const half = Math.ceil(list.length / 2);
  return list.slice(0, half);
});

const col2 = computed(() => {
  const list = visiblePayouts.value;
  const half = Math.ceil(list.length / 2);
  return list.slice(half);
});

const totalBountyCash = computed(() => {
  return sortedPayouts.value.reduce(
    (acc, p) => acc + p.high_score_amount + p.high_loser_amount,
    0
  );
});
</script>

<template>
  <div class="rounded-xl border border-slate-800/90 bg-[#0b101b] overflow-hidden shadow-lg">
    <!-- Header Strip -->
    <div class="flex items-center justify-between px-3.5 py-2.5 bg-slate-900/90 border-b border-slate-800/90">
      <div class="flex items-baseline gap-2 min-w-0">
        <h3 class="text-xs sm:text-sm font-black uppercase tracking-tight text-slate-100 truncate">
          Weekly Bounties
        </h3>
        <span class="text-[10px] font-mono uppercase text-slate-400 truncate">
          $10 High Score · $10 High Loser
        </span>
      </div>

      <div class="text-right shrink-0 font-mono text-[11px]">
        <span class="font-bold text-emerald-400 tabular-nums">
          ${{ totalBountyCash.toFixed(0) }}
        </span>
        <span class="text-slate-500 text-[10px] ml-1">Awarded</span>
      </div>
    </div>

    <!-- Empty State -->
    <div
      v-if="sortedPayouts.length === 0"
      class="p-6 text-center text-slate-500 text-xs font-mono"
    >
      No weekly bounties recorded yet for Season {{ seasonYear ?? '' }}.
    </div>

    <!-- 2-Column Layout of Weeks (Week 1 & Week 2 in Col 1, Week 3 & Week 4 in Col 2) -->
    <div v-else class="p-2 sm:p-3 grid grid-cols-1 sm:grid-cols-2 gap-2.5 items-start">
      <!-- Column 1 -->
      <div class="space-y-2.5">
        <div
          v-for="item in col1"
          :key="item.week"
          class="rounded-lg bg-slate-900/70 border border-slate-800/80 p-2.5 space-y-2 transition-colors hover:border-slate-700/80"
        >
          <!-- Week Header Row -->
          <div class="flex items-center justify-between text-[11px] font-mono border-b border-slate-800/50 pb-1.5">
            <span class="font-bold uppercase tracking-wider text-slate-200">
              Week {{ item.week }}
            </span>
            <span class="text-slate-400 font-semibold tabular-nums">
              ${{ (item.high_score_amount + item.high_loser_amount).toFixed(0) }}
            </span>
          </div>

          <!-- High Score Row (Green to Signify Win) -->
          <div class="flex items-center justify-between gap-2">
            <div class="flex items-center gap-2 min-w-0">
              <TeamAvatar
                :src="item.high_score_avatar_url"
                :name="item.high_score_team_name"
                size="xs"
                rounded="lg"
              />
              <div class="min-w-0">
                <div class="flex items-center gap-1.5">
                  <span class="text-[9px] font-mono font-black uppercase tracking-wider px-1.5 py-0.2 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 shrink-0">
                    High Score
                  </span>
                  <span class="text-xs font-bold text-slate-100 truncate">
                    {{ item.high_score_team_name }}
                  </span>
                </div>
                <div class="text-[10px] text-slate-400 truncate">
                  {{ item.high_score_manager_name }}
                </div>
              </div>
            </div>

            <div class="text-right shrink-0 font-mono">
              <div class="text-xs font-bold text-emerald-400 tabular-nums">
                {{ item.high_score_points.toFixed(2) }}
              </div>
              <div class="text-[10px] font-bold text-emerald-400">
                +${{ item.high_score_amount.toFixed(0) }}
              </div>
            </div>
          </div>

          <!-- High Loser Row (Rose/Slate to Signify Loss) -->
          <div class="flex items-center justify-between gap-2 pt-1 border-t border-slate-800/40">
            <div class="flex items-center gap-2 min-w-0">
              <TeamAvatar
                :src="item.high_loser_avatar_url"
                :name="item.high_loser_team_name"
                size="xs"
                rounded="lg"
              />
              <div class="min-w-0">
                <div class="flex items-center gap-1.5">
                  <span class="text-[9px] font-mono font-black uppercase tracking-wider px-1.5 py-0.2 rounded bg-rose-500/15 text-rose-300 border border-rose-500/30 shrink-0">
                    High Loser
                  </span>
                  <span class="text-xs font-bold text-slate-100 truncate">
                    {{ item.high_loser_team_name }}
                  </span>
                </div>
                <div class="text-[10px] text-slate-400 truncate">
                  {{ item.high_loser_manager_name }}
                </div>
              </div>
            </div>

            <div class="text-right shrink-0 font-mono">
              <div class="text-xs font-bold text-slate-300 tabular-nums">
                {{ item.high_loser_points.toFixed(2) }}
              </div>
              <div class="text-[10px] font-bold text-emerald-400">
                +${{ item.high_loser_amount.toFixed(0) }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Column 2 -->
      <div class="space-y-2.5">
        <div
          v-for="item in col2"
          :key="item.week"
          class="rounded-lg bg-slate-900/70 border border-slate-800/80 p-2.5 space-y-2 transition-colors hover:border-slate-700/80"
        >
          <!-- Week Header Row -->
          <div class="flex items-center justify-between text-[11px] font-mono border-b border-slate-800/50 pb-1.5">
            <span class="font-bold uppercase tracking-wider text-slate-200">
              Week {{ item.week }}
            </span>
            <span class="text-slate-400 font-semibold tabular-nums">
              ${{ (item.high_score_amount + item.high_loser_amount).toFixed(0) }}
            </span>
          </div>

          <!-- High Score Row (Green to Signify Win) -->
          <div class="flex items-center justify-between gap-2">
            <div class="flex items-center gap-2 min-w-0">
              <TeamAvatar
                :src="item.high_score_avatar_url"
                :name="item.high_score_team_name"
                size="xs"
                rounded="lg"
              />
              <div class="min-w-0">
                <div class="flex items-center gap-1.5">
                  <span class="text-[9px] font-mono font-black uppercase tracking-wider px-1.5 py-0.2 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 shrink-0">
                    High Score
                  </span>
                  <span class="text-xs font-bold text-slate-100 truncate">
                    {{ item.high_score_team_name }}
                  </span>
                </div>
                <div class="text-[10px] text-slate-400 truncate">
                  {{ item.high_score_manager_name }}
                </div>
              </div>
            </div>

            <div class="text-right shrink-0 font-mono">
              <div class="text-xs font-bold text-emerald-400 tabular-nums">
                {{ item.high_score_points.toFixed(2) }}
              </div>
              <div class="text-[10px] font-bold text-emerald-400">
                +${{ item.high_score_amount.toFixed(0) }}
              </div>
            </div>
          </div>

          <!-- High Loser Row (Rose/Slate to Signify Loss) -->
          <div class="flex items-center justify-between gap-2 pt-1 border-t border-slate-800/40">
            <div class="flex items-center gap-2 min-w-0">
              <TeamAvatar
                :src="item.high_loser_avatar_url"
                :name="item.high_loser_team_name"
                size="xs"
                rounded="lg"
              />
              <div class="min-w-0">
                <div class="flex items-center gap-1.5">
                  <span class="text-[9px] font-mono font-black uppercase tracking-wider px-1.5 py-0.2 rounded bg-rose-500/15 text-rose-300 border border-rose-500/30 shrink-0">
                    High Loser
                  </span>
                  <span class="text-xs font-bold text-slate-100 truncate">
                    {{ item.high_loser_team_name }}
                  </span>
                </div>
                <div class="text-[10px] text-slate-400 truncate">
                  {{ item.high_loser_manager_name }}
                </div>
              </div>
            </div>

            <div class="text-right shrink-0 font-mono">
              <div class="text-xs font-bold text-slate-300 tabular-nums">
                {{ item.high_loser_points.toFixed(2) }}
              </div>
              <div class="text-[10px] font-bold text-emerald-400">
                +${{ item.high_loser_amount.toFixed(0) }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Collapse / Expand Footer Bar (when more than 4 weeks exist) -->
    <div
      v-if="sortedPayouts.length > 4"
      class="p-1.5 bg-slate-900/80 border-t border-slate-800/80 text-center"
    >
      <button
        type="button"
        class="w-full py-1 px-3 text-[11px] font-mono font-bold text-slate-400 hover:text-slate-200 flex items-center justify-center gap-1 transition-colors"
        @click="isExpanded = !isExpanded"
      >
        <span>{{ isExpanded ? 'Show Fewer Weeks' : `View All ${sortedPayouts.length} Weeks` }}</span>
        <component :is="isExpanded ? ChevronUp : ChevronDown" class="w-3.5 h-3.5 text-slate-400" />
      </button>
    </div>
  </div>
</template>
