import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import AppShell from '@/components/AppShell.vue'
import { useAuthStore } from '@/stores/auth'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const push = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
  RouterLink: { template: '<a><slot /></a>' },
}))

const USER = {
  id: 'u1',
  email: 'alice@range42.local',
  display_name: 'Alice Writer',
  avatar_url: null,
  is_global_admin: false,
}

function mountShell() {
  return mount(AppShell, { global: { plugins: [i18n] } })
}

describe('AppShell.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    push.mockClear()
  })

  it('offers a logout control to a signed-in user', () => {
    useAuthStore().setSession({ access_token: 'tok', token_type: 'bearer', user: USER })
    expect(mountShell().find('[data-test="app-logout"]').exists()).toBe(true)
  })

  it('offers no logout control when nobody is signed in', () => {
    expect(mountShell().find('[data-test="app-logout"]').exists()).toBe(false)
  })

  it('clears the session and redirects to the login page', async () => {
    const auth = useAuthStore()
    auth.setSession({ access_token: 'tok', token_type: 'bearer', user: USER })
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify({ data: { revoked: true } }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
      ),
    )

    const w = mountShell()
    await w.find('[data-test="app-logout"]').trigger('click')
    await flushPromises()

    expect(auth.token).toBeNull()
    expect(auth.user).toBeNull()
    expect(localStorage.getItem('rt_token')).toBeNull()
    expect(push).toHaveBeenCalledWith('/login')
    vi.unstubAllGlobals()
  })
})
