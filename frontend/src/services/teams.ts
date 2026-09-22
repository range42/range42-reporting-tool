import { apiDelete, apiGet, apiPost } from '@/services/http'

export interface Team {
  id: string
  exercise_id: string
  name: string
  team_type: string
  color: string | null
}

export interface TeamMemberSummary {
  id: string
  user_id: string
  display_name: string
  email: string
  created_at: string
}

export const listTeams = (token: string, exerciseId: string): Promise<Team[]> =>
  apiGet<Team[]>(`/api/v1/exercises/${exerciseId}/teams`, token)

export const listTeamMembers = (
  token: string,
  exerciseId: string,
  teamId: string,
): Promise<TeamMemberSummary[]> =>
  apiGet<TeamMemberSummary[]>(`/api/v1/exercises/${exerciseId}/teams/${teamId}/members`, token)

/** One evaluator assigned to a team, independent of any campaign. */
export interface TeamEvaluatorSummary {
  id: string
  team_id: string
  evaluator_id: string
  display_name: string
  email: string
  created_at: string
}

export const listTeamEvaluators = (
  token: string,
  exerciseId: string,
  teamId: string,
): Promise<TeamEvaluatorSummary[]> =>
  apiGet<TeamEvaluatorSummary[]>(
    `/api/v1/exercises/${exerciseId}/teams/${teamId}/evaluators`,
    token,
  )

export const addTeamEvaluator = (
  token: string,
  exerciseId: string,
  teamId: string,
  evaluatorId: string,
): Promise<TeamEvaluatorSummary> =>
  apiPost<TeamEvaluatorSummary>(
    `/api/v1/exercises/${exerciseId}/teams/${teamId}/evaluators`,
    { evaluator_id: evaluatorId },
    token,
  )

export const removeTeamEvaluator = (
  token: string,
  exerciseId: string,
  teamId: string,
  evaluatorId: string,
): Promise<void> =>
  apiDelete(`/api/v1/exercises/${exerciseId}/teams/${teamId}/evaluators/${evaluatorId}`, token)
