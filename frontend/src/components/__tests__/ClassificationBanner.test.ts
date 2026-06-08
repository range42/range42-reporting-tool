import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ClassificationBanner from '@/components/ClassificationBanner.vue'

describe('ClassificationBanner', () => {
  it('renders the marking text', () => {
    const w = mount(ClassificationBanner, { props: { marking: 'UNCLASSIFIED' } })
    expect(w.text()).toContain('UNCLASSIFIED')
  })
})
