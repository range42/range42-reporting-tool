import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import SingleEvaluation from '@/views/evaluations/SingleEvaluation.vue'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/services/http'
import * as svc from '@/services/evaluations'
import { useGradeDraftCache } from '@/composables/useGradeDraftCache'
import { useEvaluationStore } from '@/stores/evaluation'
import type { EvaluationDetail, GradableSection, SectionGrade } from '@/services/evaluations'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const push = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { exerciseId: 'ex1', rid: 'r1', evid: 'ev1' } }),
  useRouter: () => ({ push, hasRoute: () => true }),
  RouterLink: {
    props: ['to'],
    template: '<a :data-to="JSON.stringify(to)"><slot /></a>',
  },
}))

const EVALUATOR = {
  id: 'u1',
  email: 'e',
  display_name: 'Eve',
  avatar_url: null,
  is_global_admin: false,
}
const ADMIN = { id: 'ga', email: 'a', display_name: 'Ada', avatar_url: null, is_global_admin: true }

function grade(over: Partial<SectionGrade> = {}): SectionGrade {
  return {
    id: 'g1',
    evaluation_id: 'ev1',
    report_section_id: 's1',
    grade: '5.00',
    pass_fail_result: null,
    rubric_scores: null,
    feedback: null,
    created_at: '2026-09-08T10:00:00Z',
    updated_at: '2026-09-08T10:00:00Z',
    ...over,
  }
}

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
    report_name: 'SITREP #6',
    report_status: 'under_evaluation',
    team_name: 'Team Alpha',
    submitted_at: '2026-09-09T09:00:00Z',
    grade_version: 1,
    sections: [
      section({ report_section_id: 's2', name: 'Actions', position: 1 }),
      section({ report_section_id: 's1', name: 'Findings', position: 0 }),
    ],
    ...over,
  }
}

async function setup(user = EVALUATOR, d: EvaluationDetail = detail()) {
  useAuthStore().setSession({ access_token: 'tok', token_type: 'bearer', user })
  vi.spyOn(svc, 'getEvaluation').mockResolvedValue(d)
  vi.spyOn(svc, 'listEvaluationsForReport').mockResolvedValue({
    report_id: 'r1',
    report_status: 'under_evaluation',
    finalize_policy: 'all_must_finalize',
    finalize_gate_satisfied: false,
    aggregate: {
      overall_grade: '7.50',
      grade_version: 3,
      counted_evaluator_count: 1,
      completed_evaluator_count: 0,
      aggregated_weight_total: '1.00',
    },
    evaluations: [],
  })
  const w = mount(SingleEvaluation, { global: { plugins: [i18n] } })
  await flushPromises()
  return w
}

