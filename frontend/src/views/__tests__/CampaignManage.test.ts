import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import CampaignManage from '@/views/settings/CampaignManage.vue'
import { useAuthStore } from '@/stores/auth'
import * as campaignsSvc from '@/services/campaigns'
import type { Campaign } from '@/services/campaigns'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

const push = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { exerciseId: 'ex1' } }),
  useRouter: () => ({ push }),
  RouterLink: {
    props: ['to'],
    template: '<a :href="typeof to === \'string\' ? to : JSON.stringify(to)"><slot /></a>',
  },
}))

function campaign(over: Partial<Campaign> = {}): Campaign {
  return {
    id: 'c1',
    exercise_id: 'ex1',
    name: 'Sitreps',
    description: null,
    report_count: 6,
    created_by: 'u1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...over,
  }
}

async function mountPage() {
  const wrapper = mount(CampaignManage, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

describe('CampaignManage.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    push.mockClear()
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'ga', email: 'a', display_name: 'Ada', avatar_url: null, is_global_admin: true },
    })
  })

  it('lists campaigns with their report count', async () => {
    vi.spyOn(campaignsSvc, 'listCampaigns').mockResolvedValue([campaign()])
    const wrapper = await mountPage()

    expect(wrapper.get('[data-test="campaign-row-c1"]').text()).toContain('Sitreps')
    expect(wrapper.get('[data-test="campaign-row-c1"]').text()).toContain('6')
  })

  it('shows an empty state when there are no campaigns', async () => {
    vi.spyOn(campaignsSvc, 'listCampaigns').mockResolvedValue([])
    const wrapper = await mountPage()

    expect(wrapper.find('[data-test="campaigns-empty"]').exists()).toBe(true)
  })

  it('surfaces a load error', async () => {
    vi.spyOn(campaignsSvc, 'listCampaigns').mockRejectedValue(new Error('boom'))
    const wrapper = await mountPage()

    expect(wrapper.find('[data-test="campaigns-load-error"]').exists()).toBe(true)
  })

  it('links "New campaign" to the create form', async () => {
    vi.spyOn(campaignsSvc, 'listCampaigns').mockResolvedValue([])
    const wrapper = await mountPage()

    const link = wrapper.get('[data-test="new-campaign-link"]')
    expect(link.attributes('href')).toContain('/exercises/ex1/campaigns/new')
  })

  it('links each row to its detail page', async () => {
    vi.spyOn(campaignsSvc, 'listCampaigns').mockResolvedValue([campaign()])
    const wrapper = await mountPage()

    const link = wrapper.get('[data-test="campaign-link-c1"]')
    expect(link.attributes('href')).toContain('/exercises/ex1/campaigns/c1')
  })

  it('deletes a campaign after confirmation and removes the row', async () => {
    vi.spyOn(campaignsSvc, 'listCampaigns').mockResolvedValue([campaign()])
    const del = vi.spyOn(campaignsSvc, 'deleteCampaign').mockResolvedValue(undefined)
    vi.stubGlobal(
      'confirm',
      vi.fn(() => true),
    )
    const wrapper = await mountPage()

    await wrapper.get('[data-test="delete-campaign-c1"]').trigger('click')
    await flushPromises()

    expect(del).toHaveBeenCalledWith('tok', 'ex1', 'c1')
    expect(wrapper.find('[data-test="campaign-row-c1"]').exists()).toBe(false)
  })

  it('does not delete when the confirmation is declined', async () => {
    vi.spyOn(campaignsSvc, 'listCampaigns').mockResolvedValue([campaign()])
    const del = vi.spyOn(campaignsSvc, 'deleteCampaign').mockResolvedValue(undefined)
    vi.stubGlobal(
      'confirm',
      vi.fn(() => false),
    )
    const wrapper = await mountPage()

    await wrapper.get('[data-test="delete-campaign-c1"]').trigger('click')
    await flushPromises()

    expect(del).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="campaign-row-c1"]').exists()).toBe(true)
  })

  it('surfaces a delete error without removing the row', async () => {
    vi.spyOn(campaignsSvc, 'listCampaigns').mockResolvedValue([campaign()])
    vi.spyOn(campaignsSvc, 'deleteCampaign').mockRejectedValue(new Error('boom'))
    vi.stubGlobal(
      'confirm',
      vi.fn(() => true),
    )
    const wrapper = await mountPage()

    await wrapper.get('[data-test="delete-campaign-c1"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-test="delete-campaign-error-c1"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="campaign-row-c1"]').exists()).toBe(true)
  })
})
