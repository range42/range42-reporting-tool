import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import EvaluationSummaryView from '@/views/reports/EvaluationSummaryView.vue'
import type { ReportSection } from '@/services/reports'
import type { EvaluationSummary } from '@/services/evaluations'

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

function summary(over: Partial<EvaluationSummary> = {}): EvaluationSummary {
  return {
    report_id: 'r1',
    overall_grade: '8.00',
    overall_feedback: 'Solid overall.',
    evaluated_at: '2026-09-01T00:00:00Z',
    section_grades: [
      {
        section_def_id: 'd1',
        name: 'Executive Summary',
        grade: '8.00',
        weight: '1.0',
        feedback: 'Good structure.',
      },
    ],
    ...over,
  }
}

function mountView(props: { sections: ReportSection[]; summary: EvaluationSummary | null }) {
  return mount(EvaluationSummaryView, { props, global: { plugins: [i18n] } })
}

describe('EvaluationSummaryView.vue', () => {
  it('renders the section content read-only, regardless of summary availability', () => {
    const wrapper = mountView({ sections: [section()], summary: null })
    expect(wrapper.text()).toContain('Situation stable.')
  })

  it('renders no input, textarea, or select at all', () => {
    const wrapper = mountView({ sections: [section()], summary: summary() })
    expect(wrapper.findAll('input')).toHaveLength(0)
    expect(wrapper.findAll('textarea')).toHaveLength(0)
    expect(wrapper.findAll('select')).toHaveLength(0)
  })

  it('shows no scores at all when summary is null — a quiet, non-error state', () => {
    const wrapper = mountView({ sections: [section()], summary: null })
    expect(wrapper.find('[data-test="evaluation-summary-overall"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="evaluation-summary-section-grade-d1"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="evaluation-summary-error"]').exists()).toBe(false)
  })

  it('shows the overall grade and feedback once a summary is available', () => {
    const wrapper = mountView({ sections: [section()], summary: summary() })
    const overall = wrapper.find('[data-test="evaluation-summary-overall"]')
    expect(overall.exists()).toBe(true)
    expect(overall.text()).toContain('8.00')
    expect(overall.text()).toContain('Solid overall.')
  })

  it('shows each section grade and feedback matched by section_def_id', () => {
    const wrapper = mountView({ sections: [section()], summary: summary() })
    expect(wrapper.find('[data-test="evaluation-summary-section-grade-d1"]').text()).toContain(
      '8.00',
    )
    expect(wrapper.find('[data-test="evaluation-summary-section-feedback-d1"]').text()).toContain(
      'Good structure.',
    )
  })

  it('leaves a section with no matching grade entry un-scored', () => {
    const other = section({ id: 's2', section_def_id: 'd2', name: 'Timeline' })
    const wrapper = mountView({ sections: [section(), other], summary: summary() })
    expect(wrapper.find('[data-test="evaluation-summary-section-grade-d2"]').exists()).toBe(false)
  })

  it('renders empty-section text for a null-content section', () => {
    const wrapper = mountView({ sections: [section({ content: null })], summary: null })
    expect(wrapper.text()).toContain(en.evaluations.emptySection)
  })

  it('renders choice_values as text chips, never as markup', () => {
    const wrapper = mountView({
      sections: [section({ content: null, choice_values: ['<b>x</b>', 'green'] })],
      summary: null,
    })
    expect(wrapper.html()).not.toContain('<b>x</b>')
    expect(wrapper.text()).toContain('<b>x</b>')
    expect(wrapper.text()).toContain('green')
  })

  it('sanitizes section HTML content before rendering it', () => {
    const wrapper = mountView({
      sections: [section({ content: '<script>alert(1)</script><p>ok</p>' })],
      summary: null,
    })
    expect(wrapper.html()).not.toContain('<script>')
    expect(wrapper.text()).toContain('ok')
  })
})
