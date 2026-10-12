<script setup lang="ts">
/**
 * Header for one evaluation: which report this is, whose it is, and the view-mode switch.
 *
 * `teamName` and `submittedAt` are optional because they are not the evaluator's to see —
 * they come from a report row that `GET …/reports/{rid}` refuses to a non-member, so the
 * header renders without them rather than blocking on context it may never get.
 */
import { useI18n } from 'vue-i18n'
import ViewModeSwitch from '@/views/evaluations/ViewModeSwitch.vue'
import type { RouteLocationNamedRaw } from 'vue-router'

const props = withDefaults(
  defineProps<{
    reportName: string
    reportStatus: string
    teamName: string | null
    submittedAt: string | null
    campaignTo: RouteLocationNamedRaw | null
    mode?: 'single' | 'campaign'
    singleTo?: RouteLocationNamedRaw | null
  }>(),
  { mode: 'single', singleTo: null },
)

const { t } = useI18n()

const submittedLabel = (): string =>
  props.submittedAt === null
    ? ''
    : t('evaluations.submittedAt', { when: new Date(props.submittedAt).toLocaleString() })
</script>

<template>
  <header data-test="evaluation-header" class="mb-4 space-y-1">
    <div class="flex flex-wrap items-baseline justify-between gap-3">
      <h1 class="text-lg font-semibold">{{ reportName }}</h1>
      <ViewModeSwitch :campaign-to="campaignTo" :mode="mode" :single-to="singleTo" />
    </div>
    <p class="flex flex-wrap items-baseline gap-3 text-xs text-[var(--rt-fg-muted)]">
      <span v-if="teamName" data-test="evaluation-team">{{ teamName }}</span>
      <span v-if="submittedAt" data-test="evaluation-submitted">{{ submittedLabel() }}</span>
      <span>{{ reportStatus }}</span>
    </p>
  </header>
</template>
