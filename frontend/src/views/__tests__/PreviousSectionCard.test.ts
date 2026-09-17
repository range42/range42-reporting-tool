import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import PreviousSectionCard from '@/views/evaluations/PreviousSectionCard.vue'
import type { ReportSection } from '@/services/reports'
import type { SectionGrade } from '@/services/evaluations'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

function section(over: Partial<ReportSection> = {}): ReportSection {
  return {
    id: 's1',
    report_id: 'r1',
    section_def_id: 'd1',
    position: 0,
    name: 'Executive Summary',
    description: null,
    field_type: 'rich_text',
    is_required: true,
    char_limit: null,
    choice_config: null,
    content: '<p>Situation stable.</p>',
    content_plain: 'Situation stable.',
    char_count: 17,
    choice_values: null,
    version: 1,
    last_edited_by: null,
    last_edited_at: null,
    created_at: '',
    updated_at: '',
    ...over,
  }
}

function grade(over: Partial<SectionGrade> = {}): SectionGrade {
  return {
    id: 'g1',
    evaluation_id: 'ev1',
    report_section_id: 's1',
    grade: '7.50',
    pass_fail_result: null,
    rubric_scores: null,
    feedback: 'Good clarity.',
    created_at: '',
    updated_at: '',
    ...over,
  }
}

function mountCard(props: {
  section: ReportSection
  hasOwnPreviousEvaluation: boolean
  grade: SectionGrade | null
}) {
  return mount(PreviousSectionCard, { props, global: { plugins: [i18n] } })
}

describe('PreviousSectionCard.vue', () => {
  it('renders the previous section content read-only', () => {
    const wrapper = mountCard({
      section: section(),
      hasOwnPreviousEvaluation: true,
      grade: grade(),
    })
    expect(wrapper.text()).toContain('Situation stable.')
  })

  it('renders no input, textarea, or select at all', () => {
    const wrapper = mountCard({
      section: section(),
      hasOwnPreviousEvaluation: true,
      grade: grade(),
    })
    expect(wrapper.findAll('input')).toHaveLength(0)
    expect(wrapper.findAll('textarea')).toHaveLength(0)
    expect(wrapper.findAll('select')).toHaveLength(0)
  })

  it("renders the caller's own previous grade and feedback when present", () => {
    const wrapper = mountCard({
      section: section(),
      hasOwnPreviousEvaluation: true,
      grade: grade(),
    })
    expect(wrapper.find('[data-test="prev-grade"]').text()).toContain('7.50')
    expect(wrapper.text()).toContain('Good clarity.')
  })

  it('shows the did-not-evaluate note and hides per-section grade when the caller has no own previous evaluation', () => {
    const wrapper = mountCard({ section: section(), hasOwnPreviousEvaluation: false, grade: null })
    expect(wrapper.find('[data-test="prev-not-evaluated"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="prev-grade"]').exists()).toBe(false)
  })

  it('never renders a grade sourced from another evaluator', () => {
    // hasOwnPreviousEvaluation=false but a grade prop is present anyway (simulated bug upstream) —
    // the component must still refuse to show it.
    const wrapper = mountCard({
      section: section(),
      hasOwnPreviousEvaluation: false,
      grade: grade({ grade: '9.99', feedback: 'foreign feedback' }),
    })
    expect(wrapper.text()).not.toContain('9.99')
    expect(wrapper.text()).not.toContain('foreign feedback')
  })

  it('renders an empty-content placeholder for a section the team left blank', () => {
    const wrapper = mountCard({
      section: section({ content: null, content_plain: null, char_count: 0 }),
      hasOwnPreviousEvaluation: true,
      grade: null,
    })
    expect(wrapper.find('[data-test="prev-empty"]').exists()).toBe(true)
  })
})
