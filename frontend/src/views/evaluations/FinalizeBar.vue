<script setup lang="ts">
/**
 * The sticky bottom bar: where the evaluator sees their overall number, writes the summary
 * feedback, and finalizes.
 *
 * WHICH NUMBER IS SHOWN. The server's `overall_grade` wins whenever it exists; the local
 * weighted preview only fills the gap before the first save, and is labelled provisional so
 * nobody quotes it (`rollup.py` is canonical).
 *
 * THE WAITING NOTE CARRIES NO HEADCOUNT. An evaluator who finalizes first is told the report
 * grade is not published yet — but not how many peers remain, nor who they are. The aggregate
 * does carry a headcount and is deliberately not used here: evaluator isolation.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { finalizeEvaluation, updateEvaluation } from '@/services/evaluations'
import { useAuthStore } from '@/stores/auth'
import { useEvaluationStore } from '@/stores/evaluation'
import { formatGrade } from '@/lib/decimal'

const props = defineProps<{ exerciseId: string; rid: string; evid: string }>()

const ALL_MUST_FINALIZE = 'all_must_finalize'

const { t } = useI18n()
const auth = useAuthStore()
const store = useEvaluationStore()

const isFinalizing = ref(false)
const isWaitingOnOthers = ref(false)
const isDone = ref(false)
const failed = ref(false)
const feedback = ref(store.detail?.overall_feedback ?? '')

const serverGrade = computed(() => store.detail?.overall_grade ?? null)
const isProvisional = computed(() => serverGrade.value === null && store.previewGrade !== null)
const shownGrade = computed(() => serverGrade.value ?? formatGrade(store.previewGrade) ?? '—')

const remaining = computed(() => Math.max(store.gradableCount - store.gradedCount, 0))
/** True from the moment the server accepts the finalize, and on every later visit. */
const isFinalized = computed(() => store.isFinalized || isDone.value)
const canFinalize = computed(() => store.canFinalize && !isFinalizing.value && !isFinalized.value)

async function onFinalize(): Promise<void> {
  if (!canFinalize.value || !auth.token) return
  isFinalizing.value = true
  failed.value = false
  try {
    const breakdown = await finalizeEvaluation(auth.token, props.exerciseId, props.rid, props.evid)
    isDone.value = true
    // The server has closed the evaluation for writes; lock the grading surface with it.
    store.markFinalized()
    isWaitingOnOthers.value =
      breakdown.finalize_policy === ALL_MUST_FINALIZE && !breakdown.finalize_gate_satisfied
  } catch {
    failed.value = true
  } finally {
    isFinalizing.value = false
  }
}

/** Overall feedback lives on the evaluation, not on a section, so it PATCHes separately.
 *  A finalized evaluation refuses the PATCH, so it is not attempted. */
async function onFeedbackBlur(): Promise<void> {
  if (!auth.token || isFinalized.value) return
  const next = feedback.value.trim() === '' ? null : feedback.value
  if (next === (store.detail?.overall_feedback ?? null)) return
  try {
    await updateEvaluation(auth.token, props.exerciseId, props.rid, props.evid, {
      overall_feedback: next,
    })
  } catch {
    failed.value = true
  }
}
</script>

<template>
  <div
    data-test="finalize-bar"
    class="sticky bottom-0 z-20 border-t border-[var(--rt-border)] bg-[var(--rt-bg-elev)]/90 backdrop-blur"
  >
    <div class="mx-auto flex max-w-[1800px] flex-wrap items-center gap-4 px-4 py-3">
      <div class="flex items-baseline gap-2">
        <span class="text-xs text-[var(--rt-fg-muted)]">{{ t('evaluations.overallGrade') }}</span>
        <output
          data-test="finalize-grade"
          class="font-mono text-lg font-semibold tabular-nums text-[var(--rt-accent)]"
        >
          {{ shownGrade }}
        </output>
        <span
          v-if="isProvisional"
          data-test="finalize-provisional"
          class="text-[10px] uppercase tracking-wider text-[var(--rt-fg-muted)]"
        >
          {{ t('evaluations.provisional') }}
        </span>
      </div>

      <p data-test="finalize-remaining" class="text-xs text-[var(--rt-fg-muted)]">
        {{
          remaining === 0
            ? t('evaluations.allGraded')
            : t('evaluations.remaining', { count: remaining, total: store.gradableCount })
        }}
      </p>

      <div class="min-w-[280px] flex-1">
        <label for="finalize-feedback-input" class="sr-only">
          {{ t('evaluations.overallFeedbackLabel') }}
        </label>
        <input
          id="finalize-feedback-input"
          v-model="feedback"
          data-test="finalize-feedback"
          type="text"
          :disabled="isFinalized"
          :placeholder="t('evaluations.overallFeedbackPlaceholder')"
          class="h-9 w-full rounded-md border border-[var(--rt-border)] bg-[var(--rt-bg-elev)] px-3 text-sm"
          @blur="onFeedbackBlur"
        />
      </div>

      <button
        data-test="finalize-btn"
        type="button"
        :disabled="!canFinalize"
        class="h-9 rounded-md bg-emerald-600 px-3 text-sm font-medium text-white transition-opacity duration-150 hover:opacity-90 disabled:opacity-50"
        @click="onFinalize"
      >
        {{ isFinalizing ? t('evaluations.finalizing') : t('evaluations.finalize') }}
      </button>
    </div>

    <p
      v-if="isWaitingOnOthers"
      data-test="finalize-waiting"
      class="px-4 pb-2 text-xs text-[var(--rt-fg-muted)]"
    >
      {{ t('evaluations.waitingOthers') }}
    </p>
    <p v-else-if="isFinalized" data-test="finalize-done" class="px-4 pb-2 text-xs text-emerald-600">
      {{ t('evaluations.finalized') }}
    </p>
    <p v-if="failed" data-test="finalize-error" class="px-4 pb-2 text-xs text-red-500">
      {{ t('evaluations.finalizeFailed') }}
    </p>
  </div>
</template>
