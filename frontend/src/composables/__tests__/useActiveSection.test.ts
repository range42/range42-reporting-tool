import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { useActiveSection } from '@/composables/useActiveSection'

const replace = vi.fn()
const push = vi.fn()
let currentQuery: Record<string, string> = {}

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: currentQuery }),
  useRouter: () => ({ replace, push }),
}))

class FakeIntersectionObserver {
  static instances: FakeIntersectionObserver[] = []
  callback: IntersectionObserverCallback
  observed = new Set<Element>()
  disconnect = vi.fn(() => undefined)
  unobserve = vi.fn((el: Element) => {
    this.observed.delete(el)
  })
  observe = vi.fn((el: Element) => {
    this.observed.add(el)
  })

  constructor(callback: IntersectionObserverCallback) {
    this.callback = callback
    FakeIntersectionObserver.instances.push(this)
  }
}

function fireIntersecting(el: Element): void {
  const inst = FakeIntersectionObserver.instances.at(-1)!
  inst.callback(
    [{ isIntersecting: true, target: el } as IntersectionObserverEntry],
    inst as unknown as IntersectionObserver,
  )
}

beforeEach(() => {
  currentQuery = {}
  replace.mockClear()
  push.mockClear()
  FakeIntersectionObserver.instances = []
  vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver)
})

afterEach(() => vi.unstubAllGlobals())

describe('useActiveSection', () => {
  it('reports the first section as active on mount', () => {
    const { activeSectionId } = useActiveSection(ref(['d1', 'd2', 'd3']))
    expect(activeSectionId.value).toBe('d1')
  })

  it('updates the active section when an observer entry becomes intersecting', () => {
    const { activeSectionId, registerRow } = useActiveSection(ref(['d1', 'd2']))
    const el = document.createElement('div')
    registerRow('d2', el)
    fireIntersecting(el)
    expect(activeSectionId.value).toBe('d2')
  })

  it('writes the active section into the URL query without adding history entries', () => {
    const { registerRow } = useActiveSection(ref(['d1', 'd2']))
    const el = document.createElement('div')
    registerRow('d2', el)
    fireIntersecting(el)
    expect(replace).toHaveBeenCalledWith({ query: { section: 'd2' } })
    expect(push).not.toHaveBeenCalled()
  })

  it('scrolls the paired row into view when jumpTo is called', () => {
    const { registerRow, jumpTo } = useActiveSection(ref(['d1']))
    const el = document.createElement('div')
    el.scrollIntoView = vi.fn()
    registerRow('d1', el)
    jumpTo('d1')
    expect(el.scrollIntoView).toHaveBeenCalledWith({ block: 'start', behavior: 'smooth' })
  })

  it('uses auto scroll behavior when prefers-reduced-motion is set', () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }))
    const { registerRow, jumpTo } = useActiveSection(ref(['d1']))
    const el = document.createElement('div')
    el.scrollIntoView = vi.fn()
    registerRow('d1', el)
    jumpTo('d1')
    expect(el.scrollIntoView).toHaveBeenCalledWith({ block: 'start', behavior: 'auto' })
  })

  it('disconnects the observer on unmount', () => {
    const { registerRow, disconnect } = useActiveSection(ref(['d1']))
    registerRow('d1', document.createElement('div'))
    disconnect()
    expect(FakeIntersectionObserver.instances[0]!.disconnect).toHaveBeenCalled()
  })

  it('degrades to no-op tracking when IntersectionObserver is unavailable', () => {
    vi.stubGlobal('IntersectionObserver', undefined)
    const { activeSectionId, registerRow, jumpTo, disconnect } = useActiveSection(ref(['d1']))
    const el = document.createElement('div')
    el.scrollIntoView = vi.fn()
    expect(() => {
      registerRow('d1', el)
      jumpTo('d1')
      disconnect()
    }).not.toThrow()
    expect(activeSectionId.value).toBe('d1')
    expect(el.scrollIntoView).toHaveBeenCalled()
  })
})
