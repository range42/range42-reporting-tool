import { apiGet } from '@/services/http'

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
