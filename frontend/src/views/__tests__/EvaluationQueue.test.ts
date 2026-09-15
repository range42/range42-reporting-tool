import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import EvaluationQueue from '@/views/evaluations/EvaluationQueue.vue'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/services/http'
import * as svc from '@/services/evaluations'
import type { EvaluationAssignment } from '@/services/evaluations'
import type { QueueEntry } from '@/lib/groupByDeadline'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const push = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { exerciseId: 'ex1' } }),
  useRouter: () => ({ push }),
  RouterLink: { template: '<a><slot /></a>' },
}))

function entry(over: Partial<QueueEntry> = {}): QueueEntry {
  return {
    evaluationId: 'ev1',
    reportId: 'r1',
    reportName: 'SITREP #6',
    teamName: 'Team Alpha',
    templateName: 'SITREP',
    submittedAt: '2026-09-09T09:00:00Z',
    dueAt: '2026-09-10T18:00:00Z',
    gradedSectionCount: 2,
    gradableSectionCount: 5,
    ...over,
  }
}

function mountQueue(entries: QueueEntry[], aiAvailable = false) {
  return mount(EvaluationQueue, {
    props: { entries, aiAvailable },
    global: { plugins: [i18n] },
  })
}

describe('EvaluationQueue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    push.mockClear()
    vi.restoreAllMocks()
  })

  it('renders one group header per deadline', () => {
    const w = mountQueue([
      entry(),
      entry({ evaluationId: 'ev2', reportId: 'r2', dueAt: '2026-09-11T18:00:00Z' }),
      entry({ evaluationId: 'ev3', reportId: 'r3' }),
    ])
    expect(w.findAll('[data-test="deadline-group"]')).toHaveLength(2)
  })

  it('renders one row per assigned report with team, template, and submitted time', () => {
    const w = mountQueue([entry()])
    const rows = w.findAll('[data-test="queue-row"]')
    expect(rows).toHaveLength(1)
    const text = rows[0]!.text()
    expect(text).toContain('Team Alpha')
    expect(text).toContain('SITREP #6')
    expect(text).toContain('SITREP')
    expect(w.get('[data-test="queue-submitted-ev1"]').text()).not.toBe('')
  })

  it('shows graded progress as n/total for an in-progress evaluation', () => {
    const w = mountQueue([entry()])
    expect(w.get('[data-test="queue-progress-ev1"]').text()).toBe('2/5')
  })

  it('renders an empty state when nothing is assigned', () => {
    const w = mountQueue([])
    expect(w.get('[data-test="queue-empty"]').text()).toBe(en.evaluations.queueEmpty)
    expect(w.findAll('[data-test="queue-row"]')).toHaveLength(0)
  })

  it('navigates to the evaluation route when a row action is clicked', async () => {
    const w = mountQueue([entry()])
    await w.get('[data-test="queue-open-ev1"]').trigger('click')
    expect(push).toHaveBeenCalledWith({
      name: 'evaluation',
      params: { exerciseId: 'ex1', rid: 'r1', evid: 'ev1' },
    })
  })

  it('shows a compare-across-teams action for a deadline group with two or more teams', () => {
    const w = mountQueue([
      entry(),
      entry({ evaluationId: 'ev2', reportId: 'r2', teamName: 'Team Bravo' }),
    ])
    expect(w.findAll('[data-test="compare-group"]')).toHaveLength(1)
  })

  it('hides the compare action for a single-report group', () => {
    const w = mountQueue([entry()])
    expect(w.find('[data-test="compare-group"]').exists()).toBe(false)
  })

  it('hides the compare action when one team filed twice against a deadline', () => {
    // Two reports, one team: nothing to compare across.
    const w = mountQueue([
      entry(),
      entry({ evaluationId: 'ev2', reportId: 'r2', reportName: 'SITREP #7' }),
    ])
    expect(w.find('[data-test="compare-group"]').exists()).toBe(false)
  })

  it('lists not-yet-submitted assignments in a separate section', () => {
    const w = mountQueue([
      entry(),
      entry({ evaluationId: 'ev9', reportId: 'r9', submittedAt: null }),
    ])
    const upcoming = w.get('[data-test="queue-upcoming"]')
    expect(upcoming.text()).toContain('SITREP #6')
    expect(upcoming.findAll('[data-test="queue-row"]')).toHaveLength(1)
    // The unsubmitted row is not inside a deadline group.
    expect(w.findAll('[data-test="deadline-group"]')).toHaveLength(1)
    expect(w.get('[data-test="deadline-group"]').findAll('[data-test="queue-row"]')).toHaveLength(1)
  })

  it('omits the AI pre-check column when GET /ai/status reports unavailable', () => {
    const off = mountQueue([entry()], false)
    expect(off.find('[data-test="queue-ai-col"]').exists()).toBe(false)
    expect(off.find('[data-test="queue-ai-ev1"]').exists()).toBe(false)

    const on = mountQueue([entry()], true)
    expect(on.get('[data-test="queue-ai-col"]').text()).toBe(en.evaluations.colAi)
    expect(on.find('[data-test="queue-ai-ev1"]').exists()).toBe(true)
  })

  it("fetches the caller's own assignments when no rows are supplied", async () => {
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'u1', email: 'e', display_name: 'E', avatar_url: null, is_global_admin: false },
    })
    const assignment: EvaluationAssignment = {
      id: 'ev7',
      report_id: 'r7',
      report_name: 'SITREP #9',
      report_status: 'submitted',
      team_id: 't1',
      team_name: 'Team Delta',
      template_name: 'SITREP',
      due_at: '2026-09-12T18:00:00Z',
      submitted_at: '2026-09-11T09:00:00Z',
      status: 'assigned',
      graded_section_count: 1,
      gradable_section_count: 4,
    }
    const list = vi.spyOn(svc, 'listMyEvaluations').mockResolvedValue([assignment])

    const w = mount(EvaluationQueue, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(list).toHaveBeenCalledWith('tok', 'ex1')
    const row = w.get('[data-test="queue-row"]').text()
    expect(row).toContain('Team Delta')
    expect(row).toContain('SITREP #9')
    expect(w.get('[data-test="queue-progress-ev7"]').text()).toBe('1/4')
  })

  it('does not fetch when rows are supplied by a parent', async () => {
    const list = vi.spyOn(svc, 'listMyEvaluations')
    mountQueue([entry()])
    await flushPromises()
    expect(list).not.toHaveBeenCalled()
  })

  it('reports a failed queue load instead of showing an empty queue', async () => {
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'u1', email: 'e', display_name: 'E', avatar_url: null, is_global_admin: false },
    })
    vi.spyOn(svc, 'listMyEvaluations').mockRejectedValue(
      new ApiError('forbidden', 'no evaluator role here', [], undefined, 403),
    )

    const w = mount(EvaluationQueue, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(w.get('[data-test="queue-error"]').text()).toBe('no evaluator role here')
    expect(w.find('[data-test="queue-empty"]').exists()).toBe(false)
  })
})
