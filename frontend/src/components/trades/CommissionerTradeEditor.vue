<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import type { TradeDetail } from '@/types/api';
import {
  verifyTradeAdminPassword,
  fetchTradeAdminOptions,
  updateTradeAdmin,
  createTradeAdmin,
  deleteTradeAdmin,
  restoreTradeAdmin,
  type TradeAdminOptionsResponse,
  type TradeAdminPlayerOption,
  type TradeAdminDraftPickInput,
  type TradeAdminUpdatePayload,
  type TradeAdminCreatePayload,
} from '@/api/client';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import {
  Lock,
  Unlock,
  ShieldCheck,
  AlertCircle,
  CheckCircle2,
  Trash2,
  Plus,
  RotateCcw,
  Edit3,
  X,
  Search,
  Ticket,
  Coins,
  Calendar,
  Layers,
} from 'lucide-vue-next';

const props = defineProps<{
  trades: TradeDetail[];
  initialTradeToEdit?: TradeDetail | null;
}>();

const emit = defineEmits<{
  (e: 'updated'): void;
}>();

// Authentication State
const password = ref<string>('');
const enteredPassword = ref<string>('');
const isAuthenticated = ref<boolean>(false);
const authLoading = ref<boolean>(false);
const authError = ref<string | null>(null);

// Admin Options
const adminOptions = ref<TradeAdminOptionsResponse | null>(null);
const optionsLoading = ref<boolean>(false);
const feedbackMessage = ref<{ type: 'success' | 'error'; text: string } | null>(null);

// View Modes: 'list' | 'editor' | 'deleted'
const activeTab = ref<'list' | 'deleted'>('list');
const isEditorOpen = ref<boolean>(false);
const isCreatingNew = ref<boolean>(false);

// Search / Filter inside Commissioner Panel
const listSearchQuery = ref<string>('');
const listSeasonFilter = ref<number | null>(null);

// Form State for Bilateral Trade Editing
interface FormSideState {
  team_id: number | null;
  players: TradeAdminPlayerOption[];
  draft_picks: TradeAdminDraftPickInput[];
  faab_received: number;
  playerSearch: string;
  newPickYear: number;
  newPickRound: number;
  newPickNumber: number | null;
}

const formTradeId = ref<number | null>(null);
const formSeasonYear = ref<number>(new Date().getFullYear());
const formWeek = ref<number>(1);
const formSubmitting = ref<boolean>(false);
const formValidation = ref<string | null>(null);

const sideA = ref<FormSideState>({
  team_id: null,
  players: [],
  draft_picks: [],
  faab_received: 0,
  playerSearch: '',
  newPickYear: new Date().getFullYear(),
  newPickRound: 1,
  newPickNumber: null,
});

const sideB = ref<FormSideState>({
  team_id: null,
  players: [],
  draft_picks: [],
  faab_received: 0,
  playerSearch: '',
  newPickYear: new Date().getFullYear(),
  newPickRound: 1,
  newPickNumber: null,
});

// Load session password on mount
onMounted(async () => {
  const saved = sessionStorage.getItem('ff_trade_admin_password');
  if (saved) {
    enteredPassword.value = saved;
    await handleAuthenticate();
  }
});

async function handleAuthenticate() {
  if (!enteredPassword.value.trim()) {
    authError.value = 'Please enter commissioner password';
    return;
  }
  authLoading.value = true;
  authError.value = null;
  try {
    const res = await verifyTradeAdminPassword(enteredPassword.value);
    if (res.authenticated) {
      password.value = enteredPassword.value;
      sessionStorage.setItem('ff_trade_admin_password', password.value);
      isAuthenticated.value = true;
      await loadAdminOptions();
      if (props.initialTradeToEdit) {
        startEditTrade(props.initialTradeToEdit);
      }
    } else {
      authError.value = 'Incorrect commissioner password';
    }
  } catch (err: unknown) {
    authError.value = err instanceof Error ? err.message : 'Authentication failed';
  } finally {
    authLoading.value = false;
  }
}

function handleLockSession() {
  sessionStorage.removeItem('ff_trade_admin_password');
  password.value = '';
  enteredPassword.value = '';
  isAuthenticated.value = false;
  adminOptions.value = null;
  isEditorOpen.value = false;
}

async function loadAdminOptions() {
  if (!password.value) return;
  optionsLoading.value = true;
  try {
    adminOptions.value = await fetchTradeAdminOptions(password.value);
  } catch (err: unknown) {
    showFeedback('error', err instanceof Error ? err.message : 'Failed to load options');
  } finally {
    optionsLoading.value = false;
  }
}

function showFeedback(type: 'success' | 'error', text: string) {
  feedbackMessage.value = { type, text };
  setTimeout(() => {
    if (feedbackMessage.value?.text === text) {
      feedbackMessage.value = null;
    }
  }, 4500);
}

// Available teams for selected form season
const availableSeasonTeams = computed(() => {
  if (!adminOptions.value) return [];
  const year = formSeasonYear.value;
  const filtered = adminOptions.value.teams.filter((t) => t.season_year === year);
  if (filtered.length > 0) return filtered;
  // fallback to all unique teams
  const seen = new Set<number>();
  return adminOptions.value.teams.filter((t) => {
    if (seen.has(t.team_id)) return false;
    seen.add(t.team_id);
    return true;
  });
});

// Watch initialTradeToEdit prop
watch(
  () => props.initialTradeToEdit,
  (trade) => {
    if (trade && isAuthenticated.value) {
      startEditTrade(trade);
    }
  }
);

