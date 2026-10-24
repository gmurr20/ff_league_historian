<script setup lang="ts">
import type { TopTradePartner } from '@/types/api';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import { ArrowLeftRight, ChevronRight } from 'lucide-vue-next';

const props = withDefaults(
  defineProps<{
    partner: TopTradePartner;
    rank: number;
    selected?: boolean;
    isInactiveA?: boolean;
    isInactiveB?: boolean;
  }>(),
  {
    selected: false,
    isInactiveA: false,
    isInactiveB: false,
  }
);

const emit = defineEmits<{
  (e: 'select', partner: TopTradePartner): void;
}>();

function handleClick() {
  emit('select', props.partner);
}
</script>

<template>
  <article
    role="button"
    tabindex="0"
    :aria-selected="selected"
    class="group rounded-2xl border transition-colors cursor-pointer p-3.5 space-y-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50"
    :class="[
      selected
        ? 'border-emerald-500/60 bg-slate-900/90 shadow-md shadow-emerald-950/20'
        : 'border-slate-800/80 bg-slate-900/50 hover:bg-slate-900/80 hover:border-slate-700',
      (isInactiveA || isInactiveB) && !selected ? 'opacity-70 hover:opacity-100 bg-slate-950/40' : '',
    ]"
    @click="handleClick"
    @keydown.enter="handleClick"
    @keydown.space.prevent="handleClick"
  >
    <!-- Top row: Rank, Trade Count, and Action cue -->
    <header class="flex items-center justify-between text-xs">
      <div class="flex items-center gap-2">
        <span
          class="font-mono text-xs font-bold tabular-nums"
          :class="rank === 1 ? 'text-amber-400' : 'text-slate-500'"
        >
          #{{ rank }}
        </span>
        <span class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Alliance
        </span>
      </div>

      <div class="flex items-center gap-1.5">
        <span
          class="px-2 py-0.5 rounded-md text-[11px] font-mono font-bold tabular-nums"
          :class="
            selected
              ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
              : 'bg-slate-800/80 text-slate-300 border border-slate-700/60'
          "
        >
          {{ partner.trade_count }} {{ partner.trade_count === 1 ? 'trade' : 'trades' }}
        </span>
        <ChevronRight
          class="w-3.5 h-3.5 text-slate-600 group-hover:text-slate-300 group-hover:translate-x-0.5 transition"
        />
      </div>
    </header>

    <!-- Bilateral Partners: Team A ⇄ Team B -->
    <div class="space-y-2 pt-0.5">
      <!-- Team A -->
      <div class="flex items-center gap-2.5 min-w-0">
        <TeamAvatar
          :src="partner.manager_a_avatar_url"
          :name="partner.manager_a_team_name || partner.manager_a_name"
          size="sm"
        />
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-1.5 min-w-0">
            <span
              class="text-[13px] font-semibold text-slate-100 truncate leading-tight"
              :title="partner.manager_a_team_name || partner.manager_a_name"
            >
              {{ partner.manager_a_team_name || partner.manager_a_name }}
            </span>
            <span
              v-if="isInactiveA"
              class="inline-flex items-center text-[7.5px] font-mono font-bold uppercase px-1 py-0.2 rounded bg-slate-800 text-slate-400 border border-slate-700/60 shrink-0"
            >
              Inactive
            </span>
          </div>
          <div class="text-[11px] text-slate-500 truncate">{{ partner.manager_a_name }}</div>
        </div>
      </div>

      <!-- Divider with clean corridor icon -->
      <div class="flex items-center gap-2 px-1 text-slate-700">
        <div class="h-px flex-1 bg-slate-800" />
        <ArrowLeftRight class="w-3 h-3 text-slate-500" />
        <div class="h-px flex-1 bg-slate-800" />
      </div>

      <!-- Team B -->
      <div class="flex items-center gap-2.5 min-w-0">
        <TeamAvatar
          :src="partner.manager_b_avatar_url"
          :name="partner.manager_b_team_name || partner.manager_b_name"
          size="sm"
        />
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-1.5 min-w-0">
            <span
              class="text-[13px] font-semibold text-slate-100 truncate leading-tight"
              :title="partner.manager_b_team_name || partner.manager_b_name"
            >
              {{ partner.manager_b_team_name || partner.manager_b_name }}
            </span>
            <span
              v-if="isInactiveB"
              class="inline-flex items-center text-[7.5px] font-mono font-bold uppercase px-1 py-0.2 rounded bg-slate-800 text-slate-400 border border-slate-700/60 shrink-0"
            >
              Inactive
            </span>
          </div>
          <div class="text-[11px] text-slate-500 truncate">{{ partner.manager_b_name }}</div>
        </div>
      </div>
    </div>

    <!-- Metrics footer -->
    <footer
      class="pt-2 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-500 font-mono tabular-nums"
    >
      <span>
        {{ partner.total_assets_exchanged }} {{ partner.total_assets_exchanged === 1 ? 'asset' : 'assets' }} · {{ partner.total_trade_score_volume.toFixed(1) }} vol
      </span>
      <span v-if="partner.net_score_differential > 0" class="text-slate-400">
        Δ {{ partner.net_score_differential.toFixed(1) }} margin
      </span>
    </footer>
  </article>
</template>
