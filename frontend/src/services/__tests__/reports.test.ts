import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as svc from '@/services/reports'

function env(status: number, data: unknown): Response {
  return new Response(JSON.stringify({ data }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('reports service', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('listReports GETs the exercise-scoped path with token and unwraps the array', async () => {
    const fetchMock = vi.fn().mockResolvedValue(env(200, [{ id: 'r1', name: 'R' }]))
    vi.stubGlobal('fetch', fetchMock)
    const out = await svc.listReports('tok', 'ex1')
    expect(out).toEqual([{ id: 'r1', name: 'R' }])
    expect(fetchMock.mock.calls[0]![0]).toContain('/api/v1/exercises/ex1/reports')
    expect(fetchMock.mock.calls[0]![1].headers.Authorization).toBe('Bearer tok')
  })

  it('saveSection PATCHes the section path with version + body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(env(200, { id: 's1', version: 2 }))
    vi.stubGlobal('fetch', fetchMock)
    await svc.saveSection('tok', 'ex1', 'r1', 's1', {
      version: 1,
      body: { kind: 'rich_text', content: '<p>x</p>' },
    })
    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toContain('/api/v1/exercises/ex1/reports/r1/sections/s1')
    expect(init.method).toBe('PATCH')
    expect(JSON.parse(init.body)).toEqual({
      version: 1,
      body: { kind: 'rich_text', content: '<p>x</p>' },
    })
  })

  it('submitReport POSTs the submit path', async () => {
    const fetchMock = vi.fn().mockResolvedValue(env(200, { status: 'submitted' }))
    vi.stubGlobal('fetch', fetchMock)
    await svc.submitReport('tok', 'ex1', 'r1')
    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toContain('/api/v1/exercises/ex1/reports/r1/submit')
    expect(init.method).toBe('POST')
  })

  it('approveReport POSTs the approve path with the decision body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(env(200, { status: 'submitted' }))
    vi.stubGlobal('fetch', fetchMock)
    await svc.approveReport('tok', 'ex1', 'r1', { step: 2, comment: 'ok' })
    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toContain('/api/v1/exercises/ex1/reports/r1/approve')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ step: 2, comment: 'ok' })
  })

  it('rejectReport POSTs the reject path with the required comment', async () => {
    const fetchMock = vi.fn().mockResolvedValue(env(200, { status: 'draft' }))
    vi.stubGlobal('fetch', fetchMock)
    await svc.rejectReport('tok', 'ex1', 'r1', { comment: 'needs work' })
    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toContain('/api/v1/exercises/ex1/reports/r1/reject')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ comment: 'needs work' })
  })

  it('recallReport POSTs the recall path', async () => {
    const fetchMock = vi.fn().mockResolvedValue(env(200, { status: 'draft' }))
    vi.stubGlobal('fetch', fetchMock)
    await svc.recallReport('tok', 'ex1', 'r1')
    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toContain('/api/v1/exercises/ex1/reports/r1/recall')
    expect(init.method).toBe('POST')
  })

  it('listPendingApproval filters the list by pending_approval status', async () => {
    const fetchMock = vi.fn().mockResolvedValue(env(200, []))
    vi.stubGlobal('fetch', fetchMock)
    await svc.listPendingApproval('tok', 'ex1', 'team1')
    const url = fetchMock.mock.calls[0]![0] as string
    expect(url).toContain('/api/v1/exercises/ex1/reports')
    expect(url).toContain('status=pending_approval')
    expect(url).toContain('team_id=team1')
  })
})
