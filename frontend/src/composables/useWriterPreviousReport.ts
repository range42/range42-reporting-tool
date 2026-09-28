import { ref, type Ref } from 'vue'
import { getCampaignTimeline, listCampaigns, type TimelineEntry } from '@/services/campaigns'
import { getReport, type ReportDetail } from '@/services/reports'
import { getReportEvaluationSummary, type EvaluationSummary } from '@/services/evaluations'
import { selectPreviousEntry } from '@/composables/useCampaignPairing'
import { ApiError } from '@/services/http'

export type PreviousReportStatus =
  | 'idle'
  | 'loading'
  | 'no_campaign'
  | 'no_previous'
  | 'ready'
  | 'error'

export interface UseWriterPreviousReportParams {
  token: string
  exerciseId: string
  reportId: string
  teamId: string
}

export interface UseWriterPreviousReportResult {
  status: Ref<PreviousReportStatus>
  error: Ref<string | null>
  previousReport: Ref<ReportDetail | null>
  /** Null while the previous report isn't evaluated yet (or scores are hidden by
   *  `teams_see_own_scores`) — a normal state, never surfaced as `status: 'error'`. */
  previousSummary: Ref<EvaluationSummary | null>
  load: () => Promise<void>
}

async function findEntries(params: UseWriterPreviousReportParams): Promise<TimelineEntry[] | null> {
  const all = await listCampaigns(params.token, params.exerciseId)
  for (const c of all) {
    const entries = await getCampaignTimeline(params.token, params.exerciseId, c.id)
    if (entries.some((e) => e.report_id === params.reportId)) return entries
  }
  return null
}

/**
 * Writer-scoped analogue of `useCampaignPairing`: finds the same-team predecessor of the
 * current report in its campaign and fetches its content PLUS its evaluation summary — never
 * blocking on the predecessor's grading status (the campaign view is always available; only
 * the summary's presence is conditional). Reuses `selectPreviousEntry`, not
 * `useCampaignPairing` wholesale, since that composable also pulls evaluator-only data this
 * writer-facing screen has no reason to fetch.
 */
export function useWriterPreviousReport(
  params: UseWriterPreviousReportParams,
): UseWriterPreviousReportResult {
  const status = ref<PreviousReportStatus>('idle')
  const error = ref<string | null>(null)
  const previousReport = ref<ReportDetail | null>(null)
  const previousSummary = ref<EvaluationSummary | null>(null)

  async function load(): Promise<void> {
    status.value = 'loading'
    error.value = null
    try {
      const entries = await findEntries(params)
      if (entries === null) {
        status.value = 'no_campaign'
        return
      }
      const prev = selectPreviousEntry(entries, params.reportId, params.teamId)
      if (prev === null) {
        status.value = 'no_previous'
        return
      }
      previousReport.value = await getReport(params.token, params.exerciseId, prev.report_id)
      try {
        previousSummary.value = await getReportEvaluationSummary(
          params.token,
          params.exerciseId,
          prev.report_id,
        )
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) previousSummary.value = null
        else throw e
      }
      status.value = 'ready'
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'failed to load the previous report'
      status.value = 'error'
    }
  }

  return { status, error, previousReport, previousSummary, load }
}
