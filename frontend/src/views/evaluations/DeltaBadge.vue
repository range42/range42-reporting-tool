<script setup lang="ts">
/**
 * Trend vs. the caller's own previous grade (D1c). Renders nothing unless both sides are
 * genuinely known — no zero, no dash implying parity — which also covers a `not_graded`
 * section (D8) and a caller with no own previous evaluation for free: both simply arrive here
 * as a null `current`/`previous`.
 */
import { computed } from 'vue'
import { TrendingDown, TrendingUp } from '@lucide/vue'
import { parseGrade } from '@/lib/decimal'

const props = defineProps<{
  current: string | null
  previous: string | null
}>()

/** Pure, DB/component-free: the two-decimal-string parsing happens before this is called. */
function computeDelta(current: number | null, previous: number | null): number | null {
  if (current === null || previous === null) return null
  const diff = Math.round((current - previous) * 100) / 100
  return diff === 0 ? null : diff
}

const delta = computed(() => computeDelta(parseGrade(props.current), parseGrade(props.previous)))
const isUp = computed(() => (delta.value ?? 0) > 0)
const label = computed(() => {
  if (delta.value === null) return ''
  return `${delta.value > 0 ? '+' : ''}${delta.value.toFixed(2)}`
})
</script>

<template>
  <span
    v-if="delta !== null"
    data-test="delta-badge"
    class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium tabular-nums"
    :class="
      isUp
        ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300'
        : 'bg-rose-100 text-rose-800 dark:bg-rose-500/15 dark:text-rose-300'
    "
  >
    <TrendingUp v-if="isUp" data-test="delta-icon-up" class="h-3 w-3" />
    <TrendingDown v-else data-test="delta-icon-down" class="h-3 w-3" />
    {{ label }}
  </span>
</template>
