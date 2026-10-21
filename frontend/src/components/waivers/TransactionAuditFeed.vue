<script setup lang="ts">
import { ref, computed } from 'vue';
import type { TransactionAuditItem, FailureReasonCount } from '@/types/api';
import {
  Search,
  CheckCircle2,
  XCircle,
  AlertOctagon,
  ArrowRightLeft,
  Plus,
  Minus,
  Clock,
  AlertTriangle,
} from 'lucide-vue-next';

const props = defineProps<{
  transactions: TransactionAuditItem[];
  failureReasons: FailureReasonCount[];
}>();

const searchQuery = ref<string>('');
const statusFilter = ref<'ALL' | 'EXECUTED' | 'FAILED'>('ALL');
const typeFilter = ref<'ALL' | 'WAIVER' | 'FREE_AGENT' | 'DROP' | 'TRADE'>('ALL');

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

function getPositionClass(pos: string): string {
  switch (pos?.toUpperCase()) {
    case 'QB':
      return 'bg-rose-500/20 text-rose-300 border-rose-500/40';
    case 'RB':
      return 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40';
    case 'WR':
      return 'bg-sky-500/20 text-sky-300 border-sky-500/40';
    case 'TE':
      return 'bg-amber-500/20 text-amber-300 border-amber-500/40';
    case 'K':
      return 'bg-purple-500/20 text-purple-300 border-purple-500/40';
    default:
      return 'bg-slate-700 text-slate-300 border-slate-600';
  }
}

const filteredTransactions = computed(() => {
  let list = props.transactions;

  // Status Filter
  if (statusFilter.value !== 'ALL') {
    list = list.filter((t) => t.status === statusFilter.value);
  }

  // Type Filter
  if (typeFilter.value !== 'ALL') {
    list = list.filter((t) => t.transaction_type === typeFilter.value);
  }

  // Search Filter
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
      return playerMatch;
    });
  }

  return list;
});
</script>

