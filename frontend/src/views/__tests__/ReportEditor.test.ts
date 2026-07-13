import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import ReportEditor from '@/views/reports/ReportEditor.vue'
import * as reports from '@/services/reports'
import { useAuthStore } from '@/stores/auth'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

vi.mock('@/services/reports')
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { exerciseId: 'ex1', rid: 'r1' } }),
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { template: '<a><slot /></a>' },
}))
// ProseMirror can't run under jsdom — stub TipTap; the RichTextField textarea
// mirror is the surface these tests drive.
vi.mock('@tiptap/vue-3', () => ({
  useEditor: () => ({ value: undefined }),
  EditorContent: { name: 'EditorContent', template: '<div />' },
}))
vi.mock('@tiptap/starter-kit', () => ({ default: {} }))

const richDetail = {
  id: 'r1',
  status: 'draft',
  name: 'R',
  updated_at: '2026-06-26T10:00:00Z',
  sections: [
    {
      id: 's1',
      section_def_id: 'd1',
      field_type: 'rich_text',
      name: 'Summary',
      description: '',
      char_limit: 5,
      is_required: true,
      content: '',
      content_plain: '',
      char_count: 0,
      choice_values: null,
      choice_config: null,
      version: 1,
      position: 0,
      updated_at: '2026-06-26T10:00:00Z',
    },
  ],
}

function mountEditor() {
  return mount(ReportEditor, { global: { plugins: [i18n] } })
}

describe('ReportEditor.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'a', email: 'a', display_name: 'a', avatar_url: null, is_global_admin: true },
    })
  })

  it('renders a char counter for rich_text and blocks over the limit', async () => {
    vi.mocked(reports.getReport).mockResolvedValue(richDetail as never)
    const w = mountEditor()
    await flushPromises()
    expect(w.find('[data-test="char-counter-s1"]').exists()).toBe(true)
    await w.find('[data-test="content-s1"]').setValue('toolong')
    await flushPromises()
    expect(w.find('[data-test="save-s1"]').attributes('disabled')).toBeDefined()
  })

  it('saveSection sends the current version; a 409 shows the conflict banner', async () => {
    vi.mocked(reports.getReport).mockResolvedValue(richDetail as never)
    vi.mocked(reports.saveSection).mockRejectedValue({ status: 409 } as never)
    const w = mountEditor()
    await flushPromises()
    await w.find('[data-test="content-s1"]').setValue('ok')
    await w.find('[data-test="save-s1"]').trigger('click')
    await flushPromises()
    expect(reports.saveSection).toHaveBeenCalledWith(
      'tok',
      'ex1',
      'r1',
      's1',
      expect.objectContaining({ version: 1 }),
    )
    expect(w.find('[data-test="conflict-s1"]').exists()).toBe(true)
  })
})
