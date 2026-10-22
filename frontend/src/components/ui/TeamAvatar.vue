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

const hasLogo = computed(() => {
  return Boolean(props.src && !imgFailed.value);
});

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

// Deterministic aesthetic gradient and border for non-generic team initials
const colorTheme = computed(() => {
  const raw = (props.name || 'Team').trim();
  let hash = 0;
  for (let i = 0; i < raw.length; i++) {
    hash = (hash << 5) - hash + raw.charCodeAt(i);
    hash |= 0;
  }
  const palettes = [
    { bg: 'bg-gradient-to-br from-emerald-950/80 to-slate-900', border: 'border-emerald-500/30', text: 'text-emerald-400' },
    { bg: 'bg-gradient-to-br from-amber-950/80 to-slate-900', border: 'border-amber-500/30', text: 'text-amber-400' },
    { bg: 'bg-gradient-to-br from-sky-950/80 to-slate-900', border: 'border-sky-500/30', text: 'text-sky-400' },
    { bg: 'bg-gradient-to-br from-violet-950/80 to-slate-900', border: 'border-violet-500/30', text: 'text-violet-400' },
    { bg: 'bg-gradient-to-br from-rose-950/80 to-slate-900', border: 'border-rose-500/30', text: 'text-rose-400' },
    { bg: 'bg-gradient-to-br from-teal-950/80 to-slate-900', border: 'border-teal-500/30', text: 'text-teal-400' },
    { bg: 'bg-gradient-to-br from-indigo-950/80 to-slate-900', border: 'border-indigo-500/30', text: 'text-indigo-400' },
  ];
  return palettes[Math.abs(hash) % palettes.length];
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
    class="relative overflow-hidden shrink-0 flex items-center justify-center shadow-inner select-none transition-transform"
    :class="[
      sizeClasses,
      roundedClass,
      hasLogo ? 'bg-slate-800/90 border border-slate-700/80' : `${colorTheme.bg} border ${colorTheme.border}`
    ]"
  >
    <img
      v-if="hasLogo"
      :src="src!"
      :alt="name || 'Team Avatar'"
      class="w-full h-full object-cover"
      loading="lazy"
      @error="imgFailed = true"
    />
    <span
      v-else
      class="font-black font-mono tracking-wider leading-none"
      :class="colorTheme.text"
    >
      {{ initials }}
    </span>
  </div>
</template>
