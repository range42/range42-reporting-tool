<script setup lang="ts">
/**
 * The grading input for one section, in whichever mode its template declares.
 *
 * Mode dispatch is a MAP, not an if/else chain: each mode owns the translation from its
 * control's raw value to the `GradeUpsertInput` the service expects, so adding a mode means
 * adding a map entry and a template branch rather than editing a conditional others share.
 *
 * The range check here is a courtesy, not the enforcement: the store rejects an out-of-range
 * grade before it can be queued, and the server refuses it again. Showing it at the input is
 * what stops the evaluator discovering the problem one save later.
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import RubricGrid from '@/views/evaluations/RubricGrid.vue'
import { formatGrade, parseGrade } from '@/lib/decimal'
import type {
  GradableSection,
  GradeMode,
  GradeUpsertInput,
  RubricScoreEntry,
} from '@/services/evaluations'

const props = defineProps<{
  section: GradableSection
  grade: number | null
  passFailResult: boolean | null
  rubricScores: RubricScoreEntry[] | null
  /** A server-side error for this section, shown in place of the local range message. */
  error?: string | null
  /** Set once the evaluation is finalized: the server refuses writes, so the controls
   *  must stop inviting them — there is no edit-after-finalize. */
  disabled?: boolean
}>()
const emit = defineEmits<{ update: [GradeUpsertInput] }>()

const { t } = useI18n()

/** Raw input text, kept locally so the evaluator's typing survives a value the store
 *  refuses to hold — otherwise a rejected grade would vanish under the cursor. */
const raw = ref(formatGrade(props.grade) ?? '')
watch(
  () => props.grade,
  (next) => {
    if (parseGrade(raw.value) !== next) raw.value = formatGrade(next) ?? ''
  },
)

const min = computed(() => parseGrade(props.section.grade_min))
const max = computed(() => parseGrade(props.section.grade_max))
const sectionId = computed(() => props.section.report_section_id)
const numericId = computed(() => `grade-${sectionId.value}`)
const hintId = computed(() => `grade-hint-${sectionId.value}`)

/** Raw value -> the payload for that mode. The one place a control's value becomes a write. */
const UPDATE_BY_MODE: Record<
  GradeMode,
  (value: string | boolean | RubricScoreEntry[]) => GradeUpsertInput
> = {
  numeric: (value) => ({ grade: parseGrade(String(value)) }),
  pass_fail: (value) => ({ pass_fail_result: Boolean(value) }),
  rubric: (value) => ({ rubric_scores: value as RubricScoreEntry[] }),
  not_graded: () => ({}),
}

function push(value: string | boolean | RubricScoreEntry[]): void {
  emit('update', UPDATE_BY_MODE[props.section.grade_mode](value))
}

const parsed = computed(() => parseGrade(raw.value))
const isBlank = computed(() => raw.value.trim() === '')
const isMalformed = computed(() => !isBlank.value && parsed.value === null)
const isOutOfRange = computed(() => {
  if (parsed.value === null) return false
  if (min.value !== null && parsed.value < min.value) return true
  return max.value !== null && parsed.value > max.value
})
const message = computed(() => {
  if (props.error) return props.error
  if (isMalformed.value) return t('evaluations.badNumber')
  return isOutOfRange.value ? t('evaluations.outOfRange') : null
})

function onNumeric(value: string): void {
  raw.value = value
  push(value)
}
</script>

<template>
  <div :data-test="`grade-control-${sectionId}`">
    <template v-if="section.grade_mode === 'numeric'">
      <label
        :for="numericId"
        class="block text-[10px] font-medium uppercase tracking-wider text-[var(--rt-fg-muted)]"
      >
        {{ t('evaluations.grade') }}
      </label>
      <div class="flex items-center gap-1.5">
        <input
          :id="numericId"
          :data-test="`grade-numeric-${sectionId}`"
          type="number"
          inputmode="decimal"
          :min="min ?? undefined"
          :max="max ?? undefined"
          step="0.01"
          :disabled="disabled"
          :value="raw"
          :aria-invalid="message !== null ? 'true' : 'false'"
          :aria-describedby="hintId"
          class="h-8 w-20 rounded-md border border-[var(--rt-border)] bg-[var(--rt-bg-elev)] px-2 font-mono text-sm"
          @input="onNumeric(($event.target as HTMLInputElement).value)"
        />
        <span v-if="max !== null" class="text-xs text-[var(--rt-fg-muted)]">/ {{ max }}</span>
      </div>
      <p :id="hintId" class="mt-0.5 text-[11px] text-[var(--rt-fg-muted)]">
        {{ t('evaluations.gradeRange', { min: min ?? 0, max: max ?? '—' }) }}
      </p>
      <p v-if="message" :data-test="`grade-error-${sectionId}`" class="text-[11px] text-red-500">
        {{ message }}
      </p>
    </template>

    <template v-else-if="section.grade_mode === 'pass_fail'">
      <span
        class="block text-[10px] font-medium uppercase tracking-wider text-[var(--rt-fg-muted)]"
      >
        {{ t('evaluations.grade') }}
      </span>
      <div
        class="inline-flex overflow-hidden rounded-md border border-[var(--rt-border)]"
        role="group"
      >
        <button
          :data-test="`grade-pass-${sectionId}`"
          type="button"
          :disabled="disabled"
          :aria-pressed="passFailResult === true"
          class="px-3 py-1 text-xs aria-pressed:bg-[var(--rt-accent)] aria-pressed:text-white"
          @click="push(true)"
        >
          {{ t('evaluations.pass') }}
        </button>
        <button
          :data-test="`grade-fail-${sectionId}`"
          type="button"
          :disabled="disabled"
          :aria-pressed="passFailResult === false"
          class="border-l border-[var(--rt-border)] px-3 py-1 text-xs aria-pressed:bg-[var(--rt-accent)] aria-pressed:text-white"
          @click="push(false)"
        >
          {{ t('evaluations.fail') }}
        </button>
      </div>
    </template>

    <template v-else-if="section.grade_mode === 'rubric'">
      <RubricGrid
        :section-id="sectionId"
        :criteria="section.rubric_criteria ?? []"
        :scores="rubricScores"
        :grade-min="min"
        :grade-max="max"
        :disabled="disabled"
        @update="push"
      />
    </template>

    <template v-else>
      <p
        :data-test="`grade-not-graded-${sectionId}`"
        class="text-[11px] italic text-[var(--rt-fg-muted)]"
      >
        {{ t('evaluations.notGraded') }}
      </p>
    </template>
  </div>
</template>
