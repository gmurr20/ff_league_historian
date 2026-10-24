<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue';
import type {
  TransactionAuditItem,
  FailureReasonCount,
  BiddingWar,
  LosingBid,
  TransactionItem,
} from '@/types/api';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import BiddingWarDrawer from '@/components/waivers/BiddingWarDrawer.vue';
import {
  Search,
  CheckCircle2,
  XCircle,
  Plus,
  Minus,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  ChevronDown,
  X,
  Receipt,
  ArrowLeftRight,
} from 'lucide-vue-next';
import { positionTextClass } from '@/components/trades/tradeUi';

const props = withDefaults(
  defineProps<{
    transactions: TransactionAuditItem[];
    biddingWars?: BiddingWar[];
    failureReasons?: FailureReasonCount[];
    pageSize?: number;
    initialTypeFilter?: 'ALL' | 'WAIVER' | 'FREE_AGENT' | 'DROP' | 'TRADE';
    selectedManagerId?: number | null;
  }>(),
  {
    biddingWars: () => [],
    failureReasons: () => [],
    pageSize: 50,
    initialTypeFilter: 'WAIVER',
    selectedManagerId: null,
  }
);

const emit = defineEmits<{
  (e: 'clearManagerFilter'): void;
}>();

const searchQuery = ref<string>('');
const statusFilter = ref<'ALL' | 'EXECUTED' | 'FAILED'>('ALL');
const typeFilter = ref<'ALL' | 'WAIVER' | 'FREE_AGENT' | 'DROP' | 'TRADE'>(
  props.initialTypeFilter
);

// Pagination state
const currentPage = ref<number>(1);
const feedTopRef = ref<HTMLElement | null>(null);

// Contested Bidding War Drawer state
const selectedWar = ref<BiddingWar | null>(null);
const drawerOpen = ref<boolean>(false);

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateStr;
  }
}

interface TradeParticipantSide {
  team_name: string;
  manager_name: string | null;
  manager_id: number | null;
  receives: TransactionItem[];
  sends: TransactionItem[];
  drops: TransactionItem[];
}

function getTradeSides(tx: TransactionAuditItem): TradeParticipantSide[] {
  if (tx.transaction_type !== 'TRADE') return [];
  const sidesMap = new Map<string, TradeParticipantSide>();

  function getSide(teamName: string, mgrName: string | null, mgrId: number | null): TradeParticipantSide {
    if (!sidesMap.has(teamName)) {
      sidesMap.set(teamName, {
        team_name: teamName,
        manager_name: mgrName,
        manager_id: mgrId,
        receives: [],
        sends: [],
        drops: [],
      });
    }
    return sidesMap.get(teamName)!;
  }

  for (const it of tx.items) {
    if (it.item_type === 'TRADE') {
      if (it.to_team_name) {
        const side = getSide(it.to_team_name, it.to_manager_name ?? null, it.to_manager_id ?? null);
        side.receives.push(it);
      }
      if (it.from_team_name) {
        const side = getSide(it.from_team_name, it.from_manager_name ?? null, it.from_manager_id ?? null);
        side.sends.push(it);
      }
    } else if (it.item_type === 'DROP') {
      if (it.from_team_name) {
        const side = getSide(it.from_team_name, it.from_manager_name ?? null, it.from_manager_id ?? null);
        side.drops.push(it);
      }
    }
  }

  return Array.from(sidesMap.values());
}

function getAddedItem(tx: TransactionAuditItem): TransactionItem | null {
  if (tx.transaction_type === 'TRADE') return null;
  return tx.items.find((i) => i.item_type === 'ADD') ?? (tx.transaction_type !== 'DROP' ? (tx.items.length > 0 ? tx.items[0] : null) : null);
}

function getDroppedItem(tx: TransactionAuditItem): TransactionItem | null {
  if (tx.transaction_type === 'TRADE') return null;
  return tx.items.find((i) => i.item_type === 'DROP') ?? (tx.transaction_type === 'DROP' ? (tx.items.length > 0 ? tx.items[0] : null) : null);
}

