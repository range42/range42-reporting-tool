import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useEvaluationStore } from '@/stores/evaluation'
import type { EvaluationDetail, GradableSection } from '@/services/evaluations'

const CTX = { token: 'tok', exerciseId: 'ex1', rid: 'r1', evid: 'ev1' } as const

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
    gradable_section_count: 1,
    created_at: '2026-09-09T00:00:00Z',
    updated_at: '2026-09-09T00:00:00Z',
    report_name: 'R',
    report_status: 'submitted',
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

function errEnv(status: number, code: string): Response {
  return new Response(JSON.stringify({ error: { code, message: 'no', details: [] } }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** GET the detail, then answer every later call with `rest` in order. */
function stubFetch(first: Response, ...rest: Response[]): ReturnType<typeof vi.fn> {
  const mock = vi.fn()
  mock.mockResolvedValueOnce(first)
  for (const r of rest) mock.mockResolvedValueOnce(r)
  vi.stubGlobal('fetch', mock)
  return mock
}

describe('evaluation store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('load() normalizes sections and grades into a section-keyed map', async () => {
    const graded = section({
      report_section_id: 's2',
      grade: {
        id: 'g1',
        evaluation_id: 'ev1',
        report_section_id: 's2',
        grade: '7.50',
        pass_fail_result: null,
        rubric_scores: null,
        feedback: 'ok',
        created_at: '2026-09-09T00:00:00Z',
        updated_at: '2026-09-09T00:00:00Z',
      },
    })
    stubFetch(env(200, detail({ sections: [section(), graded] })))
    const s = useEvaluationStore()
    await s.load(CTX.token, CTX.exerciseId, CTX.rid, CTX.evid)

    expect(Object.keys(s.sectionsById)).toEqual(['s1', 's2'])
    expect(s.sectionsById.s2!.name).toBe('Findings')
    expect(s.effectiveGrade('s2')).toBe(7.5)
    expect(s.effectiveGrade('s1')).toBeNull()
    expect(s.gradeVersion).toBe(1)
  })

  it('setGrade marks the section dirty without mutating the previous grade object', async () => {
    const stored = {
      id: 'g1',
      evaluation_id: 'ev1',
      report_section_id: 's1',
      grade: '7.50',
      pass_fail_result: null,
      rubric_scores: null,
      feedback: null,
      created_at: '2026-09-09T00:00:00Z',
      updated_at: '2026-09-09T00:00:00Z',
    }
    stubFetch(env(200, detail({ sections: [section({ grade: stored })] })))
    const s = useEvaluationStore()
    await s.load(CTX.token, CTX.exerciseId, CTX.rid, CTX.evid)

    s.setGrade('s1', { grade: 9 })

    expect(s.isDirty('s1')).toBe(true)
    expect(s.effectiveGrade('s1')).toBe(9)
    // The server's grade row is untouched — the edit lives in a separate draft.
    expect(s.sectionsById.s1!.grade!.grade).toBe('7.50')
    expect(stored.grade).toBe('7.50')
  })

  it('gradableCount excludes not_graded sections', async () => {
    stubFetch(
      env(
        200,
        detail({
          sections: [
            section({ report_section_id: 's1' }),
            section({ report_section_id: 's2', grade_mode: 'not_graded' }),
            section({ report_section_id: 's3', grade_mode: 'pass_fail' }),
          ],
        }),
      ),
    )
    const s = useEvaluationStore()
    await s.load(CTX.token, CTX.exerciseId, CTX.rid, CTX.evid)
    expect(s.gradableCount).toBe(2)
  })

  it('canFinalize is false while any gradable section has a null grade', async () => {
    stubFetch(
      env(
        200,
        detail({
          sections: [section({ report_section_id: 's1' }), section({ report_section_id: 's2' })],
        }),
      ),
    )
    const s = useEvaluationStore()
    await s.load(CTX.token, CTX.exerciseId, CTX.rid, CTX.evid)
    s.setGrade('s1', { grade: 8 })
    expect(s.canFinalize).toBe(false)
  })

  it('canFinalize is true once every gradable section is graded', async () => {
    stubFetch(
      env(
        200,
        detail({
          sections: [
            section({ report_section_id: 's1' }),
            section({ report_section_id: 's2', grade_mode: 'not_graded' }),
          ],
        }),
      ),
    )
    const s = useEvaluationStore()
    await s.load(CTX.token, CTX.exerciseId, CTX.rid, CTX.evid)
    s.setGrade('s1', { grade: 8 })
    expect(s.canFinalize).toBe(true)
  })

  it('rejects a numeric grade outside grade_min..grade_max and records a field error', async () => {
    stubFetch(env(200, detail()))
    const s = useEvaluationStore()
    await s.load(CTX.token, CTX.exerciseId, CTX.rid, CTX.evid)

    s.setGrade('s1', { grade: 11 })

    expect(s.errorFor('s1')).toBe('out_of_range')
    expect(s.isDirty('s1')).toBe(false)
    expect(s.effectiveGrade('s1')).toBeNull()

    s.setGrade('s1', { grade: 9 })
    expect(s.errorFor('s1')).toBeNull()
    expect(s.isDirty('s1')).toBe(true)
  })

  it('flush() saves only dirty sections and clears dirty on success', async () => {
    const mock = stubFetch(
      env(
        200,
        detail({
          sections: [section({ report_section_id: 's1' }), section({ report_section_id: 's2' })],
        }),
      ),
      env(200, { id: 'g1', report_section_id: 's1', grade: '8.00' }),
      env(200, detail({ graded_section_count: 1 })),
    )
    const s = useEvaluationStore()
    await s.load(CTX.token, CTX.exerciseId, CTX.rid, CTX.evid)
    s.setGrade('s1', { grade: 8 })

    await s.flush()

    const puts = mock.mock.calls.filter((c) => c[1]?.method === 'PUT')
    expect(puts).toHaveLength(1)
    expect(puts[0]![0]).toContain('/evaluations/ev1/grades/s1')
    expect(s.isDirty('s1')).toBe(false)
  })

  it('keeps the section dirty and records an error when the save rejects', async () => {
    stubFetch(env(200, detail()), errEnv(409, 'evaluation_finalized'))
    const s = useEvaluationStore()
    await s.load(CTX.token, CTX.exerciseId, CTX.rid, CTX.evid)
    s.setGrade('s1', { grade: 8 })

    await s.flush()

    expect(s.isDirty('s1')).toBe(true)
    expect(s.errorFor('s1')).toBe('evaluation_finalized')
  })

  it('adopts the server overall_grade from a save response, discarding the provisional value', async () => {
    stubFetch(
      env(200, detail()),
      env(200, { id: 'g1', report_section_id: 's1', grade: '8.00' }),
      env(200, detail({ overall_grade: '8.25', graded_section_count: 1 })),
    )
    const s = useEvaluationStore()
    await s.load(CTX.token, CTX.exerciseId, CTX.rid, CTX.evid)
    s.setGrade('s1', { grade: 8 })
    expect(s.previewGrade).toBe(8)

    await s.flush()

    // The server's number wins over the local preview once it arrives.
    expect(s.overallGrade).toBe(8.25)
  })

  it('sends grades as two-decimal strings', async () => {
    const mock = stubFetch(
      env(200, detail()),
      env(200, { id: 'g1', report_section_id: 's1', grade: '7.05' }),
      env(200, detail()),
    )
    const s = useEvaluationStore()
    await s.load(CTX.token, CTX.exerciseId, CTX.rid, CTX.evid)
    s.setGrade('s1', { grade: 7.05 })

    await s.flush()

    const put = mock.mock.calls.find((c) => c[1]?.method === 'PUT')!
    expect(JSON.parse(put[1].body)).toEqual({ grade: '7.05' })
  })

  it('prefers the server graded_section_count over the local count once a response arrives', async () => {
    stubFetch(
      env(
        200,
        detail({
          graded_section_count: 0,
          sections: [section({ report_section_id: 's1' }), section({ report_section_id: 's2' })],
        }),
      ),
      env(200, { id: 'g1', report_section_id: 's1', grade: '8.00' }),
      // The server counts two: a peer's concurrent save landed as well.
      env(
        200,
        detail({
          graded_section_count: 2,
          sections: [section({ report_section_id: 's1' }), section({ report_section_id: 's2' })],
        }),
      ),
    )
    const s = useEvaluationStore()
    await s.load(CTX.token, CTX.exerciseId, CTX.rid, CTX.evid)
    s.setGrade('s1', { grade: 8 })
    expect(s.gradedCount).toBe(1)

    await s.flush()

    expect(s.gradedCount).toBe(2)
  })

  it('flags a stale grade_version and requests a reload instead of overwriting', async () => {
    const mock = stubFetch(env(200, detail({ grade_version: 1 })))
    const s = useEvaluationStore()
    await s.load(CTX.token, CTX.exerciseId, CTX.rid, CTX.evid)
    s.setGrade('s1', { grade: 8 })

    // A reopen elsewhere moved the published grade on: our draft is against a dead version.
    s.observeGradeVersion(2)
    expect(s.needsReload).toBe(true)

    await s.flush()

    expect(mock.mock.calls.filter((c) => c[1]?.method === 'PUT')).toHaveLength(0)
    expect(s.isDirty('s1')).toBe(true)
  })
})
