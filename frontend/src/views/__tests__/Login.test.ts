import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import Login from '@/views/Login.vue'
import { useAuthStore } from '@/stores/auth'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const push = vi.fn()
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))

function mountLogin() {
  return mount(Login, { global: { plugins: [i18n] } })
}

describe('Login.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    push.mockClear()
  })

  it('submits the emergency form and routes to /exercises on success', async () => {
    const wrapper = mountLogin()
    const auth = useAuthStore()
    vi.spyOn(auth, 'loginEmergency').mockResolvedValue()
    await wrapper.find('input[type="password"]').setValue('pw')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    expect(auth.loginEmergency).toHaveBeenCalledWith('pw')
    expect(push).toHaveBeenCalledWith('/exercises')
  })

  it('shows an error alert when emergency login fails', async () => {
    const wrapper = mountLogin()
    const auth = useAuthStore()
    vi.spyOn(auth, 'loginEmergency').mockRejectedValue(new Error('nope'))
    await wrapper.find('input[type="password"]').setValue('bad')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    expect(wrapper.find('.alert-error').exists()).toBe(true)
    expect(push).not.toHaveBeenCalled()
  })
})
