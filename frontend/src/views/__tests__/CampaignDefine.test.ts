import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import CampaignDefine from '@/views/settings/CampaignDefine.vue'
import { useAuthStore } from '@/stores/auth'
import * as templatesSvc from '@/services/templates'
import * as campaignsSvc from '@/services/campaigns'
import type { TemplateSummary } from '@/services/templates'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

const push = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { exerciseId: 'ex1' } }),
  useRouter: () => ({ push }),
  RouterLink: { template: '<a><slot /></a>' },
}))

function template(over: Partial<TemplateSummary> = {}): TemplateSummary {
  return {
    id: 'tpl1',
    lineage_id: 'lin1',
    version: 1,
    name: 'SITREP',
    report_type: 'sitrep',
    description: null,
    status: 'published',
    section_count: 1,
    ...over,
  }
}

async function mountPage() {
  vi.spyOn(templatesSvc, 'listTemplates').mockResolvedValue([template()])
  const wrapper = mount(CampaignDefine, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

describe('CampaignDefine', () => {
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

  it('starts with one empty spec row and disables submit', async () => {
    const wrapper = await mountPage()

    expect(wrapper.findAll('[data-test^="spec-row-"]')).toHaveLength(1)
    expect(wrapper.get('[data-test="define-submit"]').attributes('disabled')).toBeDefined()
  })

  it('adding a spec row appends another; removing drops it', async () => {
    const wrapper = await mountPage()

    await wrapper.get('[data-test="add-spec"]').trigger('click')
    expect(wrapper.findAll('[data-test^="spec-row-"]')).toHaveLength(2)

    await wrapper.get('[data-test="remove-spec-1"]').trigger('click')
    expect(wrapper.findAll('[data-test^="spec-row-"]')).toHaveLength(1)
  })

  it('enables submit once a name and a spec template are set', async () => {
    const wrapper = await mountPage()

    await wrapper.get('[data-test="define-name"]').setValue('SITREP campaign')
    await wrapper.get('[data-test="spec-template-0"]').setValue('tpl1')

    expect(wrapper.get('[data-test="define-submit"]').attributes('disabled')).toBeUndefined()
  })

  it('submits report_specs with ISO due/available dates and navigates to the new campaign evaluators screen', async () => {
    const create = vi
      .spyOn(campaignsSvc, 'createCampaign')
      .mockResolvedValue({ id: 'c1', name: 'C', report_count: 3 } as never)
    const wrapper = await mountPage()

    await wrapper.get('[data-test="define-name"]').setValue('SITREP campaign')
    await wrapper.get('[data-test="spec-template-0"]').setValue('tpl1')
    await wrapper.get('[data-test="spec-available-0"]').setValue('2026-11-25T00:00')
    await wrapper.get('[data-test="spec-due-0"]').setValue('2026-12-01T00:00')
    await wrapper.get('[data-test="define-form"]').trigger('submit')
    await flushPromises()

    expect(create).toHaveBeenCalledWith('tok', 'ex1', {
      name: 'SITREP campaign',
      report_specs: [
        {
          template_id: 'tpl1',
          available_at: new Date('2026-11-25T00:00').toISOString(),
          due_at: new Date('2026-12-01T00:00').toISOString(),
        },
      ],
    })
    expect(push).toHaveBeenCalledWith('/exercises/ex1/campaigns/c1/evaluators')
  })

  it('surfaces a create error without navigating', async () => {
    vi.spyOn(campaignsSvc, 'createCampaign').mockRejectedValue(new Error('boom'))
    const wrapper = await mountPage()

    await wrapper.get('[data-test="define-name"]').setValue('C')
    await wrapper.get('[data-test="spec-template-0"]').setValue('tpl1')
    await wrapper.get('[data-test="define-form"]').trigger('submit')
    await flushPromises()

    expect(wrapper.find('[data-test="define-error"]').exists()).toBe(true)
    expect(push).not.toHaveBeenCalled()
  })
})
