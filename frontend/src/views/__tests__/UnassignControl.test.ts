import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import UnassignControl from '@/views/reports/UnassignControl.vue'
import { useAuthStore } from '@/stores/auth'
import * as svc from '@/services/evaluations'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

function mountControl() {
  return mount(UnassignControl, {
    props: { exerciseId: 'ex1', rid: 'r1', evid: 'ev1' },
    global: { plugins: [i18n] },
  })
}

async function openAndType(wrapper: ReturnType<typeof mountControl>, reason: string) {
  await wrapper.find('[data-test="unassign-open-ev1"]').trigger('click')
  await wrapper.find('[data-test="unassign-reason-ev1"]').setValue(reason)
  return wrapper.find('[data-test="unassign-submit-ev1"]')
}

describe('UnassignControl.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.restoreAllMocks()
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'ga', email: 'a', display_name: 'Ada', avatar_url: null, is_global_admin: true },
    })
  })

  // The server refuses a blank reason; blocking it here saves discovering that by round trip.
  it('will not submit a blank or whitespace-only reason', async () => {
    const wrapper = mountControl()
    const submit = await openAndType(wrapper, '   ')
    expect(submit.attributes('disabled')).toBeDefined()
  })

  it('sends the reason and announces the removal', async () => {
    const call = vi.spyOn(svc, 'unassignEvaluator').mockResolvedValue({} as never)
    const wrapper = mountControl()
    const submit = await openAndType(wrapper, 'on leave')
    await submit.trigger('click')
    await flushPromises()
    expect(call).toHaveBeenCalledWith('tok', 'ex1', 'r1', 'ev1', 'on leave')
    expect(wrapper.emitted('unassigned')).toHaveLength(1)
  })

  it('reports a failure and stays open so the reason is not lost', async () => {
    vi.spyOn(svc, 'unassignEvaluator').mockRejectedValue(new Error('nope'))
    const wrapper = mountControl()
    const submit = await openAndType(wrapper, 'on leave')
    await submit.trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="unassign-error-ev1"]').exists()).toBe(true)
    expect(wrapper.emitted('unassigned')).toBeUndefined()
  })
})
