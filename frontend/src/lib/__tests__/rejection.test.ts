import { describe, expect, it } from 'vitest'
import { latestRejection } from '@/lib/rejection'
import type { ApprovalRecord } from '@/services/reports'

function record(over: Partial<ApprovalRecord>): ApprovalRecord {
  return {
    id: 'a1',
    report_id: 'r1',
    approver_id: 'u1',
    step: 1,
    cycle: 1,
    action: 'rejected',
    is_admin_override: false,
    comment: 'needs work',
    created_at: '2026-10-13T10:00:00Z',
    section_remarks: [],
    ...over,
  }
}

describe('latestRejection', () => {
  it('returns the comment and remarks of the rejection that sent the report back', () => {
    // Arrange
    const rejection = record({
      section_remarks: [
        {
          id: 'm1',
          report_section_id: 's1',
          remark: 'cite it',
          created_at: '2026-10-13T10:00:00Z',
        },
      ],
    })

    // Act
    const result = latestRejection({
      status: 'draft',
      approval_cycle: 2,
      approval_records: [rejection],
    })

    // Assert
    expect(result).toEqual({ comment: 'needs work', remarks: { s1: 'cite it' } })
  })

  it('returns null once the report has been resubmitted', () => {
    const result = latestRejection({
      status: 'pending_approval',
      approval_cycle: 2,
      approval_records: [record({})],
    })
    expect(result).toBeNull()
  })

  it('ignores a rejection from an older submission', () => {
    // Rejected in cycle 1, resubmitted, then recalled: the old rejection no longer applies.
    const result = latestRejection({
      status: 'draft',
      approval_cycle: 3,
      approval_records: [record({ cycle: 1 })],
    })
    expect(result).toBeNull()
  })

  it('returns null for a draft that was never rejected', () => {
    const result = latestRejection({
      status: 'draft',
      approval_cycle: 2,
      approval_records: [record({ action: 'approved' })],
    })
    expect(result).toBeNull()
  })

  it('tolerates a payload without approval fields', () => {
    expect(latestRejection({ status: 'draft' })).toBeNull()
  })
})
