<script setup lang="ts">
/**
 * Read-only report content plus its evaluation summary, shared by the report list's "view
 * evaluation" affordance and the writer's previous-report campaign panel.
 *
 * Section content is ALWAYS shown (report read scope — `reports:read:own` already covers it).
 * The overall grade/feedback and each section's grade/feedback render only when `summary` is
 * non-null: `summary === null` is a normal, expected state (not yet evaluated, or hidden by
 * `scoring_config.teams_see_own_scores`), never an error — callers pass `null` on a 409 from
 * `getReportEvaluationSummary`, not a caught exception message.
 *
 * SECURITY: section content is writer-authored HTML, i.e. untrusted. It reaches `v-html` only
 * through `sanitize()`, never raw. `choice_values` render as TEXT, never markup.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ReportSection } from '@/services/reports'
import type { EvaluationSummary, SectionGradeSummary } from '@/services/evaluations'
import EvaluationSummarySection from '@/views/reports/EvaluationSummarySection.vue'

const props = defineProps<{
  sections: ReportSection[]
  summary: EvaluationSummary | null
}>()

const { t } = useI18n()

const gradesBySectionDefId = computed<Map<string, SectionGradeSummary>>(() => {
  const map = new Map<string, SectionGradeSummary>()
  for (const g of props.summary?.section_grades ?? []) map.set(g.section_def_id, g)
  return map
})

function gradeFor(section: ReportSection): SectionGradeSummary | null {
  return gradesBySectionDefId.value.get(section.section_def_id) ?? null
}
</script>

<template>
  <div class="space-y-3">
    <div
      v-if="summary"
      data-test="evaluation-summary-overall"
      class="rounded-lg border border-[var(--rt-border)] bg-[var(--rt-bg-elev)] px-4 py-3"
    >
      <p class="text-xs text-[var(--rt-fg-muted)]">
        {{ t('evaluations.overallGrade') }}:
        <span class="font-mono font-semibold tabular-nums text-[var(--rt-fg)]">
          {{ summary.overall_grade ?? '—' }}
        </span>
      </p>
      <p v-if="summary.overall_feedback" class="mt-1 text-xs text-[var(--rt-fg-muted)]">
        {{ summary.overall_feedback }}
      </p>
    </div>
    <p v-else class="text-xs italic text-[var(--rt-fg-muted)]">
      {{ t('evaluations.evaluationSummaryPending') }}
    </p>

    <EvaluationSummarySection
      v-for="section in sections"
      :key="section.id"
      :section="section"
      :grade="gradeFor(section)"
    />
  </div>
</template>
