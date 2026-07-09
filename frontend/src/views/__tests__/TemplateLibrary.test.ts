import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import TemplateLibrary from '@/views/settings/TemplateLibrary.vue'
import { useAuthStore } from '@/stores/auth'
import * as svc from '@/services/templates'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const push = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
  RouterLink: { template: '<a><slot /></a>' },
}))

function mountLib() {
  return mount(TemplateLibrary, { global: { plugins: [i18n] } })
}

describe('TemplateLibrary.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    push.mockClear()
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'a', email: 'a', display_name: 'a', avatar_url: null, is_global_admin: true },
    })
  })

  it('lists templates with status', async () => {
    vi.spyOn(svc, 'listTemplates').mockResolvedValue([
      {
        id: 't1',
        lineage_id: 'l1',
        version: 2,
        name: 'Spot',
        report_type: 'spot',
        description: null,
        status: 'published',
        section_count: 3,
      },
    ])
    const wrapper = mountLib()
    await flushPromises()
    expect(wrapper.findAll('[data-test="template-row"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('Spot')
  })

  it('shows empty state', async () => {
    vi.spyOn(svc, 'listTemplates').mockResolvedValue([])
    const wrapper = mountLib()
    await flushPromises()
    expect(wrapper.find('[data-test="empty"]').exists()).toBe(true)
  })

  it('creates a template and routes to the builder', async () => {
    vi.spyOn(svc, 'listTemplates').mockResolvedValue([])
    vi.spyOn(svc, 'createTemplate').mockResolvedValue({
      id: 'new',
      lineage_id: 'l',
      version: 1,
      name: 'Untitled',
      report_type: 'custom',
      description: null,
      status: 'draft',
      section_count: 0,
    })
    const wrapper = mountLib()
    await flushPromises()
    await wrapper.get('[data-test="new"]').trigger('click')
    await flushPromises()
    expect(svc.createTemplate).toHaveBeenCalled()
    expect(push).toHaveBeenCalledWith('/settings/templates/new')
  })

  it('imports a valid JSON bundle and routes to the builder', async () => {
    vi.spyOn(svc, 'listTemplates').mockResolvedValue([])
    vi.spyOn(svc, 'importTemplate').mockResolvedValue({
      id: 'imported',
      lineage_id: 'l2',
      version: 1,
      name: 'Imported',
      report_type: 'custom',
      description: null,
      status: 'draft',
      metadata: null,
      sections: [],
    })
    const wrapper = mountLib()
    await flushPromises()

    const bundle = { name: 'Imported', sections: [] }
    const mockFile = { text: vi.fn().mockResolvedValue(JSON.stringify(bundle)) }
    const fileInput = wrapper.find('input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', {
      value: { 0: mockFile, length: 1 },
      configurable: true,
    })

    await fileInput.trigger('change')
    await flushPromises()

    expect(svc.importTemplate).toHaveBeenCalledWith('tok', bundle)
    expect(push).toHaveBeenCalledWith('/settings/templates/imported')
    expect(wrapper.find('.alert-error').exists()).toBe(false)
  })

  it('shows alert-error when import JSON is malformed', async () => {
    vi.spyOn(svc, 'listTemplates').mockResolvedValue([])
    const wrapper = mountLib()
    await flushPromises()

    const mockFile = { text: vi.fn().mockResolvedValue('not-json{{{') }
    const fileInput = wrapper.find('input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', {
      value: { 0: mockFile, length: 1 },
      configurable: true,
    })

    await fileInput.trigger('change')
    await flushPromises()

    expect(wrapper.find('.alert-error').exists()).toBe(true)
    expect(push).not.toHaveBeenCalled()
  })
})
