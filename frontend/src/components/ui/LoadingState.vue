<script setup lang="ts">
withDefaults(
  defineProps<{
    message?: string;
    variant?: 'skeleton' | 'spinner' | 'cards';
    rows?: number;
  }>(),
  {
    message: 'Loading league records...',
    variant: 'skeleton',
    rows: 4,
  }
);
</script>

<template>
  <div class="w-full py-8 px-4 flex flex-col items-center justify-center animate-fadeIn">
    <!-- Spinner Variant -->
    <div v-if="variant === 'spinner'" class="flex flex-col items-center gap-3">
      <div class="relative w-10 h-10">
        <div class="absolute inset-0 rounded-full border-2 border-slate-800"></div>
        <div
          class="absolute inset-0 rounded-full border-2 border-emerald-500 border-t-transparent animate-spin"
        ></div>
      </div>
      <p v-if="message" class="text-xs font-medium text-slate-400 tracking-wide uppercase">
        {{ message }}
      </p>
    </div>

    <!-- Cards Variant -->
    <div v-else-if="variant === 'cards'" class="w-full space-y-3">
      <div
        v-for="i in rows"
        :key="i"
        class="w-full p-4 rounded-xl bg-slate-900/80 border border-slate-800/80 animate-pulse space-y-3"
      >
        <div class="flex items-center justify-between">
          <div class="h-4 bg-slate-800 rounded w-1/3"></div>
          <div class="h-4 bg-slate-800 rounded w-1/6"></div>
        </div>
        <div class="h-3 bg-slate-800/60 rounded w-2/3"></div>
      </div>
    </div>

    <!-- Skeleton Table / List Variant (Default) -->
    <div v-else class="w-full space-y-2.5">
      <div
        v-for="i in rows"
        :key="i"
        class="w-full h-14 rounded-lg bg-slate-900/70 border border-slate-800/60 p-3 flex items-center justify-between animate-pulse"
      >
        <div class="flex items-center gap-3 w-3/5">
          <div class="w-8 h-8 rounded-full bg-slate-800 shrink-0"></div>
          <div class="space-y-1.5 w-full">
            <div class="h-3.5 bg-slate-800 rounded w-3/4"></div>
            <div class="h-2.5 bg-slate-800/60 rounded w-1/2"></div>
          </div>
        </div>
        <div class="h-5 bg-slate-800 rounded w-16 shrink-0"></div>
      </div>
      <p v-if="message" class="text-center text-xs text-slate-500 mt-4 font-mono">
        {{ message }}
      </p>
    </div>
  </div>
</template>
