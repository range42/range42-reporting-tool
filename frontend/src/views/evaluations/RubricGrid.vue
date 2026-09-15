<script setup lang="ts">
/**
 * One scored row per rubric criterion, plus a provisional section rollup.
 *
 * Presentational: the parent owns the scores and the save. Every change emits the COMPLETE
 * `rubric_scores` array, because the server replaces the whole column rather than merging
 * one criterion into it — emitting a single row would silently drop the others.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { rubricRollupPreview } from '@/lib/scoringPreview'
import type { RubricScoreEntry } from '@/services/evaluations'
import type { RubricCriterion } from '@/services/templates'

const props = defineProps<{
  sectionId: string
  criteria: RubricCriterion[]
  scores: RubricScoreEntry[] | null
  gradeMin: number | null
  gradeMax: number | null
  disabled?: boolean
}>()
const emit = defineEmits<{ update: [RubricScoreEntry[]] }>()

const { t } = useI18n()

const scoreByCriterion = computed(() => new Map((props.scores ?? []).map((s) => [s.criterion, s])))

const rollup = computed(() => {
  // Blank until every criterion is scored: a partial rubric average reads as a finished
  // section grade, and it would swing on every keystroke.
  const scored = props.criteria.filter((c) => scoreByCriterion.value.has(c.name))
  if (scored.length !== props.criteria.length) return null
  return rubricRollupPreview(props.criteria, props.scores, props.gradeMin, props.gradeMax)
})

const inputId = (name: string): string => `rubric-${props.sectionId}-${name}`
const noteId = (name: string): string => `rubric-note-${props.sectionId}-${name}`

/** Rebuild the whole array with this criterion replaced, preserving template order. */
function emitWith(name: string, patch: Partial<RubricScoreEntry>): void {
  const next = props.criteria
    .map((c) => {
      const existing = scoreByCriterion.value.get(c.name)
      const base: RubricScoreEntry = existing ?? { criterion: c.name, score: 0, note: null }
      return c.name === name ? { ...base, ...patch } : existing
    })
    .filter((entry): entry is RubricScoreEntry => entry !== undefined)
  emit('update', next)
}

function onScore(name: string, raw: string): void {
  const score = Number(raw)
  if (raw.trim() === '' || !Number.isFinite(score)) return
  emitWith(name, { score })
}
</script>

<template>
  <fieldset :data-test="`rubric-grid-${sectionId}`" class="space-y-2">
    <legend class="sr-only">{{ t('evaluations.rubricCriterion') }}</legend>

    <div
      v-for="c in criteria"
      :key="c.name"
      :data-test="`rubric-row-${sectionId}-${c.name}`"
      class="flex items-start gap-2"
    >
      <div class="min-w-0 flex-1">
        <label :for="inputId(c.name)" class="block text-xs font-medium">
          {{ c.name }}
          <span class="text-[var(--rt-fg-muted)]"> / {{ c.max_score }}</span>
        </label>
        <p v-if="c.description" class="text-[11px] text-[var(--rt-fg-muted)]">
          {{ c.description }}
        </p>
      </div>

      <input
        :id="inputId(c.name)"
        :data-test="`rubric-score-${sectionId}-${c.name}`"
        type="number"
        inputmode="decimal"
        min="0"
        :max="c.max_score"
        step="0.01"
        :disabled="disabled"
        :value="scoreByCriterion.get(c.name)?.score ?? ''"
        class="h-8 w-16 rounded-md border border-[var(--rt-border)] bg-[var(--rt-bg-elev)] px-2 font-mono text-sm"
        @input="onScore(c.name, ($event.target as HTMLInputElement).value)"
      />

      <label :for="noteId(c.name)" class="sr-only">
        {{ t('evaluations.rubricNote', { criterion: c.name }) }}
      </label>
      <input
        :id="noteId(c.name)"
        :data-test="`rubric-note-${sectionId}-${c.name}`"
        type="text"
        :disabled="disabled"
        :value="scoreByCriterion.get(c.name)?.note ?? ''"
        class="h-8 min-w-0 flex-1 rounded-md border border-[var(--rt-border)] bg-[var(--rt-bg-elev)] px-2 text-xs"
        @input="emitWith(c.name, { note: ($event.target as HTMLInputElement).value || null })"
      />
    </div>

    <p class="flex items-baseline gap-2 text-xs">
      <span class="text-[var(--rt-fg-muted)]">{{ t('evaluations.rubricRollup') }}</span>
      <output :data-test="`rubric-rollup-${sectionId}`" class="font-mono tabular-nums">
        {{ rollup === null ? '—' : rollup.toFixed(2) }}
      </output>
      <span :data-test="`rubric-rollup-note-${sectionId}`" class="text-[var(--rt-fg-muted)] italic">
        {{ t('evaluations.rubricProvisional') }}
      </span>
    </p>
  </fieldset>
</template>
