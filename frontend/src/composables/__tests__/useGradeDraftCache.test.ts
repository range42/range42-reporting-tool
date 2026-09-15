import { beforeEach, describe, expect, it } from 'vitest'
import { useGradeDraftCache } from '@/composables/useGradeDraftCache'

describe('useGradeDraftCache', () => {
  beforeEach(() => localStorage.clear())

  it('writes a draft under the evaluationId:sectionId key', () => {
    const cache = useGradeDraftCache('ev1')
    cache.save('s1', { grade: 7.5 }, '2026-09-09T12:00:00Z')

    expect(localStorage.getItem('r42:grade-draft:ev1:s1')).not.toBeNull()
    expect(cache.read('s1')?.value).toEqual({ grade: 7.5 })
    // A different evaluation's draft for the same section is a different key.
    expect(useGradeDraftCache('ev2').read('s1')).toBeNull()
  })

  it('isNewerThanServer is true when the cached draft postdates the server updated_at', () => {
    const cache = useGradeDraftCache('ev1')
    cache.save('s1', { grade: 7.5 }, '2026-09-09T12:00:00Z')

    expect(cache.isNewerThanServer('s1', '2026-09-09T10:00:00Z')).toBe(true)
    expect(cache.isNewerThanServer('s1', '2026-09-09T13:00:00Z')).toBe(false)
    // No draft at all is not "newer".
    expect(cache.isNewerThanServer('s2', '2026-09-09T10:00:00Z')).toBe(false)
  })

  it('clear() removes only that section key', () => {
    const cache = useGradeDraftCache('ev1')
    cache.save('s1', { grade: 1 }, '2026-09-09T12:00:00Z')
    cache.save('s2', { grade: 2 }, '2026-09-09T12:00:00Z')

    cache.clear('s1')

    expect(cache.read('s1')).toBeNull()
    expect(cache.read('s2')?.value).toEqual({ grade: 2 })
  })

  it('returns null for a malformed localStorage payload instead of throwing', () => {
    const cache = useGradeDraftCache('ev1')
    localStorage.setItem('r42:grade-draft:ev1:s1', '{not json')
    expect(cache.read('s1')).toBeNull()
    expect(cache.isNewerThanServer('s1', '2026-09-09T10:00:00Z')).toBe(false)

    // Valid JSON of the wrong shape is malformed too.
    localStorage.setItem('r42:grade-draft:ev1:s2', '[1,2,3]')
    expect(cache.read('s2')).toBeNull()
    localStorage.setItem('r42:grade-draft:ev1:s3', '{"value":{"grade":1}}')
    expect(cache.read('s3')).toBeNull()
  })
})
