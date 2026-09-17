import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import CampaignEvaluation from '@/views/evaluations/CampaignEvaluation.vue'
import { useAuthStore } from '@/stores/auth'
import * as evalSvc from '@/services/evaluations'
import * as campaignSvc from '@/services/campaigns'
import { ApiError } from '@/services/http'
import type {
  EvaluationBreakdown,
  EvaluationDetail,
  GradableSection,
  SectionGrade,
} from '@/services/evaluations'
import type { Campaign, TimelineEntry } from '@/services/campaigns'
import type { ReportDetail, ReportSection } from '@/services/reports'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const routerReplace = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { exerciseId: 'ex1', rid: 'r1', evid: 'ev1' }, query: {} }),
  useRouter: () => ({ push: vi.fn(), replace: routerReplace, hasRoute: () => true }),
  RouterLink: {
    props: ['to'],
    template: '<a :data-to="JSON.stringify(to)"><slot /></a>',
  },
}))

const EVALUATOR = {
  id: 'u1',
  email: 'e',
  display_name: 'Eve',
  avatar_url: null,
  is_global_admin: false,
}

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

function currentDetail(over: Partial<EvaluationDetail> = {}): EvaluationDetail {
  return {
    id: 'ev1',
    report_id: 'r1',
    evaluator_id: 'u1',
    status: 'in_progress',
    overall_feedback: null,
    overall_grade: '7.50',
    completed_at: null,
    reopen_count: 0,
    graded_section_count: 2,
    gradable_section_count: 2,
    created_at: '',
    updated_at: '',
    report_name: 'Day 2 SITREP',
    report_status: 'under_evaluation',
    team_name: 'Blue Team Alpha',
    submitted_at: '2026-09-09T09:00:00Z',
    grade_version: 1,
    sections: [
      section({ report_section_id: 's1', section_def_id: 'd1', name: 'Findings', position: 0 }),
      section({ report_section_id: 's2', section_def_id: 'd2', name: 'Actions', position: 1 }),
    ],
    ...over,
  }
}

function reportSection(over: Partial<ReportSection> = {}): ReportSection {
  return {
    id: 'ps1',
    report_id: 'r0',
    section_def_id: 'd1',
    position: 0,
    name: 'Findings',
    description: null,
    field_type: 'rich_text',
    is_required: true,
    char_limit: null,
    choice_config: null,
    content: '<p>previous content</p>',
    content_plain: 'previous content',
    char_count: 17,
    choice_values: null,
    version: 1,
    last_edited_by: null,
    last_edited_at: null,
    created_at: '',
    updated_at: '',
    ...over,
  }
}

function reportDetail(id: string, sections: ReportSection[]): ReportDetail {
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
    sections,
    approval_chain: null,
    approval_cycle: 1,
    approval_records: [],
    can_approve: false,
  }
}

function timelineEntry(over: Partial<TimelineEntry> = {}): TimelineEntry {
  return {
    report_id: 'r1',
    name: 'Day',
    status: 'under_evaluation',
    team_id: 't1',
    team_name: 'Blue Team Alpha',
    submitted_at: '2026-09-09T09:00:00Z',
    due_at: null,
    created_at: '2026-09-08T00:00:00Z',
    ...over,
  }
}

const CAMPAIGN: Campaign = {
  id: 'c1',
  exercise_id: 'ex1',
  name: 'Autumn Campaign',
  description: null,
  report_count: 2,
  created_by: 'ga',
  created_at: '',
  updated_at: '',
}

function currentBreakdown(): EvaluationBreakdown {
  return {
    report_id: 'r1',
    report_status: 'under_evaluation',
    finalize_policy: 'all_must_finalize',
    finalize_gate_satisfied: false,
    aggregate: {
      overall_grade: '7.50',
      grade_version: 1,
      counted_evaluator_count: 1,
      completed_evaluator_count: 0,
      aggregated_weight_total: '1.00',
    },
    evaluations: [],
  }
}

