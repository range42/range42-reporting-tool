import { beforeEach, describe, expect, it, vi } from 'vitest'
import { selectPreviousEntry, useCampaignPairing } from '@/composables/useCampaignPairing'
import * as campaigns from '@/services/campaigns'
import * as evaluations from '@/services/evaluations'
import { ApiError } from '@/services/http'
import type { TimelineEntry } from '@/services/campaigns'
import type { ReportDetail } from '@/services/reports'

vi.mock('@/services/campaigns')
vi.mock('@/services/evaluations')

function entry(over: Partial<TimelineEntry> = {}): TimelineEntry {
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

function report(id: string): ReportDetail {
  return {
    id,
    exercise_id: 'ex1',
    team_id: 't1',
    template_id: 'tpl1',
    template_version_at_creation: 1,
    name: id,
    description: null,
    status: 'submitted',
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

describe('selectPreviousEntry', () => {
  it('selects the entry immediately before the current report in server order', () => {
    const entries = [
      entry({ report_id: 'r1' }),
      entry({ report_id: 'r2' }),
      entry({ report_id: 'r3' }),
    ]
    expect(selectPreviousEntry(entries, 'r2', 't1')?.report_id).toBe('r1')
  })

  it("restricts candidates to the current report's team", () => {
    const entries = [
      entry({ report_id: 'r1', team_id: 't2' }),
      entry({ report_id: 'r2', team_id: 't1' }),
      entry({ report_id: 'r3', team_id: 't1' }),
    ]
    expect(selectPreviousEntry(entries, 'r3', 't1')?.report_id).toBe('r2')
  })

  it('returns no previous entry for the first report in the campaign', () => {
    const entries = [entry({ report_id: 'r1' }), entry({ report_id: 'r2' })]
    expect(selectPreviousEntry(entries, 'r1', 't1')).toBeNull()
  })

  it('honours an explicit prev report id from the URL over the immediate predecessor', () => {
    const entries = [
      entry({ report_id: 'r1' }),
      entry({ report_id: 'r2' }),
      entry({ report_id: 'r3' }),
    ]
    expect(selectPreviousEntry(entries, 'r3', 't1', 'r1')?.report_id).toBe('r1')
  })

  it('does not re-sort the timeline entries it was given', () => {
    // Deliberately out of chronological order — selectPreviousEntry must use array order only.
    const entries = [
      entry({ report_id: 'r2', submitted_at: '2026-09-02T09:00:00Z' }),
      entry({ report_id: 'r1', submitted_at: '2026-09-01T09:00:00Z' }),
      entry({ report_id: 'r3', submitted_at: '2026-09-03T09:00:00Z' }),
    ]
    expect(selectPreviousEntry(entries, 'r3', 't1')?.report_id).toBe('r1')
  })
})

describe('useCampaignPairing', () => {
  beforeEach(() => vi.resetAllMocks())

  it('picks the campaign that contains the current report when the exercise has several', async () => {
    vi.mocked(campaigns.listCampaigns).mockResolvedValue([
      {
        id: 'c1',
        exercise_id: 'ex1',
        name: 'A',
        description: null,
        report_count: 2,
        created_by: 'u1',
        created_at: '',
        updated_at: '',
      },
      {
        id: 'c2',
        exercise_id: 'ex1',
        name: 'B',
        description: null,
        report_count: 2,
        created_by: 'u1',
        created_at: '',
        updated_at: '',
      },
    ])
    vi.mocked(campaigns.getCampaignTimeline).mockImplementation(async (_t, _e, cid) =>
      cid === 'c1'
        ? [entry({ report_id: 'x1' }), entry({ report_id: 'x2' })]
        : [entry({ report_id: 'r1' }), entry({ report_id: 'r2' })],
    )
    vi.mocked(campaigns.compareCampaignReports).mockResolvedValue([report('r1'), report('r2')])
    vi.mocked(evaluations.listEvaluationsForReport).mockRejectedValue(
      new ApiError('forbidden', 'no', [], undefined, 403),
    )

    const p = useCampaignPairing({
      token: 'tok',
      exerciseId: 'ex1',
      reportId: 'r2',
      userId: 'u1',
    })
    await p.load()

    expect(p.status.value).toBe('ready')
    expect(p.campaign.value?.id).toBe('c2')
    expect(p.previousEntry.value?.report_id).toBe('r1')
  })

  it('reports a no-campaign state when the report belongs to none', async () => {
    vi.mocked(campaigns.listCampaigns).mockResolvedValue([
      {
        id: 'c1',
        exercise_id: 'ex1',
        name: 'A',
        description: null,
        report_count: 1,
        created_by: 'u1',
        created_at: '',
        updated_at: '',
      },
    ])
    vi.mocked(campaigns.getCampaignTimeline).mockResolvedValue([entry({ report_id: 'other' })])

    const p = useCampaignPairing({
      token: 'tok',
      exerciseId: 'ex1',
      reportId: 'r9',
      userId: 'u1',
    })
    await p.load()

    expect(p.status.value).toBe('no_campaign')
    expect(campaigns.compareCampaignReports).not.toHaveBeenCalled()
  })

  it('exposes hasOwnPreviousEvaluation=false when the caller has no evaluation on the previous report', async () => {
    vi.mocked(campaigns.listCampaigns).mockResolvedValue([
      {
        id: 'c1',
        exercise_id: 'ex1',
        name: 'A',
        description: null,
        report_count: 2,
        created_by: 'u1',
        created_at: '',
        updated_at: '',
      },
    ])
    vi.mocked(campaigns.getCampaignTimeline).mockResolvedValue([
      entry({ report_id: 'r1' }),
      entry({ report_id: 'r2' }),
    ])
    vi.mocked(campaigns.compareCampaignReports).mockResolvedValue([report('r1'), report('r2')])
    vi.mocked(evaluations.listEvaluationsForReport).mockRejectedValue(
      new ApiError('forbidden', 'no', [], undefined, 403),
    )

    const p = useCampaignPairing({
      token: 'tok',
      exerciseId: 'ex1',
      reportId: 'r2',
      userId: 'u1',
    })
    await p.load()

    expect(p.status.value).toBe('ready')
    expect(p.hasOwnPreviousEvaluation.value).toBe(false)
    expect(p.previousGrades.value).toBeNull()
    expect(evaluations.listSectionGrades).not.toHaveBeenCalled()
  })

  it('loads previous grades only when the caller has their own previous evaluation', async () => {
    vi.mocked(campaigns.listCampaigns).mockResolvedValue([
      {
        id: 'c1',
        exercise_id: 'ex1',
        name: 'A',
        description: null,
        report_count: 2,
        created_by: 'u1',
        created_at: '',
        updated_at: '',
      },
    ])
    vi.mocked(campaigns.getCampaignTimeline).mockResolvedValue([
      entry({ report_id: 'r1' }),
      entry({ report_id: 'r2' }),
    ])
    vi.mocked(campaigns.compareCampaignReports).mockResolvedValue([report('r1'), report('r2')])
    vi.mocked(evaluations.listEvaluationsForReport).mockResolvedValue({
      report_id: 'r1',
      report_status: 'submitted',
      finalize_policy: 'all_must_finalize',
      finalize_gate_satisfied: false,
      aggregate: {
        overall_grade: null,
        grade_version: 0,
        counted_evaluator_count: 1,
        completed_evaluator_count: 0,
        aggregated_weight_total: '0',
      },
      evaluations: [
        {
          id: 'ev-prev',
          evaluator_id: 'u1',
          evaluator_display_name: null,
          status: 'completed',
          overall_grade: '7.50',
          aggregated_weight: '1',
          completed_at: '2026-09-01T10:00:00Z',
          finalized_by: null,
          finalize_is_admin_override: false,
          unassigned_at: null,
          unassign_reason: null,
          reopen_count: 0,
        },
      ],
    })
    vi.mocked(evaluations.listSectionGrades).mockResolvedValue([
      {
        id: 'g1',
        evaluation_id: 'ev-prev',
        report_section_id: 's1',
        grade: '7.50',
        pass_fail_result: null,
        rubric_scores: null,
        feedback: null,
        created_at: '',
        updated_at: '',
      },
    ])

    const p = useCampaignPairing({
      token: 'tok',
      exerciseId: 'ex1',
      reportId: 'r2',
      userId: 'u1',
    })
    await p.load()

    expect(p.hasOwnPreviousEvaluation.value).toBe(true)
    expect(evaluations.listSectionGrades).toHaveBeenCalledWith('tok', 'ex1', 'r1', 'ev-prev')
    expect(p.previousGrades.value).toHaveLength(1)
    expect(p.previousOverallGrade.value).toBe('7.50')
    expect(p.entries.value.map((e) => e.report_id)).toEqual(['r1', 'r2'])
  })

  it('reports a forbidden status when a campaign endpoint returns 403', async () => {
    vi.mocked(campaigns.listCampaigns).mockRejectedValue(
      new ApiError('forbidden', 'no', [], undefined, 403),
    )

    const p = useCampaignPairing({
      token: 'tok',
      exerciseId: 'ex1',
      reportId: 'r2',
      userId: 'u1',
    })
    await p.load()

    expect(p.status.value).toBe('forbidden')
  })
})
