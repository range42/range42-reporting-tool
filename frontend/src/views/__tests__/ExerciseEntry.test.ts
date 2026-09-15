import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import ExerciseEntry from '@/views/ExerciseEntry.vue'
import { useAuthStore } from '@/stores/auth'
import * as exercises from '@/services/exercises'

const replace = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { exerciseId: 'ex1' } }),
  useRouter: () => ({ replace }),
}))

const REPORTS = '/exercises/ex1/reports'
const QUEUE = { name: 'evaluation-queue', params: { exerciseId: 'ex1' } }

function signIn(isGlobalAdmin: boolean): void {
  useAuthStore().setSession({
    access_token: 'tok',
    token_type: 'bearer',
    user: {
      id: 'u',
      email: 'e',
      display_name: 'd',
      avatar_url: null,
      is_global_admin: isGlobalAdmin,
    },
  })
}

function grant(capabilities: string[], isGlobalAdmin = false): void {
  vi.spyOn(exercises, 'getMyCapabilities').mockResolvedValue({
    is_global_admin: isGlobalAdmin,
    capabilities,
  })
}

describe('ExerciseEntry.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.restoreAllMocks()
    replace.mockClear()
  })

  it('sends an evaluator straight to their own queue', async () => {
    signIn(false)
    grant(['evaluations:write'])
    mount(ExerciseEntry)
    await flushPromises()
    expect(replace).toHaveBeenCalledWith(QUEUE)
  })

  it('sends a player to the report list', async () => {
    signIn(false)
    grant(['reports:write'])
    mount(ExerciseEntry)
    await flushPromises()
    expect(replace).toHaveBeenCalledWith(REPORTS)
  })

  // A global admin carries every capability, evaluations:write included. Keying the decision
  // on the capability alone would divert them out of the report list they run.
  it('leaves a global admin on the report list even though they may evaluate', async () => {
    signIn(true)
    grant(['evaluations:write', 'reports:write'], true)
    mount(ExerciseEntry)
    await flushPromises()
    expect(replace).toHaveBeenCalledWith(REPORTS)
  })

  it('falls back to the report list when capabilities cannot be loaded', async () => {
    signIn(false)
    vi.spyOn(exercises, 'getMyCapabilities').mockRejectedValue(new Error('boom'))
    mount(ExerciseEntry)
    await flushPromises()
    expect(replace).toHaveBeenCalledWith(REPORTS)
  })
})
