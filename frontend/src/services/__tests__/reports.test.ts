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
})
