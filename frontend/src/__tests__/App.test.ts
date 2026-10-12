import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import App from '@/App.vue'

describe('App', () => {
  it('renders the routed page without a classification banner', () => {
    const w = mount(App, { global: { stubs: { RouterView: { template: '<main>page</main>' } } } })
    expect(w.text()).toBe('page')
  })
})
