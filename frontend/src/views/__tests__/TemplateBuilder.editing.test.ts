import { describe, it, expect, vi, beforeEach, type MockInstance } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import TemplateBuilder from '@/views/settings/TemplateBuilder.vue'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/services/http'
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

function section(overrides: Partial<svc.Section> = {}): svc.Section {
  return {
    id: 's1',
    template_id: 't1',
    position: 0,
    name: 'Findings',
    description: null,
    field_type: 'rich_text',
    char_limit: 500,
    is_required: true,
    grade_mode: 'not_graded',
    grade_min: null,
    grade_max: null,
    grade_weight: 3,
    rubric_criteria: null,
    evaluation_criteria: null,
    choice_config: null,
    mitre_attack_tags: [],
    capec_tags: [],
    cwe_tags: [],
    ...overrides,
  }
}

const CHOICE = section({
  field_type: 'choice',
  char_limit: null,
  choice_config: {
    selection: 'single',
    values: [{ code: 'a', label: 'Alpha', position: 0, deprecated_at: null }],
  },
})

const RUBRIC = section({
  grade_mode: 'rubric',
  rubric_criteria: [{ name: 'Depth', weight: 2, max_score: 7 }],
})

/** Server copy of each section, so a mocked update returns the merged section. */
let stored = new Map<string, svc.Section>()

