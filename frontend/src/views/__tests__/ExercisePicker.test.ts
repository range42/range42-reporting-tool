import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import ExercisePicker from '@/views/ExercisePicker.vue'
import { useAuthStore } from '@/stores/auth'
import * as svc from '@/services/exercises'
import type { Exercise } from '@/services/exercises'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const push = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
  RouterLink: { template: '<a><slot /></a>' },
}))

function exercise(over: Partial<Exercise> = {}): Exercise {
  return {
    id: '1',
    name: 'Alpha',
    description: null,
    status: 'active',
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

function mountPicker() {
  return mount(ExercisePicker, { global: { plugins: [i18n] } })
}

describe('ExercisePicker.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    const auth = useAuthStore()
    auth.setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'u', email: 'e', display_name: 'd', avatar_url: null, is_global_admin: true },
    })
  })

  it('renders a card per exercise', async () => {
    vi.spyOn(svc, 'listExercises').mockResolvedValue([
      exercise({ id: '1', name: 'Alpha', status: 'active' }),
      exercise({ id: '2', name: 'Bravo', description: 'x', status: 'draft' }),
    ])
    const wrapper = mountPicker()
    await flushPromises()
    expect(wrapper.findAll('[data-test="exercise-card"]')).toHaveLength(2)
    expect(wrapper.text()).toContain('Alpha')
    expect(wrapper.text()).toContain('Bravo')
    expect(svc.listExercises).toHaveBeenCalledWith('tok')
  })

  it('shows the empty state when there are none', async () => {
    vi.spyOn(svc, 'listExercises').mockResolvedValue([])
    const wrapper = mountPicker()
    await flushPromises()
    expect(wrapper.find('[data-test="empty"]').exists()).toBe(true)
  })

  it('shows a New exercise action for admins that navigates to the wizard', async () => {
    vi.spyOn(svc, 'listExercises').mockResolvedValue([])
    const wrapper = mountPicker()
    await flushPromises()
    await wrapper.get('[data-test="new-exercise"]').trigger('click')
    expect(push).toHaveBeenCalledWith('/exercises/new')
  })

  it('hides the New exercise action for non-admins', async () => {
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'u', email: 'e', display_name: 'd', avatar_url: null, is_global_admin: false },
    })
    vi.spyOn(svc, 'listExercises').mockResolvedValue([])
    const wrapper = mountPicker()
    await flushPromises()
    expect(wrapper.find('[data-test="new-exercise"]').exists()).toBe(false)
  })
})
