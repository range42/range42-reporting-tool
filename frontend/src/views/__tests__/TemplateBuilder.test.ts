import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import TemplateBuilder from '@/views/settings/TemplateBuilder.vue'
import { useAuthStore } from '@/stores/auth'
import * as svc from '@/services/templates'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

const { mockPush } = vi.hoisted(() => ({ mockPush: vi.fn() }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
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
    mockPush.mockClear()
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'a', email: 'a', display_name: 'a', avatar_url: null, is_global_admin: true },
    })
    vi.spyOn(svc, 'listVersions').mockResolvedValue([
      { id: 't1', version: 1, status: 'draft', created_at: '' },
    ])
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: vi.fn(() => 'blob:x'),
      revokeObjectURL: vi.fn(),
    })
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

  it('imports choice values from a CSV and replaces the section', async () => {
    const choiceSection: svc.Section = {
      id: 's1',
      template_id: 't1',
      position: 0,
      name: 'Services',
      description: null,
      field_type: 'choice',
      char_limit: null,
      is_required: true,
      grade_mode: 'not_graded',
      grade_min: null,
      grade_max: null,
      grade_weight: 1,
      rubric_criteria: null,
      evaluation_criteria: null,
      choice_config: {
        selection: 'single',
        values: [{ code: 'a', label: 'A', position: 0, deprecated_at: null }],
      },
      mitre_attack_tags: [],
      capec_tags: [],
      cwe_tags: [],
    }
    vi.spyOn(svc, 'getTemplate').mockResolvedValue({ ...DRAFT, sections: [choiceSection] })
    const imported = vi.spyOn(svc, 'importChoiceValues').mockResolvedValue({
      ...choiceSection,
      choice_config: {
        selection: 'single',
        values: [
          { code: 'a', label: 'A', position: 0, deprecated_at: null },
          { code: 'b', label: 'Bravo', position: 1, deprecated_at: null },
        ],
      },
    })
    const wrapper = mountBuilder()
    await flushPromises()
    await wrapper.get('[data-test="csv-import-btn-s1"]').trigger('click')
    const input = wrapper.get('[data-test="csv-import-input"]')
    const file = new File([new TextEncoder().encode('code,label\nb,Bravo\n')], 'v.csv')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await flushPromises()
    expect(imported).toHaveBeenCalledWith('tok', 't1', 's1', file)
    const codes = wrapper
      .findAll('input')
      .map((i) => (i.element as HTMLInputElement).value)
      .filter((v) => v === 'b' || v === 'Bravo')
    expect(codes).toContain('b')
  })

  it('disables editing for a published template', async () => {
    vi.spyOn(svc, 'getTemplate').mockResolvedValue({ ...DRAFT, status: 'published' })
    const wrapper = mountBuilder()
    await flushPromises()
    expect(wrapper.get('[data-test="template-name"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="add-section"]').exists()).toBe(false)
  })

  it('reorders sections via the service', async () => {
    const A = {
      id: 'a',
      template_id: 't1',
      position: 0,
      name: 'A',
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
    } as svc.Section
    const B = { ...A, id: 'b', name: 'B', position: 1 } as svc.Section
    vi.spyOn(svc, 'getTemplate').mockResolvedValue({ ...DRAFT, sections: [A, B] })
    const reorder = vi.spyOn(svc, 'reorderSections').mockResolvedValue([B, A])
    const wrapper = mountBuilder()
    await flushPromises()
    await wrapper.get('[data-test="move-up-b"]').trigger('click') // up/down buttons also drive reorder
    await flushPromises()
    expect(reorder).toHaveBeenCalledWith('tok', 't1', ['b', 'a'])
  })

  it('re-fetches version history after publish', async () => {
    vi.spyOn(svc, 'getTemplate').mockResolvedValue(DRAFT)
    vi.spyOn(svc, 'publishTemplate').mockResolvedValue({ ...DRAFT, section_count: 0 })
    // Re-spy and clear accumulated calls from prior tests
    const listSpy = vi
      .spyOn(svc, 'listVersions')
      .mockResolvedValue([{ id: 't1', version: 1, status: 'draft', created_at: '' }])
    listSpy.mockClear()
    const wrapper = mountBuilder()
    await flushPromises()
    expect(listSpy).toHaveBeenCalledTimes(1) // once on mount
    await wrapper.get('[data-test="publish"]').trigger('click')
    await flushPromises()
    expect(listSpy).toHaveBeenCalledTimes(2) // once more after publish
  })

  it('exports the template as a JSON download', async () => {
    vi.spyOn(svc, 'getTemplate').mockResolvedValue({ ...DRAFT, status: 'published' })
    vi.spyOn(svc, 'exportTemplate').mockResolvedValue({
      schema_version: 1,
      name: 'Spot',
      report_type: 'spot',
      description: null,
      sections: [],
    })
    const wrapper = mountBuilder()
    await flushPromises()
    await wrapper.get('[data-test="export"]').trigger('click')
    await flushPromises()
    expect(svc.exportTemplate).toHaveBeenCalledWith('tok', 't1')
  })

  it('deletes a draft template and navigates to the template list', async () => {
    vi.spyOn(svc, 'getTemplate').mockResolvedValue(DRAFT)
    vi.stubGlobal('confirm', () => true)
    const del = vi.spyOn(svc, 'deleteTemplate').mockResolvedValue(undefined)
    const wrapper = mountBuilder()
    await flushPromises()
    await wrapper.get('[data-test="delete-template"]').trigger('click')
    await flushPromises()
    expect(del).toHaveBeenCalledWith('tok', 't1')
    expect(mockPush).toHaveBeenCalledWith('/settings/templates')
    expect(wrapper.find('.alert-error').exists()).toBe(false)
  })

  it('does not show the delete button for a published template', async () => {
    vi.spyOn(svc, 'getTemplate').mockResolvedValue({ ...DRAFT, status: 'published' })
    const wrapper = mountBuilder()
    await flushPromises()
    expect(wrapper.find('[data-test="delete-template"]').exists()).toBe(false)
  })
})
