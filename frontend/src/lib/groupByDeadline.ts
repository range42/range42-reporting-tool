/**
 * Bucket queue entries by the deadline they share.
 *
 * The evaluator's working unit is a DEADLINE, not a report: several teams file against the
 * same due time, and those are the reports to grade together — which is also why the compare
 * action hangs off a group rather than a row.
 *
 * Grouping is by INSTANT, not by string: `…T18:00:00Z` and `…T20:00:00+02:00` are the same
 * moment written two ways, and bucketing on the raw string would split one deadline into two
 * headers reading the same local time. Entries with no deadline sort last — undated work is
 * real work, but it never outranks something actually due.
 */

export interface HasDeadline {
  dueAt: string | null
}

/**
 * One row of the evaluator's queue: their evaluation, plus the report context they need to
 * decide what to grade next. Flattened deliberately — the queue reads across reports, and a
 * nested report object would make every template blank-check for undefined.
 */
export interface QueueEntry extends HasDeadline {
  evaluationId: string
  reportId: string
  reportName: string
  teamName: string
  templateName: string | null
  /** Null while the writers still have the report — those rows sit outside the deadline groups. */
  submittedAt: string | null
  gradedSectionCount: number
  gradableSectionCount: number
}

export interface DeadlineGroup<T extends HasDeadline> {
  /** The group's deadline as first seen, or null for the undated bucket. */
  dueAt: string | null
  items: T[]
}

const NO_DEADLINE = 'none'

/** Stable key for one instant; unparseable timestamps keep their raw form rather than
 *  collapsing into each other. */
function instantKey(dueAt: string | null): string {
  if (dueAt === null) return NO_DEADLINE
  const ms = new Date(dueAt).getTime()
  return Number.isNaN(ms) ? `raw:${dueAt}` : String(ms)
}

export function groupByDeadline<T extends HasDeadline>(items: readonly T[]): DeadlineGroup<T>[] {
  const buckets = new Map<string, DeadlineGroup<T>>()
  for (const item of items) {
    const key = instantKey(item.dueAt)
    const existing = buckets.get(key)
    if (existing) existing.items.push(item)
    else buckets.set(key, { dueAt: item.dueAt, items: [item] })
  }
  return [...buckets.values()].sort((a, b) => {
    if (a.dueAt === null) return b.dueAt === null ? 0 : 1
    if (b.dueAt === null) return -1
    return new Date(a.dueAt).getTime() - new Date(b.dueAt).getTime()
  })
}
