<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import type {
  SideBetDetail,
  SideBetCreatePayload,
  SideBetScoringMode,
} from '@/types/api';
import {
  verifyTradeAdminPassword,
  fetchTradeAdminOptions,
  fetchSideBets,
  createSideBetAdmin,
  updateSideBetAdmin,
  deleteSideBetAdmin,
  triggerLiveScoreSyncAdmin,
  type TradeAdminOptionsResponse,
  type TradeAdminTeamOption,
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
  Edit3,
  X,
  RefreshCw,
  Minus,
  Swords,
} from 'lucide-vue-next';

const props = defineProps<{
  selectedSeason: number | null;
}>();

const emit = defineEmits<{
  (e: 'updated'): void;
  (e: 'auth-change', isAuthenticated: boolean): void;
}>();

// Authentication State
const password = ref<string>('');
const enteredPassword = ref<string>('');
const isAuthenticated = ref<boolean>(false);
const authLoading = ref<boolean>(false);
const authError = ref<string | null>(null);

// Admin Options & Existing Side Bets
const adminOptions = ref<TradeAdminOptionsResponse | null>(null);
const existingBets = ref<SideBetDetail[]>([]);
const optionsLoading = ref<boolean>(false);
const liveSyncing = ref<boolean>(false);
const feedbackMessage = ref<{ type: 'success' | 'error'; text: string } | null>(null);

// Editor State
const isEditorOpen = ref<boolean>(false);
const isCreatingNew = ref<boolean>(true);
const editingBetId = ref<number | null>(null);
const formSubmitting = ref<boolean>(false);
const formValidation = ref<string | null>(null);

// Form Fields
const formSeasonYear = ref<number>(props.selectedSeason ?? new Date().getFullYear());
const formWeek = ref<number>(1);
const formTitle = ref<string>('');
const formSideAName = ref<string>('Side A');
const formSideBName = ref<string>('Side B');
const formSideATeamIds = ref<number[]>([]);
const formSideBTeamIds = ref<number[]>([]);
const formSpreadSideA = ref<number>(0);
const formStakeAmount = ref<number>(20);
const formStakeDescription = ref<string>('');
const formScoringMode = ref<SideBetScoringMode>('STARTERS');

// Load saved commissioner password from sessionStorage on mount
onMounted(async () => {
  const saved = sessionStorage.getItem('ff_trade_admin_password');
  if (saved) {
    enteredPassword.value = saved;
    await handleAuthenticate();
  }
});

watch(
  () => props.selectedSeason,
  (newSeason) => {
    if (newSeason !== null) {
      formSeasonYear.value = newSeason;
    }
    if (isAuthenticated.value) {
      loadExistingBets();
    }
  }
);

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
      emit('auth-change', true);
      await Promise.all([loadAdminOptions(), loadExistingBets()]);
    } else {
      sessionStorage.removeItem('ff_trade_admin_password');
      isAuthenticated.value = false;
      emit('auth-change', false);
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
  emit('auth-change', false);
  adminOptions.value = null;
  isEditorOpen.value = false;
}

async function loadAdminOptions() {
  if (!password.value) return;
  optionsLoading.value = true;
  try {
    adminOptions.value = await fetchTradeAdminOptions(password.value);
    if (!props.selectedSeason && adminOptions.value.seasons.length > 0) {
      formSeasonYear.value = adminOptions.value.seasons[0];
    }
  } catch (err: unknown) {
    showFeedback('error', err instanceof Error ? err.message : 'Failed to load franchise options');
  } finally {
    optionsLoading.value = false;
  }
}

