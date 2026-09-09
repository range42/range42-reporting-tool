import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import FinalizeBar from '@/views/evaluations/FinalizeBar.vue'
import { useAuthStore } from '@/stores/auth'
import { useEvaluationStore } from '@/stores/evaluation'
import * as svc from '@/services/evaluations'
import type { EvaluationBreakdown, EvaluationDetail, GradableSection } from '@/services/evaluations'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const USER = { id: 'u1', email: 'm', display_name: 'M', avatar_url: null, is_global_admin: false }

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
    gradable_section_count: 2,
    created_at: '2026-09-09T00:00:00Z',
    updated_at: '2026-09-09T00:00:00Z',
    report_name: 'R',
    report_status: 'under_evaluation',
    grade_version: 1,
    sections: [section(), section({ report_section_id: 's2' })],
    ...over,
  }
}

function breakdown(over: Partial<EvaluationBreakdown> = {}): EvaluationBreakdown {
  return {
    report_id: 'r1',
    report_status: 'under_evaluation',
    finalize_policy: 'all_must_finalize',
    finalize_gate_satisfied: false,
    aggregate: {
      overall_grade: null,
      grade_version: 1,
      counted_evaluator_count: 3,
      completed_evaluator_count: 1,
      aggregated_weight_total: '3.00',
    },
    evaluations: [],
    ...over,
  }
}

async function setup(d: EvaluationDetail = detail()) {
  useAuthStore().setSession({ access_token: 'tok', token_type: 'bearer', user: USER })
  vi.spyOn(svc, 'getEvaluation').mockResolvedValue(d)
  const store = useEvaluationStore()
  await store.load('tok', 'ex1', 'r1', 'ev1')
  const w = mount(FinalizeBar, {
    props: { exerciseId: 'ex1', rid: 'r1', evid: 'ev1' },
    global: { plugins: [i18n] },
  })
  await flushPromises()
  return { store, w }
}

describe('FinalizeBar', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('shows the server overall grade when present and the provisional preview otherwise', async () => {
    const withServer = await setup(detail({ overall_grade: '8.25' }))
    expect(withServer.w.get('[data-test="finalize-grade"]').text()).toContain('8.25')
    expect(withServer.w.find('[data-test="finalize-provisional"]').exists()).toBe(false)

    setActivePinia(createPinia())
    vi.restoreAllMocks()
    const preview = await setup()
    preview.store.setGrade('s1', { grade: 6 })
    preview.store.setGrade('s2', { grade: 8 })
    await flushPromises()
    expect(preview.w.get('[data-test="finalize-grade"]').text()).toContain('7')
  })

  it('labels the preview value as provisional', async () => {
    const { store, w } = await setup()
    store.setGrade('s1', { grade: 6 })
    store.setGrade('s2', { grade: 8 })
    await flushPromises()
    expect(w.get('[data-test="finalize-provisional"]').text()).toBe(en.evaluations.provisional)
  })

  it('disables finalize until every gradable section is graded', async () => {
    const { store, w } = await setup()
    expect((w.get('[data-test="finalize-btn"]').element as HTMLButtonElement).disabled).toBe(true)

    store.setGrade('s1', { grade: 6 })
    await flushPromises()
    expect((w.get('[data-test="finalize-btn"]').element as HTMLButtonElement).disabled).toBe(true)

    store.setGrade('s2', { grade: 8 })
    await flushPromises()
    expect((w.get('[data-test="finalize-btn"]').element as HTMLButtonElement).disabled).toBe(false)
  })

  it('states how many gradable sections remain', async () => {
    const { store, w } = await setup()
    expect(w.get('[data-test="finalize-remaining"]').text()).toContain('2')

    store.setGrade('s1', { grade: 6 })
    await flushPromises()
    expect(w.get('[data-test="finalize-remaining"]').text()).toContain('1')
  })

  it('calls finalizeEvaluation once and disables the button while in flight', async () => {
    const { store, w } = await setup()
    store.setGrade('s1', { grade: 6 })
    store.setGrade('s2', { grade: 8 })
    await flushPromises()

    let release!: (b: EvaluationBreakdown) => void
    const pending = new Promise<EvaluationBreakdown>((r) => (release = r))
    const fin = vi.spyOn(svc, 'finalizeEvaluation').mockReturnValue(pending)

    const btn = w.get('[data-test="finalize-btn"]')
    await btn.trigger('click')
    await btn.trigger('click')

    expect(fin).toHaveBeenCalledTimes(1)
    expect((w.get('[data-test="finalize-btn"]').element as HTMLButtonElement).disabled).toBe(true)

    release(breakdown({ finalize_gate_satisfied: true }))
    await flushPromises()
  })

  it('shows a waiting-on-other-evaluators note after finalizing when all must finalize', async () => {
    const { store, w } = await setup()
    store.setGrade('s1', { grade: 6 })
    store.setGrade('s2', { grade: 8 })
    await flushPromises()
    vi.spyOn(svc, 'finalizeEvaluation').mockResolvedValue(
      breakdown({ finalize_policy: 'all_must_finalize', finalize_gate_satisfied: false }),
    )

    expect(w.find('[data-test="finalize-waiting"]').exists()).toBe(false)
    await w.get('[data-test="finalize-btn"]').trigger('click')
    await flushPromises()

    expect(w.get('[data-test="finalize-waiting"]').text()).toBe(en.evaluations.waitingOthers)
  })

  it("does not name or count another evaluator's progress in the waiting note", async () => {
    const { store, w } = await setup()
    store.setGrade('s1', { grade: 6 })
    store.setGrade('s2', { grade: 8 })
    await flushPromises()
    vi.spyOn(svc, 'finalizeEvaluation').mockResolvedValue(
      breakdown({
        finalize_gate_satisfied: false,
        evaluations: [],
        aggregate: {
          overall_grade: null,
          grade_version: 1,
          counted_evaluator_count: 3,
          completed_evaluator_count: 1,
          aggregated_weight_total: '3.00',
        },
      }),
    )
    await w.get('[data-test="finalize-btn"]').trigger('click')
    await flushPromises()

    const note = w.get('[data-test="finalize-waiting"]').text()
    // No headcounts, no ratios, no peer identities (D1/E1).
    expect(note).not.toMatch(/\d/)
  })

  it('persists overall feedback through PATCH /evaluations/{id}', async () => {
    const { w } = await setup()
    const patch = vi.spyOn(svc, 'updateEvaluation').mockResolvedValue({
      ...detail(),
      overall_feedback: 'Solid work overall.',
    })

    const box = w.get('[data-test="finalize-feedback"]')
    await box.setValue('Solid work overall.')
    await box.trigger('blur')
    await flushPromises()

    expect(patch).toHaveBeenCalledWith('tok', 'ex1', 'r1', 'ev1', {
      overall_feedback: 'Solid work overall.',
    })
  })
})