// ---------------------------------------------------------------------------
// 1. FAAB Bidding War & Failed Bids Correlation Index
// ---------------------------------------------------------------------------
const failedBidsByWinningTxId = computed<Map<number, LosingBid[]>>(() => {
  const map = new Map<number, LosingBid[]>();

  for (const war of props.biddingWars) {
    if (war.winning_transaction_id) {
      map.set(war.winning_transaction_id, [...war.losing_bids]);
    }
  }

  const txByEspnIdMap = new Map<string, TransactionAuditItem>();
  for (const tx of props.transactions) {
    if (tx.espn_transaction_id) {
      txByEspnIdMap.set(tx.espn_transaction_id, tx);
    }
  }

  for (const tx of props.transactions) {
    if (tx.status === 'FAILED' && tx.related_espn_transaction_id) {
      const parent = txByEspnIdMap.get(tx.related_espn_transaction_id);
      if (parent) {
        const existingList = map.get(parent.transaction_id) ?? [];
        const duplicateManagerBid = existingList.some(
          (b) => b.manager_id === tx.manager_id && b.bid_amount === (tx.bid_amount ?? 0)
        );
        if (!existingList.some((b) => b.transaction_id === tx.transaction_id) && !duplicateManagerBid) {
          existingList.push({
            transaction_id: tx.transaction_id,
            team_id: tx.team_id ?? 0,
            team_name: tx.team_name ?? 'Unknown Team',
            logo_url: tx.logo_url,
            manager_id: tx.manager_id ?? 0,
            manager_name: tx.manager_name ?? 'Unknown Manager',
            bid_amount: tx.bid_amount ?? 0,
            failure_reason: tx.failure_reason ?? 'OUTBID',
            waiver_priority: tx.waiver_priority,
          });
          existingList.sort(
            (a, b) =>
              b.bid_amount - a.bid_amount ||
              (a.waiver_priority ?? 999) - (b.waiver_priority ?? 999)
          );
          map.set(parent.transaction_id, existingList);
        }
      }
    }
  }

  return map;
});

const warByWinningTxId = computed<Map<number, BiddingWar>>(() => {
  const map = new Map<number, BiddingWar>();
  for (const war of props.biddingWars) {
    if (war.winning_transaction_id) {
      map.set(war.winning_transaction_id, war);
    }
  }
  return map;
});

const txByEspnId = computed<Map<string, TransactionAuditItem>>(() => {
  const map = new Map<string, TransactionAuditItem>();
  for (const tx of props.transactions) {
    if (tx.espn_transaction_id) {
      map.set(tx.espn_transaction_id, tx);
    }
  }
  return map;
});

function getFailedBidsForTransaction(tx: TransactionAuditItem): LosingBid[] {
  return failedBidsByWinningTxId.value.get(tx.transaction_id) ?? [];
}

function getWarForTransaction(tx: TransactionAuditItem): BiddingWar | null {
  const war = warByWinningTxId.value.get(tx.transaction_id);
  if (war) return war;

  const losing = failedBidsByWinningTxId.value.get(tx.transaction_id);
  if (losing && losing.length > 0 && tx.items.length > 0) {
    const firstItem = tx.items[0];
    return {
      winning_transaction_id: tx.transaction_id,
      espn_transaction_id: tx.espn_transaction_id,
      season_year: tx.season_year,
      week: tx.week,
      executed_at: tx.executed_at,
      player: {
        player_id: firstItem.player_id,
        full_name: firstItem.full_name,
        default_position: firstItem.default_position,
        pro_team: firstItem.pro_team,
        headshot_url: firstItem.headshot_url,
      },
      winner: {
        team_id: tx.team_id ?? 0,
        team_name: tx.team_name ?? '',
        logo_url: tx.logo_url,
        manager_id: tx.manager_id ?? 0,
        manager_name: tx.manager_name ?? '',
        bid_amount: tx.bid_amount ?? 0,
        post_claim_starter_points: 0,
      },
      losing_bids: losing,
    };
  }
  return null;
}

function getWinningParentForFailedTx(
  tx: TransactionAuditItem
): TransactionAuditItem | null {
  if (!tx.related_espn_transaction_id) return null;
  return txByEspnId.value.get(tx.related_espn_transaction_id) ?? null;
}

function openWarReceipt(tx: TransactionAuditItem) {
  const war = getWarForTransaction(tx);
  if (war) {
    selectedWar.value = war;
    drawerOpen.value = true;
  }
}

