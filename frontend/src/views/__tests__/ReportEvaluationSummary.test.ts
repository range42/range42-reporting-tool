import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import ReportEvaluationSummary from '@/views/reports/ReportEvaluationSummary.vue'
import { useAuthStore } from '@/stores/auth'
import * as reports from '@/services/reports'
import * as evaluations from '@/services/evaluations'
import { ApiError } from '@/services/http'
import type { ReportDetail } from '@/services/reports'
import type { EvaluationSummary } from '@/services/evaluations'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { exerciseId: 'ex1', rid: 'r1' } }),
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { template: '<a><slot /></a>' },
}))

function reportDetail(over: Partial<ReportDetail> = {}): ReportDetail {
  return {
    id: 'r1',
    exercise_id: 'ex1',
    team_id: 't1',
    template_id: 'tpl1',
    template_version_at_creation: 1,
    name: 'Day 2 SITREP',
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

async function mountPage() {
  const wrapper = mount(ReportEvaluationSummary, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

describe('ReportEvaluationSummary.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.restoreAllMocks()
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'u1', email: 'a', display_name: 'Ada', avatar_url: null, is_global_admin: false },
    })
  })

  it('opens for an evaluated report and shows its content and scores', async () => {
    vi.spyOn(reports, 'getReport').mockResolvedValue(reportDetail())
    vi.spyOn(evaluations, 'getReportEvaluationSummary').mockResolvedValue(summary())
    const wrapper = await mountPage()
    expect(wrapper.text()).toContain('Situation stable.')
    expect(wrapper.find('[data-test="evaluation-summary-overall"]').text()).toContain('8.00')
  })

  it('opens for a NOT-yet-evaluated report unconditionally, showing content only', async () => {
    vi.spyOn(reports, 'getReport').mockResolvedValue(reportDetail({ status: 'submitted' }))
    vi.spyOn(evaluations, 'getReportEvaluationSummary').mockRejectedValue(
      new ApiError('HTTP_ERROR', 'not_yet_evaluated', [], undefined, 409),
    )
    const wrapper = await mountPage()
    expect(wrapper.text()).toContain('Situation stable.')
    expect(wrapper.find('[data-test="evaluation-summary-overall"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="evaluation-summary-load-error"]').exists()).toBe(false)
  })

  it('treats a 409 from teams_see_own_scores being off the same way — content only, no error', async () => {
    vi.spyOn(reports, 'getReport').mockResolvedValue(reportDetail())
    vi.spyOn(evaluations, 'getReportEvaluationSummary').mockRejectedValue(
      new ApiError('HTTP_ERROR', 'scores_not_visible', [], undefined, 409),
    )
    const wrapper = await mountPage()
    expect(wrapper.text()).toContain('Situation stable.')
    expect(wrapper.find('[data-test="evaluation-summary-load-error"]').exists()).toBe(false)
  })

  it('shows a real error when the report itself fails to load', async () => {
    vi.spyOn(reports, 'getReport').mockRejectedValue(
      new ApiError('HTTP_ERROR', 'boom', [], undefined, 500),
    )
    vi.spyOn(evaluations, 'getReportEvaluationSummary').mockResolvedValue(null as never)
    const wrapper = await mountPage()
    expect(wrapper.find('[data-test="evaluation-summary-load-error"]').exists()).toBe(true)
  })

  it('rethrows a non-409 error from the summary call instead of silently hiding scores', async () => {
    vi.spyOn(reports, 'getReport').mockResolvedValue(reportDetail())
    vi.spyOn(evaluations, 'getReportEvaluationSummary').mockRejectedValue(
      new ApiError('HTTP_ERROR', 'server exploded', [], undefined, 500),
    )
    const wrapper = await mountPage()
    expect(wrapper.find('[data-test="evaluation-summary-load-error"]').exists()).toBe(true)
  })
})
