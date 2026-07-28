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

  it('importChoiceValues POSTs the CSV as multipart to the import endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(env(200, { id: 's1' }))
    vi.stubGlobal('fetch', fetchMock)
    const file = new File([new TextEncoder().encode('code,label\na,A\n')], 'values.csv', {
      type: 'text/csv',
    })
    await svc.importChoiceValues('tok', 't1', 's1', file)
    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toBe('/api/v1/templates/t1/sections/s1/choice-values/import')
    expect(init.method).toBe('POST')
    expect(init.body).toBeInstanceOf(FormData)
    expect(init.body.get('file')).toBe(file)
    // multipart boundary must come from the browser, not a manual header
    expect(init.headers['Content-Type']).toBeUndefined()
  })
})
