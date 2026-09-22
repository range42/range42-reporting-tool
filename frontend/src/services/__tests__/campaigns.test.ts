import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as svc from '@/services/campaigns'
import { ApiError } from '@/services/http'

function env(status: number, data: unknown): Response {
  return new Response(JSON.stringify({ data }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function errEnv(status: number, code: string, message = 'no'): Response {
  return new Response(JSON.stringify({ error: { code, message, details: [] } }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function entry(over: Partial<svc.TimelineEntry> = {}): svc.TimelineEntry {
  return {
    report_id: 'r1',
    name: 'Day 1',
    status: 'submitted',
    team_id: 't1',
    team_name: 'Blue',
    submitted_at: '2026-09-01T09:00:00Z',
    due_at: null,
    created_at: '2026-09-01T08:00:00Z',
    ...over,
  }
}

describe('campaigns service', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('listCampaigns GETs the exercise-scoped campaigns path and unwraps data', async () => {
    // Arrange
    const fetchMock = vi.fn().mockResolvedValue(env(200, [{ id: 'c1', name: 'Campaign' }]))
    vi.stubGlobal('fetch', fetchMock)

    // Act
    const out = await svc.listCampaigns('tok', 'ex1')

    // Assert
    expect(out).toEqual([{ id: 'c1', name: 'Campaign' }])
    expect(fetchMock.mock.calls[0]![0]).toContain('/api/v1/exercises/ex1/campaigns')
    expect(fetchMock.mock.calls[0]![1].headers.Authorization).toBe('Bearer tok')
  })

  it('getCampaignTimeline returns entries in the order the server sent them', async () => {
    // Arrange
    const first = entry({ report_id: 'r1', name: 'Day 1' })
    const second = entry({ report_id: 'r2', name: 'Day 2' })
    const fetchMock = vi.fn().mockResolvedValue(env(200, [first, second]))
    vi.stubGlobal('fetch', fetchMock)

    // Act
    const out = await svc.getCampaignTimeline('tok', 'ex1', 'c1')

    // Assert
    expect(out.map((e) => e.report_id)).toEqual(['r1', 'r2'])
    expect(fetchMock.mock.calls[0]![0]).toContain('/api/v1/exercises/ex1/campaigns/c1/timeline')
  })

  it('compareCampaignReports repeats report_ids as separate query params', async () => {
    // Arrange
    const fetchMock = vi.fn().mockResolvedValue(env(200, []))
    vi.stubGlobal('fetch', fetchMock)

    // Act
    await svc.compareCampaignReports('tok', 'ex1', 'c1', ['r1', 'r2', 'r3'])

    // Assert
    const url = fetchMock.mock.calls[0]![0] as string
    expect(url).toContain('/api/v1/exercises/ex1/campaigns/c1/compare')
    expect(url.match(/report_ids=/g)).toHaveLength(3)
    expect(new URL(url, 'http://x').searchParams.getAll('report_ids')).toEqual(['r1', 'r2', 'r3'])
  })

  it('compareCampaignReports rejects more than eight report ids before calling fetch', async () => {
    // Arrange
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const nine = Array.from({ length: 9 }, (_, i) => `r${i + 1}`)

    // Act / Assert
    await expect(svc.compareCampaignReports('tok', 'ex1', 'c1', nine)).rejects.toThrow()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('surfaces the report_not_in_campaign 404 detail as an ApiError', async () => {
    // Arrange
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(errEnv(404, 'HTTP_ERROR', 'report_not_in_campaign')),
    )

    // Act / Assert
    await expect(svc.compareCampaignReports('tok', 'ex1', 'c1', ['r1'])).rejects.toBeInstanceOf(
      ApiError,
    )
  })

  it('surfaces a 403 so the view can render the assignment-scope message', async () => {
    // Arrange
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(errEnv(403, 'HTTP_ERROR', 'forbidden')))

    // Act / Assert
    await expect(svc.getCampaignTimeline('tok', 'ex1', 'c1')).rejects.toMatchObject({ status: 403 })
  })

  it('createCampaign POSTs the campaign path with the report_specs payload', async () => {
    // Arrange
    const fetchMock = vi
      .fn()
      .mockResolvedValue(env(201, { id: 'c1', name: 'SITREP', report_count: 6 }))
    vi.stubGlobal('fetch', fetchMock)

    // Act
    const out = await svc.createCampaign('tok', 'ex1', {
      name: 'SITREP',
      report_specs: [{ template_id: 'tpl1', available_at: '2026-01-01T00:00:00Z', due_at: null }],
    })

    // Assert
    expect(out.report_count).toBe(6)
    expect(fetchMock.mock.calls[0]![0]).toBe('/api/v1/exercises/ex1/campaigns')
    const body = JSON.parse(fetchMock.mock.calls[0]![1].body as string)
    expect(body.report_specs).toEqual([
      { template_id: 'tpl1', available_at: '2026-01-01T00:00:00Z', due_at: null },
    ])
  })

  it('listCampaignEvaluators GETs the evaluators sub-path', async () => {
    // Arrange
    const fetchMock = vi.fn().mockResolvedValue(
      env(200, [
        {
          id: 'ce1',
          campaign_id: 'c1',
          evaluator_id: 'u1',
          display_name: 'Eve',
          email: 'eve@x',
          created_at: 'now',
        },
      ]),
    )
    vi.stubGlobal('fetch', fetchMock)

    // Act
    const out = await svc.listCampaignEvaluators('tok', 'ex1', 'c1')

    // Assert
    expect(out).toHaveLength(1)
    expect(fetchMock.mock.calls[0]![0]).toBe('/api/v1/exercises/ex1/campaigns/c1/evaluators')
  })

  it('addCampaignEvaluator POSTs the evaluator_id', async () => {
    // Arrange
    const fetchMock = vi.fn().mockResolvedValue(env(201, { id: 'ce1' }))
    vi.stubGlobal('fetch', fetchMock)

    // Act
    await svc.addCampaignEvaluator('tok', 'ex1', 'c1', 'u1')

    // Assert
    expect(fetchMock.mock.calls[0]![0]).toBe('/api/v1/exercises/ex1/campaigns/c1/evaluators')
    expect(JSON.parse(fetchMock.mock.calls[0]![1].body as string)).toEqual({ evaluator_id: 'u1' })
  })

  it('removeCampaignEvaluator DELETEs the specific evaluator', async () => {
    // Arrange
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    // Act
    await svc.removeCampaignEvaluator('tok', 'ex1', 'c1', 'u1')

    // Assert
    expect(fetchMock.mock.calls[0]![0]).toBe('/api/v1/exercises/ex1/campaigns/c1/evaluators/u1')
    expect(fetchMock.mock.calls[0]![1].method).toBe('DELETE')
  })
})
