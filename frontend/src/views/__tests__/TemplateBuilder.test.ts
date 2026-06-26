import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import TemplateBuilder from '@/views/settings/TemplateBuilder.vue'
import { useAuthStore } from '@/stores/auth'
import * as svc from '@/services/templates'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ params: { id: 't1' } }),
  RouterLink: { template: '<a><slot /></a>' },
}))

const DRAFT: svc.TemplateDetail = {
  id: 't1',
  lineage_id: 'l1',
  version: 1,
  name: 'Spot',
  report_type: 'spot',
  description: null,
  status: 'draft',
  metadata: null,
  sections: [],
}

function mountBuilder() {
  return mount(TemplateBuilder, { global: { plugins: [i18n] } })
}

describe('TemplateBuilder.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'a', email: 'a', display_name: 'a', avatar_url: null, is_global_admin: true },
    })
    vi.spyOn(svc, 'listVersions').mockResolvedValue([
      { id: 't1', version: 1, status: 'draft', created_at: '' },
    ])
  })

  it('loads and shows the template name', async () => {
    vi.spyOn(svc, 'getTemplate').mockResolvedValue(DRAFT)
    const wrapper = mountBuilder()
    await flushPromises()
    expect((wrapper.get('[data-test="template-name"]').element as HTMLInputElement).value).toBe(
      'Spot',
    )
  })

  it('adds a section', async () => {
    vi.spyOn(svc, 'getTemplate').mockResolvedValue(DRAFT)
    const add = vi.spyOn(svc, 'addSection').mockResolvedValue({
      id: 's1',
      template_id: 't1',
      position: 0,
      name: 'New section',
      description: null,
      field_type: 'rich_text',
      char_limit: null,
      is_required: true,
      grade_mode: 'not_graded',
      grade_min: null,
      grade_max: null,
      grade_weight: 1,
      rubric_criteria: null,
      evaluation_criteria: null,
      choice_config: null,
      mitre_attack_tags: [],
      capec_tags: [],
      cwe_tags: [],
    })
    const wrapper = mountBuilder()
    await flushPromises()
    await wrapper.get('[data-test="add-section"]').trigger('click')
    await flushPromises()
    expect(add).toHaveBeenCalledWith(
      'tok',
      't1',
      expect.objectContaining({ field_type: 'rich_text' }),
    )
    expect(wrapper.find('[data-test="section-row-s1"]').exists()).toBe(true)
  })

  it('disables editing for a published template', async () => {
    vi.spyOn(svc, 'getTemplate').mockResolvedValue({ ...DRAFT, status: 'published' })
    const wrapper = mountBuilder()
    await flushPromises()
    expect(wrapper.get('[data-test="template-name"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="add-section"]').exists()).toBe(false)
  })
})
