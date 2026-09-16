import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import ReportEvaluators from '@/views/reports/ReportEvaluators.vue'
import { useAuthStore } from '@/stores/auth'
import * as svc from '@/services/evaluations'
import * as reports from '@/services/reports'
import type { EvaluationBreakdown, EvaluationBreakdownRow } from '@/services/evaluations'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { exerciseId: 'ex1', rid: 'r1' } }),
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { template: '<a><slot /></a>' },
}))

function row(over: Partial<EvaluationBreakdownRow> = {}): EvaluationBreakdownRow {
  return {
    id: 'ev1',
    evaluator_id: 'u1',
    evaluator_display_name: 'Eve',
    status: 'assigned',
    overall_grade: null,
    aggregated_weight: '1.00',
    completed_at: null,
    finalized_by: null,
    finalize_is_admin_override: false,
    unassigned_at: null,
    unassign_reason: null,
    reopen_count: 0,
    ...over,
  }
}

function breakdown(rows: EvaluationBreakdownRow[]): EvaluationBreakdown {
  return {
    report_id: 'r1',
    report_status: 'submitted',
    finalize_policy: 'all_must_finalize',
    finalize_gate_satisfied: false,
    aggregate: {
      overall_grade: null,
      grade_version: 1,
      counted_evaluator_count: rows.length,
      completed_evaluator_count: 0,
      aggregated_weight_total: '1.00',
    },
    evaluations: rows,
  }
}

const CANDIDATES = [
  { user_id: 'u1', display_name: 'Eve', email: 'eve@x' },
  { user_id: 'u2', display_name: 'Ivan', email: 'ivan@x' },
]

function arrange(rows: EvaluationBreakdownRow[], candidates = CANDIDATES) {
  vi.spyOn(reports, 'getReport').mockResolvedValue({ name: 'Day 1 report' } as never)
  vi.spyOn(svc, 'listEvaluatorCandidates').mockResolvedValue(candidates)
  vi.spyOn(svc, 'listEvaluationsForReport').mockResolvedValue(breakdown(rows))
}

async function mountPage() {
  const wrapper = mount(ReportEvaluators, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

describe('ReportEvaluators.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.restoreAllMocks()
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'ga', email: 'a', display_name: 'Ada', avatar_url: null, is_global_admin: true },
    })
  })

  it('lists who is assigned, with the report it belongs to', async () => {
    arrange([row()])
    const wrapper = await mountPage()
    expect(wrapper.find('[data-test="assign-report-name"]').text()).toBe('Day 1 report')
    expect(wrapper.find('[data-test="assign-row-ev1"]').text()).toContain('Eve')
  })

  it('says so when nobody is assigned yet', async () => {
    arrange([])
    const wrapper = await mountPage()
    expect(wrapper.find('[data-test="assign-none"]').exists()).toBe(true)
  })

  // An active seat is not offerable: assigning the same person twice is a 409 at the server.
  it('offers only evaluators who do not already hold an active seat', async () => {
    arrange([row()])
    const wrapper = await mountPage()
    const options = wrapper.findAll('[data-test="assign-pick"] option').map((o) => o.text())
    expect(options.some((o) => o.includes('Ivan'))).toBe(true)
    expect(options.some((o) => o.includes('Eve'))).toBe(false)
  })

  it('assigns the chosen evaluator and reloads the list', async () => {
    arrange([])
    const assign = vi.spyOn(svc, 'assignEvaluator').mockResolvedValue({} as never)
    const wrapper = await mountPage()
    await wrapper.find('[data-test="assign-pick"]').setValue('u2')
    await wrapper.find('[data-test="assign-submit"]').trigger('click')
    await flushPromises()
    expect(assign).toHaveBeenCalledWith('tok', 'ex1', 'r1', 'u2')
    expect(svc.listEvaluationsForReport).toHaveBeenCalledTimes(2)
  })

  it('surfaces a failed assignment instead of silently doing nothing', async () => {
    arrange([])
    vi.spyOn(svc, 'assignEvaluator').mockRejectedValue(new Error('nope'))
    const wrapper = await mountPage()
    await wrapper.find('[data-test="assign-pick"]').setValue('u2')
    await wrapper.find('[data-test="assign-submit"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="assign-error"]').exists()).toBe(true)
  })

  // The removal is soft: the row stays readable with its reason for the dispute trail, but it
  // cannot be removed twice.
  it('keeps a removed evaluator visible with their reason and no remove control', async () => {
    arrange([row({ unassigned_at: '2026-09-10T10:00:00Z', unassign_reason: 'on leave' })])
    const wrapper = await mountPage()
    expect(wrapper.find('[data-test="assign-removed-ev1"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('on leave')
    expect(wrapper.find('[data-test="unassign-open-ev1"]').exists()).toBe(false)
  })

  it('tells the admin when the exercise has no evaluators to offer', async () => {
    arrange([], [])
    const wrapper = await mountPage()
    expect(wrapper.find('[data-test="assign-no-candidates"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="assign-pick"]').exists()).toBe(false)
  })
})