// ---------------------------------------------------------------------------
// 2. Transaction Counts for Filter Pills & Manager Quick Filter
// ---------------------------------------------------------------------------
const localManagerFilter = ref<number | null>(props.selectedManagerId ?? null);

watch(
  () => props.selectedManagerId,
  (val) => {
    localManagerFilter.value = val ?? null;
  }
);

watch(localManagerFilter, (val) => {
  if (val === null) {
    emit('clearManagerFilter');
  }
});

const effectiveManagerFilter = computed<number | null>(() => {
  return localManagerFilter.value;
});

const availableTeams = computed(() => {
  const map = new Map<number, { id: number; name: string; manager_name: string }>();
  for (const t of props.transactions) {
    if (t.manager_id && (t.team_name || t.manager_name)) {
      if (!map.has(t.manager_id)) {
        map.set(t.manager_id, {
          id: t.manager_id,
          name: t.team_name || t.manager_name || `Manager ${t.manager_id}`,
          manager_name: t.manager_name || '',
        });
      }
    }
  }
  return Array.from(map.values()).sort((a, b) => a.name.localeCompare(b.name));
});

const counts = computed(() => {
  let waiver = 0;
  let freeAgent = 0;
  let drop = 0;
  let trade = 0;
  let executed = 0;
  let failed = 0;

  for (const t of props.transactions) {
    if (t.transaction_type === 'WAIVER') {
      if (
        t.status === 'EXECUTED' ||
        (t.status === 'FAILED' &&
          (!t.related_espn_transaction_id ||
            !txByEspnId.value.has(t.related_espn_transaction_id)))
      ) {
        waiver++;
      }
    } else if (t.transaction_type === 'FREE_AGENT') {
      freeAgent++;
    } else if (t.transaction_type === 'DROP') {
      drop++;
    } else if (t.transaction_type === 'TRADE') {
      trade++;
    }

    if (t.status === 'EXECUTED') executed++;
    else if (t.status === 'FAILED') failed++;
  }

  const all = waiver + freeAgent + drop + trade;

  return { all, waiver, freeAgent, drop, trade, executed, failed };
});

// ---------------------------------------------------------------------------
// 3. Filtered Transactions
// ---------------------------------------------------------------------------
const filteredTransactions = computed(() => {
  let list = props.transactions;

  if (statusFilter.value !== 'FAILED') {
    list = list.filter((t) => {
      if (t.transaction_type === 'WAIVER') {
        if (t.status === 'CANCELED') {
          return false;
        }
        if (
          t.status === 'FAILED' &&
          t.related_espn_transaction_id &&
          txByEspnId.value.has(t.related_espn_transaction_id)
        ) {
          return false;
        }
      }
      return true;
    });
  }

  if (typeFilter.value !== 'ALL') {
    list = list.filter((t) => t.transaction_type === typeFilter.value);
  }

  if (statusFilter.value !== 'ALL') {
    list = list.filter((t) => t.status === statusFilter.value);
  }

  if (effectiveManagerFilter.value !== null && effectiveManagerFilter.value !== undefined) {
    const filterId = effectiveManagerFilter.value;
    list = list.filter((t) => {
      if (t.manager_id === filterId) return true;
      if (t.transaction_type === 'TRADE') {
        if (
          t.items.some(
            (it) => it.from_manager_id === filterId || it.to_manager_id === filterId
          )
        ) {
          return true;
        }
      }
      const losing = failedBidsByWinningTxId.value.get(t.transaction_id);
      if (losing?.some((lb) => lb.manager_id === filterId)) {
        return true;
      }
      return false;
    });
  }

  const q = searchQuery.value.trim().toLowerCase();
  if (q) {
    list = list.filter((t) => {
      const managerMatch =
        (t.manager_name && t.manager_name.toLowerCase().includes(q)) ||
        (t.team_name && t.team_name.toLowerCase().includes(q));
      if (managerMatch) return true;

      const playerMatch = t.items.some(
        (item) =>
          item.full_name.toLowerCase().includes(q) ||
          item.pro_team.toLowerCase().includes(q) ||
          item.default_position.toLowerCase().includes(q)
      );
      if (playerMatch) return true;

      const losing = failedBidsByWinningTxId.value.get(t.transaction_id);
      if (
        losing?.some(
          (lb) =>
            lb.manager_name.toLowerCase().includes(q) ||
            lb.team_name.toLowerCase().includes(q)
        )
      ) {
        return true;
      }

      return false;
    });
  }

  return list;
});

