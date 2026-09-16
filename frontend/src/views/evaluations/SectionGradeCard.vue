<script setup lang="ts">
/**
 * One section as the evaluator works it: submitted content, the criteria to grade against,
 * the grade control for the section's mode, and a feedback box.
 *
 * This is the CONTAINER of the trio — it owns the store wiring so `ReportContentPane`,
 * `EvaluationCriteria` and `GradeControl` stay presentational and reusable in the paired and
 * compare layouts.
 *
 * SAVE TIMING: edits land in the store immediately (so the preview and `canFinalize` react as
 * the evaluator types) but only reach the server on blur. Nothing here debounces —
 * `useEvaluationStore.flushAfter()` exists for that, so the autosave cadence belongs to the
 * whole view rather than to each card racing its own timer.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import ReportContentPane from '@/views/evaluations/ReportContentPane.vue'
import EvaluationCriteria from '@/views/evaluations/EvaluationCriteria.vue'
import GradeControl from '@/views/evaluations/GradeControl.vue'
import { useEvaluationStore } from '@/stores/evaluation'
import { parseGrade } from '@/lib/decimal'
import type { GradeUpsertInput } from '@/services/evaluations'

const props = defineProps<{ sectionId: string }>()

const { t, te } = useI18n()
const store = useEvaluationStore()

const section = computed(() => store.sectionsById[props.sectionId] ?? null)
const isGradable = computed(() => section.value?.grade_mode !== 'not_graded')
/** A finalized evaluation is closed for writes server-side; the UI must not invite them. */
const isLocked = computed(() => store.isFinalized)

const grade = computed(() => store.effectiveGrade(props.sectionId))
const storedGrade = computed(() => section.value?.grade ?? null)
/** The draft wins over the stored row: binding the box to the stored value makes it snap
 *  back on the re-render that the first keystroke itself triggers. */
const feedback = computed(() => store.effectiveFeedback(props.sectionId))

/** Save-error codes come from the API. Translate when we have a message, else show the
 *  code — an untranslated code is poor, but hiding a refused save is worse. */
const error = computed(() => {
  const code = store.errorFor(props.sectionId)
  if (code === null) return null
  const key = `evaluations.saveErrors.${code}`
  return te(key) ? t(key) : code
})

const meta = computed(() => {
  const s = section.value
  if (!s) return ''
  const weight = t('evaluations.weight', { weight: parseGrade(s.grade_weight) ?? 1 })
  if (s.grade_mode === 'not_graded') return t('evaluations.modeNotGraded')
  const mode =
    s.grade_mode === 'numeric'
      ? t('evaluations.modeNumeric', {
          min: parseGrade(s.grade_min) ?? 0,
          max: parseGrade(s.grade_max) ?? '—',
        })
      : t(s.grade_mode === 'pass_fail' ? 'evaluations.modePassFail' : 'evaluations.modeRubric')
  return `${mode} · ${weight}`
})

function onGradeUpdate(patch: GradeUpsertInput): void {
  store.setGrade(props.sectionId, patch)
}

function onFeedback(value: string): void {
  store.setGrade(props.sectionId, { feedback: value })
}

function save(): void {
  void store.flush()
}
</script>

<template>
  <section
    v-if="section"
    :data-test="`section-card-${sectionId}`"
    class="space-y-2 rounded-lg border border-[var(--rt-border)] p-3"
  >
    <p :data-test="`section-meta-${sectionId}`" class="text-xs text-[var(--rt-fg-muted)]">
      {{ meta }}
    </p>

    <ReportContentPane :section="section" />

    <EvaluationCriteria
      v-if="section.evaluation_criteria"
      :section-id="sectionId"
      :criteria="section.evaluation_criteria"
    />

    <div :data-test="`grade-${sectionId}`" @blur.capture="save">
      <GradeControl
        :section="section"
        :grade="grade"
        :pass-fail-result="storedGrade?.pass_fail_result ?? null"
        :rubric-scores="storedGrade?.rubric_scores ?? null"
        :error="error"
        :disabled="isLocked"
        @update="onGradeUpdate"
      />
    </div>

    <div v-if="isGradable">
      <label
        :for="`feedback-input-${sectionId}`"
        class="block text-[10px] font-medium uppercase tracking-wider text-[var(--rt-fg-muted)]"
      >
        {{ t('evaluations.feedbackLabel') }}
      </label>
      <textarea
        :id="`feedback-input-${sectionId}`"
        :data-test="`feedback-${sectionId}`"
        rows="2"
        :disabled="isLocked"
        :placeholder="t('evaluations.feedbackPlaceholder')"
        :value="feedback"
        class="w-full resize-none rounded-md border border-[var(--rt-border)] bg-[var(--rt-bg-elev)] p-2 text-xs"
        @input="onFeedback(($event.target as HTMLTextAreaElement).value)"
        @blur="save"
      />
    </div>
  </section>
</template>
