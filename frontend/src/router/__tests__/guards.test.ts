import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { resolveNavigation } from '@/router/guards'
import { useAuthStore } from '@/stores/auth'
import { useCapabilitiesStore } from '@/stores/capabilities'

const ADMIN = { id: 'a', email: 'a', display_name: 'a', avatar_url: null, is_global_admin: true }
const MEMBER = { id: 'm', email: 'm', display_name: 'm', avatar_url: null, is_global_admin: false }

describe('resolveNavigation', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('redirects unauthenticated users away from a protected route', () => {
    expect(resolveNavigation({ requiresAuth: true }, '/exercises')).toBe('/login')
  })

  it('lets an authenticated user into a protected route', () => {
    const s = useAuthStore()
    s.setSession({ access_token: 't', token_type: 'bearer', user: MEMBER })
    expect(resolveNavigation({ requiresAuth: true }, '/exercises')).toBeNull()
  })

  it('redirects a non-admin away from an admin route', () => {
    const s = useAuthStore()
    s.setSession({ access_token: 't', token_type: 'bearer', user: MEMBER })
    expect(resolveNavigation({ requiresAuth: true, requiresAdmin: true }, '/settings/roles')).toBe(
      '/exercises',
    )
  })

  it('lets an admin into an admin route', () => {
    const s = useAuthStore()
    s.setSession({ access_token: 't', token_type: 'bearer', user: ADMIN })
    expect(
      resolveNavigation({ requiresAuth: true, requiresAdmin: true }, '/settings/roles'),
    ).toBeNull()
  })

  it('bounces an authenticated user off the login page', () => {
    const s = useAuthStore()
    s.setSession({ access_token: 't', token_type: 'bearer', user: MEMBER })
    expect(resolveNavigation({ public: true, loginPage: true }, '/login')).toBe('/exercises')
  })

  it('lets a global admin into an approver route', () => {
    const s = useAuthStore()
    s.setSession({ access_token: 't', token_type: 'bearer', user: ADMIN })
    expect(
      resolveNavigation(
        { requiresAuth: true, requiresApprover: true },
        '/exercises/ex1/reports/approvals',
      ),
    ).toBeNull()
  })

  it('lets an approver with the cached capability into an approver route', () => {
    const s = useAuthStore()
    s.setSession({ access_token: 't', token_type: 'bearer', user: MEMBER })
    useCapabilitiesStore().set('ex1', ['reports:approve'])
    expect(
      resolveNavigation(
        { requiresAuth: true, requiresApprover: true },
        '/exercises/ex1/reports/approvals',
      ),
    ).toBeNull()
  })

  it('redirects a non-approver away from an approver route', () => {
    const s = useAuthStore()
    s.setSession({ access_token: 't', token_type: 'bearer', user: MEMBER })
    expect(
      resolveNavigation(
        { requiresAuth: true, requiresApprover: true },
        '/exercises/ex1/reports/approvals',
      ),
    ).toBe('/exercises')
  })
})