describe('SingleEvaluation', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    push.mockClear()
    vi.restoreAllMocks()
  })

  it('loads the evaluation and renders one section card per section in position order', async () => {
    const w = await setup()
    const cards = w.findAll('[data-test^="section-card-"]')
    expect(cards).toHaveLength(2)
    expect(cards[0]!.attributes('data-test')).toBe('section-card-s1')
    expect(cards[1]!.attributes('data-test')).toBe('section-card-s2')
  })

  it('renders the report name, team, and submitted time in the header', async () => {
    const w = await setup()
    const header = w.get('[data-test="evaluation-header"]').text()
    expect(header).toContain('SITREP #6')
    expect(header).toContain('Team Alpha')
    expect(w.get('[data-test="evaluation-submitted"]').text()).not.toBe('')
  })

  it('renders the view-mode switch with Single active', async () => {
    const w = await setup()
    expect(w.get('[data-test="mode-single"]').attributes('aria-current')).toBe('page')
  })

  it('links campaign mode to the campaign route for this evaluation', async () => {
    const w = await setup()
    const to = w.get('[data-test="mode-campaign"]').attributes('data-to')!
    expect(JSON.parse(to)).toMatchObject({
      params: { exerciseId: 'ex1', rid: 'r1', evid: 'ev1' },
    })
  })

  it('shows a scope message instead of the grid when the API returns 403', async () => {
    useAuthStore().setSession({ access_token: 'tok', token_type: 'bearer', user: EVALUATOR })
    vi.spyOn(svc, 'getEvaluation').mockRejectedValue(
      new ApiError('forbidden', 'nope', [], undefined, 403),
    )
    const w = mount(SingleEvaluation, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(w.get('[data-test="evaluation-scope"]').text()).toBe(en.evaluations.scopeDenied)
    expect(w.findAll('[data-test^="section-card-"]')).toHaveLength(0)
  })

  it('offers a restore prompt when a cached grade draft is newer than the server value', async () => {
    // Seed a draft that postdates the stored grade's updated_at.
    useGradeDraftCache('ev1').save('s1', { grade: 9 }, '2026-09-08T12:00:00Z')
    const w = await setup(EVALUATOR, detail({ sections: [section({ grade: grade() })] }))
    expect(w.get('[data-test="draft-restore"]').text()).toContain(en.evaluations.draftRestore)
    expect(w.find('[data-test="draft-restore-apply"]').exists()).toBe(true)
  })

  it('renders the finalize bar with the report aggregate grade', async () => {
    const w = await setup()
    expect(w.find('[data-test="finalize-btn"]').exists()).toBe(true)
    expect(w.get('[data-test="breakdown-aggregate"]').text()).toContain('7.50')
  })

  it('offers the reopen control to the evaluator who owns a completed evaluation', async () => {
    // Arrange / Act
    const w = await setup(EVALUATOR, detail({ status: 'completed', evaluator_id: EVALUATOR.id }))

    // Assert — reopening is the only route back to an editable, finalizable evaluation.
    expect(w.find('[data-test="reopen-open"]').exists()).toBe(true)
  })

  it('offers the reopen control to a global admin on a completed evaluation', async () => {
    // Arrange / Act
    const w = await setup(ADMIN, detail({ status: 'completed' }))

    // Assert
    expect(w.find('[data-test="reopen-open"]').exists()).toBe(true)
  })

  it('offers no reopen control while the evaluation is still in progress', async () => {
    // Arrange / Act
    const w = await setup(ADMIN, detail({ status: 'in_progress' }))

    // Assert
    expect(w.find('[data-test="reopen-open"]').exists()).toBe(false)
  })

  it('requires a reason before submitting a reopen', async () => {
    const w = await setup(ADMIN, detail({ status: 'completed' }))
    const reopen = vi.spyOn(svc, 'reopenEvaluation')

    await w.get('[data-test="reopen-open"]').trigger('click')
    const submit = w.get('[data-test="reopen-submit"]')
    expect((submit.element as HTMLButtonElement).disabled).toBe(true)
    await submit.trigger('click')
    expect(reopen).not.toHaveBeenCalled()

    await w.get('[data-test="reopen-reason"]').setValue('grade was wrong')
    expect((w.get('[data-test="reopen-submit"]').element as HTMLButtonElement).disabled).toBe(false)
  })

  it('mounts no AI pre-check slot when AI is disabled', async () => {
    const w = await setup()
    expect(w.findAll('[data-test-kind="ai-precheck"]')).toHaveLength(0)
  })

  it('mounts one AI pre-check slot per section once AI is available', async () => {
    // Proves the absence above is the flag doing its job, not a selector that never matches.
    const w = await setup()
    await w.setProps({ aiAvailable: true })
    expect(w.findAll('[data-test-kind="ai-precheck"]')).toHaveLength(2)
  })

  it('restores cached drafts into the store when the prompt is accepted', async () => {
    useGradeDraftCache('ev1').save('s1', { grade: 9 }, '2026-09-08T12:00:00Z')
    const w = await setup(EVALUATOR, detail({ sections: [section({ grade: grade() })] }))
    const store = useEvaluationStore()

    await w.get('[data-test="draft-restore-apply"]').trigger('click')

    // Replayed through setGrade, so the restored value passed the same range validation.
    expect(store.effectiveGrade('s1')).toBe(9)
    expect(w.find('[data-test="draft-restore"]').exists()).toBe(false)
  })

  it('clears the cache when the restore prompt is discarded', async () => {
    const cache = useGradeDraftCache('ev1')
    cache.save('s1', { grade: 9 }, '2026-09-08T12:00:00Z')
    const w = await setup(EVALUATOR, detail({ sections: [section({ grade: grade() })] }))

    await w.get('[data-test="draft-restore-discard"]').trigger('click')

    expect(cache.read('s1')).toBeNull()
    expect(w.find('[data-test="draft-restore"]').exists()).toBe(false)
    expect(useEvaluationStore().effectiveGrade('s1')).toBe(5)
  })

  it('submits a reopen with its reason and re-reads the evaluation afterwards', async () => {
    const w = await setup(ADMIN, detail({ status: 'completed' }))
    const reopen = vi.spyOn(svc, 'reopenEvaluation').mockResolvedValue({
      report_id: 'r1',
      report_status: 'under_evaluation',
      finalize_policy: 'all_must_finalize',
      finalize_gate_satisfied: false,
      aggregate: {
        overall_grade: null,
        grade_version: 4,
        counted_evaluator_count: 1,
        completed_evaluator_count: 0,
        aggregated_weight_total: '1.00',
      },
      evaluations: [],
    })
    const reread = vi.spyOn(svc, 'getEvaluation')

    await w.get('[data-test="reopen-open"]').trigger('click')
    await w.get('[data-test="reopen-reason"]').setValue('grade was wrong')
    await w.get('[data-test="reopen-submit"]').trigger('click')
    await flushPromises()

    expect(reopen).toHaveBeenCalledWith('tok', 'ex1', 'r1', 'ev1', 'grade was wrong')
    // A reopen publishes a new grade version, so the view re-reads rather than guessing.
    expect(reread).toHaveBeenCalled()
    expect(w.find('[data-test="reopen-reason"]').exists()).toBe(false)
  })

  it('keeps the reopen form open and reports the failure when the reopen rejects', async () => {
    const w = await setup(ADMIN, detail({ status: 'completed' }))
    vi.spyOn(svc, 'reopenEvaluation').mockRejectedValue(
      new ApiError('reason_required', 'no', [], undefined, 422),
    )

    await w.get('[data-test="reopen-open"]').trigger('click')
    await w.get('[data-test="reopen-reason"]').setValue('typo')
    await w.get('[data-test="reopen-submit"]').trigger('click')
    await flushPromises()

    expect(w.get('[data-test="reopen-error"]').text()).toBe(en.evaluations.reopenFailed)
    expect(w.find('[data-test="reopen-reason"]').exists()).toBe(true)
  })

  it('takes the header team and submitted time from the evaluation payload alone', async () => {
    // No report fetch: GET /reports/{rid} is refused to an evaluator outside the team, so the
    // fields ride on the evaluation itself.
    const w = await setup()
    expect(w.get('[data-test="evaluation-team"]').text()).toBe('Team Alpha')
    expect(w.get('[data-test="evaluation-submitted"]').text()).toContain('2026')
  })
})
