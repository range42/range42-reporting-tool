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

  const SECTION = { name: 'S' } as svc.SectionInput
  const BUNDLE = { schema_version: 1, name: 'B' } as svc.TemplateBundle
  const T = '/api/v1/templates'

  it.each([
    [
      'listTemplates(status)',
      () => svc.listTemplates('tok', 'draft'),
      'GET',
      `${T}?per_page=100&status=draft`,
    ],
    ['getTemplate', () => svc.getTemplate('tok', 't1'), 'GET', `${T}/t1`],
    ['updateTemplate', () => svc.updateTemplate('tok', 't1', { name: 'N' }), 'PATCH', `${T}/t1`],
    ['deleteTemplate', () => svc.deleteTemplate('tok', 't1'), 'DELETE', `${T}/t1`],
    ['publishTemplate', () => svc.publishTemplate('tok', 't1'), 'POST', `${T}/t1/publish`],
    ['cloneTemplate', () => svc.cloneTemplate('tok', 't1'), 'POST', `${T}/t1/clone`],
    ['archiveTemplate', () => svc.archiveTemplate('tok', 't1'), 'POST', `${T}/t1/archive`],
    ['listVersions', () => svc.listVersions('tok', 't1'), 'GET', `${T}/t1/versions`],
    ['exportTemplate', () => svc.exportTemplate('tok', 't1'), 'GET', `${T}/t1/export`],
    ['importTemplate', () => svc.importTemplate('tok', BUNDLE), 'POST', `${T}/import`],
    ['addSection', () => svc.addSection('tok', 't1', SECTION), 'POST', `${T}/t1/sections`],
    [
      'updateSection',
      () => svc.updateSection('tok', 't1', 's1', { name: 'X' }),
      'PATCH',
      `${T}/t1/sections/s1`,
    ],
    ['deleteSection', () => svc.deleteSection('tok', 't1', 's1'), 'DELETE', `${T}/t1/sections/s1`],
    [
      'reorderSections',
      () => svc.reorderSections('tok', 't1', ['s2', 's1']),
      'POST',
      `${T}/t1/sections/reorder`,
    ],
  ] as const)('%s calls %s on the right URL', async (_name, call, method, url) => {
    const fetchMock = vi.fn().mockResolvedValue(env(200, {}))
    vi.stubGlobal('fetch', fetchMock)
    await call()
    const [calledUrl, init] = fetchMock.mock.calls[0]!
    expect(calledUrl).toBe(url)
    expect(init.method ?? 'GET').toBe(method)
  })

  it('reorderSections sends the ids in order', async () => {
    const fetchMock = vi.fn().mockResolvedValue(env(200, []))
    vi.stubGlobal('fetch', fetchMock)
    await svc.reorderSections('tok', 't1', ['s2', 's1'])
    expect(JSON.parse(fetchMock.mock.calls[0]![1].body)).toEqual({ ordered_ids: ['s2', 's1'] })
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