// ---------------------------------------------------------------------------
// 4. Pagination
// ---------------------------------------------------------------------------
const totalPages = computed(() =>
  Math.max(1, Math.ceil(filteredTransactions.value.length / props.pageSize))
);

watch(
  [
    searchQuery,
    statusFilter,
    typeFilter,
    () => effectiveManagerFilter.value,
    () => props.transactions,
  ],
  () => {
    currentPage.value = 1;
  }
);

const paginatedTransactions = computed(() => {
  const start = (currentPage.value - 1) * props.pageSize;
  return filteredTransactions.value.slice(start, start + props.pageSize);
});

const pageStart = computed(() => {
  if (filteredTransactions.value.length === 0) return 0;
  return (currentPage.value - 1) * props.pageSize + 1;
});

const pageEnd = computed(() => {
  return Math.min(
    currentPage.value * props.pageSize,
    filteredTransactions.value.length
  );
});

function goToPage(page: number) {
  if (page < 1 || page > totalPages.value) return;
  currentPage.value = page;
  nextTick(() => {
    feedTopRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
}

const pageNumbers = computed<(number | string)[]>(() => {
  const total = totalPages.value;
  const current = currentPage.value;
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }

  const pages: (number | string)[] = [1];
  if (current > 3) {
    pages.push('...');
  }

  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);
  for (let i = start; i <= end; i++) {
    pages.push(i);
  }

  if (current < total - 2) {
    pages.push('...');
  }
  pages.push(total);

  return pages;
});
</script>

