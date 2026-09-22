import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import TeamTypesPanel from '@/views/settings/TeamTypesPanel.vue'
import { useAuthStore } from '@/stores/auth'
import { createPinia, setActivePinia } from 'pinia'
import * as svc from '@/services/teamTypes'
import { ApiError } from '@/services/http'
import type { TeamTypeConfig } from '@/services/teamTypes'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

function teamType(over: Partial<TeamTypeConfig> = {}): TeamTypeConfig {
  return {
    id: 'tt1',
    exercise_id: 'ex1',
    type_key: 'blue',
    display_label: 'Blue Team',
    default_color: '#3B82F6',
    is_visible_to_others: true,
    ...over,
  }
}

function mountPanel() {
  return mount(TeamTypesPanel, { props: { exerciseId: 'ex1' }, global: { plugins: [i18n] } })
}

describe('TeamTypesPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'ga', email: 'a', display_name: 'Ada', avatar_url: null, is_global_admin: true },
    })
  })

  it('lists team types on mount', async () => {
    vi.spyOn(svc, 'listTeamTypes').mockResolvedValue([teamType()])
    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.text()).toContain('Blue Team')
    expect(svc.listTeamTypes).toHaveBeenCalledWith('tok', 'ex1')
  })

  it('creates a team type and reloads', async () => {
    vi.spyOn(svc, 'listTeamTypes').mockResolvedValueOnce([])
    const create = vi.spyOn(svc, 'createTeamType').mockResolvedValue(teamType())
    const wrapper = mountPanel()
    await flushPromises()

    vi.mocked(svc.listTeamTypes).mockResolvedValue([teamType()])
    await wrapper.get('[data-test="type-key"]').setValue('blue')
    await wrapper.get('[data-test="type-label"]').setValue('Blue Team')
    await wrapper.get('[data-test="type-form"]').trigger('submit')
    await flushPromises()

    expect(create).toHaveBeenCalledWith('tok', 'ex1', {
      type_key: 'blue',
      display_label: 'Blue Team',
      default_color: null,
      is_visible_to_others: true,
    })
    expect(wrapper.text()).toContain('Blue Team')
  })

  it('surfaces the 409 when deleting a type still in use', async () => {
    vi.spyOn(svc, 'listTeamTypes').mockResolvedValue([teamType()])
    vi.spyOn(svc, 'deleteTeamType').mockRejectedValue(
      new ApiError('HTTP_ERROR', 'type in use', [], undefined, 409),
    )
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.get('[data-test="type-delete-tt1"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="type-error"]').exists()).toBe(true)
  })
})
