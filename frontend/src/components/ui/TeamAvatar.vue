<script setup lang="ts">
import { ref, computed, watch } from 'vue';

const props = withDefaults(
  defineProps<{
    src?: string | null;
    name?: string | null;
    size?: 'xs' | 'sm' | 'md' | 'lg';
    rounded?: 'full' | 'xl' | 'lg';
  }>(),
  {
    src: null,
    name: '',
    size: 'md',
    rounded: 'xl',
  }
);

const imgFailed = ref(false);

watch(
  () => props.src,
  () => {
    imgFailed.value = false;
  }
);

const initials = computed(() => {
  const raw = (props.name || '').trim();
  if (!raw) return '?';
  const words = raw
    .replace(/[^a-zA-Z0-9\s]/g, '')
    .split(/\s+/)
    .filter((w) => w.length > 0 && w.toLowerCase() !== 'the');
  if (words.length >= 2) {
    return `${words[0][0]}${words[1][0]}`.toUpperCase();
  }
  if (words.length === 1) {
    return words[0].slice(0, 2).toUpperCase();
  }
  return raw.slice(0, 2).toUpperCase();
});

const sizeClasses = computed(() => {
  switch (props.size) {
    case 'xs':
      return 'w-6 h-6 text-[10px]';
    case 'sm':
      return 'w-8 h-8 text-xs';
    case 'lg':
      return 'w-12 h-12 text-sm';
    case 'md':
    default:
      return 'w-9 h-9 text-xs';
  }
});

const roundedClass = computed(() => {
  switch (props.rounded) {
    case 'full':
      return 'rounded-full';
    case 'lg':
      return 'rounded-lg';
    case 'xl':
    default:
      return 'rounded-xl';
  }
});
</script>

<template>
  <div
    class="relative bg-slate-800/90 border border-slate-700/80 overflow-hidden shrink-0 flex items-center justify-center shadow-inner select-none"
    :class="[sizeClasses, roundedClass]"
  >
    <img
      v-if="src && !imgFailed"
      :src="src"
      :alt="name || 'Team Avatar'"
      class="w-full h-full object-cover"
      loading="lazy"
      @error="imgFailed = true"
    />
    <span
      v-else
      class="font-black font-mono text-slate-300 tracking-tighter leading-none"
    >
      {{ initials }}
    </span>
  </div>
</template>