<template>
  <div class="space-y-4">
    <!-- Failure Reasons Breakdown Summary Chips -->
    <div v-if="failureReasons.length > 0" class="stadium-card rounded-xl p-3 border border-slate-800 space-y-2">
      <div class="flex items-center gap-1.5 text-xs font-bold text-slate-300 uppercase tracking-tight">
        <AlertTriangle class="w-3.5 h-3.5 text-rose-400" />
        <span>Waiver Bid Failure Reason Breakdown</span>
      </div>

      <div class="flex items-center gap-2 flex-wrap">
        <div
          v-for="fr in failureReasons"
          :key="fr.reason"
          class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-mono font-bold bg-rose-950/30 text-rose-300 border border-rose-500/30"
        >
          <span class="w-1.5 h-1.5 rounded-full bg-rose-400"></span>
          <span>{{ fr.reason }}</span>
          <span class="bg-rose-500/30 px-1.5 py-0.2 rounded text-[11px] text-white">
            {{ fr.count }}
          </span>
        </div>
      </div>
    </div>

    <!-- Filter Controls Row -->
    <div class="space-y-2.5">
      <!-- Search Input -->
      <div class="relative">
        <Search class="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Filter audit feed by manager, team, or player..."
          class="w-full bg-slate-900/90 border border-slate-800 rounded-xl pl-9 pr-4 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-amber-500 transition-colors"
        />
      </div>

      <!-- Filter Pills: Status & Type -->
      <div class="flex items-center justify-between gap-2 flex-wrap">
        <!-- Status Filter Pills -->
        <div class="inline-flex items-center rounded-lg bg-slate-900 border border-slate-800 p-0.5 text-xs">
          <button
            type="button"
            class="px-2.5 py-1 rounded-md font-semibold transition-colors"
            :class="statusFilter === 'ALL' ? 'bg-amber-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'"
            @click="statusFilter = 'ALL'"
          >
            All Status
          </button>
          <button
            type="button"
            class="px-2.5 py-1 rounded-md font-semibold transition-colors flex items-center gap-1"
            :class="statusFilter === 'EXECUTED' ? 'bg-emerald-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'"
            @click="statusFilter = 'EXECUTED'"
          >
            <CheckCircle2 class="w-3 h-3" />
            <span>Executed</span>
          </button>
          <button
            type="button"
            class="px-2.5 py-1 rounded-md font-semibold transition-colors flex items-center gap-1"
            :class="statusFilter === 'FAILED' ? 'bg-rose-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'"
            @click="statusFilter = 'FAILED'"
          >
            <XCircle class="w-3 h-3" />
            <span>Failed</span>
          </button>
        </div>

        <!-- Type Filter Pills -->
        <div class="inline-flex items-center rounded-lg bg-slate-900 border border-slate-800 p-0.5 text-xs overflow-x-auto max-w-full">
          <button
            type="button"
            class="px-2.5 py-1 rounded-md font-semibold transition-colors shrink-0"
            :class="typeFilter === 'ALL' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'"
            @click="typeFilter = 'ALL'"
          >
            All Types
          </button>
          <button
            type="button"
            class="px-2 py-1 rounded-md font-semibold transition-colors shrink-0"
            :class="typeFilter === 'WAIVER' ? 'bg-amber-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'"
            @click="typeFilter = 'WAIVER'"
          >
            Waiver
          </button>
          <button
            type="button"
            class="px-2 py-1 rounded-md font-semibold transition-colors shrink-0"
            :class="typeFilter === 'FREE_AGENT' ? 'bg-sky-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'"
            @click="typeFilter = 'FREE_AGENT'"
          >
            Free Agent
          </button>
          <button
            type="button"
            class="px-2 py-1 rounded-md font-semibold transition-colors shrink-0"
            :class="typeFilter === 'DROP' ? 'bg-slate-700 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'"
            @click="typeFilter = 'DROP'"
          >
            Drop
          </button>
          <button
            type="button"
            class="px-2 py-1 rounded-md font-semibold transition-colors shrink-0"
            :class="typeFilter === 'TRADE' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'"
            @click="typeFilter = 'TRADE'"
          >
            Trade
          </button>
        </div>
      </div>
    </div>

    <!-- Audit Feed List -->
    <div class="space-y-2.5">
      <div
        v-for="tx in filteredTransactions"
        :key="tx.transaction_id"
        class="stadium-card rounded-xl p-3 border transition-all"
        :class="
          tx.status === 'FAILED'
            ? 'border-rose-500/40 bg-rose-950/10'
            : tx.status === 'EXECUTED'
              ? 'border-slate-800 hover:border-slate-700'
              : 'border-slate-800/80 bg-slate-900/40'
        "
      >
        <!-- Transaction Top Row: Status + Type + Date -->
        <div class="flex items-center justify-between gap-2 text-xs">
          <div class="flex items-center gap-1.5 flex-wrap">
            <!-- Status Badge -->
            <span
              v-if="tx.status === 'EXECUTED'"
              class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-mono font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
            >
              <CheckCircle2 class="w-3 h-3 text-emerald-400" />
              <span>EXECUTED</span>
            </span>
            <span
              v-else-if="tx.status === 'FAILED'"
              class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-mono font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40 shadow-sm"
            >
              <XCircle class="w-3 h-3 text-rose-400" />
              <span>FAILED: {{ tx.failure_reason || 'UNFULFILLED' }}</span>
            </span>
            <span
              v-else
              class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-mono font-bold bg-slate-800 text-slate-400 border border-slate-700"
            >
              <AlertOctagon class="w-3 h-3 text-slate-400" />
              <span>{{ tx.status }}</span>
            </span>

            <!-- Type Badge -->
            <span
              class="px-2 py-0.5 rounded-md text-[11px] font-mono font-bold border"
              :class="
                tx.transaction_type === 'WAIVER'
                  ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                  : tx.transaction_type === 'FREE_AGENT'
                    ? 'bg-sky-500/15 text-sky-300 border-sky-500/30'
                    : tx.transaction_type === 'DROP'
                      ? 'bg-slate-800 text-slate-300 border-slate-700'
                      : 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30'
              "
            >
              {{ tx.transaction_type }}
            </span>

            <span v-if="tx.week != null" class="text-[11px] font-mono text-slate-400">
              Wk {{ tx.week }}
            </span>
          </div>

          <div class="flex items-center gap-1 text-[11px] text-slate-500 font-mono">
            <Clock class="w-3 h-3 text-slate-600" />
            <span>{{ formatDate(tx.executed_at) }}</span>
          </div>
        </div>

        <!-- Manager / Team Row + FAAB Bid -->
        <div class="flex items-center justify-between gap-2 pt-2 border-t border-slate-800/60 mt-2">
          <div class="min-w-0">
            <span class="font-bold text-xs text-slate-100 truncate block" :title="tx.manager_name || 'System'">
              {{ tx.manager_name || 'League System' }}
            </span>
            <span v-if="tx.team_name" class="text-[11px] text-slate-400 truncate block" :title="tx.team_name">
              {{ tx.team_name }}
            </span>
          </div>

          <div v-if="tx.bid_amount != null" class="text-right shrink-0">
            <div
              class="text-xs font-mono font-black"
              :class="tx.status === 'FAILED' ? 'text-rose-400' : 'text-amber-300'"
            >
              ${{ tx.bid_amount }} FAAB
            </div>
            <div v-if="tx.waiver_priority != null" class="text-[10px] font-mono text-slate-500">
              Priority: #{{ tx.waiver_priority }}
            </div>
          </div>
        </div>

        <!-- Player Items Involved -->
        <div v-if="tx.items.length > 0" class="space-y-1.5 pt-2">
          <div
            v-for="item in tx.items"
            :key="`${tx.transaction_id}-${item.player_id}-${item.item_type}`"
            class="bg-slate-900/80 rounded-lg p-2 border border-slate-800/80 flex items-center justify-between gap-2"
          >
            <div class="flex items-center gap-2 min-w-0">
              <!-- Action Badge (ADD / DROP / TRADE) -->
              <span
                class="px-1.5 py-0.5 rounded text-[10px] font-mono font-black uppercase flex items-center gap-0.5 border shrink-0"
                :class="
                  item.item_type === 'ADD'
                    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                    : item.item_type === 'DROP'
                      ? 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                      : 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40'
                "
              >
                <Plus v-if="item.item_type === 'ADD'" class="w-2.5 h-2.5" />
                <Minus v-else-if="item.item_type === 'DROP'" class="w-2.5 h-2.5" />
                <ArrowRightLeft v-else class="w-2.5 h-2.5" />
                <span>{{ item.item_type }}</span>
              </span>

              <div class="min-w-0">
                <span class="font-bold text-xs text-slate-200 truncate block" :title="item.full_name">
                  {{ item.full_name }}
                </span>
                <span class="text-[10px] font-mono text-slate-400">
                  {{ item.default_position }} • {{ item.pro_team }}
                </span>
              </div>
            </div>

            <span
              class="px-1.5 py-0.2 rounded text-[10px] font-mono font-bold border shrink-0"
              :class="getPositionClass(item.default_position)"
            >
              {{ item.default_position }}
            </span>
          </div>
        </div>
      </div>

      <!-- Empty State -->
      <div
        v-if="filteredTransactions.length === 0"
        class="text-center py-8 text-slate-500 text-xs italic bg-slate-900/30 rounded-xl border border-slate-800/60"
      >
        No transactions match the selected filters.
      </div>
    </div>
  </div>
</template>
