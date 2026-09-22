import { apiDelete, apiGet, apiPatch, apiPost } from '@/services/http'

export interface TeamTypeConfig {
  id: string
  exercise_id: string
  type_key: string
  display_label: string
  default_color: string | null
  is_visible_to_others: boolean
}

export interface TeamTypeConfigCreateInput {
  type_key: string
  display_label: string
  default_color?: string | null
  is_visible_to_others?: boolean
}

export type TeamTypeConfigUpdateInput = Partial<{
  display_label: string
  default_color: string | null
  is_visible_to_others: boolean
}>

const base = (exerciseId: string): string => `/api/v1/exercises/${exerciseId}/team-types`

export const listTeamTypes = (token: string, exerciseId: string): Promise<TeamTypeConfig[]> =>
  apiGet<TeamTypeConfig[]>(base(exerciseId), token)

export const createTeamType = (
  token: string,
  exerciseId: string,
  body: TeamTypeConfigCreateInput,
): Promise<TeamTypeConfig> => apiPost<TeamTypeConfig>(base(exerciseId), body, token)

export const updateTeamType = (
  token: string,
  exerciseId: string,
  typeId: string,
  body: TeamTypeConfigUpdateInput,
): Promise<TeamTypeConfig> => apiPatch<TeamTypeConfig>(`${base(exerciseId)}/${typeId}`, body, token)

export const deleteTeamType = (token: string, exerciseId: string, typeId: string): Promise<void> =>
  apiDelete(`${base(exerciseId)}/${typeId}`, token)