function startCreateTrade() {
  isCreatingNew.value = true;
  isEditorOpen.value = true;
  formTradeId.value = null;
  formSeasonYear.value = adminOptions.value?.seasons[0] ?? new Date().getFullYear();
  formWeek.value = 1;
  formValidation.value = null;

  sideA.value = {
    team_id: availableSeasonTeams.value[0]?.team_id ?? null,
    players: [],
    draft_picks: [],
    faab_received: 0,
    playerSearch: '',
    newPickYear: formSeasonYear.value + 1,
    newPickRound: 1,
    newPickNumber: null,
  };

  sideB.value = {
    team_id: availableSeasonTeams.value[1]?.team_id ?? null,
    players: [],
    draft_picks: [],
    faab_received: 0,
    playerSearch: '',
    newPickYear: formSeasonYear.value + 1,
    newPickRound: 1,
    newPickNumber: null,
  };
}

function startEditTrade(trade: TradeDetail) {
  isCreatingNew.value = false;
  isEditorOpen.value = true;
  formTradeId.value = trade.trade_id;
  formSeasonYear.value = trade.season_year;
  formWeek.value = trade.week ?? 0;
  formValidation.value = null;

  const rawSideA = trade.sides[0];
  const rawSideB = trade.sides[1];

  sideA.value = {
    team_id: rawSideA?.team_id ?? null,
    players: (rawSideA?.assets_received ?? [])
      .filter((a) => a.asset_type === 'PLAYER')
      .map((a) => ({
        player_id: a.player_id,
        full_name: a.full_name,
        default_position: a.default_position,
        pro_team: a.pro_team,
        headshot_url: a.headshot_url,
      })),
    draft_picks: (rawSideA?.assets_received ?? [])
      .filter((a) => a.asset_type === 'PICK')
      .map((a) => ({
        season_year: trade.season_year,
        round: a.pick_round ?? 1,
        pick_number: a.pick_number ?? null,
      })),
    faab_received: rawSideA?.faab_received ?? 0,
    playerSearch: '',
    newPickYear: trade.season_year + 1,
    newPickRound: 1,
    newPickNumber: null,
  };

  sideB.value = {
    team_id: rawSideB?.team_id ?? null,
    players: (rawSideB?.assets_received ?? [])
      .filter((a) => a.asset_type === 'PLAYER')
      .map((a) => ({
        player_id: a.player_id,
        full_name: a.full_name,
        default_position: a.default_position,
        pro_team: a.pro_team,
        headshot_url: a.headshot_url,
      })),
    draft_picks: (rawSideB?.assets_received ?? [])
      .filter((a) => a.asset_type === 'PICK')
      .map((a) => ({
        season_year: trade.season_year,
        round: a.pick_round ?? 1,
        pick_number: a.pick_number ?? null,
      })),
    faab_received: rawSideB?.faab_received ?? 0,
    playerSearch: '',
    newPickYear: trade.season_year + 1,
    newPickRound: 1,
    newPickNumber: null,
  };
}

function cancelEditor() {
  isEditorOpen.value = false;
  formTradeId.value = null;
  formValidation.value = null;
}

// Player search results per side
function getFilteredPlayers(side: FormSideState): TradeAdminPlayerOption[] {
  if (!adminOptions.value) return [];
  const q = side.playerSearch.trim().toLowerCase();
  if (!q) return [];

  const existingIds = new Set<number>([
    ...sideA.value.players.map((p) => p.player_id),
    ...sideB.value.players.map((p) => p.player_id),
  ]);

  return adminOptions.value.players
    .filter((p) => {
      if (existingIds.has(p.player_id)) return false;
      return (
        p.full_name.toLowerCase().includes(q) ||
        p.pro_team.toLowerCase().includes(q) ||
        p.default_position.toLowerCase().includes(q)
      );
    })
    .slice(0, 8);
}

function addPlayerToSide(side: FormSideState, player: TradeAdminPlayerOption) {
  side.players.push(player);
  side.playerSearch = '';
}

function removePlayerFromSide(side: FormSideState, playerId: number) {
  side.players = side.players.filter((p) => p.player_id !== playerId);
}

function addDraftPickToSide(side: FormSideState) {
  side.draft_picks.push({
    season_year: side.newPickYear,
    round: side.newPickRound,
    pick_number: side.newPickNumber || null,
  });
  side.newPickNumber = null;
}

function removeDraftPickFromSide(side: FormSideState, index: number) {
  side.draft_picks.splice(index, 1);
}

