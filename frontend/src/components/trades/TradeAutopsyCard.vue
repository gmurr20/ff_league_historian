<script setup lang="ts">
import { ref } from 'vue';
import type { TradeDetail, TradePlayerAsset } from '@/types/api';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import { ChevronRight } from 'lucide-vue-next';
import {
  positionTextClass,
  gradeTileClass,
  weekLabel,
  shortDate,
  tierText,
} from '@/components/trades/tradeUi';

defineProps<{
  trade: TradeDetail;
}>();

const emit = defineEmits<{
  (e: 'select', trade: TradeDetail): void;
}>();

// Track headshots that fail to load so we fall back to a position token
const failedImages = ref<Record<string | number, boolean>>({});

function handleImageError(id: string | number) {
  failedImages.value[id] = true;
}

function playerMeta(asset: TradePlayerAsset): string[] {
  const bits: string[] = [];
  if (asset.pro_team) bits.push(asset.pro_team);
  if (asset.positional_rank) bits.push(`${asset.default_position}${asset.positional_rank}`);
  const tier = tierText(asset.tier_label);
  if (tier) bits.push(tier);
  return bits;
}
</script>

<template>
  <article
    role="button"
    tabindex="0"
    class="group rounded-2xl border border-slate-800/80 bg-slate-900/50 hover:bg-slate-900/80 hover:border-slate-700 transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50"
    @click="emit('select', trade)"
    @keydown.enter="emit('select', trade)"
  >
    <!-- Meta row -->
    <header class="flex items-center justify-between gap-3 px-4 pt-3 pb-2 text-[11px]">
      <div class="flex items-center gap-1.5 min-w-0 text-slate-400 font-mono tabular-nums">
        <span class="text-slate-200 font-semibold">{{ trade.season_year }}</span>
        <template v-if="trade.week != null">
          <span class="text-slate-600">/</span>
          <span>{{ weekLabel(trade.week, true) }}</span>
        </template>
        <template v-if="trade.executed_at">
          <span class="text-slate-600">/</span>
          <span>{{ shortDate(trade.executed_at) }}</span>
        </template>
        <span v-if="trade.is_projected" class="ml-1 inline-flex items-center gap-1 text-cyan-300 font-sans">
          <span class="w-1.5 h-1.5 rounded-full bg-cyan-400" />
          Live
        </span>
      </div>

      <div class="flex items-center gap-1 shrink-0">
        <ChevronRight class="w-4 h-4 text-slate-600 group-hover:text-slate-300 group-hover:translate-x-0.5 transition" />
      </div>
    </header>

    <!-- Sides: stacked on mobile, side-by-side from md -->
    <div class="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-slate-800/80 border-t border-slate-800/80">
      <section
        v-for="side in trade.sides"
        :key="side.manager_id"
        class="px-4 py-3 space-y-2.5 min-w-0"
      >
        <!-- Team + grade -->
        <div class="flex items-center gap-3">
          <TeamAvatar :src="side.logo_url" :name="side.team_name || side.manager_name" size="sm" />
          <div class="min-w-0 flex-1">
            <div class="text-sm font-semibold text-slate-100 truncate leading-tight" :title="side.team_name">
              {{ side.team_name }}
            </div>
            <div class="text-xs text-slate-500 truncate">{{ side.manager_name }}</div>
          </div>
          <div
            class="w-10 h-10 rounded-lg flex items-center justify-center text-base font-black tracking-tight shrink-0"
            :class="gradeTileClass(side.grade)"
            :title="`Trade grade ${side.grade}`"
          >
            {{ side.grade || '–' }}
          </div>
        </div>

        <!-- Received assets -->
        <ul class="space-y-2 pl-11">
          <li v-for="asset in side.assets_received" :key="asset.player_id" class="flex items-start gap-2.5 min-w-0">
            <!-- Draft pick -->
            <template v-if="asset.asset_type === 'PICK'">
              <div class="w-7 h-7 rounded-md bg-violet-500/10 text-violet-300 text-[10px] font-bold font-mono flex items-center justify-center shrink-0">
                R{{ asset.pick_round ?? '?' }}
              </div>
              <div class="min-w-0 flex-1">
                <div class="text-[13px] font-medium text-slate-200 truncate leading-tight">{{ asset.full_name }}</div>
                <div class="text-[11px] text-slate-500 truncate mt-0.5">
                  <template v-if="asset.drafted_player_name">
                    Became
                    <span class="text-slate-300">{{ asset.drafted_player_name }}</span>
                    <span v-if="asset.drafted_player_position" :class="positionTextClass(asset.drafted_player_position)">
                      {{ asset.drafted_player_position }}
                    </span>
                  </template>
                  <template v-else>Draft pick<span v-if="tierText(asset.tier_label)"> · {{ tierText(asset.tier_label) }}</span></template>
                </div>
              </div>
            </template>

            <!-- Player -->
            <template v-else>
              <div class="w-7 h-7 rounded-full bg-slate-800 overflow-hidden shrink-0 flex items-center justify-center">
                <img
                  v-if="asset.headshot_url && !failedImages[asset.player_id]"
                  :src="asset.headshot_url"
                  :alt="asset.full_name"
                  class="w-full h-full object-cover"
                  loading="lazy"
                  @error="handleImageError(asset.player_id)"
                />
                <span v-else class="text-[9px] font-bold font-mono" :class="positionTextClass(asset.default_position)">
                  {{ asset.default_position }}
                </span>
              </div>
              <div class="min-w-0 flex-1">
                <div class="text-[13px] font-medium text-slate-200 truncate leading-tight" :title="asset.full_name">
                  {{ asset.full_name }}
                </div>
                <div class="text-[11px] text-slate-500 truncate mt-0.5">
                  <span class="font-semibold" :class="positionTextClass(asset.default_position)">{{ asset.default_position }}</span>
                  <span v-for="bit in playerMeta(asset)" :key="bit"> · {{ bit }}</span>
                </div>
              </div>
            </template>
          </li>

          <li v-if="side.faab_received > 0" class="flex items-center gap-2.5">
            <div class="w-7 h-7 rounded-md bg-amber-500/10 text-amber-300 text-xs font-bold flex items-center justify-center shrink-0">$</div>
            <div class="text-[13px] font-medium text-slate-200 font-mono tabular-nums">${{ side.faab_received }} FAAB</div>
          </li>

          <li
            v-if="side.assets_received.length === 0 && side.faab_received <= 0"
            class="text-xs text-slate-500 italic"
          >
            Nothing recorded
          </li>
        </ul>
      </section>
    </div>

    <!-- Verdict footer -->
    <footer
      v-if="trade.verdict_label"
      class="px-4 py-2 border-t border-slate-800/80 text-[11px] text-slate-500 flex items-center justify-between gap-2"
    >
      <span class="truncate">{{ trade.verdict_label }}</span>
      <span class="text-slate-400 group-hover:text-emerald-300 transition-colors shrink-0">Breakdown</span>
    </footer>
  </article>
</template>
