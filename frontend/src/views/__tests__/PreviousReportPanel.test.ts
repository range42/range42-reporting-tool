import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import PreviousReportPanel from '@/views/reports/PreviousReportPanel.vue'
import type { PreviousReportStatus } from '@/composables/useWriterPreviousReport'
import type { ReportDetail } from '@/services/reports'
import type { EvaluationSummary } from '@/services/evaluations'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

function report(over: Partial<ReportDetail> = {}): ReportDetail {
  return {
    id: 'r0',
    exercise_id: 'ex1',
    team_id: 't1',
    template_id: 'tpl1',
    template_version_at_creation: 1,
    name: 'Day 1 SITREP',
    description: null,
    status: 'evaluated',
    approval_required: false,
    due_at: null,
    submitted_at: null,
    assigned_writer_id: null,
    writer_notes: null,
    metadata: null,
    sections: [
      {
        id: 's1',
        report_id: 'r0',
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
      },
    ],
    approval_chain: null,
    approval_cycle: 1,
    approval_records: [],
    can_approve: false,
    ...over,
  }
}

function summary(over: Partial<EvaluationSummary> = {}): EvaluationSummary {
  return {
    report_id: 'r0',
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

function mountPanel(props: {
  status: PreviousReportStatus
  previousReport: ReportDetail | null
  previousSummary: EvaluationSummary | null
}) {
  return mount(PreviousReportPanel, { props, global: { plugins: [i18n] } })
}

describe('PreviousReportPanel.vue', () => {
  it('renders nothing while idle, loading, no_campaign, no_previous, or error', () => {
    const statuses: PreviousReportStatus[] = [
      'idle',
      'loading',
      'no_campaign',
      'no_previous',
      'error',
    ]
    for (const status of statuses) {
      const wrapper = mountPanel({ status, previousReport: null, previousSummary: null })
      expect(wrapper.text().trim()).toBe('')
    }
  })

  it('shows the previous report content once ready, even with no summary yet', () => {
    const wrapper = mountPanel({
      status: 'ready',
      previousReport: report(),
      previousSummary: null,
    })
    expect(wrapper.text()).toContain('Day 1 SITREP')
    expect(wrapper.text()).toContain('Situation stable.')
    expect(wrapper.find('[data-test="evaluation-summary-overall"]').exists()).toBe(false)
  })

  it('shows the previous report scores once the summary is available', () => {
    const wrapper = mountPanel({
      status: 'ready',
      previousReport: report(),
      previousSummary: summary(),
    })
    const overall = wrapper.find('[data-test="evaluation-summary-overall"]')
    expect(overall.exists()).toBe(true)
    expect(overall.text()).toContain('8.00')
  })
})
