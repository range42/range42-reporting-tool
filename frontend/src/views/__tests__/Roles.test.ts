import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import Roles from '@/views/settings/Roles.vue'
import { useAuthStore } from '@/stores/auth'
import * as svc from '@/services/roles'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { template: '<a><slot /></a>' },
}))

const SYSTEM: svc.Role = {
  id: 's',
  role_key: 'observer',
  display_label: 'Observer',
  description: null,
  permissions: ['exercises:read'],
  is_system: true,
  created_at: '',
  updated_at: '',
}
const CUSTOM: svc.Role = {
  id: 'c',
  role_key: 'ciso',
  display_label: 'CISO',
  description: null,
  permissions: ['exercises:read'],
  is_system: false,
  created_at: '',
  updated_at: '',
}

function mountRoles() {
  return mount(Roles, { global: { plugins: [i18n] } })
}

describe('Roles.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'a', email: 'a', display_name: 'a', avatar_url: null, is_global_admin: true },
    })
    vi.spyOn(svc, 'listPermissions').mockResolvedValue([
      'exercises:read',
      'teams:read',
      'reports:write',
    ])
  })

  it('lists roles and marks system roles read-only', async () => {
    vi.spyOn(svc, 'listRoles').mockResolvedValue([SYSTEM, CUSTOM])
    const wrapper = mountRoles()
    await flushPromises()
    expect(wrapper.text()).toContain('Observer')
    expect(wrapper.text()).toContain('CISO')
    const systemRow = wrapper.get('[data-test="role-row-s"]')
    expect(systemRow.get('[data-test="edit"]').attributes('disabled')).toBeDefined()
  })

  it('creates a role through the modal', async () => {
    vi.spyOn(svc, 'listRoles').mockResolvedValue([])
    const create = vi.spyOn(svc, 'createRole').mockResolvedValue(CUSTOM)
    const wrapper = mountRoles()
    await flushPromises()
    await wrapper.get('[data-test="create"]').trigger('click')
    await wrapper.get('[data-test="role_key"]').setValue('ciso')
    await wrapper.get('[data-test="display_label"]').setValue('CISO')
    await wrapper.get('input[value="exercises:read"]').setValue(true)
    await wrapper.get('[data-test="save-form"]').trigger('submit')
    await flushPromises()
    expect(create).toHaveBeenCalledWith(
      'tok',
      expect.objectContaining({
        role_key: 'ciso',
        display_label: 'CISO',
        permissions: ['exercises:read'],
      }),
    )
  })

  it('surfaces a 409 on delete as an alert', async () => {
    vi.spyOn(svc, 'listRoles').mockResolvedValue([CUSTOM])
    const { ApiError } = await import('@/services/http')
    vi.spyOn(svc, 'deleteRole').mockRejectedValue(
      new ApiError('HTTP_ERROR', 'role has active assignments'),
    )
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const wrapper = mountRoles()
    await flushPromises()
    await wrapper.get('[data-test="delete"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('.alert-error').exists()).toBe(true)
  })
})
