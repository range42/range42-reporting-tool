import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import StalledEvaluations from '@/views/evaluations/StalledEvaluations.vue'
import * as evaluations from '@/services/evaluations'
import { ApiError } from '@/services/http'
import { useAuthStore } from '@/stores/auth'
import type { StalledReport } from '@/services/evaluations'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

const push = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { exerciseId: 'ex1' } }),
  useRouter: () => ({ push }),
  RouterLink: { template: '<a><slot /></a>' },
}))

const NOW = new Date('2026-10-13T12:00:00Z')

function row(over: Partial<StalledReport>): StalledReport {
  return {
    report_id: 'r1',
    report_name: 'Day 1 SITREP',
    team_id: 't1',
    team_name: 'Blue 1',
    under_evaluation_since: '2026-10-03T12:00:00Z',
    counted_evaluator_count: 2,
    completed_evaluator_count: 1,
    oldest_pending_activity_at: '2026-10-06T12:00:00Z',
    ...over,
  }
}

function mountView() {
  return mount(StalledEvaluations, { global: { plugins: [i18n] } })
}

describe('StalledEvaluations.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    push.mockClear()
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(NOW)
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'a', email: 'a', display_name: 'a', avatar_url: null, is_global_admin: true },
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('lists the reports in the order the server ranked them', async () => {
    // Arrange
    vi.spyOn(evaluations, 'listStalledReports').mockResolvedValue({
      finalize_policy: 'all_must_finalize',
      reports: [
        row({ report_id: 'r2', report_name: 'Orphaned' }),
        row({ report_id: 'r1', report_name: 'Day 1 SITREP' }),
      ],
    })

    // Act
    const w = mountView()
    await flushPromises()

    // Assert
    const names = w.findAll('[data-test="stalled-name"]').map((n) => n.text())
    expect(names).toEqual(['Orphaned', 'Day 1 SITREP'])
    expect(evaluations.listStalledReports).toHaveBeenCalledWith('tok', 'ex1')
  })

  it('shows how long each report has waited and who has finalized', async () => {
    vi.spyOn(evaluations, 'listStalledReports').mockResolvedValue({
      finalize_policy: 'all_must_finalize',
      reports: [row({})],
    })
    const w = mountView()
    await flushPromises()
    const text = w.find('[data-test="stalled-row"]').text()
    expect(text).toContain('Blue 1')
    expect(text).toContain('10 days')
    expect(text).toContain('1 of 2')
    expect(text).toContain('7 days ago')
  })

  it('flags a report with no pending evaluator', async () => {
    vi.spyOn(evaluations, 'listStalledReports').mockResolvedValue({
      finalize_policy: 'all_must_finalize',
      reports: [
        row({
          counted_evaluator_count: 0,
          completed_evaluator_count: 0,
          oldest_pending_activity_at: null,
        }),
      ],
    })
    const w = mountView()
    await flushPromises()
    expect(w.find('[data-test="stalled-row"]').text()).toContain(
      en.evaluations.stalled.noPendingEvaluator,
    )
  })

  it('opens the report evaluators screen for a row', async () => {
    vi.spyOn(evaluations, 'listStalledReports').mockResolvedValue({
      finalize_policy: 'all_must_finalize',
      reports: [row({ report_id: 'r9' })],
    })
    const w = mountView()
    await flushPromises()
    await w.get('[data-test="stalled-open"]').trigger('click')
    expect(push).toHaveBeenCalledWith({
      name: 'report-evaluators',
      params: { exerciseId: 'ex1', rid: 'r9' },
    })
  })

  it('says so when nothing is under evaluation', async () => {
    vi.spyOn(evaluations, 'listStalledReports').mockResolvedValue({
      finalize_policy: 'any_can_finalize',
      reports: [],
    })
    const w = mountView()
    await flushPromises()
    expect(w.find('[data-test="stalled-empty"]').exists()).toBe(true)
    expect(w.find('[data-test="stalled-policy"]').text()).toContain(
      en.evaluations.stalled.policy.any_can_finalize,
    )
  })

  it('shows the API error when loading fails', async () => {
    vi.spyOn(evaluations, 'listStalledReports').mockRejectedValue(
      new ApiError('HTTP_ERROR', 'not_global_admin'),
    )
    const w = mountView()
    await flushPromises()
    expect(w.find('[data-test="stalled-error"]').text()).toContain('not_global_admin')
  })
})
