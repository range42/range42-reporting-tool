import { apiDelete, apiGet, apiPatch, apiPost } from '@/services/http'

export interface Team {
  id: string
  exercise_id: string
  name: string
  team_type: string
  color: string | null
}

export interface TeamCreateInput {
  name: string
  team_type: string
  color?: string | null
}

export type TeamUpdateInput = Partial<{
  name: string
  team_type: string
  color: string | null
}>

export interface TeamMemberSummary {
  id: string
  user_id: string
  display_name: string
  email: string
  created_at: string
}

export const listTeams = (token: string, exerciseId: string): Promise<Team[]> =>
  apiGet<Team[]>(`/api/v1/exercises/${exerciseId}/teams`, token)

export const createTeam = (
  token: string,
  exerciseId: string,
  body: TeamCreateInput,
): Promise<Team> => apiPost<Team>(`/api/v1/exercises/${exerciseId}/teams`, body, token)

export const updateTeam = (
  token: string,
  exerciseId: string,
  teamId: string,
  body: TeamUpdateInput,
): Promise<Team> => apiPatch<Team>(`/api/v1/exercises/${exerciseId}/teams/${teamId}`, body, token)

export const deleteTeam = (token: string, exerciseId: string, teamId: string): Promise<void> =>
  apiDelete(`/api/v1/exercises/${exerciseId}/teams/${teamId}`, token)

export const listTeamMembers = (
  token: string,
  exerciseId: string,
  teamId: string,
): Promise<TeamMemberSummary[]> =>
  apiGet<TeamMemberSummary[]>(`/api/v1/exercises/${exerciseId}/teams/${teamId}/members`, token)

export const addTeamMember = (
  token: string,
  exerciseId: string,
  teamId: string,
  userId: string,
): Promise<TeamMemberSummary> =>
  apiPost<TeamMemberSummary>(
    `/api/v1/exercises/${exerciseId}/teams/${teamId}/members`,
    { user_id: userId },
    token,
  )

export const removeTeamMember = (
  token: string,
  exerciseId: string,
  teamId: string,
  userId: string,
): Promise<void> =>
  apiDelete(`/api/v1/exercises/${exerciseId}/teams/${teamId}/members/${userId}`, token)

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
