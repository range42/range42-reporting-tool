import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import en from '@/locales/en/common.json'
import MembersPanel from '@/views/settings/MembersPanel.vue'
import { useAuthStore } from '@/stores/auth'
import * as teamsSvc from '@/services/teams'
import * as usersSvc from '@/services/users'
import type { TeamMemberSummary } from '@/services/teams'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

function member(over: Partial<TeamMemberSummary> = {}): TeamMemberSummary {
  return {
    id: 'm1',
    user_id: 'u1',
    display_name: 'Eve',
    email: 'eve@x',
    created_at: 'now',
    ...over,
  }
}

function mountPanel() {
  return mount(MembersPanel, {
    props: { exerciseId: 'ex1', teamId: 't1' },
    global: { plugins: [i18n] },
  })
}

describe('MembersPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'ga', email: 'a', display_name: 'Ada', avatar_url: null, is_global_admin: true },
    })
  })

  it('lists current members on mount', async () => {
    vi.spyOn(teamsSvc, 'listTeamMembers').mockResolvedValue([member()])
    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.text()).toContain('Eve')
    expect(teamsSvc.listTeamMembers).toHaveBeenCalledWith('tok', 'ex1', 't1')
  })

  it('searches users and adds the picked one, then reloads', async () => {
    vi.spyOn(teamsSvc, 'listTeamMembers').mockResolvedValueOnce([])
    vi.spyOn(usersSvc, 'searchUsers').mockResolvedValue([
      { id: 'u2', display_name: 'Ivan', email: 'ivan@x', avatar_url: null, is_global_admin: false },
    ])
    const add = vi.spyOn(teamsSvc, 'addTeamMember').mockResolvedValue(member({ user_id: 'u2' }))
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.get('[data-test="member-search"]').setValue('ivan')
    await flushPromises()
    vi.mocked(teamsSvc.listTeamMembers).mockResolvedValue([
      member({ user_id: 'u2', display_name: 'Ivan' }),
    ])
    await wrapper.get('[data-test="member-candidate-u2"]').trigger('click')
    await flushPromises()

    expect(add).toHaveBeenCalledWith('tok', 'ex1', 't1', 'u2')
    expect(wrapper.text()).toContain('Ivan')
  })

  it('removes a member and reloads', async () => {
    vi.spyOn(teamsSvc, 'listTeamMembers').mockResolvedValue([member()])
    const remove = vi.spyOn(teamsSvc, 'removeTeamMember').mockResolvedValue(undefined)
    const wrapper = mountPanel()
    await flushPromises()

    vi.mocked(teamsSvc.listTeamMembers).mockResolvedValue([])
    await wrapper.get('[data-test="member-remove-m1"]').trigger('click')
    await flushPromises()

    expect(remove).toHaveBeenCalledWith('tok', 'ex1', 't1', 'u1')
    expect(wrapper.find('[data-test="member-row-m1"]').exists()).toBe(false)
  })
})
