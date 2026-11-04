<script setup lang="ts">
import { ref, computed } from 'vue';
import type { HistoricalDraftData } from '@/types/api';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import {
  ListOrdered,
  Users,
  Search,
  X,
  Lock,
  Calendar,
  Layers,
} from 'lucide-vue-next';

const props = defineProps<{
  draftData: HistoricalDraftData;
}>();

// Sub-view toggle: 'board' (Draft Board) | 'team' (By Team)
const activeSubView = ref<'board' | 'team'>('board');

// Filter state
const searchQuery = ref<string>('');
const selectedRound = ref<number | null>(null);
const onlyKeepers = ref<boolean>(false);
const onlyTraded = ref<boolean>(false);
const selectedPosition = ref<string | null>(null);

// Headshot error tracking
const failedHeadshots = ref<Set<number>>(new Set());

function handleImageError(playerId: number) {
  failedHeadshots.value.add(playerId);
}

// Position color mappings
function getPositionBadge(pos: string): string {
  switch ((pos || '').toUpperCase()) {
    case 'QB':
      return 'bg-amber-500/20 text-amber-300 border-amber-500/40';
    case 'RB':
      return 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40';
    case 'WR':
      return 'bg-sky-500/20 text-sky-300 border-sky-500/40';
    case 'TE':
      return 'bg-orange-500/20 text-orange-300 border-orange-500/40';
    case 'K':
      return 'bg-purple-500/20 text-purple-300 border-purple-500/40';
    case 'D/ST':
    case 'DST':
      return 'bg-teal-500/20 text-teal-300 border-teal-500/40';
    default:
      return 'bg-slate-800 text-slate-300 border-slate-700';
  }
}

// Quick position pill list
const positionOptions = ['QB', 'RB', 'WR', 'TE', 'K', 'D/ST'];

// Rounds list
const rounds = computed(() => props.draftData.rounds);

// Traded picks count
const tradedPicksCount = computed(() => {
  return props.draftData.picks.filter((p) => p.was_traded).length;
});

// Format draft date for stadium display
const formattedDraftDate = computed(() => {
  if (!props.draftData.draft_date) return null;
  try {
    const d = new Date(props.draftData.draft_date);
    return d.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return null;
  }
});

// Filter rounds and picks based on user input
const filteredRounds = computed(() => {
  const query = searchQuery.value.trim().toLowerCase();

  return rounds.value
    .filter((r) => {
      if (selectedRound.value !== null && r.round !== selectedRound.value) {
        return false;
      }
      return true;
    })
    .map((r) => {
      const picks = r.picks.filter((p) => {
        // Keeper filter
        if (onlyKeepers.value && !p.is_keeper) return false;

        // Traded filter
        if (onlyTraded.value && !p.was_traded) return false;

        // Position filter
        if (selectedPosition.value !== null) {
          const normPos = (p.player.default_position || '').toUpperCase();
          if (selectedPosition.value === 'D/ST') {
            if (normPos !== 'D/ST' && normPos !== 'DST') return false;
          } else if (normPos !== selectedPosition.value) {
            return false;
          }
        }

        // Text query search
        if (query) {
          const playerName = (p.player.full_name || '').toLowerCase();
          const teamName = (p.drafting_team.team_name || '').toLowerCase();
          const managerName = (p.drafting_team.manager_name || '').toLowerCase();
          const proTeam = (p.player.pro_team || '').toLowerCase();
          const pos = (p.player.default_position || '').toLowerCase();

          return (
            playerName.includes(query) ||
            teamName.includes(query) ||
            managerName.includes(query) ||
            proTeam.includes(query) ||
            pos.includes(query)
          );
        }

        return true;
      });

      return {
        round: r.round,
        picks,
      };
    })
    .filter((r) => r.picks.length > 0);
});

// Total picks matching current active search/filters
const totalVisiblePicksCount = computed(() => {
  return filteredRounds.value.reduce((acc, r) => acc + r.picks.length, 0);
});

// Teams summary list for By Team view
const teamsWithPicks = computed(() => props.draftData.by_team);

function selectRoundPill(r: number | null) {
  selectedRound.value = r;
}

function toggleKeepersOnly() {
  onlyKeepers.value = !onlyKeepers.value;
  if (onlyKeepers.value) {
    onlyTraded.value = false;
  }
}

