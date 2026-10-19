import { describe, expect, it } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import type { Editor } from '@tiptap/vue-3'
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

  it('keeps the document when the saved copy only differs in markup', async () => {
    const editorTable =
      '<p>intro</p><table style="min-width: 50px;"><colgroup><col style="min-width: 25px;">' +
      '</colgroup><tbody><tr><td colspan="1" rowspan="1"><p>cell</p></td></tr></tbody></table>'
    const serverTable =
      '<p>intro</p><table><tbody><tr><td colspan="1" rowspan="1"><p>cell</p></td></tr></tbody></table>'
    const w = mount(RichTextField, {
      props: { modelValue: editorTable, testId: 't' },
      global: { plugins: [i18n] },
      attachTo: document.body,
    })
    await flushPromises()
    const editor = (w.find('.tiptap').element as HTMLElement & { editor: Editor }).editor
    let replacements = 0
    editor.on('transaction', ({ transaction }) => {
      if (transaction.docChanged) replacements += 1
    })

    await w.setProps({ modelValue: serverTable })
    await flushPromises()

    expect(replacements).toBe(0)
    w.unmount()
  })
})