async function loadExistingBets() {
  try {
    const res = await fetchSideBets(props.selectedSeason, undefined, true);
    existingBets.value = res.bets;
    if (res.current_week && isCreatingNew.value && !isEditorOpen.value) {
      formWeek.value = res.current_week;
    }
  } catch (err: unknown) {
    console.error('Error loading side bets in commish desk:', err);
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

// Available teams for the selected form season
const availableSeasonTeams = computed<TradeAdminTeamOption[]>(() => {
  if (!adminOptions.value) return [];
  const year = formSeasonYear.value;
  const filtered = adminOptions.value.teams.filter((t) => t.season_year === year);
  if (filtered.length > 0) return filtered;
  const seen = new Set<number>();
  return adminOptions.value.teams.filter((t) => {
    if (seen.has(t.team_id)) return false;
    seen.add(t.team_id);
    return true;
  });
});

// Clear invalid team selections if season changes during creation
watch(formSeasonYear, () => {
  if (isCreatingNew.value) {
    const validIds = new Set(availableSeasonTeams.value.map((t) => t.team_id));
    formSideATeamIds.value = formSideATeamIds.value.filter((id) => validIds.has(id));
    formSideBTeamIds.value = formSideBTeamIds.value.filter((id) => validIds.has(id));
  }
});

function getTeamAssignment(teamId: number): 'A' | 'B' | null {
  if (formSideATeamIds.value.includes(teamId)) return 'A';
  if (formSideBTeamIds.value.includes(teamId)) return 'B';
  return null;
}

function assignTeamToSide(teamId: number, side: 'A' | 'B' | null) {
  formSideATeamIds.value = formSideATeamIds.value.filter((id) => id !== teamId);
  formSideBTeamIds.value = formSideBTeamIds.value.filter((id) => id !== teamId);
  if (side === 'A') {
    formSideATeamIds.value.push(teamId);
  } else if (side === 'B') {
    formSideBTeamIds.value.push(teamId);
  }
}

function adjustSpread(delta: number) {
  const next = Math.round((formSpreadSideA.value + delta) * 100) / 100;
  formSpreadSideA.value = next;
}

function formatSpread(spread: number): string {
  if (spread === 0) return 'PK (0.0)';
  return spread > 0 ? `+${spread.toFixed(1)}` : `${spread.toFixed(1)}`;
}

function startCreateBet() {
  isCreatingNew.value = true;
  editingBetId.value = null;
  formSeasonYear.value = props.selectedSeason ?? adminOptions.value?.seasons[0] ?? new Date().getFullYear();
  formTitle.value = '';
  formSideAName.value = 'Side A';
  formSideBName.value = 'Side B';
  formSideATeamIds.value = [];
  formSideBTeamIds.value = [];
  formSpreadSideA.value = 0;
  formStakeAmount.value = 20;
  formStakeDescription.value = '';
  formScoringMode.value = 'STARTERS';
  formValidation.value = null;
  isEditorOpen.value = true;
}

function startEditBet(bet: SideBetDetail) {
  isCreatingNew.value = false;
  editingBetId.value = bet.bet_id;
  formSeasonYear.value = bet.season_year;
  formWeek.value = bet.week;
  formTitle.value = bet.title;
  formSideAName.value = bet.side_a.side_name || 'Side A';
  formSideBName.value = bet.side_b.side_name || 'Side B';
  formSideATeamIds.value = bet.side_a.teams.map((t) => t.team_id);
  formSideBTeamIds.value = bet.side_b.teams.map((t) => t.team_id);
  formSpreadSideA.value = bet.spread_side_a;
  formStakeAmount.value = bet.stake_amount;
  formStakeDescription.value = bet.stake_description || '';
  formScoringMode.value = bet.scoring_mode || 'STARTERS';
  formValidation.value = null;
  isEditorOpen.value = true;
}

function cancelEditor() {
  isEditorOpen.value = false;
  editingBetId.value = null;
  formValidation.value = null;
}

async function handleSaveBet() {
  formValidation.value = null;

  if (formSideATeamIds.value.length === 0 || formSideBTeamIds.value.length === 0) {
    formValidation.value = 'Both Side A and Side B must have at least 1 franchise assigned.';
    return;
  }

  const overlap = formSideATeamIds.value.some((id) => formSideBTeamIds.value.includes(id));
  if (overlap) {
    formValidation.value = 'A franchise cannot be on both Side A and Side B.';
    return;
  }

  formSubmitting.value = true;
  try {
    const payload: SideBetCreatePayload = {
      season_year: formSeasonYear.value,
      week: formWeek.value,
      title: formTitle.value.trim(),
      side_a_name: formSideAName.value.trim() || 'Side A',
      side_b_name: formSideBName.value.trim() || 'Side B',
      side_a_team_ids: formSideATeamIds.value,
      side_b_team_ids: formSideBTeamIds.value,
      spread_side_a: Number(formSpreadSideA.value) || 0,
      stake_amount: Math.max(0, Number(formStakeAmount.value) || 0),
      stake_description: formStakeDescription.value.trim(),
      scoring_mode: formScoringMode.value,
    };

    if (isCreatingNew.value) {
      await createSideBetAdmin(password.value, payload);
      showFeedback('success', 'Side bet created and synced to scoreboard!');
    } else if (editingBetId.value !== null) {
      await updateSideBetAdmin(password.value, editingBetId.value, payload);
      showFeedback('success', `Side bet #${editingBetId.value} updated!`);
    }

    isEditorOpen.value = false;
    await loadExistingBets();
    emit('updated');
  } catch (err: unknown) {
    formValidation.value = err instanceof Error ? err.message : 'Failed to save side bet';
  } finally {
    formSubmitting.value = false;
  }
}

async function handleDeleteBet(betId: number) {
  if (!confirm('Are you sure you want to delete this side bet?')) {
    return;
  }
  try {
    await deleteSideBetAdmin(password.value, betId);
    showFeedback('success', `Side bet #${betId} deleted.`);
    if (editingBetId.value === betId) {
      isEditorOpen.value = false;
    }
    await loadExistingBets();
    emit('updated');
  } catch (err: unknown) {
    showFeedback('error', err instanceof Error ? err.message : 'Failed to delete side bet');
  }
}

async function handleTriggerLiveSync() {
  if (!password.value) return;
  liveSyncing.value = true;
  try {
    const res = await triggerLiveScoreSyncAdmin(password.value);
    showFeedback(
      'success',
      `${res.message || 'Live score sync finished'} (${res.records_processed ?? 0} lineups updated)`
    );
    await loadExistingBets();
    emit('updated');
  } catch (err: unknown) {
    showFeedback('error', err instanceof Error ? err.message : 'Live score sync failed');
  } finally {
    liveSyncing.value = false;
  }
}
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
          Commissioner Side Bet Desk
        </h3>
        <p class="text-xs text-slate-400 max-w-sm mx-auto">
          Authenticate with commissioner access to create 1v1 or multi-team group side bets, set point spreads, manage cash stakes, and trigger live ESPN score syncs.
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
          <span>{{ authLoading ? 'Verifying...' : 'Unlock Side Bet Desk' }}</span>
        </button>
      </form>
    </div>

    <!-- STATE 2: UNLOCKED COMMISSIONER WORKSPACE -->
    <div v-else class="space-y-4">
      <!-- Commissioner Top Bar -->
      <div class="rounded-2xl px-4 py-3 border border-slate-800 bg-slate-900/90 flex items-center justify-between gap-3 flex-wrap shadow-md">
        <div class="flex items-center gap-2.5">
          <div class="w-8 h-8 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 flex items-center justify-center">
            <ShieldCheck class="w-4 h-4" />
          </div>
          <div>
            <div class="flex items-center gap-2">
              <span class="text-sm font-bold uppercase tracking-tight text-slate-100">
                Commissioner Side Bet Desk
              </span>
              <span class="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                Unlocked
              </span>
            </div>
            <p class="text-[11px] text-slate-400">
              Create 1v1 or N vs. M team wagers with point spreads &amp; cash stakes
            </p>
          </div>
        </div>

        <div class="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            class="px-3 py-1.5 rounded-lg text-xs font-mono font-bold bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/40 flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50"
            :disabled="liveSyncing"
            @click="handleTriggerLiveSync"
          >
            <RefreshCw class="w-3.5 h-3.5" :class="liveSyncing ? 'animate-spin' : ''" />
            <span>{{ liveSyncing ? 'Syncing ESPN...' : 'Sync Live ESPN Scores' }}</span>
          </button>

          <button
            type="button"
            class="px-3 py-1.5 rounded-lg text-xs font-bold uppercase bg-indigo-600 hover:bg-indigo-500 text-white flex items-center gap-1.5 shadow-sm transition-colors cursor-pointer"
            @click="startCreateBet"
          >
            <Plus class="w-3.5 h-3.5" />
            <span>New Side Bet</span>
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

      <!-- SIDE BET CREATOR / EDITOR FORM -->
      <div
        v-if="isEditorOpen"
        class="rounded-2xl p-4 sm:p-5 border border-indigo-500/50 bg-slate-900/95 space-y-5 shadow-2xl"
      >
        <!-- Form Header -->
        <div class="flex items-center justify-between border-b border-slate-800 pb-3 flex-wrap gap-2">
          <div class="flex items-center gap-2">
            <div class="w-7 h-7 rounded-lg bg-indigo-500/20 text-indigo-400 flex items-center justify-center">
              <Edit3 class="w-4 h-4" />
            </div>
            <h4 class="text-sm font-black uppercase tracking-tight text-slate-100">
              {{ isCreatingNew ? 'Create New Side Bet' : `Edit Side Bet #${editingBetId}` }}
            </h4>
          </div>

          <button
            type="button"
            class="text-slate-400 hover:text-slate-200 p-1 cursor-pointer"
            @click="cancelEditor"
          >
            <X class="w-4 h-4" />
          </button>
        </div>

        <!-- Validation Alert -->
        <div
          v-if="formValidation"
          class="p-3 rounded-xl bg-rose-950/80 border border-rose-500/40 text-rose-300 text-xs flex items-center gap-2"
        >
          <AlertCircle class="w-4 h-4 text-rose-400 shrink-0" />
          <span>{{ formValidation }}</span>
        </div>

        <!-- Row 1: Season, Week, Title, Scoring Mode -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div>
            <label class="text-[11px] font-mono font-bold uppercase text-slate-400 block mb-1">Season</label>
            <select
              v-model.number="formSeasonYear"
              class="w-full h-10 bg-slate-950 border border-slate-800 rounded-xl px-3 text-xs font-mono text-slate-200 focus:outline-none focus:border-indigo-500"
            >
              <option v-for="s in adminOptions?.seasons ?? [formSeasonYear]" :key="s" :value="s">
                {{ s }}
              </option>
            </select>
          </div>

          <div>
            <label class="text-[11px] font-mono font-bold uppercase text-slate-400 block mb-1">Week</label>
            <select
              v-model.number="formWeek"
              class="w-full h-10 bg-slate-950 border border-slate-800 rounded-xl px-3 text-xs font-mono text-slate-200 focus:outline-none focus:border-indigo-500"
            >
              <option v-for="w in 18" :key="w" :value="w">Week {{ w }}</option>
            </select>
          </div>

          <div>
            <label class="text-[11px] font-mono font-bold uppercase text-slate-400 block mb-1">Stake ($ / Team)</label>
            <input
              v-model.number="formStakeAmount"
              type="number"
              min="0"
              step="5"
              placeholder="20"
              class="w-full h-10 bg-slate-950 border border-slate-800 rounded-xl px-3 text-xs font-mono text-slate-200 focus:outline-none focus:border-indigo-500"
            />
          </div>

          <div>
            <label class="text-[11px] font-mono font-bold uppercase text-slate-400 block mb-1">Scoring Mode</label>
            <select
              v-model="formScoringMode"
              class="w-full h-10 bg-slate-950 border border-slate-800 rounded-xl px-3 text-xs font-mono text-slate-200 focus:outline-none focus:border-indigo-500"
            >
              <option value="STARTERS">Starters (Default)</option>
              <option value="MAX_PF">Max PF (Optimal)</option>
              <option value="BENCH">Bench Points</option>
            </select>
          </div>
        </div>

        <!-- Row 2: Bet Title & Point Spread Stepper -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label class="text-[11px] font-mono font-bold uppercase text-slate-400 block mb-1">
              Bet Title (Optional)
            </label>
            <input
              v-model="formTitle"
              type="text"
              placeholder="e.g. Rivalry Week Grudge Match or East vs. West 2v2"
              class="w-full h-10 bg-slate-950 border border-slate-800 rounded-xl px-3 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            />
          </div>

          <div>
            <label class="text-[11px] font-mono font-bold uppercase text-slate-400 block mb-1">
              Side A Point Spread ({{ formatSpread(formSpreadSideA) }})
            </label>
            <div class="flex items-center gap-1.5">
              <button
                type="button"
                class="h-10 px-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-mono font-bold text-slate-200 flex items-center gap-1 cursor-pointer shrink-0"
                @click="adjustSpread(-0.5)"
              >
                <Minus class="w-3.5 h-3.5" />
                <span>0.5</span>
              </button>

              <input
                v-model.number="formSpreadSideA"
                type="number"
                step="0.5"
                class="w-full h-10 bg-slate-950 border border-slate-800 rounded-xl px-3 text-center text-xs font-mono font-bold text-emerald-400 focus:outline-none focus:border-indigo-500"
              />

              <button
                type="button"
                class="h-10 px-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-mono font-bold text-slate-200 flex items-center gap-1 cursor-pointer shrink-0"
                @click="adjustSpread(0.5)"
              >
                <Plus class="w-3.5 h-3.5" />
                <span>0.5</span>
              </button>

              <button
                type="button"
                class="h-10 px-2.5 rounded-xl bg-slate-950 border border-slate-800 hover:border-slate-700 text-[11px] font-mono text-slate-400 hover:text-slate-200 cursor-pointer shrink-0"
                @click="formSpreadSideA = 0"
              >
                PK
              </button>
            </div>
          </div>
        </div>

        <!-- Group Labels (Side A Name & Side B Name) -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label class="text-[11px] font-mono font-bold uppercase text-indigo-400 block mb-1">
              Side A Label ({{ formSideATeamIds.length }} selected)
            </label>
            <input
              v-model="formSideAName"
              type="text"
              placeholder="Side A"
              class="w-full h-9 bg-slate-950 border border-slate-800 rounded-xl px-3 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
            />
          </div>

          <div>
            <label class="text-[11px] font-mono font-bold uppercase text-amber-400 block mb-1">
              Side B Label ({{ formSideBTeamIds.length }} selected)
            </label>
            <input
              v-model="formSideBName"
              type="text"
              placeholder="Side B"
              class="w-full h-9 bg-slate-950 border border-slate-800 rounded-xl px-3 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
            />
          </div>
        </div>

        <!-- Franchise Assignment Matrix (Assign any team to Side A, Side B, or Off) -->
        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <label class="text-[11px] font-mono font-bold uppercase text-slate-300">
              Assign Franchises to Side A vs. Side B
            </label>
            <span class="text-[10px] font-mono text-slate-500">
              Supports 1v1, 2v2, 3v3, or handicap N vs. M groups
            </span>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-80 overflow-y-auto pr-1">
            <div
              v-for="team in availableSeasonTeams"
              :key="team.team_id"
              class="p-2 rounded-xl border flex items-center justify-between gap-2 transition-colors"
              :class="
                getTeamAssignment(team.team_id) === 'A'
                  ? 'bg-indigo-950/35 border-indigo-500/50'
                  : getTeamAssignment(team.team_id) === 'B'
                  ? 'bg-amber-950/35 border-amber-500/50'
                  : 'bg-slate-950/60 border-slate-800/80'
              "
            >
              <div class="flex items-center gap-2 min-w-0">
                <TeamAvatar :src="team.logo_url" :name="team.team_name" size="xs" rounded="lg" />
                <div class="min-w-0">
                  <div class="text-xs font-bold text-slate-100 truncate">
                    {{ team.team_name }}
                  </div>
                  <div class="text-[10px] text-slate-400 truncate">
                    {{ team.manager_name }}
                  </div>
                </div>
              </div>

              <!-- A / B / Off Pill Buttons -->
              <div class="inline-flex items-center rounded-lg bg-slate-900 border border-slate-800 p-0.5 shrink-0 font-mono text-[10px]">
                <button
                  type="button"
                  class="px-2 py-1 rounded-md font-bold transition-colors cursor-pointer"
                  :class="
                    getTeamAssignment(team.team_id) === 'A'
                      ? 'bg-indigo-600 text-white shadow-sm'
                      : 'text-slate-400 hover:text-slate-200'
                  "
                  @click="assignTeamToSide(team.team_id, getTeamAssignment(team.team_id) === 'A' ? null : 'A')"
                >
                  Side A
                </button>
                <button
                  type="button"
                  class="px-2 py-1 rounded-md font-bold transition-colors cursor-pointer"
                  :class="
                    getTeamAssignment(team.team_id) === 'B'
                      ? 'bg-amber-500 text-slate-950 shadow-sm'
                      : 'text-slate-400 hover:text-slate-200'
                  "
                  @click="assignTeamToSide(team.team_id, getTeamAssignment(team.team_id) === 'B' ? null : 'B')"
                >
                  Side B
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Form Actions -->
        <div class="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
          <button
            type="button"
            class="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:text-slate-200 bg-slate-800/80 hover:bg-slate-800 cursor-pointer"
            @click="cancelEditor"
          >
            Cancel
          </button>
          <button
            type="button"
            class="px-4 py-2 rounded-xl text-xs font-bold uppercase tracking-wide bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg cursor-pointer disabled:opacity-50"
            :disabled="formSubmitting"
            @click="handleSaveBet"
          >
            {{ formSubmitting ? 'Saving...' : isCreatingNew ? 'Create Side Bet' : 'Save Changes' }}
          </button>
        </div>
      </div>

      <!-- EXISTING SIDE BETS LIST FOR MANAGEMENT -->
      <div class="rounded-2xl border border-slate-800 bg-[#0b101b] overflow-hidden shadow-lg">
        <div class="px-4 py-3 bg-slate-900/95 border-b border-slate-800 flex items-center justify-between gap-2">
          <div class="flex items-center gap-2">
            <Swords class="w-4 h-4 text-indigo-400" />
            <h4 class="text-xs sm:text-sm font-black uppercase tracking-tight text-slate-100">
              Recorded Side Bets ({{ existingBets.length }})
            </h4>
          </div>
          <span class="text-[11px] font-mono text-slate-400">
            {{ selectedSeason ? `Season ${selectedSeason}` : 'All Seasons' }}
          </span>
        </div>

        <div v-if="existingBets.length > 0" class="divide-y divide-slate-800/60">
          <div
            v-for="bet in existingBets"
            :key="bet.bet_id"
            class="px-4 py-3 flex items-center justify-between gap-3 hover:bg-slate-900/60 transition-colors flex-wrap"
          >
            <div class="min-w-0 flex-1 space-y-1">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-200 text-[10px] font-mono font-bold">
                  {{ bet.season_year }} · Wk {{ bet.week }}
                </span>
                <span
                  v-if="bet.stake_amount > 0"
                  class="px-2 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30 text-[10px] font-mono font-bold"
                >
                  ${{ bet.stake_amount.toFixed(0) }}
                </span>
                <span class="text-xs sm:text-sm font-bold text-slate-100 truncate">
                  {{ bet.title || `${bet.side_a.teams.length}v${bet.side_b.teams.length} Matchup` }}
                </span>
              </div>

              <div class="text-[11px] font-mono text-slate-400">
                <span class="text-indigo-300 font-semibold">
                  {{ bet.side_a.teams.map((t) => t.team_name).join(' + ') }}
                </span>
                <span class="text-emerald-400 font-bold mx-1">
                  ({{ formatSpread(bet.spread_side_a) }})
                </span>
                <span class="text-slate-500">vs.</span>
                <span class="text-amber-300 font-semibold ml-1">
                  {{ bet.side_b.teams.map((t) => t.team_name).join(' + ') }}
                </span>
                <span class="text-slate-500 ml-2">
                  [{{ bet.side_a.raw_points.toFixed(1) }} – {{ bet.side_b.raw_points.toFixed(1) }}]
                </span>
              </div>
            </div>

            <div class="flex items-center gap-1.5 shrink-0">
              <button
                type="button"
                class="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors cursor-pointer"
                title="Edit Side Bet"
                @click="startEditBet(bet)"
              >
                <Edit3 class="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                class="p-2 rounded-lg bg-rose-950/60 hover:bg-rose-900/70 text-rose-300 border border-rose-500/30 transition-colors cursor-pointer"
                title="Delete Side Bet"
                @click="handleDeleteBet(bet.bet_id)"
              >
                <Trash2 class="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>

        <div v-else class="p-6 text-center text-xs font-mono text-slate-500">
          No side bets recorded yet. Click "New Side Bet" above to create one.
        </div>
      </div>
    </div>
  </div>
</template>
