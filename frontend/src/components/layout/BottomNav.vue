<script setup lang="ts">
import { useRoute } from 'vue-router';
import { Trophy, DollarSign, Award, ArrowLeftRight, Zap } from 'lucide-vue-next';

interface NavItem {
  name: string;
  label: string;
  to: string;
  icon: any;
}

const navItems: NavItem[] = [
  { name: 'standings', label: 'Standings', to: '/', icon: Trophy },
  { name: 'earnings', label: 'Earnings', to: '/earnings', icon: DollarSign },
  { name: 'hall-of-fame', label: 'Hall of Fame', to: '/hall-of-fame', icon: Award },
  { name: 'trades', label: 'Trades', to: '/trades', icon: ArrowLeftRight },
  { name: 'waivers', label: 'Waivers', to: '/waivers', icon: Zap },
];

const route = useRoute();

function isActive(to: string): boolean {
  if (to === '/') {
    return route.path === '/';
  }
  return route.path.startsWith(to);
}
</script>

<template>
  <nav
    class="fixed bottom-0 inset-x-0 z-40 bg-slate-950/95 backdrop-blur-lg border-t border-slate-800/80 pb-safe transition-all select-none"
    aria-label="Primary Navigation"
  >
    <div class="max-w-md mx-auto grid grid-cols-5 h-14 sm:h-16">
      <router-link
        v-for="item in navItems"
        :key="item.name"
        :to="item.to"
        class="relative flex flex-col items-center justify-center min-h-[56px] px-1 py-1 text-center transition-colors group"
        :class="isActive(item.to) ? 'text-emerald-400' : 'text-slate-400 hover:text-slate-200'"
      >
        <!-- Active indicator pill at top of tab -->
        <span
          v-if="isActive(item.to)"
          class="absolute top-0 w-8 h-0.5 rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]"
        ></span>

        <!-- Icon with subtle bounce/glow on active -->
        <component
          :is="item.icon"
          class="w-5 h-5 transition-transform group-active:scale-90"
          :class="isActive(item.to) ? 'stroke-[2.5px]' : 'stroke-[1.75px]'"
        />

        <!-- Label -->
        <span
          class="text-[9.5px] sm:text-[10px] tracking-tight font-medium mt-1 truncate max-w-full"
          :class="isActive(item.to) ? 'font-semibold text-emerald-400' : 'text-slate-400'"
        >
          {{ item.label }}
        </span>
      </router-link>
    </div>
  </nav>
</template>
