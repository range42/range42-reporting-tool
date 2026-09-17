import { ref, type Ref } from 'vue'
import {
  compareCampaignReports,
  getCampaignTimeline,
  listCampaigns,
  type Campaign,
  type TimelineEntry,
} from '@/services/campaigns'
import {
  listEvaluationsForReport,
  listSectionGrades,
  type SectionGrade,
} from '@/services/evaluations'
import { ApiError } from '@/services/http'
import type { ReportDetail } from '@/services/reports'

export interface UseCampaignPairingParams {
  token: string
  exerciseId: string
  reportId: string
  userId: string
  /** `?prev=` from the URL — pins a specific earlier cycle over the immediate predecessor. */
  pinnedPrevReportId?: string | null
}

export type CampaignPairingStatus =
  | 'idle'
  | 'loading'
  | 'no_campaign'
  | 'no_previous'
  | 'forbidden'
  | 'ready'
  | 'error'

export interface UseCampaignPairingResult {
  status: Ref<CampaignPairingStatus>
  error: Ref<string | null>
  campaign: Ref<Campaign | null>
  /** The whole campaign timeline, in server order — feeds CampaignNavigator directly. */
  entries: Ref<TimelineEntry[]>
  previousEntry: Ref<TimelineEntry | null>
  previousReport: Ref<ReportDetail | null>
  currentReport: Ref<ReportDetail | null>
  hasOwnPreviousEvaluation: Ref<boolean>
  previousGrades: Ref<SectionGrade[] | null>
  /** The caller's OWN previous evaluation's overall_grade (D6) — never the report aggregate,
   *  and never populated when `hasOwnPreviousEvaluation` is false. */
  previousOverallGrade: Ref<string | null>
  load: () => Promise<void>
}

/**
 * "Previous" is derived, not stored (D11): `campaign`/`campaign_report` carry no sequence
 * column, so ordering is exactly what the caller's timeline array already has — this never
 * re-sorts it. "Previous" is the same-team entry immediately before the current report in that
 * order, unless `pinned` (the URL's `?prev=`) names an earlier cycle explicitly.
 */
export function selectPreviousEntry(
  entries: readonly TimelineEntry[],
  currentId: string,
  teamId: string,
  pinned?: string | null,
): TimelineEntry | null {
  const sameTeam = entries.filter((e) => e.team_id === teamId)
  if (pinned) return sameTeam.find((e) => e.report_id === pinned) ?? null
  const idx = sameTeam.findIndex((e) => e.report_id === currentId)
  if (idx <= 0) return null
  return sameTeam[idx - 1] ?? null
}

async function findCampaign(
  params: UseCampaignPairingParams,
): Promise<{ campaign: Campaign; entries: TimelineEntry[] } | null> {
  const all = await listCampaigns(params.token, params.exerciseId)
  for (const c of all) {
    const entries = await getCampaignTimeline(params.token, params.exerciseId, c.id)
    if (entries.some((e) => e.report_id === params.reportId)) return { campaign: c, entries }
  }
  return null
}

/** Own-scoped probe: a 403 means no evaluation of the caller's own on that report, not an error
 *  — `report_evaluation_breakdown` gates on row ownership before it ever reveals content. */
async function ownPreviousEvaluation(
  params: UseCampaignPairingParams,
  previousReportId: string,
): Promise<{ id: string; overallGrade: string | null } | null> {
  try {
    const breakdown = await listEvaluationsForReport(
      params.token,
      params.exerciseId,
      previousReportId,
    )
    const own = breakdown.evaluations.find((e) => e.evaluator_id === params.userId)
    return own ? { id: own.id, overallGrade: own.overall_grade } : null
  } catch (e) {
    if (e instanceof ApiError && e.status === 403) return null
    throw e
  }
}

export function useCampaignPairing(params: UseCampaignPairingParams): UseCampaignPairingResult {
  const status = ref<CampaignPairingStatus>('idle')
  const error = ref<string | null>(null)
  const campaign = ref<Campaign | null>(null)
  const entries = ref<TimelineEntry[]>([])
  const previousEntry = ref<TimelineEntry | null>(null)
  const previousReport = ref<ReportDetail | null>(null)
  const currentReport = ref<ReportDetail | null>(null)
  const hasOwnPreviousEvaluation = ref(false)
  const previousGrades = ref<SectionGrade[] | null>(null)
  const previousOverallGrade = ref<string | null>(null)

  async function load(): Promise<void> {
    status.value = 'loading'
    error.value = null
    try {
      const found = await findCampaign(params)
      if (!found) {
        status.value = 'no_campaign'
        return
      }
      campaign.value = found.campaign
      entries.value = found.entries

      // The report-nested EvaluationDetail carries team_name, not team_id — the caller can't
      // supply it, so it's read off the caller's own entry in the timeline we just fetched.
      const myTeamId = found.entries.find((e) => e.report_id === params.reportId)?.team_id ?? ''
      const prev = selectPreviousEntry(
        found.entries,
        params.reportId,
        myTeamId,
        params.pinnedPrevReportId,
      )
      previousEntry.value = prev
      if (!prev) {
        status.value = 'no_previous'
        return
      }

      const reports = await compareCampaignReports(
        params.token,
        params.exerciseId,
        found.campaign.id,
        [prev.report_id, params.reportId],
      )
      previousReport.value = reports.find((r) => r.id === prev.report_id) ?? null
      currentReport.value = reports.find((r) => r.id === params.reportId) ?? null

      const own = await ownPreviousEvaluation(params, prev.report_id)
      hasOwnPreviousEvaluation.value = own !== null
      previousOverallGrade.value = own?.overallGrade ?? null
      previousGrades.value = own
        ? await listSectionGrades(params.token, params.exerciseId, prev.report_id, own.id)
        : null

      status.value = 'ready'
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        status.value = 'forbidden'
        return
      }
      status.value = 'error'
      error.value = e instanceof Error ? e.message : 'unknown error'
    }
  }

  return {
    status,
    error,
    campaign,
    entries,
    previousEntry,
    previousReport,
    currentReport,
    hasOwnPreviousEvaluation,
    previousGrades,
    previousOverallGrade,
    load,
  }
}
