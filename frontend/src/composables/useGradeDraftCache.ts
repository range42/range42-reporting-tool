import { createDraftCache, type DraftCache } from '@/lib/draftCache'
import type { GradeUpsertInput } from '@/services/evaluations'

/**
 * Per-section grade drafts, surviving a reload while a save is still pending.
 *
 * Keyed by `evaluationId:sectionId`, never by section alone: two evaluators grade the same
 * report sections in the same browser profile during a debrief, and a section-only key would
 * hand one evaluator the other's unsaved numbers — the isolation the whole slice is built on.
 */
export function useGradeDraftCache(evaluationId: string): DraftCache<GradeUpsertInput> {
  return createDraftCache<GradeUpsertInput>(
    (sectionId) => `r42:grade-draft:${evaluationId}:${sectionId}`,
  )
}
