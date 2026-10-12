import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import TeamEvaluators from '@/views/settings/TeamEvaluators.vue'
import { useAuthStore } from '@/stores/auth'
import * as evalSvc from '@/services/evaluations'
import * as teamsSvc from '@/services/teams'
import type { TeamEvaluatorSummary } from '@/services/teams'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { exerciseId: 'ex1', teamId: 't1' } }),
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { template: '<a><slot /></a>' },
}))

const CANDIDATES = [
  { user_id: 'u1', display_name: 'Eve', email: 'eve@x' },
  { user_id: 'u2', display_name: 'Ivan', email: 'ivan@x' },
]

function assignment(over: Partial<TeamEvaluatorSummary> = {}): TeamEvaluatorSummary {
  return {
    id: 'te1',
    team_id: 't1',
    evaluator_id: 'u1',
    display_name: 'Eve',
    email: 'eve@x',
    created_at: '2026-01-01T00:00:00Z',
    ...over,
  }
}

function arrange(rows: TeamEvaluatorSummary[], candidates = CANDIDATES) {
  vi.spyOn(evalSvc, 'listEvaluatorCandidates').mockResolvedValue(candidates)
  vi.spyOn(teamsSvc, 'listTeamEvaluators').mockResolvedValue(rows)
}

async function mountPage() {
  const wrapper = mount(TeamEvaluators, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

describe('TeamEvaluators', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'ga', email: 'a', display_name: 'Ada', avatar_url: null, is_global_admin: true },
    })
  })

  it('loads candidates and current assignments on mount', async () => {
    arrange([assignment()])
    const wrapper = await mountPage()

    expect(wrapper.get('[data-test="assign-row-te1"]').text()).toContain('Eve')
    expect(evalSvc.listEvaluatorCandidates).toHaveBeenCalledWith('tok', 'ex1')
    expect(teamsSvc.listTeamEvaluators).toHaveBeenCalledWith('tok', 'ex1', 't1')
  })

  it('renders empty states when there are no candidates or assignments', async () => {
    arrange([], [])
    const wrapper = await mountPage()

    expect(wrapper.find('[data-test="assign-no-candidates"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="assign-none"]').exists()).toBe(true)
  })

  it('adding an evaluator calls the service then reloads the list', async () => {
    arrange([])
    vi.spyOn(teamsSvc, 'addTeamEvaluator').mockResolvedValue(assignment())
    const wrapper = await mountPage()

    vi.mocked(teamsSvc.listTeamEvaluators).mockResolvedValue([assignment()])
    await wrapper.get('[data-test="assign-pick"]').setValue('u1')
    await wrapper.get('[data-test="assign-submit"]').trigger('click')
    await flushPromises()

    expect(teamsSvc.addTeamEvaluator).toHaveBeenCalledWith('tok', 'ex1', 't1', 'u1')
    expect(wrapper.get('[data-test="assign-row-te1"]').text()).toContain('Eve')
  })

  it('removing an evaluator calls the service then reloads the list', async () => {
    arrange([assignment()])
    vi.spyOn(teamsSvc, 'removeTeamEvaluator').mockResolvedValue(undefined)
    const wrapper = await mountPage()

    vi.mocked(teamsSvc.listTeamEvaluators).mockResolvedValue([])
    await wrapper.get('[data-test="assign-remove-te1"]').trigger('click')
    await flushPromises()

    expect(teamsSvc.removeTeamEvaluator).toHaveBeenCalledWith('tok', 'ex1', 't1', 'u1')
    expect(wrapper.find('[data-test="assign-row-te1"]').exists()).toBe(false)
  })

  it('surfaces a load error', async () => {
    vi.spyOn(evalSvc, 'listEvaluatorCandidates').mockRejectedValue(new Error('boom'))
    const wrapper = await mountPage()

    expect(wrapper.find('[data-test="assign-load-error"]').exists()).toBe(true)
  })
})