function toggleTradedOnly() {
  onlyTraded.value = !onlyTraded.value;
  if (onlyTraded.value) {
    onlyKeepers.value = false;
  }
}

function togglePositionPill(pos: string) {
  if (selectedPosition.value === pos) {
    selectedPosition.value = null;
  } else {
    selectedPosition.value = pos;
  }
}

function clearAllFilters() {
  searchQuery.value = '';
  selectedRound.value = null;
  onlyKeepers.value = false;
  onlyTraded.value = false;
  selectedPosition.value = null;
}
</script>

<template>
  <div class="space-y-4">
    <!-- 1. Draft Overview Stats Card -->
    <div
      class="bg-gradient-to-r from-slate-900/90 via-slate-900/80 to-slate-950 border border-slate-800 rounded-2xl p-3.5 sm:p-4 text-xs shadow-lg space-y-3"
    >
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div class="flex items-center gap-2.5">
          <div class="w-9 h-9 rounded-xl bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center justify-center shrink-0">
            <Layers class="w-4 h-4" />
          </div>
          <div>
            <h2 class="text-base sm:text-lg font-black text-white tracking-tight">
              {{ draftData.season_year }} Draft Board
            </h2>
            <div class="flex items-center gap-2 text-slate-400 text-[11px] font-mono mt-0.5">
              <span>{{ draftData.league_size }} Teams</span>
              <span>·</span>
              <span>{{ draftData.total_rounds }} Rounds ({{ draftData.total_picks }} Picks)</span>
              <span>·</span>
              <span class="uppercase">{{ draftData.draft_type }}</span>
            </div>
          </div>
        </div>

        <div v-if="formattedDraftDate" class="flex items-center gap-1.5 text-slate-400 text-[11px] font-mono self-start sm:self-auto">
          <Calendar class="w-3.5 h-3.5 text-slate-500 shrink-0" />
          <span>{{ formattedDraftDate }}</span>
        </div>
      </div>

      <!-- Quick KPI Chips -->
      <div class="grid grid-cols-3 gap-2 pt-2 border-t border-slate-800/80">
        <div class="bg-slate-950/60 border border-slate-800/60 rounded-xl p-2 text-center">
          <div class="text-[10px] font-mono uppercase text-slate-400">Total Picks</div>
          <div class="text-sm sm:text-base font-black font-mono text-white mt-0.5">
            {{ draftData.total_picks }}
          </div>
        </div>

        <div class="bg-slate-950/60 border border-slate-800/60 rounded-xl p-2 text-center">
          <div class="text-[10px] font-mono uppercase text-amber-400 flex items-center justify-center gap-1">
            <Lock class="w-2.5 h-2.5" />
            <span>Keepers</span>
          </div>
          <div class="text-sm sm:text-base font-black font-mono text-amber-300 mt-0.5">
            {{ draftData.keeper_count }}
          </div>
        </div>

        <div class="bg-slate-950/60 border border-slate-800/60 rounded-xl p-2 text-center">
          <div class="text-[10px] font-mono uppercase text-slate-400">
            Traded Picks
          </div>
          <div class="text-sm sm:text-base font-black font-mono text-emerald-400 mt-0.5">
            {{ tradedPicksCount }}
          </div>
        </div>
      </div>
    </div>

    <!-- 2. Sub-Navigation Tabs (Draft Board vs By Team) -->
    <div class="flex items-center justify-between gap-2 border-b border-slate-800/80 pb-3">
      <div class="inline-flex rounded-xl bg-slate-900 p-1 border border-slate-800/80">
        <button
          type="button"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer min-h-[36px]"
          :class="
            activeSubView === 'board'
              ? 'bg-emerald-500 text-slate-950 shadow-sm'
              : 'text-slate-400 hover:text-white'
          "
          @click="activeSubView = 'board'"
        >
          <ListOrdered class="w-3.5 h-3.5" />
          <span>Draft Board</span>
        </button>

        <button
          type="button"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer min-h-[36px]"
          :class="
            activeSubView === 'team'
              ? 'bg-emerald-500 text-slate-950 shadow-sm'
              : 'text-slate-400 hover:text-white'
          "
          @click="activeSubView = 'team'"
        >
          <Users class="w-3.5 h-3.5" />
          <span>By Team</span>
        </button>
      </div>

      <div class="text-[11px] font-mono text-slate-400">
        <span v-if="activeSubView === 'board'">
          {{ totalVisiblePicksCount }} of {{ draftData.total_picks }}
        </span>
        <span v-else>
          {{ teamsWithPicks.length }} Rosters
        </span>
      </div>
    </div>

    <!-- ===================================================================== -->
    <!-- VIEW A: DRAFT BOARD                                                   -->
    <!-- ===================================================================== -->
    <div v-if="activeSubView === 'board'" class="space-y-4">
      <!-- Search & Filters Container -->
      <div class="space-y-2.5">
        <!-- Search Input -->
        <div class="relative">
          <Search class="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search by player, position, NFL team, or manager..."
            class="w-full bg-slate-900 border border-slate-800 focus:border-emerald-500/60 rounded-xl pl-9 pr-9 py-2 text-xs text-white placeholder-slate-500 focus:outline-none transition-colors"
          />
          <button
            v-if="searchQuery"
            type="button"
            class="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 p-1 cursor-pointer"
            aria-label="Clear search"
            @click="searchQuery = ''"
          >
            <X class="w-3.5 h-3.5" />
          </button>
        </div>

        <!-- Filter Row: Keepers, Traded, Position chips -->
        <div class="flex items-center gap-1.5 overflow-x-auto py-1 no-scrollbar select-none">
          <button
            type="button"
            class="px-2.5 py-1 rounded-lg text-xs font-mono font-bold transition-all border shrink-0 cursor-pointer min-h-[32px] flex items-center gap-1"
            :class="
              onlyKeepers
                ? 'bg-amber-500 text-slate-950 border-amber-400 shadow-sm'
                : 'bg-slate-900 text-slate-400 hover:text-amber-300 border-slate-800'
            "
            @click="toggleKeepersOnly"
          >
            <Lock class="w-3 h-3" />
            <span>Keepers ({{ draftData.keeper_count }})</span>
          </button>

          <button
            v-if="tradedPicksCount > 0"
            type="button"
            class="px-2.5 py-1 rounded-lg text-xs font-mono font-bold transition-all border shrink-0 cursor-pointer min-h-[32px] flex items-center gap-1"
            :class="
              onlyTraded
                ? 'bg-emerald-500 text-slate-950 border-emerald-400 shadow-sm'
                : 'bg-slate-900 text-slate-400 hover:text-white border-slate-800'
            "
            @click="toggleTradedOnly"
          >
            <span>Traded ({{ tradedPicksCount }})</span>
          </button>

          <div class="h-4 w-px bg-slate-800 mx-0.5 shrink-0"></div>

          <!-- Position Pills -->
          <button
            v-for="pos in positionOptions"
            :key="pos"
            type="button"
            class="px-2 py-1 rounded-lg text-xs font-mono font-bold transition-all border shrink-0 cursor-pointer min-h-[32px]"
            :class="
              selectedPosition === pos
                ? 'bg-emerald-500 text-slate-950 border-emerald-400 shadow-sm'
                : 'bg-slate-900 text-slate-400 hover:text-slate-200 border-slate-800'
            "
            @click="togglePositionPill(pos)"
          >
            {{ pos }}
          </button>

          <!-- Reset Filter if active -->
          <button
            v-if="searchQuery || selectedRound !== null || onlyKeepers || onlyTraded || selectedPosition !== null"
            type="button"
            class="px-2 py-1 rounded-lg text-xs font-mono text-rose-400 hover:bg-rose-950/30 border border-rose-500/30 shrink-0 cursor-pointer min-h-[32px] ml-auto"
            @click="clearAllFilters"
          >
            Reset All
          </button>
        </div>

        <!-- Round Carousel Pills -->
        <div class="flex items-center gap-1.5 overflow-x-auto py-1 no-scrollbar select-none">
          <button
            type="button"
            class="px-2.5 py-1 rounded-lg text-xs font-mono font-bold transition-all border shrink-0 cursor-pointer min-h-[32px]"
            :class="
              selectedRound === null
                ? 'bg-emerald-500 text-slate-950 border-emerald-400 shadow-sm'
                : 'bg-slate-900 text-slate-400 hover:text-slate-200 border-slate-800'
            "
            @click="selectRoundPill(null)"
          >
            All Rounds
          </button>

          <button
            v-for="r in draftData.total_rounds"
            :key="r"
            type="button"
            class="px-2.5 py-1 rounded-lg text-xs font-mono font-bold transition-all border shrink-0 flex items-center gap-1 cursor-pointer min-h-[32px]"
            :class="
              selectedRound === r
                ? 'bg-emerald-500 text-slate-950 border-emerald-400 shadow-sm'
                : 'bg-slate-900 text-slate-400 hover:text-slate-200 border-slate-800'
            "
            @click="selectRoundPill(r)"
          >
            <span>Rd {{ r }}</span>
            <span
              v-if="rounds[r - 1]?.picks.some((p) => p.is_keeper)"
              class="w-1.5 h-1.5 rounded-full bg-amber-400 shadow-[0_0_6px_#fbbf24]"
              title="Has Keeper"
            ></span>
            <span
              v-else-if="rounds[r - 1]?.picks.some((p) => p.was_traded)"
              class="w-1.5 h-1.5 rounded-full bg-violet-400 shadow-[0_0_6px_#a78bfa]"
              title="Has Traded Pick"
            ></span>
          </button>
        </div>
      </div>

      <!-- Empty State when filters yield no results -->
      <div
        v-if="filteredRounds.length === 0"
        class="py-12 text-center bg-slate-900/40 border border-slate-800/80 rounded-2xl p-6 space-y-2"
      >
        <div class="text-sm font-bold text-slate-300">No Draft Picks Found</div>
        <p class="text-xs text-slate-500 font-mono">
          Try clearing your search query or loosening round / position filters.
        </p>
        <button
          type="button"
          class="mt-3 px-3 py-1.5 rounded-lg text-xs font-bold bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors border border-slate-700 cursor-pointer"
          @click="clearAllFilters"
        >
          Reset All Filters
        </button>
      </div>

      <!-- Rounds List -->
      <div v-else class="space-y-6">
        <section
          v-for="roundObj in filteredRounds"
          :key="roundObj.round"
          class="bg-slate-900/60 border border-slate-800/90 rounded-2xl p-3 sm:p-4 space-y-3"
        >
          <!-- Round Header -->
          <div class="flex items-center justify-between border-b border-slate-800/80 pb-2">
            <div class="flex items-center gap-2">
              <span
                class="w-2 h-2 rounded-full"
                :class="
                  roundObj.round % 2 === 1
                    ? 'bg-emerald-400 shadow-[0_0_6px_#34d399]'
                    : 'bg-sky-400 shadow-[0_0_6px_#38bdf8]'
                "
              ></span>
              <h3 class="text-sm sm:text-base font-black text-white uppercase tracking-tight">
                Round {{ roundObj.round }}
              </h3>
            </div>

            <div class="text-[11px] font-mono text-slate-400 flex items-center gap-2">
              <span v-if="roundObj.picks.some((p) => p.is_keeper)" class="text-amber-400 font-bold">
                {{ roundObj.picks.filter((p) => p.is_keeper).length }} Keeper{{ roundObj.picks.filter((p) => p.is_keeper).length > 1 ? 's' : '' }}
              </span>
              <span v-if="roundObj.picks.some((p) => p.was_traded)" class="text-violet-400 font-bold">
                {{ roundObj.picks.filter((p) => p.was_traded).length }} Traded
              </span>
              <span class="text-slate-500">
                {{ roundObj.picks.length }} Pick{{ roundObj.picks.length > 1 ? 's' : '' }}
              </span>
            </div>
          </div>

          <!-- Picks Grid -->
          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
            <div
              v-for="pick in roundObj.picks"
              :key="pick.overall_pick"
              class="relative rounded-xl p-3 transition-all flex flex-col justify-between border"
              :class="
                pick.is_keeper
                  ? 'bg-gradient-to-r from-amber-950/25 via-slate-900/90 to-slate-900/90 border-amber-500/40 shadow-sm'
                  : pick.was_traded
                  ? 'bg-gradient-to-r from-violet-950/30 via-slate-900/90 to-slate-900/90 border-violet-500/40 shadow-sm'
                  : 'bg-slate-900/90 border-slate-800/90 hover:border-slate-700'
              "
            >
              <!-- Top Row: Pick Badge & Drafting Team -->
              <div class="flex items-start justify-between gap-2">
                <div class="flex items-center gap-2 min-w-0">
                  <!-- Pick Badge -->
                  <div
                    class="font-mono px-2 py-0.5 rounded-md text-xs font-black tracking-tight shrink-0 border"
                    :class="
                      pick.is_keeper
                        ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                        : pick.was_traded
                        ? 'bg-violet-500/20 text-violet-300 border-violet-500/40'
                        : 'bg-slate-950 text-emerald-400 border-slate-800'
                    "
                  >
                    <span>{{ pick.round }}.{{ String(pick.round_pick).padStart(2, '0') }}</span>
                    <span class="text-[10px] text-slate-400 font-normal ml-1">#{{ pick.overall_pick }}</span>
                  </div>

                  <!-- Drafting Franchise Ref -->
                  <div class="flex items-center gap-1.5 min-w-0">
                    <TeamAvatar
                      :src="pick.drafting_team.logo_url"
                      :name="pick.drafting_team.team_name"
                      size="xs"
                      rounded="lg"
                    />
                    <div class="min-w-0 leading-tight">
                      <div class="text-xs font-bold text-white truncate">
                        {{ pick.drafting_team.team_name }}
                      </div>
                      <div class="text-[10px] text-slate-400 truncate">
                        {{ pick.drafting_team.manager_name }}
                      </div>
                    </div>
                  </div>
                </div>

                <!-- Status Badges: Keeper, Traded, Bid -->
                <div class="flex items-center gap-1 shrink-0">
                  <span
                    v-if="pick.is_keeper"
                    class="inline-flex items-center gap-0.5 text-[9px] font-mono font-bold uppercase px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40"
                    title="Player kept from previous season"
                  >
                    <Lock class="w-2.5 h-2.5" />
                    <span>Keeper</span>
                  </span>

                  <span
                    v-if="pick.was_traded"
                    class="inline-block text-[9px] font-mono font-bold uppercase px-1.5 py-0.2 rounded bg-slate-800 text-slate-200 border border-slate-700"
                    :title="`Traded pick originally owned by ${pick.original_team?.manager_name || pick.original_team?.team_name || 'other team'}`"
                  >
                    Traded
                  </span>

                  <span
                    v-if="pick.bid_amount > 0"
                    class="text-[9.5px] font-mono font-bold px-1.5 py-0.2 rounded bg-emerald-950/60 text-emerald-400 border border-emerald-500/30"
                  >
                    ${{ pick.bid_amount }}
                  </span>
                </div>
              </div>

              <!-- Bottom Row: Player Info & Headshot -->
              <div class="mt-2.5 pt-2 border-t border-slate-800/80 flex items-center justify-between gap-2">
                <div class="flex items-center gap-2.5 min-w-0">
                  <!-- Headshot with graceful error fallback -->
                  <div class="relative shrink-0">
                    <img
                      v-if="pick.player.headshot_url && !failedHeadshots.has(pick.player.player_id)"
                      :src="pick.player.headshot_url"
                      :alt="pick.player.full_name"
                      class="w-9 h-9 rounded-full object-cover bg-slate-800 border border-slate-700"
                      loading="lazy"
                      @error="handleImageError(pick.player.player_id)"
                    />
                    <div
                      v-else
                      class="w-9 h-9 rounded-full flex items-center justify-center font-mono font-black text-xs border border-slate-700"
                      :class="getPositionBadge(pick.player.default_position)"
                    >
                      {{ pick.player.default_position }}
                    </div>
                  </div>

                  <!-- Player Name, Position, Pro Team -->
                  <div class="min-w-0 leading-tight">
                    <div class="text-xs sm:text-sm font-black text-slate-100 truncate tracking-tight">
                      {{ pick.player.full_name }}
                    </div>
                    <div class="flex items-center gap-1.5 mt-0.5">
                      <span
                        class="text-[9.5px] font-mono font-black uppercase px-1.5 py-0.2 rounded border"
                        :class="getPositionBadge(pick.player.default_position)"
                      >
                        {{ pick.player.default_position }}
                      </span>
                      <span class="text-[10px] font-mono font-semibold text-slate-400">
                        {{ pick.player.pro_team }}
                      </span>
                    </div>
                  </div>
                </div>

                <!-- Traded Pick Origin Pill if applicable -->
                <div
                  v-if="pick.was_traded && pick.original_team"
                  class="text-right shrink-0"
                >
                  <div class="text-[9px] font-mono text-slate-500 uppercase">Original Pick</div>
                  <div class="text-[10px] font-medium text-violet-300 truncate max-w-[100px]">
                    {{ pick.original_team.manager_name || pick.original_team.team_name }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>

    <!-- ===================================================================== -->
    <!-- VIEW B: BY TEAM (DRAFTED ROSTERS)                                     -->
    <!-- ===================================================================== -->
    <div v-else class="space-y-4">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3.5">
        <div
          v-for="teamItem in teamsWithPicks"
          :key="teamItem.team_id"
          class="bg-slate-900/80 border border-slate-800 rounded-2xl p-3.5 sm:p-4 space-y-3 shadow-md"
        >
          <!-- Team Header -->
          <div class="flex items-center justify-between gap-2 border-b border-slate-800/80 pb-2.5">
            <div class="flex items-center gap-2.5 min-w-0">
              <TeamAvatar
                :src="teamItem.logo_url"
                :name="teamItem.team_name"
                size="md"
                rounded="xl"
              />
              <div class="min-w-0 leading-tight">
                <div class="text-sm font-bold text-white truncate">
                  {{ teamItem.team_name }}
                </div>
                <div class="text-xs text-slate-400 truncate">
                  {{ teamItem.manager_name }}
                </div>
              </div>
            </div>

            <!-- Total Picks & Keepers -->
            <div class="text-right shrink-0">
              <div class="text-sm sm:text-base font-black font-mono text-white">
                {{ teamItem.total_picks }} <span class="text-[10px] text-slate-500">Picks</span>
              </div>
              <div v-if="teamItem.keepers_count > 0" class="text-[10.5px] font-mono text-amber-400">
                {{ teamItem.keepers_count }} Keeper{{ teamItem.keepers_count > 1 ? 's' : '' }}
              </div>
            </div>
          </div>

          <!-- Roster Picks Table / List -->
          <div class="space-y-1.5 max-h-[380px] overflow-y-auto pr-1 no-scrollbar">
            <div
              v-for="pick in teamItem.picks"
              :key="pick.overall_pick"
              class="flex items-center justify-between gap-2 p-1.5 rounded-lg text-xs font-mono transition-colors border"
              :class="
                pick.is_keeper
                  ? 'bg-amber-950/20 border-amber-500/30'
                  : pick.was_traded
                  ? 'bg-violet-950/20 border-violet-500/30'
                  : 'bg-slate-950/60 border-slate-800/60 hover:border-slate-700'
              "
            >
              <!-- Pick round & overall badge -->
              <div class="flex items-center gap-2 min-w-0">
                <span class="text-[11px] font-bold text-slate-400 shrink-0 w-10">
                  {{ pick.round }}.{{ String(pick.round_pick).padStart(2, '0') }}
                </span>

                <span
                  class="text-[9px] font-mono font-black uppercase px-1 py-0.2 rounded border shrink-0"
                  :class="getPositionBadge(pick.player.default_position)"
                >
                  {{ pick.player.default_position }}
                </span>

                <span class="text-xs font-bold text-slate-200 truncate font-sans">
                  {{ pick.player.full_name }}
                </span>

                <span class="text-[10px] text-slate-500 shrink-0">
                  {{ pick.player.pro_team }}
                </span>
              </div>

              <!-- Keeper / Traded tag -->
              <div class="flex items-center gap-1 shrink-0">
                <span
                  v-if="pick.is_keeper"
                  class="text-[9px] font-mono font-bold text-amber-300 bg-amber-500/20 px-1.5 py-0.2 rounded border border-amber-500/40 uppercase"
                >
                  Keeper
                </span>

                <span
                  v-if="pick.was_traded"
                  class="text-[9px] font-mono font-bold text-violet-300 bg-violet-500/20 px-1.5 py-0.2 rounded border border-violet-500/40 uppercase"
                  :title="`Traded from ${pick.original_team?.manager_name || 'other team'}`"
                >
                  Traded
                </span>
              </div>
            </div>
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
</style>
