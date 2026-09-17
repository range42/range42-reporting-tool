import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import SectionJumpBar from '@/views/evaluations/SectionJumpBar.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

const SECTIONS = [
  { section_def_id: 'd1', name: 'Executive Summary' },
  { section_def_id: 'd2', name: 'Technical Analysis' },
  { section_def_id: 'd3', name: 'Recommendations' },
]

function mountBar(activeSectionId: string | null) {
  return mount(SectionJumpBar, {
    props: { sections: SECTIONS, activeSectionId },
    global: { plugins: [i18n] },
  })
}

describe('SectionJumpBar.vue', () => {
  it('renders one link per section in position order', () => {
    const wrapper = mountBar(null)
    const links = wrapper.findAll('a')
    expect(links.map((l) => l.attributes('data-test'))).toEqual(['jump-d1', 'jump-d2', 'jump-d3'])
    expect(links.map((l) => l.text())).toEqual([
      'Executive Summary',
      'Technical Analysis',
      'Recommendations',
    ])
  })

  it('marks the active section with aria-current', () => {
    const wrapper = mountBar('d2')
    expect(wrapper.find('[data-test="jump-d1"]').attributes('aria-current')).toBeUndefined()
    expect(wrapper.find('[data-test="jump-d2"]').attributes('aria-current')).toBe('true')
  })

  it('emits jump with the section_def_id on activation', async () => {
    const wrapper = mountBar(null)
    await wrapper.find('[data-test="jump-d3"]').trigger('click')
    expect(wrapper.emitted('jump')).toEqual([['d3']])
  })
})