async function handleSaveTrade() {
  formValidation.value = null;

  if (!sideA.value.team_id || !sideB.value.team_id) {
    formValidation.value = 'Both Side A and Side B must have a team selected.';
    return;
  }

  if (sideA.value.team_id === sideB.value.team_id) {
    formValidation.value = 'Side A and Side B cannot be the same franchise.';
    return;
  }

  const hasAssets =
    sideA.value.players.length > 0 ||
    sideA.value.draft_picks.length > 0 ||
    sideA.value.faab_received > 0 ||
    sideB.value.players.length > 0 ||
    sideB.value.draft_picks.length > 0 ||
    sideB.value.faab_received > 0;

  if (!hasAssets) {
    formValidation.value = 'At least one asset (player, draft pick, or FAAB) must be traded.';
    return;
  }

  formSubmitting.value = true;
  try {
    if (isCreatingNew.value) {
      const payload: TradeAdminCreatePayload = {
        season_year: formSeasonYear.value,
        week: formWeek.value,
        sides: [
          {
            team_id: sideA.value.team_id,
            player_ids: sideA.value.players.map((p) => p.player_id),
            draft_picks: sideA.value.draft_picks,
            faab_received: Number(sideA.value.faab_received) || 0,
          },
          {
            team_id: sideB.value.team_id,
            player_ids: sideB.value.players.map((p) => p.player_id),
            draft_picks: sideB.value.draft_picks,
            faab_received: Number(sideB.value.faab_received) || 0,
          },
        ],
      };
      await createTradeAdmin(password.value, payload);
      showFeedback('success', 'Manual trade successfully created and evaluated!');
    } else {
      const payload: TradeAdminUpdatePayload = {
        week: formWeek.value,
        sides: [
          {
            team_id: sideA.value.team_id,
            player_ids: sideA.value.players.map((p) => p.player_id),
            draft_picks: sideA.value.draft_picks,
            faab_received: Number(sideA.value.faab_received) || 0,
          },
          {
            team_id: sideB.value.team_id,
            player_ids: sideB.value.players.map((p) => p.player_id),
            draft_picks: sideB.value.draft_picks,
            faab_received: Number(sideB.value.faab_received) || 0,
          },
        ],
      };
      await updateTradeAdmin(password.value, formTradeId.value!, payload);
      showFeedback('success', 'Trade successfully updated and recalculations applied!');
    }

    isEditorOpen.value = false;
    await loadAdminOptions();
    emit('updated');
  } catch (err: unknown) {
    formValidation.value = err instanceof Error ? err.message : 'Failed to save trade changes';
  } finally {
    formSubmitting.value = false;
  }
}

async function handleDeleteTrade(tradeId: number) {
  if (!confirm('Are you sure you want to soft-delete this trade? It can be restored at any time.')) {
    return;
  }
  try {
    await deleteTradeAdmin(password.value, tradeId);
    showFeedback('success', `Trade #${tradeId} deleted.`);
    if (isEditorOpen.value && formTradeId.value === tradeId) {
      isEditorOpen.value = false;
    }
    await loadAdminOptions();
    emit('updated');
  } catch (err: unknown) {
    showFeedback('error', err instanceof Error ? err.message : 'Failed to delete trade');
  }
}

async function handleRestoreTrade(tradeId: number) {
  try {
    await restoreTradeAdmin(password.value, tradeId);
    showFeedback('success', `Trade #${tradeId} restored.`);
    await loadAdminOptions();
    emit('updated');
  } catch (err: unknown) {
    showFeedback('error', err instanceof Error ? err.message : 'Failed to restore trade');
  }
}

// Filtered trades list in manager view
const filteredExistingTrades = computed(() => {
  const q = listSearchQuery.value.trim().toLowerCase();
  return props.trades.filter((trade) => {
    if (listSeasonFilter.value !== null && trade.season_year !== listSeasonFilter.value) {
      return false;
    }
    if (!q) return true;
    const matchManager = trade.sides.some(
      (s) =>
        s.manager_name.toLowerCase().includes(q) ||
        s.team_name.toLowerCase().includes(q)
    );
    if (matchManager) return true;
    const matchPlayer = trade.sides.some((s) =>
      s.assets_received.some((a) => a.full_name.toLowerCase().includes(q))
    );
    return matchPlayer;
  });
});
</script>

