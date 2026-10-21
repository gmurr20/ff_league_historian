<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue';
import { X } from 'lucide-vue-next';

const props = withDefaults(
  defineProps<{
    modelValue: boolean;
    title?: string;
    subtitle?: string;
    maxHeight?: string;
  }>(),
  {
    maxHeight: 'max-h-[85vh]',
  }
);

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
  (e: 'close'): void;
}>();

const drawerRef = ref<HTMLElement | null>(null);
const contentRef = ref<HTMLElement | null>(null);
const startY = ref<number>(0);
const currentTranslateY = ref<number>(0);
const isDragging = ref<boolean>(false);

function close() {
  emit('update:modelValue', false);
  emit('close');
}

function handleTouchStart(e: TouchEvent) {
  // Only start drag if at the top of scrollable content
  if (contentRef.value && contentRef.value.scrollTop > 0) {
    return;
  }
  startY.value = e.touches[0].clientY;
  isDragging.value = true;
}

function handleTouchMove(e: TouchEvent) {
  if (!isDragging.value) return;
  const currentY = e.touches[0].clientY;
  const delta = currentY - startY.value;

  // Only allow downward drag
  if (delta > 0) {
    currentTranslateY.value = delta;
    if (e.cancelable) {
      e.preventDefault();
    }
  } else {
    currentTranslateY.value = 0;
  }
}

function handleTouchEnd() {
  if (!isDragging.value) return;
  isDragging.value = false;

  // If dragged down more than 75px, trigger close
  if (currentTranslateY.value > 75) {
    close();
  }
  currentTranslateY.value = 0;
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.modelValue) {
    close();
  }
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      document.body.style.overflow = 'hidden';
      currentTranslateY.value = 0;
    } else {
      document.body.style.overflow = '';
    }
  }
);

onMounted(() => {
  window.addEventListener('keydown', handleKeydown);
});

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown);
  document.body.style.overflow = '';
});
</script>

<template>
  <Teleport to="body">
    <!-- Backdrop -->
    <Transition
      enter-active-class="transition-opacity duration-200 ease-out"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition-opacity duration-150 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="modelValue"
        class="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm"
        @click="close"
        aria-hidden="true"
      ></div>
    </Transition>

    <!-- Bottom Sheet / Drawer -->
    <Transition
      enter-active-class="transition-transform duration-300 ease-out"
      enter-from-class="translate-y-full"
      enter-to-class="translate-y-0"
      leave-active-class="transition-transform duration-200 ease-in"
      leave-from-class="translate-y-0"
      leave-to-class="translate-y-full"
    >
      <div
        v-if="modelValue"
        ref="drawerRef"
        class="fixed inset-x-0 bottom-0 z-50 flex flex-col bg-slate-900 border-t border-slate-700/80 rounded-t-2xl shadow-2xl pb-safe overflow-hidden touch-pan-y"
        :class="maxHeight"
        :style="{
          transform: currentTranslateY > 0 ? `translateY(${currentTranslateY}px)` : undefined,
          transition: isDragging ? 'none' : 'transform 0.25s ease-out',
        }"
        role="dialog"
        aria-modal="true"
      >
        <!-- Swipe Handle Area -->
        <div
          class="pt-3 pb-2 cursor-grab active:cursor-grabbing shrink-0"
          @touchstart="handleTouchStart"
          @touchmove="handleTouchMove"
          @touchend="handleTouchEnd"
        >
          <div class="w-12 h-1.5 bg-slate-600 rounded-full mx-auto"></div>
        </div>

        <!-- Header -->
        <div
          v-if="title || $slots.header"
          class="px-4 pb-3 flex items-start justify-between border-b border-slate-800 shrink-0"
        >
          <slot name="header">
            <div>
              <h2 class="text-base font-bold text-slate-100 tracking-tight">
                {{ title }}
              </h2>
              <p v-if="subtitle" class="text-xs text-slate-400 mt-0.5">
                {{ subtitle }}
              </p>
            </div>
          </slot>
          <button
            type="button"
            class="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
            @click="close"
            aria-label="Close"
          >
            <X class="w-5 h-5" />
          </button>
        </div>

        <!-- Scrollable Content Body -->
        <div
          ref="contentRef"
          class="flex-1 overflow-y-auto px-4 py-4 overscroll-contain text-slate-200 text-sm"
        >
          <slot></slot>
        </div>

        <!-- Optional Footer -->
        <div
          v-if="$slots.footer"
          class="px-4 py-3 border-t border-slate-800 bg-slate-950/50 shrink-0"
        >
          <slot name="footer"></slot>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
