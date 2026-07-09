import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { installAuthGuards } from '@/stores/auth_boot'
import { useAuthStore } from '@/stores/auth'
import * as http from '@/services/http'

describe('installAuthGuards', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('registers a 401 handler that clears the store and redirects to /login', () => {
    const redirect = vi.fn()
    const spy = vi.spyOn(http, 'registerUnauthorizedHandler')
    const store = useAuthStore()
    store.setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'u', email: 'e', display_name: 'd', avatar_url: null, is_global_admin: false },
    })
    installAuthGuards(redirect)
    const [firstCall] = spy.mock.calls
    expect(firstCall).toBeDefined()
    const handler = firstCall![0]
    handler()
    expect(store.token).toBeNull()
    expect(redirect).toHaveBeenCalledWith('/login')
  })
})
