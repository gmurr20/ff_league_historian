<script setup lang="ts">
import { AlertCircle, Inbox, RefreshCw } from 'lucide-vue-next';

withDefaults(
  defineProps<{
    title?: string;
    description?: string;
    isError?: boolean;
    actionText?: string;
  }>(),
  {
    title: 'No Data Available',
    isError: false,
  }
);

defineEmits<{
  (e: 'action'): void;
}>();
</script>

<template>
  <div
    class="w-full py-12 px-6 flex flex-col items-center justify-center text-center rounded-2xl bg-slate-900/40 border border-slate-800/60 my-4"
  >
    <!-- Icon Badge -->
    <div
      class="w-14 h-14 rounded-2xl flex items-center justify-center mb-4 transition-transform shadow-inner"
      :class="
        isError
          ? 'bg-rose-950/60 border border-rose-800/60 text-rose-400 shadow-rose-950/50'
          : 'bg-slate-800/80 border border-slate-700/60 text-slate-400 shadow-slate-900'
      "
    >
      <AlertCircle v-if="isError" class="w-7 h-7 stroke-[1.75px]" />
      <Inbox v-else class="w-7 h-7 stroke-[1.75px]" />
    </div>

    <!-- Title -->
    <h3 class="text-base font-bold text-slate-200 tracking-tight">
      {{ title }}
    </h3>

    <!-- Description -->
    <p v-if="description" class="text-xs sm:text-sm text-slate-400 max-w-sm mt-1.5 leading-relaxed">
      {{ description }}
    </p>

    <!-- Action Button (e.g. Retry or Backfill) -->
    <button
      v-if="actionText"
      type="button"
      class="mt-5 inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold tracking-wide transition-all active:scale-95 shadow-md"
      :class="
        isError
          ? 'bg-rose-600 hover:bg-rose-500 text-white shadow-rose-950/50'
          : 'bg-emerald-600 hover:bg-emerald-500 text-slate-950 shadow-emerald-950/50'
      "
      @click="$emit('action')"
    >
      <RefreshCw class="w-3.5 h-3.5 stroke-[2.25px]" />
      <span>{{ actionText }}</span>
    </button>
  </div>
</template>
