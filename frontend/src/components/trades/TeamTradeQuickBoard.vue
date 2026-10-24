<script setup lang="ts">
import { computed } from 'vue';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import {
  Users,
  ArrowLeftRight,
  X,
  Layers,
} from 'lucide-vue-next';

export interface TeamActivityItem {
  manager_id: number;
  team_name: string;
  manager_name: string;
  logo_url: string | null;
  total_trades: number;
  executed_waivers: number;
  free_agent_adds: number;
  average_grade?: string | null;
}

const props = defineProps<{
  teams: TeamActivityItem[];
  selectedManagerId: number | null;
  totalTradesCount: number;
  totalWaiversCount: number;
}>();

const emit = defineEmits<{
  (e: 'select', managerId: number | null): void;
}>();

function toggleManager(mid: number) {
  if (props.selectedManagerId === mid) {
    emit('select', null);
  } else {
    emit('select', mid);
  }
}

const selectedTeam = computed(() => {
  if (props.selectedManagerId === null) return null;
  return props.teams.find((t) => t.manager_id === props.selectedManagerId) ?? null;
});

function getGradeBadgeClass(grade: string | null | undefined): string {
  if (!grade) return 'bg-slate-800 text-slate-400 border-slate-700';
  const g = grade.toUpperCase();
  if (g.startsWith('A')) return 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40';
  if (g.startsWith('B')) return 'bg-sky-500/20 text-sky-300 border-sky-500/40';
  if (g.startsWith('C')) return 'bg-amber-500/20 text-amber-300 border-amber-500/40';
  return 'bg-rose-500/20 text-rose-300 border-rose-500/40';
}
</script>