function previousBreakdown(overallGrade: string | null = '8.00'): EvaluationBreakdown {
  return {
    report_id: 'r0',
    report_status: 'evaluated',
    finalize_policy: 'all_must_finalize',
    finalize_gate_satisfied: true,
    aggregate: {
      overall_grade: overallGrade,
      grade_version: 1,
      counted_evaluator_count: 1,
      completed_evaluator_count: 1,
      aggregated_weight_total: '1.00',
    },
    evaluations: [
      {
        id: 'ev0',
        evaluator_id: 'u1',
        evaluator_display_name: null,
        status: 'completed',
        overall_grade: overallGrade,
        aggregated_weight: '1.00',
        completed_at: '2026-09-01T10:00:00Z',
        finalized_by: null,
        finalize_is_admin_override: false,
        unassigned_at: null,
        unassign_reason: null,
        reopen_count: 0,
      },
    ],
  }
}

function previousGrade(over: Partial<SectionGrade> = {}): SectionGrade {
  return {
    id: 'pg1',
    evaluation_id: 'ev0',
    report_section_id: 'ps1',
    grade: '8.00',
    pass_fail_result: null,
    rubric_scores: null,
    feedback: 'Solid.',
    created_at: '',
    updated_at: '',
    ...over,
  }
}

interface SetupOptions {
  entries?: TimelineEntry[]
  campaigns?: Campaign[]
  hasOwnPrevious?: boolean
  previousOverallGrade?: string | null
  /** listCampaigns rejects with 403 instead of resolving. */
  forbidden?: boolean
}

async function setup(opts: SetupOptions = {}) {
  useAuthStore().setSession({ access_token: 'tok', token_type: 'bearer', user: EVALUATOR })

  vi.spyOn(evalSvc, 'getEvaluation').mockResolvedValue(currentDetail())
  if (opts.hasOwnPrevious === false) {
    vi.spyOn(evalSvc, 'listEvaluationsForReport').mockImplementation(async (_t, _e, rid) => {
      if (rid === 'r0') throw new ApiError('forbidden', 'no', [], undefined, 403)
      return currentBreakdown()
    })
  } else {
    vi.spyOn(evalSvc, 'listEvaluationsForReport').mockImplementation(async (_t, _e, rid) =>
      rid === 'r0' ? previousBreakdown(opts.previousOverallGrade ?? '8.00') : currentBreakdown(),
    )
  }
  vi.spyOn(evalSvc, 'listSectionGrades').mockResolvedValue([previousGrade()])

  if (opts.forbidden) {
    vi.spyOn(campaignSvc, 'listCampaigns').mockRejectedValue(
      new ApiError('forbidden', 'no', [], undefined, 403),
    )
  } else {
    vi.spyOn(campaignSvc, 'listCampaigns').mockResolvedValue(opts.campaigns ?? [CAMPAIGN])
  }
  vi.spyOn(campaignSvc, 'getCampaignTimeline').mockResolvedValue(
    opts.entries ?? [
      timelineEntry({ report_id: 'r0', name: 'Day 1', submitted_at: '2026-09-01T09:00:00Z' }),
      timelineEntry({ report_id: 'r1', name: 'Day 2', submitted_at: '2026-09-09T09:00:00Z' }),
    ],
  )
  vi.spyOn(campaignSvc, 'compareCampaignReports').mockResolvedValue([
    reportDetail('r0', [
      reportSection({ id: 'ps1', section_def_id: 'd1' }),
      reportSection({ id: 'ps2', section_def_id: 'd2', name: 'Actions' }),
    ]),
    reportDetail('r1', []),
  ])

  const w = mount(CampaignEvaluation, { global: { plugins: [i18n] } })
  await flushPromises()
  await flushPromises()
  return w
}

