import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import en from '@/locales/en/common.json'
import RoleAssignmentsPanel from '@/views/settings/RoleAssignmentsPanel.vue'
import { useAuthStore } from '@/stores/auth'
import * as exerciseRolesSvc from '@/services/exerciseRoles'
import * as rolesSvc from '@/services/roles'
import * as usersSvc from '@/services/users'
import { ApiError } from '@/services/http'
import type { ExerciseRoleAssignment } from '@/services/exerciseRoles'
import type { Role } from '@/services/roles'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

function assignment(over: Partial<ExerciseRoleAssignment> = {}): ExerciseRoleAssignment {
  return {
    id: 'r1',
    exercise_id: 'ex1',
    user_id: 'u1',
    role_key: 'evaluator',
    created_at: 'now',
    ...over,
  }
}

function role(over: Partial<Role> = {}): Role {
  return {
    id: 'rd1',
    role_key: 'evaluator',
    display_label: 'Evaluator',
    description: null,
    permissions: [],
    is_system: true,
    created_at: 'now',
    updated_at: 'now',
    ...over,
  }
}

function mountPanel() {
  return mount(RoleAssignmentsPanel, { props: { exerciseId: 'ex1' }, global: { plugins: [i18n] } })
}

describe('RoleAssignmentsPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'ga', email: 'a', display_name: 'Ada', avatar_url: null, is_global_admin: true },
    })
    vi.spyOn(rolesSvc, 'listRoles').mockResolvedValue([role()])
  })

  it('lists current assignments on mount', async () => {
    vi.spyOn(exerciseRolesSvc, 'listExerciseRoleAssignments').mockResolvedValue([assignment()])
    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.text()).toContain('Evaluator')
  })

  it('grants a role to a searched user, then reloads', async () => {
    vi.spyOn(exerciseRolesSvc, 'listExerciseRoleAssignments').mockResolvedValueOnce([])
    vi.spyOn(usersSvc, 'searchUsers').mockResolvedValue([
      { id: 'u2', display_name: 'Ivan', email: 'ivan@x', avatar_url: null, is_global_admin: false },
    ])
    const grant = vi
      .spyOn(exerciseRolesSvc, 'grantExerciseRole')
      .mockResolvedValue(assignment({ id: 'r2', user_id: 'u2' }))
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.get('[data-test="role-search"]').setValue('ivan')
    await flushPromises()
    await wrapper.get('[data-test="role-candidate-u2"]').trigger('click')
    await wrapper.get('[data-test="role-select"]').setValue('evaluator')
    vi.mocked(exerciseRolesSvc.listExerciseRoleAssignments).mockResolvedValue([
      assignment({ id: 'r2', user_id: 'u2' }),
    ])
    await wrapper.get('[data-test="role-grant"]').trigger('click')
    await flushPromises()

    expect(grant).toHaveBeenCalledWith('tok', 'ex1', 'u2', 'evaluator')
    expect(wrapper.text()).toContain('Ivan')
  })

  it('revokes an assignment and reloads', async () => {
    vi.spyOn(exerciseRolesSvc, 'listExerciseRoleAssignments').mockResolvedValue([assignment()])
    const revoke = vi.spyOn(exerciseRolesSvc, 'revokeExerciseRole').mockResolvedValue(undefined)
    const wrapper = mountPanel()
    await flushPromises()

    vi.mocked(exerciseRolesSvc.listExerciseRoleAssignments).mockResolvedValue([])
    await wrapper.get('[data-test="role-revoke-r1"]').trigger('click')
    await flushPromises()

    expect(revoke).toHaveBeenCalledWith('tok', 'ex1', 'r1')
    expect(wrapper.find('[data-test="role-row-r1"]').exists()).toBe(false)
  })

  it('surfaces a duplicate-grant 409', async () => {
    vi.spyOn(exerciseRolesSvc, 'listExerciseRoleAssignments').mockResolvedValue([])
    vi.spyOn(usersSvc, 'searchUsers').mockResolvedValue([
      { id: 'u2', display_name: 'Ivan', email: 'ivan@x', avatar_url: null, is_global_admin: false },
    ])
    vi.spyOn(exerciseRolesSvc, 'grantExerciseRole').mockRejectedValue(
      new ApiError('HTTP_ERROR', 'already granted', [], undefined, 409),
    )
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.get('[data-test="role-search"]').setValue('ivan')
    await flushPromises()
    await wrapper.get('[data-test="role-candidate-u2"]').trigger('click')
    await wrapper.get('[data-test="role-select"]').setValue('evaluator')
    await wrapper.get('[data-test="role-grant"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-test="role-error"]').exists()).toBe(true)
  })
})