<template>
  <div class="space-y-2.5">
    <!-- Header Strip -->
    <div class="flex items-center justify-between gap-2 flex-wrap">
      <div class="flex items-center gap-2">
        <div class="w-6 h-6 rounded-lg bg-indigo-500/20 border border-indigo-500/40 flex items-center justify-center text-indigo-400">
          <Layers class="w-3.5 h-3.5" />
        </div>
        <div>
          <h3 class="text-xs font-black uppercase tracking-wider text-slate-200 flex items-center gap-2">
            <span>Franchise Activity & Trades</span>
            <span class="text-[10px] font-mono font-normal text-slate-400 lowercase">
              (click to isolate team)
            </span>
          </h3>
        </div>
      </div>

      <!-- Active Filter Pill if selected -->
      <div v-if="selectedTeam" class="flex items-center gap-2">
        <span class="text-[11px] text-slate-400">Filtering:</span>
        <button
          type="button"
          class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-600 text-white shadow-sm border border-indigo-400 hover:bg-indigo-500 transition-colors cursor-pointer"
          @click="emit('select', null)"
        >
          <span>{{ selectedTeam.team_name }}</span>
          <span class="text-[10px] font-mono opacity-80">({{ selectedTeam.total_trades }} trades)</span>
          <X class="w-3 h-3 ml-0.5" />
        </button>
      </div>
    </div>

    <!-- Quick Board Carousel / Strip -->
    <div class="flex items-stretch gap-2.5 overflow-x-auto pb-2 pt-0.5 scrollbar-thin scrollbar-thumb-slate-800">
      <!-- "All Franchises" Card -->
      <button
        type="button"
        class="shrink-0 w-36 sm:w-40 stadium-card rounded-xl p-3 border text-left transition-all flex flex-col justify-between gap-2 cursor-pointer focus:outline-none"
        :class="
          selectedManagerId === null
            ? 'bg-indigo-950/40 border-indigo-500 ring-2 ring-indigo-500/50 shadow-md shadow-indigo-950/60'
            : 'bg-slate-900/80 border-slate-800 hover:border-slate-700 hover:bg-slate-850'
        "
        @click="emit('select', null)"
      >
        <div class="flex items-center gap-2 min-w-0">
          <div
            class="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 border"
            :class="
              selectedManagerId === null
                ? 'bg-indigo-600 text-white border-indigo-400'
                : 'bg-slate-800 text-indigo-400 border-slate-700'
            "
          >
            <Users class="w-4 h-4" />
          </div>
          <div class="min-w-0 flex-1">
            <div class="text-xs font-bold text-slate-100 truncate">All Teams</div>
            <div class="text-[10px] text-slate-400 truncate">League Roster</div>
          </div>
        </div>

        <div class="flex items-center gap-1.5 flex-wrap pt-1 border-t border-slate-800/80">
          <span
            class="px-2 py-0.5 rounded text-[10px] font-mono font-bold border"
            :class="
              selectedManagerId === null
                ? 'bg-indigo-500/30 text-indigo-200 border-indigo-400'
                : 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30'
            "
          >
            {{ totalTradesCount }} Trades
          </span>
          <span class="px-1.5 py-0.5 rounded text-[10px] font-mono text-slate-400 bg-slate-800/80 border border-slate-700/60">
            {{ totalWaiversCount }} W
          </span>
        </div>
      </button>

      <!-- Team Franchise Cards -->
      <button
        v-for="t in teams"
        :key="t.manager_id"
        type="button"
        class="shrink-0 w-44 sm:w-48 stadium-card rounded-xl p-3 border text-left transition-all flex flex-col justify-between gap-2.5 cursor-pointer focus:outline-none"
        :class="
          selectedManagerId === t.manager_id
            ? 'bg-indigo-950/50 border-indigo-500 ring-2 ring-indigo-500/50 shadow-lg shadow-indigo-950/60'
            : 'bg-slate-900/80 border-slate-800 hover:border-slate-700 hover:bg-slate-850'
        "
        @click="toggleManager(t.manager_id)"
      >
        <!-- Team Info Row -->
        <div class="flex items-center gap-2.5 min-w-0">
          <TeamAvatar
            :src="t.logo_url"
            :name="t.team_name"
            size="sm"
          />
          <div class="min-w-0 flex-1">
            <div
              class="text-xs font-bold truncate transition-colors"
              :class="selectedManagerId === t.manager_id ? 'text-indigo-200' : 'text-slate-100'"
              :title="t.team_name"
            >
              {{ t.team_name }}
            </div>
            <div class="text-[10px] text-slate-400 truncate mt-0.5" :title="t.manager_name">
              {{ t.manager_name }}
            </div>
          </div>
        </div>

        <!-- Metrics Badges (Trades, Waivers, Grade / Add-ons) -->
        <div class="space-y-1.5 pt-1.5 border-t border-slate-800/80">
          <div class="flex items-center justify-between gap-1 text-[10px] font-mono">
            <!-- Trades Count -->
            <span
              class="inline-flex items-center gap-1 px-2 py-0.5 rounded font-bold border"
              :class="
                t.total_trades > 0
                  ? selectedManagerId === t.manager_id
                    ? 'bg-indigo-500 text-white border-indigo-400'
                    : 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40'
                  : 'bg-slate-800/60 text-slate-500 border-slate-800'
              "
            >
              <ArrowLeftRight class="w-3 h-3" />
              <span>{{ t.total_trades }} {{ t.total_trades === 1 ? 'Trade' : 'Trades' }}</span>
            </span>

            <!-- Waivers Count -->
            <span
              class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded border"
              :class="
                t.executed_waivers > 0
                  ? 'bg-amber-500/15 text-amber-300 border-amber-500/30 font-semibold'
                  : 'bg-slate-800/60 text-slate-500 border-slate-800'
              "
              :title="`${t.executed_waivers} successful waiver claims`"
            >
              <span>{{ t.executed_waivers }} W</span>
            </span>
          </div>

          <!-- Add-ons: Free Agent Adds & Trade Grade -->
          <div class="flex items-center justify-between gap-1 text-[10px] font-mono text-slate-400">
            <span class="truncate">
              {{ t.free_agent_adds }} FA adds
            </span>

            <span
              v-if="t.average_grade"
              class="px-1.5 py-0.2 rounded text-[10px] font-bold border shrink-0"
              :class="getGradeBadgeClass(t.average_grade)"
              :title="`Average trade grade: ${t.average_grade}`"
            >
              Grade {{ t.average_grade }}
            </span>
            <span v-else class="text-slate-600 text-[9px]">
              No trades
            </span>
          </div>
        </div>
      </button>
    </div>
  </div>
</template>
