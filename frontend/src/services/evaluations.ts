import { apiGet, apiPatch, apiPost, apiPut } from '@/services/http'
import type { RubricCriterion } from '@/services/templates'
import { formatGrade } from '@/lib/decimal'

export type EvaluationStatus = 'assigned' | 'in_progress' | 'completed'

export type GradeMode = 'not_graded' | 'numeric' | 'pass_fail' | 'rubric'

/** One rubric criterion's score (mirrors the backend `RubricScoreEntry`). */
export interface RubricScoreEntry {
  criterion: string
  score: number
  note?: string | null
}

/** A stored section grade. `grade` stays a two-decimal STRING on the wire. */
export interface SectionGrade {
  id: string
  evaluation_id: string
  report_section_id: string
  grade: string | null
  pass_fail_result: boolean | null
  rubric_scores: RubricScoreEntry[] | null
  feedback: string | null
  created_at: string
  updated_at: string
}

/**
 * Evaluator-facing section view — the only place the evaluator-only template fields
 * (`evaluation_criteria`, `rubric_criteria`, the grade bounds) are exposed (L12).
 */
export interface GradableSection {
  report_section_id: string
  section_def_id: string
  name: string
  description: string | null
  position: number
  field_type: string
  content: string | null
  content_plain: string | null
  choice_values: string[] | null
  grade_mode: GradeMode
  grade_min: string | null
  grade_max: string | null
  grade_weight: string
  rubric_criteria: RubricCriterion[] | null
  evaluation_criteria: string | null
  grade: SectionGrade | null
}

export interface Evaluation {
  id: string
  report_id: string
  evaluator_id: string
  status: EvaluationStatus
  overall_feedback: string | null
  overall_grade: string | null
  completed_at: string | null
  reopen_count: number
  graded_section_count: number
  gradable_section_count: number
  created_at: string
  updated_at: string
}

/** `GET .../evaluations/{evid}`. Carries `grade_version` so a client can detect that a
 *  reopen invalidated published numbers (D19). */
export interface EvaluationDetail extends Evaluation {
  report_name: string
  report_status: string
  /** Served here because an evaluator outside the report's team may not read the report row. */
  team_name: string
  submitted_at: string | null
  grade_version: number
  sections: GradableSection[]
}

/** Report-level numbers, identical for every caller allowed to see the breakdown at all. */
export interface BreakdownAggregate {
  overall_grade: string | null
  grade_version: number
  counted_evaluator_count: number
  completed_evaluator_count: number
  aggregated_weight_total: string
}

/** One evaluator's line. Peer names, weights and timestamps are null for a non-admin caller. */
export interface EvaluationBreakdownRow {
  id: string
  evaluator_id: string
  evaluator_display_name: string | null
  status: EvaluationStatus
  overall_grade: string | null
  aggregated_weight: string
  completed_at: string | null
  finalized_by: string | null
  finalize_is_admin_override: boolean
  unassigned_at: string | null
  unassign_reason: string | null
  reopen_count: number
}

/** `GET .../evaluations` — the W5-3 breakdown that replaced W5-1's plain list. */
export interface EvaluationBreakdown {
  report_id: string
  report_status: string
  finalize_policy: string
  finalize_gate_satisfied: boolean
  aggregate: BreakdownAggregate
  evaluations: EvaluationBreakdownRow[]
}

/** A section-grade write. `grade` is a number here and is serialized to two decimals. */
export type GradeUpsertInput = Partial<{
  grade: number | null
  pass_fail_result: boolean | null
  rubric_scores: RubricScoreEntry[] | null
  feedback: string | null
}>

/** D2's admin deadlock exit: finalize in an absent evaluator's name, with a mandatory comment. */
export type FinalizeInput = Partial<{
  on_behalf_of: string | null
  comment: string | null
}>

/** Every path is report-nested — there is no flat `/evaluations/{id}` surface. */
const base = (exerciseId: string, rid: string): string =>
  `/api/v1/exercises/${exerciseId}/reports/${rid}/evaluations`

/** One row of the caller's own evaluator queue (`GET /exercises/{id}/evaluations`). */
export interface EvaluationAssignment {
  id: string
  report_id: string
  report_name: string
  report_status: string
  team_id: string
  team_name: string
  template_name: string
  due_at: string | null
  submitted_at: string | null
  status: EvaluationStatus
  graded_section_count: number
  gradable_section_count: number
}

/**
 * The caller's own assignments in an exercise, deadline-ordered.
 *
 * Own rows only — there is no `assignee` parameter, by design: a queue that could be pointed
 * at another evaluator would be a peer-visibility surface.
 */
export const listMyEvaluations = (
  token: string,
  exerciseId: string,
): Promise<EvaluationAssignment[]> =>
  apiGet<EvaluationAssignment[]>(`/api/v1/exercises/${exerciseId}/evaluations`, token)

export const listEvaluationsForReport = (
  token: string,
  exerciseId: string,
  rid: string,
): Promise<EvaluationBreakdown> => apiGet<EvaluationBreakdown>(base(exerciseId, rid), token)

export const getEvaluation = (
  token: string,
  exerciseId: string,
  rid: string,
  evid: string,
): Promise<EvaluationDetail> => apiGet<EvaluationDetail>(`${base(exerciseId, rid)}/${evid}`, token)

export const putGrade = (
  token: string,
  exerciseId: string,
  rid: string,
  evid: string,
  sectionId: string,
  input: GradeUpsertInput,
): Promise<SectionGrade> => {
  // Only the keys the caller actually set are sent: the route picks the legal grading
  // channel from the section's grade_mode, and an unasked-for null is a channel switch.
  const body: Record<string, unknown> = {}
  if ('grade' in input) body.grade = formatGrade(input.grade)
  if ('pass_fail_result' in input) body.pass_fail_result = input.pass_fail_result
  if ('rubric_scores' in input) body.rubric_scores = input.rubric_scores
  if ('feedback' in input) body.feedback = input.feedback
  return apiPut<SectionGrade>(`${base(exerciseId, rid)}/${evid}/grades/${sectionId}`, body, token)
}

/** `PATCH .../evaluations/{evid}` — overall feedback only; the grade is never set here
 *  (A7: `rollup.py` is the sole writer of a grade). */
export const updateEvaluation = (
  token: string,
  exerciseId: string,
  rid: string,
  evid: string,
  body: { overall_feedback: string | null },
): Promise<Evaluation> => apiPatch<Evaluation>(`${base(exerciseId, rid)}/${evid}`, body, token)

export const finalizeEvaluation = (
  token: string,
  exerciseId: string,
  rid: string,
  evid: string,
  input: FinalizeInput = {},
): Promise<EvaluationBreakdown> =>
  apiPost<EvaluationBreakdown>(`${base(exerciseId, rid)}/${evid}/finalize`, input, token)

/** Global Admin only, and `reason` is mandatory — the handler refuses a blank one. */
export const reopenEvaluation = (
  token: string,
  exerciseId: string,
  rid: string,
  evid: string,
  reason: string,
): Promise<EvaluationBreakdown> =>
  apiPost<EvaluationBreakdown>(`${base(exerciseId, rid)}/${evid}/reopen`, { reason }, token)
