import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import en from '@/locales/en/common.json'
import TeamsPanel from '@/views/settings/TeamsPanel.vue'
import { useAuthStore } from '@/stores/auth'
import * as teamsSvc from '@/services/teams'
import * as teamTypesSvc from '@/services/teamTypes'
import type { Team } from '@/services/teams'
import type { TeamTypeConfig } from '@/services/teamTypes'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

function team(over: Partial<Team> = {}): Team {
  return { id: 't1', exercise_id: 'ex1', name: 'Alpha', team_type: 'blue', color: null, ...over }
}

function teamType(over: Partial<TeamTypeConfig> = {}): TeamTypeConfig {
  return {
    id: 'tt1',
    exercise_id: 'ex1',
    type_key: 'blue',
    display_label: 'Blue Team',
    default_color: null,
    is_visible_to_others: true,
    ...over,
  }
}

function mountPanel() {
  return mount(TeamsPanel, { props: { exerciseId: 'ex1' }, global: { plugins: [i18n] } })
}

describe('TeamsPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'ga', email: 'a', display_name: 'Ada', avatar_url: null, is_global_admin: true },
    })
    vi.spyOn(teamTypesSvc, 'listTeamTypes').mockResolvedValue([teamType()])
  })

  it('lists teams on mount', async () => {
    vi.spyOn(teamsSvc, 'listTeams').mockResolvedValue([team()])
    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.text()).toContain('Alpha')
  })

  it('creates a team and reloads', async () => {
    vi.spyOn(teamsSvc, 'listTeams').mockResolvedValueOnce([])
    const create = vi.spyOn(teamsSvc, 'createTeam').mockResolvedValue(team())
    const wrapper = mountPanel()
    await flushPromises()

    vi.mocked(teamsSvc.listTeams).mockResolvedValue([team()])
    await wrapper.get('[data-test="team-name"]').setValue('Alpha')
    await wrapper.get('[data-test="team-type"]').setValue('blue')
    await wrapper.get('[data-test="team-form"]').trigger('submit')
    await flushPromises()

    expect(create).toHaveBeenCalledWith('tok', 'ex1', {
      name: 'Alpha',
      team_type: 'blue',
      color: null,
    })
    expect(wrapper.text()).toContain('Alpha')
  })

  it('deletes a team and reloads', async () => {
    vi.spyOn(teamsSvc, 'listTeams').mockResolvedValue([team()])
    const del = vi.spyOn(teamsSvc, 'deleteTeam').mockResolvedValue(undefined)
    const wrapper = mountPanel()
    await flushPromises()

    vi.mocked(teamsSvc.listTeams).mockResolvedValue([])
    await wrapper.get('[data-test="team-delete-t1"]').trigger('click')
    await flushPromises()

    expect(del).toHaveBeenCalledWith('tok', 'ex1', 't1')
    expect(wrapper.find('[data-test="team-row-t1"]').exists()).toBe(false)
  })

  it('toggles a team open to show its members panel', async () => {
    vi.spyOn(teamsSvc, 'listTeams').mockResolvedValue([team()])
    vi.spyOn(teamsSvc, 'listTeamMembers').mockResolvedValue([])
    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.find('[data-test="member-search"]').exists()).toBe(false)
    await wrapper.get('[data-test="team-expand-t1"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="member-search"]').exists()).toBe(true)
  })
})
