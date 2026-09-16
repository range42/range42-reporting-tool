import { apiGet } from '@/services/http'
import type { ReportDetail } from '@/services/reports'

/** Server-side cap on how many reports one compare call may ask for. */
export const COMPARE_MAX_REPORTS = 8

/** A campaign as listed for an exercise. */
export interface Campaign {
  id: string
  exercise_id: string
  name: string
  description: string | null
  report_count: number
  created_by: string
  created_at: string
  updated_at: string
}

/** One campaign report on the evaluator timeline. */
export interface TimelineEntry {
  report_id: string
  name: string
  status: string
  team_id: string
  team_name: string
  submitted_at: string | null
  due_at: string | null
  created_at: string
}

const base = (exerciseId: string): string => `/api/v1/exercises/${exerciseId}/campaigns`

export const listCampaigns = (token: string, exerciseId: string): Promise<Campaign[]> =>
  apiGet<Campaign[]>(base(exerciseId), token)

export const getCampaignTimeline = (
  token: string,
  exerciseId: string,
  cid: string,
): Promise<TimelineEntry[]> => apiGet<TimelineEntry[]>(`${base(exerciseId)}/${cid}/timeline`, token)

export const compareCampaignReports = (
  token: string,
  exerciseId: string,
  cid: string,
  reportIds: readonly string[],
): Promise<ReportDetail[]> => {
  if (reportIds.length < 1 || reportIds.length > COMPARE_MAX_REPORTS) {
    return Promise.reject(
      new RangeError(
        `compare takes 1 to ${COMPARE_MAX_REPORTS} report ids, got ${reportIds.length}`,
      ),
    )
  }
  const qs = new URLSearchParams()
  for (const id of reportIds) qs.append('report_ids', id)
  return apiGet<ReportDetail[]>(`${base(exerciseId)}/${cid}/compare?${qs.toString()}`, token)
}
