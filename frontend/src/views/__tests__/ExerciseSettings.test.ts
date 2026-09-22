import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import en from '@/locales/en/common.json'
import ExerciseSettings from '@/views/settings/ExerciseSettings.vue'
import { useAuthStore } from '@/stores/auth'
import * as exercisesSvc from '@/services/exercises'
import * as teamTypesSvc from '@/services/teamTypes'
import * as teamsSvc from '@/services/teams'
import * as exerciseRolesSvc from '@/services/exerciseRoles'
import * as rolesSvc from '@/services/roles'
import type { Exercise } from '@/services/exercises'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { exerciseId: 'ex1' } }),
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { template: '<a><slot /></a>' },
}))

function exercise(over: Partial<Exercise> = {}): Exercise {
  return {
    id: 'ex1',
    name: 'Autumn Range',
    description: null,
    status: 'draft',
    starts_at: null,
    ends_at: null,
    classification: null,
    tlp: null,
    classification_caveats: null,
    created_by: 'u',
    created_at: '',
    updated_at: '',
    ...over,
  }
}

function mountPage() {
  return mount(ExerciseSettings, { global: { plugins: [i18n] } })
}

describe('ExerciseSettings', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'ga', email: 'a', display_name: 'Ada', avatar_url: null, is_global_admin: true },
    })
    vi.spyOn(exercisesSvc, 'getExercise').mockResolvedValue(exercise())
    vi.spyOn(teamTypesSvc, 'listTeamTypes').mockResolvedValue([])
    vi.spyOn(teamsSvc, 'listTeams').mockResolvedValue([])
    vi.spyOn(exerciseRolesSvc, 'listExerciseRoleAssignments').mockResolvedValue([])
    vi.spyOn(rolesSvc, 'listRoles').mockResolvedValue([])
  })

  it('loads the exercise and shows the Details tab by default', async () => {
    const wrapper = mountPage()
    await flushPromises()
    expect((wrapper.get('[data-test="details-name"]').element as HTMLInputElement).value).toBe(
      'Autumn Range',
    )
  })

  it('saves details via updateExercise', async () => {
    const update = vi
      .spyOn(exercisesSvc, 'updateExercise')
      .mockResolvedValue(exercise({ name: 'Winter' }))
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('[data-test="details-name"]').setValue('Winter')
    await wrapper.get('[data-test="details-form"]').trigger('submit')
    await flushPromises()

    expect(update).toHaveBeenCalledWith('tok', 'ex1', expect.objectContaining({ name: 'Winter' }))
  })

  it('archives the exercise', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const archive = vi
      .spyOn(exercisesSvc, 'archiveExercise')
      .mockResolvedValue(exercise({ status: 'archived' }))
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('[data-test="details-archive"]').trigger('click')
    await flushPromises()

    expect(archive).toHaveBeenCalledWith('tok', 'ex1')
  })

  it('switches tabs and mounts the corresponding panel', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.find('[data-test="type-form"]').exists()).toBe(false)
    await wrapper.get('[data-test="tab-teamTypes"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="type-form"]').exists()).toBe(true)

    await wrapper.get('[data-test="tab-teams"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="team-form"]').exists()).toBe(true)

    await wrapper.get('[data-test="tab-roles"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="role-search"]').exists()).toBe(true)
  })
})
