import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as svc from '@/services/evaluations'

function env(status: number, data: unknown): Response {
  return new Response(JSON.stringify({ data }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function errEnv(status: number, code: string): Response {
  return new Response(JSON.stringify({ error: { code, message: 'nope', details: [] } }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const NESTED = '/api/v1/exercises/ex1/reports/r1/evaluations'

describe('evaluations service', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('getEvaluation GETs the report-nested evaluation path with a bearer token and unwraps data', async () => {
    const fetchMock = vi.fn().mockResolvedValue(env(200, { id: 'ev1', status: 'in_progress' }))
    vi.stubGlobal('fetch', fetchMock)
    const out = await svc.getEvaluation('tok', 'ex1', 'r1', 'ev1')
    expect(out).toEqual({ id: 'ev1', status: 'in_progress' })
    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toBe(`${NESTED}/ev1`)
    expect(init.method).toBe('GET')
    expect(init.headers.Authorization).toBe('Bearer tok')
  })

  it('putGrade PUTs the report-nested grades path with the grade as a two-decimal string', async () => {
    const fetchMock = vi.fn().mockResolvedValue(env(200, { id: 'g1', grade: '7.50' }))
    vi.stubGlobal('fetch', fetchMock)
    await svc.putGrade('tok', 'ex1', 'r1', 'ev1', 's1', { grade: 7.5, feedback: 'good' })
    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toBe(`${NESTED}/ev1/grades/s1`)
    expect(init.method).toBe('PUT')
    expect(JSON.parse(init.body)).toEqual({ grade: '7.50', feedback: 'good' })
  })

  it('putGrade forwards rubric_scores unchanged for rubric mode', async () => {
    const fetchMock = vi.fn().mockResolvedValue(env(200, { id: 'g1' }))
    vi.stubGlobal('fetch', fetchMock)
    const rubric_scores = [{ criterion: 'clarity', score: 3, note: null }]
    await svc.putGrade('tok', 'ex1', 'r1', 'ev1', 's1', { rubric_scores })
    const body = JSON.parse(fetchMock.mock.calls[0]![1].body)
    expect(body).toEqual({ rubric_scores })
    expect(body.grade).toBeUndefined()
  })

  // The route returns the whole W5-3 breakdown, not the single evaluation: finalize settles
  // the report-level gate, so the caller needs the new aggregate too.
  it('finalizeEvaluation POSTs the nested finalize path and returns the updated evaluation', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(env(200, { report_id: 'r1', finalize_gate_satisfied: true }))
    vi.stubGlobal('fetch', fetchMock)
    const out = await svc.finalizeEvaluation('tok', 'ex1', 'r1', 'ev1')
    expect(out.finalize_gate_satisfied).toBe(true)
    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toBe(`${NESTED}/ev1/finalize`)
    expect(init.method).toBe('POST')
  })

  it('reopenEvaluation sends the mandatory reason in the body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(env(200, { report_id: 'r1', evaluations: [] }))
    vi.stubGlobal('fetch', fetchMock)
    await svc.reopenEvaluation('tok', 'ex1', 'r1', 'ev1', 'grade was wrong')
    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toBe(`${NESTED}/ev1/reopen`)
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ reason: 'grade was wrong' })
  })

  it('listEvaluationsForReport hits the report-scoped evaluations path', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      env(200, {
        report_id: 'r1',
        aggregate: { grade_version: 2, counted_evaluator_count: 2 },
        evaluations: [{ id: 'ev1' }, { id: 'ev2' }],
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const out = await svc.listEvaluationsForReport('tok', 'ex1', 'r1')
    expect(out.evaluations).toHaveLength(2)
    expect(out.aggregate.grade_version).toBe(2)
    expect(fetchMock.mock.calls[0]![0]).toBe(NESTED)
  })

  it('exposes grade_version from the detail response', async () => {
    const fetchMock = vi.fn().mockResolvedValue(env(200, { id: 'ev1', grade_version: 3 }))
    vi.stubGlobal('fetch', fetchMock)
    const out = await svc.getEvaluation('tok', 'ex1', 'r1', 'ev1')
    expect(out.grade_version).toBe(3)
  })

  it('throws ApiError with status 403 so views can render a scope message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(errEnv(403, 'forbidden')))
    await expect(svc.getEvaluation('tok', 'ex1', 'r1', 'ev1')).rejects.toMatchObject({
      code: 'forbidden',
      status: 403,
    })
  })
})
