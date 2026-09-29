<script setup lang="ts">
/** Position pills #1..#N along one team's campaign timeline. An earlier pill pins that report
 * as the previous pane (`select`); the current pill is inert and later pills are disabled.
 * Status is a per-pill decoration only — "current" wins, evaluated is the next-most visible
 * state, and everything else (draft/submitted/under_evaluation) reads as "not evaluated yet". */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { TimelineEntry } from '@/services/campaigns'

const props = defineProps<{
  entries: TimelineEntry[]
  currentReportId: string
  /** The report shown in the previous pane, if any. */
  pinnedReportId?: string | null
}>()
const emit = defineEmits<{ select: [reportId: string] }>()

const { t } = useI18n()

type PillState = 'current' | 'evaluated' | 'pending'

const PILL_STYLE: Record<PillState, string> = {
  current: 'bg-[var(--rt-accent)] text-white',
  evaluated: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300',
  pending: 'bg-[var(--rt-border)] text-[var(--rt-fg-muted)]',
}

const currentIndex = computed(() =>
  props.entries.findIndex((e) => e.report_id === props.currentReportId),
)

function pillState(entry: TimelineEntry): PillState {
  if (entry.report_id === props.currentReportId) return 'current'
  if (entry.status === 'evaluated') return 'evaluated'
  return 'pending'
}

function isCurrent(entry: TimelineEntry): boolean {
  return entry.report_id === props.currentReportId
}

function isLater(index: number): boolean {
  return currentIndex.value >= 0 && index > currentIndex.value
}

function onClick(entry: TimelineEntry, index: number): void {
  if (isCurrent(entry) || isLater(index)) return
  emit('select', entry.report_id)
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
      :title="entry.name"
      :aria-current="isCurrent(entry) ? 'true' : undefined"
      :aria-pressed="isCurrent(entry) ? undefined : entry.report_id === pinnedReportId"
      :disabled="isLater(i)"
      :class="[
        'flex h-7 w-7 items-center justify-center rounded-full text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-40',
        PILL_STYLE[pillState(entry)],
        entry.report_id === pinnedReportId ? 'ring-2 ring-[var(--rt-accent)] ring-offset-1' : '',
      ]"
      @click="onClick(entry, i)"
    >
      {{ i + 1 }}
    </button>
  </nav>
</template>
