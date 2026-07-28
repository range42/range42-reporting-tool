import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import ReportEditor from '@/views/reports/ReportEditor.vue'
import * as reports from '@/services/reports'
import * as attachments from '@/services/attachments'
import { useAuthStore } from '@/stores/auth'
import { useCapabilitiesStore } from '@/stores/capabilities'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

vi.mock('@/services/reports')
vi.mock('@/services/attachments')
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
vi.mock('@tiptap/extension-image', () => ({ default: { extend: () => ({}) } }))

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

const serverSection = {
  ...richDetail.sections[0],
  content: '<p>server text</p>',
  version: 5,
  updated_at: '2026-06-26T11:00:00Z',
}

const staleError = {
  status: 409,
  details: [{ error: 'stale_version', section: serverSection }],
}

async function mountWithConflict() {
  vi.mocked(reports.getReport).mockResolvedValue(richDetail as never)
  vi.mocked(reports.saveSection).mockRejectedValueOnce(staleError as never)
  const w = mountEditor()
  await flushPromises()
  await w.find('[data-test="content-s1"]').setValue('mine')
  await w.find('[data-test="save-s1"]').trigger('click')
  await flushPromises()
  return w
}

describe('ReportEditor.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
    localStorage.clear()
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'a', email: 'a', display_name: 'a', avatar_url: null, is_global_admin: true },
    })
    vi.mocked(attachments.listAttachments).mockResolvedValue([])
    vi.mocked(attachments.attachmentUrl).mockImplementation(
      (ex, rid, aid) => `/api/v1/exercises/${ex}/reports/${rid}/attachments/${aid}/download`,
    )
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

  it('saveSection sends the current version; a stale 409 opens the merge panel', async () => {
    const w = await mountWithConflict()
    expect(reports.saveSection).toHaveBeenCalledWith(
      'tok',
      'ex1',
      'r1',
      's1',
      expect.objectContaining({ version: 1 }),
    )
    const panel = w.find('[data-test="merge-s1"]')
    expect(panel.exists()).toBe(true)
    expect(panel.text()).toContain('mine')
    expect(panel.text()).toContain('server text')
  })

  it('keep mine re-saves the local content against the server version', async () => {
    const w = await mountWithConflict()
    vi.mocked(reports.saveSection).mockResolvedValueOnce({
      ...serverSection,
      content: 'mine',
      version: 6,
    } as never)
    await w.find('[data-test="merge-keep-mine-s1"]').trigger('click')
    await flushPromises()
    expect(reports.saveSection).toHaveBeenLastCalledWith(
      'tok',
      'ex1',
      'r1',
      's1',
      expect.objectContaining({ version: 5, body: { kind: 'rich_text', content: 'mine' } }),
    )
    expect(w.find('[data-test="merge-s1"]').exists()).toBe(false)
  })

  it('use server replaces the section, clears the panel and the draft cache', async () => {
    const w = await mountWithConflict()
    expect(localStorage.getItem('r42:draft:r1:d1')).not.toBeNull()
    await w.find('[data-test="merge-use-server-s1"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-test="merge-s1"]').exists()).toBe(false)
    expect((w.find('[data-test="content-s1"]').element as HTMLTextAreaElement).value).toBe(
      '<p>server text</p>',
    )
    expect(localStorage.getItem('r42:draft:r1:d1')).toBeNull()
  })

  it('manual merge saves the edited content against the server version', async () => {
    const w = await mountWithConflict()
    await w.find('[data-test="merge-manual-s1"]').trigger('click')
    await w.find('[data-test="merge-editor-s1"]').setValue('mrgd')
    vi.mocked(reports.saveSection).mockResolvedValueOnce({
      ...serverSection,
      content: 'mrgd',
      version: 6,
    } as never)
    await w.find('[data-test="merge-apply-s1"]').trigger('click')
    await flushPromises()
    expect(reports.saveSection).toHaveBeenLastCalledWith(
      'tok',
      'ex1',
      'r1',
      's1',
      expect.objectContaining({ version: 5, body: { kind: 'rich_text', content: 'mrgd' } }),
    )
    expect(w.find('[data-test="merge-s1"]').exists()).toBe(false)
  })

  it('a 409 without a usable section payload falls back to a refetch', async () => {
    vi.mocked(reports.getReport).mockResolvedValue(richDetail as never)
    vi.mocked(reports.saveSection).mockRejectedValue({ status: 409, details: [] } as never)
    const w = mountEditor()
    await flushPromises()
    await w.find('[data-test="content-s1"]').setValue('ok')
    await w.find('[data-test="save-s1"]').trigger('click')
    await flushPromises()
    expect(reports.getReport).toHaveBeenCalledTimes(2)
    expect(w.find('[data-test="merge-s1"]').exists()).toBe(false)
  })

  it('a draft assigned to another user is read-only with the assignment-lock banner', async () => {
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'a', email: 'a', display_name: 'a', avatar_url: null, is_global_admin: false },
    })
    vi.mocked(reports.getReport).mockResolvedValue({
      ...richDetail,
      assigned_writer_id: 'someone-else',
    } as never)
    const w = mountEditor()
    await flushPromises()
    expect(w.find('[data-test="assignment-lock"]').exists()).toBe(true)
    expect(w.find('[data-test="save-s1"]').exists()).toBe(false)
    expect(w.find('[data-test="content-s1"]').attributes('disabled')).toBeDefined()
  })

  it('the assigned writer is not locked out of their own draft', async () => {
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'a', email: 'a', display_name: 'a', avatar_url: null, is_global_admin: false },
    })
    vi.mocked(reports.getReport).mockResolvedValue({
      ...richDetail,
      assigned_writer_id: 'a',
    } as never)
    const w = mountEditor()
    await flushPromises()
    expect(w.find('[data-test="assignment-lock"]').exists()).toBe(false)
    expect(w.find('[data-test="save-s1"]').exists()).toBe(true)
  })

  it('a submitted report shows recall for a recall-capable caller and recalls it', async () => {
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'a', email: 'a', display_name: 'a', avatar_url: null, is_global_admin: false },
    })
    useCapabilitiesStore().set('ex1', ['reports:recall'])
    vi.mocked(reports.getReport).mockResolvedValue({
      ...richDetail,
      status: 'submitted',
    } as never)
    vi.mocked(reports.recallReport).mockResolvedValue({ ...richDetail, status: 'draft' } as never)
    const w = mountEditor()
    await flushPromises()
    const btn = w.find('[data-test="recall-report"]')
    expect(btn.exists()).toBe(true)
    await btn.trigger('click')
    await flushPromises()
    expect(reports.recallReport).toHaveBeenCalledWith('tok', 'ex1', 'r1')
    expect(w.find('[data-test="recall-report"]').exists()).toBe(false)
  })

  it('no recall button without the capability', async () => {
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'a', email: 'a', display_name: 'a', avatar_url: null, is_global_admin: false },
    })
    vi.mocked(reports.getReport).mockResolvedValue({
      ...richDetail,
      status: 'submitted',
    } as never)
    const w = mountEditor()
    await flushPromises()
    expect(w.find('[data-test="recall-report"]').exists()).toBe(false)
  })

  const attachment = {
    id: 'a1',
    report_id: 'r1',
    section_id: 's1',
    filename: 'pic.png',
    content_type: 'image/png',
    size_bytes: 42,
    classification: null,
    uploaded_by: 'a',
    created_at: '2026-06-26T10:00:00Z',
  }

  it('lists section attachments loaded on mount', async () => {
    vi.mocked(reports.getReport).mockResolvedValue(richDetail as never)
    vi.mocked(attachments.listAttachments).mockResolvedValue([attachment])
    const w = mountEditor()
    await flushPromises()
    expect(w.text()).toContain('pic.png')
    expect(w.find('[data-test="attach-remove-a1"]').exists()).toBe(true)
  })

  it('uploads a picked file through the panel and appends it to the list', async () => {
    vi.mocked(reports.getReport).mockResolvedValue(richDetail as never)
    vi.mocked(attachments.uploadAttachment).mockResolvedValue(attachment)
    const w = mountEditor()
    await flushPromises()
    const input = w.find('[data-test="attach-input-s1"]')
    const file = new File([new Uint8Array([1])], 'pic.png', { type: 'image/png' })
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await flushPromises()
    expect(attachments.uploadAttachment).toHaveBeenCalledWith('tok', 'ex1', 'r1', 's1', file)
    expect(w.text()).toContain('pic.png')
  })

  it('shows the API error when an upload is rejected (e.g. spoofed type)', async () => {
    vi.mocked(reports.getReport).mockResolvedValue(richDetail as never)
    vi.mocked(attachments.uploadAttachment).mockRejectedValue(new Error('nope'))
    const w = mountEditor()
    await flushPromises()
    const input = w.find('[data-test="attach-input-s1"]')
    Object.defineProperty(input.element, 'files', {
      value: [new File([new Uint8Array([1])], 'x.zip')],
    })
    await input.trigger('change')
    await flushPromises()
    expect(w.find('[data-test="attach-error-s1"]').exists()).toBe(true)
  })

  it('removes an attachment via the panel', async () => {
    vi.mocked(reports.getReport).mockResolvedValue(richDetail as never)
    vi.mocked(attachments.listAttachments).mockResolvedValue([attachment])
    vi.mocked(attachments.deleteAttachment).mockResolvedValue()
    const w = mountEditor()
    await flushPromises()
    await w.find('[data-test="attach-remove-a1"]').trigger('click')
    await flushPromises()
    expect(attachments.deleteAttachment).toHaveBeenCalledWith('tok', 'ex1', 'r1', 'a1')
    expect(w.find('[data-test="attach-remove-a1"]').exists()).toBe(false)
  })

  it('no upload affordance on a read-only report', async () => {
    vi.mocked(reports.getReport).mockResolvedValue({ ...richDetail, status: 'submitted' } as never)
    const w = mountEditor()
    await flushPromises()
    expect(w.find('[data-test="attach-btn-s1"]').exists()).toBe(false)
    expect(w.find('[data-test="img-btn-s1"]').exists()).toBe(false)
  })
})
