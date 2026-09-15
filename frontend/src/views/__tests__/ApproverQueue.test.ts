import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import ApproverQueue from '@/views/reports/ApproverQueue.vue'
import { useAuthStore } from '@/stores/auth'
import * as reports from '@/services/reports'
import * as exercises from '@/services/exercises'
import type { Report, ReportDetail } from '@/services/reports'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { exerciseId: 'ex1' } }),
  // AppShell renders the logout control and needs a router.
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { template: '<a><slot /></a>' },
}))

function pending(id: string, name: string): Report {
  return {
    id,
    exercise_id: 'ex1',
    team_id: 't1',
    template_id: 'tpl1',
    template_version_at_creation: 1,
    name,
    description: null,
    status: 'pending_approval',
    approval_required: true,
    due_at: null,
    submitted_at: null,
    assigned_writer_id: null,
    section_count: 1,
    can_approve: true,
  }
}

function detail(canApprove: boolean, over: Partial<ReportDetail> = {}): ReportDetail {
  return {
    id: 'r1',
    exercise_id: 'ex1',
    team_id: 't1',
    template_id: 'tpl1',
    template_version_at_creation: 1,
    name: 'Report One',
    description: null,
    status: 'pending_approval',
    approval_required: true,
    due_at: null,
    submitted_at: null,
    assigned_writer_id: null,
    writer_notes: null,
    metadata: null,
    sections: [],
    approval_chain: null,
    approval_cycle: 1,
    approval_records: [],
    can_approve: canApprove,
    ...over,
  }
}

function approvalRecord(step: number, cycle: number) {
  return {
    id: `a${step}-${cycle}`,
    report_id: 'r1',
    approver_id: 'u1',
    step,
    cycle,
    action: 'approved' as const,
    is_admin_override: false,
    comment: null,
    created_at: '2026-09-15T10:00:00Z',
  }
}

function mountQueue() {
  return mount(ApproverQueue, { global: { plugins: [i18n] } })
}

function setAuth(isAdmin: boolean) {
  useAuthStore().setSession({
    access_token: 'tok',
    token_type: 'bearer',
    user: { id: 'a', email: 'a', display_name: 'a', avatar_url: null, is_global_admin: isAdmin },
  })
}

describe('ApproverQueue.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.restoreAllMocks()
    vi.spyOn(exercises, 'getMyCapabilities').mockResolvedValue({
      is_global_admin: false,
      capabilities: ['reports:approve'],
    })
    setAuth(false)
  })

  it('renders the pending queue', async () => {
    vi.spyOn(reports, 'listPendingApproval').mockResolvedValue([pending('r1', 'Report One')])
    const w = mountQueue()
    await flushPromises()
    expect(w.findAll('[data-test="queue-item"]')).toHaveLength(1)
    expect(w.text()).toContain('Report One')
  })

  it('shows the decision block after selecting an approvable report', async () => {
    vi.spyOn(reports, 'listPendingApproval').mockResolvedValue([pending('r1', 'Report One')])
    vi.spyOn(reports, 'getReport').mockResolvedValue(detail(true))
    const w = mountQueue()
    await flushPromises()
    await w.find('[data-test="queue-item"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-test="decision-block"]').exists()).toBe(true)
    // reject is disabled until a note is entered; approve is enabled
    expect(w.find('[data-test="reject-btn"]').attributes('disabled')).toBeDefined()
    await w.find('[data-test="decision-note"]').setValue('needs work')
    expect(w.find('[data-test="reject-btn"]').attributes('disabled')).toBeUndefined()
  })

  it('approve calls the service with the report id', async () => {
    vi.spyOn(reports, 'listPendingApproval').mockResolvedValue([pending('r1', 'Report One')])
    vi.spyOn(reports, 'getReport').mockResolvedValue(detail(true))
    const approve = vi.spyOn(reports, 'approveReport').mockResolvedValue(detail(true))
    const w = mountQueue()
    await flushPromises()
    await w.find('[data-test="queue-item"]').trigger('click')
    await flushPromises()
    await w.find('[data-test="approve-btn"]').trigger('click')
    await flushPromises()
    expect(approve).toHaveBeenCalledWith('tok', 'ex1', 'r1', {})
  })

  it('hides the decision block when the caller cannot act', async () => {
    vi.spyOn(reports, 'listPendingApproval').mockResolvedValue([pending('r1', 'Report One')])
    vi.spyOn(reports, 'getReport').mockResolvedValue(detail(false))
    const w = mountQueue()
    await flushPromises()
    await w.find('[data-test="queue-item"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-test="decision-block"]').exists()).toBe(false)
    expect(w.find('[data-test="not-approver"]').exists()).toBe(true)
  })

  // A recall or rejection bumps the report's cycle, superseding the approvals of the withdrawn
  // submission. Counting them would mark step 1 done and skip it on the resubmission — the
  // client-side half of the same bug the backend cycle fixes.

  /** The first chain step's markup; the dot class carries its state. */
  function firstStep(w: ReturnType<typeof mountQueue>): string {
    const step = w.findAll('[data-test="chain-step"]')[0]
    if (!step) throw new Error('no chain step rendered')
    return step.html()
  }

  async function selectWith(over: Partial<ReportDetail>) {
    vi.spyOn(reports, 'listPendingApproval').mockResolvedValue([pending('r1', 'Report One')])
    vi.spyOn(reports, 'getReport').mockResolvedValue(detail(true, over))
    const w = mountQueue()
    await flushPromises()
    await w.find('[data-test="queue-item"]').trigger('click')
    await flushPromises()
    return w
  }

  it('counts an approval from the current submission as done', async () => {
    const w = await selectWith({
      approval_cycle: 1,
      approval_records: [approvalRecord(1, 1)],
      approval_chain: [
        { role_key: 'team_approver', required: true },
        { role_key: 'team_approver', required: true },
      ],
    })
    expect(firstStep(w)).toContain('bg-emerald-500')
  })

  it('ignores an approval superseded by a recall', async () => {
    const w = await selectWith({
      approval_cycle: 2,
      approval_records: [approvalRecord(1, 1)],
      approval_chain: [
        { role_key: 'team_approver', required: true },
        { role_key: 'team_approver', required: true },
      ],
    })
    const first = firstStep(w)
    expect(first).not.toContain('bg-emerald-500')
    expect(first).toContain('bg-amber-500')
  })
})
