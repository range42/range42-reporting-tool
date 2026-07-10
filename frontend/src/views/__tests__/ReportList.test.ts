import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import ReportList from '@/views/reports/ReportList.vue'
import { useAuthStore } from '@/stores/auth'
import * as svc from '@/services/reports'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const push = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { exerciseId: 'ex1' } }),
  useRouter: () => ({ push }),
  RouterLink: { template: '<a><slot /></a>' },
}))

function mountList() {
  return mount(ReportList, { global: { plugins: [i18n] } })
}

function setAdmin(isAdmin: boolean) {
  useAuthStore().setSession({
    access_token: 'tok',
    token_type: 'bearer',
    user: { id: 'a', email: 'a', display_name: 'a', avatar_url: null, is_global_admin: isAdmin },
  })
}

describe('ReportList.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    push.mockClear()
    setAdmin(true)
  })

  it('renders report rows from the service', async () => {
    vi.spyOn(svc, 'listReports').mockResolvedValue([
      {
        id: 'r1',
        exercise_id: 'ex1',
        team_id: 't1',
        template_id: 'tpl1',
        template_version_at_creation: 1,
        name: 'My Report',
        description: null,
        status: 'draft',
        approval_required: false,
        due_at: null,
        submitted_at: null,
        assigned_writer_id: null,
        section_count: 2,
      },
    ])
    const w = mountList()
    await flushPromises()
    expect(w.text()).toContain('My Report')
    expect(w.find('[data-test="report-row"]').exists()).toBe(true)
  })

  it('shows an empty state when there are no reports', async () => {
    vi.spyOn(svc, 'listReports').mockResolvedValue([])
    const w = mountList()
    await flushPromises()
    expect(w.find('[data-test="reports-empty"]').exists()).toBe(true)
  })

  it('hides the New report button for non-admins', async () => {
    setAdmin(false)
    vi.spyOn(svc, 'listReports').mockResolvedValue([])
    const w = mountList()
    await flushPromises()
    expect(w.find('[data-test="new-report"]').exists()).toBe(false)
  })
})
