import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import SectionGradeCard from '@/views/evaluations/SectionGradeCard.vue'
import { useEvaluationStore } from '@/stores/evaluation'
import type { EvaluationDetail, GradableSection } from '@/services/evaluations'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

function section(over: Partial<GradableSection> = {}): GradableSection {
  return {
    report_section_id: 's1',
    section_def_id: 'd1',
    name: 'Findings',
    description: null,
    position: 0,
    field_type: 'rich_text',
    content: '<p>body text</p>',
    content_plain: 'body text',
    choice_values: null,
    grade_mode: 'numeric',
    grade_min: '0.00',
    grade_max: '10.00',
    grade_weight: '1.50',
    rubric_criteria: null,
    evaluation_criteria: null,
    grade: null,
    ...over,
  }
}

function detail(over: Partial<EvaluationDetail> = {}): EvaluationDetail {
  return {
    id: 'ev1',
    report_id: 'r1',
    evaluator_id: 'u1',
    status: 'in_progress',
    overall_feedback: null,
    overall_grade: null,
    completed_at: null,
    reopen_count: 0,
    graded_section_count: 0,
    gradable_section_count: 1,
    created_at: '2026-09-09T00:00:00Z',
    updated_at: '2026-09-09T00:00:00Z',
    report_name: 'R',
    report_status: 'submitted',
    team_name: 'Team Alpha',
    submitted_at: '2026-09-09T09:00:00Z',
    grade_version: 1,
    sections: [section()],
    ...over,
  }
}

function env(status: number, data: unknown): Response {
  return new Response(JSON.stringify({ data }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** Load the store from a stubbed detail, then mount the card against it. */
async function setup(d: EvaluationDetail = detail()) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(env(200, d)))
  const store = useEvaluationStore()
  await store.load('tok', 'ex1', 'r1', 'ev1')
  const w = mount(SectionGradeCard, {
    props: { sectionId: d.sections[0]!.report_section_id },
    global: { plugins: [i18n] },
  })
  return { store, w }
}

describe('SectionGradeCard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('renders the evaluator-only evaluation_criteria text', async () => {
    const { w } = await setup(
      detail({ sections: [section({ evaluation_criteria: 'Cite the CTI indicator IDs.' })] }),
    )
    expect(w.get('[data-test="criteria-s1"]').text()).toContain('Cite the CTI indicator IDs.')
  })

  it('omits the criteria block when the section has no criteria', async () => {
    const { w } = await setup()
    expect(w.find('[data-test="criteria-s1"]').exists()).toBe(false)
  })

  it('shows grade mode, range, and weight in the section header', async () => {
    const { w } = await setup()
    const header = w.get('[data-test="section-meta-s1"]').text()
    expect(header).toContain('0–10')
    expect(header).toContain('1.5')
  })

  it('renders the content pane and the grade control in one card', async () => {
    const { w } = await setup()
    const card = w.get('[data-test="section-card-s1"]')
    expect(card.find('[data-test="content-body-s1"]').exists()).toBe(true)
    expect(card.find('[data-test="grade-s1"]').exists()).toBe(true)
    expect(card.find('[data-test="feedback-s1"]').exists()).toBe(true)
  })

  it('saves the section grade through the store on blur', async () => {
    const { store, w } = await setup()
    const setGrade = vi.spyOn(store, 'setGrade')
    const flush = vi.spyOn(store, 'flush').mockResolvedValue()

    await w.get('[data-test="grade-numeric-s1"]').setValue('8')
    expect(setGrade).toHaveBeenCalledWith('s1', { grade: 8 })
    expect(flush).not.toHaveBeenCalled()

    await w.get('[data-test="grade-numeric-s1"]').trigger('blur')
    expect(flush).toHaveBeenCalledOnce()
  })

  it('saves section feedback through the store on blur', async () => {
    const { store, w } = await setup()
    const setGrade = vi.spyOn(store, 'setGrade')
    const flush = vi.spyOn(store, 'flush').mockResolvedValue()

    const box = w.get('[data-test="feedback-s1"]')
    await box.setValue('Tie findings back to the indicators.')
    expect(setGrade).toHaveBeenCalledWith('s1', {
      feedback: 'Tie findings back to the indicators.',
    })

    await box.trigger('blur')
    expect(flush).toHaveBeenCalledOnce()
  })

  it('shows a per-section error when the save fails and keeps the entered value', async () => {
    const { store, w } = await setup()
    // A rejected save records the code against the section and keeps the draft.
    vi.spyOn(store, 'errorFor').mockReturnValue('evaluation_finalized')
    await w.get('[data-test="grade-numeric-s1"]').setValue('8')

    // Task 11 added evaluations.saveErrors.*, so the code is now translated for the user;
    // the raw code only shows for a code with no message yet.
    expect(w.get('[data-test="grade-error-s1"]').text()).toBe(
      en.evaluations.saveErrors.evaluation_finalized,
    )
    expect((w.get('[data-test="grade-numeric-s1"]').element as HTMLInputElement).value).toBe('8')
  })

  it('renders read-only content with no controls for a not_graded section', async () => {
    const { w } = await setup(detail({ sections: [section({ grade_mode: 'not_graded' })] }))
    expect(w.get('[data-test="content-body-s1"]').text()).toContain('body text')
    expect(w.find('[data-test="grade-numeric-s1"]').exists()).toBe(false)
    expect(w.find('[data-test="feedback-s1"]').exists()).toBe(false)
    expect(w.get('[data-test="grade-not-graded-s1"]').text()).toBe(en.evaluations.notGraded)
  })

  it('disables every control once the evaluation status is completed', async () => {
    const { w } = await setup(detail({ status: 'completed' }))
    expect((w.get('[data-test="grade-numeric-s1"]').element as HTMLInputElement).disabled).toBe(
      true,
    )
    expect((w.get('[data-test="feedback-s1"]').element as HTMLTextAreaElement).disabled).toBe(true)
  })
})
