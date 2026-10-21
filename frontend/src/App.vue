<script setup lang="ts">
import { onMounted } from 'vue';
import { useLeagueMeta } from '@/composables/useLeagueMeta';
import TopHeader from '@/components/layout/TopHeader.vue';
import BottomNav from '@/components/layout/BottomNav.vue';
import LoadingState from '@/components/ui/LoadingState.vue';
import EmptyState from '@/components/ui/EmptyState.vue';

const { loading, error, loadMeta } = useLeagueMeta();

onMounted(async () => {
  await loadMeta();
});
</script>

<template>
  <div class="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-emerald-500 selection:text-slate-950">
    <!-- Top Sticky Stadium Header -->
    <TopHeader />

    <!-- Main Viewport Area -->
    <main class="flex-1 w-full max-w-7xl mx-auto px-3 sm:px-4 py-4 mb-16 sm:mb-20">
      <!-- Initial Loading State -->
      <div v-if="loading" class="py-12">
        <LoadingState message="Connecting to League Archive..." variant="spinner" />
      </div>

      <!-- Network / Server Error Fallback -->
      <div v-else-if="error" class="py-8">
        <EmptyState
          title="Could Not Connect to League API"
          :description="error"
          :is-error="true"
          action-text="Retry Connection"
          @action="loadMeta(true)"
        />
      </div>

      <!-- Active Route Content -->
      <router-view v-else v-slot="{ Component }">
        <transition
          enter-active-class="transition duration-150 ease-out"
          enter-from-class="opacity-0 translate-y-1"
          enter-to-class="opacity-100 translate-y-0"
          mode="out-in"
        >
          <component :is="Component" />
        </transition>
      </router-view>
    </main>

    <!-- Fixed Stadium Mobile Bottom Navigation Bar -->
    <BottomNav />
  </div>
</template>
