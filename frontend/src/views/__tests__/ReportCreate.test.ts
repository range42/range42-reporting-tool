import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import ReportCreate from '@/views/reports/ReportCreate.vue'
import * as reportsSvc from '@/services/reports'
import * as templatesSvc from '@/services/templates'
import * as teamsSvc from '@/services/teams'
import { useAuthStore } from '@/stores/auth'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const push = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { exerciseId: 'ex1' } }),
  useRouter: () => ({ push }),
  RouterLink: { template: '<a><slot /></a>' },
}))

function mountCreate() {
  return mount(ReportCreate, { global: { plugins: [i18n] } })
}

describe('ReportCreate.vue', () => {
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

  it('only offers published templates and creates a report', async () => {
    const listSpy = vi
      .spyOn(templatesSvc, 'listTemplates')
      .mockResolvedValue([
        { id: 't1', name: 'Spot', status: 'published', report_type: 'spot', version: 1 },
      ] as never)
    vi.spyOn(teamsSvc, 'listTeams').mockResolvedValue([
      { id: 'tm1', exercise_id: 'ex1', name: 'Blue', team_type: 'blue', color: null },
    ] as never)
    const createSpy = vi.spyOn(reportsSvc, 'createReport').mockResolvedValue({ id: 'r9' } as never)

    const w = mountCreate()
    await flushPromises()
    expect(listSpy).toHaveBeenCalledWith('tok', 'published') // token first, status positional

    await w.find('[data-test="report-name"]').setValue('New R')
    await w.find('[data-test="report-template"]').setValue('t1')
    await w.find('[data-test="report-team"]').setValue('tm1')
    await w.find('[data-test="report-create-submit"]').trigger('submit')
    await flushPromises()

    expect(createSpy).toHaveBeenCalledWith(
      'tok',
      'ex1',
      expect.objectContaining({ template_id: 't1', team_id: 'tm1', name: 'New R' }),
    )
    expect(push).toHaveBeenCalledWith('/exercises/ex1/reports/r9')
  })

  it('choosing a team fetches its members into the writer selector', async () => {
    vi.spyOn(templatesSvc, 'listTemplates').mockResolvedValue([
      { id: 't1', name: 'Spot', status: 'published', report_type: 'spot', version: 1 },
    ] as never)
    vi.spyOn(teamsSvc, 'listTeams').mockResolvedValue([
      { id: 'tm1', exercise_id: 'ex1', name: 'Blue', team_type: 'blue', color: null },
    ] as never)
    const membersSpy = vi.spyOn(teamsSvc, 'listTeamMembers').mockResolvedValue([
      {
        id: 'm1',
        user_id: 'u1',
        display_name: 'Wri Ter',
        email: 'w@x',
        created_at: '2026-06-26T10:00:00Z',
      },
    ])
    vi.spyOn(reportsSvc, 'createReport').mockResolvedValue({ id: 'r9' } as never)

    const w = mountCreate()
    await flushPromises()
    await w.find('[data-test="report-team"]').setValue('tm1')
    await flushPromises()
    expect(membersSpy).toHaveBeenCalledWith('tok', 'ex1', 'tm1')
    const writerSelect = w.find('[data-test="report-writer"]')
    expect(writerSelect.exists()).toBe(true)
    expect(writerSelect.text()).toContain('Wri Ter')
  })

  it('submits the selected writer, or null when left on anyone', async () => {
    vi.spyOn(templatesSvc, 'listTemplates').mockResolvedValue([
      { id: 't1', name: 'Spot', status: 'published', report_type: 'spot', version: 1 },
    ] as never)
    vi.spyOn(teamsSvc, 'listTeams').mockResolvedValue([
      { id: 'tm1', exercise_id: 'ex1', name: 'Blue', team_type: 'blue', color: null },
    ] as never)
    vi.spyOn(teamsSvc, 'listTeamMembers').mockResolvedValue([
      {
        id: 'm1',
        user_id: 'u1',
        display_name: 'Wri Ter',
        email: 'w@x',
        created_at: '2026-06-26T10:00:00Z',
      },
    ])
    const createSpy = vi.spyOn(reportsSvc, 'createReport').mockResolvedValue({ id: 'r9' } as never)

    const w = mountCreate()
    await flushPromises()
    await w.find('[data-test="report-name"]').setValue('New R')
    await w.find('[data-test="report-template"]').setValue('t1')
    await w.find('[data-test="report-team"]').setValue('tm1')
    await flushPromises()
    await w.find('[data-test="report-writer"]').setValue('u1')
    await w.find('[data-test="report-create-submit"]').trigger('submit')
    await flushPromises()
    expect(createSpy).toHaveBeenCalledWith(
      'tok',
      'ex1',
      expect.objectContaining({ assigned_writer_id: 'u1' }),
    )

    // Leaving the selector on the default sends null.
    createSpy.mockClear()
    await w.find('[data-test="report-writer"]').setValue('')
    await w.find('[data-test="report-create-submit"]').trigger('submit')
    await flushPromises()
    expect(createSpy).toHaveBeenCalledWith(
      'tok',
      'ex1',
      expect.objectContaining({ assigned_writer_id: null }),
    )
  })
})
