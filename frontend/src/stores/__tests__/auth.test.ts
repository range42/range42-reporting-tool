import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'

const USER = {
  id: 'u1',
  email: 'a@x.test',
  display_name: 'Ann',
  avatar_url: null,
  is_global_admin: true,
}

function envelope(status: number, data: unknown): Response {
  return new Response(JSON.stringify({ data }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('starts unauthenticated', () => {
    const s = useAuthStore()
    expect(s.isAuthenticated).toBe(false)
    expect(s.isAdmin).toBe(false)
  })

  it('emergency login stores token + user and persists the token', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          envelope(200, { access_token: 'tok', token_type: 'bearer', user: USER }),
        ),
    )
    const s = useAuthStore()
    await s.loginEmergency('pw')
    expect(s.token).toBe('tok')
    expect(s.user).toEqual(USER)
    expect(s.isAuthenticated).toBe(true)
    expect(s.isAdmin).toBe(true)
    expect(localStorage.getItem('rt_token')).toBe('tok')
  })

  it('rehydrate loads token from localStorage and fetches me', async () => {
    localStorage.setItem('rt_token', 'persisted')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(envelope(200, USER)))
    const s = useAuthStore()
    await s.rehydrate()
    expect(s.token).toBe('persisted')
    expect(s.user).toEqual(USER)
  })

  it('rehydrate clears a stale token when /auth/me 401s', async () => {
    localStorage.setItem('rt_token', 'stale')
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { code: 'X', message: 'no', details: [] } }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )
    const s = useAuthStore()
    await s.rehydrate()
    expect(s.token).toBeNull()
    expect(s.user).toBeNull()
    expect(localStorage.getItem('rt_token')).toBeNull()
  })

  it('logout clears state + storage and calls the endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(envelope(200, { revoked: true }))
    vi.stubGlobal('fetch', fetchMock)
    const s = useAuthStore()
    s.setSession({ access_token: 'tok', token_type: 'bearer', user: USER })
    await s.logout()
    expect(s.token).toBeNull()
    expect(s.user).toBeNull()
    expect(localStorage.getItem('rt_token')).toBeNull()
    expect(fetchMock).toHaveBeenCalledOnce()
  })
})
