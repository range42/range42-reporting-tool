import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import ExerciseWizard from '@/views/settings/ExerciseWizard.vue'
import { useAuthStore } from '@/stores/auth'
import * as svc from '@/services/exercises'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const push = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
  RouterLink: { template: '<a><slot /></a>' },
}))

function mountPage() {
  return mount(ExerciseWizard, { global: { plugins: [i18n] } })
}

describe('ExerciseWizard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    push.mockClear()
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'ga', email: 'a', display_name: 'Ada', avatar_url: null, is_global_admin: true },
    })
  })

  it('disables submit until a name is entered', () => {
    const wrapper = mountPage()
    expect(wrapper.get('[data-test="wizard-submit"]').attributes('disabled')).toBeDefined()
  })

  it('creates the exercise and navigates to its settings screen', async () => {
    const create = vi
      .spyOn(svc, 'createExercise')
      .mockResolvedValue({ id: 'e1', name: 'Autumn Range' } as never)
    const wrapper = mountPage()

    await wrapper.get('[data-test="wizard-name"]').setValue('Autumn Range')
    await wrapper.get('[data-test="wizard-starts"]').setValue('2026-09-01T00:00')
    await wrapper.get('[data-test="wizard-form"]').trigger('submit')
    await flushPromises()

    expect(create).toHaveBeenCalledWith('tok', {
      name: 'Autumn Range',
      description: null,
      starts_at: new Date('2026-09-01T00:00').toISOString(),
      ends_at: null,
      classification: null,
      tlp: null,
    })
    expect(push).toHaveBeenCalledWith('/exercises/e1/settings')
  })

  it('surfaces a create error without navigating', async () => {
    vi.spyOn(svc, 'createExercise').mockRejectedValue(new Error('boom'))
    const wrapper = mountPage()

    await wrapper.get('[data-test="wizard-name"]').setValue('C')
    await wrapper.get('[data-test="wizard-form"]').trigger('submit')
    await flushPromises()

    expect(wrapper.find('[data-test="wizard-error"]').exists()).toBe(true)
    expect(push).not.toHaveBeenCalled()
  })
})
