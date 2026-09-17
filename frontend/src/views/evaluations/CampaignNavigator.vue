<script setup lang="ts">
/** Position pills #1..#N along a campaign's timeline. Status is a per-pill decoration
 * only — the "current" entry always wins the priority, evaluated is the next-most
 * visible state, and everything else (draft/submitted/under_evaluation) reads as
 * "not evaluated yet" (D12: pixel-scroll-syncing is out of scope here). */
import { useI18n } from 'vue-i18n'
import type { TimelineEntry } from '@/services/campaigns'

defineProps<{
  entries: TimelineEntry[]
  currentReportId: string
}>()
const emit = defineEmits<{ select: [reportId: string] }>()

const { t } = useI18n()

type PillState = 'current' | 'evaluated' | 'pending'

const PILL_STYLE: Record<PillState, string> = {
  current: 'bg-[var(--rt-accent)] text-white',
  evaluated: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300',
  pending: 'bg-[var(--rt-border)] text-[var(--rt-fg-muted)]',
}

function pillState(entry: TimelineEntry, currentReportId: string): PillState {
  if (entry.report_id === currentReportId) return 'current'
  if (entry.status === 'evaluated') return 'evaluated'
  return 'pending'
}
</script>

<template>
  <nav :aria-label="t('evaluations.campaignNavAriaLabel')" class="flex flex-wrap gap-1.5">
    <button
      v-for="(entry, i) in entries"
      :key="entry.report_id"
      type="button"
      :data-test="`nav-pill-${entry.report_id}`"
      :data-status="entry.status"
      :aria-current="entry.report_id === currentReportId ? 'true' : undefined"
      :class="[
        'flex h-7 w-7 items-center justify-center rounded-full text-xs font-medium transition',
        PILL_STYLE[pillState(entry, currentReportId)],
      ]"
      @click="emit('select', entry.report_id)"
    >
      {{ i + 1 }}
    </button>
  </nav>
</template>
