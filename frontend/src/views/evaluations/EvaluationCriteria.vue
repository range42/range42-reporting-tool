<script setup lang="ts">
/**
 * The template's evaluation criteria for one section — the guidance the evaluator grades
 * against.
 *
 * EVALUATOR-ONLY (L12). This field reaches the client on `GradableSection` and nowhere else;
 * it is deliberately absent from the writer-facing `ReportSectionOut`, so this component must
 * never be reused on a writer surface. It is free text in the database, not HTML, and is
 * rendered as text: no `v-html` here, on purpose.
 */
import { useI18n } from 'vue-i18n'

defineProps<{ sectionId: string; criteria: string }>()

const { t } = useI18n()
</script>

<template>
  <aside
    :data-test="`criteria-${sectionId}`"
    class="rounded-md border border-dashed border-[var(--rt-border)] px-3 py-2"
  >
    <p class="flex items-baseline gap-2">
      <span class="text-[10px] font-medium uppercase tracking-wider text-[var(--rt-fg-muted)]">
        {{ t('evaluations.criteriaHeading') }}
      </span>
      <span class="text-[10px] italic text-[var(--rt-fg-muted)]">
        {{ t('evaluations.criteriaEvaluatorOnly') }}
      </span>
    </p>
    <p class="mt-1 whitespace-pre-line text-xs">{{ criteria }}</p>
  </aside>
</template>
