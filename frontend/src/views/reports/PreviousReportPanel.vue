<script setup lang="ts">
/**
 * Thin wrapper mounting `EvaluationSummaryView` with the writer-scoped previous-report state
 * from `useWriterPreviousReport`. A bonus reference panel, not a required element: renders
 * nothing for every status except `ready` — `no_campaign`/`no_previous`/`error` must not read
 * as an error state, since most reports are not part of any campaign at all.
 */
import { useI18n } from 'vue-i18n'
import EvaluationSummaryView from '@/views/reports/EvaluationSummaryView.vue'
import type { PreviousReportStatus } from '@/composables/useWriterPreviousReport'
import type { ReportDetail } from '@/services/reports'
import type { EvaluationSummary } from '@/services/evaluations'

defineProps<{
  status: PreviousReportStatus
  previousReport: ReportDetail | null
  previousSummary: EvaluationSummary | null
}>()

const { t } = useI18n()
</script>

<template>
  <div v-if="status === 'ready' && previousReport" data-test="previous-report-panel">
    <h3 class="mb-2 text-sm font-semibold text-[var(--rt-fg-muted)]">
      {{ t('reports.previousReportHeading') }}: {{ previousReport.name }}
    </h3>
    <EvaluationSummaryView :sections="previousReport.sections" :summary="previousSummary" />
  </div>
</template>
