<script setup lang="ts">
/**
 * Read-only view of one section of the PREVIOUS report in a campaign pairing (D13: only the
 * current report is ever editable — no inputs here, not even disabled ones).
 *
 * D1b: previous content is always shown (report read scope), but the previous grade/feedback
 * are shown only when the caller has their OWN evaluation on that earlier report — gated on
 * `hasOwnPreviousEvaluation`, never inferred from whether `grade` happens to be non-null, so a
 * grade prop populated by a caller bug can never leak as if it were the caller's own.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { sanitize } from '@/services/sanitize'
import type { ReportSection } from '@/services/reports'
import type { SectionGrade } from '@/services/evaluations'

const props = defineProps<{
  section: ReportSection
  hasOwnPreviousEvaluation: boolean
  grade: SectionGrade | null
}>()

const { t } = useI18n()

const choices = computed<string[]>(() => props.section.choice_values ?? [])
const hasChoices = computed(() => choices.value.length > 0)
const safeContent = computed(() =>
  props.section.content === null ? '' : sanitize(props.section.content),
)
const isEmpty = computed(() => !hasChoices.value && safeContent.value.trim() === '')
const ownGrade = computed(() => (props.hasOwnPreviousEvaluation ? props.grade : null))
</script>

<template>
  <article
    :data-test="`prev-card-${section.section_def_id}`"
    class="rounded-lg border border-[var(--rt-border)] bg-[var(--rt-bg-elev)]"
  >
    <header class="border-b border-[var(--rt-border)] px-4 py-2.5">
      <h3 class="truncate text-sm font-semibold">{{ section.name }}</h3>
      <p v-if="section.description" class="truncate text-xs text-[var(--rt-fg-muted)]">
        {{ section.description }}
      </p>
    </header>

    <div class="px-4 py-3 text-sm">
      <ul v-if="hasChoices" class="flex flex-wrap gap-1.5">
        <li
          v-for="(choice, i) in choices"
          :key="`${section.id}-${i}`"
          class="rounded-full border border-[var(--rt-border)] px-2.5 py-0.5 text-xs"
        >
          {{ choice }}
        </li>
      </ul>

      <p
        v-else-if="isEmpty"
        data-test="prev-empty"
        class="text-xs italic text-[var(--rt-fg-muted)]"
      >
        {{ t('evaluations.emptySection') }}
      </p>

      <!-- eslint-disable-next-line vue/no-v-html -- sanitize() is the shared allowlist -->
      <div v-else class="prose-rt max-w-none" v-html="safeContent" />

      <p
        v-if="!hasOwnPreviousEvaluation"
        data-test="prev-not-evaluated"
        class="mt-3 text-xs italic text-[var(--rt-fg-muted)]"
      >
        {{ t('evaluations.campaignDidNotEvaluate') }}
      </p>
      <div v-else-if="ownGrade" class="mt-3 border-t border-[var(--rt-border)] pt-2">
        <p class="text-xs text-[var(--rt-fg-muted)]">
          {{ t('evaluations.grade') }}:
          <span
            data-test="prev-grade"
            class="font-mono font-semibold tabular-nums text-[var(--rt-fg)]"
          >
            {{ ownGrade.grade }}
          </span>
        </p>
        <p v-if="ownGrade.feedback" class="mt-1 text-xs text-[var(--rt-fg-muted)]">
          {{ ownGrade.feedback }}
        </p>
      </div>
    </div>
  </article>
</template>
