import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import RubricGrid from '@/views/evaluations/RubricGrid.vue'
import type { RubricScoreEntry } from '@/services/evaluations'
import type { RubricCriterion } from '@/services/templates'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

const CRITERIA: RubricCriterion[] = [
  { name: 'clarity', description: 'Reads well', weight: 1, max_score: 5 },
  { name: 'evidence', weight: 3, max_score: 10 },
]

function mountGrid(scores: RubricScoreEntry[] | null = null) {
  return mount(RubricGrid, {
    props: { sectionId: 's1', criteria: CRITERIA, scores, gradeMin: 0, gradeMax: 10 },
    global: { plugins: [i18n] },
  })
}

describe('RubricGrid', () => {
  it('renders one row per rubric criterion with an accessible label', () => {
    const w = mountGrid()
    expect(w.findAll('[data-test^="rubric-row-s1-"]')).toHaveLength(2)

    const input = w.get('[data-test="rubric-score-s1-clarity"]')
    const label = w.get(`label[for="${input.attributes('id')}"]`)
    expect(label.text()).toContain('clarity')
    expect(input.attributes('max')).toBe('5')
    expect(input.attributes('inputmode')).toBe('decimal')
  })

  it('emits the complete rubric_scores array on a single criterion change', async () => {
    const w = mountGrid([{ criterion: 'clarity', score: 4, note: null }])

    await w.get('[data-test="rubric-score-s1-evidence"]').setValue('9')

    const emitted = w.emitted('update')!.at(-1)![0] as RubricScoreEntry[]
    // Both criteria travel together: the server replaces the whole array.
    expect(emitted).toEqual([
      { criterion: 'clarity', score: 4, note: null },
      { criterion: 'evidence', score: 9, note: null },
    ])
    expect(typeof emitted[1]!.score).toBe('number')
  })

  it('shows the provisional rollup and labels it as not final', async () => {
    // clarity 5/5 weight 1, evidence 5/10 weight 3 -> (1·1 + 0.5·3)/4 = 0.625 -> 6.25 on 0..10
    const w = mountGrid([
      { criterion: 'clarity', score: 5, note: null },
      { criterion: 'evidence', score: 5, note: null },
    ])
    const rollup = w.get('[data-test="rubric-rollup-s1"]')
    expect(rollup.text()).toContain('6.25')
    expect(w.get('[data-test="rubric-rollup-note-s1"]').text()).toBe(
      en.evaluations.rubricProvisional,
    )
  })

  it('leaves the rollup blank until every criterion is scored', () => {
    const w = mountGrid([{ criterion: 'clarity', score: 5, note: null }])
    expect(w.get('[data-test="rubric-rollup-s1"]').text()).toBe('—')
  })
})
