<script setup lang="ts">
import { computed } from 'vue';
import type { H2HManagerRef, H2HMatrixEntry } from '@/types/api';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import { Swords, Info } from 'lucide-vue-next';

const props = defineProps<{
  managers: H2HManagerRef[];
  matrix: H2HMatrixEntry[];
  selectedManagerA: number | null;
  selectedManagerB: number | null;
}>();

const emit = defineEmits<{
  (e: 'selectPair', managerA: number, managerB: number): void;
}>();

const matrixMap = computed(() => {
  const map = new Map<string, H2HMatrixEntry>();
  for (const entry of props.matrix) {
    map.set(`${entry.manager_a_id}_${entry.manager_b_id}`, entry);
  }
  return map;
});

function getCellData(rowId: number, colId: number) {
  if (rowId === colId) {
    return {
      isSelf: true,
      wins: 0,
      losses: 0,
      ties: 0,
      winPct: 0,
      totalGames: 0,
    };
  }

  // Direct lookup
  const direct = matrixMap.value.get(`${rowId}_${colId}`);
  if (direct) {
    return {
      isSelf: false,
      wins: direct.wins,
      losses: direct.losses,
      ties: direct.ties,
      winPct: direct.win_pct,
      totalGames: direct.total_games,
    };
  }

  // Reverse lookup fallback
  const reverse = matrixMap.value.get(`${colId}_${rowId}`);
  if (reverse) {
    const total = reverse.total_games;
    const wins = reverse.losses;
    const losses = reverse.wins;
    const ties = reverse.ties;
    const winPct = total > 0 ? (wins + 0.5 * ties) / total : 0;
    return {
      isSelf: false,
      wins,
      losses,
      ties,
      winPct,
      totalGames: total,
    };
  }

  return {
    isSelf: false,
    wins: 0,
    losses: 0,
    ties: 0,
    winPct: 0,
    totalGames: 0,
  };
}

function handleCellClick(rowManagerId: number, colManagerId: number) {
  if (rowManagerId === colManagerId) return;
  emit('selectPair', rowManagerId, colManagerId);
}
</script>

