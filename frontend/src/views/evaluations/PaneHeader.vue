<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{
  /** Caller-supplied ("Previous" / "Current") — translated by the caller, not here. */
  label: string
  reportName: string
  teamName: string
  overallGrade: string | null
  gradeMax: string
  isCurrent?: boolean
}>()

const { t } = useI18n()
</script>

<template>
  <header class="flex items-center justify-between gap-3 border-b border-[var(--rt-border)] pb-2">
    <div class="min-w-0">
      <p class="text-[10px] font-medium uppercase tracking-wider text-[var(--rt-fg-muted)]">
        {{ label }}
        <span v-if="isCurrent" data-test="pane-being-graded" class="text-[var(--rt-accent)]">
          · {{ t('evaluations.campaignBeingGraded') }}
        </span>
      </p>
      <h3 class="truncate text-sm font-semibold">{{ reportName }}</h3>
      <p class="truncate text-xs text-[var(--rt-fg-muted)]">{{ teamName }}</p>
    </div>
    <div class="shrink-0 text-right">
      <span class="text-[10px] uppercase tracking-wider text-[var(--rt-fg-muted)]">
        {{ t('evaluations.overallGrade') }}
      </span>
      <p class="font-mono text-lg font-semibold tabular-nums" data-test="pane-grade">
        {{ overallGrade ?? '—' }} / {{ gradeMax }}
      </p>
    </div>
  </header>
</template>
