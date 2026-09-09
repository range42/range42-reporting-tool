import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import GradeControl from '@/views/evaluations/GradeControl.vue'
import type { GradableSection, GradeUpsertInput } from '@/services/evaluations'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

function section(over: Partial<GradableSection> = {}): GradableSection {
  return {
    report_section_id: 's1',
    section_def_id: 'd1',
    name: 'Findings',
    description: null,
    position: 0,
    field_type: 'rich_text',
    content: '<p>x</p>',
    content_plain: 'x',
    choice_values: null,
    grade_mode: 'numeric',
    grade_min: '0.00',
    grade_max: '10.00',
    grade_weight: '1.00',
    rubric_criteria: null,
    evaluation_criteria: null,
    grade: null,
    ...over,
  }
}

function mountControl(over: Partial<GradableSection> = {}, props: Record<string, unknown> = {}) {
  return mount(GradeControl, {
    props: {
      section: section(over),
      grade: null,
      passFailResult: null,
      rubricScores: null,
      ...props,
    },
    global: { plugins: [i18n] },
  })
}

describe('GradeControl', () => {
  it('renders a number input bounded by grade_min and grade_max for numeric mode', () => {
    const w = mountControl()
    const input = w.get('[data-test="grade-numeric-s1"]')
    expect(input.attributes('type')).toBe('number')
    expect(input.attributes('min')).toBe('0')
    expect(input.attributes('max')).toBe('10')
    expect(input.attributes('inputmode')).toBe('decimal')
    expect(input.attributes('step')).toBeDefined()
    // A real label and a range hint wired through aria-describedby.
    expect(w.get(`label[for="${input.attributes('id')}"]`).text()).toContain('Grade')
    const hintId = input.attributes('aria-describedby')!
    expect(w.get(`#${hintId}`).text()).toContain('10')
  })

  it('renders a pass/fail segmented control for pass_fail mode', () => {
    const w = mountControl({ grade_mode: 'pass_fail' })
    expect(w.get('[data-test="grade-pass-s1"]').text()).toBe(en.evaluations.pass)
    expect(w.get('[data-test="grade-fail-s1"]').text()).toBe(en.evaluations.fail)
    expect(w.find('[data-test="grade-numeric-s1"]').exists()).toBe(false)
  })

  it('renders the rubric grid for rubric mode', () => {
    const w = mountControl({
      grade_mode: 'rubric',
      rubric_criteria: [{ name: 'clarity', weight: 1, max_score: 5 }],
    })
    expect(w.findAll('[data-test^="rubric-row-s1-"]')).toHaveLength(1)
    expect(w.find('[data-test="grade-numeric-s1"]').exists()).toBe(false)
  })

  it('renders no grade control at all for not_graded mode', () => {
    const w = mountControl({ grade_mode: 'not_graded' })
    expect(w.find('[data-test="grade-numeric-s1"]').exists()).toBe(false)
    expect(w.find('[data-test="grade-pass-s1"]').exists()).toBe(false)
    expect(w.find('[data-test="rubric-grid-s1"]').exists()).toBe(false)
    expect(w.get('[data-test="grade-not-graded-s1"]').text()).toBe(en.evaluations.notGraded)
  })

  it('emits update with a parsed number, not a string, on input', async () => {
    const w = mountControl()
    await w.get('[data-test="grade-numeric-s1"]').setValue('7.5')

    const payload = w.emitted('update')!.at(-1)![0] as GradeUpsertInput
    expect(payload).toEqual({ grade: 7.5 })
    expect(typeof payload.grade).toBe('number')
  })

  it('emits pass_fail_result as a boolean', async () => {
    const w = mountControl({ grade_mode: 'pass_fail' })

    await w.get('[data-test="grade-pass-s1"]').trigger('click')
    expect(w.emitted('update')!.at(-1)![0]).toEqual({ pass_fail_result: true })

    await w.get('[data-test="grade-fail-s1"]').trigger('click')
    const payload = w.emitted('update')!.at(-1)![0] as GradeUpsertInput
    expect(payload).toEqual({ pass_fail_result: false })
    expect(typeof payload.pass_fail_result).toBe('boolean')
  })

  it('sets aria-invalid and shows a message when the value is out of range', async () => {
    const w = mountControl()
    const input = w.get('[data-test="grade-numeric-s1"]')
    expect(input.attributes('aria-invalid')).toBe('false')

    await input.setValue('11')

    expect(w.get('[data-test="grade-numeric-s1"]').attributes('aria-invalid')).toBe('true')
    expect(w.get('[data-test="grade-error-s1"]').text()).toBe(en.evaluations.outOfRange)
  })
})
