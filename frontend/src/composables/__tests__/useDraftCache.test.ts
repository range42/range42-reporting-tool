import { beforeEach, describe, expect, it } from 'vitest'
import { useDraftCache } from '@/composables/useDraftCache'

describe('useDraftCache', () => {
  beforeEach(() => localStorage.clear())

  it('writes and reads a draft', () => {
    const cache = useDraftCache('r1')
    cache.write('s1', '<p>hi</p>', '2026-06-26T10:00:00Z')
    expect(cache.read('s1')?.value).toBe('<p>hi</p>')
  })

  it('clear removes a draft', () => {
    const cache = useDraftCache('r1')
    cache.write('s1', 'x', '2026-06-26T10:00:00Z')
    cache.clear('s1')
    expect(cache.read('s1')).toBeNull()
  })

  it('isNewerThanServer compares timestamps', () => {
    const cache = useDraftCache('r1')
    cache.write('s1', 'x', '2026-06-26T12:00:00Z')
    expect(cache.isNewerThanServer('s1', '2026-06-26T10:00:00Z')).toBe(true)
    expect(cache.isNewerThanServer('s1', '2026-06-26T13:00:00Z')).toBe(false)
  })
})
