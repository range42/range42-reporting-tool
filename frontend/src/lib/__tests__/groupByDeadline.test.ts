import { describe, expect, it } from 'vitest'
import { groupByDeadline } from '@/lib/groupByDeadline'

const A = { id: 'a', dueAt: '2026-09-10T18:00:00Z' }
const B = { id: 'b', dueAt: '2026-09-10T18:00:00Z' }
const C = { id: 'c', dueAt: '2026-09-09T12:00:00Z' }
const N = { id: 'n', dueAt: null }

describe('groupByDeadline', () => {
  it('buckets reports by identical due_at', () => {
    const groups = groupByDeadline([A, C, B])
    const late = groups.find((g) => g.dueAt === '2026-09-10T18:00:00Z')!
    expect(late.items.map((i) => i.id)).toEqual(['a', 'b'])
    expect(groups).toHaveLength(2)
  })

  it('orders groups by deadline ascending with null deadlines last', () => {
    const groups = groupByDeadline([N, A, C])
    expect(groups.map((g) => g.dueAt)).toEqual([
      '2026-09-09T12:00:00Z',
      '2026-09-10T18:00:00Z',
      null,
    ])
  })

  it('returns an empty array for no items', () => {
    expect(groupByDeadline([])).toEqual([])
  })

  it('treats equal instants written differently as one deadline', () => {
    // Same instant, different offset notation: one bucket, not two.
    const groups = groupByDeadline([
      { id: 'z', dueAt: '2026-09-10T18:00:00Z' },
      { id: 'y', dueAt: '2026-09-10T20:00:00+02:00' },
    ])
    expect(groups).toHaveLength(1)
    expect(groups[0]!.items.map((i) => i.id)).toEqual(['z', 'y'])
  })
})
