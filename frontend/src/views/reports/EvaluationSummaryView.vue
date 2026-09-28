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
import { sanitize } from '@/services/sanitize'
import type { ReportSection } from '@/services/reports'
import type { EvaluationSummary, SectionGradeSummary } from '@/services/evaluations'

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

function choicesFor(section: ReportSection): string[] {
  return section.choice_values ?? []
}

function safeContent(section: ReportSection): string {
  return section.content === null ? '' : sanitize(section.content)
}

function isEmpty(section: ReportSection): boolean {
  return choicesFor(section).length === 0 && safeContent(section).trim() === ''
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

    <article
      v-for="section in sections"
      :key="section.id"
      :data-test="`evaluation-summary-section-${section.section_def_id}`"
      class="rounded-lg border border-[var(--rt-border)] bg-[var(--rt-bg-elev)]"
    >
      <header class="border-b border-[var(--rt-border)] px-4 py-2.5">
        <h4 class="truncate text-sm font-semibold">{{ section.name }}</h4>
        <p v-if="section.description" class="truncate text-xs text-[var(--rt-fg-muted)]">
          {{ section.description }}
        </p>
      </header>

      <div class="px-4 py-3 text-sm">
        <ul v-if="choicesFor(section).length" class="flex flex-wrap gap-1.5">
          <li
            v-for="(choice, i) in choicesFor(section)"
            :key="`${section.id}-${i}`"
            class="rounded-full border border-[var(--rt-border)] px-2.5 py-0.5 text-xs"
          >
            {{ choice }}
          </li>
        </ul>
        <p v-else-if="isEmpty(section)" class="text-xs italic text-[var(--rt-fg-muted)]">
          {{ t('evaluations.emptySection') }}
        </p>
        <!-- eslint-disable-next-line vue/no-v-html -- sanitize() is the shared allowlist -->
        <div v-else class="prose-rt max-w-none" v-html="safeContent(section)" />

        <div v-if="gradeFor(section)" class="mt-3 border-t border-[var(--rt-border)] pt-2">
          <p class="text-xs text-[var(--rt-fg-muted)]">
            {{ t('evaluations.grade') }}:
            <span
              :data-test="`evaluation-summary-section-grade-${section.section_def_id}`"
              class="font-mono font-semibold tabular-nums text-[var(--rt-fg)]"
            >
              {{ gradeFor(section)!.grade ?? '—' }}
            </span>
          </p>
          <p
            v-if="gradeFor(section)!.feedback"
            :data-test="`evaluation-summary-section-feedback-${section.section_def_id}`"
            class="mt-1 text-xs text-[var(--rt-fg-muted)]"
          >
            {{ gradeFor(section)!.feedback }}
          </p>
        </div>
      </div>
    </article>
  </div>
</template>