<template>
  <div class="space-y-3">
    <!-- Matrix Header & Instructions -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 px-1">
      <div>
        <h3 class="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
          <Swords class="w-4 h-4 text-emerald-400" />
          <span>Career Win-Rate Matrix</span>
        </h3>
        <p class="text-[11px] text-slate-400 mt-0.5">
          Row Manager record vs Column Opponent. Tap any matchup cell to inspect.
        </p>
      </div>

      <!-- Quick Legend -->
      <div class="flex items-center gap-3 text-[11px] text-slate-400 font-medium">
        <div class="flex items-center gap-1.5">
          <span class="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
          <span>Winning (&gt;50%)</span>
        </div>
        <div class="flex items-center gap-1.5">
          <span class="w-2.5 h-2.5 rounded-full bg-amber-500"></span>
          <span>Even (.500)</span>
        </div>
        <div class="flex items-center gap-1.5">
          <span class="w-2.5 h-2.5 rounded-full bg-rose-500"></span>
          <span>Losing (&lt;50%)</span>
        </div>
      </div>
    </div>

    <!-- Scrollable Matrix Table Container -->
    <div
      class="stadium-card rounded-2xl border border-slate-800 overflow-hidden shadow-2xl relative"
    >
      <div class="overflow-x-auto max-h-[70vh] overscroll-x-contain">
        <table class="w-full border-collapse text-left">
          <!-- Table Column Headers -->
          <thead>
            <tr>
              <!-- Top-Left Sticky Corner Cell -->
              <th
                class="sticky top-0 left-0 z-30 bg-slate-900 border-r border-b border-slate-800 p-2.5 min-w-[120px] max-w-[140px] text-left"
              >
                <div class="text-[10px] font-black uppercase tracking-wider text-slate-400 flex items-center justify-between">
                  <span>Row \ Col</span>
                  <Swords class="w-3.5 h-3.5 text-slate-500" />
                </div>
              </th>

              <!-- Manager Column Headers -->
              <th
                v-for="col in managers"
                :key="col.manager_id"
                class="sticky top-0 z-10 bg-slate-900/95 backdrop-blur-md border-b border-slate-800 p-2 text-center min-w-[88px] transition-colors"
                :class="[
                  selectedManagerB === col.manager_id
                    ? 'bg-emerald-950/40 text-emerald-300'
                    : 'text-slate-300',
                ]"
              >
                <div class="flex flex-col items-center gap-0.5">
                  <TeamAvatar :src="col.avatar_url" :name="col.team_name" size="xs" rounded="lg" />
                  <span
                    class="block text-[10px] font-bold truncate max-w-[80px] leading-tight mt-0.5"
                    :title="col.team_name"
                  >
                    {{ col.team_name }}
                  </span>
                  <span
                    class="block text-[9px] text-slate-400 font-normal truncate max-w-[80px] leading-tight"
                    :title="col.display_name"
                  >
                    {{ col.display_name }}
                  </span>
                </div>
              </th>
            </tr>
          </thead>

          <!-- Table Body (Rows: Manager A) -->
          <tbody>
            <tr
              v-for="row in managers"
              :key="row.manager_id"
              class="border-b border-slate-800/60 hover:bg-slate-800/20 transition-colors"
            >
              <!-- Row Manager Header (Sticky First Column) -->
              <th
                class="sticky left-0 z-20 bg-slate-900/95 backdrop-blur-md border-r border-slate-800 p-2.5 min-w-[140px] max-w-[165px] transition-colors"
                :class="[
                  selectedManagerA === row.manager_id
                    ? 'bg-emerald-950/40 text-emerald-300'
                    : 'text-slate-200',
                ]"
              >
                <div class="flex items-center gap-2 min-w-0">
                  <TeamAvatar :src="row.avatar_url" :name="row.team_name" size="xs" rounded="lg" />
                  <div class="min-w-0">
                    <div class="text-xs font-bold truncate leading-tight" :title="row.team_name">
                      {{ row.team_name }}
                    </div>
                    <div class="text-[10px] text-slate-400 font-normal truncate leading-tight mt-0.5" :title="row.display_name">
                      {{ row.display_name }}
                    </div>
                  </div>
                </div>
              </th>

              <!-- Matrix Cells -->
              <td
                v-for="col in managers"
                :key="`${row.manager_id}_${col.manager_id}`"
                class="p-1 text-center"
              >
                <template v-if="getCellData(row.manager_id, col.manager_id).isSelf">
                  <!-- Diagonal: Self Matchup -->
                  <div
                    class="w-full h-12 rounded-lg bg-slate-950/60 border border-slate-800/30 flex items-center justify-center text-slate-600 select-none cursor-not-allowed"
                    title="Self"
                  >
                    <span class="text-sm font-bold opacity-30">—</span>
                  </div>
                </template>

                <template v-else>
                  <!-- Interactive Record Cell -->
                  <button
                    type="button"
                    class="w-full h-12 rounded-lg p-1 flex flex-col items-center justify-center transition-all select-none group"
                    :class="[
                      // Highlight if currently selected pair
                      selectedManagerA === row.manager_id && selectedManagerB === col.manager_id
                        ? 'ring-2 ring-emerald-400 ring-offset-1 ring-offset-slate-950 shadow-md shadow-emerald-950 z-10'
                        : '',
                      // Color coding based on win percentage & games
                      getCellData(row.manager_id, col.manager_id).totalGames === 0
                        ? 'bg-slate-900/40 text-slate-500 hover:bg-slate-800/60'
                        : getCellData(row.manager_id, col.manager_id).winPct > 0.5
                          ? 'bg-emerald-950/40 border border-emerald-800/40 text-emerald-300 hover:bg-emerald-900/60'
                          : getCellData(row.manager_id, col.manager_id).winPct < 0.5
                            ? 'bg-rose-950/40 border border-rose-800/40 text-rose-300 hover:bg-rose-900/60'
                            : 'bg-amber-950/40 border border-amber-800/40 text-amber-300 hover:bg-amber-900/60',
                    ]"
                    :title="`${row.display_name} vs ${col.display_name}: ${getCellData(row.manager_id, col.manager_id).wins}-${getCellData(row.manager_id, col.manager_id).losses}${getCellData(row.manager_id, col.manager_id).ties > 0 ? `-${getCellData(row.manager_id, col.manager_id).ties}` : ''}`"
                    @click="handleCellClick(row.manager_id, col.manager_id)"
                  >
                    <!-- Record (W-L or W-L-T) -->
                    <span class="font-mono text-xs font-bold leading-tight tabular-nums">
                      {{ getCellData(row.manager_id, col.manager_id).wins }}-{{ getCellData(row.manager_id, col.manager_id).losses }}<template v-if="getCellData(row.manager_id, col.manager_id).ties > 0">-{{ getCellData(row.manager_id, col.manager_id).ties }}</template>
                    </span>

                    <!-- Win Percentage -->
                    <span
                      v-if="getCellData(row.manager_id, col.manager_id).totalGames > 0"
                      class="text-[9px] font-mono opacity-80 leading-none mt-0.5"
                    >
                      {{ Math.round(getCellData(row.manager_id, col.manager_id).winPct * 100) }}%
                    </span>
                    <span
                      v-else
                      class="text-[9px] font-mono text-slate-600 leading-none mt-0.5"
                    >
                      unplayed
                    </span>
                  </button>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Matrix Footnote / Helpful Hint -->
    <div class="flex items-center gap-2 px-2 text-xs text-slate-500">
      <Info class="w-3.5 h-3.5 shrink-0 text-slate-400" />
      <span>Tap any cell in the grid to open the Tale of the Tape and historical matchups.</span>
    </div>
  </div>
</template>