<template>
  <div ref="feedTopRef" class="space-y-3.5">
    <!-- Search Bar -->
    <div class="relative">
      <Search class="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
      <input
        v-model="searchQuery"
        type="search"
        placeholder="Search players, managers, rivals"
        class="w-full h-11 bg-slate-900/80 border border-slate-800 rounded-xl pl-9 pr-10 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-slate-600 transition-colors"
      />
      <button
        v-if="searchQuery"
        type="button"
        aria-label="Clear search"
        class="absolute right-1 top-1/2 -translate-y-1/2 w-9 h-9 flex items-center justify-center text-slate-500 hover:text-slate-200 cursor-pointer"
        @click="searchQuery = ''"
      >
        <X class="w-4 h-4" />
      </button>
    </div>

    <!-- Filter Controls: Type Pills (wrapped, zero horizontal overflow) -->
    <div class="space-y-2">
      <div class="flex flex-wrap gap-1 p-1 rounded-xl bg-slate-900/80 border border-slate-800/80">
        <button
          type="button"
          class="h-8 px-3 rounded-lg text-xs font-semibold transition-colors cursor-pointer"
          :class="
            typeFilter === 'WAIVER'
              ? 'bg-slate-700/80 text-white'
              : 'text-slate-400 hover:text-slate-200'
          "
          @click="typeFilter = 'WAIVER'"
        >
          Waivers ({{ counts.waiver }})
        </button>

        <button
          type="button"
          class="h-8 px-3 rounded-lg text-xs font-semibold transition-colors cursor-pointer"
          :class="
            typeFilter === 'FREE_AGENT'
              ? 'bg-slate-700/80 text-white'
              : 'text-slate-400 hover:text-slate-200'
          "
          @click="typeFilter = 'FREE_AGENT'"
        >
          Free Agents ({{ counts.freeAgent }})
        </button>

        <button
          type="button"
          class="h-8 px-3 rounded-lg text-xs font-semibold transition-colors cursor-pointer"
          :class="
            typeFilter === 'ALL'
              ? 'bg-slate-700/80 text-white'
              : 'text-slate-400 hover:text-slate-200'
          "
          @click="typeFilter = 'ALL'"
        >
          All Moves ({{ counts.all }})
        </button>

        <button
          type="button"
          class="h-8 px-2.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer"
          :class="
            typeFilter === 'DROP'
              ? 'bg-slate-700/80 text-white'
              : 'text-slate-400 hover:text-slate-200'
          "
          @click="typeFilter = 'DROP'"
        >
          Drops ({{ counts.drop }})
        </button>

        <button
          type="button"
          class="h-8 px-2.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer"
          :class="
            typeFilter === 'TRADE'
              ? 'bg-slate-700/80 text-white'
              : 'text-slate-400 hover:text-slate-200'
          "
          @click="typeFilter = 'TRADE'"
        >
          Trades ({{ counts.trade }})
        </button>
      </div>

      <!-- Secondary Row: Status Pills & Franchise select -->
      <div class="flex items-center justify-between gap-2 flex-wrap">
        <!-- Status filter -->
        <div class="inline-flex items-center rounded-lg bg-slate-900 border border-slate-800 p-0.5 text-xs">
          <button
            type="button"
            class="px-2.5 py-1 rounded-md font-semibold transition-colors cursor-pointer"
            :class="statusFilter === 'ALL' ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'"
            @click="statusFilter = 'ALL'"
          >
            All
          </button>
          <button
            type="button"
            class="px-2.5 py-1 rounded-md font-semibold transition-colors cursor-pointer"
            :class="statusFilter === 'EXECUTED' ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'"
            @click="statusFilter = 'EXECUTED'"
          >
            Executed
          </button>
          <button
            type="button"
            class="px-2.5 py-1 rounded-md font-semibold transition-colors cursor-pointer"
            :class="statusFilter === 'FAILED' ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'"
            @click="statusFilter = 'FAILED'"
          >
            Failed
          </button>
        </div>

        <!-- Franchise select -->
        <div class="flex items-center gap-1.5 flex-1 sm:flex-initial justify-end">
          <label class="relative inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-300 cursor-pointer">
            <span class="truncate max-w-[160px]">
              {{ availableTeams.find(t => t.id === localManagerFilter)?.name || 'All franchises' }}
            </span>
            <ChevronDown class="w-3.5 h-3.5 text-slate-500 shrink-0" />
            <select
              v-model="localManagerFilter"
              aria-label="Filter by Franchise"
              class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            >
              <option :value="null">All franchises ({{ availableTeams.length }})</option>
              <option
                v-for="t in availableTeams"
                :key="t.id"
                :value="t.id"
              >
                {{ t.name }}
              </option>
            </select>
          </label>

          <button
            v-if="localManagerFilter !== null"
            type="button"
            class="h-8 px-2 rounded-lg text-xs font-semibold text-slate-400 hover:text-slate-200 bg-slate-900 border border-slate-800 cursor-pointer flex items-center"
            title="Clear franchise filter"
            @click="localManagerFilter = null; emit('clearManagerFilter')"
          >
            <X class="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>

    <!-- Feed Count Strip -->
    <div class="flex items-baseline justify-between px-0.5 pt-1 text-xs text-slate-500">
      <span class="font-mono tabular-nums">
        Showing {{ pageStart }}–{{ pageEnd }} of {{ filteredTransactions.length }}
      </span>
      <span v-if="totalPages > 1" class="font-mono text-[11px] tabular-nums">
        Page {{ currentPage }} of {{ totalPages }}
      </span>
    </div>

    <!-- Feed List -->
    <div class="space-y-2.5">
      <article
        v-for="tx in paginatedTransactions"
        :key="tx.transaction_id"
        class="rounded-2xl border transition-colors overflow-hidden p-3.5 space-y-3"
        :class="[
          tx.status === 'FAILED'
            ? 'border-rose-500/30 bg-slate-900/40'
            : getFailedBidsForTransaction(tx).length > 0
              ? 'border-slate-800/90 bg-slate-900/60'
              : 'border-slate-800/80 bg-slate-900/50',
        ]"
      >
        <!-- Meta Bar -->
        <header class="flex items-center justify-between gap-2 text-[11px] font-mono tabular-nums">
          <div class="flex items-center gap-1.5 text-slate-400">
            <span v-if="tx.status === 'EXECUTED'" class="inline-flex items-center gap-1 text-emerald-400 font-sans font-semibold">
              <CheckCircle2 class="w-3 h-3" />
              <span>Executed</span>
            </span>
            <span v-else-if="tx.status === 'FAILED'" class="inline-flex items-center gap-1 text-rose-400 font-sans font-semibold">
              <XCircle class="w-3 h-3" />
              <span>Failed</span>
            </span>
            <span v-else class="text-slate-400">{{ tx.status }}</span>

            <span class="text-slate-600">/</span>
            <span>{{ tx.transaction_type.replace('_', ' ') }}</span>
            <template v-if="tx.week != null">
              <span class="text-slate-600">/</span>
              <span>Wk {{ tx.week }}</span>
            </template>
          </div>

          <div class="flex items-center gap-2 text-slate-500">
            <span>{{ formatDate(tx.executed_at) }}</span>
            <button
              v-if="getFailedBidsForTransaction(tx).length > 0"
              type="button"
              class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold text-amber-300 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/20 transition-colors cursor-pointer"
              title="View full bidding war receipt"
              @click="openWarReceipt(tx)"
            >
              <Receipt class="w-3 h-3" />
              <span>Receipt</span>
            </button>
          </div>
        </header>

        <!-- Trade Actions: Bilateral asset movement -->
        <div v-if="tx.transaction_type === 'TRADE'" class="space-y-2 py-0.5">
          <div
            v-for="side in getTradeSides(tx)"
            :key="side.team_name"
            class="p-2.5 rounded-xl bg-slate-950/60 border border-slate-800/60 space-y-1.5"
          >
            <div class="flex items-center justify-between text-xs font-semibold text-slate-200">
              <span class="truncate">{{ side.team_name }}</span>
              <span class="text-[10px] font-mono uppercase tracking-wider text-emerald-400">Acquires</span>
            </div>

            <!-- Assets received by this team -->
            <div class="space-y-1">
              <div
                v-for="asset in side.receives"
                :key="asset.player_id"
                class="flex items-center gap-2 text-xs"
              >
                <span class="w-4 h-4 rounded flex items-center justify-center bg-emerald-500/15 text-emerald-400 shrink-0 font-bold text-xs">
                  +
                </span>
                <span class="font-semibold text-slate-100 truncate" :title="asset.full_name">
                  {{ asset.full_name }}
                </span>
                <span class="text-[11px] font-mono font-bold" :class="positionTextClass(asset.default_position)">
                  {{ asset.default_position }}
                </span>
                <span v-if="asset.pro_team && asset.pro_team !== 'FA'" class="text-[10px] text-slate-500 font-mono">
                  {{ asset.pro_team }}
                </span>
              </div>
            </div>

            <!-- Drops during trade -->
            <div v-if="side.drops.length > 0" class="space-y-1 pt-1 border-t border-slate-800/40">
              <div
                v-for="drop in side.drops"
                :key="drop.player_id"
                class="flex items-center gap-2 text-xs text-slate-400"
              >
                <span class="w-4 h-4 rounded flex items-center justify-center bg-rose-500/15 text-rose-400 shrink-0 font-bold text-xs">
                  −
                </span>
                <span class="truncate text-slate-400">{{ drop.full_name }}</span>
                <span class="text-[10px] font-mono" :class="positionTextClass(drop.default_position)">
                  {{ drop.default_position }}
                </span>
                <span class="text-[10px] text-slate-500">(dropped)</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Non-trade actions (Claimed & Dropped for waivers / free agents) -->
        <div v-else class="space-y-1.5 pl-1">
          <!-- Added -->
          <div v-if="getAddedItem(tx)" class="flex items-baseline justify-between gap-2 min-w-0">
            <div class="flex items-center gap-2 min-w-0">
              <span class="w-4 h-4 rounded flex items-center justify-center bg-emerald-500/15 text-emerald-400 shrink-0">
                <Plus class="w-3 h-3" />
              </span>
              <span class="text-sm font-semibold text-slate-100 truncate" :title="getAddedItem(tx)?.full_name">
                {{ getAddedItem(tx)?.full_name }}
              </span>
              <span class="text-[11px] font-mono font-bold" :class="positionTextClass(getAddedItem(tx)?.default_position)">
                {{ getAddedItem(tx)?.default_position }}
              </span>
              <span class="text-[11px] text-slate-500 font-mono">
                {{ getAddedItem(tx)?.pro_team }}
              </span>
            </div>
          </div>

          <!-- Dropped -->
          <div v-if="getDroppedItem(tx)" class="flex items-baseline justify-between gap-2 min-w-0">
            <div class="flex items-center gap-2 min-w-0 text-slate-400">
              <span class="w-4 h-4 rounded flex items-center justify-center bg-rose-500/15 text-rose-400 shrink-0">
                <Minus class="w-3 h-3" />
              </span>
              <span class="text-xs text-slate-400 truncate" :title="getDroppedItem(tx)?.full_name">
                {{ getDroppedItem(tx)?.full_name }}
              </span>
              <span class="text-[10px] font-mono" :class="positionTextClass(getDroppedItem(tx)?.default_position)">
                {{ getDroppedItem(tx)?.default_position }}
              </span>
              <span class="text-[10px] text-slate-600 font-mono">
                {{ getDroppedItem(tx)?.pro_team }}
              </span>
            </div>
          </div>
        </div>

        <!-- Trade footer (Bilateral) -->
        <div v-if="tx.transaction_type === 'TRADE'" class="flex items-center justify-between gap-2 pt-2 border-t border-slate-800/80">
          <div class="flex items-center gap-2 text-slate-400 min-w-0">
            <ArrowLeftRight class="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            <span class="font-mono text-xs text-slate-300 font-semibold truncate">
              Completed Bilateral Trade
            </span>
          </div>
          <span class="text-[11px] font-mono text-slate-500 tabular-nums">
            {{ tx.items.filter((i) => i.item_type === 'TRADE').length }} assets exchanged
          </span>
        </div>

        <!-- Manager row & Bid Callout -->
        <div v-else class="flex items-center justify-between gap-2 pt-2 border-t border-slate-800/80">
          <div class="flex items-center gap-2.5 min-w-0">
            <TeamAvatar
              :src="tx.logo_url"
              :name="tx.team_name || tx.manager_name || 'Franchise'"
              size="sm"
            />
            <div class="min-w-0">
              <div class="text-xs font-semibold text-slate-200 truncate leading-tight">
                {{ tx.team_name || tx.manager_name || 'Franchise' }}
              </div>
              <div class="text-[10px] text-slate-500 truncate">{{ tx.manager_name }}</div>
            </div>
          </div>

          <div class="text-right shrink-0">
            <div
              v-if="tx.bid_amount != null"
              class="font-mono text-sm font-bold tabular-nums"
              :class="tx.status === 'FAILED' ? 'text-rose-400' : 'text-slate-100'"
            >
              ${{ tx.bid_amount }} <span class="text-[10px] text-slate-500 font-normal">FAAB</span>
            </div>
            <div v-else-if="tx.transaction_type === 'FREE_AGENT'" class="text-[11px] font-mono text-slate-500">
              $0 FAAB
            </div>
            <div v-if="tx.waiver_priority != null" class="text-[10px] font-mono text-slate-500">
              Priority #{{ tx.waiver_priority }}
            </div>
          </div>
        </div>

        <!-- Competing Losing Bids (when contested) -->
        <div
          v-if="getFailedBidsForTransaction(tx).length > 0"
          class="rounded-xl bg-slate-950/40 p-2.5 space-y-1.5 border border-slate-800/60"
        >
          <div class="flex items-center justify-between text-[11px] font-mono text-slate-400">
            <span>{{ getFailedBidsForTransaction(tx).length }} losing bid{{ getFailedBidsForTransaction(tx).length > 1 ? 's' : '' }}</span>
            <span class="text-emerald-400 font-bold">
              +${{ (tx.bid_amount ?? 0) - (getFailedBidsForTransaction(tx)[0]?.bid_amount ?? 0) }} winning margin
            </span>
          </div>

          <div class="space-y-1 pt-0.5">
            <div
              v-for="losing in getFailedBidsForTransaction(tx)"
              :key="losing.transaction_id"
              class="flex items-center justify-between text-xs text-slate-300 py-0.5"
            >
              <div class="flex items-center gap-1.5 min-w-0">
                <TeamAvatar :src="losing.logo_url" :name="losing.team_name || losing.manager_name" size="xs" />
                <span class="truncate text-slate-300 text-[11px]">{{ losing.team_name }}</span>
              </div>
              <div class="flex items-center gap-2 font-mono text-[11px] tabular-nums shrink-0">
                <span class="text-rose-400">${{ losing.bid_amount }}</span>
                <span class="text-slate-500 text-[10px] uppercase">({{ losing.failure_reason }})</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Outbid explanation if tx is itself a failed bid -->
        <div
          v-else-if="tx.status === 'FAILED' && getWinningParentForFailedTx(tx)"
          class="text-xs text-rose-300/90 bg-rose-950/20 rounded-lg p-2 flex items-center justify-between gap-2"
        >
          <span class="truncate">
            Outbid by <strong>{{ getWinningParentForFailedTx(tx)?.team_name }}</strong> (${{ getWinningParentForFailedTx(tx)?.bid_amount }} FAAB)
          </span>
          <span class="font-mono text-[10px] uppercase font-bold shrink-0">{{ tx.failure_reason }}</span>
        </div>
      </article>

      <!-- Empty State -->
      <div
        v-if="filteredTransactions.length === 0"
        class="text-center py-12 px-4 text-slate-400 text-xs rounded-2xl border border-slate-800/80 space-y-2"
      >
        <p class="font-semibold text-slate-200 text-sm">No transactions match</p>
        <p class="text-slate-500 max-w-sm mx-auto">
          Try resetting your search query or status filter.
        </p>
        <button
          type="button"
          class="mt-2 h-9 px-4 rounded-lg text-xs font-semibold bg-slate-800 text-slate-200 hover:bg-slate-700 cursor-pointer"
          @click="
            searchQuery = '';
            statusFilter = 'ALL';
            typeFilter = 'ALL';
            emit('clearManagerFilter');
          "
        >
          Reset filters
        </button>
      </div>
    </div>

    <!-- Pagination Controls (wrapped, never overflows horizontally) -->
    <div
      v-if="totalPages > 1"
      class="flex items-center justify-between gap-2 flex-wrap pt-3 border-t border-slate-800/80"
    >
      <div class="text-xs text-slate-500 font-mono tabular-nums">
        Showing {{ pageStart }}–{{ pageEnd }} of {{ filteredTransactions.length }}
      </div>

      <div class="flex items-center gap-1">
        <button
          type="button"
          class="w-8 h-8 rounded-lg border border-slate-800 flex items-center justify-center text-slate-400 hover:text-white disabled:opacity-25 disabled:cursor-not-allowed cursor-pointer"
          :disabled="currentPage === 1"
          title="First page"
          @click="goToPage(1)"
        >
          <ChevronsLeft class="w-3.5 h-3.5" />
        </button>

        <button
          type="button"
          class="w-8 h-8 rounded-lg border border-slate-800 flex items-center justify-center text-slate-400 hover:text-white disabled:opacity-25 disabled:cursor-not-allowed cursor-pointer"
          :disabled="currentPage === 1"
          title="Previous page"
          @click="goToPage(currentPage - 1)"
        >
          <ChevronLeft class="w-3.5 h-3.5" />
        </button>

        <template v-for="(p, idx) in pageNumbers" :key="`p-${idx}`">
          <span v-if="p === '...'" class="px-1 text-slate-600 font-mono text-xs">…</span>
          <button
            v-else
            type="button"
            class="min-w-[32px] h-8 px-1.5 rounded-lg text-xs font-mono font-bold transition-all cursor-pointer"
            :class="
              currentPage === p
                ? 'bg-slate-700 text-white'
                : 'text-slate-400 hover:text-slate-200 border border-slate-800'
            "
            @click="goToPage(Number(p))"
          >
            {{ p }}
          </button>
        </template>

        <button
          type="button"
          class="w-8 h-8 rounded-lg border border-slate-800 flex items-center justify-center text-slate-400 hover:text-white disabled:opacity-25 disabled:cursor-not-allowed cursor-pointer"
          :disabled="currentPage === totalPages"
          title="Next page"
          @click="goToPage(currentPage + 1)"
        >
          <ChevronRight class="w-3.5 h-3.5" />
        </button>

        <button
          type="button"
          class="w-8 h-8 rounded-lg border border-slate-800 flex items-center justify-center text-slate-400 hover:text-white disabled:opacity-25 disabled:cursor-not-allowed cursor-pointer"
          :disabled="currentPage === totalPages"
          title="Last page"
          @click="goToPage(totalPages)"
        >
          <ChevronsRight class="w-3.5 h-3.5" />
        </button>
      </div>
    </div>

    <!-- FAAB Bidding War Drawer -->
    <BiddingWarDrawer v-model="drawerOpen" :war="selectedWar" />
  </div>
</template>
