import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import AuthCallback from '@/views/AuthCallback.vue'
import { useAuthStore } from '@/stores/auth'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const push = vi.fn()
let query: Record<string, string> = {}
vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
  useRoute: () => ({ query }),
}))

function mountCb() {
  return mount(AuthCallback, { global: { plugins: [i18n] } })
}

describe('AuthCallback.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    push.mockClear()
    query = {}
  })

  it('completes the OIDC exchange and redirects to /exercises', async () => {
    query = { code: 'c', state: 's' }
    const auth = useAuthStore()
    const spy = vi.spyOn(auth, 'completeOidc').mockResolvedValue()
    mountCb()
    await flushPromises()
    expect(spy).toHaveBeenCalledWith('c', 's')
    expect(push).toHaveBeenCalledWith('/exercises')
  })

  it('shows an error and does not redirect when code/state are missing', async () => {
    query = {}
    const wrapper = mountCb()
    await flushPromises()
    expect(wrapper.find('.alert-error').exists()).toBe(true)
    expect(push).not.toHaveBeenCalled()
  })
})