async function mountWith(tpl: svc.TemplateDetail): Promise<VueWrapper> {
  stored = new Map(tpl.sections.map((s) => [s.id, s]))
  vi.spyOn(svc, 'getTemplate').mockResolvedValue(tpl)
  const wrapper = mount(TemplateBuilder, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

async function change(wrapper: VueWrapper, selector: string, value: string): Promise<void> {
  await wrapper.get(selector).setValue(value)
  await flushPromises()
}

function buttonByText(wrapper: VueWrapper, text: string) {
  const button = wrapper.findAll('button').find((b) => b.text() === text)
  if (!button) throw new Error(`no button "${text}"`)
  return button
}

describe('TemplateBuilder.vue editing', () => {
  let update: MockInstance<typeof svc.updateSection>
  const patchAt = (n: number): Partial<svc.SectionInput> => update.mock.calls[n]![3]

  beforeEach(() => {
    vi.restoreAllMocks()
    setActivePinia(createPinia())
    mockPush.mockClear()
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'a', email: 'a', display_name: 'a', avatar_url: null, is_global_admin: true },
    })
    vi.spyOn(svc, 'listVersions').mockResolvedValue([
      { id: 't1', version: 1, status: 'published', created_at: '' },
    ])
    update = vi.spyOn(svc, 'updateSection').mockImplementation(async (_t, _tid, sid, partial) => {
      const merged = { ...(stored.get(sid) ?? section({ id: sid })), ...partial }
      stored.set(sid, merged)
      return merged
    })
    vi.stubGlobal('confirm', () => true)
  })

  describe('template metadata', () => {
    it('saves the edited name, type and description', async () => {
      const save = vi.spyOn(svc, 'updateTemplate').mockResolvedValue({ ...DRAFT, section_count: 0 })
      const wrapper = await mountWith(DRAFT)
      await wrapper.get('[data-test="template-name"]').setValue('Renamed')
      await wrapper.get('select').setValue('custom')
      await wrapper.get('textarea').setValue('About it')
      await wrapper.get('[data-test="save-template"]').trigger('click')
      await flushPromises()
      expect(save).toHaveBeenCalledWith('tok', 't1', {
        name: 'Renamed',
        report_type: 'custom',
        description: 'About it',
      })
    })

    it.each([
      [new ApiError('conflict', 'Name taken'), 'Name taken'],
      [new Error('boom'), 'Save failed'],
    ])('shows the save error (%s)', async (err, shown) => {
      vi.spyOn(svc, 'updateTemplate').mockRejectedValue(err)
      const wrapper = await mountWith(DRAFT)
      await wrapper.get('[data-test="save-template"]').trigger('click')
      await flushPromises()
      expect(wrapper.get('.alert-error').text()).toContain(shown)
    })

    it('shows a load error when the template cannot be fetched', async () => {
      vi.spyOn(svc, 'getTemplate').mockRejectedValue(new Error('down'))
      const wrapper = mount(TemplateBuilder, { global: { plugins: [i18n] } })
      await flushPromises()
      expect(wrapper.get('.alert-error').text()).toContain('Failed to load template')
    })

    it('shows the server message when publishing fails', async () => {
      vi.spyOn(svc, 'publishTemplate').mockRejectedValue(new ApiError('invalid', 'No sections'))
      const wrapper = await mountWith(DRAFT)
      await wrapper.get('[data-test="publish"]').trigger('click')
      await flushPromises()
      expect(wrapper.get('.alert-error').text()).toContain('No sections')
    })
  })

  describe('section fields', () => {
    it('saves a renamed section', async () => {
      const wrapper = await mountWith({ ...DRAFT, sections: [section()] })
      await change(wrapper, '[data-test="section-name-s1"]', 'Summary')
      expect(update).toHaveBeenCalledWith('tok', 't1', 's1', { name: 'Summary' })
    })

    it('starts an empty choice list when switching a section to choice', async () => {
      const wrapper = await mountWith({ ...DRAFT, sections: [section()] })
      await change(wrapper, '[data-test="section-field-type-s1"]', 'choice')
      expect(update).toHaveBeenCalledWith('tok', 't1', 's1', {
        field_type: 'choice',
        choice_config: { selection: 'single', values: [] },
      })
    })

    it('sets and clears the character limit', async () => {
      const wrapper = await mountWith({ ...DRAFT, sections: [section()] })
      const limit = wrapper
        .findAll('input[type="number"]')
        .find((i) => (i.element as HTMLInputElement).value === '500')!
      await limit.setValue('800')
      await limit.setValue('')
      await flushPromises()
      expect(update).toHaveBeenCalledWith('tok', 't1', 's1', { char_limit: 800 })
      expect(update).toHaveBeenCalledWith('tok', 't1', 's1', { char_limit: null })
    })

    it('saves the required flag, grade mode and weight', async () => {
      const wrapper = await mountWith({ ...DRAFT, sections: [section()] })
      await wrapper.get('#req-s1').setValue(false)
      const gradeMode = wrapper
        .findAll('select')
        .find((s) => s.find('option[value="rubric"]').exists())!
      await gradeMode.setValue('numeric')
      const weight = wrapper
        .findAll('input[type="number"]')
        .find((i) => (i.element as HTMLInputElement).value === '3')!
      await weight.setValue('5')
      await flushPromises()
      expect(update).toHaveBeenCalledWith('tok', 't1', 's1', { is_required: false })
      expect(update).toHaveBeenCalledWith('tok', 't1', 's1', { grade_mode: 'numeric' })
      expect(update).toHaveBeenCalledWith('tok', 't1', 's1', { grade_weight: 5 })
    })

    it('splits tag lists on commas and drops blanks', async () => {
      const wrapper = await mountWith({ ...DRAFT, sections: [section()] })
      await change(wrapper, 'input[placeholder="e.g. T1059, T1078"]', 'T1059, T1078 ,')
      await change(wrapper, 'input[placeholder="e.g. CWE-79, CWE-89"]', 'CWE-79')
      expect(update).toHaveBeenCalledWith('tok', 't1', 's1', {
        mitre_attack_tags: ['T1059', 'T1078'],
      })
      expect(update).toHaveBeenCalledWith('tok', 't1', 's1', { cwe_tags: ['CWE-79'] })
    })

    it('shows an error when a section update fails', async () => {
      update.mockRejectedValue(new Error('down'))
      const wrapper = await mountWith({ ...DRAFT, sections: [section()] })
      await change(wrapper, '[data-test="section-name-s1"]', 'Summary')
      expect(wrapper.get('.alert-error').text()).toContain('Failed to update section')
    })
  })

  describe('section list', () => {
    const A = section({ id: 'a', name: 'A' })
    const B = section({ id: 'b', name: 'B', position: 1 })

    it('moves a section down', async () => {
      const reorder = vi.spyOn(svc, 'reorderSections').mockResolvedValue([B, A])
      const wrapper = await mountWith({ ...DRAFT, sections: [A, B] })
      await wrapper.get('[data-test="move-down-a"]').trigger('click')
      await flushPromises()
      expect(reorder).toHaveBeenCalledWith('tok', 't1', ['b', 'a'])
    })

    it('shows an error when reordering fails', async () => {
      vi.spyOn(svc, 'reorderSections').mockRejectedValue(new ApiError('conflict', 'Stale order'))
      const wrapper = await mountWith({ ...DRAFT, sections: [A, B] })
      await wrapper.get('[data-test="move-down-a"]').trigger('click')
      await flushPromises()
      expect(wrapper.get('.alert-error').text()).toContain('Stale order')
    })

    it('deletes a section after confirmation', async () => {
      const del = vi.spyOn(svc, 'deleteSection').mockResolvedValue(undefined)
      const wrapper = await mountWith({ ...DRAFT, sections: [A, B] })
      await wrapper.get('[data-test="delete-section-a"]').trigger('click')
      await flushPromises()
      expect(del).toHaveBeenCalledWith('tok', 't1', 'a')
      expect(wrapper.find('[data-test="section-row-a"]').exists()).toBe(false)
    })

    it('keeps the section when the deletion is not confirmed', async () => {
      vi.stubGlobal('confirm', () => false)
      const del = vi.spyOn(svc, 'deleteSection')
      const wrapper = await mountWith({ ...DRAFT, sections: [A] })
      await wrapper.get('[data-test="delete-section-a"]').trigger('click')
      await flushPromises()
      expect(del).not.toHaveBeenCalled()
    })

    it('shows an error when adding a section fails', async () => {
      vi.spyOn(svc, 'addSection').mockRejectedValue(new Error('down'))
      const wrapper = await mountWith(DRAFT)
      await wrapper.get('[data-test="add-section"]').trigger('click')
      await flushPromises()
      expect(wrapper.get('.alert-error').text()).toContain('Failed to add section')
    })
  })

  describe('choice values', () => {
    it('adds an empty value at the end', async () => {
      const wrapper = await mountWith({ ...DRAFT, sections: [CHOICE] })
      await buttonByText(wrapper, 'Add value').trigger('click')
      await flushPromises()
      const values = patchAt(0).choice_config!.values
      expect(values).toHaveLength(2)
      expect(values[1]).toEqual({ code: '', label: '', position: 1, deprecated_at: null })
    })

    it('edits the code and label of a value', async () => {
      const wrapper = await mountWith({ ...DRAFT, sections: [CHOICE] })
      await change(wrapper, 'input[placeholder="code"]', 'b')
      await change(wrapper, 'input[placeholder="label"]', 'Bravo')
      expect(patchAt(0).choice_config!.values[0]!.code).toBe('b')
      expect(patchAt(1).choice_config!.values[0]!.label).toBe('Bravo')
    })

    it('deprecates a value and removes another', async () => {
      const wrapper = await mountWith({ ...DRAFT, sections: [CHOICE] })
      await wrapper.get('button[title="Deprecate"]').trigger('click')
      await flushPromises()
      expect(patchAt(0).choice_config!.values[0]!.deprecated_at).toEqual(expect.any(String))
      const row = wrapper.get('button[title="Deprecate"]').element.parentElement!
      ;(row.querySelectorAll('button')[1] as HTMLButtonElement).click()
      await flushPromises()
      expect(patchAt(1).choice_config!.values).toEqual([])
    })

    it('switches between single and multiple selection', async () => {
      const wrapper = await mountWith({ ...DRAFT, sections: [CHOICE] })
      const selection = wrapper
        .findAll('select')
        .find((s) => s.find('option[value="multiple"]').exists())!
      await selection.setValue('multiple')
      await flushPromises()
      expect(patchAt(0).choice_config!.selection).toBe('multiple')
    })

    it('previews a multiple-choice section as checkboxes', async () => {
      const multi = section({
        ...CHOICE,
        choice_config: { ...CHOICE.choice_config!, selection: 'multiple' },
      })
      const wrapper = await mountWith({ ...DRAFT, sections: [multi] })
      expect(wrapper.find('aside input[type="checkbox"]').exists()).toBe(true)
      expect(wrapper.get('aside').text()).toContain('Alpha')
    })
  })

  describe('rubric criteria', () => {
    it('adds a criterion with default weight and score', async () => {
      const wrapper = await mountWith({ ...DRAFT, sections: [RUBRIC] })
      await buttonByText(wrapper, 'Add criterion').trigger('click')
      await flushPromises()
      expect(patchAt(0).rubric_criteria).toEqual([
        { name: 'Depth', weight: 2, max_score: 7 },
        { name: '', weight: 1, max_score: 10 },
      ])
    })

    it('edits the name, weight and max score of a criterion', async () => {
      const wrapper = await mountWith({ ...DRAFT, sections: [RUBRIC] })
      const byValue = (v: string) =>
        wrapper.findAll('input').find((i) => (i.element as HTMLInputElement).value === v)!
      await byValue('Depth').setValue('Breadth')
      await byValue('2').setValue('4')
      await byValue('7').setValue('9')
      await flushPromises()
      const crits = update.mock.calls.map((c) => c[3].rubric_criteria![0])
      expect(crits).toEqual([
        { name: 'Breadth', weight: 2, max_score: 7 },
        { name: 'Breadth', weight: 4, max_score: 7 },
        { name: 'Breadth', weight: 4, max_score: 9 },
      ])
    })

    it('removes a criterion', async () => {
      const wrapper = await mountWith({ ...DRAFT, sections: [RUBRIC] })
      const row = wrapper
        .findAll('input')
        .find((i) => (i.element as HTMLInputElement).value === 'Depth')!.element.parentElement!
      ;(row.querySelector('button') as HTMLButtonElement).click()
      await flushPromises()
      expect(patchAt(0).rubric_criteria).toEqual([])
    })
  })

  describe('published template actions', () => {
    const PUBLISHED = { ...DRAFT, status: 'published' as const }

    it('clones the template and opens the copy', async () => {
      vi.spyOn(svc, 'cloneTemplate').mockResolvedValue({ ...DRAFT, id: 't2' })
      const wrapper = await mountWith(PUBLISHED)
      await buttonByText(wrapper, 'Clone to edit').trigger('click')
      await flushPromises()
      expect(mockPush).toHaveBeenCalledWith('/settings/templates/t2')
    })

    it('archives the template and reloads it', async () => {
      const archive = vi
        .spyOn(svc, 'archiveTemplate')
        .mockResolvedValue({ ...PUBLISHED, section_count: 0 })
      const wrapper = await mountWith(PUBLISHED)
      await buttonByText(wrapper, 'Archive').trigger('click')
      await flushPromises()
      expect(archive).toHaveBeenCalledWith('tok', 't1')
      expect(svc.getTemplate).toHaveBeenCalledTimes(2)
    })

    it.each([
      ['Clone to edit', 'cloneTemplate', 'Clone failed'],
      ['Archive', 'archiveTemplate', 'Archive failed'],
      ['Export JSON', 'exportTemplate', 'Export failed'],
    ] as const)('shows an error when %s fails', async (label, fn, shown) => {
      vi.spyOn(svc, fn).mockRejectedValue(new Error('down'))
      const wrapper = await mountWith(PUBLISHED)
      await buttonByText(wrapper, label).trigger('click')
      await flushPromises()
      expect(wrapper.get('.alert-error').text()).toContain(shown)
    })
  })

  it('summarises the section composition', async () => {
    const wrapper = await mountWith({ ...DRAFT, sections: [section(), CHOICE] })
    const summary = wrapper.get('aside').text()
    expect(summary).toMatch(/Rich text sections\s*1/)
    expect(summary).toMatch(/Choice sections\s*1/)
    expect(summary).toMatch(/Total char budget\s*500/)
    expect(summary).toMatch(/Choice values defined\s*1/)
  })
})
