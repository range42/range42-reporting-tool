import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import CampaignEvaluators from '@/views/settings/CampaignEvaluators.vue'
import { useAuthStore } from '@/stores/auth'
import * as evalSvc from '@/services/evaluations'
import * as campaignsSvc from '@/services/campaigns'
import type { CampaignEvaluatorSummary } from '@/services/campaigns'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { exerciseId: 'ex1', campaignId: 'c1' } }),
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { template: '<a><slot /></a>' },
}))

const CANDIDATES = [
  { user_id: 'u1', display_name: 'Eve', email: 'eve@x' },
  { user_id: 'u2', display_name: 'Ivan', email: 'ivan@x' },
]

function assignment(over: Partial<CampaignEvaluatorSummary> = {}): CampaignEvaluatorSummary {
  return {
    id: 'ce1',
    campaign_id: 'c1',
    evaluator_id: 'u1',
    display_name: 'Eve',
    email: 'eve@x',
    created_at: '2026-01-01T00:00:00Z',
    ...over,
  }
}

function arrange(rows: CampaignEvaluatorSummary[], candidates = CANDIDATES) {
  vi.spyOn(evalSvc, 'listEvaluatorCandidates').mockResolvedValue(candidates)
  vi.spyOn(campaignsSvc, 'listCampaignEvaluators').mockResolvedValue(rows)
}

async function mountPage() {
  const wrapper = mount(CampaignEvaluators, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

describe('CampaignEvaluators', () => {
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

    expect(wrapper.get('[data-test="assign-row-ce1"]').text()).toContain('Eve')
    expect(evalSvc.listEvaluatorCandidates).toHaveBeenCalledWith('tok', 'ex1')
    expect(campaignsSvc.listCampaignEvaluators).toHaveBeenCalledWith('tok', 'ex1', 'c1')
  })

  it('renders empty states when there are no candidates or assignments', async () => {
    arrange([], [])
    const wrapper = await mountPage()

    expect(wrapper.find('[data-test="assign-no-candidates"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="assign-none"]').exists()).toBe(true)
  })

  it('adding an evaluator calls the service then reloads the list', async () => {
    arrange([])
    vi.spyOn(campaignsSvc, 'addCampaignEvaluator').mockResolvedValue(assignment())
    const wrapper = await mountPage()

    vi.mocked(campaignsSvc.listCampaignEvaluators).mockResolvedValue([assignment()])
    await wrapper.get('[data-test="assign-pick"]').setValue('u1')
    await wrapper.get('[data-test="assign-submit"]').trigger('click')
    await flushPromises()

    expect(campaignsSvc.addCampaignEvaluator).toHaveBeenCalledWith('tok', 'ex1', 'c1', 'u1')
    expect(wrapper.get('[data-test="assign-row-ce1"]').text()).toContain('Eve')
  })

  it('removing an evaluator calls the service then reloads the list', async () => {
    arrange([assignment()])
    vi.spyOn(campaignsSvc, 'removeCampaignEvaluator').mockResolvedValue(undefined)
    const wrapper = await mountPage()

    vi.mocked(campaignsSvc.listCampaignEvaluators).mockResolvedValue([])
    await wrapper.get('[data-test="assign-remove-ce1"]').trigger('click')
    await flushPromises()

    expect(campaignsSvc.removeCampaignEvaluator).toHaveBeenCalledWith('tok', 'ex1', 'c1', 'u1')
    expect(wrapper.find('[data-test="assign-row-ce1"]').exists()).toBe(false)
  })

  it('surfaces a load error', async () => {
    vi.spyOn(evalSvc, 'listEvaluatorCandidates').mockRejectedValue(new Error('boom'))
    const wrapper = await mountPage()

    expect(wrapper.find('[data-test="assign-load-error"]').exists()).toBe(true)
  })
})