describe('CampaignEvaluation', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    routerReplace.mockClear()
    vi.restoreAllMocks()
  })

  it('renders one paired row per section with previous on the left and current on the right', async () => {
    const w = await setup()
    const rows = w.findAll('[data-test^="pair-row-"]')
    expect(rows.map((r) => r.attributes('data-test'))).toEqual(['pair-row-d1', 'pair-row-d2'])
    const row = w.get('[data-test="pair-row-d1"]')
    expect(row.find('[data-test="prev-card-d1"]').exists()).toBe(true)
    expect(row.find('[data-test="section-card-s1"]').exists()).toBe(true)
  })

  it('renders the spanning section header with grade mode, range, and weight', async () => {
    const w = await setup()
    const meta = w.get('[data-test="section-meta-s1"]').text()
    expect(meta).toContain('0')
    expect(meta).toContain('10')
    expect(meta).toContain('1')
  })

  it('renders only the current report’s grading controls', async () => {
    const w = await setup()
    const prevCard = w.get('[data-test="prev-card-d1"]')
    expect(prevCard.findAll('input')).toHaveLength(0)
    expect(prevCard.findAll('textarea')).toHaveLength(0)
    expect(prevCard.findAll('select')).toHaveLength(0)
    const currentCard = w.get('[data-test="section-card-s1"]')
    expect(currentCard.findAll('textarea').length).toBeGreaterThan(0)
  })

  it('renders the campaign navigator with the current report marked', async () => {
    const w = await setup()
    expect(w.get('[data-test="nav-pill-r1"]').attributes('aria-current')).toBe('true')
  })

  it('shows a first-report state with no previous pane when the report opens the campaign', async () => {
    const w = await setup({ entries: [timelineEntry({ report_id: 'r1' })] })
    expect(w.find('[data-test="campaign-empty"]').exists()).toBe(true)
    expect(w.find('[data-test="section-card-s1"]').exists()).toBe(true)
    expect(w.find('[data-test="prev-card-d1"]').exists()).toBe(false)
  })

  it('shows a no-campaign state with a link back to the single view', async () => {
    const w = await setup({ campaigns: [] })
    w.get('[data-test="no-campaign"]')
    const link = w.get('[data-test="mode-single"]')
    expect(JSON.parse(link.attributes('data-to')!)).toMatchObject({
      name: 'evaluation',
      params: { exerciseId: 'ex1', rid: 'r1', evid: 'ev1' },
    })
  })

  it('saves a current-section grade through the evaluation store', async () => {
    const putGrade = vi.spyOn(evalSvc, 'putGrade').mockResolvedValue(previousGrade({ id: 'g-new' }))
    const w = await setup()
    const numberInput = w.get('[data-test="grade-s1"] input')
    await numberInput.setValue(9)
    await numberInput.trigger('blur')
    await flushPromises()
    expect(putGrade).toHaveBeenCalled()
  })

  it('renders the vs-previous delta in the finalize bar from the two server overall grades', async () => {
    const w = await setup({ previousOverallGrade: '8.00' })
    const bar = w.get('[data-test="finalize-bar"]')
    expect(bar.find('[data-test="delta-badge"]').exists()).toBe(true)
  })

  it('omits the vs-previous delta when there is no previous report', async () => {
    const w = await setup({ entries: [timelineEntry({ report_id: 'r1' })] })
    const bar = w.get('[data-test="finalize-bar"]')
    expect(bar.find('[data-test="delta-badge"]').exists()).toBe(false)
  })

  it('shows the assignment-scope message when the campaign endpoints return 403', async () => {
    const w = await setup({ forbidden: true })
    expect(w.find('[data-test="evaluation-scope"]').exists()).toBe(true)
  })

  it('renders the view-mode switch with Campaign active and Single linked', async () => {
    const w = await setup()
    expect(w.get('[data-test="mode-campaign"]').attributes('aria-current')).toBe('page')
    expect(w.get('[data-test="mode-single"]').attributes('data-to')).toBeDefined()
  })

  it('fetches both reports in a single compare call', async () => {
    const compare = vi
      .spyOn(campaignSvc, 'compareCampaignReports')
      .mockResolvedValue([
        reportDetail('r0', [reportSection({ id: 'ps1', section_def_id: 'd1' })]),
        reportDetail('r1', []),
      ])
    await setup()
    expect(compare).toHaveBeenCalledTimes(1)
    expect(compare.mock.calls[0]![3]).toEqual(['r0', 'r1'])
  })
})
