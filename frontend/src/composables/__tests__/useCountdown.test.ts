import { describe, expect, it } from 'vitest'
import { useCountdown } from '@/composables/useCountdown'

// Deterministic stand-in for vue-i18n's t: echoes the key, appending {time}.
const t = (key: string, named?: Record<string, unknown>): string =>
  named && 'time' in named ? `${key} ${String(named.time)}` : key

const now = new Date('2026-06-26T10:00:00Z')

const dueIn = (ms: number): string => new Date(now.getTime() + ms).toISOString()

const MS_PER_HOUR = 3_600_000
const MS_PER_MINUTE = 60_000

describe('useCountdown', () => {
  const { info } = useCountdown(t)

  it('returns null when there is no due date', () => {
    expect(info(null, now)).toBeNull()
  })

  it('overdue → critical with the overdue label', () => {
    expect(info(dueIn(-MS_PER_MINUTE), now)).toEqual({
      label: 'reports.overdue',
      urgency: 'critical',
    })
  })

  it('less than 1h → critical countdown in minutes', () => {
    expect(info(dueIn(30 * MS_PER_MINUTE), now)).toEqual({
      label: 'reports.dueIn 30m',
      urgency: 'critical',
    })
  })

  it('between 1h and 24h → soon countdown in hours and minutes', () => {
    expect(info(dueIn(5 * MS_PER_HOUR + 12 * MS_PER_MINUTE), now)).toEqual({
      label: 'reports.dueIn 5h 12m',
      urgency: 'soon',
    })
  })

  it('more than 24h → none with an absolute date', () => {
    const dueAt = dueIn(48 * MS_PER_HOUR)
    expect(info(dueAt, now)).toEqual({
      label: new Date(dueAt).toLocaleDateString(),
      urgency: 'none',
    })
  })

  it('exactly 1h remaining is still critical', () => {
    expect(info(dueIn(MS_PER_HOUR), now)).toEqual({
      label: 'reports.dueIn 1h 0m',
      urgency: 'critical',
    })
  })

  it('exactly 24h remaining is still a countdown', () => {
    expect(info(dueIn(24 * MS_PER_HOUR), now)).toEqual({
      label: 'reports.dueIn 24h 0m',
      urgency: 'soon',
    })
  })
})
