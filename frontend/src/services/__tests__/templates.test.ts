import { describe, it, expect, vi, beforeEach } from 'vitest'
import * as svc from '@/services/templates'

function env(status: number, data: unknown): Response {
  return new Response(JSON.stringify({ data }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('templates service', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('listTemplates GETs with token and unwraps data', async () => {
    const fetchMock = vi.fn().mockResolvedValue(env(200, [{ id: 't1', name: 'A' }]))
    vi.stubGlobal('fetch', fetchMock)
    const out = await svc.listTemplates('tok')
    expect(out).toEqual([{ id: 't1', name: 'A' }])
    expect(fetchMock.mock.calls[0]![0]).toContain('/api/v1/templates')
    expect(fetchMock.mock.calls[0]![1].headers.Authorization).toBe('Bearer tok')
  })

  it('createTemplate POSTs the body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(env(201, { id: 't2' }))
    vi.stubGlobal('fetch', fetchMock)
    await svc.createTemplate('tok', { name: 'N', report_type: 'spot' })
    expect(fetchMock.mock.calls[0]![1].method).toBe('POST')
  })
})
