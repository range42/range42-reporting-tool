export const COUNTDOWN_THRESHOLD_HOURS = 24
export const CRITICAL_THRESHOLD_HOURS = 1

const MS_PER_HOUR = 3_600_000
const MS_PER_MINUTE = 60_000

export type CountdownUrgency = 'none' | 'soon' | 'critical'

export interface CountdownInfo {
  label: string
  urgency: CountdownUrgency
}

type TranslateFn = (key: string, named?: Record<string, unknown>) => string

/**
 * Deadline countdown shared by report lists and editors. `t` is injected so
 * the composable stays pure and testable outside a component/i18n context.
 *
 * Buckets: overdue or ≤1h → `critical`; ≤24h → `soon` (both with a relative
 * countdown label); beyond 24h → `none` with an absolute date.
 */
export function useCountdown(t: TranslateFn) {
  function info(dueAt: string | null, now: Date = new Date()): CountdownInfo | null {
    if (!dueAt) return null
    const due = new Date(dueAt)
    const ms = due.getTime() - now.getTime()
    if (ms <= 0) return { label: t('reports.overdue'), urgency: 'critical' }
    const hours = ms / MS_PER_HOUR
    if (hours > COUNTDOWN_THRESHOLD_HOURS) {
      return { label: due.toLocaleDateString(), urgency: 'none' }
    }
    const h = Math.floor(hours)
    const m = Math.floor((ms % MS_PER_HOUR) / MS_PER_MINUTE)
    return {
      label: t('reports.dueIn', { time: h > 0 ? `${h}h ${m}m` : `${m}m` }),
      urgency: hours <= CRITICAL_THRESHOLD_HOURS ? 'critical' : 'soon',
    }
  }

  return { info }
}
