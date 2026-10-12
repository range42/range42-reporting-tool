<script setup lang="ts">
/**
 * One section's read-only content plus its grade/feedback, extracted from
 * `EvaluationSummaryView.vue` so it can also be used as one side of a paired row (the
 * writer's side-by-side previous-report view, mirroring the evaluator's
 * `CampaignSectionRow.vue`/`PreviousSectionCard.vue` pattern) without duplicating the
 * sanitize-and-render logic.
 *
 * SECURITY: section content is writer-authored HTML, i.e. untrusted. It reaches `v-html` only
 * through `sanitize()`, never raw. `choice_values` render as TEXT, never markup.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { sanitize } from '@/services/sanitize'
import type { ReportSection } from '@/services/reports'
import type { SectionGradeSummary } from '@/services/evaluations'

const props = defineProps<{
  section: ReportSection
  grade: SectionGradeSummary | null
}>()

const { t } = useI18n()

const choices = computed<string[]>(() => props.section.choice_values ?? [])
const safeContent = computed(() =>
  props.section.content === null ? '' : sanitize(props.section.content),
)
const isEmpty = computed(() => choices.value.length === 0 && safeContent.value.trim() === '')
</script>

<template>
  <article
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
      <ul v-if="choices.length" class="flex flex-wrap gap-1.5">
        <li
          v-for="(choice, i) in choices"
          :key="`${section.id}-${i}`"
          class="rounded-full border border-[var(--rt-border)] px-2.5 py-0.5 text-xs"
        >
          {{ choice }}
        </li>
      </ul>
      <p v-else-if="isEmpty" class="text-xs italic text-[var(--rt-fg-muted)]">
        {{ t('evaluations.emptySection') }}
      </p>
      <!-- eslint-disable-next-line vue/no-v-html -- sanitize() is the shared allowlist -->
      <div v-else class="prose-rt max-w-none" v-html="safeContent" />

      <div v-if="grade" class="mt-3 border-t border-[var(--rt-border)] pt-2">
        <p class="text-xs text-[var(--rt-fg-muted)]">
          {{ t('evaluations.grade') }}:
          <span
            :data-test="`evaluation-summary-section-grade-${section.section_def_id}`"
            class="font-mono font-semibold tabular-nums text-[var(--rt-fg)]"
          >
            {{ grade.grade ?? '—' }}
          </span>
        </p>
        <p
          v-if="grade.feedback"
          :data-test="`evaluation-summary-section-feedback-${section.section_def_id}`"
          class="mt-1 text-xs text-[var(--rt-fg-muted)]"
        >
          {{ grade.feedback }}
        </p>
      </div>
    </div>
  </article>
</template>
