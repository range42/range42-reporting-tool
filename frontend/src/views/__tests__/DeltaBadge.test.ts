import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import DeltaBadge from '@/views/evaluations/DeltaBadge.vue'

describe('DeltaBadge.vue', () => {
  it('renders an upward delta with a sign for an improvement', () => {
    const wrapper = mount(DeltaBadge, { props: { current: '8.00', previous: '7.50' } })
    expect(wrapper.find('[data-test="delta-badge"]').text()).toContain('+0.50')
  })

  it('renders a downward delta for a regression', () => {
    const wrapper = mount(DeltaBadge, { props: { current: '6.00', previous: '7.50' } })
    expect(wrapper.find('[data-test="delta-badge"]').text()).toContain('-1.50')
  })

  it('renders nothing when the previous grade is unavailable', () => {
    const wrapper = mount(DeltaBadge, { props: { current: '8.00', previous: null } })
    expect(wrapper.find('[data-test="delta-badge"]').exists()).toBe(false)
  })

  it('renders nothing for a not_graded section', () => {
    const wrapper = mount(DeltaBadge, { props: { current: null, previous: null } })
    expect(wrapper.find('[data-test="delta-badge"]').exists()).toBe(false)
  })

  it('conveys direction by text and icon, not colour alone', () => {
    const up = mount(DeltaBadge, { props: { current: '8.00', previous: '7.50' } })
    const down = mount(DeltaBadge, { props: { current: '6.00', previous: '7.50' } })
    expect(up.find('[data-test="delta-icon-up"]').exists()).toBe(true)
    expect(up.text()).toContain('+')
    expect(down.find('[data-test="delta-icon-down"]').exists()).toBe(true)
    expect(down.text()).toContain('-')
  })

  it('parses two-decimal string grades before comparing them', () => {
    // "7.50" vs "7.5" must compare equal, not string-diff, so no badge for parity.
    const wrapper = mount(DeltaBadge, { props: { current: '7.50', previous: '7.5' } })
    expect(wrapper.find('[data-test="delta-badge"]').exists()).toBe(false)
  })
})