<template>
  <div class="space-y-4">
    <!-- Feedback Banner -->
    <transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="opacity-0 -translate-y-1"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition duration-150 ease-in"
      leave-from-class="opacity-100 translate-y-0"
      leave-to-class="opacity-0 -translate-y-1"
    >
      <div
        v-if="feedbackMessage"
        class="px-4 py-2.5 rounded-xl text-xs font-semibold flex items-center justify-between gap-2 border shadow-lg"
        :class="
          feedbackMessage.type === 'success'
            ? 'bg-emerald-950/80 text-emerald-300 border-emerald-500/40'
            : 'bg-rose-950/80 text-rose-300 border-rose-500/40'
        "
      >
        <div class="flex items-center gap-2">
          <CheckCircle2 v-if="feedbackMessage.type === 'success'" class="w-4 h-4 text-emerald-400" />
          <AlertCircle v-else class="w-4 h-4 text-rose-400" />
          <span>{{ feedbackMessage.text }}</span>
        </div>
        <button
          type="button"
          class="text-slate-400 hover:text-slate-200 cursor-pointer"
          @click="feedbackMessage = null"
        >
          <X class="w-4 h-4" />
        </button>
      </div>
    </transition>

    <!-- STATE 1: LOCKED COMMISSIONER CARD -->
    <div
      v-if="!isAuthenticated"
      class="stadium-card rounded-2xl p-6 sm:p-8 border border-slate-800 bg-slate-900/90 max-w-lg mx-auto text-center space-y-4 shadow-2xl"
    >
      <div class="w-14 h-14 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-amber-400 flex items-center justify-center mx-auto shadow-inner">
        <Lock class="w-7 h-7" />
      </div>

      <div class="space-y-1.5">
        <h3 class="text-lg font-black text-slate-100 uppercase tracking-tight">
          Commissioner Trade Desk
        </h3>
        <p class="text-xs text-slate-400 max-w-sm mx-auto">
          Authenticate with commissioner access to modify historical trades, log off-platform deals, or record future draft pick exchanges.
        </p>
      </div>

      <form class="space-y-3 max-w-xs mx-auto pt-2" @submit.prevent="handleAuthenticate">
        <div>
          <input
            v-model="enteredPassword"
            type="password"
            placeholder="Enter commissioner password..."
            class="w-full bg-slate-950/90 border border-slate-800 rounded-xl px-3.5 py-2.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors text-center"
            :disabled="authLoading"
          />
        </div>

        <div v-if="authError" class="text-xs text-rose-400 font-medium">
          {{ authError }}
        </div>

        <button
          type="submit"
          class="w-full py-2.5 px-4 rounded-xl font-bold text-xs uppercase tracking-wide bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg transition-colors flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
          :disabled="authLoading"
        >
          <Unlock v-if="!authLoading" class="w-3.5 h-3.5" />
          <span>{{ authLoading ? 'Verifying...' : 'Unlock Trade Editor' }}</span>
        </button>
      </form>
    </div>

    <!-- STATE 2: UNLOCKED COMMISSIONER WORKSPACE -->
    <div v-else class="space-y-4">
      <!-- Commissioner Top Bar -->
      <div class="stadium-card rounded-2xl px-4 py-3 border border-slate-800 bg-slate-900/90 flex items-center justify-between gap-3 flex-wrap shadow-md">
        <div class="flex items-center gap-2.5">
          <div class="w-8 h-8 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 flex items-center justify-center">
            <ShieldCheck class="w-4 h-4" />
          </div>
          <div>
            <div class="flex items-center gap-2">
              <span class="text-sm font-bold uppercase tracking-tight text-slate-100">
                Commissioner Trade Desk
              </span>
              <span class="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                Unlocked
              </span>
            </div>
            <p class="text-[11px] text-slate-400">
              Bilateral trade editor, manual backfill & draft pick exchange controls
            </p>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <button
            type="button"
            class="px-3 py-1.5 rounded-lg text-xs font-bold uppercase bg-indigo-600 hover:bg-indigo-500 text-white flex items-center gap-1.5 shadow-sm transition-colors cursor-pointer"
            @click="startCreateTrade"
          >
            <Plus class="w-3.5 h-3.5" />
            <span>New Manual Trade</span>
          </button>

          <button
            type="button"
            class="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 bg-slate-800 hover:bg-slate-700/80 transition-colors flex items-center gap-1 cursor-pointer"
            @click="handleLockSession"
          >
            <Lock class="w-3.5 h-3.5" />
            <span>Lock</span>
          </button>
        </div>
      </div>

      <!-- BILATERAL TRADE EDITOR MODAL / FORM (Shown when editing or creating) -->
      <div
        v-if="isEditorOpen"
        class="stadium-card rounded-2xl p-5 border border-indigo-500/50 bg-slate-900/95 space-y-5 shadow-2xl"
      >
        <!-- Editor Header -->
        <div class="flex items-center justify-between border-b border-slate-800 pb-3 flex-wrap gap-2">
          <div class="flex items-center gap-2">
            <div class="w-7 h-7 rounded-lg bg-indigo-500/20 text-indigo-400 flex items-center justify-center">
              <Edit3 class="w-4 h-4" />
            </div>
            <h4 class="text-sm font-black uppercase tracking-tight text-slate-100">
              {{ isCreatingNew ? 'Create New Manual Trade' : `Edit Trade #${formTradeId}` }}
            </h4>
          </div>

          <div class="flex items-center gap-3">
            <!-- Season Year (Editable only on create) -->
            <div class="flex items-center gap-1.5 text-xs font-mono">
              <span class="text-slate-400">Season:</span>
              <select
                v-if="isCreatingNew"
                v-model.number="formSeasonYear"
                class="bg-slate-950 border border-slate-800 rounded-lg px-2 py-1 text-slate-200 text-xs focus:outline-none focus:border-indigo-500"
              >
                <option v-for="s in adminOptions?.seasons ?? [formSeasonYear]" :key="s" :value="s">
                  {{ s }}
                </option>
              </select>
              <span v-else class="font-bold text-slate-200 bg-slate-800 px-2 py-0.5 rounded">
                {{ formSeasonYear }}
              </span>
            </div>

            <!-- Week -->
            <div class="flex items-center gap-1.5 text-xs font-mono">
              <span class="text-slate-400">Week:</span>
              <select
                v-model.number="formWeek"
                class="bg-slate-950 border border-slate-800 rounded-lg px-2 py-1 text-slate-200 text-xs focus:outline-none focus:border-indigo-500"
              >
                <option :value="0">0 (Preseason / Draft)</option>
                <option v-for="w in 18" :key="w" :value="w">Wk {{ w }}</option>
              </select>
            </div>

            <button
              type="button"
              class="text-slate-400 hover:text-slate-200 p-1 cursor-pointer"
              @click="cancelEditor"
            >
              <X class="w-4 h-4" />
            </button>
          </div>
        </div>

        <!-- Validation Alert -->
        <div
          v-if="formValidation"
          class="p-3 rounded-xl bg-rose-950/80 border border-rose-500/40 text-rose-300 text-xs flex items-center gap-2"
        >
          <AlertCircle class="w-4 h-4 text-rose-400 shrink-0" />
          <span>{{ formValidation }}</span>
        </div>

        <!-- Two Bilateral Sides -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <!-- SIDE A -->
          <div class="space-y-4 p-4 rounded-xl bg-slate-950/60 border border-slate-800">
            <div class="flex items-center justify-between border-b border-slate-800/80 pb-2.5">
              <span class="text-xs font-black uppercase tracking-wider text-indigo-400">
                Side A (Receiving)
              </span>
            </div>

            <!-- Team Selector -->
            <div class="space-y-1">
              <label class="text-[11px] font-semibold text-slate-400">Franchise:</label>
              <select
                v-model="sideA.team_id"
                class="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
              >
                <option :value="null">-- Select Team --</option>
                <option
                  v-for="t in availableSeasonTeams"
                  :key="t.team_id"
                  :value="t.team_id"
                  :disabled="t.team_id === sideB.team_id"
                >
                  {{ t.team_name }} ({{ t.manager_name }})
                </option>
              </select>
            </div>

            <!-- Players Received by Side A -->
            <div class="space-y-2">
              <div class="flex items-center justify-between text-[11px] font-semibold text-slate-400">
                <span>Players Received ({{ sideA.players.length }})</span>
              </div>

              <!-- List of attached players -->
              <div class="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                <div
                  v-for="player in sideA.players"
                  :key="player.player_id"
                  class="flex items-center justify-between gap-2 p-2 rounded-lg bg-slate-900/90 border border-slate-800 text-xs"
                >
                  <div class="flex items-center gap-2 min-w-0">
                    <span class="px-1.5 py-0.2 rounded text-[10px] font-mono font-bold bg-slate-800 text-slate-300">
                      {{ player.default_position }}
                    </span>
                    <span class="font-bold text-slate-200 truncate">{{ player.full_name }}</span>
                    <span class="text-[10px] text-slate-400 font-mono">{{ player.pro_team }}</span>
                  </div>
                  <button
                    type="button"
                    class="text-rose-400 hover:text-rose-300 p-1 cursor-pointer"
                    title="Remove player"
                    @click="removePlayerFromSide(sideA, player.player_id)"
                  >
                    <X class="w-3.5 h-3.5" />
                  </button>
                </div>
                <div v-if="sideA.players.length === 0" class="text-xs text-slate-500 italic py-1 text-center">
                  No players attached
                </div>
              </div>

              <!-- Add Player Search Input -->
              <div class="relative pt-1">
                <Search class="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2 mt-0.5" />
                <input
                  v-model="sideA.playerSearch"
                  type="text"
                  placeholder="Search player to add to Side A..."
                  class="w-full bg-slate-900 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
                <!-- Search Suggestions Dropdown -->
                <div
                  v-if="sideA.playerSearch.trim() && getFilteredPlayers(sideA).length > 0"
                  class="absolute left-0 right-0 top-full mt-1 bg-slate-900 border border-slate-700 rounded-xl shadow-xl z-20 max-h-48 overflow-y-auto divide-y divide-slate-800"
                >
                  <button
                    v-for="p in getFilteredPlayers(sideA)"
                    :key="p.player_id"
                    type="button"
                    class="w-full px-3 py-2 text-left flex items-center justify-between text-xs hover:bg-slate-800 cursor-pointer"
                    @click="addPlayerToSide(sideA, p)"
                  >
                    <div class="flex items-center gap-2">
                      <span class="px-1.5 py-0.2 rounded text-[10px] font-mono font-bold bg-slate-800 text-slate-300">
                        {{ p.default_position }}
                      </span>
                      <span class="font-bold text-slate-200">{{ p.full_name }}</span>
                    </div>
                    <span class="text-[10px] text-slate-400 font-mono">{{ p.pro_team }}</span>
                  </button>
                </div>
              </div>
            </div>

            <!-- Draft Picks Received by Side A -->
            <div class="space-y-2 pt-2 border-t border-slate-800/80">
              <div class="text-[11px] font-semibold text-slate-400 flex items-center justify-between">
                <span>Draft Picks Received ({{ sideA.draft_picks.length }})</span>
              </div>

              <!-- Attached Picks List -->
              <div class="flex flex-wrap gap-1.5">
                <div
                  v-for="(pick, pIdx) in sideA.draft_picks"
                  :key="pIdx"
                  class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-violet-950/40 text-violet-300 border border-violet-500/30 text-xs font-mono"
                >
                  <Ticket class="w-3 h-3 text-violet-400" />
                  <span>{{ pick.season_year || formSeasonYear }} Rd {{ pick.round }}{{ pick.pick_number ? ` (#${pick.pick_number})` : '' }}</span>
                  <button
                    type="button"
                    class="text-rose-400 hover:text-rose-300 ml-1 cursor-pointer"
                    @click="removeDraftPickFromSide(sideA, pIdx)"
                  >
                    <X class="w-3 h-3" />
                  </button>
                </div>
              </div>

              <!-- Inline Add Pick Controls -->
              <div class="bg-slate-900/90 rounded-lg p-2 border border-slate-800/80 grid grid-cols-4 gap-1.5 text-xs">
                <div>
                  <label class="text-[9px] text-slate-500 uppercase font-mono">Year</label>
                  <input
                    v-model.number="sideA.newPickYear"
                    type="number"
                    class="w-full bg-slate-950 border border-slate-800 rounded px-1.5 py-1 text-slate-200 text-xs font-mono"
                  />
                </div>
                <div>
                  <label class="text-[9px] text-slate-500 uppercase font-mono">Round</label>
                  <select
                    v-model.number="sideA.newPickRound"
                    class="w-full bg-slate-950 border border-slate-800 rounded px-1.5 py-1 text-slate-200 text-xs font-mono"
                  >
                    <option v-for="r in 16" :key="r" :value="r">Rd {{ r }}</option>
                  </select>
                </div>
                <div>
                  <label class="text-[9px] text-slate-500 uppercase font-mono">Pick # (opt)</label>
                  <input
                    v-model.number="sideA.newPickNumber"
                    type="number"
                    placeholder="e.g. 57"
                    class="w-full bg-slate-950 border border-slate-800 rounded px-1.5 py-1 text-slate-200 text-xs font-mono"
                  />
                </div>
                <div class="flex items-end">
                  <button
                    type="button"
                    class="w-full py-1 rounded bg-violet-600 hover:bg-violet-500 text-white font-bold text-xs uppercase transition-colors cursor-pointer"
                    @click="addDraftPickToSide(sideA)"
                  >
                    + Pick
                  </button>
                </div>
              </div>
            </div>

            <!-- FAAB Received by Side A -->
            <div class="space-y-1 pt-2 border-t border-slate-800/80">
              <label class="text-[11px] font-semibold text-slate-400 flex items-center gap-1">
                <Coins class="w-3 h-3 text-amber-400" />
                <span>FAAB Dollars Received ($):</span>
              </label>
              <input
                v-model.number="sideA.faab_received"
                type="number"
                min="0"
                class="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 font-mono"
              />
            </div>
          </div>

          <!-- SIDE B -->
          <div class="space-y-4 p-4 rounded-xl bg-slate-950/60 border border-slate-800">
            <div class="flex items-center justify-between border-b border-slate-800/80 pb-2.5">
              <span class="text-xs font-black uppercase tracking-wider text-sky-400">
                Side B (Receiving)
              </span>
            </div>

            <!-- Team Selector -->
            <div class="space-y-1">
              <label class="text-[11px] font-semibold text-slate-400">Franchise:</label>
              <select
                v-model="sideB.team_id"
                class="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
              >
                <option :value="null">-- Select Team --</option>
                <option
                  v-for="t in availableSeasonTeams"
                  :key="t.team_id"
                  :value="t.team_id"
                  :disabled="t.team_id === sideA.team_id"
                >
                  {{ t.team_name }} ({{ t.manager_name }})
                </option>
              </select>
            </div>

            <!-- Players Received by Side B -->
            <div class="space-y-2">
              <div class="flex items-center justify-between text-[11px] font-semibold text-slate-400">
                <span>Players Received ({{ sideB.players.length }})</span>
              </div>

              <!-- List of attached players -->
              <div class="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                <div
                  v-for="player in sideB.players"
                  :key="player.player_id"
                  class="flex items-center justify-between gap-2 p-2 rounded-lg bg-slate-900/90 border border-slate-800 text-xs"
                >
                  <div class="flex items-center gap-2 min-w-0">
                    <span class="px-1.5 py-0.2 rounded text-[10px] font-mono font-bold bg-slate-800 text-slate-300">
                      {{ player.default_position }}
                    </span>
                    <span class="font-bold text-slate-200 truncate">{{ player.full_name }}</span>
                    <span class="text-[10px] text-slate-400 font-mono">{{ player.pro_team }}</span>
                  </div>
                  <button
                    type="button"
                    class="text-rose-400 hover:text-rose-300 p-1 cursor-pointer"
                    title="Remove player"
                    @click="removePlayerFromSide(sideB, player.player_id)"
                  >
                    <X class="w-3.5 h-3.5" />
                  </button>
                </div>
                <div v-if="sideB.players.length === 0" class="text-xs text-slate-500 italic py-1 text-center">
                  No players attached
                </div>
              </div>

              <!-- Add Player Search Input -->
              <div class="relative pt-1">
                <Search class="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2 mt-0.5" />
                <input
                  v-model="sideB.playerSearch"
                  type="text"
                  placeholder="Search player to add to Side B..."
                  class="w-full bg-slate-900 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
                <!-- Search Suggestions Dropdown -->
                <div
                  v-if="sideB.playerSearch.trim() && getFilteredPlayers(sideB).length > 0"
                  class="absolute left-0 right-0 top-full mt-1 bg-slate-900 border border-slate-700 rounded-xl shadow-xl z-20 max-h-48 overflow-y-auto divide-y divide-slate-800"
                >
                  <button
                    v-for="p in getFilteredPlayers(sideB)"
                    :key="p.player_id"
                    type="button"
                    class="w-full px-3 py-2 text-left flex items-center justify-between text-xs hover:bg-slate-800 cursor-pointer"
                    @click="addPlayerToSide(sideB, p)"
                  >
                    <div class="flex items-center gap-2">
                      <span class="px-1.5 py-0.2 rounded text-[10px] font-mono font-bold bg-slate-800 text-slate-300">
                        {{ p.default_position }}
                      </span>
                      <span class="font-bold text-slate-200">{{ p.full_name }}</span>
                    </div>
                    <span class="text-[10px] text-slate-400 font-mono">{{ p.pro_team }}</span>
                  </button>
                </div>
              </div>
            </div>

            <!-- Draft Picks Received by Side B -->
            <div class="space-y-2 pt-2 border-t border-slate-800/80">
              <div class="text-[11px] font-semibold text-slate-400 flex items-center justify-between">
                <span>Draft Picks Received ({{ sideB.draft_picks.length }})</span>
              </div>

              <!-- Attached Picks List -->
              <div class="flex flex-wrap gap-1.5">
                <div
                  v-for="(pick, pIdx) in sideB.draft_picks"
                  :key="pIdx"
                  class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-violet-950/40 text-violet-300 border border-violet-500/30 text-xs font-mono"
                >
                  <Ticket class="w-3 h-3 text-violet-400" />
                  <span>{{ pick.season_year || formSeasonYear }} Rd {{ pick.round }}{{ pick.pick_number ? ` (#${pick.pick_number})` : '' }}</span>
                  <button
                    type="button"
                    class="text-rose-400 hover:text-rose-300 ml-1 cursor-pointer"
                    @click="removeDraftPickFromSide(sideB, pIdx)"
                  >
                    <X class="w-3 h-3" />
                  </button>
                </div>
              </div>

              <!-- Inline Add Pick Controls -->
              <div class="bg-slate-900/90 rounded-lg p-2 border border-slate-800/80 grid grid-cols-4 gap-1.5 text-xs">
                <div>
                  <label class="text-[9px] text-slate-500 uppercase font-mono">Year</label>
                  <input
                    v-model.number="sideB.newPickYear"
                    type="number"
                    class="w-full bg-slate-950 border border-slate-800 rounded px-1.5 py-1 text-slate-200 text-xs font-mono"
                  />
                </div>
                <div>
                  <label class="text-[9px] text-slate-500 uppercase font-mono">Round</label>
                  <select
                    v-model.number="sideB.newPickRound"
                    class="w-full bg-slate-950 border border-slate-800 rounded px-1.5 py-1 text-slate-200 text-xs font-mono"
                  >
                    <option v-for="r in 16" :key="r" :value="r">Rd {{ r }}</option>
                  </select>
                </div>
                <div>
                  <label class="text-[9px] text-slate-500 uppercase font-mono">Pick # (opt)</label>
                  <input
                    v-model.number="sideB.newPickNumber"
                    type="number"
                    placeholder="e.g. 57"
                    class="w-full bg-slate-950 border border-slate-800 rounded px-1.5 py-1 text-slate-200 text-xs font-mono"
                  />
                </div>
                <div class="flex items-end">
                  <button
                    type="button"
                    class="w-full py-1 rounded bg-violet-600 hover:bg-violet-500 text-white font-bold text-xs uppercase transition-colors cursor-pointer"
                    @click="addDraftPickToSide(sideB)"
                  >
                    + Pick
                  </button>
                </div>
              </div>
            </div>

            <!-- FAAB Received by Side B -->
            <div class="space-y-1 pt-2 border-t border-slate-800/80">
              <label class="text-[11px] font-semibold text-slate-400 flex items-center gap-1">
                <Coins class="w-3 h-3 text-amber-400" />
                <span>FAAB Dollars Received ($):</span>
              </label>
              <input
                v-model.number="sideB.faab_received"
                type="number"
                min="0"
                class="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 font-mono"
              />
            </div>
          </div>
        </div>

        <!-- Form Action Buttons -->
        <div class="flex items-center justify-between pt-3 border-t border-slate-800 flex-wrap gap-2">
          <div>
            <button
              v-if="!isCreatingNew && formTradeId"
              type="button"
              class="px-3 py-2 rounded-xl text-xs font-bold text-rose-400 hover:text-rose-300 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 transition-colors flex items-center gap-1.5 cursor-pointer"
              @click="handleDeleteTrade(formTradeId)"
            >
              <Trash2 class="w-3.5 h-3.5" />
              <span>Delete Trade</span>
            </button>
          </div>

          <div class="flex items-center gap-2">
            <button
              type="button"
              class="px-4 py-2 rounded-xl text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 transition-colors cursor-pointer"
              @click="cancelEditor"
            >
              Cancel
            </button>
            <button
              type="button"
              class="px-5 py-2 rounded-xl text-xs font-bold uppercase tracking-wide bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
              :disabled="formSubmitting"
              @click="handleSaveTrade"
            >
              <span>{{ formSubmitting ? 'Saving Changes...' : isCreatingNew ? 'Create Manual Trade' : 'Save Trade Changes' }}</span>
            </button>
          </div>
        </div>
      </div>

      <!-- WORKSPACE MODE TABS: Existing Trades vs Deleted Trades -->
      <div class="flex items-center gap-2 border-b border-slate-800 pb-2">
        <button
          type="button"
          class="px-3 py-1.5 rounded-lg text-xs font-bold uppercase transition-colors flex items-center gap-1.5 cursor-pointer"
          :class="activeTab === 'list' ? 'bg-slate-800 text-indigo-400 border border-indigo-500/40' : 'text-slate-400 hover:text-slate-200'"
          @click="activeTab = 'list'"
        >
          <Layers class="w-3.5 h-3.5" />
          <span>Active & Historical Deals ({{ filteredExistingTrades.length }})</span>
        </button>

        <button
          type="button"
          class="px-3 py-1.5 rounded-lg text-xs font-bold uppercase transition-colors flex items-center gap-1.5 cursor-pointer"
          :class="activeTab === 'deleted' ? 'bg-slate-800 text-indigo-400 border border-indigo-500/40' : 'text-slate-400 hover:text-slate-200'"
          @click="activeTab = 'deleted'"
        >
          <Trash2 class="w-3.5 h-3.5" />
          <span>Deleted Archive ({{ adminOptions?.deleted_trades?.length ?? 0 }})</span>
        </button>
      </div>

      <!-- TAB 1: Existing Trades List with Quick Commissioner Controls -->
      <div v-show="activeTab === 'list'" class="space-y-3">
        <!-- Search & Filter Bar -->
        <div class="flex items-center gap-2 flex-wrap">
          <div class="relative flex-1 min-w-[200px]">
            <Search class="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              v-model="listSearchQuery"
              type="text"
              placeholder="Filter trades by manager, player, or franchise..."
              class="w-full bg-slate-900 border border-slate-800 rounded-xl pl-8 pr-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            />
          </div>

          <div class="flex items-center gap-1">
            <select
              v-model="listSeasonFilter"
              class="bg-slate-900 border border-slate-800 rounded-xl px-2.5 py-2 text-xs text-slate-300 focus:outline-none focus:border-indigo-500"
            >
              <option :value="null">All Seasons</option>
              <option v-for="s in adminOptions?.seasons ?? []" :key="s" :value="s">
                Season {{ s }}
              </option>
            </select>
          </div>
        </div>

        <!-- Trades Cards in Commissioner Mode -->
        <div class="space-y-2.5">
          <div
            v-for="trade in filteredExistingTrades"
            :key="trade.trade_id"
            class="stadium-card rounded-xl p-3.5 border border-slate-800 bg-slate-900/80 flex items-center justify-between gap-3 flex-wrap"
          >
            <!-- Trade Brief Info -->
            <div class="flex items-center gap-3 min-w-0">
              <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-slate-800 text-slate-300">
                <Calendar class="w-3 h-3 text-slate-400" />
                <span>{{ trade.season_year }} Wk {{ trade.week ?? 0 }}</span>
              </span>

              <div class="flex items-center gap-1 shrink-0">
                <TeamAvatar
                  v-if="trade.sides[0]"
                  :src="trade.sides[0].logo_url"
                  :name="trade.sides[0].team_name || trade.sides[0].manager_name"
                  size="sm"
                />
                <TeamAvatar
                  v-if="trade.sides[1]"
                  :src="trade.sides[1].logo_url"
                  :name="trade.sides[1].team_name || trade.sides[1].manager_name"
                  size="sm"
                />
              </div>

              <div class="min-w-0">
                <div class="flex items-center gap-2 text-xs font-bold text-slate-200 truncate">
                  <span class="text-indigo-300">{{ trade.sides[0]?.team_name }}</span>
                  <span class="text-slate-500">↔</span>
                  <span class="text-sky-300">{{ trade.sides[1]?.team_name }}</span>
                </div>
                <div class="text-[11px] text-slate-400 truncate mt-0.5 flex items-center gap-2">
                  <span>{{ trade.sides[0]?.assets_received.length || 0 }} assets for {{ trade.sides[1]?.assets_received.length || 0 }} assets</span>
                  <span>•</span>
                  <span class="font-mono">{{ trade.verdict_label }}</span>
                </div>
              </div>
            </div>

            <!-- Actions -->
            <div class="flex items-center gap-2 shrink-0">
              <button
                type="button"
                class="px-2.5 py-1 rounded-lg text-xs font-semibold bg-indigo-600/20 text-indigo-300 hover:bg-indigo-600/30 border border-indigo-500/30 transition-colors flex items-center gap-1 cursor-pointer"
                @click="startEditTrade(trade)"
              >
                <Edit3 class="w-3 h-3" />
                <span>Edit</span>
              </button>

              <button
                type="button"
                class="px-2.5 py-1 rounded-lg text-xs font-semibold bg-rose-500/10 text-rose-400 hover:bg-rose-500/20 border border-rose-500/20 transition-colors flex items-center gap-1 cursor-pointer"
                @click="handleDeleteTrade(trade.trade_id)"
              >
                <Trash2 class="w-3 h-3" />
                <span>Delete</span>
              </button>
            </div>
          </div>

          <div
            v-if="filteredExistingTrades.length === 0"
            class="text-center py-8 text-xs text-slate-500 italic bg-slate-950/40 rounded-xl border border-slate-800"
          >
            No trades match the current filter.
          </div>
        </div>
      </div>

      <!-- TAB 2: Deleted Trades Archive -->
      <div v-show="activeTab === 'deleted'" class="space-y-3">
        <div class="space-y-2.5">
          <div
            v-for="dTrade in adminOptions?.deleted_trades ?? []"
            :key="dTrade.trade_id"
            class="stadium-card rounded-xl p-3.5 border border-slate-800/80 bg-slate-950/60 flex items-center justify-between gap-3 flex-wrap"
          >
            <div class="flex items-center gap-3 min-w-0">
              <span class="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-rose-500/10 text-rose-400 border border-rose-500/20">
                Deleted #{{ dTrade.trade_id }}
              </span>

              <div class="min-w-0 text-xs">
                <div class="flex items-center gap-2 font-bold text-slate-300 truncate">
                  <span>{{ dTrade.sides[0]?.team_name }}</span>
                  <span class="text-slate-500">↔</span>
                  <span>{{ dTrade.sides[1]?.team_name }}</span>
                </div>
                <div class="text-[11px] text-slate-500 font-mono mt-0.5">
                  Season {{ dTrade.season_year }} • Week {{ dTrade.week ?? 0 }}
                </div>
              </div>
            </div>

            <button
              type="button"
              class="px-3 py-1.5 rounded-lg text-xs font-bold text-emerald-400 hover:text-emerald-300 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 transition-colors flex items-center gap-1.5 cursor-pointer"
              @click="handleRestoreTrade(dTrade.trade_id)"
            >
              <RotateCcw class="w-3.5 h-3.5" />
              <span>Restore Trade</span>
            </button>
          </div>

          <div
            v-if="!adminOptions?.deleted_trades || adminOptions.deleted_trades.length === 0"
            class="text-center py-8 text-xs text-slate-500 italic bg-slate-950/40 rounded-xl border border-slate-800"
          >
            No deleted trades in the archive.
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
