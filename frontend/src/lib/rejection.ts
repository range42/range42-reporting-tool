import type { ReportDetail } from '@/services/reports'

/** What the approver said when they sent the report back: overall note + remark per section id. */
export interface RejectionFeedback {
  readonly comment: string | null
  readonly remarks: Readonly<Record<string, string>>
}

type RejectionSource = Pick<ReportDetail, 'status'> &
  Partial<Pick<ReportDetail, 'approval_cycle' | 'approval_records'>>

/**
 * The rejection the writer is currently addressing, or null.
 *
 * Only a draft whose previous submission ended in a rejection qualifies: a rejection bumps
 * `approval_cycle`, so the decision that sent it back belongs to `approval_cycle - 1`.
 */
export function latestRejection(report: RejectionSource): RejectionFeedback | null {
  if (report.status !== 'draft' || report.approval_cycle === undefined) return null
  const previousCycle = report.approval_cycle - 1
  const rejection = (report.approval_records ?? [])
    .filter((r) => r.action === 'rejected' && r.cycle === previousCycle)
    .at(-1)
  if (!rejection) return null
  return {
    comment: rejection.comment,
    remarks: Object.fromEntries(
      (rejection.section_remarks ?? []).map((m) => [m.report_section_id, m.remark]),
    ),
  }
}
