import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useWriterPreviousReport } from '@/composables/useWriterPreviousReport'
import * as campaigns from '@/services/campaigns'
import * as reports from '@/services/reports'
import * as evaluations from '@/services/evaluations'
import { ApiError } from '@/services/http'
import type { TimelineEntry } from '@/services/campaigns'
import type { ReportDetail } from '@/services/reports'
import type { EvaluationSummary } from '@/services/evaluations'

vi.mock('@/services/campaigns')
vi.mock('@/services/reports')
vi.mock('@/services/evaluations')

function entry(over: Partial<TimelineEntry> = {}): TimelineEntry {
  return {
    report_id: 'r1',
    name: 'Day 1',
    status: 'evaluated',
    team_id: 't1',
    team_name: 'Blue',
    submitted_at: '2026-09-01T09:00:00Z',
    due_at: null,
    created_at: '2026-09-01T08:00:00Z',
    ...over,
  }
}

function report(id: string): ReportDetail {
  return {
    id,
    exercise_id: 'ex1',
    team_id: 't1',
    template_id: 'tpl1',
    template_version_at_creation: 1,
    name: id,
    description: null,
    status: 'evaluated',
    approval_required: false,
    due_at: null,
    submitted_at: '2026-09-01T09:00:00Z',
    assigned_writer_id: null,
    writer_notes: null,
    metadata: null,
    sections: [],
    approval_chain: null,
    approval_cycle: 1,
    approval_records: [],
    can_approve: false,
  }
}

function summary(over: Partial<EvaluationSummary> = {}): EvaluationSummary {
  return {
    report_id: 'r0',
    overall_grade: '8.00',
    overall_feedback: 'Solid overall.',
    evaluated_at: '2026-09-01T00:00:00Z',
    section_grades: [],
    ...over,
  }
}

function campaign(id: string) {
  return {
    id,
    exercise_id: 'ex1',
    name: 'Sitreps',
    description: null,
    report_count: 2,
    created_by: 'u1',
    created_at: '',
    updated_at: '',
  }
}

describe('useWriterPreviousReport', () => {
  beforeEach(() => vi.resetAllMocks())

  it('resolves the previous same-team report in the current report campaign, content + scores', async () => {
    vi.mocked(campaigns.listCampaigns).mockResolvedValue([campaign('c1')])
    vi.mocked(campaigns.getCampaignTimeline).mockResolvedValue([
      entry({ report_id: 'r0', name: 'Day 1' }),
      entry({ report_id: 'r1', name: 'Day 2', status: 'draft' }),
    ])
    vi.mocked(reports.getReport).mockResolvedValue(report('r0'))
    vi.mocked(evaluations.getReportEvaluationSummary).mockResolvedValue(summary())

    const result = useWriterPreviousReport({
      token: 'tok',
      exerciseId: 'ex1',
      reportId: 'r1',
      teamId: 't1',
    })
    await result.load()

    expect(result.status.value).toBe('ready')
    expect(result.previousReport.value?.id).toBe('r0')
    expect(result.previousSummary.value?.overall_grade).toBe('8.00')
  })

  it('is ready with a null summary when the previous report is not evaluated yet', async () => {
    vi.mocked(campaigns.listCampaigns).mockResolvedValue([campaign('c1')])
    vi.mocked(campaigns.getCampaignTimeline).mockResolvedValue([
      entry({ report_id: 'r0', status: 'submitted' }),
      entry({ report_id: 'r1', status: 'draft' }),
    ])
    vi.mocked(reports.getReport).mockResolvedValue(report('r0'))
    vi.mocked(evaluations.getReportEvaluationSummary).mockRejectedValue(
      new ApiError('HTTP_ERROR', 'not_yet_evaluated', [], undefined, 409),
    )

    const result = useWriterPreviousReport({
      token: 'tok',
      exerciseId: 'ex1',
      reportId: 'r1',
      teamId: 't1',
    })
    await result.load()

    expect(result.status.value).toBe('ready')
    expect(result.previousReport.value?.id).toBe('r0')
    expect(result.previousSummary.value).toBeNull()
  })

  it('is no_campaign when the current report belongs to none', async () => {
    vi.mocked(campaigns.listCampaigns).mockResolvedValue([])
    const result = useWriterPreviousReport({
      token: 'tok',
      exerciseId: 'ex1',
      reportId: 'r1',
      teamId: 't1',
    })
    await result.load()
    expect(result.status.value).toBe('no_campaign')
    expect(result.previousReport.value).toBeNull()
  })

  it('is no_previous when the current report is the first in its campaign', async () => {
    vi.mocked(campaigns.listCampaigns).mockResolvedValue([campaign('c1')])
    vi.mocked(campaigns.getCampaignTimeline).mockResolvedValue([entry({ report_id: 'r1' })])
    const result = useWriterPreviousReport({
      token: 'tok',
      exerciseId: 'ex1',
      reportId: 'r1',
      teamId: 't1',
    })
    await result.load()
    expect(result.status.value).toBe('no_previous')
  })

  it('is error, not ready, when a non-409 failure interrupts the load', async () => {
    vi.mocked(campaigns.listCampaigns).mockRejectedValue(
      new ApiError('HTTP_ERROR', 'server exploded', [], undefined, 500),
    )
    const result = useWriterPreviousReport({
      token: 'tok',
      exerciseId: 'ex1',
      reportId: 'r1',
      teamId: 't1',
    })
    await result.load()
    expect(result.status.value).toBe('error')
    expect(result.error.value).toBe('server exploded')
  })

  it('rethrows (does not swallow) a non-409 error from the summary call', async () => {
    vi.mocked(campaigns.listCampaigns).mockResolvedValue([campaign('c1')])
    vi.mocked(campaigns.getCampaignTimeline).mockResolvedValue([
      entry({ report_id: 'r0' }),
      entry({ report_id: 'r1', status: 'draft' }),
    ])
    vi.mocked(reports.getReport).mockResolvedValue(report('r0'))
    vi.mocked(evaluations.getReportEvaluationSummary).mockRejectedValue(
      new ApiError('HTTP_ERROR', 'server exploded', [], undefined, 500),
    )
    const result = useWriterPreviousReport({
      token: 'tok',
      exerciseId: 'ex1',
      reportId: 'r1',
      teamId: 't1',
    })
    await result.load()
    expect(result.status.value).toBe('error')
  })
})
