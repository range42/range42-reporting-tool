<script setup lang="ts">
/**
 * Route-level "view evaluation" screen — opens for ANY report, regardless of status. Content
 * is always fetched and shown; the evaluation summary is best-effort: a 409 from
 * `getReportEvaluationSummary` (not yet evaluated, or hidden by
 * `scoring_config.teams_see_own_scores`) is expected and simply leaves `summary` null, never
 * surfaced as an error. Any other failure — including the report itself failing to load — is
 * a real error.
 */
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { TriangleAlert } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/services/http'
import AppShell from '@/components/AppShell.vue'
import { getReport, type ReportDetail } from '@/services/reports'
import { getReportEvaluationSummary, type EvaluationSummary } from '@/services/evaluations'
import EvaluationSummaryView from '@/views/reports/EvaluationSummaryView.vue'

const { t } = useI18n()
const route = useRoute()
const auth = useAuthStore()

const exerciseId = String(route.params.exerciseId)
const rid = String(route.params.rid)

const report = ref<ReportDetail | null>(null)
const summary = ref<EvaluationSummary | null>(null)
const error = ref('')

onMounted(async () => {
  if (!auth.token) return
  try {
    report.value = await getReport(auth.token, exerciseId, rid)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('reports.loadError')
    return
  }
  try {
    summary.value = await getReportEvaluationSummary(auth.token, exerciseId, rid)
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) {
      summary.value = null
    } else {
      error.value = e instanceof ApiError ? e.message : t('reports.loadError')
    }
  }
})
</script>

<template>
  <AppShell :title="report?.name ?? t('reports.title')">
    <div class="mx-auto max-w-3xl">
      <div
        v-if="error"
        data-test="evaluation-summary-load-error"
        class="mb-4 flex items-center gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-600 dark:text-red-400"
      >
        <TriangleAlert class="h-4 w-4 shrink-0" />
        <span>{{ error }}</span>
      </div>

      <EvaluationSummaryView v-if="report" :sections="report.sections" :summary="summary" />
    </div>
  </AppShell>
</template>
