import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import EvaluatorBreakdown from '@/views/evaluations/EvaluatorBreakdown.vue'
import { useAuthStore } from '@/stores/auth'
import * as svc from '@/services/evaluations'
import type { EvaluationBreakdown, EvaluationBreakdownRow } from '@/services/evaluations'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

const ADMIN = {
  id: 'ga1',
  email: 'a',
  display_name: 'Ada',
  avatar_url: null,
  is_global_admin: true,
}
const MINE = {
  id: 'u1',
  email: 'm',
  display_name: 'Mine',
  avatar_url: null,
  is_global_admin: false,
}

function row(over: Partial<EvaluationBreakdownRow> = {}): EvaluationBreakdownRow {
  return {
    id: 'ev1',
    evaluator_id: 'u1',
    evaluator_display_name: 'Mine',
    status: 'completed',
    overall_grade: '8.00',
    aggregated_weight: '1.50',
    completed_at: '2026-09-08T10:00:00Z',
    finalized_by: 'u1',
    finalize_is_admin_override: false,
    unassigned_at: null,
    unassign_reason: null,
    reopen_count: 2,
    ...over,
  }
}

function breakdown(rows: EvaluationBreakdownRow[]): EvaluationBreakdown {
  return {
    report_id: 'r1',
    report_status: 'under_evaluation',
    finalize_policy: 'all_must_finalize',
    finalize_gate_satisfied: false,
    aggregate: {
      overall_grade: '7.50',
      grade_version: 3,
      counted_evaluator_count: 2,
      completed_evaluator_count: 1,
      aggregated_weight_total: '2.50',
    },
    evaluations: rows,
  }
}

async function setup(user: typeof ADMIN | typeof MINE, rows: EvaluationBreakdownRow[]) {
  useAuthStore().setSession({ access_token: 'tok', token_type: 'bearer', user })
  vi.spyOn(svc, 'listEvaluationsForReport').mockResolvedValue(breakdown(rows))
  const w = mount(EvaluatorBreakdown, {
    props: { exerciseId: 'ex1', rid: 'r1' },
    global: { plugins: [i18n] },
  })
  await flushPromises()
  return w
}

describe('EvaluatorBreakdown', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('renders the per-evaluator table including completed_at for a global admin', async () => {
    const w = await setup(ADMIN, [
      row(),
      row({
        id: 'ev2',
        evaluator_id: 'u2',
        evaluator_display_name: 'Other',
        overall_grade: '6.00',
      }),
    ])
    expect(w.findAll('[data-test^="breakdown-row-"]')).toHaveLength(2)
    expect(w.get('[data-test="breakdown-row-ev1"]').text()).toContain('Mine')
    expect(w.get('[data-test="breakdown-row-ev2"]').text()).toContain('Other')
    // completed_at is admin-visible (D4a).
    expect(w.get('[data-test="breakdown-completed-ev1"]').text()).not.toBe('')
  })

  it('shows reopen_count and aggregated_weight in the admin table', async () => {
    const w = await setup(ADMIN, [row()])
    expect(w.get('[data-test="breakdown-reopens-ev1"]').text()).toContain('2')
    expect(w.get('[data-test="breakdown-weight-ev1"]').text()).toContain('1.5')
  })

  it("renders only the caller's own row for a non-admin evaluator", async () => {
    // The server already scopes this to one row; the client filters as UI hygiene.
    const w = await setup(MINE, [
      row(),
      row({
        id: 'ev2',
        evaluator_id: 'u2',
        evaluator_display_name: 'Other',
        overall_grade: '6.00',
      }),
    ])
    expect(w.findAll('[data-test^="breakdown-row-"]')).toHaveLength(1)
    expect(w.get('[data-test="breakdown-row-ev1"]').text()).toContain('8.00')
    // The report-level aggregate IS shown to an evaluator.
    expect(w.get('[data-test="breakdown-aggregate"]').text()).toContain('7.50')
  })

  it("never renders another evaluator's grade or feedback text", async () => {
    const w = await setup(MINE, [
      row(),
      row({
        id: 'ev2',
        evaluator_id: 'u2',
        evaluator_display_name: 'Other',
        overall_grade: '6.00',
      }),
    ])
    const html = w.html()
    expect(html).not.toContain('Other')
    expect(html).not.toContain('6.00')
    expect(html).not.toContain('ev2')
  })
})
