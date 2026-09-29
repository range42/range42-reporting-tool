import { describe, expect, it } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import RichTextField from '@/views/reports/RichTextField.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

describe('RichTextField.vue', () => {
  it('does not emit an update when only the disabled state changes', async () => {
    const w = mount(RichTextField, {
      props: { modelValue: '<p>text</p>', testId: 't', disabled: true },
      global: { plugins: [i18n] },
      attachTo: document.body,
    })
    await flushPromises()
    await w.setProps({ disabled: false })
    await flushPromises()
    expect(w.emitted('update:modelValue')).toBeUndefined()
    w.unmount()
  })
})
