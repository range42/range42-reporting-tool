import { apiGet } from '@/services/http'

export interface Team {
  id: string
  exercise_id: string
  name: string
  team_type: string
  color: string | null
}

export const listTeams = (token: string, exerciseId: string): Promise<Team[]> =>
  apiGet<Team[]>(`/api/v1/exercises/${exerciseId}/teams`, token)
